# cdti.py — conector CDTI (Centro para el Desarrollo Tecnológico Industrial)
#
# Dos vías que se fusionan: el calendario oficial de convocatorias recorrido
# con Chromium —con sus fichas de detalle— y un catálogo curado que da
# cobertura a las líneas de ventanilla abierta, que no aparecen en el
# calendario. `_merge_cdti_results()` las combina con prioridad creciente:
# catálogo < calendario oficial.
#
# El calendario es un punto único de descubrimiento: si su tabla cambia de
# estructura, la cobertura cae aunque las fichas sigan disponibles. Por eso
# cada ejecución declara acceso, estructura, volumen, carga de fichas,
# cobertura de fechas y antigüedad a `assess_web_inventory_health()`.
#
# Los registros de CDTI se fusionan después con los de BDNS cuando comparten
# identidad; eso lo decide `grant_radar/dedup.py`, no este módulo.

import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from grant_radar.audit import audit_exclusion
from grant_radar.browser import PlaywrightBrowser
from grant_radar.dedup import _document_role
from grant_radar.documents import enrich_with_official_documents
from grant_radar.parsing_helpers import (
    _SPANISH_MONTHS,
    _absolute_url,
    _days_until,
    _extract_application_dates,
    _fold_text,
    _parse_cdti_calendar_date,
    select_evidence_excerpt,
)
from grant_radar.runtime_state import RUN_DIAGNOSTICS, SOURCE_RUNTIME_METADATA
from grant_radar.source_health import assess_web_inventory_health
from grant_radar.tech_taxonomy import keyword_match

log = logging.getLogger("grant_radar")


