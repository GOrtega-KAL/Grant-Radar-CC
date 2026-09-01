# bdns.py — conector BDNS / SNPSAP (Base de Datos Nacional de Subvenciones)
#
# Inventario transversal del sistema: recorre `convocatorias/ultimas` y
# `convocatorias/busqueda` de la API REST oficial, pide el detalle de las filas
# candidatas y las traduce al formato interno. Su `bdns_id` prevalece como
# identidad fuerte cuando la misma ayuda llega también por BOE, IDAE o CDTI.
#
# Dos cosas que conviene saber antes de tocarlo:
#
# - La API ignora en silencio los filtros de administración o región en
#   servidor, así que el filtrado es en cliente (`grant_radar/bdns_scope.py`).
#   Por eso `BDNS_LATEST_MAX_PAGES` ensancha la ventana para TODAS las
#   administraciones, no solo para Aragón (AGENTS.md sección 26).
# - Los PDF de `documentos` se recuperan por su identificador numérico; el
#   detalle no trae la URL (AGENTS.md sección 13, piloto v3).
#
# La decisión de relevancia NO está aquí: la toma la matriz previa a Claude
# (`_bdns_pre_claude_gate()`), que vive en grant_radar/bdns_rules.py. Este módulo
# solo lee la fuente. Las primitivas de campo que ambos comparten están en
# `grant_radar/bdns_fields.py`.

import calendar
import json
import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests

from grant_radar.bdns_fields import (
    BDNS_NAMED_ACCESS_TERMS,
    _bdns_codes,
    _bdns_company_eligible,
    _bdns_descriptions,
    _bdns_execution_days,
    _nace_section,
)
from grant_radar.bdns_scope import (
    _bdns_is_aragon_regional_administration,
    _bdns_is_prefilter_candidate,
)
from grant_radar.call_text import _extract_deadline_from_text
from grant_radar.http_client import _http_get, _is_safe_public_https_url
from grant_radar.parsing_helpers import (
    _days_until,
    _fold_text,
    _parse_flexible_date,
    _signed_days_until,
    _web_url_or_empty,
    select_evidence_excerpt,
)
from grant_radar.runtime_state import SOURCE_RUNTIME_METADATA
from grant_radar.tech_taxonomy import keyword_match

log = logging.getLogger("grant_radar")


# ── BDNS / SNPSAP: API REST oficial ─────────────────────────────────────────
BDNS_API_BASE = "https://www.infosubvenciones.es/bdnstrans/api"
BDNS_PUBLIC_BASE = "https://www.pap.hacienda.gob.es/bdnstrans/GE/es/convocatorias"
BDNS_PAGE_SIZE = 100
# Ventana cubierta por `convocatorias/ultimas` (BDNS), TODAS las
# administraciones (la API no filtra por región en servidor — ver AGENTS.md
# sección 26). La ventana es deslizante: la estrecha el volumen publicado, no
# el tiempo. Mediciones reales de 35 páginas × 100 filas:
#
#   17-18/08/2026   ~44 filas/día   ≈ 79 días
#   20/08/2026      ~54 filas/día   ≈ 65 días   (AGENTS.md 40.4)
#   31/08/2026      ~52 filas/día      67 días  (medido contra la API)
#
# Es decir, entre 5 y 7 días de colchón sobre el mínimo de negocio de 60, no
# los 19 que sugería la primera medición. Si una medición posterior muestra
# una densidad mayor, subir páginas —y actualizar la prueba de regresión, que
# fija la densidad más alta observada—, nunca mover la cifra a ciegas.
BDNS_LATEST_MAX_PAGES = 35
BDNS_SEARCH_GROUPS = (
    "industria eficiencia energia descarbonizacion",
    "innovacion investigacion desarrollo demostracion",
    "hidrogeno calor hornos combustion emisiones",
    "economia circular residuos digitalizacion",
)


