# ╔══════════════════════════════════════════════════════════════════╗
# ║  Grant-Radar — Backend Kalfrisa · Windows local                 ║
# ║  APIs oficiales + Chromium para fuentes web                    ║
# ╚══════════════════════════════════════════════════════════════════╝


# ─────────────────────────────────────────────────────────────────────
# CELDA 1 — INSTALACIÓN Y EJECUCIÓN EN WINDOWS LOCAL
# ─────────────────────────────────────────────────────────────────────
# Preparación inicial desde PowerShell:
# cd C:\Users\guillermo.ortega\Desktop\Guillermo\Grant-Radar - Claude Code
# poetry config virtualenvs.in-project true
# poetry add requests beautifulsoup4 anthropic pydantic playwright
# poetry run playwright install chromium
# poetry run python "Grant-Radar-prueba.py"
# poetry run python "Grant-Radar-prueba.py" --no-claude
# poetry run python "Grant-Radar-prueba.py" --max-claude 2
# poetry run python "Grant-Radar-prueba.py" --max-claude 2 --claude-match INNOVAE --claude-match HORIZON-CL5-2026-09-D4-08
# poetry run python "Grant-Radar-prueba.py" --max-claude 2 --force-reanalysis --claude-match INNOVAE --claude-match HORIZON-CL5-2026-09-D4-08
#
# --max-claude N analiza como máximo N convocatorias nuevas, guarda esos análisis
# en la caché y termina SIN generar convocatorias.json ni publicar en GitHub.
# Sirve para validar credenciales y calidad antes de una ejecución completa.
# --claude-match TEXTO limita ese modo a coincidencias de título, identificador,
# URL o descripción. Se puede repetir para seleccionar varias convocatorias.
# --force-reanalysis permite volver a analizar coincidencias ya presentes en
# caché. Por seguridad exige --max-claude y al menos un --claude-match.
#
# ESTIMACIÓN ORIENTATIVA DE TOKENS Y COSTE — Claude Haiku 4.5
# Tarifa consultada el 31/07/2026: 1 USD/MTok de entrada y 5 USD/MTok de salida.
# Fuente oficial: https://platform.claude.com/docs/en/about-claude/pricing
# El pipeline hace 2 llamadas por convocatoria nueva o cuyo contenido cambió:
# extracción factual compacta (incluye líneas) + evaluación. El esquema evita
# uniones anulables para mantenerse dentro de los límites de las salidas
# estructuradas. No usa la caché de prompts de Anthropic.
#
# Calibración real del 20/08/2026 sobre una ejecución completa (n=76), la
# primera con el extractor v7 y la evidencia enriquecida:
# 6.482-26.353 tokens de entrada (media 12.610) y 1.202-6.483 de salida
# (media 2.590) por convocatoria.
# Coste por convocatoria: mediana 0,0242 USD, media 0,0256 USD,
#   p95 0,0464 USD y máximo observado 0,0550 USD.
# Ejecución completa de 76 convocatorias: 1,83 USD reales.
# Sustituye a la calibración del 03/08/2026, que se hizo con una muestra de
# dos y daba 0,0265 central: acertó en la media pero subestimaba la cola, que
# es lo que importa para la barrera de seguridad.
# Siguen siendo estimaciones, no límites: documentos más largos elevan el coste
# y un cambio de perfil/prompt/versión puede invalidar toda la caché.


# ─────────────────────────────────────────────────────────────────────
# CELDA 2 — IMPORTS, CREDENCIALES Y CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────

import os
import sys
import argparse
import calendar
import io
import json
import time
import logging
import re
import unicodedata
import statistics
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from collections import Counter, deque
from typing import Literal
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from pypdf import PdfReader
from pydantic import Field
from dotenv import load_dotenv  # Lee credenciales desde el archivo .env local (no versionado)

# Módulos extraídos de este script al paquete `grant_radar/` (división propuesta
# en SUGERENCIAS.MD 3.2; historial por rondas en AGENTS.md, secciones 21-48).
# Cada uno se puede leer y probar sin ejecutar el resto del pipeline. Lo que
# queda aquí, desde el 31/08/2026, son solo dos cosas y las dos por decisión:
# la matriz de reglas previa a Claude (sesión propia, AGENTS.md 4.1) y la
# orquestación de `run_pipeline()`, que va la última porque arrastra el resto.
from grant_radar.cache import cache_key, cache_load, cache_save, source_hash
from grant_radar.claude_schemas import (
    BdnsHoldFacts,
    CallEvaluation,
    CallFacts,
    ClaudeAnalysisError,
    EvaluationScores,
    FundingLineFacts,
    validate_structured_output_schema,
)
# Las quince salvaguardas deterministas posteriores al modelo ya no se importan
# aquí: se fueron con `_build_compatible_analysis()` a grant_radar/analysis.py
# el 31/08/2026, que es quien las llamaba. Su historia sigue siendo la mejor
# advertencia del proyecto: faltaban en este import desde que se extrajeron
# (AGENTS.md sección 23) y el NameError solo habría aparecido en una ejecución
# real con Claude, porque `--no-claude` no recorre esa ruta y el bloque de
# fusión de APP las inyectaba en estos mismos globals durante las pruebas. De
# ahí tests/test_grant_radar_script_names.py.
from grant_radar.deterministic_rules import BDNS_DIRECT_OWN_INVESTMENT_TERMS
from grant_radar.versions import (
    ANALYSIS_PROMPT_VERSION,
    CACHE_SCHEMA_VERSION,
    CLAUDE_MODEL,
    EVALUATOR_VERSION,
    EXTRACTOR_VERSION,
    PARTNER_CATALOG_VERSION,
    PROFILE_VERSION,
)
from grant_radar.profile_scope import (
    _explicit_profile_incompatibility,
    _hard_out_of_scope,
)
from grant_radar.holds import (
    BDNS_HOLD_PILOT_MAX,
    BDNS_HOLD_REPLAY_FILE,
    BDNS_HOLD_REPORT_FILE,
    replay_bdns_hold_report,
    resolve_bdns_holds_for_pipeline,
    run_bdns_hold_pilot,
)
from grant_radar.analysis import (
    CLAUDE_SLEEP_S,
    _hydrate_stable_cached_documents,
    # La resolución de holds con Haiku, que sigue aquí, comparte con la capa de
    # análisis la llamada estructurada y su contabilidad de tokens. Saldrá con
    # ella cuando se extraiga la segunda mitad del dominio de holds.
    analyze_with_claude,
    claude_key_format_is_valid,
)
from grant_radar.tech_taxonomy import (
    INDUSTRIAL_CONTEXT_TERMS,
    KEYWORDS,
    TECH_CONTEXT_TERMS,
    TECH_DISCOVERY_TERMS,
    TECH_TAG_COMPAT_ALIASES,
    TECH_TAG_CONTEXTUAL_TERMS,
    TECH_TAG_STRONG_TERMS,
    _contextual_term_present,
    _term_present,
    detect_tech_tags,
    has_technology_discovery_signal,
    is_relevant,
    keyword_match,
)
from grant_radar.parsing_helpers import (
    _SPANISH_MONTHS,
    _absolute_url,
    _date_to_iso,
    _es_titulo_valido,
    _extract_date_range,
    _extract_spanish_application_dates,
    _fold_text,
    _levenshtein,
    _parse_cdti_calendar_date,
    _signed_days_until,
)
from grant_radar.audit import (
    DISCOVERY_AUDIT,
    audit_exclusion,
    load_audit_runs,
    save_discovery_audit,
)
from grant_radar.runtime_state import (
    COVERAGE_WATCH_RESULTS,
    IDENTITY_LANDINGS,
    RUN_DIAGNOSTICS,
    SOURCE_RUNTIME_METADATA,
)
from grant_radar.http_client import (
    HTTP_USER_AGENT,
    _http_get,
    _is_safe_public_https_url,
)
from grant_radar.browser import PlaywrightBrowser
# La matriz de reglas previa a Claude. El script solo necesita estas dos: el
# resto de la matriz es interno, y `holds.py` y el conector ECCP las reciben
# inyectadas desde aquí como parámetros, no importadas (AGENTS.md 57).
from grant_radar.bdns_rules import (
    _bdns_intrinsic_exclusion,
    deterministic_prefilter,
)
from grant_radar.gap_report import (
    build_gap_report,
    cache_version_state,
    format_budget_watch,
    format_gap_report,
    gap_records_from_cache,
    gap_records_from_product,
)
from grant_radar.staleness import (
    build_collection_state,
    build_staleness_report,
    format_staleness_report,
    summarize_staleness,
)
from grant_radar.source_health import (
    assess_web_inventory_health,
    compare_funnels,
    previous_source_health,
)
from grant_radar.call_text import (
    CALL_LINK_TERMS,
    FUNDING_CONTEXT_TERMS,
    _extract_deadline_from_text,
    _extract_funding_budget,
    _external_links,
    _funding_mechanism,
    _official_call_identifier,
)
from grant_radar.documents import (
    BDNS_HOLD_MAX_DOCUMENT_BYTES,
    BDNS_HOLD_MAX_EVIDENCE_CHARS,
    SOURCE_DOCUMENT_CACHE_FILE,
    _hold_document_text,
    enrich_with_official_documents,
)
from grant_radar.product_watch import (
    compare_published_products,
    summarize_product_changes,
)
from grant_radar.publishing import github_upload
from grant_radar.claude_usage import (
    aggregate_aborted_run_usage,
    aggregate_partial_token_usage,
    aggregate_token_usage,
)
from grant_radar.claude_selection import (
    CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS,
    CLAUDE_OBSERVED_MEAN_USD_PER_ANALYSIS,
    CLAUDE_OBSERVED_P05_USD_PER_ANALYSIS,
    CLAUDE_MAX_ANALYSES_PER_RUN,
    CLAUDE_MAX_ESTIMATED_COST_USD,
    build_claude_analysis_selection,
    build_no_claude_candidate_inventory,
    claude_safety_preflight,
    select_claude_candidates,
)
from grant_radar.coverage_watch import (
    build_recurrent_coverage_watch,
    probe_missing_recurrent_coverage,
)
from grant_radar.public_output import (
    _assemble_public_record,
    build_keywords,
    build_source_status,
    build_stats,
    derive_eligible_actions,
    post_procesar_texto,
    verificar_urls,
)
from grant_radar.dedup import (
    _deduplicate_raw_convocations,
    _document_rank,
    _document_role,
    _programme_identity,
)
from grant_radar.bdns_fields import (
    BDNS_NAMED_ACCESS_TERMS,
    BDNS_NEW_ESTABLISHMENT_MIN_DAYS,
    BDNS_TECHNOLOGY_TERMS,
    _bdns_codes,
    _bdns_company_eligible,
    _bdns_descriptions,
    _nace_section,
)
from grant_radar.bdns_scope import (
    _bdns_is_aragon_regional_administration,
    _bdns_is_prefilter_candidate,
)
from grant_radar.sources.horizon_europe import fetch_horizon_europe
from grant_radar.sources.een import fetch_een_funding
from grant_radar.sources.eccp import fetch_eccp
from grant_radar.sources.bdns import (
    BDNS_API_BASE,
    BDNS_PUBLIC_BASE,
    # _bdns_relative_application_deadline la usa resolve_hold_deterministically()
    # al recalcular un plazo desde la cita recuperada de las bases oficiales.
    _bdns_detail_to_raw,
    fetch_bdns,
)
from grant_radar.sources.boe_miteco import fetch_boe
from grant_radar.sources.cdti import fetch_cdti
from grant_radar.sources.idae import fetch_idae, fetch_idae_catalog