def _fetch_cdti_static() -> list:
    """
    CDTI — catálogo curado complementario.

    El calendario oficial se extrae automáticamente con Playwright. Este catálogo
    conserva programas permanentes, contexto técnico y excepciones que no figuran
    en la tabla anual. Sus fechas nunca sustituyen datos oficiales más recientes.
    """
    log.info("CDTI: cargando catálogo curado complementario...")

    # ── Catálogo estático de convocatorias CDTI relevantes para Kalfrisa ──
    # ESTADO: ★ = abierta confirmada | ◷ = fecha prevista (sujeta a PGE y disponibilidad)
    # Fuente: https://www.cdti.es/calendario-de-convocatorias (versión 7 abril 2026)
    # Última revisión: 2026-08-20
    #
    # MANTENIMIENTO: las URLs de aquí se teclean a mano y caducan sin avisar.
    # El 20/08/2026 seis de las diez apuntaban a rutas inexistentes (ver
    # AGENTS.md, sección 44). Al revisarlas, tomarlas del calendario oficial o
    # de https://www.cdti.es/ayudas en vez de construirlas, y comprobarlas con
    # el navegador: cdti.es responde 200 a cualquier ruta pedida por un cliente
    # HTTP corriente, así que `verificar_urls()` no puede detectar el fallo.
    # `_drop_catalog_entries_with_dead_urls()` aparta en cada ejecución las que
    # den 404, pero es una red de seguridad, no un sustituto de la revisión.
    _STATIC = [
        # ── VENTANILLA PERMANENTE ─────────────────────────────────────────────
        {
            "title":         "Proyectos de I+D — Línea PID (ventanilla abierta)",
            "description":   "Financiación de proyectos empresariales de investigación industrial y "
                             "desarrollo experimental para la creación o mejora significativa de "
                             "procesos productivos, productos o servicios. Presupuesto mínimo 175.000 €. "
                             "Ayuda parcialmente reembolsable hasta el 85% con tramo no reembolsable "
                             "del 10-33%. Modalidad individual, cooperación nacional e internacional. "
                             "Aplica directamente a proyectos de eficiencia térmica, control de "
                             "emisiones y combustión industrial H2-ready de Kalfrisa.",
            "open_date":     "",
            "deadline_date": "",
            "deadline_note": "ventanilla_permanente",
            "budget":        "Hasta 85% del presupuesto (mín. 175.000 €)",
            "url":           "https://www.cdti.es/ayudas/proyectos-de-i-d",
            # Corregida el 21/08/2026 a la ficha concreta (AGENTS.md 44.1): ya no
            # es una página general de programa, y el aviso del panel sobraba.
            "url_generica":  False,
            "keywords":      ["eficiencia energética", "eficiencia térmica", "descarbonización",
                              "calor residual", "emisiones industriales"],
        },
        {
            "title":         "Proyectos Transferencia Tecnológica Cervera (ventanilla abierta)",
            "description":   "Proyectos de I+D empresarial en colaboración obligatoria con Centros "
                             "Tecnológicos acreditados. Área prioritaria 'Transición Energética' "
                             "incluida. Subcontratación mínima 10% al Centro Tecnológico. Tramo "
                             "no reembolsable fijo del 33%. Máximo encaje para Kalfrisa dada su "
                             "relación con ITAINNOVA y CIRCE en Aragón.",
            "open_date":     "",
            "deadline_date": "",
            "deadline_note": "ventanilla_permanente",
            "budget":        "Hasta 85% · 33% no reembolsable (mín. 175.000 €)",
            "url":           "https://www.cdti.es/ayudas/proyectos-de-id-de-transferencia-tecnologica-cervera-0",
            # Corregida el 21/08/2026 a la ficha concreta (AGENTS.md 44.1): ya no
            # es una página general de programa, y el aviso del panel sobraba.
            "url_generica":  False,
            "keywords":      ["eficiencia energética", "calor residual", "descarbonización",
                              "hidrógeno", "eficiencia térmica"],
        },
        {
            "title":         "Infraestructuras de Ensayo y Experimentación CDTI (ventanilla abierta)",
            "description":   "Ayudas para el desarrollo o mejora de infraestructuras de ensayo, "
                             "caracterización y demostración tecnológica en empresas. Abierto desde "
                             "16 de marzo de 2026 de forma permanente a través de la sede electrónica "
                             "del CDTI. Interesante para laboratorios de validación de quemadores "
                             "H2-ready y sistemas de medición de emisiones de Kalfrisa.",
            "open_date":     "2026-03-16",
            "deadline_date": "",
            "deadline_note": "ventanilla_permanente",
            "budget":        "Ver convocatoria",
            "url":           "https://www.cdti.es/ayudas/linea-de-ayudas-infraestructuras-de-ensayo-y-experimentacion",
            # Corregida el 21/08/2026 a la ficha concreta (AGENTS.md 44.1): ya no
            # es una página general de programa, y el aviso del panel sobraba.
            "url_generica":  False,
            "keywords":      ["eficiencia energética", "eficiencia térmica", "hidrógeno",
                              "emisiones industriales"],
        },
        # ── ABIERTAS CONFIRMADAS ──────────────────────────────────────────────
        {
            "title":         "PRIMA 2026 — Proyectos I+D ámbito mediterráneo",
            "description":   "Programa internacional de I+D para países del Mediterráneo. Convocatoria "
                             "abierta desde 20 marzo 2026. Cierre PRIMA: 15 mayo 2026. Requiere "
                             "consorcio de al menos 4 socios de 3 países. Presupuesto: 32,5M€ "
                             "(Sección 1, UE) + 36,1M€ (Sección 2, países). Las empresas españolas "
                             "deben presentar también solicitud PRI en sede CDTI antes del 15 mayo.",
            "open_date":     "2026-03-20",
            "deadline_date": "2026-05-15",
            "deadline_note": "★ abierta",
            "budget":        "32,5M€ Sec.1 + 36,1M€ Sec.2",
            "url":           "https://www.cdti.es/ayudas/prima",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "descarbonización", "hidrógeno",
                              "eficiencia térmica"],
        },
        {
            "title":         "Neotec 2026 — Empresas innovadoras de base tecnológica",
            "description":   "Subvenciones a fondo perdido para startups y pequeñas empresas "
                             "innovadoras de base tecnológica con antigüedad máxima de 3 años. "
                             "Presupuesto 20,38M€. Financiación hasta el 70% (o 85% con contratación "
                             "de doctor). Máximo 250.000 € (o 325.000 €). Relevante si Kalfrisa "
                             "tiene spin-offs tecnológicos con menos de 3 años de vida o vinculados "
                             "a tecnologías de combustión H2-ready o control de emisiones.",
            "open_date":     "2026-04-14",
            "deadline_date": "2026-05-14",
            "deadline_note": "★ abierta",
            "budget":        "Hasta 325.000 € por empresa · subvención a fondo perdido",
            "url":           "https://www.cdti.es/ayudas/ayudas-neotec-2026",
            "url_generica":  False,
            "keywords":      ["eficiencia energética", "hidrógeno", "descarbonización",
                              "eficiencia térmica"],
        },
        {
            "title":         "Proyectos Bilaterales CDTI — 13ª convocatoria (todo 2026)",
            "description":   "Financiación de proyectos bilaterales de I+D en cooperación con socios "
                             "internacionales, con certificación y seguimiento unilateral CDTI. "
                             "Convocatoria permanente durante todo 2026 con dos fechas de corte. "
                             "Instrumento para proyectos de combustión industrial y eficiencia "
                             "térmica con partners europeos.",
            "open_date":     "2026-01-01",
            "deadline_date": "2026-12-31",
            "deadline_note": "★ abierta (dos fechas de corte)",
            "budget":        "Ver convocatoria · ayuda parcialmente reembolsable",
            "url":           "https://www.cdti.es/programas-de-cooperacion-tecnologica-internacional-pcti",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "eficiencia térmica", "calor residual",
                              "descarbonización"],
        },
        # ── FECHAS PREVISTAS ─────────────────────────────────────────────────
        {
            "title":         "Sello de Excelencia + FEDER 2026",
            "description":   "Financiación nacional para proyectos que hayan obtenido el Sello de "
                             "Excelencia en convocatorias europeas competitivas (Horizon Europe EIC). "
                             "Subvención FEDER complementaria a la evaluación europea ya superada. "
                             "Apertura prevista abril 2026, cierre mayo 2026 según calendario CDTI.",
            "open_date":     "2026-04-01",
            "deadline_date": "2026-05-31",
            "deadline_note": "◷ fecha prevista",
            "budget":        "Ver convocatoria · subvención FEDER",
            "url":           "https://www.cdti.es/ayudas/ayudas-pymes-sello-de-excelencia-2026",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "descarbonización", "hidrógeno",
                              "eficiencia térmica"],
        },
        {
            "title":         "Misiones Ciencia e Innovación 2026",
            "description":   "Proyectos cooperativos de I+D de gran envergadura articulados en "
                             "consorcios empresariales, orientados a retos incluyendo transición "
                             "energética y descarbonización industrial. Presupuesto mínimo 3,5M€ "
                             "por proyecto. Apertura prevista mayo 2026, cierre junio 2026. "
                             "Kalfrisa puede participar como socio tecnológico en consorcios del "
                             "sector cerámico, siderúrgico o químico.",
            "open_date":     "2026-05-01",
            "deadline_date": "2026-06-30",
            "deadline_note": "◷ fecha prevista",
            "budget":        "~140M€ total (subvención FEDER) · mín. 3,5M€ por proyecto",
            "url":           "https://www.cdti.es/ayudas/misiones-ciencia-e-innovacion-2026",
            "url_generica":  False,
            "keywords":      ["descarbonización", "eficiencia energética", "hidrógeno",
                              "emisiones industriales", "transición energética"],
        },
        {
            "title":         "Cervera Centros 2026 — I+D con centros tecnológicos (prevista)",
            "description":   "Convocatoria competitiva anual de Proyectos Cervera para empresas "
                             "en colaboración con Centros Tecnológicos acreditados en áreas "
                             "tecnológicas prioritarias incluyendo 'Transición Energética'. "
                             "Apertura prevista mayo 2026, cierre junio 2026 según calendario CDTI. "
                             "Kalfrisa + ITAINNOVA/CIRCE son la combinación natural para esta línea.",
            "open_date":     "2026-05-01",
            "deadline_date": "2026-06-30",
            "deadline_note": "◷ fecha prevista",
            "budget":        "Ver convocatoria · 33% no reembolsable",
            "url":           "https://www.cdti.es/ayudas/ayudas-cervera-para-centros-tecnologicos-2026",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "calor residual", "descarbonización",
                              "hidrógeno", "eficiencia térmica"],
        },
        {
            "title":         "CIIP Eurostars CoD10 2026 — Cooperación I+D internacional Eureka",
            "description":   "Instrumento nacional CDTI para financiar participación española en "
                             "proyectos aprobados en Eurostars-3 (red Eureka). Evaluación internacional "
                             "previa. 10ª fecha de corte prevista julio 2026. Dirigido a pymes "
                             "con proyectos colaborativos de I+D con socios de países Eureka.",
            "open_date":     "2026-07-01",
            "deadline_date": "2026-07-31",
            "deadline_note": "◷ fecha prevista",
            "budget":        "Ver convocatoria · subvención",
            "url":           "https://www.cdti.es/ayudas/eurostars-3-2026-cod10",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "descarbonización", "eficiencia térmica",
                              "calor residual"],
        },
        {
            "title":         "Partenariados Pilar 2 SERA 2026 — Segunda llamada",
            "description":   "Instrumento de adjudicación directa CDTI para financiar entidades "
                             "españolas en proyectos internacionales seleccionados en partenariados "
                             "cofinanciados del Pilar 2 de Horizon Europe. Segunda llamada prevista "
                             "julio 2026. El proyecto debe aprobarse primero en el marco europeo.",
            "open_date":     "2026-07-01",
            "deadline_date": "2026-07-31",
            "deadline_note": "◷ fecha prevista",
            "budget":        "Ver convocatoria · adjudicación directa",
            "url":           "https://www.cdti.es/ayudas/partenariados-pilar-2-sera-2026-1",
            "url_generica":  False,
            "keywords":      ["eficiencia energética", "descarbonización", "hidrógeno",
                              "eficiencia térmica"],
        },
    ]

    results = []
    for c in _STATIC:
        # Calcular deadline_days
        if c["deadline_note"] == "ventanilla_permanente":
            deadline_days        = 365
            deadline_date        = ""
            open_date            = ""
            fecha_sin_confirmar  = True
            fecha_prevista       = False
        else:
            close_str   = c.get("deadline_date", "")
            open_str    = c.get("open_date", "")
            deadline_days = _days_until(close_str) if close_str else 180
            if deadline_days <= 0:
                log.debug(f"  CDTI estático: descartando cerrada: {c['title'][:60]}")
                continue
            deadline_date   = close_str
            open_date       = open_str
            es_prevista     = c["deadline_note"].startswith("◷")
            fecha_sin_confirmar = not bool(close_str) or es_prevista
            fecha_prevista  = es_prevista

        kw_found = [k for k in c.get("keywords", []) if k.lower() in " ".join(c["keywords"]).lower()]

        results.append({
            "source":              "CDTI",
            "title":               c["title"],
            "description":         c["description"],
            "deadline_days":       deadline_days,
            "deadline_date":       deadline_date,
            "open_date":           open_date,
            "fecha_sin_confirmar": fecha_sin_confirmar,
            "fecha_prevista":      fecha_prevista,
            "budget":              c["budget"],
            "url":                 c["url"],
            "url_generica":        c.get("url_generica", False),
            "keywords_found":      c["keywords"],
            "org":                 "CDTI — Centro para el Desarrollo Tecnológico Industrial",
            "source_type":         "Catálogo curado",
        })

    log.info(f"  → {len(results)} convocatorias CDTI vigentes en catálogo curado")
    return results


