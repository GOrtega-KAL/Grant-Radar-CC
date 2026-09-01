# -*- coding: utf-8 -*-
# programme_annexes.py — las condiciones generales del programa, leídas del
# documento oficial que la propia convocatoria enlaza
#
# El problema que resuelve: un topic de Horizon Europe son 3.000 caracteres de
# «Expected Outcome» y «Scope» y **no dice quién puede solicitar**. Eso vive en
# los Anexos Generales del programa de trabajo, comunes a todos los topics de
# esa edición. Sin ellos, el evaluador declaraba la elegibilidad «desconocida»
# en 14 de las 17 convocatorias que quedaban sin confirmar, y hacía bien: el
# prompt le prohíbe completar huecos (AGENTS.md, secciones 49.3 y 49.7).
#
# **Por qué no es un catálogo escrito a mano.** La alternativa evidente era
# teclear las reglas del programa en un JSON. Este proyecto ya tiene dos
# catálogos así y los dos han caducado en silencio: seis URLs de CDTI en 404
# durante cuatro meses (sección 44.1) y un catálogo de BOA con «última revisión
# 2026-04-09» (punto 28 del backlog). Aquí no hace falta: **la respuesta de la
# API trae el enlace al anexo de la edición del propio topic**
# (`…/wp-call/2026-2027/wp-15-general-annexes_horizon-2026-2027_en.pdf`), así
# que cuando cambie el programa de trabajo, el enlace cambia con él y esto
# sigue leyendo el documento correcto sin tocar una línea.
#
# Qué se extrae y por qué solo eso: tres secciones con título propio que son
# las que deciden si Kalfrisa puede presentarse. El documento entero son
# 128.000 caracteres —unos 33.000 tokens por llamada— y pasarlo sería tirar el
# dinero; los tres extractos acotados son ~3.400 y contienen la regla operativa
# completa, incluida la lista de países y el mínimo de tres socios.
#
# Si algo falla —no hay enlace, el PDF no responde, el texto no trae las
# secciones— se devuelve vacío y el dato queda ausente. Nunca se supone: es la
# misma disciplina que el resto del pipeline.

import hashlib
import json
import logging
import os
import re
from datetime import date, datetime, timezone

log = logging.getLogger("grant_radar")

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANNEXES_CACHE_FILE = os.path.join(
    _PROJECT_DIR, "grant_radar_data", "programme_annexes_cache.json"
)
# Subir esta versión invalida lo guardado y obliga a releer el documento. Hay
# que hacerlo siempre que cambie QUÉ se extrae, no solo cuando cambie el
# documento: el 01/09/2026 se añadió la sección de tasas de financiación, y sin
# invalidar, las entradas escritas el 31/08 se habrían reutilizado durante los
# siete días de `ANNEXES_REFRESH_DAYS` sin la sección nueva (AGENTS.md 59).
ANNEXES_CACHE_VERSION = "programme-annexes-2026-09-v2-funding-rates"
# Cada cuántos días se vuelve a leer el documento. Un anexo publicado no cambia
# a diario, pero la Comisión publica correcciones dentro de una misma edición y
# descargarlo cuesta 0,7 s: una semana es suficiente margen sin ser terco.
ANNEXES_REFRESH_DAYS = 7

# El enlace aparece en el HTML de `topicConditions`, entre otros treinta.
_ANNEXES_URL_RE = re.compile(
    r'href="(https://[^"]*general-annexes[^"]*\.pdf)"', re.IGNORECASE
)

# Cabecera repetida en cada página del PDF: aparece en mitad de las frases al
# extraer el texto y no aporta nada.
_PAGE_HEADER_RE = re.compile(
    r"Horizon Europe\s*-\s*Work programme\s*\d{4}\s*-\s*\d{4}\s*"
    r"General Annexes\s*Part\s*\d+\s*-\s*Page\s*\d+\s*of\s*\d+",
    re.IGNORECASE,
)

