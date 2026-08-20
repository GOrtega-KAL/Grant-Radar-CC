# claude_selection.py — qué se manda a Claude y la barrera de coste
#
# Entre el filtro determinista y la primera llamada a Haiku hay tres
# decisiones, y las tres viven aquí:
#
# - `select_claude_candidates()` y `build_claude_analysis_selection()`: qué
#   convocatorias necesitan análisis nuevo, distinguiendo las que ya están en
#   caché con el mismo hash factual de las nuevas o modificadas.
# - `claude_safety_preflight()`: la barrera previa. Detiene la ejecución si se
#   han seleccionado más análisis de la cuenta o si el extremo superior
#   estimado supera el límite en dólares. Es una barrera presupuestaria basada
#   en la calibración observada, no una garantía sobre la factura real.
# - `build_no_claude_candidate_inventory()`: el inventario compacto que
#   `--no-claude` guarda en la auditoría, para poder explicar después qué
#   habría costado la ejecución y por qué.

import logging
import re
from collections import Counter

from grant_radar.cache import cache_key, source_hash
from grant_radar.parsing_helpers import _fold_text

log = logging.getLogger("grant_radar")

# Límites autorizados el 11/08/2026 (ver AGENTS.md sección 11).
CLAUDE_MAX_ANALYSES_PER_RUN = 200
CLAUDE_MAX_ESTIMATED_COST_USD = 5.0

# Calibración del 20/08/2026 sobre una ejecución completa de 76 análisis, la
# primera con la evidencia enriquecida del extractor v7. La anterior salía de
# una muestra de dos convocatorias: acertaba en la media pero subestimaba la
# cola, que es justo lo que debe cubrir una barrera de seguridad.
#
# El valor de la barrera es el percentil 95 observado (0,0464), redondeado
# hacia arriba. Con él, el límite de 5 USD permite 106 análisis por ejecución
# en vez de los 142 que autorizaba el 0,035 anterior: menos margen nominal,
# pero un margen que ahora refleja el coste real de las convocatorias caras.
CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS = 0.047
CLAUDE_OBSERVED_MEAN_USD_PER_ANALYSIS = 0.0256
CLAUDE_OBSERVED_P05_USD_PER_ANALYSIS = 0.0155


def _candidate_cache_identity_tokens(conv: dict) -> set[str]:
    """Identidades exactas para distinguir novedad de cambio factual."""
    tokens = set()
    for field in ("identifier", "bdns_id", "programme_key", "catalog_ref"):
        value = _fold_text(str(conv.get(field, ""))).strip()
        if value:
            tokens.add(f"{field}:{value}")
    url = re.sub(r"[?#].*$", "", str(conv.get("url", "")).strip()).rstrip("/").casefold()
    if url:
        tokens.add(f"url:{url}")
    source = _fold_text(str(conv.get("source", ""))).strip()
    title = _fold_text(str(conv.get("title", ""))).strip()
    if source and title:
        tokens.add(f"source_title:{source}|{title}")
    return tokens


def select_claude_candidates(
    candidates: list[dict],
    match_values: list[str] | None,
) -> list[dict]:
    """Filtra de forma determinista el modo limitado sin llamar a Claude."""
    normalized_matches = [
        _fold_text(value) for value in (match_values or []) if value.strip()
    ]
    if not normalized_matches:
        return list(candidates)
    return [
        conv for conv in candidates
        if any(
            match in _fold_text(" ".join(str(value) for value in (
                conv.get("identifier", ""),
                conv.get("title", ""),
                conv.get("url", ""),
                conv.get("description", ""),
            )))
            for match in normalized_matches
        )
    ]


def build_claude_analysis_selection(
    all_items: list[dict],
    cache: dict,
    match_values: list[str] | None,
    force_reanalysis: bool = False,
) -> dict:
    """Planifica análisis nuevos o reanálisis selectivos sin alterar la caché."""
    new_items = [item for item in all_items if cache_key(item) not in cache]
    cached_items = [item for item in all_items if cache_key(item) in cache]
    pool = all_items if force_reanalysis else new_items
    candidates = select_claude_candidates(pool, match_values)
    forced_cached = [
        item for item in candidates if cache_key(item) in cache
    ] if force_reanalysis else []
    return {
        "new_items": new_items,
        "cached_items": cached_items,
        "pool": pool,
        "candidates": candidates,
        "forced_cached": forced_cached,
    }


