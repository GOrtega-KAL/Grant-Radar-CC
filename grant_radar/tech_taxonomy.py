# tech_taxonomy.py — taxonomía tecnológica de Kalfrisa y su clasificación
#
# Lee grant_radar/tech_taxonomy.json (el vocabulario: qué palabras
# corresponden a cada categoría técnica) y expone tanto los datos derivados
# (TECH_TAGS, KEYWORDS...) como las funciones que comparan un texto contra
# esa taxonomía. Ampliar el vocabulario de una categoría existente es editar
# el JSON; añadir una categoría nueva sigue necesitando tocar este archivo,
# porque cada categoría puede participar de forma distinta en el resto del
# pipeline (ver AGENTS.md, sección 4, "Principios de extracción y análisis").
#
# Antes de cambiar el JSON, añadir primero un caso a
# tests/fixtures/common_scope_filter_cases.json o a los fixtures BDNS/ECCP,
# como exige AGENTS.md para cualquier ajuste de vocabulario.

import json
import re
from pathlib import Path

from grant_radar.parsing_helpers import _fold_text

_TAXONOMY_FILE = Path(__file__).parent / "tech_taxonomy.json"

with open(_TAXONOMY_FILE, "r", encoding="utf-8") as _f:
    _DATA = json.load(_f)

TECH_TAG_STRONG_TERMS = {
    tag: list(terms) for tag, terms in _DATA["strong_terms"].items()
}
TECH_TAG_CONTEXTUAL_TERMS = {
    tag: list(terms) for tag, terms in _DATA["contextual_terms"].items()
}
TECH_DISCOVERY_TERMS = tuple(_DATA["discovery_terms"])
TECH_TAG_COMPAT_ALIASES = {
    tag: set(codes) for tag, codes in _DATA["compat_aliases"].items()
}
INDUSTRIAL_CONTEXT_TERMS = list(_DATA["industrial_context_terms"])

# Contrato de categorías aceptadas por el esquema, el frontend y Haiku.
TECH_TAGS = {
    tag: list(dict.fromkeys(
        TECH_TAG_STRONG_TERMS.get(tag, [])
        + TECH_TAG_CONTEXTUAL_TERMS.get(tag, [])
    ))
    for tag in dict.fromkeys([
        *TECH_TAG_STRONG_TERMS.keys(), *TECH_TAG_CONTEXTUAL_TERMS.keys(),
    ])
}

KEYWORDS = sorted({
    keyword
    for tag_keywords in TECH_TAGS.values()
    for keyword in tag_keywords
})

# Superconjunto de INDUSTRIAL_CONTEXT_TERMS con matices adicionales para
# exigir contexto a una expresión ambigua (ver _contextual_term_present).
# dict.fromkeys conserva el orden y elimina duplicados entre ambas listas,
# igual que en el script original.
TECH_CONTEXT_TERMS = tuple(dict.fromkeys([
    *INDUSTRIAL_CONTEXT_TERMS,
    *_DATA["tech_context_extra_terms"],
]))


def _term_present(text: str, term: str) -> bool:
    """Evita falsos positivos de siglas: RTO no debe casar con demonstration."""
    folded_text = _fold_text(text)
    folded_term = _fold_text(term).strip()
    if not folded_term:
        return False
    return bool(re.search(
        rf"(?<![a-z0-9]){re.escape(folded_term)}(?![a-z0-9])",
        folded_text,
    ))


def _contextual_term_present(text: str, term: str, window: int = 280) -> bool:
    """Exige contexto industrial/térmico cerca de una expresión ambigua."""
    folded_text = _fold_text(text)
    folded_term = _fold_text(term).strip()
    if not folded_term:
        return False
    pattern = re.compile(
        rf"(?<![a-z0-9]){re.escape(folded_term)}(?![a-z0-9])"
    )
    for match in pattern.finditer(folded_text):
        excerpt = folded_text[
            max(0, match.start() - window):min(len(folded_text), match.end() + window)
        ]
        if any(_term_present(excerpt, context) for context in TECH_CONTEXT_TERMS):
            return True
    return False


def detect_tech_tags(text: str) -> list[str]:
    """Clasificación determinista y auditable según la taxonomía tecnológica."""
    detected = []
    for tag in TECH_TAGS:
        strong = any(
            _term_present(text, term)
            for term in TECH_TAG_STRONG_TERMS.get(tag, [])
        )
        contextual = any(
            _contextual_term_present(text, term)
            for term in TECH_TAG_CONTEXTUAL_TERMS.get(tag, [])
        )
        if strong or contextual:
            detected.append(tag)
    return detected


def has_technology_discovery_signal(text: str) -> bool:
    """Señal amplia para abrir un registro; nunca decide su compatibilidad."""
    return bool(
        detect_tech_tags(text)
        or any(_term_present(text, term) for term in TECH_DISCOVERY_TERMS)
    )


def _compat_tags_for(tech_tags: list[str]) -> list[str]:
    """Devuelve los códigos cortos antiguos equivalentes a `tech_tags`, para
    el campo público `tags` (compatibilidad hacia atrás; no altera `tech_tags`)."""
    return sorted({
        compat_code
        for tag in tech_tags
        for compat_code in TECH_TAG_COMPAT_ALIASES.get(tag, set())
    })


def keyword_match(text: str) -> list:
    """Devuelve las keywords encontradas en el texto."""
    return [kw for kw in KEYWORDS if _term_present(text, kw)]


def is_relevant(text: str, min_matches: int = 1) -> bool:
    """
    Prefiltro de alta cobertura. Una mención genérica a eficiencia o net-zero
    solo se acepta si existe además contexto industrial; las familias técnicas
    específicas son relevantes por sí solas.
    """
    tags = detect_tech_tags(text)
    specific_tags = set(tags) - {"energy_efficiency"}
    if specific_tags:
        return True
    return (
        "energy_efficiency" in tags
        and any(_term_present(text, term) for term in INDUSTRIAL_CONTEXT_TERMS)
    )