# Secciones que deciden la elegibilidad, con el título literal que llevan en el
# documento y cuánto texto hace falta para que la regla quede entera. Los
# límites están medidos sobre la edición 2026-2027: el mínimo de consorcio
# necesita 1.200 caracteres porque la enumeración va después de una nota al pie.
ELIGIBILITY_SECTIONS = (
    ("entities_eligible_to_participate", "Entities eligible to participate", 700),
    ("entities_eligible_for_funding", "Entities eligible for funding", 1500),
    ("consortium_composition", "Consortium composition", 1200),
    # Cuánto de tu gasto cubre la ayuda. Es el dato que decide si una
    # convocatoria interesa: en un proyecto de 3 M€, la diferencia entre el
    # 100 % de una Research and Innovation Action y el 70 % de una Innovation
    # Action son 900.000 € que pone la empresa. Vive en la sección G del mismo
    # documento, y hasta el 01/09/2026 no se leía porque cae en la página 32,
    # más allá del corte de caracteres por defecto (AGENTS.md 59).
    # 1.900 caracteres: medidos, la lista completa de tasas ocupa 1.578 desde
    # el encabezado.
    ("funding_rates", "Form of grant, funding rate and maximum grant amount", 1900),
)

# Los Anexos Generales tienen 46 páginas y 124.411 caracteres (edición
# 2026-2027). El corte por defecto de la capa documental —48.000— basta para la
# elegibilidad, que va en las primeras páginas, pero deja fuera las tasas de
# financiación. Se pide explícitamente leer más lejos solo para este documento.
ANNEXES_MAX_CHARS = 130_000