def claude_safety_preflight(planned_analyses: int) -> dict:
    """Impide iniciar Claude cuando el volumen o el coste superior exceden límites."""
    planned = max(0, int(planned_analyses))
    estimated_upper = round(
        planned * CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS, 4
    )
    breaches = []
    if planned > CLAUDE_MAX_ANALYSES_PER_RUN:
        breaches.append("candidate_limit")
    if estimated_upper > CLAUDE_MAX_ESTIMATED_COST_USD:
        breaches.append("estimated_cost_limit")
    return {
        "allowed": not breaches,
        "planned_analyses": planned,
        "max_analyses": CLAUDE_MAX_ANALYSES_PER_RUN,
        "estimated_upper_cost_usd": estimated_upper,
        "max_estimated_cost_usd": CLAUDE_MAX_ESTIMATED_COST_USD,
        "upper_cost_per_analysis_usd": (
            CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS
        ),
        "effective_max_analyses": min(
            CLAUDE_MAX_ANALYSES_PER_RUN,
            int(
                CLAUDE_MAX_ESTIMATED_COST_USD
                / CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS
            ),
        ),
        "breaches": breaches,
    }


def build_no_claude_candidate_inventory(all_items: list[dict], cache: dict) -> dict:
    """Construye el inventario compacto y reproducible del run sin Claude."""
    cached_identity_index = set()
    for record in cache.values():
        cached_conv = (
            (record.get("raw_document") or record.get("conv", {}))
            if isinstance(record, dict) else {}
        )
        if isinstance(cached_conv, dict):
            cached_identity_index.update(_candidate_cache_identity_tokens(cached_conv))

    items = []
    cache_counts = Counter()
    inclusion_counts = Counter()
    for conv in all_items:
        current_cache_key = cache_key(conv)
        identity_tokens = _candidate_cache_identity_tokens(conv)
        if current_cache_key in cache:
            cache_status = "hit"
        elif identity_tokens.intersection(cached_identity_index):
            cache_status = "content_changed"
        else:
            cache_status = "new"
        cache_counts[cache_status] += 1

        prefilter = conv.get("deterministic_prefilter", {})
        if not isinstance(prefilter, dict):
            prefilter = {}
        hold_resolution = conv.get("bdns_hold_resolution", {})
        if not isinstance(hold_resolution, dict):
            hold_resolution = {}
        reason_code = str(prefilter.get("reason_code", "generic_prefilter"))
        inclusion_counts[reason_code] += 1
        items.append({
            "identifier": str(conv.get("identifier", "")),
            "bdns_id": str(conv.get("bdns_id", "")),
            "programme_key": str(conv.get("programme_key", "")),
            "title": " ".join(str(conv.get("title", "")).split())[:500],
            "source": str(conv.get("source", "")),
            "discovery_sources": list(conv.get("discovery_sources", [])),
            "url": str(conv.get("url", "")),
            "deadline_date": str(conv.get("deadline_date", "")),
            "deadline_unconfirmed": bool(conv.get("fecha_sin_confirmar", False)),
            "funding_mechanism": str(conv.get("funding_mechanism", "unknown")),
            "opportunity_role": str(conv.get("opportunity_role", "unknown")),
            "opportunity_labels": list(conv.get("opportunity_labels", [])),
            "inclusion": {
                "decision": str(prefilter.get("decision", "ambiguous")),
                "reason_code": reason_code,
                "reason": " ".join(str(prefilter.get("reason", "")).split())[:500],
                "score": prefilter.get("score", 0),
                "signals": prefilter.get("signals", {}),
                "initial_hold_reason": str(conv.get("bdns_initial_hold_reason", "")),
                "hold_resolution": dict(hold_resolution),
            },
            "bdns_scope": {
                "admin_type": str(conv.get("bdns_admin_type", "")),
                "regions": list(conv.get("bdns_regions", [])),
                "beneficiary_types": list(conv.get("bdns_beneficiary_types", [])),
                "nace_sections": list(conv.get("bdns_nace_sections", [])),
                "finality": str(conv.get("bdns_finality", "")),
                "territorial_requirement": str(
                    conv.get("bdns_territorial_requirement", "")
                ),
            } if conv.get("bdns_filter_ready") else {},
            "cache": {
                "status": cache_status,
                "cache_key": current_cache_key,
                "source_hash": source_hash(conv),
            },
        })

    items.sort(key=lambda item: (
        item["source"].casefold(), item["title"].casefold(), item["identifier"]
    ))
    return {
        "schema_version": 1,
        "count": len(items),
        "cache_status_counts": dict(cache_counts),
        "inclusion_reason_counts": dict(inclusion_counts),
        "items": items,
    }