# Alias cortos de `--source`. Los nombres internos llevan espacios y acentos
# ("BOE / MITECO", "IDAE CATÁLOGO"), que en línea de comandos obligan a comillas y
# se teclean mal; estos son los que se escriben. `idae` selecciona las dos
# mitades de esa fuente —fichas y catálogo—, porque son un solo conector
# partido en dos llamadas y comprobar una sin la otra no dice nada.
SOURCE_ALIASES = {
    "horizon": ["HORIZON EUROPE"],
    "bdns":    ["BDNS"],
    "eccp":    ["ECCP"],
    "een":     ["EEN"],
    "cdti":    ["CDTI"],
    "idae":    ["IDAE", "IDAE CATÁLOGO"],
    "boe":     ["BOE / MITECO"],
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Carga variables desde ".env" si el archivo existe junto a este script.
# ".env" está en .gitignore: es el sitio recomendado para las claves reales.
# Quien prefiera el flujo antiguo puede seguir pegando la clave directamente
# más abajo; las variables de entorno (incluidas las de .env) tienen prioridad.
load_dotenv()

# ── TU API KEY DE CLAUDE (Anthropic) ─────────────────────────────────
# Generar, renovar o revocar: https://console.anthropic.com/settings/keys
# Se toma de la variable de entorno CLAUDE_API_KEY (definida en .env) si existe;
# si no, se usa el valor de respaldo de abajo ("Placeholder" = deshabilitada).
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "Placeholder")

# ── PUBLICACIÓN EN GITHUB PAGES ──────────────────────────────────────
# Generar, renovar o revocar el token: https://github.com/settings/tokens
# El token necesita permiso de escritura sobre el contenido del repositorio.
# Igual que arriba: prioridad a la variable de entorno GITHUB_TOKEN (.env).
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "Placeholder")

GITHUB_USER = "GOrtega-KAL"
GITHUB_REPO = "Grant-Radar-CC"  # Repositorio paralelo de esta copia de trabajo
GITHUB_BRANCH = "main"

# ── MODELO Y PARÁMETROS ───────────────────────────────────────────────
# CLAUDE_MODEL vive en grant_radar/versions.py, junto al resto de versiones
# que identifican un análisis en caché; CLAUDE_SLEEP_S, en
# grant_radar/analysis.py, que es la capa que marca el ritmo de llamada.
# Barrera previa a cualquier llamada. El coste usa el extremo superior observado
# por convocatoria; sigue siendo una estimación, no una garantía de facturación.
# PROFILE_VERSION, EXTRACTOR_VERSION, EVALUATOR_VERSION,
# PARTNER_CATALOG_VERSION, ANALYSIS_PROMPT_VERSION y CACHE_SCHEMA_VERSION
# viven en grant_radar/versions.py. Subir cualquiera invalida de forma
# intencionada los análisis anteriores.
PUBLIC_SCHEMA_VERSION = 3