CDTI_MAX_CALENDAR_CALLS = 100
CDTI_MIN_EXPECTED_CALENDAR_CALLS = 10
CDTI_MAX_CALENDAR_VERSION_AGE_DAYS = 62


def _parse_cdti_calendar_html(html: str) -> tuple[list[dict], dict]:
    """Extrae todas las fichas del calendario antes de decidir su relevancia."""
    base = "https://www.cdti.es"
    soup = BeautifulSoup(html, "html.parser")
    page_text = " ".join(soup.get_text(" ", strip=True).split())
    folded_page = _fold_text(page_text)
    version_match = re.search(
        r"ultima version:\s*"
        r"(\d{1,2}\s+de\s+[a-z]+\s+de\s+(20\d{2}))",
        folded_page,
        re.IGNORECASE,
    )
    version_label = version_match.group(1) if version_match else ""
    calendar_year = (
        int(version_match.group(2)) if version_match else datetime.now().year
    )
    version_date, _ = _parse_cdti_calendar_date(version_label, calendar_year)
    # La tabla viva usa actualmente celdas `td` también en su cabecera; no se
    # presupone `th`, pero sí los nombres funcionales de las columnas.
    header_rows = [
        _fold_text(" ".join(
            cell.get_text(" ", strip=True)
            for cell in row.find_all(["th", "td"])
        ))
        for row in soup.select("tr")[:3]
    ]
    required_columns_present = any(
        "apertura" in header and "cierre" in header
        for header in header_rows
    )

    calls = []
    seen_urls = set()
    for row in soup.select("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 3:
            continue
        anchor = cells[0].find("a", href=True)
        if not anchor:
            continue
        href = anchor.get("href", "").strip()
        if "/ayudas/" not in href:
            continue
        url = _absolute_url(base, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        title = " ".join(anchor.get_text(" ", strip=True).split())
        title = re.sub(r"\s*\(\*\)\s*", "", title).strip()
        if len(title) < 3:
            continue
        open_date, open_estimated = _parse_cdti_calendar_date(
            cells[1].get_text(" ", strip=True), calendar_year,
        )
        deadline_date, deadline_estimated = _parse_cdti_calendar_date(
            cells[2].get_text(" ", strip=True), calendar_year, month_end=True,
        )
        calls.append({
            "title": title,
            "url": url,
            "open_date": open_date,
            "deadline_date": deadline_date,
            "fecha_prevista": open_estimated or deadline_estimated,
            "calendar_cells": [
                " ".join(cell.get_text(" ", strip=True).split())
                for cell in cells
            ],
        })
        if len(calls) >= CDTI_MAX_CALENDAR_CALLS:
            break
    return calls, {
        "source_version": version_date,
        "source_version_label": version_label,
        "calendar_year": calendar_year,
        "required_columns_present": required_columns_present,
    }


def _cdti_field(fields: dict[str, str], *labels: str) -> str:
    wanted = {_fold_text(label) for label in labels}
    for label, value in fields.items():
        if _fold_text(label) in wanted:
            return value
    return ""


def _parse_cdti_application_period(raw: str, default_year: int) -> tuple[str, str]:
    """Interpreta rangos abreviados como 'del 17 de junio al 16 de julio de 2026'."""
    folded = _fold_text(raw)
    months = "|".join(_SPANISH_MONTHS)
    full_range = re.search(
        rf"(?:desde\s+el|del?)\s+(\d{{1,2}})\s+de\s+({months})"
        rf"(?:\s+de\s+(20\d{{2}}))?\s+(?:al|hasta\s+el)\s+"
        rf"(\d{{1,2}})\s+de\s+({months})(?:\s+de\s+(20\d{{2}}))?",
        folded,
    )
    if full_range:
        close_year = int(full_range.group(6) or full_range.group(3) or default_year)
        open_year = int(full_range.group(3) or close_year)
        try:
            return (
                datetime(
                    open_year,
                    _SPANISH_MONTHS[full_range.group(2)],
                    int(full_range.group(1)),
                ).strftime("%Y-%m-%d"),
                datetime(
                    close_year,
                    _SPANISH_MONTHS[full_range.group(5)],
                    int(full_range.group(4)),
                ).strftime("%Y-%m-%d"),
            )
        except ValueError:
            return "", ""

    same_month = re.search(
        rf"(?:desde\s+el|del?)\s+(\d{{1,2}})\s+(?:al|hasta\s+el)\s+"
        rf"(\d{{1,2}})\s+de\s+({months})(?:\s+de\s+(20\d{{2}}))?",
        folded,
    )
    if same_month:
        year = int(same_month.group(4) or default_year)
        month = _SPANISH_MONTHS[same_month.group(3)]
        try:
            return (
                datetime(year, month, int(same_month.group(1))).strftime("%Y-%m-%d"),
                datetime(year, month, int(same_month.group(2))).strftime("%Y-%m-%d"),
            )
        except ValueError:
            return "", ""
    return "", ""


def _cdti_budget_summary(fields: dict[str, str]) -> str:
    raw = _cdti_field(fields, "Presupuesto convocatoria", "Presupuesto")
    if not raw:
        return "Ver convocatoria"
    amount = re.search(
        r"\b\d+(?:[.,]\d+)*(?:\s+millones?)?\s*(?:de\s+)?(?:euros?|EUR|€)\b",
        raw,
        re.IGNORECASE,
    )
    aid_type = _cdti_field(fields, "Tipo de la ayuda", "Tipo de ayuda")
    if amount:
        parts = [f"{amount.group(0)} total"]
        if aid_type:
            parts.append(aid_type[:100].rstrip(" ."))
        return " · ".join(parts)
    return raw[:300].rstrip()


def _parse_cdti_detail_html(
    html: str,
    detail_url: str,
    fallback_title: str,
    default_year: int,
) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup
    fields = {}
    for wrapper in main.select(".ficha-field-wrapper"):
        label_node = wrapper.select_one(".ficha-label")
        value_node = wrapper.select_one(".text")
        if not label_node or not value_node:
            continue
        label = " ".join(label_node.get_text(" ", strip=True).split())
        value = " ".join(value_node.get_text(" ", strip=True).split())
        if label and value:
            fields[label] = value

    description = " ".join(main.get_text(" ", strip=True).split())
    application_period = _cdti_field(
        fields, "Plazo de presentación", "Plazo de solicitud",
    )
    open_date, deadline_date = _extract_application_dates(
        f"Plazo de presentación: {application_period}"
    )
    if not deadline_date:
        open_date, deadline_date = _parse_cdti_application_period(
            application_period, default_year,
        )

    documents = []
    for anchor in main.find_all("a", href=True):
        href = urljoin(detail_url, anchor.get("href", "").strip())
        label = " ".join(anchor.get_text(" ", strip=True).split())
        if not href.startswith("https://"):
            continue
        if not (
            href.casefold().endswith(".pdf")
            or "/sites/default/files/" in href.casefold()
            or re.search(
                r"\b(bases|convocatoria|extracto|resolucion|documentacion)\b",
                _fold_text(label),
            )
        ):
            continue
        trace = {
            "source": "CDTI",
            "title": label or href.rsplit("/", 1)[-1],
            "url": href,
            "document_role": _document_role({"title": label, "url": href}),
        }
        if trace not in documents:
            documents.append(trace)

    title = fallback_title
    if soup.title:
        html_title = re.sub(
            r"\s*\|\s*CDTI\s*$", "", soup.title.get_text(" ", strip=True),
            flags=re.IGNORECASE,
        ).strip()
        if html_title:
            title = html_title
    return {
        "title": title,
        "description": description,
        "fields": fields,
        "open_date": open_date,
        "deadline_date": deadline_date,
        "status": _cdti_field(fields, "Estado de la convocatoria", "Estado"),
        "budget": _cdti_budget_summary(fields),
        "documents": documents,
    }


def _fetch_cdti_playwright(browser: PlaywrightBrowser) -> list:
    """Visita todas las fichas del calendario y filtra solo tras inspeccionarlas."""
    base = "https://www.cdti.es"
    calendar_url = f"{base}/calendario-de-convocatorias"
    html = browser.html(calendar_url)
    if not html:
        health = assess_web_inventory_health(
            "CDTI",
            inventory_loaded=False,
            structure_ok=False,
            discovered_count=0,
            expected_min_inventory=CDTI_MIN_EXPECTED_CALENDAR_CALLS,
            expected_date_coverage=0.8,
            max_version_age_days=CDTI_MAX_CALENDAR_VERSION_AGE_DAYS,
        )
        SOURCE_RUNTIME_METADATA["CDTI"] = {
            "status": "warn",
            "strategy": "calendario y fichas CDTI mediante Playwright",
            "calendar_loaded": False,
            "health": health,
        }
        return []

    candidates, calendar_meta = _parse_cdti_calendar_html(html)
    results = []
    checked = []
    loaded_count = 0
    closed_count = 0
    for calendar_data in candidates:
        detail_url = calendar_data["url"]
        detail_html = browser.html(detail_url)
        raw_detail = _parse_cdti_detail_html(
            detail_html,
            detail_url,
            calendar_data["title"],
            calendar_meta["calendar_year"],
        ) if detail_html else {
            "title": calendar_data["title"],
            "description": calendar_data["title"],
            "fields": {},
            "open_date": "",
            "deadline_date": "",
            "status": "",
            "budget": "Ver convocatoria",
            "documents": [],
        }
        detail_loaded = bool(
            detail_html
            and (
                raw_detail["fields"]
                or len(raw_detail.get("description", "")) >= 500
            )
        )
        loaded_count += int(detail_loaded)
        detail = raw_detail if detail_loaded else {
            "title": calendar_data["title"],
            "description": calendar_data["title"],
            "fields": {},
            "open_date": "",
            "deadline_date": "",
            "status": "",
            "budget": "Ver convocatoria",
            "documents": [],
        }

        open_date = detail["open_date"] or calendar_data["open_date"]
        deadline_date = detail["deadline_date"] or calendar_data["deadline_date"]
        detail_has_dates = bool(detail["open_date"] or detail["deadline_date"])
        fecha_prevista = False if detail_has_dates else calendar_data["fecha_prevista"]
        deadline_days = _days_until(deadline_date) if deadline_date else 90
        folded_status = _fold_text(detail["status"])
        explicitly_closed = bool(re.search(r"\bcerrad[ao]\b", folded_status))
        explicitly_open = bool(re.search(r"\babiert[ao]\b", folded_status))
        past_deadline = bool(deadline_date) and deadline_days <= 0
        status_conflict = explicitly_open and past_deadline
        closed = explicitly_closed or past_deadline
        outcome = "closed" if closed else "active_or_upcoming"
        checked.append({
            "title": calendar_data["title"],
            "url": detail_url,
            "detail_loaded": detail_loaded,
            "structured_fields": len(detail["fields"]),
            "document_links": len(detail["documents"]),
            "open_date": open_date,
            "deadline_date": deadline_date,
            "deadline_estimated": fecha_prevista,
            "source_status": detail["status"],
            "status_conflict": status_conflict,
            "outcome": outcome,
        })
        if closed:
            closed_count += 1
            audit_exclusion(
                {
                    "source": "CDTI",
                    "title": detail["title"],
                    "url": detail_url,
                    "open_date": open_date,
                    "deadline_date": deadline_date,
                },
                "deadline_closed",
                "cdti_detail_status",
            )
            continue

        description = select_evidence_excerpt(
            detail["description"], detail["title"], 20_000,
        )
        combined = f"{detail['title']} {description}"
        call = {
            "source": "CDTI",
            "title": detail["title"][:240],
            "description": description,
            "deadline_days": deadline_days,
            "deadline_date": deadline_date,
            "open_date": open_date,
            "fecha_sin_confirmar": not bool(deadline_date) or fecha_prevista,
            "fecha_prevista": fecha_prevista,
            "budget": detail["budget"],
            "url": detail_url,
            "url_generica": False,
            "keywords_found": keyword_match(combined),
            "org": "CDTI — Centro para el Desarrollo Tecnológico Industrial",
            "source_type": "Playwright CDTI (calendario + ficha oficial)",
            "source_version": calendar_meta["source_version"],
            "source_version_label": calendar_meta["source_version_label"],
            "cdti_detail_fields": {
                "beneficiaries": _cdti_field(detail["fields"], "Beneficiarios"),
                "aid_type": _cdti_field(
                    detail["fields"], "Tipo de la ayuda", "Tipo de ayuda",
                ),
                "application_period": _cdti_field(
                    detail["fields"], "Plazo de presentación", "Plazo de solicitud",
                ),
                "call_status": detail["status"],
            },
            "related_documents_trace": [
                {
                    "source": "CDTI",
                    "title": detail["title"],
                    "url": detail_url,
                    "document_role": "call",
                },
                *detail["documents"],
            ],
            "related_documents_count": 1 + len(detail["documents"]),
        }
        results.append(enrich_with_official_documents(
            call,
            detail["documents"],
            "CDTI",
        ))

    diagnostics = {
        "calendar_url": calendar_url,
        "calendar_loaded": True,
        "calendar_calls": len(candidates),
        "detail_attempted": len(candidates),
        "detail_loaded": loaded_count,
        "detail_failed": len(candidates) - loaded_count,
        "closed": closed_count,
        "active_or_upcoming": len(results),
        "status_conflicts": sum(
            bool(item.get("status_conflict")) for item in checked
        ),
        "checked_calls": checked,
    }
    health = assess_web_inventory_health(
        "CDTI",
        inventory_loaded=True,
        structure_ok=calendar_meta["required_columns_present"],
        discovered_count=len(candidates),
        detail_attempted=len(candidates),
        detail_loaded=loaded_count,
        dated_count=sum(
            bool(item.get("open_date") or item.get("deadline_date"))
            for item in checked
        ),
        published_count=len(results),
        expected_min_inventory=CDTI_MIN_EXPECTED_CALENDAR_CALLS,
        expected_date_coverage=0.8,
        source_version=calendar_meta["source_version"],
        max_version_age_days=CDTI_MAX_CALENDAR_VERSION_AGE_DAYS,
    )
    diagnostics["health"] = health
    RUN_DIAGNOSTICS["cdti_scrape_audit"] = diagnostics
    SOURCE_RUNTIME_METADATA["CDTI"] = {
        "status": "ok" if health["status"] == "healthy" else "warn",
        "strategy": "calendario y todas las fichas CDTI mediante Playwright",
        "health": health,
        **{key: diagnostics[key] for key in (
            "calendar_calls", "detail_attempted", "detail_loaded",
            "detail_failed", "closed", "active_or_upcoming",
            "status_conflicts",
        )},
    }
    log.info(
        "  CDTI Playwright: "
        f"{len(candidates)} fichas comprobadas, {loaded_count} cargadas, "
        f"{closed_count} cerradas y {len(results)} vigentes/próximas"
    )
    return results


def _cdti_program_key(item: dict) -> str:
    """Agrupa variantes de título/URL pertenecientes al mismo programa CDTI."""
    text = _fold_text(f"{item.get('title', '')} {item.get('url', '')}")
    aliases = (
        (r"eurostars.*cod\s*10|cod10.*eurostars", "eurostars_cod10"),
        (r"eurostars.*cod\s*9|cod9.*eurostars", "eurostars_cod9"),
        (r"sera.*segunda|sera-2026-2", "sera_segunda"),
        (r"sera.*primera|sera-2026-1", "sera_primera"),
        (r"cervera.*centros|centros.*cervera|ayudas-cervera-para-centros", "cervera_centros"),
        (r"transferencia tecnologica.*cervera|proyectos-cervera", "cervera_transferencia"),
        (r"proyectos?-de-i-d|proyectos? i\\+d.*linea pid|^proyectos? i\\+d\\b", "proyectos_id"),
        (r"infraestructuras?.*ensayo", "infraestructuras_ensayo"),
        (r"proyectos?.*bilaterales", "proyectos_bilaterales"),
        (r"misiones.*ciencia", "misiones"),
        (r"neotec", "neotec"),
        (r"sello.*excelencia", "sello_excelencia"),
        (r"innterconecta", "innterconecta"),
        (r"innoglobal", "innoglobal"),
        (r"ecosistemas.*innovacion", "ecosistemas_innovacion"),
        (r"prima", "prima"),
    )
    for pattern, key in aliases:
        if re.search(pattern, text):
            return key
    clean_url = re.sub(r"[?#].*$", "", str(item.get("url", "")).rstrip("/").casefold())
    return clean_url or re.sub(r"\W+", "_", text).strip("_")


def _merge_cdti_results(*result_groups: list) -> list:
    """
    Fusiona catálogo, calendario y API. Los datos vivos tienen prioridad y el
    catálogo solo completa campos ausentes. Las keywords se acumulan.
    """
    merged = {}
    for group in result_groups:
        for item in group:
            key = _cdti_program_key(item)
            previous = merged.get(key)
            if previous is None:
                merged[key] = dict(item)
                continue

            combined = dict(item)
            for field in (
                "description",
                "deadline_date",
                "open_date",
                "budget",
                "url",
                "org",
                "source_version",
                "source_version_label",
            ):
                if not combined.get(field) and previous.get(field):
                    combined[field] = previous[field]

            if not combined.get("deadline_date") and previous.get("deadline_date"):
                combined["deadline_days"] = previous.get("deadline_days", 90)
                combined["fecha_sin_confirmar"] = previous.get("fecha_sin_confirmar", True)
                combined["fecha_prevista"] = previous.get("fecha_prevista", False)

            combined["keywords_found"] = sorted(set(
                previous.get("keywords_found", []) + combined.get("keywords_found", [])
            ))
            source_types = {
                previous.get("source_type", ""),
                combined.get("source_type", ""),
            }
            combined["source_type"] = " + ".join(sorted(value for value in source_types if value))
            merged[key] = combined

    results = list(merged.values())
    results.sort(key=lambda item: (item.get("deadline_days", 9999), item.get("title", "")))
    log.info(f"  CDTI combinado: {len(results)} convocatorias únicas vigentes")
    return results


# Códigos que prueban que la ficha ya no existe. Cualquier otro resultado
# —incluido un bloqueo de WAF, un 5xx o un fallo de red— deja la entrada en su
# sitio: un catálogo curado no debe vaciarse porque el servidor tenga un mal día.
CDTI_DEAD_URL_STATUSES = frozenset({404, 410})


def _drop_catalog_entries_with_dead_urls(
    browser: PlaywrightBrowser, curated: list
) -> tuple[list, list]:
    """
    Comprueba con el navegador las URLs del catálogo curado y aparta las que
    ya no existen.

    Hace falta el navegador y no `requests`: cdti.es está tras un WAF que
    responde 200 a un cliente sin apariencia de navegador sea cual sea la ruta,
    incluida una inventada, de modo que verificar por código HTTP desde el
    cliente HTTP normal da siempre «correcta» (ver AGENTS.md, sección 44).

    Devuelve las entradas vivas y el detalle de las apartadas, para que la
    ejecución pueda dejar constancia en su diagnóstico.
    """
    if not curated:
        return curated, []
    vivas = []
    caidas = []
    comprobadas = {}
    for entry in curated:
        url = entry.get("url", "")
        if not url:
            vivas.append(entry)
            continue
        if url not in comprobadas:
            comprobadas[url] = browser.status(url)
        status = comprobadas[url]
        if status in CDTI_DEAD_URL_STATUSES:
            caidas.append({
                "title": entry.get("title", ""),
                "url": url,
                "status": status,
            })
            audit_exclusion(
                {
                    "source": "CDTI",
                    "title": entry.get("title", ""),
                    "url": url,
                },
                "catalog_url_not_found",
                "cdti_catalog_url_check",
            )
            log.warning(
                f"  CDTI: la ficha del catálogo curado ya no existe "
                f"(HTTP {status}): {entry.get('title', '')[:60]}"
            )
            continue
        vivas.append(entry)
    if caidas:
        log.warning(
            f"  CDTI: {len(caidas)} entrada(s) del catálogo curado apartadas "
            f"por URL inexistente; revisar el catálogo"
        )
    return vivas, caidas


# Palabras que no distinguen un documento de otro al comparar títulos.
_CATALOG_TITLE_STOPWORDS = frozenset({
    "de", "del", "la", "las", "el", "los", "y", "a", "en", "para", "por",
    "linea", "ayudas", "ayuda", "convocatoria", "cdti", "ventanilla",
    "abierta", "permanente", "todo",
})


def _catalog_programme_document(entry_title: str, documents: list) -> list:
    """El documento de la ficha que describe el programa, si se reconoce.

    Una ficha de CDTI enlaza su propio PDF —el que lleva «Entidades
    beneficiarias», «Actividades excluidas» y «Gastos financiables»— junto a
    dos o tres documentos genéricos que aparecen en todas (FAQ de empresas en
    crisis, medidas de exención de garantías). Se distingue por lo obvio: su
    título repite el nombre del programa.

    Se devuelve con `document_role` de bases reguladoras porque es lo que es
    para este pipeline —la fuente de las condiciones—, y porque
    `enrich_with_official_documents()` solo descarga esos roles. Sin esta
    reclasificación el documento llegaba en el rastro pero sin una línea de
    texto, que fue justo lo que se midió la primera vez.
    """
    objetivo = {
        palabra for palabra in _fold_text(entry_title).split()
        if palabra not in _CATALOG_TITLE_STOPWORDS and len(palabra) > 2
    }
    mejor, coincidencias = None, 0
    for documento in documents:
        tokens = {
            palabra for palabra in _fold_text(documento.get("title", "")).split()
            if palabra not in _CATALOG_TITLE_STOPWORDS and len(palabra) > 2
        }
        comunes = len(objetivo & tokens)
        if comunes > coincidencias:
            mejor, coincidencias = documento, comunes
    # Dos palabras significativas en común: menos es casualidad, y con menos se
    # colaría el FAQ genérico en las fichas de título corto.
    if mejor is None or coincidencias < 2:
        return []
    return [{**mejor, "document_role": "regulatory_bases"}]


def _attach_catalog_official_documents(
    browser: PlaywrightBrowser, curated: list
) -> list:
    """Da a las fichas de ventanilla abierta las bases que sí publica CDTI.

    Las entradas del catálogo curado llegaban con ~300 caracteres tecleados a
    mano y **cero documentos**, mientras las del calendario oficial llegaban con
    sus bases adjuntas. De ahí que las cuatro de ventanilla abierta —PID,
    Cervera, Bilaterales, Infraestructuras de Ensayo— salieran siempre con la
    elegibilidad «por confirmar»: nadie le estaba enseñando al modelo quién
    puede solicitarlas (AGENTS.md 51.2).

    La ficha ya se visita con el navegador para comprobar que existe; aquí se
    aprovecha para leerla. Se reutiliza el mismo extractor que el calendario,
    así que un cambio en la maquetación de CDTI se arregla en un solo sitio.
    """
    if not curated:
        return curated
    enriquecidas = []
    con_documentos = 0
    for entry in curated:
        url = entry.get("url", "")
        # Solo las fichas concretas, que en cdti.es viven bajo /ayudas/. Una
        # página de programa lista PDF de varias convocatorias y adjuntárselos
        # a una sola sería peor que no adjuntar nada. No se usa `url_generica`
        # para decidirlo: es una marca escrita a mano que ya se quedó vieja una
        # vez —las tres fichas corregidas el 21/08 siguieron marcadas como
        # genéricas— y la ruta es un hecho comprobable.
        if not url or "/ayudas/" not in url:
            enriquecidas.append(entry)
            continue
        try:
            html = browser.html(url)
        except Exception as exc:
            log.warning(f"  CDTI: no se pudo leer la ficha {url}: {exc}")
            enriquecidas.append(entry)
            continue
        if not html:
            enriquecidas.append(entry)
            continue
        detalle = _parse_cdti_detail_html(
            html, url, entry.get("title", ""), datetime.now().year
        )
        documentos = _catalog_programme_document(
            entry.get("title", ""), detalle.get("documents") or []
        )
        if not documentos:
            enriquecidas.append(entry)
            continue
        con_documentos += 1
        entry = {
            **entry,
            "related_documents_trace": [
                {
                    "source": "CDTI",
                    "title": entry.get("title", ""),
                    "url": url,
                    "document_role": "call",
                },
                *documentos,
            ],
            "related_documents_count": 1 + len(documentos),
        }
        enriquecidas.append(
            enrich_with_official_documents(entry, documentos, "CDTI")
        )
    if con_documentos:
        log.info(
            f"  CDTI: {con_documentos} ficha(s) del catálogo curado con sus "
            f"documentos oficiales"
        )
    return enriquecidas


def fetch_cdti(browser: PlaywrightBrowser) -> list:
    """
    Combina el calendario oficial renderizado y el catálogo curado. La BDNS se
    consulta una sola vez mediante `fetch_bdns()` como inventario transversal y
    se consolida posteriormente, sin repetir aquí el acceso al portal.
    """
    log.info("Consultando CDTI (calendario Playwright + catálogo curado)...")
    browser_results = _fetch_cdti_playwright(browser)
    curated_results = _fetch_cdti_static()
    curated_results, dead_catalog_urls = _drop_catalog_entries_with_dead_urls(
        browser, curated_results
    )
    RUN_DIAGNOSTICS.setdefault("cdti_scrape_audit", {})[
        "catalog_dead_urls"
    ] = dead_catalog_urls
    curated_results = _attach_catalog_official_documents(browser, curated_results)
    if not browser_results:
        log.warning("CDTI: fuentes en vivo sin resultados; cobertura solo mediante catálogo curado")
    # Prioridad creciente: catálogo < calendario oficial.
    return _merge_cdti_results(curated_results, browser_results)
