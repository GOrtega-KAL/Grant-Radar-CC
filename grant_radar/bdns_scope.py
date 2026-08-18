# bdns_scope.py — filtros puros a nivel de listado BDNS (antes de pedir detalle)
#
# Decide qué filas de `convocatorias/ultimas` y `convocatorias/busqueda`
# entran como candidatas al resto del embudo (detalle, bases, prefiltro
# determinista, Claude). No es una decisión de relevancia final — eso lo hace
# `_bdns_pre_claude_gate()`, que sigue en Grant-Radar-prueba.py — solo evita
# pedir el detalle de filas evidentemente irrelevantes. Sin estado, sin red,
# sin caché, sin Claude.

from grant_radar.parsing_helpers import _fold_text
from grant_radar.tech_taxonomy import has_technology_discovery_signal


def _bdns_candidate_from_listing(item: dict) -> bool:
    text = " ".join(str(item.get(key, "")) for key in (
        "descripcion", "descripcionLeng", "nivel1", "nivel2", "nivel3",
    ))
    folded = _fold_text(text)
    broad_terms = (
        "industr", "energia", "energet", "innov", "investig", "desarroll",
        "digital", "descarbon", "emision", "hidrogen", "circular", "residu",
        "fabric", "empresa", "pyme", "tecnolog", "clima", "medioambient",
    )
    return bool(
        has_technology_discovery_signal(text)
        or any(term in folded for term in broad_terms)
    )


def _bdns_is_aragon_regional_administration(item: dict) -> bool:
    """True si la fila procede de la Comunidad Autónoma de Aragón.

    Filtro estructurado, no de texto libre: usa `nivel1`/`nivel2` tal como
    los entrega la API en el listado (antes de pedir el detalle). Valores
    observados de `nivel1`: AUTONOMICA, LOCAL, ESTADO, OTROS. Administraciones
    LOCAL (ayuntamientos, diputaciones) quedan fuera deliberadamente aunque su
    `nivel2` mencione Aragón: publican en el Boletín Oficial de la Provincia,
    no en BOA, y están fuera de alcance de este filtro (ver AGENTS.md
    sección 26).
    """
    admin_level = _fold_text(str(item.get("nivel1", ""))).strip()
    admin_name = _fold_text(str(item.get("nivel2", "")))
    return admin_level == "autonomica" and "aragon" in admin_name


def _bdns_is_prefilter_candidate(item: dict) -> bool:
    """Combina en OR las dos señales: palabra clave amplia o administración
    autonómica de Aragón. Una convocatoria autonómica de Aragón entra siempre
    como candidata a evaluación, aunque su descripción no contenga ninguna
    palabra clave de industria/energía/innovación."""
    return (
        _bdns_candidate_from_listing(item)
        or _bdns_is_aragon_regional_administration(item)
    )
