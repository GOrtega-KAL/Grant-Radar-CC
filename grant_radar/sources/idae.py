# idae.py — conector IDAE (Instituto para la Diversificación y Ahorro de la Energía)
#
# Dos inventarios distintos de la misma casa, por eso conviven aquí:
#
# - `fetch_idae()` recorre las fichas de ayudas y financiación con Chromium,
#   recupera fechas de solicitud de la propia ficha y recoge los documentos
#   oficiales enlazados (bases, extractos, modificaciones). Registra en
#   IDENTITY_LANDINGS las landings de programa que encuentra, para que otras
#   fuentes puedan identificar la misma convocatoria aunque lleguen por otro
#   camino.
# - `fetch_idae_catalog()` lee el catálogo de ayudas por ámbito (estatal,
#   Aragón y Zaragoza) y solo incorpora entradas con convocatoria abierta
#   verificable; el resto queda registrado como exclusión trazable.
#
# IDAE responde con bloqueo de WAF en las fichas de detalle pero sirve el
# inventario con normalidad: `PlaywrightBrowser` lo trata como un ámbito
# bloqueado propio y no descarta el host entero (ver AGENTS.md 31.3).

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from grant_radar.audit import audit_exclusion
from grant_radar.browser import PlaywrightBrowser
from grant_radar.call_text import _extract_funding_budget
from grant_radar.dedup import _document_role
from grant_radar.http_client import _is_safe_public_https_url
from grant_radar.parsing_helpers import (
    _absolute_url,
    _date_to_iso,
    _days_until,
    _extract_application_dates,
    _fold_text,
    select_evidence_excerpt,
)
from grant_radar.runtime_state import (
    IDENTITY_LANDINGS,
    RUN_DIAGNOSTICS,
    SOURCE_RUNTIME_METADATA,
)
from grant_radar.source_health import assess_web_inventory_health
from grant_radar.tech_taxonomy import is_relevant, keyword_match

log = logging.getLogger("grant_radar")


IDAE_BASE = "https://www.idae.es"
IDAE_MAX_DETAIL_PAGES = 120
IDAE_MIN_EXPECTED_INVENTORY = 40


def _parse_idae_inventory_html(page_url: str, html: str) -> list[dict]:
    """Inventa todas las rutas de ayudas antes de aplicar relevancia temática."""
    soup = BeautifulSoup(html, "html.parser")
    records = []
    seen_urls = set()
    for anchor in soup.find_all("a", href=True):
        url = re.sub(
            r"#.*$", "", urljoin(page_url, anchor.get("href", "")).strip()
        ).rstrip("/")
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if (
            not title
            or not url.startswith(f"{IDAE_BASE}/ayudas-y-financiacion/")
            or url in seen_urls
        ):
            continue
        seen_urls.add(url)
        records.append({
            "title": title,
            "url": url,
            "explicitly_closed": "/convocatorias-cerradas" in url.casefold(),
        })
        if len(records) >= IDAE_MAX_DETAIL_PAGES:
            break
    return records


def _idae_official_document_links(root: BeautifulSoup, detail_url: str) -> list[dict]:
    documents = []
    for anchor in root.find_all("a", href=True):
        url = urljoin(detail_url, anchor.get("href", "").strip())
        title = " ".join(anchor.get_text(" ", strip=True).split())
        folded = _fold_text(f"{title} {url}")
        if not _is_safe_public_https_url(url):
            continue
        if not (
            urlparse(url).path.casefold().endswith(".pdf")
            or any(host in urlparse(url).netloc.casefold() for host in (
                "boe.es", "pap.hacienda.gob.es", "sede.idae.gob.es",
            ))
            or re.search(
                r"\b(bases|convocatoria|extracto|resolucion|modificacion)\b",
                folded,
            )
        ):
            continue
        document = {
            "source": "IDAE",
            "title": title or url.rsplit("/", 1)[-1],
            "url": url,
        }
        document["document_role"] = _document_role(document)
        if document not in documents:
            documents.append(document)
    return documents


