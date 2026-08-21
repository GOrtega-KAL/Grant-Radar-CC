# boe_miteco.py — conector BOE / MITECO
#
# Busca en ayudas.php del BOE los extractos de convocatoria publicados y abre
# cada ficha para recuperar el identificador BDNS, las fechas de solicitud y
# los documentos regulatorios asociados. Es la vía por la que entran
# convocatorias estatales cuyo organismo no tiene inventario web propio
# utilizable, y la que aporta el extracto oficial de programas que también
# llegan por IDAE o BDNS: la consolidación posterior (`grant_radar/dedup.py`)
# decide cuál de los documentos manda.
#
# El parser depende del marcado de resultados del BOE, que ya se rompió una vez
# (`p.linea-dem`, ver AGENTS.md sección 2.4 de SUGERENCIAS.MD); por eso declara
# su estructura a `assess_web_inventory_health()` en cada ejecución.

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from grant_radar.audit import audit_exclusion
from grant_radar.browser import PlaywrightBrowser
from grant_radar.dedup import _document_role, _programme_identity
from grant_radar.parsing_helpers import (
    _days_until,
    _es_titulo_valido,
    _extract_application_dates,
    _fold_text,
    select_evidence_excerpt,
)
from grant_radar.runtime_state import SOURCE_RUNTIME_METADATA
from grant_radar.source_health import assess_web_inventory_health
from grant_radar.tech_taxonomy import (
    detect_tech_tags,
    has_technology_discovery_signal,
    is_relevant,
    keyword_match,
)

log = logging.getLogger("grant_radar")

# Organismos cuyas ayudas se abren aunque el listado no traiga vocabulario
# técnico. Hace falta porque el listado del BOE son citas legales —«Extracto de
# la Orden … por la que se convocan las subvenciones dispuestas en el Real
# Decreto 309/2022»— sin una sola palabra sobre la materia: medido el
# 21/08/2026 sobre las 168 entradas reales, la taxonomía técnica admitía cero, y
# las 8 que se abrían entraban todas por aquí (AGENTS.md, sección 45.2).
#
# Es una excepción acotada, no una puerta abierta: exige además una palabra de
# ayuda, y la relevancia de verdad la decide después el texto del documento.
# Deliberadamente fuera: Ciencia, Innovación y Universidades, cuyas 17 entradas
# de ese día eran institutos de salud, universidades y FECYT; la parte que sí
# interesa de ese ministerio es el CDTI, que tiene su propio conector.
BOE_TRACKED_AUTHORITIES = (
    "ministerio para la transicion ecologica y el reto demografico",
    "secretaria de estado de energia",
    "fundacion biodiversidad",
    "ministerio de industria y turismo",
    "sociedad estatal de promocion industrial y desarrollo empresarial",
)


