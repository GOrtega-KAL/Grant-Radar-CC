# een.py — conector EEN (Enterprise Europe Network)
#
# Dos canales del portal EEN: noticias de financiación y perfiles de
# cooperación I+D con bloque "Call details". Solo entra lo que apunta a una
# convocatoria oficial verificable con plazo confirmado — las búsquedas de
# socios sin convocatoria detrás son oportunidades de colaboración, no de
# financiación, y se descartan con registro en la auditoría.
#
# Sin Playwright, sin caché y sin Claude: HTTP público, filtro de relevancia y
# los helpers de texto de convocatoria compartidos (grant_radar/call_text.py).

import logging
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from grant_radar.audit import audit_exclusion
from grant_radar.call_text import (
    FUNDING_CONTEXT_TERMS,
    _external_links,
    _extract_deadline_from_text,
    _funding_mechanism,
    _official_call_identifier,
)
from grant_radar.http_client import _http_get
from grant_radar.parsing_helpers import (
    _days_until,
    _fold_text,
    _parse_flexible_date,
    select_evidence_excerpt,
)
from grant_radar.runtime_state import SOURCE_RUNTIME_METADATA
from grant_radar.tech_taxonomy import keyword_match

log = logging.getLogger("grant_radar")


# ── EEN: noticias de ayudas y calls verificables en perfiles I+D ─────────────
EEN_BASE = "https://een.ec.europa.eu"
EEN_MAX_NEWS_PAGES = 8
EEN_MAX_PROFILE_PAGES = 30
EEN_RD_REQUEST_FILTER = "p:4355"
EEN_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/127 Safari/537.36"
    )
}


def _een_listing_params(channel: str, page: int) -> dict:
    params = {"page": page}
    if channel == "profile":
        params["f[0]"] = EEN_RD_REQUEST_FILTER
    return params


def _een_profile_call_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    """Extrae el enlace del bloque Call details, no la web del socio."""
    links = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url, anchor.get("href", "")).strip()
        if not href.startswith("https://") or urlparse(href).netloc == urlparse(page_url).netloc:
            continue
        folded_href = _fold_text(href)
        if (
            bool(re.search(r"(?:^|[-_/])call(?:$|[-_/])", folded_href))
            or any(
                token in folded_href
                for token in (
                    "funding-tenders",
                    "/opportunities/",
                    "/open-call",
                    "/open_calls",
                    "/calls/",
                    "call-for-proposal",
                    "call-for-project",
                    "calls-proposal",
                )
            )
        ):
            links.append(href)
    return list(dict.fromkeys(links))


