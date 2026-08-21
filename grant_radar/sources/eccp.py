# eccp.py — conector ECCP (European Cluster Collaboration Platform)
#
# Inventario de calls de la plataforma y, cuando una call apunta a proyectos
# beneficiarios, un rastreo acotado de sus webs para encontrar convocatorias en
# cascada que no aparecen en el listado.
#
# Ese rastreo es la parte delicada: se eligió su profundidad con un experimento
# auditable de niveles 0-3 (AGENTS.md sección 3), y respeta `robots.txt`,
# HTTPS y límites de peticiones, bytes y tiempo por dominio. La prueba del
# 04/08/2026 seleccionó profundidad 1: mediana de una petición externa por
# call, mientras que el nivel 2 elevaba el total de 6 a 22 peticiones y
# activaba la parada por coste.
#
# **`is_relevant_enough` se recibe como parámetro a propósito.** El conector
# necesita descartar páginas y muestras evidentemente irrelevantes, pero no
# debe conocer las reglas de negocio: recibe un predicado
# `conv -> {"decision": ...}` y el script principal le pasa
# `deterministic_prefilter()`, que sigue viviendo allí junto al resto de la
# matriz previa a Claude (AGENTS.md sección 4.1). Así este módulo se pudo
# extraer sin mover ni una línea de esas reglas, y se puede probar con un
# predicado de mentira. Si algún día la matriz se extrae a su propio módulo,
# este parámetro puede quedarse igual —hace explícita la dependencia— o
# sustituirse por un import directo.

import logging
import re
import statistics
import time
import urllib.robotparser
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from grant_radar.audit import audit_exclusion
from grant_radar.call_text import (
    CALL_LINK_TERMS,
    FUNDING_CONTEXT_TERMS,
    _extract_deadline_from_text,
    _extract_funding_budget,
    _external_links,
    _funding_mechanism,
    _official_call_identifier,
)
from grant_radar.http_client import HTTP_USER_AGENT, _http_get
from grant_radar.parsing_helpers import _days_until, _fold_text, select_evidence_excerpt
from grant_radar.runtime_state import RUN_DIAGNOSTICS, SOURCE_RUNTIME_METADATA
from grant_radar.source_health import assess_web_inventory_health
from grant_radar.tech_taxonomy import keyword_match

log = logging.getLogger("grant_radar")


# ── ECCP: calls y documentos de proyectos beneficiarios ─────────────────────
ECCP_BASE = "https://www.clustercollaboration.eu"
ECCP_MAX_LIST_PAGES = 25
ECCP_EXPERIMENT_MAX_CALLS = 20
ECCP_DOMAIN_MAX_PAGES = 10
ECCP_DOMAIN_MAX_BYTES = 5 * 1024 * 1024
ECCP_DOMAIN_MAX_SECONDS = 20
ECCP_DETAIL_WORKERS = 4
ECCP_SELECTED_CRAWL_DEPTH = 1
ECCP_MIN_EXPECTED_INVENTORY = 10


