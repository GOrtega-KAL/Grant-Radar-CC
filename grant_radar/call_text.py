# call_text.py — lectura de texto de convocatoria común a varias fuentes
#
# Helpers que interpretan el texto de una convocatoria y que usan varias
# fuentes a la vez (ECCP, EEN, IDAE, BDNS y el prefiltro): mecanismo de
# financiación (directa o en cascada), identificador oficial europeo, fecha
# límite y presupuesto declarados en prosa, y enlaces externos de una ficha.
#
# Van aquí y no en `parsing_helpers.py` porque ese módulo es deliberadamente
# texto y fechas puros: `_external_links()` necesita BeautifulSoup y todos
# estos helpers hablan ya el vocabulario del dominio (convocatoria, deadline,
# presupuesto), no el de las cadenas de caracteres.
#
# Sin estado, sin red, sin caché, sin Claude.

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from grant_radar.parsing_helpers import _fold_text, _parse_flexible_date
from grant_radar.tech_taxonomy import _term_present


FUNDING_CONTEXT_TERMS = (
    "subvencion", "ayuda", "grant", "funding", "financial support",
    "open call", "convocatoria", "call for proposal", "cascade funding",
    "lump sum", "cofinanciacion", "co-financing",
)

CALL_LINK_TERMS = (
    "call", "apply", "application", "funding", "grant", "guideline",
    "eligibility", "convocatoria", "solicitud", "financiacion", "open-call",
)


def _funding_mechanism(text: str) -> str:
    folded = _fold_text(text)
    if any(term in folded for term in (
        "cascade funding", "financial support to third parties", "fstp",
        "financiacion en cascada", "open call for smes", "eurocluster",
        "grant amount provided by", "funding provided by the project",
        "third party support", "sub-grant", "subgrant",
    )):
        return "cascade"
    if any(_term_present(folded, term) for term in FUNDING_CONTEXT_TERMS):
        return "direct"
    return "unknown"


def _official_call_identifier(text: str) -> str:
    """Extrae identificadores europeos sin depender de una call concreta."""
    folded_original = " ".join(str(text).split())
    patterns = (
        r"\b(?:HORIZON|DIGITAL|LIFE|SMP|CEF|EIC|EIT|INTERREG)-[A-Z0-9][A-Z0-9._-]{5,}\b",
        r"/competitive-calls-cs/(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, folded_original, re.IGNORECASE)
        if match:
            return (match.group(1) if match.lastindex else match.group(0)).upper()
    eurostars = re.search(
        r"\bEUROSTARS(?:\s+3)?\s+CALL\s+(\d{1,3})\b",
        folded_original,
        re.IGNORECASE,
    )
    if eurostars:
        return f"EUROSTARS-CALL-{eurostars.group(1)}"
    return ""


def _extract_deadline_from_text(text: str) -> str:
    folded = _fold_text(text)
    for pattern in (
        r"(?:deadline|closing date|fecha limite|cierre)\s*[:\-]?\s*([^\n|]{4,50})",
        r"(?:apply by|applications? close|submit by)\s*[:\-]?\s*([^\n|]{4,50})",
        r"(?:until|hasta)\s+([^\n|]{4,40})",
    ):
        match = re.search(pattern, folded, re.IGNORECASE)
        if match:
            parsed = _parse_flexible_date(match.group(1))
            if parsed:
                return parsed
    return ""


def _external_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    host = urlparse(base_url).netloc.casefold()
    links = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, anchor.get("href", ""))
        parsed = urlparse(href)
        if parsed.scheme != "https" or not parsed.netloc or parsed.netloc.casefold() == host:
            continue
        if href not in links:
            links.append(href)
    return links


def _extract_funding_budget(text: str) -> str:
    """Recupera un presupuesto explícito sin inferir ni sumar importes."""
    compact = " ".join(str(text or "").split())
    number = r"\d(?:[\d\s.,]*\d)?"
    amount = rf"(?:EUR|EURO|euros?|€)\s*{number}(?:\s*(?:million|millones?))?|{number}\s*(?:million|millones?)?\s*(?:EUR|EURO|euros?|€)"
    for pattern in (
        rf"(?:total available budget|total budget|overall budget|presupuesto total|dotacion)\s*(?:of|de)?\s*[:\-]?\s*({amount})",
        rf"(?:budget|presupuesto)\s*[:\-]?\s*({amount})",
    ):
        match = re.search(pattern, compact, re.IGNORECASE)
        if match:
            return f"{match.group(1).strip().rstrip('.,;:')} total"
    return "Ver convocatoria"
