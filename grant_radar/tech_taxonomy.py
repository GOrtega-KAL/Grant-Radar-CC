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
from functools import lru_cache
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


# Las palabras de tres letras o menos NO se pluralizan, y esto no es un detalle
# de estilo: en este vocabulario son todas siglas (`rto`, `voc`, `cov`, `cfd`)
# o partículas (`de`, `of`, `en`, `del`).
#
# Lo aprendimos pagando en atención, no en dinero. La primera versión sí las
# pluralizaba, y `rto` pasó a casar con «RTOs». En el vocabulario de Kalfrisa
# `RTO` es un *Regenerative Thermal Oxidizer*; en la letra pequeña de Horizon,
# «RTOs» son las *Research and Technology Organisations*, que aparecen en casi
# todos los topics. Resultado: ocho convocatorias irrelevantes —infraestructura
# cuántica, mundos virtuales, software de automoción— entraron al embudo de una
# sola pasada (AGENTS.md 59.4).
#
# El docstring original de `_term_present()` ya avisaba de esto mismo: «evita
# falsos positivos de siglas: RTO no debe casar con demonstration». El guardián
# de límites lo impedía; pluralizar sin más lo reabrió por otra puerta.
PLURAL_MIN_LENGTH = 3


@lru_cache(maxsize=4096)
def _term_pattern(folded_term: str) -> re.Pattern | None:
    """
    Patrón de un término ya plegado, tolerante al plural.

    Cada palabra admite el sufijo `-s` o `-es`, porque el español
    administrativo de las convocatorias escribe casi siempre en plural y la
    coincidencia exacta lo perdía: «recuperación de calores residuales» no
    activaba `calor residual`, que es el negocio central del cliente
    (AGENTS.md 56.2). Afectaba igual a `recuperadores`, `intercambiadores de
    calor industriales` y `tratamientos térmicos`.

    **Solo plural, no género.** Se midió aparte: aceptar `-o`/`-a` no cambia
    ni una clasificación sobre 368 textos reales, y las formas que añade
    —«procesos térmicas»— son concordancias incorrectas que una convocatoria
    no escribe (AGENTS.md 58). No reabrirlo.

    Se conserva el guardián de límites `(?<![a-z0-9])…(?![a-z0-9])`, que es
    lo que evita los falsos positivos de siglas —RTO no debe casar con
    demonstration— y lo que impide que `término` case dentro de
    `térmicamente`.
    """
    if not folded_term:
        return None
    cuerpo = r"\s+".join(
        re.escape(palabra) + (r"(?:e?s)?" if len(palabra) > PLURAL_MIN_LENGTH else "")
        for palabra in folded_term.split()
    )
    return re.compile(rf"(?<![a-z0-9]){cuerpo}(?![a-z0-9])")


def _term_present(text: str, term: str) -> bool:
    """Evita falsos positivos de siglas: RTO no debe casar con demonstration."""
    pattern = _term_pattern(_fold_text(term).strip())
    if pattern is None:
        return False
    return bool(pattern.search(_fold_text(text)))


def _contextual_term_present(text: str, term: str, window: int = 280) -> bool:
    """Exige contexto industrial/térmico cerca de una expresión ambigua."""
    folded_text = _fold_text(text)
    pattern = _term_pattern(_fold_text(term).strip())
    if pattern is None:
        return False
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