def _scrape_idae_dates(browser: PlaywrightBrowser, url: str) -> tuple[str, str]:
    """
    Entra en la página de detalle de una convocatoria IDAE e intenta extraer
    las fechas de apertura y cierre del plazo.
    Devuelve (open_date, deadline_date) en formato YYYY-MM-DD o cadena vacía si no se encuentra.
    El IDAE publica estas fechas en distintos formatos según la página:
      - "Plazo de solicitud: DD/MM/YYYY al DD/MM/YYYY"
      - "Inicio del plazo: DD/MM/YYYY" / "Fin del plazo: DD/MM/YYYY"
      - Tablas con etiquetas "Fecha de inicio" / "Fecha de fin"
    """
    html = browser.html(url)
    if not html:
        return "", ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        return _extract_application_dates(text)
    except Exception:
        return "", ""


# Proporcion del inventario que merece abrirse. No se fija umbral de fecha
# ni de publicacion: el IDAE es una fuente de landings de programa, y que
# de 71 fichas salga una convocatoria es tambien su estado normal (seccion
# 44.6). Ese caso lo vigila la comparacion entre ejecuciones, no un umbral.
IDAE_MIN_EXPECTED_SELECTION_RATE = 0.40


def fetch_idae(browser: PlaywrightBrowser) -> list:
    """Navega con Chromium por el portal IDAE y sus páginas de detalle."""
    log.info("Consultando IDAE (Playwright)...")
    results = []

    # Patrones de títulos que son documentos/guías/planes, no convocatorias activas
    _IDAE_NOISE = re.compile(
        r"^(guía|plan nacional|documento|informe|memoria|estudio|manual|"
        r"metodología|registro|nota|presentación|borrador|resolución de "
        r"la secretaría|instrucción técnica|real decreto|orden ministerial)",
        re.IGNORECASE
    )

    # URLs verificadas del IDAE — la estructura web cambió en 2025
    urls_to_try = [
        "https://www.idae.es/ayudas-y-financiacion",
        "https://www.idae.es/financiacion-y-ayudas",
        "https://www.idae.es/convocatorias",
    ]

    soup = None
    inventory_html = ""
    inventory_url = ""
    attempted_inventory_urls = []
    for url in urls_to_try:
        attempted_inventory_urls.append(url)
        html = browser.html(url)
        if html:
            inventory_html = html
            inventory_url = url
            soup = BeautifulSoup(html, "html.parser")
            log.info(f"  IDAE accesible: {url}")
            break

    if not soup:
        log.warning("IDAE: ninguna URL accesible")
        health = assess_web_inventory_health(
            "IDAE",
            inventory_loaded=False,
            structure_ok=False,
            discovered_count=0,
            expected_min_inventory=IDAE_MIN_EXPECTED_INVENTORY,
        )
        RUN_DIAGNOSTICS["idae_scrape_audit"] = {
            "attempted_inventory_urls": attempted_inventory_urls,
            "inventory_loaded": False,
            "health": health,
        }
        SOURCE_RUNTIME_METADATA["IDAE"] = {
            "status": "warn",
            "strategy": "inventario y fichas IDAE mediante Playwright",
            "health": health,
        }
        return results

    inventory = _parse_idae_inventory_html(inventory_url, inventory_html)
    seen = set()
    skipped_closed = 0
    skipped_noise  = 0
    detail_attempted = 0
    detail_loaded = 0
    dated_details = 0
    checked = []

    def remember_programme_landing(title: str, link: str) -> None:
        """Conserva una landing sin publicarla como convocatoria activa."""
        if any(item.get("url") == link for item in IDENTITY_LANDINGS):
            return
        IDENTITY_LANDINGS.append({
            "source": "IDAE",
            "title": title,
            "description": "",
            "deadline_days": None,
            "deadline_date": "",
            "open_date": "",
            "fecha_sin_confirmar": True,
            "budget": "Ver convocatoria",
            "url": link,
            "keywords_found": [],
            "org": (
                "Instituto para la Diversificación y Ahorro de la Energía"
            ),
            "source_type": "Landing IDAE (identidad)",
            "identity_only": True,
        })

    for inventory_item in inventory:
        title = inventory_item["title"]
        link = inventory_item["url"]
        if not title or len(title) < 8 or link in seen:
            continue
        seen.add(link)
        if inventory_item["explicitly_closed"]:
            skipped_closed += 1
            audit_exclusion(
                {"source": "IDAE", "title": title, "url": link},
                "explicitly_closed_section",
                "idae_url_filter",
            )
            checked.append({
                "title": title,
                "url": link,
                "detail_loaded": False,
                "outcome": "explicitly_closed_path",
            })
            continue

        is_programme_landing = bool(re.match(
            r"^programas?\b", _fold_text(title)
        ))

        # Filtrar documentos/guías que no son convocatorias
        if _IDAE_NOISE.match(title):
            skipped_noise += 1
            audit_exclusion(
                {"source": "IDAE", "title": title, "url": link},
                "document_not_call",
                "idae_prefilter",
            )
            continue

        detail_attempted += 1
        detail_html = browser.html(link)
        detail_text = ""
        detail_soup = None
        content_root = None
        if detail_html:
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            content_root = (
                detail_soup.select_one("article.general-content")
                or detail_soup.select_one(".region-content")
                or detail_soup.body
            )
            detail_text = (
                content_root.get_text(" ", strip=True)
                if content_root else ""
            )
        detail_loaded += int(bool(detail_text))
        if not detail_text:
            if is_programme_landing:
                remember_programme_landing(title, link)
            audit_exclusion(
                {"source": "IDAE", "title": title, "url": link},
                "detail_page_unavailable",
                "idae_detail_fetch",
            )
            checked.append({
                "title": title,
                "url": link,
                "detail_loaded": False,
                "outcome": "detail_unavailable",
            })
            continue
        combined = f"{title} {detail_text}"
        if not is_relevant(combined):
            if is_programme_landing:
                remember_programme_landing(title, link)
            audit_exclusion(
                {"source": "IDAE", "title": title, "url": link},
                "not_relevant_local_filter",
                "idae_detail_filter",
            )
            checked.append({
                "title": title,
                "url": link,
                "detail_loaded": True,
                "outcome": "not_relevant",
            })
            continue

        # Extraer identidad y fechas desde la página de detalle ya renderizada.
        open_date, deadline_date = _extract_application_dates(detail_text)
        dated_details += int(bool(open_date or deadline_date))
        bdns_match = re.search(
            r"\bBDNS(?:\s*\(Identif\.?\))?\s*[:,]?\s*(\d{5,})",
            detail_text,
            re.IGNORECASE,
        )
        bdns_id = bdns_match.group(1) if bdns_match else ""
        call_identity_evidence = bool(
            bdns_id
            or re.search(
                r"\b(convocatoria|programas?|ayudas?\s+para)\b",
                _fold_text(f"{title} {detail_text[:2500]}"),
            )
        )
        if not call_identity_evidence:
            audit_exclusion(
                {
                    "source": "IDAE",
                    "title": title,
                    "url": link,
                    "bdns_id": bdns_id,
                },
                "information_page_not_call",
                "idae_identity_validation",
            )
            checked.append({
                "title": title,
                "url": link,
                "detail_loaded": True,
                "deadline_date": deadline_date,
                "outcome": "information_page",
            })
            continue
        deadline_days = _days_until(deadline_date) if deadline_date else None

        # Descartar convocatorias cuyo plazo ya haya cerrado
        if deadline_date and deadline_days is not None and deadline_days <= 0:
            log.debug(f"  IDAE: descartando cerrada (close={deadline_date}): {title[:60]}")
            skipped_closed += 1
            audit_exclusion(
                {
                    "source": "IDAE",
                    "title": title,
                    "url": link,
                    "open_date": open_date,
                    "deadline_date": deadline_date,
                    "bdns_id": bdns_id,
                },
                "deadline_closed",
                "idae_deadline_validation",
            )
            checked.append({
                "title": title,
                "url": link,
                "detail_loaded": True,
                "deadline_date": deadline_date,
                "outcome": "closed",
            })
            continue

        if not deadline_date:
            # Una mención al año actual o a futuras convocatorias no demuestra
            # una ventanilla abierta. Se conserva como identidad para fusionar
            # con BDNS/BOE, pero no se inventa un plazo de 30 días.
            remember_programme_landing(title, link)
            audit_exclusion(
                {
                    "source": "IDAE",
                    "title": title,
                    "url": link,
                    "bdns_id": bdns_id,
                },
                "no_active_deadline_evidence",
                "idae_deadline_validation",
            )
            checked.append({
                "title": title,
                "url": link,
                "detail_loaded": True,
                "deadline_date": "",
                "outcome": "identity_only_no_deadline",
            })
            continue

        fecha_sin_confirmar = False
        related_documents = _idae_official_document_links(content_root, link)

        results.append({
            "source":               "IDAE",
            "title":                title,
            "description":          select_evidence_excerpt(
                detail_text, title, 20_000
            ),
            "deadline_days":        deadline_days,
            "deadline_date":        deadline_date,
            "open_date":            open_date,
            "fecha_sin_confirmar":  fecha_sin_confirmar,
            "budget":               _extract_funding_budget(detail_text),
            "url":                  link,
            "keywords_found":       keyword_match(combined),
            "org":                  "Instituto para la Diversificación y Ahorro de la Energía",
            "source_type":          "Playwright IDAE",
            "identity_only":        False,
            "bdns_id":              bdns_id,
            "bdns_url":             (
                f"https://www.pap.hacienda.gob.es/bdnstrans/GE/es/convocatorias/{bdns_id}"
                if bdns_id else ""
            ),
            "related_documents_trace": related_documents,
            "related_documents_count": len(related_documents),
        })

        checked.append({
            "title": title,
            "url": link,
            "detail_loaded": True,
            "deadline_date": deadline_date,
            "outcome": "active",
            "document_links": len(related_documents),
        })

    health = assess_web_inventory_health(
        "IDAE",
        inventory_loaded=True,
        structure_ok=bool(inventory),
        discovered_count=len(inventory),
        detail_attempted=detail_attempted,
        detail_loaded=detail_loaded,
        dated_count=dated_details,
        published_count=len(results),
        expected_min_inventory=IDAE_MIN_EXPECTED_INVENTORY,
        # Medido el 21/08/2026: se abren 71 de 97 fichas (73 %). El umbral va
        # holgado porque busca un hundimiento —que el inventario deje de
        # reconocerse—, no la variacion normal del portal.
        expected_selection_rate=IDAE_MIN_EXPECTED_SELECTION_RATE,
    )
    RUN_DIAGNOSTICS["idae_scrape_audit"] = {
        "attempted_inventory_urls": attempted_inventory_urls,
        "inventory_url": inventory_url,
        "inventory_unique": len(inventory),
        "explicitly_closed_paths": sum(
            bool(item["explicitly_closed"]) for item in inventory
        ),
        "detail_attempted": detail_attempted,
        "detail_loaded": detail_loaded,
        "detail_failed": detail_attempted - detail_loaded,
        "dated_details": dated_details,
        "active_calls": len(results),
        "identity_landings": sum(
            item.get("source") == "IDAE" for item in IDENTITY_LANDINGS
        ),
        "checked_items": checked,
        "health": health,
    }
    SOURCE_RUNTIME_METADATA["IDAE"] = {
        "status": "ok" if health["status"] == "healthy" else "warn",
        "strategy": "inventario completo y fichas IDAE mediante Playwright",
        "inventory_unique": len(inventory),
        "detail_attempted": detail_attempted,
        "detail_loaded": detail_loaded,
        "active_calls": len(results),
        "health": health,
    }
    log.info(f"  → {len(results)} convocatorias IDAE válidas "
             f"(descartadas: {skipped_closed} cerradas, {skipped_noise} documentos)")
    return results


