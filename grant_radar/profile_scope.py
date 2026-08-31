# profile_scope.py — ámbito del perfil de Kalfrisa, decidido sin modelo
#
# Dos exclusiones deterministas que responden a la misma pregunta —¿esta
# convocatoria queda fuera del perfil por su propio enunciado?— y que tienen
# dos consumidores distintos, y por eso viven aquí y no en ninguno de ellos:
#
#   - `deterministic_prefilter()` y `_bdns_pre_claude_gate()`, en
#     Grant-Radar-prueba.py, las usan ANTES de llamar a Claude, para no pagar
#     por una convocatoria que ya se sabe ajena.
#   - `_build_compatible_analysis()`, en grant_radar/analysis.py, vuelve a
#     aplicar `_hard_out_of_scope()` DESPUÉS del modelo, como salvaguarda: si
#     Haiku puntúa alto algo que la regla sectorial descarta, manda la regla y
#     el caso queda marcado como discrepancia (`rule_model_discrepancy`).
#
# No están en deterministic_rules.py porque aquel módulo declara actuar solo
# sobre hechos y evaluación ya extraídos, y estas dos deciden además quién
# llega a Claude. Tampoco en analysis.py, porque eso obligaría a la matriz de
# reglas a importar de la capa de Claude para no llamarla.
#
# Ninguna decide por sector o título a solas: todas exigen ausencia de conexión
# térmica industrial explícita, que es la línea que el perfil sí traza.

import re

from grant_radar.exclusion_terms import (
    BUILDING_TERMS,
    CIVIL_SECURITY_TERMS,
    CYBERSECURITY_TERMS,
    EDUCATION_HEALTH_TERMS,
    GENERIC_DIGITAL_POLICY_TERMS,
    GOVERNANCE_PRIMARY_TERMS,
    MARINE_POLICY_TERMS,
    NUCLEAR_TERMS,
    RENEWABLE_GENERATION_TERMS,
    TRANSPORT_TERMS,
)
from grant_radar.parsing_helpers import _fold_text
from grant_radar.tech_taxonomy import _term_present, detect_tech_tags


PROFILE_INCOMPATIBLE_EXCLUSIVE_ENTITY_TYPES = (
    "cluster organisations", "cluster organizations",
    "digital innovation hubs", "regional development agencies",
)


DIRECT_MEMBER_SUPPORT_TERMS = (
    "funding to member companies", "funding for member companies",
    "grants to member companies", "financial support to member companies",
    "costs incurred by member companies", "pilots implemented by member companies",
)


def _explicit_profile_incompatibility(conv: dict) -> str | None:
    """Detecta incompatibilidades formales; nunca decide por título o sector solo."""
    text = _fold_text(f"{conv.get('title', '')} {conv.get('description', '')}")
    alternative_route = any(term in text for term in (
        "complementary sectors", "complementary sector", "technology providers are eligible",
        "machinery providers are eligible", "other sectors are eligible",
    ))
    mandatory_owned_product = any(term in text for term in (
        "have at least one product", "must have at least one product",
        "have at least one drone product", "must own a product",
        "proprietary hardware product", "develop and manufacture a tangible",
    ))
    restricted_sector = any(term in text for term in (
        "eligible applicants must be", "applicants must operate in",
        "only companies operating in", "solicitantes deben pertenecer",
        "solicitantes deberan pertenecer",
    )) and bool(re.search(r"\b(?:in|del|al)\s+(?:the\s+)?[^.;]{2,80}\bsector\b", text))
    capability_connection = bool(detect_tech_tags(text))
    if (
        mandatory_owned_product and restricted_sector
        and not capability_connection and not alternative_route
    ):
        return (
            "La convocatoria exige que el solicitante pertenezca a un sector "
            "restringido y disponga de producto propio, sin conexión tecnológica "
            "con el perfil de Kalfrisa ni vía complementaria elegible."
        )

    exclusive_access = any(term in text for term in (
        "open exclusively to", "eligible exclusively", "only eligible applicants",
        "exclusivamente para", "unicamente pueden solicitar",
    ))
    incompatible_entities = sum(
        term in text for term in PROFILE_INCOMPATIBLE_EXCLUSIVE_ENTITY_TYPES
    )
    member_support = any(term in text for term in DIRECT_MEMBER_SUPPORT_TERMS)
    if exclusive_access and incompatible_entities >= 2 and not member_support:
        return (
            "Los solicitantes están restringidos expresamente a entidades "
            "intermediarias incompatibles y no consta financiación, costes o "
            "pilotos ejecutados por empresas miembro."
        )
    return None


