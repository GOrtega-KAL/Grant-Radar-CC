# parsing_helpers.py — utilidades de texto y fechas sin estado
#
# Todo lo que hay en este archivo son funciones "puras": reciben texto y
# devuelven texto o fechas, sin leer archivos, sin llamar a Claude, sin
# depender de caché ni de reglas de negocio. Por eso fue el primer bloque
# que se separó del script principal (`Grant-Radar-prueba.py`, ~11.000
# líneas): se puede leer, probar y modificar sin entender el resto del
# pipeline. Lo usan varios conectores de fuentes (CDTI, EEN, IDAE, BOE...)
# para interpretar fechas en español y comparar títulos entre sí.
#
# Ver tests/test_grant_radar_parsing_helpers.py para pruebas aisladas de
# este módulo, sin cargar el resto del script.

import calendar
import re
import unicodedata
from datetime import datetime

# Traduce el nombre de un mes en español a su número (1-12). Se admite
# "setiembre" además de "septiembre" porque ambas formas aparecen en fuentes
# oficiales españolas.
_SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def _fold_text(value: str) -> str:
    """Minúsculas sin acentos para comparar títulos y familias de programas."""
    normalized = unicodedata.normalize("NFKD", str(value))
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def _signed_days_until(date_str: str) -> int | None:
    """Días con signo hasta una fecha; ``None`` si no puede interpretarse."""
    if not date_str:
        return None
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
        try:
            dt = datetime.strptime(date_str[:10], fmt[:10])
            return (dt.date() - datetime.now().date()).days
        except Exception:
            pass
    return None


def _days_until(date_str: str) -> int:
    """Convierte una fecha ISO o formato europeo a días restantes."""
    signed_days = _signed_days_until(date_str)
    if signed_days is not None:
        return max(0, signed_days)
    return 90


def _date_to_iso(raw: str) -> str:
    """Convierte una fecha corta (dd/mm/aaaa, dd-mm-aaaa...) a formato ISO."""
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip()[:10], fmt).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            pass
    return ""


