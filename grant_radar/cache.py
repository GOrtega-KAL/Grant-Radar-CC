# cache.py — caché de análisis de Claude (grant_radar_cache.json)
#
# Guarda y recupera los análisis ya hechos por Claude para no repetir una
# llamada cuando el contenido de una convocatoria y las versiones vigentes
# (perfil, extractor, evaluador, prompt...) no han cambiado. No confundir con
# las cachés documentales (BDNS, fuentes web), que son un concepto distinto y
# siguen en Grant-Radar-prueba.py.
#
# Se extrajo junto con grant_radar/deterministic_rules.py porque
# `filter_usable_cache()` llama a `apply_current_deterministic_rules()` de
# ese módulo cada vez que se carga la caché, para reaplicar las salvaguardas
# vigentes sin gastar una nueva llamada a Claude (ver AGENTS.md, sección 5).
# Es la única dependencia cruzada entre ambos módulos.
#
# `cache_file` se pasa como parámetro en vez de leerse de una constante
# propia: la ruta depende de dónde vive `Grant-Radar-prueba.py`
# (`os.path.dirname(os.path.abspath(__file__))`), y ese cálculo debe seguir
# haciéndose una sola vez, en el script principal, para no arriesgar que la
# caché se lea o escriba en un sitio distinto al de siempre.

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from grant_radar.deterministic_rules import apply_current_deterministic_rules
from grant_radar.versions import (
    ANALYSIS_PROMPT_VERSION,
    CACHE_SCHEMA_VERSION,
    CLAUDE_MODEL,
    EVALUATOR_VERSION,
    EXTRACTOR_VERSION,
    PARTNER_CATALOG_VERSION,
    PROFILE_VERSION,
)

log = logging.getLogger("grant_radar")