def fetch_boe(browser: PlaywrightBrowser) -> list:
    """
    BOE — búsqueda en ayudas.php.
    Cada resultado renderizado es un ``li.resultado-busqueda`` con el texto
    descriptivo y un enlace «Ir al documento».
    """
    log.info("Consultando BOE con Playwright (ayudas.php)...")
    results = []
    inventory_url = "https://www.boe.es/buscar/ayudas.php"
    html = browser.html(inventory_url)

    if not html:
        log.warning("BOE: página de ayudas no accesible")
        health = assess_web_inventory_health(
            "BOE / MITECO",
            inventory_loaded=False,
            structure_ok=False,
            discovered_count=0,
            expected_min_inventory=25,
        )
        SOURCE_RUNTIME_METADATA["BOE / MITECO"] = {
            "status": "warn", "health": health, "inventory_url": inventory_url,
        }
        return results

    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    detail_attempted = 0
    detail_loaded = 0
    dated_count = 0
    prefilter_count = 0

    # ── Parser principal: resultados renderizados ────────────────────
    bloques = soup.select("li.resultado-busqueda")
    log.info(f"  BOE: {len(bloques)} bloques ayuda encontrados")

    for bloque in bloques:
        texto_completo = bloque.get_text(separator=" ", strip=True)

        # Enlace al documento BOE real (contiene /diario/ o /buscar/doc)
        a_doc = None
        for a in bloque.find_all("a", href=True):
            href = a.get("href", "")
            if "/diario" in href or "/buscar/doc" in href or "/boe/" in href:
                a_doc = a
                break
        if not a_doc:
            a_doc = bloque.find("a", href=True)
        if not a_doc:
            continue

        # El marcado vigente usa un primer <p class="linea-dem"> para el
        # organismo y un segundo <p> para el título. Las clases descriptivas
        # antiguas ya no aparecen y hacían que se analizara el organismo como
        # título. Se mantiene un respaldo para cambios compatibles del HTML.
        org_element = bloque.select_one("p.linea-dem")
        org_line = (
            " ".join(org_element.get_text(" ", strip=True).split())
            if org_element else ""
        )
        description_paragraphs = [
            paragraph for paragraph in bloque.find_all("p", recursive=False)
            if "linea-dem" not in (paragraph.get("class") or [])
        ]
        title = (
            " ".join(description_paragraphs[0].get_text(" ", strip=True).split())
            if description_paragraphs else ""
        )
        if not title:
            title = re.sub(r"Ir al documento.*", "", texto_completo).strip()
            if org_line and title.startswith(org_line):
                title = title[len(org_line):].strip()
            title = re.sub(r"Más\.\.\.\s*\(.*?\)", "", title).strip()[:400]

        combined = f"{title} {texto_completo}"
        folded_listing = _fold_text(combined)
        is_idae_aid = (
            "instituto para la diversificacion y ahorro de la energia" in folded_listing
            and bool(re.search(
                r"\b(convocatoria|programa|incentivos?|ayudas?|subvenciones?)\b",
                folded_listing,
            ))
        )
        is_tracked_authority_aid = bool(
            any(authority in folded_listing for authority in BOE_TRACKED_AUTHORITIES)
            and re.search(
                r"\b(convocatoria|programa|incentivos?|ayudas?|subvenciones?)\b",
                folded_listing,
            )
        )
        listing_program_key, _ = _programme_identity(texto_completo)
        is_related_program_document = bool(
            listing_program_key
            and re.search(
                r"\b(bases reguladoras|convocatoria|extracto|programa)\b",
                folded_listing,
            )
            and detect_tech_tags(combined)
        )
        # Las denominaciones comerciales pueden carecer de keywords técnicas.
        # Los extractos de IDAE se visitan también y se clasifican después con
        # el texto completo del documento oficial.
        if (
            not title
            or not _es_titulo_valido(title)
            or not (
                is_relevant(combined)
                or has_technology_discovery_signal(combined)
                or is_idae_aid
                or is_tracked_authority_aid
                or is_related_program_document
            )
        ):
            continue
        prefilter_count += 1

        href = urljoin(inventory_url, a_doc.get("href", ""))

        # URL canónica por referencia BOE si está disponible
        ref_match = re.search(r"BOE-[AB]-\d{4}-\d+", href + " " + texto_completo)
        if ref_match and "/diario" not in href:
            href = f"https://www.boe.es/buscar/doc.php?id={ref_match.group()}"
        record_key = ref_match.group() if ref_match else href.casefold()
        if record_key in seen:
            continue
        seen.add(record_key)

        # Enriquecimiento general desde el documento oficial: BDNS, título
        # canónico y plazo. Esto permite relacionar extractos, bases y páginas
        # de programa sin depender de nombres introducidos manualmente.
        detail_attempted += 1
        detail_html = browser.html(href)
        detail_text = ""
        bdns_id = ""
        open_date = ""
        deadline_date = ""
        if detail_html:
            detail_loaded += 1
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            detail_text = " ".join(
                detail_soup.get_text(" ", strip=True).split()
            )
            heading = detail_soup.find("h3")
            if heading:
                official_title = " ".join(heading.get_text(" ", strip=True).split())
                if len(official_title) >= 20:
                    title = official_title
            bdns_match = re.search(
                r"\bBDNS(?:\s*\(Identif\.?\))?\s*[:,]?\s*(\d{5,})",
                detail_text,
                re.IGNORECASE,
            )
            bdns_id = bdns_match.group(1) if bdns_match else ""
            open_date, deadline_date = _extract_application_dates(detail_text)
            if deadline_date:
                dated_count += 1

        active_idae_extract = bool(
            is_idae_aid
            and deadline_date
            and (_days_until(deadline_date) or 0) > 0
        )
        if not (
            is_relevant(f"{combined} {detail_text}")
            or active_idae_extract
        ):
            audit_exclusion(
                {
                    "source": "BOE / MITECO",
                    "title": title,
                    "url": href,
                    "bdns_id": bdns_id,
                    "deadline_date": deadline_date,
                },
                "not_relevant_local_filter",
                "boe_detail_filter",
                {
                    "listing_idae_aid": is_idae_aid,
                    "listing_tracked_authority": is_tracked_authority_aid,
                    "detail_loaded": bool(detail_text),
                },
            )
            continue

        deadline_days = _days_until(deadline_date) if deadline_date else 45
        document_role = _document_role({"source": "BOE / MITECO", "title": title})
        results.append({
            "source":         "BOE / MITECO",
            "title":          title,
            "description":    select_evidence_excerpt(
                detail_text or texto_completo, title, 20_000
            ),
            "deadline_days":  deadline_days,
            "deadline_date":  deadline_date,
            "open_date":      open_date,
            "fecha_sin_confirmar": not bool(deadline_date),
            "budget":         "Ver disposición",
            "url":            href,
            "keywords_found": keyword_match(f"{combined} {detail_text}"),
            "org":            re.sub(r"\s*\(BOE\s+.*$", "", org_line).strip()
                              or "Boletín Oficial del Estado",
            "source_type":    "Playwright BOE",
            "document_role":  document_role,
            "identity_only":  bool(
                document_role == "regulatory_bases" and not deadline_date
            ),
            "bdns_id":        bdns_id,
            "bdns_url":       (
                f"https://www.pap.hacienda.gob.es/bdnstrans/GE/es/convocatorias/{bdns_id}"
                if bdns_id else ""
            ),
        })

    health = assess_web_inventory_health(
        "BOE / MITECO",
        inventory_loaded=True,
        structure_ok=bool(bloques),
        discovered_count=len(bloques),
        detail_attempted=detail_attempted,
        detail_loaded=detail_loaded,
        dated_count=dated_count,
        published_count=len(results),
        expected_min_inventory=25,
        # Desde el 21/08/2026 la cobertura se mide sobre las fichas cargadas, no
        # sobre el inventario completo, así que ya es una cifra con sentido para
        # esta fuente y el umbral puede activarse: medido, 3 de 8 (37 %). Antes
        # daba 1,8 % —porque el BOE lista ayudas de todos los ministerios y solo
        # se abre lo que pasa el prefiltro— y hubo que apagarlo (AGENTS.md 45.1).
        expected_date_coverage=0.20,
    )
    SOURCE_RUNTIME_METADATA["BOE / MITECO"] = {
        "status": "ok" if health["status"] == "healthy" else "warn",
        "health": health,
        "inventory_url": inventory_url,
        "inventory_count": len(bloques),
        "prefilter_count": prefilter_count,
        "detail_attempted": detail_attempted,
        "detail_loaded": detail_loaded,
        "dated_count": dated_count,
        "accepted_count": len(results),
        "coverage_scope": "ventana cronológica publicada por ayudas.php; BDNS es el inventario transversal",
    }

    log.info(f"  → {len(results)} convocatorias BOE relevantes")
    return results