def _parse_eccp_inventory_html(page_url: str, html: str) -> dict:
    """Extrae las fichas y la siguiente página sin depender de clases antiguas."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".search-result-item")
    containers = cards or [soup]
    detail_urls = []
    for container in containers:
        for anchor in container.find_all("a", href=True):
            href = urljoin(page_url, anchor.get("href", ""))
            if (
                "/content/" in href
                and not href.rstrip("/").endswith("/expertise")
                and href not in detail_urls
            ):
                detail_urls.append(href)
    next_anchor = soup.find("a", rel="next")
    if next_anchor is None:
        next_anchor = soup.select_one(
            '.pager a[aria-label="Next page"], .pager__item--next a'
        )
    next_url = (
        urljoin(page_url, next_anchor.get("href", ""))
        if next_anchor and next_anchor.get("href") else ""
    )
    return {
        "detail_urls": detail_urls,
        "next_url": next_url,
        "structure_ok": bool(cards) and bool(soup.select_one("nav.pager")),
    }


def _fetch_eccp_detail_html(url: str) -> tuple[str, str]:
    """Carga una ficha ECCP con sesión aislada para concurrencia moderada."""
    response = _http_get(
        url, session=requests.Session(), timeout=20, retries=2,
    )
    return url, response.text if response is not None else ""


def _robots_allows(url: str, session: requests.Session) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    response = _http_get(robots_url, session=session, timeout=8, retries=1)
    if response is None:
        return True
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser.can_fetch(HTTP_USER_AGENT, url)


def _crawl_project_domain(
    start_url: str,
    max_depth: int,
    session: requests.Session,
    is_relevant_enough,
) -> dict:
    started = time.perf_counter()
    host = urlparse(start_url).netloc.casefold()
    queue = deque([(start_url, 1)])
    seen = set()
    documents = []
    total_bytes = 0
    irrelevant = 0
    errors = 0
    if not _robots_allows(start_url, session):
        return {"documents": [], "requests": 0, "bytes": 0, "irrelevant": 0, "errors": 1}
    while queue and len(seen) < ECCP_DOMAIN_MAX_PAGES:
        if time.perf_counter() - started > ECCP_DOMAIN_MAX_SECONDS:
            break
        url, depth = queue.popleft()
        clean_url = re.sub(r"#.*$", "", url)
        if clean_url in seen or urlparse(clean_url).netloc.casefold() != host:
            continue
        seen.add(clean_url)
        response = _http_get(clean_url, session=session, timeout=12, retries=1)
        if response is None:
            errors += 1
            continue
        total_bytes += len(response.content)
        if total_bytes > ECCP_DOMAIN_MAX_BYTES:
            break
        content_type = response.headers.get("content-type", "").casefold()
        if "html" not in content_type:
            if any(term in _fold_text(clean_url) for term in CALL_LINK_TERMS):
                documents.append({
                    "source": "PROJECT WEBSITE",
                    "title": clean_url.rsplit("/", 1)[-1],
                    "url": clean_url,
                    "document_role": "beneficiary_project_call",
                    "description": "",
                })
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        text = " ".join(soup.get_text(" ", strip=True).split())
        label = _fold_text(f"{clean_url} {text[:5000]}")
        has_call_signal = any(term in label for term in CALL_LINK_TERMS)
        relevance = is_relevant_enough({
            "title": soup.title.get_text(" ", strip=True) if soup.title else "",
            "description": text,
        })
        if has_call_signal and relevance["decision"] != "reject":
            documents.append({
                "source": "PROJECT WEBSITE",
                "title": soup.title.get_text(" ", strip=True) if soup.title else clean_url,
                "url": clean_url,
                "document_role": "beneficiary_project_call",
                "description": select_evidence_excerpt(text, "", 10_000),
            })
        else:
            irrelevant += 1
        if depth < max_depth:
            for anchor in soup.find_all("a", href=True):
                href = urljoin(clean_url, anchor.get("href", ""))
                anchor_label = _fold_text(f"{anchor.get_text(' ', strip=True)} {href}")
                if (
                    urlparse(href).scheme == "https"
                    and urlparse(href).netloc.casefold() == host
                    and any(term in anchor_label for term in CALL_LINK_TERMS)
                ):
                    queue.append((href, depth + 1))
    return {
        "documents": documents,
        "requests": len(seen),
        "bytes": total_bytes,
        "irrelevant": irrelevant,
        "errors": errors,
        "seconds": round(time.perf_counter() - started, 3),
    }


def _eccp_call_from_html(url: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    heading_titles = [
        " ".join(heading.get_text(" ", strip=True).split())
        for heading in soup.find_all(["h1", "h2"])
        if _fold_text(heading.get_text(" ", strip=True)) not in {
            "opportunity", "funding opportunity", "call", "calls",
        }
    ]
    title = max(heading_titles, key=len, default="")
    if not title:
        meta_title = soup.find("meta", attrs={"property": "og:title"})
        title = str(meta_title.get("content", "")).strip() if meta_title else ""
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True).split("|")[0].strip()
    main = soup.find("main") or soup
    text = " ".join(main.get_text(" ", strip=True).split())
    folded = _fold_text(text)
    if not title or not any(term in folded for term in FUNDING_CONTEXT_TERMS):
        return None
    if "partner request" in folded and not any(
        term in folded for term in ("grant", "funding", "financial support")
    ):
        return None
    deadline_date = _extract_deadline_from_text(text)
    if deadline_date and _days_until(deadline_date) <= 0:
        return None
    return {
        "source": "ECCP",
        "identifier": _official_call_identifier(f"{url} {text}"),
        "title": title[:500],
        "description": select_evidence_excerpt(text, title, 20_000),
        "deadline_days": _days_until(deadline_date) if deadline_date else 90,
        "deadline_date": deadline_date,
        "open_date": "",
        "fecha_sin_confirmar": not bool(deadline_date),
        "budget": _extract_funding_budget(text),
        "url": url,
        "keywords_found": keyword_match(text),
        "org": "European Cluster Collaboration Platform",
        "source_type": "Scraping HTML ECCP",
        "funding_mechanism": _funding_mechanism(text),
        "document_role": "external_call_landing",
        "discovery_sources": ["ECCP"],
        "related_document_contents": [],
        # El pie global contiene redes sociales, avisos legales y newsletter.
        # Solo los enlaces del contenido principal pueden ser landings de la call.
        "external_project_links": _external_links(main, url),
    }


def _choose_eccp_depth(metrics: list[dict]) -> int:
    chosen = 0
    previous_fields = metrics[0]["critical_fields"] if metrics else 0
    previous_requests = max(metrics[0]["requests"], 1) if metrics else 1
    for metric in metrics[1:]:
        calls_gain = metric.get("unique_call_gain_pct", 0)
        field_gain = (
            (metric["critical_fields"] - previous_fields) / max(previous_fields, 1) * 100
        )
        noise = metric["irrelevant"] / max(metric["requests"], 1) * 100
        if noise > 50 or (
            metric["depth"] > 1 and metric["requests"] >= previous_requests * 2
        ):
            break
        if (
            (calls_gain >= 5 or field_gain >= 10)
            and metric.get("median_requests_per_call", 0) <= 5
            and noise < 30
        ):
            chosen = metric["depth"]
        if calls_gain < 2 and field_gain < 5:
            break
        previous_fields = metric["critical_fields"]
        previous_requests = max(metric["requests"], 1)
    return chosen


def fetch_eccp(is_relevant_enough) -> list:
    log.info("Consultando ECCP (calls y webs oficiales enlazadas)...")
    session = requests.Session()
    detail_urls = []
    pages_read = 0
    listing_errors = 0
    structure_ok = True
    next_page_url = f"{ECCP_BASE}/search-results?type=eccp_calls&page=0"
    visited_pages = set()
    while next_page_url and pages_read < ECCP_MAX_LIST_PAGES:
        if next_page_url in visited_pages:
            listing_errors += 1
            break
        visited_pages.add(next_page_url)
        response = _http_get(
            next_page_url,
            session=session,
        )
        if response is None:
            listing_errors += 1
            break
        pages_read += 1
        inventory_page = _parse_eccp_inventory_html(response.url, response.text)
        page_links = inventory_page["detail_urls"]
        structure_ok = structure_ok and (
            inventory_page["structure_ok"] or not page_links
        )
        if not page_links:
            break
        detail_urls.extend(
            href for href in page_links if href not in detail_urls
        )
        next_page_url = inventory_page["next_url"]
        time.sleep(0.1)

    results = []
    loaded_details = []
    if detail_urls:
        with ThreadPoolExecutor(max_workers=ECCP_DETAIL_WORKERS) as executor:
            loaded_details = list(executor.map(_fetch_eccp_detail_html, detail_urls))
    detail_loaded = 0
    dated_details = 0
    for url, html in loaded_details:
        if not html:
            continue
        detail_loaded += 1
        soup = BeautifulSoup(html, "html.parser")
        main = soup.find("main") or soup
        detail_text = " ".join(main.get_text(" ", strip=True).split())
        dated_details += int(bool(_extract_deadline_from_text(detail_text)))
        item = _eccp_call_from_html(url, html)
        if item:
            results.append(item)

    sample = [
        item for item in results
        if is_relevant_enough(item)["decision"] != "reject"
    ][:ECCP_EXPERIMENT_MAX_CALLS]
    base_fields = sum(
        bool(item.get(field)) for item in sample
        for field in ("deadline_date", "budget", "description", "url")
    )
    metrics = [{
        "depth": 0, "requests": 0, "bytes": 0, "irrelevant": 0,
        "errors": 0, "critical_fields": base_fields,
        "median_requests_per_call": 0, "unique_call_gain_pct": 0,
    }]
    selected_depth = ECCP_SELECTED_CRAWL_DEPTH
    per_call_requests = []
    crawl_totals = {
        "requests": 0, "bytes": 0, "irrelevant": 0, "errors": 0,
        "documents": 0,
    }
    if selected_depth:
        for item in sample:
            aggregate = {
                "documents": [], "requests": 0, "bytes": 0,
                "irrelevant": 0, "errors": 0,
            }
            for link in item.get("external_project_links", [])[:2]:
                crawl = _crawl_project_domain(
                    link, selected_depth, session, is_relevant_enough,
                )
                for key in ("requests", "bytes", "irrelevant", "errors"):
                    aggregate[key] += crawl.get(key, 0)
                aggregate["documents"].extend(crawl.get("documents", []))
            per_call_requests.append(aggregate["requests"])
            for key in ("requests", "bytes", "irrelevant", "errors"):
                crawl_totals[key] += aggregate[key]
            crawl_totals["documents"] += len(aggregate["documents"])
            item["related_document_contents"] = aggregate["documents"]
            item["related_documents_trace"] = [
                {key: document.get(key, "") for key in (
                    "source", "title", "url", "document_role",
                )}
                for document in aggregate["documents"]
            ]
            item["related_documents_count"] = len(aggregate["documents"])
        metrics.append({
            "depth": selected_depth,
            **{key: crawl_totals[key] for key in (
                "requests", "bytes", "irrelevant", "errors",
            )},
            "critical_fields": base_fields + crawl_totals["documents"],
            "median_requests_per_call": (
                statistics.median(per_call_requests) if per_call_requests else 0
            ),
            "unique_call_gain_pct": (
                crawl_totals["documents"] / max(len(sample), 1) * 100
            ),
        })

    health = assess_web_inventory_health(
        "ECCP",
        inventory_loaded=pages_read > 0,
        structure_ok=structure_ok,
        discovered_count=len(detail_urls),
        detail_attempted=len(detail_urls),
        detail_loaded=detail_loaded,
        dated_count=dated_details,
        published_count=len(results),
        expected_min_inventory=ECCP_MIN_EXPECTED_INVENTORY,
        expected_date_coverage=0.8,
    )
    RUN_DIAGNOSTICS["eccp_crawl_experiment"] = {
        "mode": "production_fixed_depth",
        "selection_basis": "experimento 2026-08-04",
        "sample_size": len(sample),
        "selected_depth": selected_depth,
        "metrics": metrics,
    }
    RUN_DIAGNOSTICS["eccp_scrape_audit"] = {
        "pages_read": pages_read,
        "listing_errors": listing_errors,
        "inventory_unique": len(detail_urls),
        "detail_attempted": len(detail_urls),
        "detail_loaded": detail_loaded,
        "detail_failed": len(detail_urls) - detail_loaded,
        "dated_details": dated_details,
        "active_calls": len(results),
        "health": health,
    }
    SOURCE_RUNTIME_METADATA["ECCP"] = {
        "status": "ok" if health["status"] == "healthy" else "warn",
        "strategy": "inventario HTML + fichas concurrentes + landing oficial",
        "pages_read": pages_read,
        "inventory_unique": len(detail_urls),
        "detail_loaded": detail_loaded,
        "active_calls": len(results),
        "selected_crawl_depth": selected_depth,
        "health": health,
    }
    log.info(f"  → {len(results)} calls ECCP vigentes; profundidad={selected_depth}")
    return results