def sections_fingerprint(sections: dict) -> str:
    """Huella del texto que se le envía al modelo.

    Es lo que hace que una convocatoria ya analizada no se vuelva a pagar
    mientras el anexo no cambie, y que sí se rehaga cuando cambie: entra en
    `source_hash()` como un campo más del documento fuente.
    """
    material = json.dumps(
        {clave: valor for clave, valor in sorted(sections.items())
         if clave not in ("source_url", "fingerprint")},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _days_since(read_on: str, today: date) -> int:
    """Días desde una lectura; un valor ilegible obliga a releer."""
    try:
        return (today - date.fromisoformat(str(read_on)[:10])).days
    except ValueError:
        return 10**6


def load_annexes_cache() -> dict:
    """Lo leído en ejecuciones anteriores, indexado por documento."""
    try:
        with open(ANNEXES_CACHE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    meta = payload.get("_meta", {}) if isinstance(payload, dict) else {}
    entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
    if meta.get("version") != ANNEXES_CACHE_VERSION or not isinstance(entries, dict):
        return {}
    return entries


def save_annexes_cache(entries: dict) -> None:
    """Guarda de forma atómica; un fallo aquí nunca detiene la recopilación."""
    if not entries:
        return
    payload = {
        "_meta": {
            "version": ANNEXES_CACHE_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "content": "programme_general_annexes_eligibility_sections",
        },
        "entries": entries,
    }
    try:
        temporary = ANNEXES_CACHE_FILE + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
        os.replace(temporary, ANNEXES_CACHE_FILE)
    except OSError as exc:
        log.warning(f"No se pudo guardar la caché de anexos: {exc}")


def annexes_url_from_conditions(conditions_html: str) -> str:
    """El enlace a los Anexos Generales dentro del bloque de condiciones."""
    match = _ANNEXES_URL_RE.search(str(conditions_html or ""))
    return match.group(1) if match else ""


def clean_annexes_text(text: str) -> str:
    """Quita la cabecera de página, que parte las frases al extraer el PDF."""
    return re.sub(r"\s+", " ", _PAGE_HEADER_RE.sub(" ", str(text or ""))).strip()


def eligibility_sections(annexes_text: str) -> dict:
    """Los extractos de las secciones que deciden quién puede presentarse.

    Devuelve solo las que encuentra: un documento que cambie de estructura dará
    menos secciones, no secciones inventadas.
    """
    clean = clean_annexes_text(annexes_text)
    if not clean:
        return {}
    found = {}
    for key, heading, limit in ELIGIBILITY_SECTIONS:
        match = re.search(re.escape(heading), clean, re.IGNORECASE)
        if not match:
            continue
        excerpt = clean[match.start():match.start() + limit].strip()
        if len(excerpt) > len(heading) + 40:
            found[key] = excerpt
    return found


def fetch_programme_eligibility(
    conditions_html: str,
    *,
    http_get,
    document_text,
    cache: dict | None = None,
    stored: dict | None = None,
    max_age_days: int = ANNEXES_REFRESH_DAYS,
    today: date | None = None,
) -> dict:
    """Condiciones generales del programa para un topic, o dict vacío.

    `http_get` y `document_text` se reciben para no atar este módulo ni al
    cliente HTTP ni al extractor documental: así se puede probar sin red y sin
    PDF.

    Dos memorias, con papeles distintos:

    - `cache` es por ejecución: una descarga por edición del programa,
      compartida por los treinta topics de Horizon de una recopilación.
    - `stored` persiste entre ejecuciones (`programme_annexes_cache.json`).
      Evita descargar el mismo documento a diario, pero sobre todo sirve de
      respaldo: si un día el portal no responde, se sigue publicando la
      elegibilidad conocida en vez de perderla y dejar treinta convocatorias
      «por confirmar». Se refresca cada `max_age_days`.

    Lo que decide si Haiku tiene que volver a analizar no es esta caché sino la
    huella `fingerprint`, que viaja con las secciones y entra en `source_hash()`
    (grant_radar/cache.py): mientras el texto del anexo no cambie, un análisis
    ya pagado se reutiliza; si cambia, se rehace. Ver AGENTS.md 51.1.
    """
    url = annexes_url_from_conditions(conditions_html)
    if not url:
        return {}
    if cache is not None and url in cache:
        return cache[url]

    today = today or date.today()
    previous = (stored or {}).get(url) if isinstance(stored, dict) else None
    if isinstance(previous, dict) and previous.get("sections"):
        if _days_since(previous.get("read_on", ""), today) < max_age_days:
            result = dict(previous["sections"])
            if cache is not None:
                cache[url] = result
            return result

    result = {}
    response = http_get(url, timeout=60)
    if response is None or getattr(response, "status_code", 0) != 200:
        if isinstance(previous, dict) and previous.get("sections"):
            log.warning(
                "Anexos Generales no disponibles (%s): se conservan los leídos "
                "el %s", url, previous.get("read_on", "?")
            )
            result = dict(previous["sections"])
        else:
            log.warning(
                "Anexos Generales no disponibles (%s): la elegibilidad del "
                "programa queda sin declarar", url
            )
    else:
        sections = eligibility_sections(
            document_text(response, url, max_chars=ANNEXES_MAX_CHARS)[0]
        )
        if sections:
            result = {
                "source_url": url,
                "fingerprint": sections_fingerprint(sections),
                **sections,
            }
            if isinstance(stored, dict):
                anterior = (previous or {}).get("sections", {}).get("fingerprint")
                stored[url] = {
                    "read_on": today.isoformat(),
                    "sections": result,
                }
                if anterior and anterior != result["fingerprint"]:
                    log.warning(
                        "Los Anexos Generales han cambiado (%s): las "
                        "convocatorias de ese programa se volverán a analizar",
                        url,
                    )
            log.info(
                f"  Condiciones generales del programa leídas de {url.rsplit('/', 1)[-1]} "
                f"({len(sections)} secciones)"
            )
        else:
            log.warning(
                "Los Anexos Generales no traen las secciones de elegibilidad "
                "esperadas (%s)", url
            )
    if cache is not None:
        cache[url] = result
    return result