_IDAE_CATALOG_INCLUDE = re.compile(
    r"(industria|industrial|investigaci[oó]n y desarrollo|i\+d|"
    r"eficiencia energ[eé]tica|descarbonizaci[oó]n|hidr[oó]geno|"
    r"calor residual|tecnolog[ií]as limpias|econom[ií]a circular|"
    r"transici[oó]n energ[eé]tica|emisiones)",
    re.IGNORECASE,
)
_IDAE_CATALOG_EXCLUDE = re.compile(
    r"(agricultur|ganader|agropecuari|regad[ií]o|vivienda|residencial|"
    r"edificios?|movilidad|veh[ií]cul|transporte|pobreza energ[eé]tica|"
    r"turismo|sanitari|hospital|educativ|colegio|universidad)",
    re.IGNORECASE,
)
_IDAE_CATALOG_CALL_MARKER = re.compile(
    r"(extracto|convoca|convocatoria)",
    re.IGNORECASE,
)


def _idae_catalog_scope(header: str) -> str:
    folded = _fold_text(header)
    if "estatal/ estatal" in folded:
        return "Estatal"
    if "autonomico/ aragon" in folded:
        return "Autonómico / Aragón"
    if "local/ zaragoza" in folded:
        return "Local / Zaragoza"
    return ""