def _stable_factual_hash_text(value: str, document_role: str = "") -> str:
    """Elimina solo relojes de sede que no cambian los hechos de la ayuda."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if document_role == "application_landing":
        months = (
            "enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
            "septiembre|setiembre|octubre|noviembre|diciembre"
        )
        text = re.sub(
            rf"\b\d{{1,2}}\s+de\s+(?:{months})\s+(?:de\s+)?20\d{{2}},?"
            r"\s+\d{1,2}:\d{2}:\d{2}\b",
            "<official-clock>", text, flags=re.IGNORECASE,
        )
    return text


def source_hash(conv: dict) -> str:
    """Huella del contenido factual enviado al extractor."""
    source_document = {
        "source": re.sub(r"\s+", " ", str(conv.get("source", "")).strip().lower()),
        "title": re.sub(r"\s+", " ", str(conv.get("title", "")).strip().lower()),
        "url": str(conv.get("url", "")).strip(),
        "description": re.sub(r"\s+", " ", str(conv.get("description", "")).strip()),
        "deadline_date": str(conv.get("deadline_date", "")),
        "open_date": str(conv.get("open_date", "")),
        "budget": str(conv.get("budget", "")),
        "bdns_id": str(conv.get("bdns_id", "")),
        "related_documents": [
            {
                "title": document.get("title", ""),
                "url": document.get("url", ""),
                "document_role": document.get("document_role", ""),
                "description": _stable_factual_hash_text(
                    document.get("description", ""),
                    str(document.get("document_role", "")),
                ),
            }
            for document in conv.get("related_document_contents", [])
        ],
    }
    # Huella de las condiciones generales del programa, cuando la convocatoria
    # las lleva (hoy, Horizon). Va aparte y solo si existen, para no cambiar la
    # huella de las fuentes que no las tienen: añadir una clave vacía
    # invalidaría de golpe toda la caché por un dato que no usan.
    #
    # Con esto, el texto del anexo se comporta como el resto de la evidencia:
    # mientras no cambie, un análisis ya pagado se reutiliza; cuando la Comisión
    # publique otra edición o una corrección, las convocatorias de ese programa
    # se vuelven a analizar solas y nadie tiene que acordarse de subir una
    # versión a mano (AGENTS.md 51.1).
    programme = conv.get("programme_eligibility")
    if isinstance(programme, dict) and programme.get("fingerprint"):
        source_document["programme_conditions"] = programme["fingerprint"]
    raw = json.dumps(
        source_document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_key(conv: dict) -> str:
    """Genera una clave estable sensible al contenido y a todas las versiones."""
    identity = {
        "analysis_version": ANALYSIS_PROMPT_VERSION,
        "profile_version": PROFILE_VERSION,
        "partner_catalog_version": PARTNER_CATALOG_VERSION,
        "source_hash": source_hash(conv),
    }
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_save(cache: dict, cache_file: str) -> None:
    """Guarda la caché con metadatos de esquema y versión del prompt."""
    payload = {
        "_meta": {
            "schema_version": CACHE_SCHEMA_VERSION,
            "prompt_version": ANALYSIS_PROMPT_VERSION,
            "profile_version": PROFILE_VERSION,
            "extractor_version": EXTRACTOR_VERSION,
            "evaluator_version": EVALUATOR_VERSION,
            "partner_catalog_version": PARTNER_CATALOG_VERSION,
            "model_version": CLAUDE_MODEL,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        },
        "entries": cache,
    }
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"No se pudo guardar caché: {e}")


def analysis_is_usable(analysis: dict) -> bool:
    """Impide reutilizar como válidos fallos o respuestas incompletas de Claude."""
    if not isinstance(analysis, dict):
        return False
    if analysis.get("resumen") in {
        "Análisis no disponible temporalmente.",
        "Pendiente de análisis.",
    }:
        return False
    return (
        isinstance(analysis.get("fit_score"), (int, float))
        and isinstance(analysis.get("actionability_score"), (int, float))
        and isinstance(analysis.get("confidence"), (int, float))
        and analysis.get("priority") in {"high", "medium", "low"}
        and isinstance(analysis.get("resumen"), str)
        and bool(analysis.get("resumen", "").strip())
        and isinstance(analysis.get("accion"), str)
        and isinstance(analysis.get("dimensiones"), list)
        and isinstance(analysis.get("call_facts"), dict)
    )


def filter_usable_cache(entries: dict) -> dict:
    """Devuelve solo entradas con un análisis utilizable, sin alterar el archivo."""
    usable = {}
    for key, record in entries.items():
        if (
            isinstance(record, dict)
            and analysis_is_usable(record.get("analysis"))
        ):
            apply_current_deterministic_rules(record)
            usable[key] = record
    ignored = len(entries) - len(usable)
    if ignored:
        log.warning(
            f"Caché: ignorando {ignored} análisis incompatibles con el esquema "
            "actual o incompletos; se volverán a solicitar a Claude"
        )
    return usable


def _reindex_cache_entries(entries: dict) -> dict:
    """Recalcula claves en memoria tras normalizaciones semánticamente neutras."""
    reindexed = {}
    changed = 0
    for old_key, record in entries.items():
        if not isinstance(record, dict):
            continue
        conv = record.get("raw_document") or record.get("conv")
        new_key = cache_key(conv) if isinstance(conv, dict) else str(old_key)
        candidate = dict(record)
        if isinstance(conv, dict):
            candidate["source_hash"] = source_hash(conv)
        previous = reindexed.get(new_key)
        if previous is None or str(candidate.get("cached_at", "")) >= str(
            previous.get("cached_at", "")
        ):
            reindexed[new_key] = candidate
        changed += new_key != old_key
    if changed:
        log.info(
            f"Caché reindexada en memoria: {changed} claves normalizadas; "
            "el archivo no se modifica durante la carga"
        )
    return reindexed


def cache_load(cache_file: str) -> dict:
    """
    Carga la caché. El formato plano antiguo se migra una sola vez a claves
    SHA-256; después, cambiar ANALYSIS_PROMPT_VERSION invalida los análisis.
    """
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}

    if isinstance(payload, dict) and isinstance(payload.get("entries"), dict):
        meta = payload.get("_meta", {})
        expected_versions = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "prompt_version": ANALYSIS_PROMPT_VERSION,
            "profile_version": PROFILE_VERSION,
            "extractor_version": EXTRACTOR_VERSION,
            "evaluator_version": EVALUATOR_VERSION,
            "partner_catalog_version": PARTNER_CATALOG_VERSION,
            "model_version": CLAUDE_MODEL,
        }
        mismatches = {
            key: {"cached": meta.get(key), "expected": expected}
            for key, expected in expected_versions.items()
            if meta.get(key) != expected
        }
        if mismatches:
            log.warning(
                "Caché invalidada por cambio de versión: "
                + ", ".join(sorted(mismatches))
            )
            return {}
        return filter_usable_cache(_reindex_cache_entries(payload["entries"]))

    if not isinstance(payload, dict):
        return {}

    migrated = {}
    for old_key, record in payload.items():
        if not isinstance(record, dict):
            continue
        conv = record.get("conv")
        new_key = cache_key(conv) if isinstance(conv, dict) else str(old_key)
        migrated[new_key] = record

    if migrated:
        cache_save(migrated, cache_file)
        log.info(f"Caché antigua migrada a SHA-256: {len(migrated)} análisis conservados")
    return filter_usable_cache(migrated)
