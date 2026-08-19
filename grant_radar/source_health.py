# source_health.py — control común de salud de los inventarios web
#
# Las fuentes que dependen de scraping (CDTI, IDAE, BOE/MITECO, ECCP) llaman a
# `assess_web_inventory_health()` en cada recopilación para declarar si su
# inventario sigue siendo utilizable: acceso, estructura esperada, volumen
# mínimo, carga de fichas, cobertura de fechas y antigüedad declarada del
# calendario o catálogo.
#
# No decide la relevancia de ninguna convocatoria: detecta degradación de la
# fuente. El resultado se guarda en RUN_DIAGNOSTICS["web_source_health"] y, si
# no es "healthy", se avisa por consola en el momento; `run_pipeline()` añade
# además un resumen consolidado al final de la recopilación.

import logging
from datetime import datetime, timezone

from grant_radar.runtime_state import RUN_DIAGNOSTICS

log = logging.getLogger("grant_radar")


def assess_web_inventory_health(
    source: str,
    *,
    inventory_loaded: bool,
    structure_ok: bool,
    discovered_count: int,
    detail_attempted: int = 0,
    detail_loaded: int = 0,
    dated_count: int = 0,
    expected_min_inventory: int = 1,
    expected_date_coverage: float = 0.0,
    source_version: str = "",
    max_version_age_days: int | None = None,
) -> dict:
    """Evalúa de forma común si un inventario web sigue siendo utilizable.

    El control se ejecuta en cada recopilación de la fuente. No decide la
    relevancia de las convocatorias: detecta caídas de acceso, roturas del HTML,
    descensos anómalos de cobertura, fallos de fichas y calendarios obsoletos.
    """
    issues = []
    critical = []
    discovered_count = max(int(discovered_count or 0), 0)
    detail_attempted = max(int(detail_attempted or 0), 0)
    detail_loaded = max(int(detail_loaded or 0), 0)
    dated_count = max(int(dated_count or 0), 0)
    detail_load_rate = (
        detail_loaded / detail_attempted if detail_attempted else None
    )
    date_coverage = dated_count / discovered_count if discovered_count else 0.0

    if not inventory_loaded:
        critical.append("inventory_unreachable")
    elif not structure_ok:
        critical.append("expected_structure_missing")
    if discovered_count < expected_min_inventory:
        critical.append("inventory_below_expected_minimum")
    if detail_load_rate is not None:
        if detail_load_rate < 0.5:
            critical.append("detail_load_rate_below_50pct")
        elif detail_load_rate < 0.9:
            issues.append("detail_load_rate_below_90pct")
    if expected_date_coverage and discovered_count:
        if date_coverage < expected_date_coverage * 0.5:
            critical.append("date_coverage_critically_low")
        elif date_coverage < expected_date_coverage:
            issues.append("date_coverage_below_expected")

    version_age_days = None
    if max_version_age_days is not None:
        try:
            version_dt = datetime.strptime(source_version, "%Y-%m-%d").date()
            version_age_days = (datetime.now().date() - version_dt).days
            if version_age_days > max_version_age_days:
                issues.append("source_version_stale")
        except (TypeError, ValueError):
            issues.append("source_version_missing")

    status = "unhealthy" if critical else "degraded" if issues else "healthy"
    health = {
        "source": source,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "issues": [*critical, *issues],
        "inventory_loaded": bool(inventory_loaded),
        "structure_ok": bool(structure_ok),
        "discovered_count": discovered_count,
        "expected_min_inventory": expected_min_inventory,
        "detail_attempted": detail_attempted,
        "detail_loaded": detail_loaded,
        "detail_load_rate": (
            round(detail_load_rate, 4) if detail_load_rate is not None else None
        ),
        "dated_count": dated_count,
        "date_coverage": round(date_coverage, 4),
        "source_version": source_version,
        "version_age_days": version_age_days,
    }
    RUN_DIAGNOSTICS.setdefault("web_source_health", {})[source] = health
    if status != "healthy":
        log.warning(
            f"{source}: estado de salud {status} "
            f"({', '.join(health['issues']) or 'sin detalle'})"
        )
    return health