def _idae_catalog_document_rank(record: dict) -> tuple:
    """Prioriza extractos/convocatorias sobre bases, correcciones y cambios."""
    title = _fold_text(record.get("title", ""))
    score = 0
    if "extracto" in title:
        score += 4
    if "convoca" in title or "convocatoria" in title:
        score += 4
    if "modifica" in title or "ampliacion" in title:
        score -= 2
    if "correccion de errores" in title:
        score -= 3
    if "bases reguladoras" in title:
        score -= 4
    return score, record.get("publication_date", "")


def _parse_idae_catalog_html(html: str) -> tuple[list, dict]:
    """Extrae y agrupa las tres secciones autorizadas del catálogo IDAE."""
    soup = BeautifulSoup(html, "html.parser")
    records = []
    section_counts = {
        "Estatal": 0,
        "Autonómico / Aragón": 0,
        "Local / Zaragoza": 0,
    }
    current_category = {}

    for page in soup.select("div.new-page"):
        header_node = page.select_one("div.contenido-cabecera")
        scope = _idae_catalog_scope(
            header_node.get_text(" ", strip=True) if header_node else ""
        )
        if not scope:
            continue

        category = current_category.get(scope, "")
        for child in page.find_all(recursive=False):
            classes = set(child.get("class", []))
            if "grupo-titulo" in classes:
                category = " ".join(child.get_text(" ", strip=True).split()).strip(" /")
                current_category[scope] = category
                continue
            if not {"item", "grupo-item"}.issubset(classes):
                continue

            section_counts[scope] += 1
            text_node = child.select_one("div.text")
            if not text_node:
                continue
            title = " ".join(text_node.get_text(" ", strip=True).split())
            combined = f"{category} {title}"
            core_category = bool(re.search(
                r"(industria|investigaci[oó]n y desarrollo|i\+d)",
                category,
                re.IGNORECASE,
            ))
            if (
                not (_IDAE_CATALOG_INCLUDE.search(title) or core_category)
                or _IDAE_CATALOG_EXCLUDE.search(combined)
            ):
                continue

            item_text = " ".join(child.get_text(" ", strip=True).split())
            bdns_match = re.search(r"\bBDNS:\s*(\d+)", item_text, re.IGNORECASE)
            ref_match = re.search(
                r"\bRef\.?:\s*([A-Za-z0-9./-]+)",
                item_text,
                re.IGNORECASE,
            )
            date_matches = re.findall(r"\b(\d{2}/\d{2}/20\d{2})\b", item_text)
            anchors = child.find_all("a", href=True)
            official_url = ""
            bdns_url = ""
            for anchor in anchors:
                href = _absolute_url("https://www.idae.es", anchor.get("href", "").strip())
                if "pap.hacienda.gob.es" in href or "infosubvenciones" in href:
                    bdns_url = href
                elif not official_url:
                    official_url = href

            records.append({
                "scope": scope,
                "category": category,
                "title": title,
                "official_url": official_url or bdns_url,
                "bdns_url": bdns_url,
                "bdns_id": bdns_match.group(1) if bdns_match else "",
                "catalog_ref": ref_match.group(1) if ref_match else "",
                "publication_date": (
                    _date_to_iso(date_matches[-1]) if date_matches else ""
                ),
            })

    grouped = {}
    for record in records:
        key = (
            f"bdns:{record['bdns_id']}"
            if record["bdns_id"]
            else f"url:{re.sub(r'[?#].*$', '', record['official_url']).rstrip('/')}"
        )
        if not key or key == "url:":
            key = f"title:{_fold_text(record['title'])}"
        grouped.setdefault(key, []).append(record)

    candidates = []
    for related in grouped.values():
        if not any(_IDAE_CATALOG_CALL_MARKER.search(item["title"]) for item in related):
            continue
        primary = max(related, key=_idae_catalog_document_rank)
        primary = dict(primary)
        primary["related_documents"] = related
        primary["related_documents_count"] = len(related)
        candidates.append(primary)

    return candidates, section_counts


