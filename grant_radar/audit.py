# audit.py — auditoría de la recopilación: qué se descartó y qué quedó guardado
#
# Dos mitades. La primera es memoria de la ejecución en curso: DISCOVERY_AUDIT
# es una lista mutable compartida por todo el pipeline y cada fuente registra
# en ella, vía audit_exclusion(), por qué se descartó una convocatoria
# candidata. El script principal importa este módulo y usa el mismo objeto
# lista (no una copia), así que `.clear()` y las lecturas desde cualquier
# módulo ven las mismas entradas.
#
# La segunda la persiste: save_discovery_audit() añade la ejecución al
# histórico de grant_radar_audit.json y load_audit_runs() lo lee. Ese archivo
# es hoy la única memoria entre ejecuciones que tiene el proyecto —de él salen
# compare_funnels() (source_health.py) y el informe de desfase
# (staleness.py)—, así que su formato importa más de lo que su tamaño sugiere.
#
# No depende de caché, reglas ni Claude.

import hashlib
import json
import logging
import os
from collections import Counter
from datetime import datetime, timezone

from grant_radar.runtime_state import COVERAGE_WATCH_RESULTS, RUN_DIAGNOSTICS

log = logging.getLogger("grant_radar")

DISCOVERY_AUDIT: list[dict] = []


def audit_exclusion(
    item: dict,
    reason: str,
    stage: str,
    details: dict | None = None,
) -> None:
    """Registra un descubrimiento excluido sin guardar descripciones extensas."""
    source = str(item.get("source", "") or "DESCONOCIDA")
    identifier = str(
        item.get("identifier")
        or item.get("bdns_id")
        or item.get("catalog_ref")
        or ""
    ).strip()
    title = " ".join(str(item.get("title", "")).split())[:500]
    url = str(item.get("url", "") or item.get("official_url", "")).strip()
    record = {
        "source": source,
        "identifier": identifier,
        "title": title,
        "url": url,
        "reason": reason,
        "stage": stage,
        "deadline_date": str(item.get("deadline_date", "")),
        "open_date": str(item.get("open_date", "")),
        "bdns_id": str(item.get("bdns_id", "")),
    }
    if details:
        record["details"] = details

    key = (
        source.casefold(),
        identifier.casefold(),
        url.casefold(),
        title.casefold(),
        reason,
        stage,
    )
    if not any(entry.get("_key") == key for entry in DISCOVERY_AUDIT):
        record["_key"] = key
        DISCOVERY_AUDIT.append(record)


# ── HISTÓRICO EN DISCO ───────────────────────────────────────────────────────
# Lo anterior (DISCOVERY_AUDIT y audit_exclusion) es memoria de la ejecución en
# curso; lo que sigue la persiste. `audit_file` se pasa como parámetro, igual
# que `cache_file` en grant_radar/cache.py: la ruta se calcula una sola vez en
# Grant-Radar-prueba.py, a partir de dónde vive el script, y no debe
# recalcularse aquí bajo ningún concepto.

AUDIT_SCHEMA_VERSION = 2
# 365 ejecuciones: suficiente para que compare_funnels() y el informe de
# desfase tengan historia con la que comparar sin que el archivo crezca sin fin.
AUDIT_MAX_RUNS = 365


def save_discovery_audit(
    run_started_at: str,
    status: str,
    source_counts: dict | None = None,
    claude_usage: dict | None = None,
    *,
    audit_file: str,
) -> None:
    """
    Añade una ejecución al histórico local sin duplicar exclusiones completas.

    El esquema v2 mantiene un catálogo normalizado de exclusiones y cada
    ejecución almacena solo sus identificadores. Al leer el esquema v1 lo migra
    en memoria; el archivo se compacta en el siguiente guardado real.
    """

    def record_id(record: dict) -> str:
        raw = json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def empty_history() -> dict:
        return {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "description": (
                "Histórico local normalizado de oportunidades descubiertas "
                "pero excluidas antes o después del análisis."
            ),
            "exclusions": {},
            "runs": [],
        }

    def migrate_history(loaded: dict) -> dict:
        if not isinstance(loaded, dict) or not isinstance(loaded.get("runs"), list):
            return empty_history()
        if loaded.get("schema_version") == AUDIT_SCHEMA_VERSION:
            if not isinstance(loaded.get("exclusions"), dict):
                return empty_history()
            return loaded
        if loaded.get("schema_version") != 1:
            return empty_history()

        migrated = empty_history()
        for old_run in loaded["runs"]:
            if not isinstance(old_run, dict):
                continue
            new_run = {
                key: value
                for key, value in old_run.items()
                if key != "excluded"
            }
            excluded_ids = []
            for record in old_run.get("excluded", []):
                if not isinstance(record, dict):
                    continue
                identifier = record_id(record)
                migrated["exclusions"][identifier] = record
                excluded_ids.append(identifier)
            new_run["excluded_ids"] = excluded_ids
            migrated["runs"].append(new_run)
        return migrated

    clean_entries = []
    for entry in DISCOVERY_AUDIT:
        clean = dict(entry)
        clean.pop("_key", None)
        clean_entries.append(clean)

    reason_counts = Counter(entry["reason"] for entry in clean_entries)
    run_record = {
        "started_at": run_started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "excluded_count": len(clean_entries),
        "reason_counts": dict(sorted(reason_counts.items())),
        "source_counts": source_counts or {},
        "coverage_watch": list(COVERAGE_WATCH_RESULTS),
        "diagnostics": dict(RUN_DIAGNOSTICS),
        "excluded_ids": [],
    }
    if claude_usage:
        run_record["claude_usage"] = claude_usage

    history = empty_history()
    if os.path.exists(audit_file):
        try:
            with open(audit_file, "r", encoding="utf-8") as audit_handle:
                loaded = json.load(audit_handle)
            history = migrate_history(loaded)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning(f"No se pudo leer la auditoría anterior; se recreará: {exc}")

    for record in clean_entries:
        identifier = record_id(record)
        history["exclusions"][identifier] = record
        run_record["excluded_ids"].append(identifier)

    history["runs"].append(run_record)
    history["runs"] = history["runs"][-AUDIT_MAX_RUNS:]
    referenced_ids = {
        identifier
        for run in history["runs"]
        for identifier in run.get("excluded_ids", [])
    }
    history["exclusions"] = {
        identifier: record
        for identifier, record in history["exclusions"].items()
        if identifier in referenced_ids
    }
    with open(audit_file, "w", encoding="utf-8") as audit_handle:
        json.dump(history, audit_handle, ensure_ascii=False, indent=2)
    log.info(
        f"Auditoría guardada: {len(clean_entries)} exclusiones del run; "
        f"{len(history['exclusions'])} registros únicos en {audit_file}"
    )


def load_audit_runs(audit_file: str) -> list:
    """Lee solo las ejecuciones del histórico, tolerando cualquier problema.

    La usan el informe de desfase (`--staleness-report`) y el resumen que cierra
    cada recopilación. Nunca debe interrumpir una ejecución: si el archivo no
    existe, está a medio escribir o tiene otra forma, devuelve una lista vacía.
    """
    try:
        with open(audit_file, "r", encoding="utf-8") as handle:
            history = json.load(handle)
        runs = history.get("runs")
        return runs if isinstance(runs, list) else []
    except Exception as exc:
        log.debug(f"No se pudo leer el histórico de auditoría: {exc}")
        return []
