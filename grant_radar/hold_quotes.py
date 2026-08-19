# hold_quotes.py — validación de las citas que resuelven un hold de BDNS
#
# Cuando una convocatoria queda en espera por falta de datos, se recupera la
# evidencia oficial y se le pide a Haiku una cita literal que resuelva la causa
# concreta. Este módulo comprueba que esa cita **prueba la conclusión**, no solo
# que aparece en el documento: una fecha de solicitud pasada para un cierre,
# obligación y establecimiento previo para el requisito de centro, señales de
# participación formal para un consorcio, y de apoyo directo a empresas miembro
# para la vía clúster.
#
# Es la diferencia entre "el modelo dijo que sí" y "la fuente lo dice": sin
# esta capa, una cita sobre el plazo de ejecución podía aceptarse como prueba
# de cierre, que es uno de los falsos rechazos que invalidaron el piloto v1
# (AGENTS.md sección 13).
#
# Texto puro: sin red, sin caché, sin Claude y sin reglas de negocio.

import re
import unicodedata
from datetime import datetime

from grant_radar.parsing_helpers import (
    _SPANISH_MONTHS,
    _fold_text,
    _parse_flexible_date,
)


def _hold_resolution(
    decision: str,
    reason_code: str,
    explanation: str,
    resolved_by: str,
    facts: dict | None = None,
) -> dict:
    return {
        "decision": decision,
        "reason_code": reason_code,
        "explanation": explanation,
        "resolved_by": resolved_by,
        "facts": facts or {},
    }


def _hold_question(hold_reason: str) -> str:
    return {
        "active_status_unverified": (
            "Determina si la solicitud está abierta, es próxima, tiene ventanilla "
            "indefinida, está cerrada o no puede determinarse."
        ),
        "territorial_eligibility_unverified": (
            "Determina si exige un centro previo en el territorio, solo localizar "
            "allí el proyecto, permite abrir un centro después o no impone restricción."
        ),
        "new_establishment_duration_unknown": (
            "Determina el plazo confirmado para implantar el centro y ejecutar el proyecto."
        ),
        "consortium_role_unverified": (
            "Determina si una empresa como Kalfrisa puede ser miembro formal con "
            "actividad, costes o presupuesto propios, y no solo contratista."
        ),
        "cluster_role_unverified": (
            "Determina si el apoyo llega a empresas miembro, pilotos o costes "
            "empresariales, en lugar de financiar solo la estructura del clúster."
        ),
    }.get(hold_reason, "Resuelve únicamente la causa indicada usando evidencia explícita.")


def _normalize_evidence_quote(value: str) -> str:
    """Normaliza solo diferencias tipográficas; no permite paráfrasis."""
    folded = _fold_text(value).replace("\u00ad", "")
    return re.sub(r"[\W_]+", " ", folded, flags=re.UNICODE).strip()


def _quote_mentions_date(quote: str, iso_date: str) -> bool:
    parsed = _parse_flexible_date(iso_date)
    if not parsed:
        return False
    year, month, day = (int(value) for value in parsed.split("-"))
    folded = _fold_text(quote)
    numeric_variants = (
        f"{day:02d}/{month:02d}/{year}", f"{day}/{month}/{year}",
        f"{day:02d}-{month:02d}-{year}", f"{day:02d}.{month:02d}.{year}",
        f"{year}-{month:02d}-{day:02d}",
    )
    if any(value in folded for value in numeric_variants):
        return True
    month_names = [
        name for name, number in _SPANISH_MONTHS.items() if number == month
    ]
    return str(year) in folded and any(
        re.search(rf"\b0?{day}\s+(?:de\s+)?{name}\b", folded)
        for name in month_names
    )


def _quote_supports_territorial_condition(quote: str, condition: str) -> bool:
    folded = _normalize_evidence_quote(quote)
    establishment = r"(?:centro de trabajo|establecimiento|sede|centro operativo)"
    obligation = r"(?:deber|debera|deberan|debe|requisito|cuenten|contar|disponer|tener)"
    if condition == "existing_establishment":
        return bool(
            re.search(rf"{obligation}.{{0,100}}{establishment}", folded)
            or re.search(rf"{establishment}.{{0,100}}{obligation}", folded)
        )
    if condition == "new_establishment_allowed":
        return bool(re.search(
            r"(?:abrir|crear|implantar|establecer).{0,50}"
            r"(?:centro|establecimiento|sede)", folded
        ))
    if condition == "project_location_only":
        project_marker = re.search(
            r"(?:proyecto|actuacion|inversion|instalacion|obras?|servei|servicio)",
            folded,
        )
        location_marker = re.search(
            r"(?:realic|ejecut|desarroll|ubic|localiz|territori|municip|puert)",
            folded,
        )
        return bool(project_marker and location_marker and not re.search(establishment, folded))
    # La ausencia de una restricción no puede demostrarse con una cita positiva aislada.
    return False


def _quote_supports_consortium_participation(quote: str) -> bool:
    folded = _normalize_evidence_quote(quote)
    consortium = (
        "consorcio", "agrupacion de empresas", "proyecto en cooperacion",
        "socios", "miembros",
    )
    direct_participation = (
        "beneficiario", "cobeneficiario", "costes elegibles", "costes subvencionables",
        "presupuesto", "paquete de trabajo", "actividad del proyecto",
        "empresas participantes", "entidades participantes",
    )
    commercial_only = (
        "contratista", "subcontratista", "proveedor externo", "adjudicatario",
    )
    return (
        any(term in folded for term in consortium)
        and any(term in folded for term in direct_participation)
        and not any(term in folded for term in commercial_only)
    )


def _quote_supports_cluster_members(quote: str) -> bool:
    folded = _normalize_evidence_quote(quote)
    return any(term in folded for term in ("cluster", "agrupacion", "asociacion")) and any(
        term in folded for term in (
            "empresas miembro", "empresas de", "participacion en proyectos",
            "proyectos de las empresas", "competitividad de las empresas",
            "beneficiarios finales", "apoyo a terceros",
        )
    )