def _een_call_from_page(url: str, html: str, channel: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h1") or soup.find("h2")
    page_title = " ".join(heading.get_text(" ", strip=True).split()) if heading else ""
    main = soup.find("main") or soup
    text = " ".join(main.get_text(" ", strip=True).split())
    folded = _fold_text(text)
    has_funding = any(term in folded for term in FUNDING_CONTEXT_TERMS)
    call_details = "call details" in folded or "deadline of the call" in folded
    if channel == "profile" and not call_details:
        return None
    if not has_funding and not call_details:
        return None
    identifier = _official_call_identifier(text)
    call_title = page_title
    title_match = re.search(
        r"Call title and identifier\s+(.{8,350}?)(?:Submission and evaluation scheme|Coordinator required|Deadline for EoI|Deadline of the call)",
        text,
        re.IGNORECASE,
    )
    if title_match:
        call_title = " ".join(title_match.group(1).split())
    deadline_date = ""
    deadline_match = re.search(
        r"Deadline of the call\s+(.{4,50}?)(?:Project duration|Web link|Dissemination|$)",
        text,
        re.IGNORECASE,
    )
    if deadline_match:
        deadline_date = _parse_flexible_date(deadline_match.group(1))
    if not deadline_date:
        deadline_date = _extract_deadline_from_text(text)
    eoi_deadline_date = ""
    eoi_match = re.search(
        r"Deadline for EoI\s+(.{4,50}?)(?:Deadline of the call|Project duration|Web link|$)",
        text,
        re.IGNORECASE,
    )
    if eoi_match:
        eoi_deadline_date = _parse_flexible_date(eoi_match.group(1))
    if deadline_date and _days_until(deadline_date) <= 0:
        return None
    if not deadline_date:
        return None
    if channel == "profile":
        official_links = _een_profile_call_links(soup, url)
    else:
        official_links = [
            link for link in _external_links(soup, url)
            if any(token in _fold_text(link) for token in (
                "funding", "tender", "open-call", "opportunities", "call", "apply",
            ))
        ]
    if channel == "profile" and not official_links:
        return None
    official_url = official_links[0] if official_links else url
    source = "HORIZON EUROPE" if identifier.startswith("HORIZON-") else "EEN"
    return {
        "source": source,
        "identifier": identifier,
        "title": call_title[:500],
        "description": select_evidence_excerpt(text, call_title, 20_000),
        "deadline_days": _days_until(deadline_date) if deadline_date else 90,
        "deadline_date": deadline_date,
        "eoi_deadline_date": eoi_deadline_date,
        "open_date": "",
        "fecha_sin_confirmar": not bool(deadline_date),
        "budget": "Ver convocatoria",
        "url": official_url,
        "keywords_found": keyword_match(text),
        "org": "Enterprise Europe Network",
        "source_type": f"Scraping EEN ({channel})",
        "funding_mechanism": _funding_mechanism(text),
        "document_role": "external_call_landing",
        "discovery_sources": ["EEN"],
        "related_documents_trace": [{
            "source": "EEN", "title": page_title, "url": url,
            "document_role": "source_record",
        }],
        "related_document_contents": [{
            "source": "EEN", "title": page_title, "url": url,
            "document_role": "source_record",
            "description": select_evidence_excerpt(text, page_title, 10_000),
        }],
    }


def fetch_een_funding() -> list:
    log.info("Consultando EEN (noticias de financiación y Call details)...")
    session = requests.Session()
    candidates = []
    seen = set()
    pages_read = 0

    def collect_listing(path: str, max_pages: int, channel: str) -> None:
        nonlocal pages_read
        for page in range(max_pages):
            response = _http_get(
                f"{EEN_BASE}{path}",
                params=_een_listing_params(channel, page),
                session=session,
                headers=EEN_BROWSER_HEADERS,
            )
            if response is None:
                break
            pages_read += 1
            soup = BeautifulSoup(response.text, "html.parser")
            prefix = "/news/" if channel == "news" else "/partnering-opportunities/"
            page_links = []
            for anchor in soup.find_all("a", href=True):
                href = urljoin(EEN_BASE, anchor.get("href", ""))
                label = _fold_text(anchor.get_text(" ", strip=True))
                if prefix not in href or href in seen:
                    continue
                if channel == "news" and not any(
                    term in label for term in ("call", "grant", "fund", "financ", "aid")
                ):
                    continue
                seen.add(href)
                page_links.append(href)
            if not page_links and page:
                break
            candidates.extend((href, channel) for href in page_links)
            time.sleep(0.1)

    collect_listing("/news", EEN_MAX_NEWS_PAGES, "news")
    collect_listing("/partnering-opportunities", EEN_MAX_PROFILE_PAGES, "profile")
    results = []
    rejected_profiles = 0
    for url, channel in candidates:
        response = _http_get(
            url, session=session, timeout=20, retries=2, headers=EEN_BROWSER_HEADERS
        )
        if response is None:
            continue
        item = _een_call_from_page(url, response.text, channel)
        if item:
            results.append(item)
        elif channel == "profile":
            rejected_profiles += 1
            audit_exclusion(
                {"source": "EEN", "title": url.rsplit("/", 1)[-1], "url": url},
                "partner_profile_without_verifiable_call",
                "een_profile_filter",
            )
    SOURCE_RUNTIME_METADATA["EEN"] = {
        "status": "ok" if pages_read else "warn",
        "strategy": "noticias de ayudas + Call details verificables",
        "pages_read": pages_read,
        "candidate_pages": len(candidates),
        "partner_profiles_rejected": rejected_profiles,
        "profile_filter": EEN_RD_REQUEST_FILTER,
    }
    log.info(f"  → {len(results)} subvenciones verificables descubiertas en EEN")
    return results