def _parse_flexible_date(raw: str) -> str:
    """Interpreta una fecha en varios formatos posibles, incluida la forma
    larga en español ("15 de septiembre de 2026") o inglés."""
    text = " ".join(str(raw or "").replace("\xa0", " ").split())
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    folded = _fold_text(text)
    month_names = {
        **_SPANISH_MONTHS,
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    match = re.search(
        r"\b(\d{1,2})\s+(?:de\s+)?([a-z]+)\s+(?:de\s+)?(20\d{2})\b",
        folded,
    )
    if match and match.group(2) in month_names:
        try:
            return datetime(
                int(match.group(3)), month_names[match.group(2)], int(match.group(1))
            ).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return ""


def _parse_cdti_calendar_date(
    raw: str,
    default_year: int,
    month_end: bool = False,
) -> tuple[str, bool]:
    """
    Convierte fechas en español (calendario CDTI y otras fuentes similares)
    a ISO. Devuelve (fecha_iso, es_estimada). Cuando solo se publica el mes,
    se usa el primer día para apertura y el último para cierre, marcándolo
    siempre como estimación.
    """
    clean = re.sub(r"\(\*\)", "", str(raw)).strip()
    folded = _fold_text(clean)
    if not folded:
        return "", True

    day_match = re.search(
        r"\b(\d{1,2})\s+de\s+([a-z]+)(?:\s+(?:de\s+)?(20\d{2}|\d{2}))?\b",
        folded,
    )
    if day_match:
        day = int(day_match.group(1))
        month = _SPANISH_MONTHS.get(day_match.group(2))
        if not month:
            return "", True
        year_raw = day_match.group(3)
        year = int(year_raw) if year_raw else default_year
        if year < 100:
            year += 2000
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d"), False
        except ValueError:
            return "", True

    month_match = re.search(
        r"\b(" + "|".join(_SPANISH_MONTHS) + r")(?:\s+(20\d{2}|\d{2}))?\b",
        folded,
    )
    if not month_match:
        return "", True
    month = _SPANISH_MONTHS[month_match.group(1)]
    year_raw = month_match.group(2)
    year = int(year_raw) if year_raw else default_year
    if year < 100:
        year += 2000
    day = calendar.monthrange(year, month)[1] if month_end else 1
    return datetime(year, month, day).strftime("%Y-%m-%d"), True


def _extract_date_range(text: str) -> tuple[str, str]:
    """Extrae apertura y cierre de texto renderizado, sin asumir un HTML concreto."""
    date_pattern = r"(\d{1,2}[./-]\d{1,2}[./-]\d{4})"
    range_match = re.search(
        date_pattern + r"\s*(?:al|a|hasta|-|–)\s*" + date_pattern,
        text,
        re.IGNORECASE,
    )
    if range_match:
        return _date_to_iso(range_match.group(1)), _date_to_iso(range_match.group(2))

    dates = {}
    labels = (
        (
            r"\b(?:inicio|apertura|desde|comienzo)\b[^.\n]{0,100}?"
            + date_pattern,
            "open",
        ),
        (
            r"\b(?:fin|finalizaci.n|cierre|hasta|vencimiento)\b"
            r"[^.\n]{0,100}?" + date_pattern,
            "close",
        ),
    )
    for pattern, key in labels:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            dates[key] = _date_to_iso(match.group(1))
    return dates.get("open", ""), dates.get("close", "")


def _extract_spanish_application_dates(text: str) -> tuple[str, str]:
    """Extrae plazos expresados como «15 de septiembre de 2026»."""
    folded = _fold_text(text)
    month_names = "|".join(_SPANISH_MONTHS)
    textual_date = (
        rf"\d{{1,2}}\s+de\s+(?:{month_names})"
        rf"(?:\s+de)?\s+20\d{{2}}"
    )
    scope_patterns = (
        rf"(?:plazo|solicitudes?|presentacion)[^.\n]{{0,300}}?"
        rf"(?:desde|inicio|comenzara)[^.\n]{{0,120}}?({textual_date})"
        rf"[^.\n]{{0,220}}?(?:hasta|fin|finalizara)[^.\n]{{0,120}}?({textual_date})",
        rf"(?:desde|inicio)[^.\n]{{0,100}}?({textual_date})"
        rf"[^.\n]{{0,220}}?(?:hasta|fin)[^.\n]{{0,100}}?({textual_date})",
    )
    for pattern in scope_patterns:
        match = re.search(pattern, folded, re.IGNORECASE)
        if match:
            open_date, _ = _parse_cdti_calendar_date(match.group(1), datetime.now().year)
            close_date, _ = _parse_cdti_calendar_date(
                match.group(2),
                datetime.now().year,
                month_end=True,
            )
            if open_date or close_date:
                return open_date, close_date

    # Algunas fichas oficiales separan con punto la apertura relativa y el
    # cierre absoluto: «El plazo para presentar solicitudes comenzará ... .
    # Finalizará ... el 15 de julio de 2025». Se exige la frase de solicitud
    # para no confundir el fin de ejecución del proyecto con el de la call.
    split_close = re.search(
        rf"(?:plazo\s+para\s+presentar\s+solicitudes|presentacion\s+de\s+solicitudes)"
        rf"[\s\S]{{0,650}}?finalizara[\s\S]{{0,160}}?({textual_date})",
        folded,
        re.IGNORECASE,
    )
    if split_close:
        close_date, _ = _parse_cdti_calendar_date(
            split_close.group(1), datetime.now().year, month_end=True,
        )
        return "", close_date

    close_match = re.search(
        rf"(?:plazo|solicitudes?|presentacion)[^.\n]{{0,350}}?"
        rf"(?:hasta|finaliza|fin)[^.\n]{{0,100}}?({textual_date})",
        folded,
        re.IGNORECASE,
    )
    if close_match:
        close_date, _ = _parse_cdti_calendar_date(
            close_match.group(1),
            datetime.now().year,
            month_end=True,
        )
        return "", close_date
    return "", ""


def _extract_application_dates(text: str) -> tuple[str, str]:
    """Extrae únicamente fechas ligadas explícitamente al plazo de solicitud."""
    textual_open, textual_close = _extract_spanish_application_dates(text)
    if textual_close:
        return textual_open, textual_close

    folded = _fold_text(text)
    date_pattern = r"(\d{1,2}[./-]\d{1,2}[./-]\d{4})"
    labelled_close = re.search(
        r"fecha[_\s-]+fin[_\s-]+solicitud[^\d]{0,30}" + date_pattern,
        folded,
        re.IGNORECASE,
    )
    if labelled_close:
        return "", _date_to_iso(labelled_close.group(1))
    scoped_range = re.search(
        r"(?:plazo|solicitudes?|presentacion)"
        r"[^.\n]{0,350}?" + date_pattern
        + r"[^.\n]{0,220}?(?:al|a|hasta|-)\s*" + date_pattern,
        folded,
        re.IGNORECASE,
    )
    if scoped_range:
        return (
            _date_to_iso(scoped_range.group(1)),
            _date_to_iso(scoped_range.group(2)),
        )

    scoped_close = re.search(
        r"(?:plazo|solicitudes?|presentacion)"
        r"[^.\n]{0,350}?(?:hasta|finaliza(?:cion)?|cierre|fin)"
        r"[^.\n]{0,100}?" + date_pattern,
        folded,
        re.IGNORECASE,
    )
    if scoped_close:
        return "", _date_to_iso(scoped_close.group(1))

    catalan_close = re.search(
        r"termini\s+de\s+presentacio[^\n]{0,350}?" + date_pattern,
        folded,
        re.IGNORECASE,
    )
    if catalan_close:
        return "", _date_to_iso(catalan_close.group(1))

    open_match = re.search(
        r"\b(?:fecha\s+de\s+)?(?:inicio|apertura)\b"
        r"[^.\n]{0,240}?" + date_pattern,
        folded,
        re.IGNORECASE,
    )
    close_match = re.search(
        r"\b(?:fecha\s+de\s+)?(?:finaliza(?:cion)?|cierre|fin)\b"
        r"[^.\n]{0,240}?" + date_pattern,
        folded,
        re.IGNORECASE,
    )
    if open_match and not re.search(
        r"\b(solicitud|plazo)\b", open_match.group(0), re.IGNORECASE
    ):
        open_match = None
    if close_match and not re.search(
        r"\b(solicitud|plazo)\b", close_match.group(0), re.IGNORECASE
    ):
        close_match = None
    return (
        _date_to_iso(open_match.group(1)) if open_match else "",
        _date_to_iso(close_match.group(1)) if close_match else "",
    )


def _absolute_url(base: str, href: str) -> str:
    """Convierte un enlace relativo ("/ayudas/foo") en una URL completa."""
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("/"):
        return base.rstrip("/") + href
    return base.rstrip("/") + "/" + href


def _levenshtein(a: str, b: str) -> int:
    """Distancia de Levenshtein clásica, sin dependencias externas."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            ins_cost = current[j - 1] + 1
            del_cost = previous[j] + 1
            sub_cost = previous[j - 1] + (ca != cb)
            current.append(min(ins_cost, del_cost, sub_cost))
        previous = current
    return previous[-1]