def _bdns_document_records(detail: dict) -> list[dict]:
    """Extrae enlaces oficiales de documentos/anuncios sin asumir claves fijas."""
    records = []

    def walk(value, kind: str, inherited_title: str = "") -> None:
        if isinstance(value, list):
            for entry in value:
                walk(entry, kind, inherited_title)
            return
        if not isinstance(value, dict):
            return
        title = next((
            " ".join(str(value.get(key) or "").split())
            for key in ("nombre", "titulo", "descripcion", "descripcionLeng", "label")
            if value.get(key)
        ), inherited_title)
        document_id = value.get("id")
        if kind == "document" and str(document_id or "").isdigit():
            candidate = (
                f"{BDNS_API_BASE}/convocatorias/documentos"
                f"?idDocumento={int(document_id)}"
            )
            records.append({
                "title": title or str(value.get("nombreFic") or f"Documento {document_id}"),
                "url": candidate,
                "kind": kind,
                "source_key": "id",
                "published_date": _parse_flexible_date(value.get("datPublicacion", "")),
            })
        for key, nested in value.items():
            if isinstance(nested, (dict, list)):
                walk(nested, kind, title)
                continue
            candidate = str(nested or "").strip()
            if candidate.startswith("/"):
                candidate = urljoin(f"{BDNS_API_BASE}/", candidate)
            if not _is_safe_public_https_url(candidate):
                continue
            record = {
                "title": title or candidate.rsplit("/", 1)[-1],
                "url": candidate,
                "kind": kind,
                "source_key": str(key),
                "published_date": _parse_flexible_date(value.get("datPublicacion", "")),
            }
            if not any(existing["url"] == candidate for existing in records):
                records.append(record)

    walk(detail.get("documentos"), "document")
    walk(detail.get("anuncios"), "announcement")
    return records


def _bdns_call_publication_date(detail: dict) -> str:
    """Primera publicación del anuncio de convocatoria, no la fecha del PDF."""
    dates = sorted({
        parsed
        for announcement in detail.get("anuncios", [])
        if isinstance(announcement, dict)
        for parsed in [_parse_flexible_date(announcement.get("datPublicacion", ""))]
        if parsed
    })
    if dates:
        return dates[0]
    received = _parse_flexible_date(detail.get("fechaRecepcion", ""))
    received_dt = (
        datetime.strptime(received, "%Y-%m-%d") if received else None
    )
    document_dates = []
    for document in detail.get("documentos", []):
        if not isinstance(document, dict):
            continue
        published = _parse_flexible_date(document.get("datPublicacion", ""))
        descriptor = _fold_text(" ".join(str(document.get(key) or "") for key in (
            "descripcion", "nombreFic",
        )))
        if not published or not any(term in descriptor for term in (
            "convocatoria", "extracto", "texto en castellano", "bases y convocatoria",
        )):
            continue
        published_dt = datetime.strptime(published, "%Y-%m-%d")
        if received_dt and abs((published_dt - received_dt).days) > 45:
            continue
        document_dates.append(published)
    return min(document_dates) if document_dates else ""


def _add_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _bdns_relative_application_deadline(
    raw_text: str,
    publication_date: str,
) -> tuple[str, bool]:
    """Calcula plazos relativos publicados; marca hábiles como estimados."""
    if not raw_text or not publication_date:
        return "", False
    try:
        published = datetime.strptime(publication_date, "%Y-%m-%d")
    except ValueError:
        return "", False
    folded = _fold_text(raw_text)
    word_numbers = {
        "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3,
        "cuatro": 4, "cinc": 5, "cinco": 5, "seis": 6,
        "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
        "once": 11, "doce": 12, "trece": 13, "catorce": 14,
        "quince": 15, "veinte": 20, "treinta": 30,
    }
    day_match = re.search(
        r"\b(\d{1,3}|un|uno|una|dos|tres|cuatro|cinc|cinco|seis|"
        r"siete|ocho|nueve|diez|once|doce|trece|catorce|quince|veinte|treinta)"
        r"\s*(?:dias?|dies)\s*(naturales?|naturals?|habiles?|habils?)\b",
        folded,
    )
    if day_match:
        raw_amount = day_match.group(1)
        amount = int(raw_amount) if raw_amount.isdigit() else word_numbers[raw_amount]
        unit = day_match.group(2)
        if unit.startswith(("natural", "natur")):
            return (published + timedelta(days=amount)).strftime("%Y-%m-%d"), False
        cursor = published
        remaining = amount
        while remaining > 0:
            cursor += timedelta(days=1)
            if cursor.weekday() < 5:
                remaining -= 1
        return cursor.strftime("%Y-%m-%d"), True
    if "dia del mes equivalente al del dia de la publicacion" in folded:
        return _add_calendar_months(published, 1).strftime("%Y-%m-%d"), False
    month_match = re.search(
        r"\b(\d{1,2}|un|uno|una|dos|tres|cuatro|cinc|cinco|seis)\s+"
        r"(?:mes|meses|mesos)\b",
        folded,
    )
    if month_match:
        raw_amount = month_match.group(1)
        amount = int(raw_amount) if raw_amount.isdigit() else word_numbers[raw_amount]
        return _add_calendar_months(published, amount).strftime("%Y-%m-%d"), False
    return "", False


