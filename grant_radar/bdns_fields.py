# bdns_fields.py — lectura de los campos que entrega la API de BDNS
#
# Primitivas que traducen la forma real de SNPSAP a valores utilizables:
# descripciones que llegan como cadena, lista o lista de dicts; códigos
# CNAE/NACE dentro de esas descripciones; la sección NACE de un código; si la
# lista de beneficiarios admite empresas; y el plazo de ejecución declarado en
# el texto.
#
# Viven en su propio módulo, y no dentro del conector, porque las comparten dos
# consumidores que no se pueden mover juntos: `grant_radar/sources/bdns.py` y
# la matriz de reglas previa a Claude (`_bdns_pre_claude_gate()` y la
# resolución de holds), que sigue deliberadamente en `Grant-Radar-prueba.py`
# (AGENTS.md sección 4.1). El script principal las reimporta, igual que ya
# hacía con `BDNS_DIRECT_OWN_INVESTMENT_TERMS`, así que el conector se pudo
# extraer sin tocar una línea de esa matriz.
#
# Aquí no se decide nada sobre elegibilidad: solo se lee lo que la fuente dice.

import re

from grant_radar.parsing_helpers import _fold_text


BDNS_NAMED_ACCESS_TERMS = (
    "subvencion nominativa", "beneficiario identificado",
    "beneficiario preseleccionado", "convenio con beneficiario",
    "proyecto previamente seleccionado", "subvencion a favor de",
    "subvencion directa excepcional", "convenio a suscribir con",
)


# Umbral de "empresa de nueva creacion" y vocabulario tecnologico. Los usan la
# matriz de reglas previa a Claude (Grant-Radar-prueba.py) y la resolucion de
# holds (grant_radar/holds.py), que ya no pueden verse entre si: por eso viven
# aqui, igual que BDNS_NAMED_ACCESS_TERMS.
BDNS_NEW_ESTABLISHMENT_MIN_DAYS = 730
BDNS_TECHNOLOGY_TERMS = (
    "ahorro energetico", "eficiencia energetica", "eficiencia termica",
    "energia industrial", "calor residual", "recuperacion de calor",
    "descarbonizacion", "hidrogeno", "combustion", "hornos industriales",
    "emisiones industriales", "depuracion de gases", "tratamiento de gases",
    "valorizacion de residuos", "waste heat", "energy efficiency",
    "industrial heat", "flue gas", "hydrogen", "decarbonisation",
)


def _bdns_descriptions(value) -> list[str]:
    """Conserva las descripciones de los catalogos estructurados de SNPSAP."""
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    descriptions = []
    for entry in value:
        if isinstance(entry, dict):
            description = next((
                entry.get(key) for key in (
                    "descripcion", "descripcionLeng", "nombre", "label", "codigo",
                ) if entry.get(key)
            ), "")
        else:
            description = entry
        cleaned = " ".join(str(description or "").split())
        if cleaned and cleaned not in descriptions:
            descriptions.append(cleaned)
    return descriptions


def _bdns_codes(value) -> list[str]:
    if not isinstance(value, list):
        value = [value] if value else []
    return [
        " ".join(str(entry.get("codigo") or "").split())
        for entry in value if isinstance(entry, dict) and entry.get("codigo")
    ]


def _nace_section(value: str) -> str:
    text = _fold_text(str(value or "")).strip()
    explicit = re.search(r"(?:seccion|section)\s+([a-u])\b", text)
    if explicit:
        return explicit.group(1).upper()
    match = re.search(r"\b(\d{1,2})(?:[.\s]|\b)", text)
    if not match:
        return ""
    division = int(match.group(1))
    ranges = (
        (1, 3, "A"), (5, 9, "B"), (10, 33, "C"), (35, 35, "D"),
        (36, 39, "E"), (41, 43, "F"), (45, 47, "G"), (49, 53, "H"),
        (55, 56, "I"), (58, 63, "J"), (64, 66, "K"), (68, 68, "L"),
        (69, 75, "M"), (77, 82, "N"), (84, 84, "O"), (85, 85, "P"),
        (86, 88, "Q"), (90, 93, "R"), (94, 96, "S"), (97, 98, "T"),
        (99, 99, "U"),
    )
    return next((section for start, end, section in ranges if start <= division <= end), "")


def _bdns_company_eligible(beneficiaries: list[str]) -> bool:
    folded = [_fold_text(value) for value in beneficiaries]
    return any(
        "gran empresa" in value
        or "pyme" in value
        or "pequena y mediana empresa" in value
        or bool(re.search(r"\bempresas?\b", value))
        or (
            "persona fisica" in value
            and "actividad economica" in value
            and "no desarrollan" not in value
        )
        for value in folded
    )


def _bdns_execution_days(text: str) -> int | None:
    folded = _fold_text(text)
    candidates = []
    patterns = (
        r"(?:plazo|periodo|duracion).{0,70}?(\d{1,3})\s*(mes(?:es)?|anos?|dias?)",
        r"ejecucion.{0,70}?(\d{1,3})\s*(mes(?:es)?|anos?|dias?)",
    )
    for pattern in patterns:
        for amount, unit in re.findall(pattern, folded):
            number = int(amount)
            candidates.append(
                number * 365 if unit.startswith("ano")
                else number * 30 if unit.startswith("mes")
                else number
            )
    return max(candidates) if candidates else None