# ── RUTAS DE ARCHIVOS (Windows local) ────────────────────────────────
# El dashboard local y GitHub Pages consumen el mismo JSON junto a index.html.
# La caché interna, que no debe publicarse, permanece en grant_radar_data.
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_DIR, "grant_radar_data")
os.makedirs(DATA_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(PROJECT_DIR, "convocatorias.json")
# Estado de la ultima recopilacion, que publica tambien el modo --no-claude:
# el dashboard lo lee aparte para avisar de cuantas convocatorias esperan
# analisis. Vive en la raiz porque GitHub Pages sirve desde ahi.
COLLECTION_STATE_FILE = os.path.join(PROJECT_DIR, "estado_recopilacion.json")
CACHE_FILE = os.path.join(DATA_DIR, "grant_radar_cache.json")
AUDIT_FILE = os.path.join(DATA_DIR, "grant_radar_audit.json")


# ── PERFIL DE KALFRISA Y CATÁLOGO DE SOCIOS ──────────────────────────
# Ver grant_radar/kalfrisa_profile.py y grant_radar/partner_catalog.py

# ── LOGGING ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("grant_radar")
# SOURCE_RUNTIME_METADATA, IDENTITY_LANDINGS, COVERAGE_WATCH_RESULTS y
# RUN_DIAGNOSTICS viven en grant_radar/runtime_state.py y se importan arriba:
# son los mismos objetos mutables, no copias (ver ese módulo).


# Vigilancia de regresiones para oportunidades estratégicas conocidas. Estas
# reglas NO crean convocatorias ni alteran la relevancia: únicamente verifican
# si el descubrimiento genérico observó su identidad en la ejecución actual.

print(f"✓ Ejecución local Windows — proyecto: {PROJECT_DIR}")
print(f"✓ Caché local: {CACHE_FILE}")
print(f"✓ JSON del dashboard: {OUTPUT_FILE}")
print(f"✓ Auditoría de descartes: {AUDIT_FILE}")
print("✓ Configuración cargada correctamente")




print("✓ Funciones auxiliares cargadas")


# ─────────────────────────────────────────────────────────────────────
# CELDA 4 — FUNCIONES DE CONSULTA DE FUENTES
# ─────────────────────────────────────────────────────────────────────


print("✓ Funciones de fuentes cargadas")


# ─────────────────────────────────────────────────────────────────────
# CELDA 5 — ANÁLISIS CON CLAUDE HAIKU 4.5 (Anthropic)
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# NORMALIZACIÓN DETERMINISTA DE ENTIDADES (post-procesamiento, sin IA)
# ─────────────────────────────────────────────────────────────────────
# Corrige alucinaciones de nombres propios que Claude Haiku puede introducir
# al redactar texto libre (p.ej. "ITAINNOMA"/"ITAINNORA" en vez de ITAINNOVA).
# Se aplica DESPUÉS de recibir la respuesta de Haiku y ANTES de guardar el
# JSON. No sustituye la verificación de veracidad por una segunda llamada a
# IA: es una corrección determinista contra una lista blanca conocida.



print("✓ Normalización determinista de entidades cargada")


print("✓ Función de análisis Claude Haiku 4.5 cargada")


# ─────────────────────────────────────────────────────────────────────
# CELDA 6 — FUNCIONES DE ENSAMBLADO DEL JSON FINAL


# ─────────────────────────────────────────────────────────────────────


print("✓ Funciones de ensamblado cargadas")


# ─────────────────────────────────────────────────────────────────────


# VERIFICACIÓN TÉCNICA DE URLs (HTTP, no IA)
# ─────────────────────────────────────────────────────────────────────


print("✓ Verificación técnica de URLs cargada")


# ─────────────────────────────────────────────────────────────────────
# CELDA 6B — CONFIGURACIÓN GITHUB PAGES Y FUNCIÓN DE SUBIDA


# ─────────────────────────────────────────────────────────────────────


print("✓ Función GitHub Pages cargada")


# ─────────────────────────────────────────────────────────────────────
# CELDA 7 — PIPELINE PRINCIPAL


# Ejecuta todo el proceso: recolección → análisis → JSON
# ─────────────────────────────────────────────────────────────────────


def publish_collection_state(staleness: dict, detected: int, active: int) -> None:
    """Deja a la vista del dashboard cuántas convocatorias esperan análisis.

    Es la pieza que faltaba del flujo acordado el 21/08/2026 (AGENTS.md 47.5):
    una recopilación diaria sin coste decide cuándo merece la pena pagar un
    análisis, pero hasta ahora ese número solo salía por consola, así que quien
    miraba el panel no podía saber si lo publicado seguía al día.

    Matiz sobre el invariante de `--no-claude`: sigue sin llamar a Claude, sin
    tocar la caché de análisis y sin generar ni publicar `convocatorias.json`.
    Lo que publica es un archivo aparte, pequeño y de solo lectura para el
    panel, que describe la recopilación y no el producto.
    """
    state = build_collection_state(
        staleness,
        detected=detected,
        active=active,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    try:
        with open(COLLECTION_STATE_FILE, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        log.warning(f"No se pudo escribir el estado de recopilación: {exc}")
        return
    print(f"  Estado de recopilación actualizado: {COLLECTION_STATE_FILE}")
    github_upload(
        COLLECTION_STATE_FILE,
        token=GITHUB_TOKEN,
        user=GITHUB_USER,
        repo=GITHUB_REPO,
        branch=GITHUB_BRANCH,
        message=(
            "Grant-Radar: estado de recopilación "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')} UTC"
        ),
    )


def run_pipeline(


    no_claude: bool = False,
    max_claude: int | None = None,


    claude_matches: list[str] | None = None,
    force_reanalysis: bool = False,


    hold_pilot: int | None = None,
    sources: list[str] | None = None,
):


    pipeline_started = time.perf_counter()
    run_started_at = datetime.now(timezone.utc).isoformat()


    DISCOVERY_AUDIT.clear()
    IDENTITY_LANDINGS.clear()


    COVERAGE_WATCH_RESULTS.clear()
    SOURCE_RUNTIME_METADATA.clear()
    RUN_DIAGNOSTICS.clear()
    print("=" * 60)
    print("Grant-Radar — Iniciando pipeline")
    print("=" * 60)

    if not no_claude and not claude_key_format_is_valid(CLAUDE_API_KEY):
        print("⚠ ERROR: el formato de CLAUDE_API_KEY no es válido.")
        print("  La ejecución se detiene antes de recopilar o modificar archivos.")
        return
    if not no_claude:
        try:
            schema_models = (
                (BdnsHoldFacts,)
                if hold_pilot is not None
                else (CallFacts, CallEvaluation)
            )
            schema_metrics = [
                validate_structured_output_schema(model)
                for model in schema_models
            ]
        except ClaudeAnalysisError as exc:
            print(f"⚠ ERROR: {exc}")
            print("  La ejecución se detiene antes de recopilar o llamar a Claude.")
            return
        print(
            "✓ Esquemas Claude compatibles: "
            + ", ".join(
                f"{item['model']} "
                f"({item['optional_fields']} opcionales, "
                f"{item['union_fields']} uniones)"
                for item in schema_metrics
            )
        )

    # 1 ── RECOLECCIÓN DE FUENTES
    # Las APIs se consultan por HTTP. Todas las fuentes HTML comparten una
    # única sesión Chromium para evitar arrancar un navegador por petición.
    source_timings = {}

    def timed_fetch(source_name, fetch_function, *args):
        started = time.perf_counter()
        try:
            return fetch_function(*args)
        finally:
            source_timings[source_name] = time.perf_counter() - started

    browser_startup_seconds = None
    # Selección parcial de fuentes (`--source`). Existe porque comprobar un
    # cambio en un solo conector obligaba a recorrer los ocho: quince minutos,
    # y ocho ejecuciones en un día bastaron el 19/08 para que boe.es
    # respondiera 429 (AGENTS.md 35, punto 5 del backlog). Solo se admite con
    # `--no-claude`, porque un recuento parcial no puede alimentar el producto.
    selected = set(sources or ())
    partial = bool(selected)

    def wanted(source_name: str) -> bool:
        return not partial or source_name in selected

    if hold_pilot is not None:
        # El piloto responde únicamente preguntas sobre registros BDNS en espera.
        # Evita iniciar Chromium o consultar fuentes que no pueden aportar casos.
        raw_by_source = {"BDNS": timed_fetch("BDNS", fetch_bdns)}
    else:
        raw_by_source = {}
        if wanted("HORIZON EUROPE"):
            raw_by_source["HORIZON EUROPE"] = timed_fetch(
                "HORIZON EUROPE", fetch_horizon_europe
            )
        if wanted("BDNS"):
            raw_by_source["BDNS"] = timed_fetch("BDNS", fetch_bdns)
        if wanted("ECCP"):
            # El conector recibe el prefiltro como predicado de relevancia: no
            # conoce las reglas, solo pregunta si algo merece conservarse.
            raw_by_source["ECCP"] = timed_fetch(
                "ECCP", fetch_eccp, deterministic_prefilter
            )
        if wanted("EEN"):
            raw_by_source["EEN"] = timed_fetch("EEN", fetch_een_funding)
        # Chromium solo se arranca si alguna fuente seleccionada lo necesita:
        # las cuatro de arriba son HTTP puro, así que verificar un cambio en
        # Horizon o BDNS ya no paga el navegador.
        browser_sources = [
            name for name in
            ("IDAE", "BOE / MITECO", "IDAE CATÁLOGO", "CDTI")
            if wanted(name)
        ]
        if browser_sources:
            browser_started = time.perf_counter()
            with PlaywrightBrowser(headless=True) as browser:
                browser_startup_seconds = time.perf_counter() - browser_started
                if wanted("IDAE"):
                    raw_by_source["IDAE"] = timed_fetch("IDAE", fetch_idae, browser)
                if wanted("BOE / MITECO"):
                    raw_by_source["BOE / MITECO"] = timed_fetch(
                        "BOE / MITECO", fetch_boe, browser
                    )
                if wanted("IDAE CATÁLOGO"):
                    raw_by_source["IDAE CATÁLOGO"] = timed_fetch(
                        "IDAE CATÁLOGO", fetch_idae_catalog, browser
                    )
                if wanted("CDTI"):
                    raw_by_source["CDTI"] = timed_fetch("CDTI", fetch_cdti, browser)
                # La vigilancia de programas recurrentes compara lo recopilado
                # con un catálogo de programas que se sabe que existen. Con una
                # selección parcial daría por desaparecido todo lo que vive en
                # las fuentes no consultadas: son alarmas falsas garantizadas,
                # así que no se ejecuta (AGENTS.md 46.4).
                if not partial:
                    coverage_items = [
                        item for items in raw_by_source.values() for item in items
                    ] + IDENTITY_LANDINGS
                    COVERAGE_WATCH_RESULTS.extend(
                        probe_missing_recurrent_coverage(browser, coverage_items)
                    )
    collection_seconds = time.perf_counter() - pipeline_started

    print("\nTiempos de recopilación:")
    if browser_startup_seconds is not None:
        print(f"  {'Chromium (inicio)':<18} {browser_startup_seconds:>7.2f} s")
    else:
        print(f"  {'Chromium':<18} {'no arrancado':>12}")
    for source_name in raw_by_source:
        print(f"  {source_name:<18} {source_timings.get(source_name, 0.0):>7.2f} s")
    print(f"  {'TOTAL RECOPILACIÓN':<18} {collection_seconds:>7.2f} s")
    if partial:
        # Este aviso no es decorativo: los recuentos de referencia (AGENTS.md
        # 53.4) solo significan algo sobre las ocho fuentes. Sin decirlo, un
        # "82 vigentes" parcial se compararía con el completo y parecería una
        # avería donde solo hay una selección.
        print(
            "\n  AVISO: recopilación PARCIAL de "
            f"{len(raw_by_source)} fuente(s): {', '.join(raw_by_source)}."
        )
        print(
            "  Los recuentos NO son comparables con las cifras de referencia,"
        )
        print("  y la vigilancia de programas recurrentes queda desactivada.")

    # Resumen consolidado de salud de fuentes: cada fuente ya avisó por
    # consola en el momento (log.warning dentro de assess_web_inventory_health),
    # pero ese aviso puede pasar desapercibido entre cientos de líneas de log
    # de una recopilación larga. Aquí se agrupan todas las fuentes que esta
    # misma ejecución marcó como "degraded" o "unhealthy", para que quede
    # visible de un vistazo sin tener que revisar el log completo ni el JSON
    # de auditoría.
    unhealthy_sources = {
        source: health
        for source, health in RUN_DIAGNOSTICS.get("web_source_health", {}).items()
        if health.get("status") != "healthy"
    }
    if unhealthy_sources:
        print("\n⚠ Fuentes con salud degradada en esta ejecución:")
        for source, health in unhealthy_sources.items():
            issues = ", ".join(health.get("issues", [])) or "sin detalle"
            print(f"  {source:<18} {health.get('status'):<10} {issues}")

    # Ningun umbral absoluto habria detectado el embudo del IDAE (AGENTS.md 45):
    # 71 fichas para una convocatoria era a la vez el sintoma y su estado normal.
    # Lo que delata ese tipo de fallo es el cambio, asi que cada etapa se compara
    # con la ejecucion anterior guardada en la auditoria.
    funnel_regressions = compare_funnels(
        previous_source_health(AUDIT_FILE),
        RUN_DIAGNOSTICS.get("web_source_health", {}),
    )
    RUN_DIAGNOSTICS["source_funnel_regressions"] = funnel_regressions
    if funnel_regressions:
        print("\n⚠ Etapas que caen respecto a la ejecución anterior:")
        for regression in funnel_regressions:
            print(
                f"  {regression['source']:<18} {regression['label']:<16} "
                f"{regression['previous']} -> {regression['current']} "
                f"(-{regression['drop']:.0%})"
            )

    all_raw_with_duplicates = [
        item for items in raw_by_source.values() for item in items
    ] + IDENTITY_LANDINGS
    all_raw = _deduplicate_raw_convocations(all_raw_with_duplicates)
    deduplicated_count = len(all_raw_with_duplicates) - len(all_raw)
    for check in COVERAGE_WATCH_RESULTS:
        log_method = (
            log.warning
            if check["status"] in {
                "not_observed",
                "active_not_captured",
                "republication_not_observed",
            }
            else log.info
        )
        log_method(
            f"  Cobertura recurrente [{check['status']}]: {check['label']} "
            f"(coincidencias={check['matches']})"
        )
    detected_count = len(all_raw)
    print(
        f"\nTotal convocatorias detectadas antes de filtros: {detected_count} "
        f"({deduplicated_count} duplicadas fusionadas)"
    )

    # ── Filtro defensivo: eliminar convocatorias con plazo ya cerrado ──
    # Puede ocurrir si la caché contiene topics cerrados de ejecuciones
    # anteriores o si el scraper extrae páginas históricas.
    all_raw_pre = len(all_raw)
    descartadas_por_deadline = [c for c in all_raw if not (c.get("deadline_days", 1) > 0)]
    all_raw = [c for c in all_raw if c.get("deadline_days", 1) > 0]
    for discarded in descartadas_por_deadline:
        audit_exclusion(
            discarded,
            "deadline_closed",
            "pipeline_deadline_filter",
        )
    n_cerradas = all_raw_pre - len(all_raw)
    if n_cerradas:
        log.info(f"  Filtradas {n_cerradas} convocatorias con plazo cerrado (deadline_days <= 0)")
        # Detalle por convocatoria: permite diagnosticar si una fuente reporta
        # "count" > 0 en sources pero 0 convocatorias visibles en el JSON final
        # (se descartaron aquí, ANTES del análisis Claude, sin pasar por
        # "descartada" — por eso tampoco aparecen en el toggle "ver descartadas").
        for c in descartadas_por_deadline:
            log.info(f"    - [{c.get('source')}] deadline_days={c.get('deadline_days')} "
                     f"deadline_date={c.get('deadline_date','')!r} :: {c.get('title','')[:70]}")
    conteo_cerradas_por_fuente = Counter(c.get("source", "") for c in descartadas_por_deadline)

    # ── Prefiltro común conservador antes de incurrir en coste IA ──
    deterministic_rejections = []
    deterministic_holds = []
    prefilter_counts = Counter()
    prefilter_by_source = {}
    bdns_reason_counts = Counter()
    bdns_role_counts = Counter()
    retained = []
    for conv in all_raw:
        outcome = deterministic_prefilter(conv)
        conv["deterministic_prefilter"] = outcome
        prefilter_counts[outcome["decision"]] += 1
        source_counter = prefilter_by_source.setdefault(
            str(conv.get("source", "unknown")), Counter()
        )
        source_counter[outcome["decision"]] += 1
        if conv.get("bdns_filter_ready"):
            bdns_reason_counts[outcome.get("reason_code", "generic_prefilter")] += 1
            if outcome["decision"] in {"retain", "ambiguous"}:
                bdns_role_counts[conv.get("opportunity_role", "unknown")] += 1
        if outcome["decision"] in {"reject", "hold_manual"}:
            target = (
                deterministic_rejections
                if outcome["decision"] == "reject"
                else deterministic_holds
            )
            target.append((conv, outcome))
            if outcome["decision"] == "reject":
                audit_exclusion(
                    conv,
                    outcome.get("reason_code", "deterministic_reject"),
                    "pre_claude_deterministic_filter",
                    outcome,
                )
        else:
            retained.append(conv)
    all_raw = retained
    RUN_DIAGNOSTICS["deterministic_prefilter"] = dict(prefilter_counts)
    RUN_DIAGNOSTICS["deterministic_prefilter_by_source"] = {
        source: dict(counts) for source, counts in prefilter_by_source.items()
    }
    RUN_DIAGNOSTICS["bdns_prefilter"] = {
        "reasons": dict(bdns_reason_counts),
        "retained_roles": dict(bdns_role_counts),
    }
    if deterministic_rejections:
        log.info(
            f"  Filtradas {len(deterministic_rejections)} convocatorias por "
            "exclusión determinista inequívoca"
        )
    if deterministic_holds:
        if hold_pilot is not None:
            log.info(
                f"  Detectadas {len(deterministic_holds)} convocatorias en espera; "
                "el piloto seleccionará una muestra y resolverá primero lo determinista"
            )
        else:
            log.info(
                f"  Detectadas {len(deterministic_holds)} convocatorias BDNS con "
                "datos pendientes; se enriquecerán localmente y las no resueltas "
                "continuarán al análisis general"
            )
    log.info(
        "  Prefiltro común: "
        + ", ".join(f"{key}={value}" for key, value in sorted(prefilter_counts.items()))
    )
    print(f"Total tras prefiltro inicial: {len(all_raw)}")

    if hold_pilot is not None:
        print("\n" + "=" * 60)
        print(
            f"PILOTO BDNS HOLD — máximo {hold_pilot} casos; "
            "una pregunta factual por caso no resuelto"
        )
        try:
            hold_report = run_bdns_hold_pilot(
                deterministic_holds,
                hold_pilot,
                CLAUDE_API_KEY,
                _bdns_intrinsic_exclusion,
            )
        except ClaudeAnalysisError as exc:
            log.error(str(exc))
            save_discovery_audit(
                run_started_at,
                "aborted_bdns_hold_pilot",
                {name: len(items) for name, items in raw_by_source.items()},
                audit_file=AUDIT_FILE,
            )
            print("PIPELINE ABORTADO — no se modificó la caché principal ni el JSON.")
            print(f"El progreso parcial está en: {BDNS_HOLD_REPORT_FILE}")
            print("=" * 60)
            return
        RUN_DIAGNOSTICS["bdns_hold_pilot"] = {
            "selected": hold_report.get("selected", 0),
            "counts": hold_report.get("counts", {}),
            "cache_hits": hold_report.get("cache_hits", 0),
            "deterministic_resolutions": hold_report.get(
                "deterministic_resolutions", 0
            ),
            "evidence_totals": {
                key: sum(
                    int(item.get("evidence_metrics", {}).get(key, 0))
                    for item in hold_report.get("results", [])
                )
                for key in (
                    "candidate_urls", "fetched_urls", "errors", "bytes",
                    "documents_with_text", "characters",
                )
            },
        }
        save_discovery_audit(
            run_started_at,
            "completed_bdns_hold_pilot",
            {name: len(items) for name, items in raw_by_source.items()},
            claude_usage=hold_report.get("usage", {}),
            audit_file=AUDIT_FILE,
        )
        result_counts = hold_report.get("counts", {})
        print(
            "  Resultados: "
            + (
                ", ".join(
                    f"{key}={value}" for key, value in sorted(result_counts.items())
                )
                if result_counts else "sin casos seleccionables"
            )
        )
        usage = hold_report.get("usage", {})
        print(
            f"  Llamadas Haiku: {usage.get('completed_api_calls', 0)} · "
            f"tokens: {usage.get('total_tokens', 0):,} · "
            f"coste estimado: ${usage.get('estimated_cost_usd', 0):.4f}"
        )
        print(f"  Informe: {BDNS_HOLD_REPORT_FILE}")
        print("  No se modificó la caché principal.")
        print("  No se generó ni publicó convocatorias.json.")
        print("=" * 60)
        return hold_report

    if deterministic_holds:
        auto_resolution = resolve_bdns_holds_for_pipeline(
            deterministic_holds,
            _bdns_intrinsic_exclusion,
            deterministic_prefilter,
        )
        all_raw.extend(auto_resolution["retained"])
        for conv, outcome in auto_resolution["rejected"]:
            deterministic_rejections.append((conv, outcome))
            audit_exclusion(
                conv,
                outcome.get("reason_code", "bdns_hold_deterministic_reject"),
                "bdns_automatic_hold_resolution",
                outcome,
            )
        RUN_DIAGNOSTICS["bdns_automatic_hold_resolution"] = {
            "initial_holds": len(deterministic_holds),
            "counts": auto_resolution["counts"],
            "local_resolutions": auto_resolution["local_resolutions"],
            "evidence_totals": auto_resolution["evidence_totals"],
            "remaining_manual": 0,
        }
        log.info(
            "  Resolución automática BDNS: "
            + ", ".join(
                f"{key}={value}"
                for key, value in sorted(auto_resolution["counts"].items())
            )
            + "; revisión manual=0"
        )

    print(f"Total tras filtros deterministas y reentrada BDNS: {len(all_raw)}")

    if not all_raw:
        save_discovery_audit(
            run_started_at,
            "completed_without_active_results",
            {name: len(items) for name, items in raw_by_source.items()},
            audit_file=AUDIT_FILE,
        )
        print("⚠ No se detectaron convocatorias. Revisa conectividad y keywords.")
        return

    if no_claude:
        cache_snapshot = cache_load(CACHE_FILE)
        _hydrate_stable_cached_documents(all_raw, cache_snapshot)
        forecast_selection = build_claude_analysis_selection(
            all_raw, cache_snapshot, []
        )
        forecast_new = len(forecast_selection["new_items"])
        forecast = {
            "candidates": len(all_raw),
            "cache_hits": len(forecast_selection["cached_items"]),
            "new_or_changed": forecast_new,
            "expected_api_calls": forecast_new * 2,
            # Calibración del 20/08/2026 sobre 76 análisis reales, la primera
            # con el extractor v7 (ver AGENTS.md sección 11). Antes eran
            # 0,0265 central y 0,0180-0,0350, de una muestra de dos.
            "estimated_cost_central_usd": round(
                forecast_new * CLAUDE_OBSERVED_MEAN_USD_PER_ANALYSIS, 4
            ),
            "estimated_cost_range_usd": [
                round(forecast_new * CLAUDE_OBSERVED_P05_USD_PER_ANALYSIS, 4),
                round(forecast_new * CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS, 4),
            ],
        }
        safety = claude_safety_preflight(forecast_new)
        RUN_DIAGNOSTICS["claude_forecast"] = forecast
        RUN_DIAGNOSTICS["claude_safety"] = safety
        RUN_DIAGNOSTICS["candidate_inventory"] = (
            build_no_claude_candidate_inventory(all_raw, cache_snapshot)
        )
        print("\n" + "=" * 60)
        print("MODO --no-claude — recopilación finalizada")
        for source_name in raw_by_source:
            valid_items = [
                item for item in all_raw
                if (
                    item.get("source") == source_name
                    or source_name in item.get("discovery_sources", [])
                )
                and item.get("deadline_days", 1) > 0
            ]
            valid_count = len(valid_items)
            print(f"  {source_name:<18} {valid_count:>3} vigentes")
            for item in sorted(
                valid_items,
                key=lambda value: value.get("deadline_days", 9999),
            ):
                deadline_label = (
                    item.get("deadline_date")
                    or f"{item.get('deadline_days', '?')} días (sin fecha confirmada)"
                )
                print(f"    - [{deadline_label}] {item.get('title', '')}")
        print(f"  {'TOTAL':<18} {len(all_raw):>3} vigentes")
        print(
            f"  Previsión Claude: {forecast['new_or_changed']} nuevas/cambiadas, "
            f"{forecast['expected_api_calls']} llamadas, "
            f"${forecast['estimated_cost_central_usd']:.4f} central "
            f"(${forecast['estimated_cost_range_usd'][0]:.4f}-"
            f"${forecast['estimated_cost_range_usd'][1]:.4f})"
        )
        print(
            "  Barrera Claude: "
            + (
                "dentro de límites"
                if safety["allowed"]
                else "BLOQUEARÍA la ejecución"
            )
            + f" · máximo {safety['max_analyses']} análisis"
            + f" · máximo estimado ${safety['max_estimated_cost_usd']:.2f}"
        )
        print("  No se llamó a Claude.")
        print("  No se modificó la caché IA; las cachés documentales públicas sí pueden actualizarse.")
        print("  No se generó ni publicó convocatorias.json.")
        save_discovery_audit(
            run_started_at,
            "completed_no_claude",
            {name: len(items) for name, items in raw_by_source.items()},
            audit_file=AUDIT_FILE,
        )
        print(f"  Auditoría de descartes actualizada: {AUDIT_FILE}")
        # Con la auditoría ya guardada, esta recopilación cuenta para el
        # desfase. Es el dato que justifica —o no— pagar una ejecución con
        # Claude, y el motivo de programar esta recopilación a diario.
        staleness = build_staleness_report(load_audit_runs(AUDIT_FILE))
        print("  " + summarize_staleness(staleness))
        print("  Detalle: --staleness-report")
        publish_collection_state(staleness, detected_count, len(all_raw))
        print("=" * 60)
        return all_raw

    # 2 ── ANÁLISIS CON CLAUDE HAIKU (solo convocatorias nuevas, las demás van de caché)
    cache = cache_load(CACHE_FILE)
    _hydrate_stable_cached_documents(all_raw, cache)
    selection = build_claude_analysis_selection(
        all_raw,
        cache,
        claude_matches,
        force_reanalysis=force_reanalysis,
    )
    nuevas = selection["new_items"]
    en_cache = selection["cached_items"]
    normalized_matches = [
        _fold_text(value) for value in (claude_matches or []) if value.strip()
    ]
    analysis_candidates = selection["candidates"]
    analysis_target = (
        analysis_candidates[:max_claude]
        if max_claude is not None
        else analysis_candidates
    )
    run_usage_records = []
    safety = claude_safety_preflight(len(analysis_target))
    RUN_DIAGNOSTICS["claude_safety"] = safety

    print(f"  → En caché (sin llamada a Claude Haiku): {len(en_cache)}")
    print(f"  → Nuevas (requieren análisis):     {len(nuevas)}")
    if force_reanalysis:
        print(
            f"  → Reanálisis forzado desde caché:  "
            f"{len(selection['forced_cached'])}"
        )
    if normalized_matches:
        print(
            f"  → Coinciden con --claude-match:    "
            f"{len(analysis_candidates)}"
        )
        for value in claude_matches or []:
            print(f"      - {value}")
    if max_claude is not None:
        print(
            f"  → Modo limitado: se analizarán como máximo {max_claude} "
            "y no se generará ni publicará JSON"
        )

    if not safety["allowed"]:
        reasons = ", ".join(safety["breaches"])
        save_discovery_audit(
            run_started_at,
            "aborted_claude_safety_limit",
            {name: len(items) for name, items in raw_by_source.items()},
            audit_file=AUDIT_FILE,
        )
        print("\n" + "=" * 60)
        print("PIPELINE DETENIDO ANTES DE CLAUDE — límite de seguridad")
        print(
            f"  Análisis previstos: {safety['planned_analyses']} "
            f"(máximo {safety['max_analyses']})"
        )
        print(
            "  Coste superior estimado: "
            f"${safety['estimated_upper_cost_usd']:.4f} "
            f"(máximo ${safety['max_estimated_cost_usd']:.2f})"
        )
        print(f"  Límites excedidos: {reasons}")
        print("  No se llamó a Claude ni se modificó la caché IA.")
        print("  No se generó ni publicó convocatorias.json.")
        print("=" * 60)
        return

    if analysis_target:
        print(
            f"\nAnalizando {len(analysis_target)} de "
            f"{len(analysis_candidates)} convocatorias seleccionadas "
            + (
                "con Claude Haiku 4.5 (reanálisis selectivo)..."
                if force_reanalysis
                else "nuevas con Claude Haiku 4.5..."
            )
        )

    for i, conv in enumerate(analysis_target):
        print(f"  [{i+1}/{len(analysis_target)}] {conv['title'][:65]}...")
        try:
            analysis = analyze_with_claude(conv, CLAUDE_API_KEY)
        except ClaudeAnalysisError as e:
            log.error(str(e))
            partial_usage = aggregate_partial_token_usage(e.partial_usages)
            aborted_run_usage = aggregate_aborted_run_usage(
                run_usage_records, e.partial_usages
            )
            if partial_usage["completed_api_calls"]:
                log.warning(
                    "Consumo parcial antes del aborto: "
                    f"{partial_usage['completed_api_calls']} llamada(s), "
                    f"{partial_usage['total_tokens']:,} tokens, "
                    f"coste estimado ${partial_usage['estimated_cost_usd']:.4f}"
                )
            save_discovery_audit(
                run_started_at,
                "aborted_claude_error",
                {name: len(items) for name, items in raw_by_source.items()},
                claude_usage=aborted_run_usage,
                audit_file=AUDIT_FILE,
            )
            print("\n" + "=" * 60)
            print("PIPELINE ABORTADO — no se generó ni publicó convocatorias.json")
            print("Los análisis completados correctamente sí permanecen en caché.")
            print("=" * 60)
            return
        usage = analysis.get("token_usage", {})
        if usage:
            run_usage_records.append(usage)
            print(
                f"       Tokens: {usage.get('input_tokens', 0):,} entrada + "
                f"{usage.get('output_tokens', 0):,} salida = "
                f"{usage.get('total_tokens', 0):,} · "
                f"coste estimado ${usage.get('estimated_cost_usd', 0):.4f}"
            )
        key = cache_key(conv)
        cache[key] = {
            "raw_document": conv,
            "extracted_facts": analysis.get("call_facts", {}),
            "evaluation": {
                field: analysis.get(field)
                for field in (
                    "fit_score", "actionability_score", "confidence", "decision",
                    "eligibility", "eligibility_reason", "recommended_role",
                    "scores", "evidence_quality", "positive_evidence",
                    "risks_and_unknowns", "partner_needs",
                    "recommended_partners", "resumen", "accion", "tags",
                )
            },
            "analysis": analysis,
            "token_usage": usage,
            "source_hash": source_hash(conv),
            "retrieved_at": run_started_at,
            "extractor_version": EXTRACTOR_VERSION,
            "evaluator_version": EVALUATOR_VERSION,
            "profile_version": PROFILE_VERSION,
            "partner_catalog_version": PARTNER_CATALOG_VERSION,
            "model_version": CLAUDE_MODEL,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }
        # Guardar caché tras cada análisis para no perder progreso si falla a mitad
        cache_save(cache, CACHE_FILE)
        if i < len(analysis_target) - 1:
            time.sleep(CLAUDE_SLEEP_S)  # pausa mínima entre llamadas

    if max_claude is not None:
        pendientes = len(analysis_candidates) - len(analysis_target)
        fuera_de_seleccion = len(selection["pool"]) - len(analysis_candidates)
        limited_usage = aggregate_token_usage(run_usage_records)
        save_discovery_audit(
            run_started_at,
            "completed_claude_limited",
            {name: len(items) for name, items in raw_by_source.items()},
            claude_usage=limited_usage,
            audit_file=AUDIT_FILE,
        )
        print("\n" + "=" * 60)
        print("MODO --max-claude FINALIZADO")
        print(f"  Análisis guardados en caché: {len(analysis_target)}")
        print(f"  Seleccionadas pendientes: {pendientes}")
        if normalized_matches:
            print(f"  Fuera de la selección: {fuera_de_seleccion}")
        print(
            f"  Tokens consumidos: {limited_usage['input_tokens']:,} entrada + "
            f"{limited_usage['output_tokens']:,} salida = "
            f"{limited_usage['total_tokens']:,}"
        )
        print(
            f"  Coste estimado de esta prueba: "
            f"${limited_usage['estimated_cost_usd']:.4f}"
        )
        print("  No se generó ni publicó convocatorias.json.")
        print("  Ejecuta el comando normal para completar y publicar.")
        print("=" * 60)
        return {
            "analyzed": len(analysis_target),
            "pending": pendientes,
            "unselected": fuera_de_seleccion,
            "published": False,
            "usage": limited_usage,
        }

    # Ensamblar resultados: caché + nuevos análisis
    enriched = []
    for conv in all_raw:
        key      = cache_key(conv)
        analysis = cache[key]["analysis"] if key in cache else {
            "match_score": 50, "fit_score": 50, "actionability_score": 0,
            "confidence": 0, "priority": "low", "decision": "watch",
            "eligibility": "unknown", "eligibility_reason": "Pendiente de análisis.",
            "recommended_role": "unknown", "scores": {},
            "evidence_quality": "low", "positive_evidence": [],
            "risks_and_unknowns": ["Análisis no disponible."], "partner_needs": [],
            "recommended_partners": [], "review_required": False,
            "review_reasons": [], "data_pending": True,
            "data_gaps": ["analysis_pending"], "monitoring_flags": [],
            "call_facts": {}, "resumen": "Pendiente de análisis.",
            "accion": "Completar el análisis automático.",
            "dimensiones": [{"name": n, "val": 50} for n in
                ["Alineación tecnológica","Capacidad de consorcio","Madurez TRL requerida","Oportunidad estratégica"]],
            "tags": [], "tech_tags": [],
        }
        enriched.append(_assemble_public_record(len(enriched) + 1, conv, analysis))
        if analysis.get("descartada", False):
            audit_exclusion(
                conv,
                "discarded_after_analysis",
                "deterministic_post_analysis",
                {
                    "motivo_descarte": analysis.get("motivo_descarte", ""),
                    "match_score": analysis.get("match_score", 50),
                    "decision": analysis.get("decision", ""),
                },
            )

    # 3 ── ORDENAR por match score
    enriched.sort(key=lambda x: x["match"], reverse=True)

    # 3B ── VERIFICACIÓN TÉCNICA DE URLs (antes de publicar)
    verificar_urls(enriched)

    # 4 ── GUARDAR JSON
    output = {
        "schema_version": PUBLIC_SCHEMA_VERSION,
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "last_updated":  datetime.now(timezone.utc).isoformat(),
        "versions": {
            "analysis": ANALYSIS_PROMPT_VERSION,
            "profile": PROFILE_VERSION,
            "extractor": EXTRACTOR_VERSION,
            "evaluator": EVALUATOR_VERSION,
            "partner_catalog": PARTNER_CATALOG_VERSION,
            "model": CLAUDE_MODEL,
        },
        "collection_seconds": round(collection_seconds, 2),
        "claude_usage": {
            "current_run": aggregate_token_usage(run_usage_records),
            "published_analysis_total": aggregate_token_usage([
                item.get("token_usage", {}) for item in enriched
            ]),
        },
        "coverage_watch": list(COVERAGE_WATCH_RESULTS),
        "convocatorias": enriched,
        "review_queue": [
            {
                "id": item["id"],
                "source": item["source"],
                "title": item["title"],
                "deadline": item["deadline"],
                "fit_score": item["fit_score"],
                "actionability_score": item["actionability_score"],
                "confidence": item["confidence"],
                "reasons": item["review_reasons"],
            }
            for item in enriched
            if item.get("review_required", False)
        ],
        "data_gap_queue": [
            {
                "id": item["id"],
                "source": item["source"],
                "title": item["title"],
                "deadline": item["deadline"],
                "fit_score": item["fit_score"],
                "actionability_score": item["actionability_score"],
                "confidence": item["confidence"],
                "reasons": item["data_gaps"],
            }
            for item in enriched
            if item.get("data_pending", False) and not item.get("descartada", False)
        ],
        "stats":         build_stats(
            enriched,
            detected_total=all_raw_pre,
            closed_total=n_cerradas,
        ),
        "sources":       build_source_status(
            raw_by_source,
            conteo_cerradas_por_fuente,
            source_timings,
            enriched,
        ),
        "keywords":      build_keywords(enriched),
    }

    # Qué cambia en lo que el usuario ve, comparado con la versión que este
    # archivo está a punto de sustituir. Se lee ANTES de escribir, que es la
    # única oportunidad de tener las dos versiones a mano (AGENTS.md 51.4).
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as previous_handle:
            previous_published = json.load(previous_handle).get("convocatorias", [])
    except (OSError, json.JSONDecodeError):
        previous_published = []
    product_changes = compare_published_products(
        previous_published, output["convocatorias"]
    )
    RUN_DIAGNOSTICS["product_changes"] = product_changes
    print("  " + summarize_product_changes(product_changes))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    save_discovery_audit(
        run_started_at,
        "completed",
        {name: len(items) for name, items in raw_by_source.items()},
        claude_usage=output["claude_usage"]["current_run"],
        audit_file=AUDIT_FILE,
    )

    # 5 ── RESUMEN FINAL
    print("\n" + "=" * 60)
    print(f"✓ JSON generado: {OUTPUT_FILE}")
    print(f"  Convocatorias detectadas:   {output['stats']['detected']}")
    print(f"  Convocatorias vigentes:     {output['stats']['active']}")
    print(f"  Descartadas tras análisis:  {output['stats']['discarded']}")
    print(f"  Relevantes para Kalfrisa:   {output['stats']['relevant']}")
    print(f"  Prioridad alta:             {output['stats']['high']}")
    print(f"  Cierre urgente (<30d):      {output['stats']['urgent']}")
    print(f"  Revisión manual requerida:  {output['stats']['review']}")
    print(
        f"  Tokens Claude registrados:  "
        f"{output['claude_usage']['current_run']['total_tokens']:,}"
    )
    print(
        f"  Coste Claude estimado:      "
        f"${output['claude_usage']['current_run']['estimated_cost_usd']:.4f}"
    )
    print("=" * 60)

    print(f"✓ Archivo guardado en: {os.path.abspath(OUTPUT_FILE)}")

    # ── SUBIDA AUTOMÁTICA A GITHUB PAGES ──────────────────────────────
    github_upload(
        OUTPUT_FILE,
        token=GITHUB_TOKEN,
        user=GITHUB_USER,
        repo=GITHUB_REPO,
        branch=GITHUB_BRANCH,
    )


# ── EJECUTAR ──────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="Monitoriza convocatorias de subvenciones relevantes para Kalfrisa."
    )
    parser.add_argument(
        "--no-claude",
        action="store_true",
        help=(
            "Recopila y filtra convocatorias sin llamar a Claude, modificar la "
            "caché, generar el JSON ni publicar en GitHub."
        ),
    )
    parser.add_argument(
        "--max-claude",
        type=int,
        metavar="N",
        help=(
            "Analiza como máximo N convocatorias nuevas, guarda la caché y "
            "termina sin generar JSON ni publicar en GitHub."
        ),
    )
    parser.add_argument(
        "--claude-match",
        action="append",
        default=[],
        metavar="TEXTO",
        help=(
            "En modo --max-claude, analiza solo convocatorias cuyo título, "
            "identificador, URL o descripción contenga TEXTO. Puede repetirse."
        ),
    )
    parser.add_argument(
        "--force-reanalysis",
        action="store_true",
        help=(
            "Ignora la caché solo para las coincidencias de --claude-match. "
            "Exige también --max-claude para limitar el coste."
        ),
    )
    parser.add_argument(
        "--hold-pilot",
        type=int,
        metavar="N",
        help=(
            "Resuelve una muestra estratificada de hasta 20 casos BDNS "
            "hold_manual con evidencia documental y una llamada focalizada a "
            "Haiku cuando las reglas no bastan. No ejecuta el análisis normal, "
            "no modifica su caché y no genera ni publica JSON."
        ),
    )
    parser.add_argument(
        "--staleness-report",
        action="store_true",
        help=(
            "Informa de cuantas convocatorias esperan analisis y desde cuando, "
            "leyendo solo la auditoria. Sin red, sin coste y sin recopilar."
        ),
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="FUENTE",
        choices=sorted(SOURCE_ALIASES),
        help=(
            "Recopila solo la fuente indicada, en vez de las ocho. Puede "
            "repetirse. Exige --no-claude: un recuento parcial no puede "
            "alimentar el producto. Alias admitidos: "
            + ", ".join(sorted(SOURCE_ALIASES))
        ),
    )
    parser.add_argument(
        "--gap-report",
        action="store_true",
        help=(
            "Cuenta por fuente los campos que faltan en lo ya analizado, "
            "leyendo el JSON publicado y la cache de analisis. Sin red, sin "
            "coste y sin recopilar. Es la forma de comprobar una prueba "
            "--max-claude sin volver a pagarla."
        ),
    )
    parser.add_argument(
        "--replay-hold-report",
        action="store_true",
        help=(
            "Reprocesa el informe hold existente con las reglas actuales, "
            "sin Claude, sin caché principal y sin generar ni publicar JSON."
        ),
    )
    args = parser.parse_args()
    if args.max_claude is not None and args.max_claude < 1:
        parser.error("--max-claude debe ser un entero mayor o igual que 1")
    if args.hold_pilot is not None and not 1 <= args.hold_pilot <= BDNS_HOLD_PILOT_MAX:
        parser.error(
            f"--hold-pilot debe estar entre 1 y {BDNS_HOLD_PILOT_MAX}"
        )
    if args.no_claude and args.max_claude is not None:
        parser.error("--no-claude y --max-claude no pueden utilizarse juntos")
    if args.hold_pilot is not None and (
        args.no_claude or args.max_claude is not None
        or args.claude_match or args.force_reanalysis
    ):
        parser.error(
            "--hold-pilot no puede combinarse con --no-claude, --max-claude, "
            "--claude-match ni --force-reanalysis"
        )
    if args.replay_hold_report and (
        args.no_claude or args.max_claude is not None or args.hold_pilot is not None
        or args.claude_match or args.force_reanalysis
    ):
        parser.error(
            "--replay-hold-report no puede combinarse con otros modos de ejecución"
        )
    if args.staleness_report and (
        args.no_claude or args.max_claude is not None or args.hold_pilot is not None
        or args.replay_hold_report or args.claude_match or args.force_reanalysis
        or args.gap_report
    ):
        parser.error(
            "--staleness-report no puede combinarse con otros modos de ejecución"
        )
    if args.gap_report and (
        args.no_claude or args.max_claude is not None or args.hold_pilot is not None
        or args.replay_hold_report or args.claude_match or args.force_reanalysis
    ):
        parser.error(
            "--gap-report no puede combinarse con otros modos de ejecución"
        )
    if args.source and not args.no_claude:
        # Deliberadamente estricto. Una selección parcial produce un catálogo
        # incompleto, y dejarla llegar al análisis publicaría un producto al
        # que le faltan fuentes enteras sin que nada lo advierta.
        parser.error(
            "--source exige --no-claude: una recopilación parcial no puede "
            "generar ni publicar el producto"
        )
    if args.claude_match and args.max_claude is None:
        parser.error("--claude-match requiere utilizar también --max-claude")
    if any(not value.strip() for value in args.claude_match):
        parser.error("--claude-match no admite textos vacíos")
    if args.force_reanalysis and args.max_claude is None:
        parser.error("--force-reanalysis requiere utilizar --max-claude")
    if args.force_reanalysis and not args.claude_match:
        parser.error(
            "--force-reanalysis requiere al menos un --claude-match"
        )
    return args


def build_gap_reports() -> list:
    """
    Reúne los dos orígenes que este informe compara: lo publicado y lo pagado.

    Se leen aquí, y no dentro de `grant_radar/gap_report.py`, por la misma
    razón que la caché recibe su ruta como parámetro: el cálculo de rutas se
    hace una sola vez, en el script, para no arriesgar leer de otro sitio.
    Los dos archivos son opcionales; si falta alguno, su informe sale vacío en
    vez de romper.
    """
    informes = []
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            producto = json.load(f)
    except Exception:
        producto = {}
    informes.append(build_gap_report(
        gap_records_from_product(producto),
        origin="Producto publicado (convocatorias.json)",
        label=(
            f"generado {str(producto.get('generated_at', ''))[:16].replace('T', ' ')}"
            if producto.get("generated_at") else "sin JSON publicado"
        ),
    ))
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache_payload = json.load(f)
    except Exception:
        cache_payload = {}
    estado_versiones = cache_version_state(cache_payload)
    informes.append(build_gap_report(
        gap_records_from_cache(cache_payload),
        origin="Caché de análisis (lo pagado, publicado o no)",
        label=(
            f"guardada {estado_versiones.get('saved_at', '')[:16].replace('T', ' ')}"
            if estado_versiones.get("saved_at") else "sin caché en disco"
        ),
        version_state=estado_versiones,
    ))
    return informes


if __name__ == "__main__":
    args = parse_args()
    if args.gap_report:
        reports = build_gap_reports()
        print(format_gap_report(reports, datetime.now().date().isoformat()))
        print()
        print(format_budget_watch(reports))
        print("\n  No se llamó a Claude ni se tocó la red: solo se leyeron archivos.")
        sys.exit(0)
    if args.staleness_report:
        print(format_staleness_report(
            build_staleness_report(load_audit_runs(AUDIT_FILE))
        ))
        sys.exit(0)
    if args.replay_hold_report:
        print("Grant-Radar — repetición determinista del piloto BDNS")
        replay_report = replay_bdns_hold_report(
            deterministic_prefilter, _bdns_intrinsic_exclusion
        )
        print(
            "  Resultados: "
            + ", ".join(
                f"{key}={value}" for key, value in sorted(replay_report["counts"].items())
            )
        )
        print(
            f"  Llamadas históricas evitables: "
            f"{replay_report['avoidable_historical_calls']} · "
            f"tokens: {replay_report['avoidable_historical_tokens']:,}"
        )
        print(f"  Informe: {BDNS_HOLD_REPLAY_FILE}")
        print("  No se llamó a Claude ni se modificó la caché principal o el JSON.")
    else:
        run_pipeline(
            no_claude=args.no_claude,
            max_claude=args.max_claude,
            claude_matches=args.claude_match,
            force_reanalysis=args.force_reanalysis,
            hold_pilot=args.hold_pilot,
            sources=[
                nombre
                for alias in args.source
                for nombre in SOURCE_ALIASES[alias]
            ],
        )