def _bdns_detail_to_raw(
    detail: dict,
    listing: dict,
    include_closed: bool = False,
) -> dict | None:
    title = " ".join(str(
        detail.get("descripcion") or listing.get("descripcion") or ""
    ).split())
    bdns_id = str(
        detail.get("codigoBDNS") or listing.get("numeroConvocatoria") or ""
    ).strip()
    if not title or not bdns_id:
        return None
    open_date = (
        _parse_flexible_date(detail.get("fechaInicioSolicitud", ""))
        or _parse_flexible_date(detail.get("textInicio", ""))
    )
    deadline_date = (
        _parse_flexible_date(detail.get("fechaFinSolicitud", ""))
        or _parse_flexible_date(detail.get("textFin", ""))
    )
    deadline_estimated = False
    call_publication_date = _bdns_call_publication_date(detail)
    if not deadline_date:
        relative_deadline, relative_estimated = _bdns_relative_application_deadline(
            str(detail.get("textFin") or ""), call_publication_date
        )
        signed_relative = _signed_days_until(relative_deadline)
        if relative_deadline and (
            not relative_estimated
            or (signed_relative is not None and (signed_relative > 0 or signed_relative < -14))
        ):
            deadline_date = relative_deadline
            deadline_estimated = relative_estimated
    signed_deadline_days = _signed_days_until(deadline_date)
    if (
        deadline_date and signed_deadline_days is not None
        and signed_deadline_days <= 0 and not include_closed
    ):
        return None
    structured_parts = []
    for key in (
        "descripcionBasesReguladoras", "descripcionFinalidad", "objetivos",
        "textInicio", "textFin", "tipoConvocatoria",
    ):
        value = detail.get(key)
        if value:
            structured_parts.append(str(value))
    for key in (
        "tiposBeneficiarios", "instrumentos", "regiones", "sectores",
        "sectoresProductos", "fondos", "documentos", "anuncios",
    ):
        value = detail.get(key)
        if value:
            structured_parts.append(json.dumps(value, ensure_ascii=False))
    description = select_evidence_excerpt(
        " ".join([title, *structured_parts]), title, 20_000
    )
    if not deadline_date:
        deadline_date = _extract_deadline_from_text(" ".join(structured_parts))
        if deadline_date and _days_until(deadline_date) <= 0:
            return None

    beneficiary_types = _bdns_descriptions(detail.get("tiposBeneficiarios"))
    regions = _bdns_descriptions(detail.get("regiones"))
    sectors = _bdns_descriptions(detail.get("sectores"))
    sector_products = _bdns_descriptions(detail.get("sectoresProductos"))
    nace_sections = sorted({
        section for section in (
            _nace_section(value) for value in [
                *sectors, *sector_products,
                *_bdns_codes(detail.get("sectores")),
                *_bdns_codes(detail.get("sectoresProductos")),
            ]
        ) if section
    })
    finality = " | ".join(_bdns_descriptions(detail.get("finalidad")))
    if not finality:
        finality = " ".join(str(detail.get("descripcionFinalidad") or "").split())
    objectives = " ".join(str(detail.get("objetivos") or "").split())
    instruments = _bdns_descriptions(detail.get("instrumentos"))
    award_mode = " ".join(str(detail.get("tipoConvocatoria") or "").split())
    received_date = _parse_flexible_date(
        detail.get("fechaRecepcion") or listing.get("fechaRecepcion") or ""
    )
    combined_folded = _fold_text(" ".join([title, description, award_mode]))
    open_flag = detail.get("abierto")
    explicitly_open = open_flag is True or _fold_text(str(open_flag or "")) in {
        "1", "s", "si", "true", "abierto",
    }
    indefinite = any(term in combined_folded for term in (
        "ventanilla permanente", "plazo indefinido", "convocatoria abierta permanentemente",
        "hasta el agotamiento", "hasta agotamiento", "sin plazo de cierre",
    ))
    if deadline_date:
        active_status = (
            "closed"
            if signed_deadline_days is not None and signed_deadline_days <= 0
            else "confirmed_deadline"
        )
        deadline_days = _days_until(deadline_date)
    elif indefinite:
        active_status = "open_ended"
        deadline_days = 365
    else:
        received_days = _signed_days_until(received_date)
        active_status = (
            "unverified_recent"
            if received_days is not None and -365 <= received_days <= 30
            else "unverified_old"
        )
        # Sentinel interno: la matriz BDNS lo retira antes de Claude. No se
        # publica ni se presenta como un plazo real.
        deadline_days = 1

    named_award = any(
        term in combined_folded for term in BDNS_NAMED_ACCESS_TERMS
    ) or bool(re.match(r"^sn\s+a(?:l|\s+la)?\b", _fold_text(title)))
    preselected_award = any(term in combined_folded for term in (
        "proyectos seleccionados previamente", "seleccion previa en la convocatoria",
        "entidades seleccionadas previamente", "seleccionado en la convocatoria europea",
    ))
    instrumental_award = "instrumental" in _fold_text(award_mode) or any(
        term in combined_folded for term in (
        "aportacion dineraria a la entidad", "transferencia nominativa",
        "financiacion de la encomienda", "compensacion a la entidad gestora",
        )
    )
    call_access = (
        "named" if named_award else "preselected" if preselected_award
        else "instrumental" if instrumental_award else "open_or_unknown"
    )

    territorial_requirement = "unknown"
    existing_centre_patterns = (
        r"(?:centro de trabajo|establecimiento|sede)\s+(?:ya\s+)?(?:situad[oa]|ubicad[oa]|radicad[oa])",
        r"disponer de (?:un )?(?:centro de trabajo|establecimiento|sede)",
        r"(?:centro de trabajo|establecimiento|sede).{0,60}(?:fecha de solicitud|presentacion de la solicitud)",
        r"(?:para|dirigid[oa]s? a) (?:empresas|pymes) de (?:la provincia|la demarcacion|el municipio|la comunidad)",
        r"(?:empresas|pymes) (?:domiciliadas|radicadas|ubicadas) en",
    )
    new_centre_patterns = (
        r"(?:compromiso|comprometerse).{0,70}(?:abrir|crear|implantar|establecer).{0,30}(?:centro|establecimiento|sede)",
        r"(?:abrir|crear|implantar|establecer).{0,30}(?:centro|establecimiento|sede).{0,70}(?:tras|despues|posterior)",
    )
    project_location_patterns = (
        r"(?:proyecto|actuacion|inversion).{0,50}(?:ejecutarse|realizarse|desarrollarse|ubicarse)",
        r"localizacion (?:del proyecto|de la inversion|de la actuacion)",
    )
    if any(re.search(pattern, combined_folded) for pattern in existing_centre_patterns):
        territorial_requirement = "existing_establishment"
    elif any(re.search(pattern, combined_folded) for pattern in new_centre_patterns):
        territorial_requirement = "new_establishment_allowed"
    elif any(re.search(pattern, combined_folded) for pattern in project_location_patterns):
        territorial_requirement = "project_location_only"
    explicit_local_company_scope = any(
        re.search(pattern, combined_folded) for pattern in existing_centre_patterns[-2:]
    )
    explicit_outside_aragon = explicit_local_company_scope and not any(
        place in combined_folded for place in ("aragon", "zaragoza", "huesca", "teruel")
    )

    org_value = detail.get("organo")
    org_levels = org_value if isinstance(org_value, dict) else {}
    admin_type = str(org_levels.get("nivel1") or listing.get("nivel1") or "").strip()
    budget_value = detail.get("presupuestoTotal")
    try:
        budget = f"€{float(budget_value):,.0f}" if budget_value is not None else "Ver convocatoria"
    except (TypeError, ValueError):
        budget = "Ver convocatoria"
    if isinstance(org_value, dict):
        org = " · ".join(str(value) for value in org_value.values() if value)
    else:
        org = str(org_value or listing.get("nivel3") or listing.get("nivel2") or "BDNS")
    return {
        "source": "BDNS",
        "identifier": bdns_id,
        "bdns_id": bdns_id,
        "bdns_url": f"{BDNS_PUBLIC_BASE}/{bdns_id}",
        "title": title[:500],
        "description": description,
        "deadline_days": deadline_days,
        "deadline_date": deadline_date,
        "open_date": open_date,
        "fecha_sin_confirmar": not bool(deadline_date) or deadline_estimated,
        "budget": budget,
        # La sede electronica es texto libre en la API y a veces trae una
        # frase entera, no una URL (AGENTS.md, punto 31): si no es
        # navegable se publica la ficha oficial de BDNS, que siempre lo es.
        "url": (
            _web_url_or_empty(detail.get("sedeElectronica"))
            or f"{BDNS_PUBLIC_BASE}/{bdns_id}"
        ),
        "keywords_found": keyword_match(f"{title} {description}"),
        "org": org,
        "source_type": "API REST SNPSAP",
        "funding_mechanism": "direct",
        "document_role": "call",
        "discovery_sources": ["BDNS"],
        "bdns_filter_ready": True,
        "bdns_active_status": active_status,
        "bdns_api_open_flag": explicitly_open,
        "bdns_received_date": received_date,
        "bdns_call_publication_date": call_publication_date,
        "bdns_admin_type": admin_type,
        "bdns_admin_levels": org_levels,
        "bdns_regions": regions,
        "bdns_beneficiary_types": beneficiary_types,
        "bdns_company_eligible": _bdns_company_eligible(beneficiary_types),
        "bdns_nace_codes": [*sectors, *sector_products],
        "bdns_nace_sections": nace_sections,
        "bdns_finality": finality,
        "bdns_objectives": objectives,
        "bdns_instruments": instruments,
        "bdns_award_mode": award_mode,
        "bdns_call_access": call_access,
        "bdns_territorial_requirement": territorial_requirement,
        "bdns_explicit_outside_aragon": explicit_outside_aragon,
        "bdns_project_execution_days": _bdns_execution_days(description),
        "bdns_is_open_ended": indefinite,
        "bdns_state_aid_reference": str(detail.get("referenciaAyudaEstado") or ""),
        "bdns_is_mrr": bool(detail.get("mrr") or detail.get("esMRR")),
        "bdns_documents": _bdns_document_records(detail),
        "opportunity_role": "direct_beneficiary" if _bdns_company_eligible(beneficiary_types) else "unknown",
        "opportunity_labels": [],
    }