def _hard_out_of_scope(conv: dict, tech_tags: list[str]) -> str | None:
    """
    Aplica exclusiones sectoriales del perfil solo cuando no existe una conexión
    térmica industrial explícita. Evita delegar descartes inequívocos al modelo.
    """
    title_text = _fold_text(conv.get("title", ""))
    text = _fold_text(f"{conv.get('title', '')} {conv.get('description', '')}")
    tags = set(tech_tags)
    thermal_core = {
        "waste_heat", "hydrogen_combustion", "emissions",
        "thermal_processes", "thermal_waste",
    }
    transport_is_scope = any(
        _term_present(title_text, term) for term in TRANSPORT_TERMS
    )
    if transport_is_scope and not tags.intersection(thermal_core):
        return (
            "Transporte o movilidad sin una conexión térmica industrial "
            "explícita; sector excluido por el perfil de Kalfrisa."
        )

    if (
        any(term in title_text for term in BUILDING_TERMS)
        and "industrial process" not in title_text
    ):
        return (
            "Edificios residenciales o terciarios sin aplicación a procesos "
            "térmicos industriales; ámbito excluido por el perfil."
        )

    if (
        any(term in title_text for term in CYBERSECURITY_TERMS)
        and not tags.intersection(thermal_core)
    ):
        return (
            "Ciberseguridad como objeto exclusivo, sin proceso termico, emisiones "
            "o valorizacion industrial vinculados a las capacidades de Kalfrisa."
        )

    if (
        any(term in title_text for term in CIVIL_SECURITY_TERMS)
        and not tags.intersection(thermal_core)
    ):
        return (
            "Seguridad civil, desastres o seguridad vial sin una aplicacion "
            "termica o de proceso industrial explicita."
        )

    if (
        (
            any(term in title_text for term in GOVERNANCE_PRIMARY_TERMS)
            or bool(re.search(r"\blife-[a-z0-9-]+-gov\b", title_text))
        )
        and not tags.intersection(thermal_core)
    ):
        return (
            "Gobernanza, economia social o asesoramiento al sector primario como "
            "objeto principal, sin tecnologia termica industrial explicita."
        )

    if (
        any(_term_present(title_text, term) for term in RENEWABLE_GENERATION_TERMS)
        and not tags.intersection(thermal_core)
    ):
        return (
            "Generación eléctrica renovable sin componente térmico industrial "
            "explícito; ámbito excluido por el perfil."
        )
    if (
        any(_term_present(title_text, term) for term in NUCLEAR_TERMS)
        and "industrial process" not in title_text
        and "waste heat" not in title_text
    ):
        return (
            "Tecnología nuclear sin integración térmica en un proceso industrial "
            "explícito; ámbito ajeno a las capacidades acreditadas de Kalfrisa."
        )

    strong_thermal_tags = {
        "waste_heat", "hydrogen_combustion", "thermal_processes", "thermal_waste",
    }
    if (
        any(term in title_text for term in MARINE_POLICY_TERMS)
        and not tags.intersection(strong_thermal_tags)
    ):
        return (
            "Medio marino, pesca o gobernanza ambiental como objeto principal, "
            "sin proceso térmico industrial explícito."
        )

    if (
        any(term in title_text for term in GENERIC_DIGITAL_POLICY_TERMS)
        and not tags.intersection(strong_thermal_tags)
    ):
        return (
            "Tecnología digital, cuántica o actividad de ecosistema genérica sin "
            "integración térmica o de proceso industrial explícita."
        )
    if (
        any(_term_present(title_text, term) for term in EDUCATION_HEALTH_TERMS)
        and not tags
    ):
        return (
            "Educación o salud mental como objeto principal, sin conexión "
            "térmica, energética, ambiental o de proceso industrial."
        )
    return None
