# partner_catalog.py — catálogo de socios técnicos y su preselección
#
# Lee grant_radar/partner_catalog.json (la lista de entidades y sus
# capacidades) y expone la función que recomienda socios para una
# convocatoria según las categorías tecnológicas detectadas
# (grant_radar/tech_taxonomy.py). Añadir o corregir un socio es editar el
# JSON; la lógica de puntuación (región, colaboración previa, experiencia
# UE) sigue en Python porque decide "cómo" se recomienda, no "quién existe".

import json
from pathlib import Path

_CATALOG_FILE = Path(__file__).parent / "partner_catalog.json"

with open(_CATALOG_FILE, "r", encoding="utf-8") as _f:
    _DATA = json.load(_f)

PARTNER_CATALOG = _DATA["partners"]

# Categorías relacionadas que también cuentan al valorar un socio: alguien
# con capacidad de combustión, por ejemplo, es relevante para una
# convocatoria de combustión de hidrógeno aunque su ficha no repita esa
# etiqueta exacta.
_CAPABILITY_EXPANSION = {
    "hydrogen_combustion": {"hydrogen_supply", "hydrogen_safety", "combustion"},
    "thermal_processes": {"combustion", "cfd", "industrial_demo"},
    "digital_thermal": {"hpc", "data", "modelling", "industrial_control",
                         "predictive_maintenance"},
    "thermal_waste": {"circularity", "materials", "industrial_demo"},
    "circular_manufacturing": {"circularity", "materials", "industrial_demo"},
    "energy_efficiency": {"energy_systems", "lca"},
}


def preselect_partners(tech_tags: list[str], limit: int = 6) -> list[dict]:
    """
    Selecciona candidatos por capacidades verificadas. CDTI e IDAE no están en
    el catálogo porque son financiadores, no socios técnicos recomendables.
    """
    requested = set(tech_tags)
    expanded = set(requested)
    for tag in requested:
        expanded.update(_CAPABILITY_EXPANSION.get(tag, set()))

    ranked = []
    for partner in PARTNER_CATALOG:
        overlap = sorted(expanded.intersection(partner["capabilities"]))
        score = len(overlap) * 10
        score += 3 if partner["region"] == "Aragón" else 0
        score += 2 if partner["prior_collaboration"] else 0
        score += 1 if partner["eu_experience"] else 0
        if overlap:
            candidate = dict(partner)
            candidate["matching_capabilities"] = overlap
            candidate["preselection_score"] = score
            ranked.append(candidate)
    ranked.sort(key=lambda item: (-item["preselection_score"], item["name"]))
    return ranked[:limit]