def fetch_bdns() -> list:
    """Inventario general BDNS por la API REST oficial documentada."""
    log.info("Consultando BDNS (API REST oficial SNPSAP)...")
    listings = {}
    pages_read = 0
    errors = 0
    session = requests.Session()

    def collect(endpoint: str, params: dict, max_pages: int) -> None:
        nonlocal pages_read, errors
        for page in range(max_pages):
            response = _http_get(
                f"{BDNS_API_BASE}/{endpoint}",
                params={
                    **params, "page": page, "pageSize": BDNS_PAGE_SIZE,
                    "order": "fechaRecepcion", "direccion": "desc",
                },
                session=session,
            )
            if response is None:
                errors += 1
                break
            try:
                payload = response.json()
            except ValueError:
                errors += 1
                break
            pages_read += 1
            rows = payload.get("content", [])
            for row in rows:
                code = str(row.get("numeroConvocatoria", "")).strip()
                if code:
                    listings[code] = row
            if payload.get("last", False) or not rows:
                break
            time.sleep(0.12)

    collect("convocatorias/ultimas", {}, BDNS_LATEST_MAX_PAGES)
    for query in BDNS_SEARCH_GROUPS:
        collect(
            "convocatorias/busqueda",
            {"descripcion": query, "descripcionTipoBusqueda": 2},
            3,
        )
    candidates = [row for row in listings.values() if _bdns_is_prefilter_candidate(row)]
    results = []
    for index, listing in enumerate(candidates):
        bdns_id = str(listing.get("numeroConvocatoria", "")).strip()
        response = _http_get(
            f"{BDNS_API_BASE}/convocatorias",
            params={"numConv": bdns_id},
            session=session,
        )
        if response is None:
            errors += 1
            continue
        try:
            raw = _bdns_detail_to_raw(response.json(), listing)
        except ValueError:
            errors += 1
            continue
        if raw:
            results.append(raw)
        if index and index % 20 == 0:
            time.sleep(0.2)
    SOURCE_RUNTIME_METADATA["BDNS"] = {
        "status": "warn" if errors else "ok",
        "strategy": "API REST SNPSAP: últimas + búsquedas temáticas + detalle",
        "inventory_unique": len(listings),
        "prefilter_candidates": len(candidates),
        "aragon_admin_candidates": sum(
            1 for row in candidates if _bdns_is_aragon_regional_administration(row)
        ),
        "pages_read": pages_read,
        "errors": errors,
    }
    log.info(f"  → {len(results)} convocatorias BDNS candidatas ({len(listings)} inventariadas)")
    return results


def fetch_bdns_by_id(
    bdns_id: str,
    session: requests.Session | None = None,
    include_closed: bool = True,
) -> dict | None:
    """Recupera un detalle BDNS concreto para diagnósticos acotados."""
    code = str(bdns_id or "").strip()
    if not code:
        return None
    response = _http_get(
        f"{BDNS_API_BASE}/convocatorias",
        params={"numConv": code},
        session=session or requests.Session(),
    )
    if response is None:
        return None
    try:
        return _bdns_detail_to_raw(
            response.json(), {"numeroConvocatoria": code},
            include_closed=include_closed,
        )
    except (TypeError, ValueError):
        return None