def _verify_idae_catalog_deadline(
    browser: PlaywrightBrowser,
    candidate: dict,
) -> tuple[str, str]:
    """Contrasta hasta dos documentos oficiales relacionados para localizar el plazo."""
    documents = sorted(
        candidate.get("related_documents", []),
        key=_idae_catalog_document_rank,
        reverse=True,
    )
    checked_urls = set()
    for document in documents:
        for url in (document.get("official_url", ""), document.get("bdns_url", "")):
            clean_url = str(url).strip()
            if not clean_url or clean_url in checked_urls:
                continue
            checked_urls.add(clean_url)
            if len(checked_urls) > 2:
                return "", ""
            boe_id_match = re.search(
                r"/(?:pdfs/)?(BOE-[AB]-20\d{2}-\d+)\.pdf$",
                clean_url,
                re.IGNORECASE,
            )
            verification_url = (
                f"https://www.boe.es/diario_boe/txt.php?id={boe_id_match.group(1)}"
                if boe_id_match
                else clean_url
            )
            # VEROBJ inicia una descarga PDF; la BDNS relacionada se intenta
            # después y resulta más útil para buscar plazos.
            if "boa.aragon.es" in verification_url and "VEROBJ" in verification_url:
                continue
            html = browser.html(verification_url)
            if not html:
                continue
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
            open_date, deadline_date = _extract_application_dates(text)
            if deadline_date:
                return open_date, deadline_date
    return "", ""


