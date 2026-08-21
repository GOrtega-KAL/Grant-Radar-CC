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
#
# Mide el embudo entero, no solo el acceso (AGENTS.md, sección 45). El 21/08/2026
# el IDAE convertía 97 fichas en 1 convocatoria y el BOE 168 en 2, y este control
# declaraba ambas fuentes "healthy": `date_coverage` se calculaba sobre el
# inventario completo —incluidas las fichas que nadie llega a abrir— así que daba
# cifras absurdas, y la única forma de que no chillara fue apagar el umbral. Un
# indicador que hay que apagar para que no moleste no es un indicador.
#
# Ahora cada tasa se mide sobre su propio denominador:
#
#   selection_rate   = detail_attempted / discovered_count   ¿cuánto se abre?
#   detail_load_rate = detail_loaded    / detail_attempted   ¿carga lo que se abre?
#   date_coverage    = dated_count      / detail_loaded      ¿tienen plazo?
#   publication_rate = published_count  / detail_loaded      ¿cuánto se publica?
#
# Cada conector declara el mínimo que espera de las que le importan. Los umbrales
# se calibran con holgura sobre medidas reales: buscan hundimientos, no ruido.

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

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
    published_count: int = 0,
    expected_min_inventory: int = 1,
    expected_date_coverage: float = 0.0,
    expected_selection_rate: float = 0.0,
    expected_publication_rate: float = 0.0,
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
    published_count = max(int(published_count or 0), 0)
    detail_load_rate = (
        detail_loaded / detail_attempted if detail_attempted else None
    )
    # Cada tasa, sobre su propio denominador. Una fecha solo puede encontrarse
    # en una ficha que se haya cargado; medirla contra el inventario completo
    # mezcla dos cosas distintas y obliga a apagar el umbral.
    selection_rate = (
        detail_attempted / discovered_count if discovered_count else None
    )
    date_coverage = dated_count / detail_loaded if detail_loaded else 0.0
    publication_rate = (
        published_count / detail_loaded if detail_loaded else None
    )

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
    if expected_date_coverage and detail_loaded:
        if date_coverage < expected_date_coverage * 0.5:
            critical.append("date_coverage_critically_low")
        elif date_coverage < expected_date_coverage:
            issues.append("date_coverage_below_expected")
    if expected_selection_rate and selection_rate is not None:
        if selection_rate < expected_selection_rate * 0.5:
            critical.append("selection_rate_critically_low")
        elif selection_rate < expected_selection_rate:
            issues.append("selection_rate_below_expected")
    if expected_publication_rate and publication_rate is not None:
        if publication_rate < expected_publication_rate * 0.5:
            critical.append("publication_rate_critically_low")
        elif publication_rate < expected_publication_rate:
            issues.append("publication_rate_below_expected")

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
        "selection_rate": (
            round(selection_rate, 4) if selection_rate is not None else None
        ),
        "dated_count": dated_count,
        "date_coverage": round(date_coverage, 4),
        "published_count": published_count,
        "publication_rate": (
            round(publication_rate, 4) if publication_rate is not None else None
        ),
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


# Etapas del embudo que se comparan entre ejecuciones, con el nombre que se le
# enseña al usuario. El orden es el del recorrido real.
FUNNEL_STAGES = (
    ("discovered_count", "inventario"),
    ("detail_attempted", "fichas abiertas"),
    ("detail_loaded", "fichas cargadas"),
    ("dated_count", "con plazo"),
    ("published_count", "publicadas"),
)

# Una etapa tiene que perder más de esto respecto a la ejecución anterior para
# que se avise. Las fuentes se mueven solas —convocatorias que cierran, listados
# que rotan—, así que un umbral bajo solo genera ruido.
FUNNEL_DROP_THRESHOLD = 0.4

# Por debajo de esto no se compara: pasar de 3 a 1 es un 66 % de caída y no
# significa nada.
FUNNEL_MIN_PREVIOUS = 8


def compare_funnels(
    previous: dict,
    current: dict,
    drop_threshold: float = FUNNEL_DROP_THRESHOLD,
) -> list[dict]:
    """
    Compara el embudo de cada fuente con el de la ejecución anterior.

    Existe porque ningún umbral absoluto habría detectado el caso del IDAE
    (AGENTS.md, sección 45): convertir 71 fichas en 1 convocatoria era a la vez
    el síntoma del fallo y su estado normal, así que solo el **cambio** lo
    delata. La auditoría guarda hasta 365 ejecuciones, de modo que la
    comparación sale gratis.

    No decide nada ni excluye nada: devuelve una lista de caídas para avisar.
    """
    regresiones = []
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return regresiones
    for source, health in sorted(current.items()):
        anterior = previous.get(source)
        if not isinstance(anterior, dict) or not isinstance(health, dict):
            continue
        for campo, etiqueta in FUNNEL_STAGES:
            antes = anterior.get(campo)
            ahora = health.get(campo)
            if not isinstance(antes, int) or not isinstance(ahora, int):
                continue
            if antes < FUNNEL_MIN_PREVIOUS or ahora >= antes:
                continue
            caida = (antes - ahora) / antes
            if caida > drop_threshold:
                regresiones.append({
                    "source": source,
                    "stage": campo,
                    "label": etiqueta,
                    "previous": antes,
                    "current": ahora,
                    "drop": round(caida, 4),
                })
    return regresiones


def previous_source_health(audit_path: str | Path) -> dict:
    """
    Lee el `web_source_health` de la última ejecución guardada en la auditoría.

    Devuelve `{}` ante cualquier problema —archivo ausente, JSON roto, esquema
    inesperado—: esta comparación es un aviso, nunca un motivo para que falle
    una recopilación.
    """
    try:
        with open(audit_path, "r", encoding="utf-8") as handle:
            history = json.load(handle)
        runs = history.get("runs")
        if not isinstance(runs, list) or not runs:
            return {}
        salud = runs[-1].get("diagnostics", {}).get("web_source_health", {})
        return salud if isinstance(salud, dict) else {}
    except Exception as exc:
        log.debug(f"No se pudo leer la salud de la ejecución anterior: {exc}")
        return {}