def fetch_idae_catalog(browser: PlaywrightBrowser) -> list:
    """
    Usa el catálogo agregado IDAE como capa de descubrimiento para Estatal,
    Aragón y Zaragoza; conserva la fuente oficial y la trazabilidad.
    """
    log.info("Consultando catálogo agregado IDAE (Estatal, Aragón, Zaragoza)...")
    catalog_url = "https://www.idae.es/catalogo-de-ayudas-preview?page=25"
    # La vista preview oculta <body> mientras prepara la maquetación de
    # impresión; esperar a <html> permite recuperar el DOM ya descargado.
    html = browser.html(catalog_url, wait_selector="html")
    if not html:
        log.warning("  Catálogo IDAE no accesible")
        SOURCE_RUNTIME_METADATA["IDAE CATÁLOGO"] = {
            "section_counts": {},
            "catalog_url": catalog_url,
            "status": "warn",
        }
        return []

    candidates, section_counts = _parse_idae_catalog_html(html)
    SOURCE_RUNTIME_METADATA["IDAE CATÁLOGO"] = {
        "section_counts": section_counts,
        "catalog_url": catalog_url,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
    }
    log.info(
        "  Catálogo IDAE bruto por sección: "
        + ", ".join(f"{name}={count}" for name, count in section_counts.items())
    )
    log.info(f"  Catálogo IDAE: {len(candidates)} grupos relevantes tras prefiltro")

    today = datetime.now().date()
    results = []
    skipped_old_unconfirmed = 0
    skipped_closed = 0

    for candidate in candidates:
        open_date, deadline_date = _verify_idae_catalog_deadline(browser, candidate)
        if deadline_date:
            deadline_days = _days_until(deadline_date)
            if deadline_days <= 0:
                skipped_closed += 1
                audit_exclusion(
                    {
                        "source": (
                            "BOE / MITECO"
                            if candidate["scope"] == "Estatal"
                            else "BOA ARAGÓN"
                            if candidate["scope"] == "Autonómico / Aragón"
                            else "ZARAGOZA"
                        ),
                        "title": candidate["title"],
                        "url": candidate.get("official_url", ""),
                        "bdns_id": candidate.get("bdns_id", ""),
                        "catalog_ref": candidate.get("catalog_ref", ""),
                        "open_date": open_date,
                        "deadline_date": deadline_date,
                    },
                    "deadline_closed",
                    "idae_catalog_deadline_validation",
                    {"catalog_scope": candidate["scope"]},
                )
                continue
            fecha_sin_confirmar = False
        else:
            publication_raw = candidate.get("publication_date", "")
            try:
                publication_date = datetime.strptime(publication_raw, "%Y-%m-%d").date()
                publication_age = (today - publication_date).days
            except (TypeError, ValueError):
                publication_age = 9999
            if publication_age < 0 or publication_age > 90:
                skipped_old_unconfirmed += 1
                audit_exclusion(
                    {
                        "source": "IDAE CATÁLOGO",
                        "title": candidate["title"],
                        "url": candidate.get("official_url", ""),
                        "bdns_id": candidate.get("bdns_id", ""),
                        "catalog_ref": candidate.get("catalog_ref", ""),
                    },
                    "old_without_verified_deadline",
                    "idae_catalog_deadline_validation",
                    {
                        "catalog_scope": candidate["scope"],
                        "publication_date": publication_raw,
                    },
                )
                continue
            deadline_days = 30
            fecha_sin_confirmar = True

        scope = candidate["scope"]
        if scope == "Estatal":
            source = "BOE / MITECO"
            org = "Organismo estatal convocante"
        elif scope == "Autonómico / Aragón":
            source = "BOA ARAGÓN"
            org = "Gobierno de Aragón / organismo convocante"
        else:
            source = "ZARAGOZA"
            org = "Ayuntamiento de Zaragoza / organismo local convocante"

        related_titles = [
            item["title"] for item in candidate.get("related_documents", [])
        ]
        description = (
            f"Descubierta mediante el catálogo IDAE. Ámbito: {scope}. "
            f"Categoría: {candidate.get('category', '')}. "
            f"Documentos relacionados ({len(related_titles)}): "
            + " | ".join(related_titles)
        )
        combined = f"{candidate['title']} {description}"
        results.append({
            "source": source,
            "title": candidate["title"][:300],
            "description": select_evidence_excerpt(
                # `title` no existía en este ámbito: era un NameError latente,
                # presente desde antes de extraer el conector y nunca disparado
                # porque el catálogo IDAE lleva tiempo sin aportar convocatorias
                # incorporables, así que esta línea no llegaba a ejecutarse.
                # Detectado por tests/test_grant_radar_script_names.py (ver
                # AGENTS.md sección 35). El título de la convocatoria es el que
                # se usa dos líneas más arriba.
                description, candidate["title"], 20_000
            ),
            "deadline_days": deadline_days,
            "deadline_date": deadline_date,
            "open_date": open_date,
            "fecha_sin_confirmar": fecha_sin_confirmar,
            "fecha_prevista": False,
            "budget": "Ver disposición oficial",
            "url": candidate.get("official_url") or candidate.get("bdns_url"),
            "keywords_found": keyword_match(combined),
            "org": org,
            "source_type": "Catálogo IDAE + fuente oficial",
            "discovered_via": "IDAE Catálogo",
            "catalog_scope": scope,
            "catalog_category": candidate.get("category", ""),
            "catalog_ref": candidate.get("catalog_ref", ""),
            "bdns_id": candidate.get("bdns_id", ""),
            "bdns_url": candidate.get("bdns_url", ""),
            "related_documents_count": candidate.get("related_documents_count", 1),
        })

    log.info(
        f"  → {len(results)} convocatorias del catálogo IDAE incorporables "
        f"(cerradas={skipped_closed}, antiguas sin plazo={skipped_old_unconfirmed})"
    )
    return results
