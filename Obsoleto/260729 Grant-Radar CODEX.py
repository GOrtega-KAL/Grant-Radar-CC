# ╔══════════════════════════════════════════════════════════════════╗
# ║  Grant-Radar — Backend Kalfrisa · Windows local                 ║
# ║  APIs oficiales + Chromium para fuentes web                    ║
# ╚══════════════════════════════════════════════════════════════════╝


# ─────────────────────────────────────────────────────────────────────
# CELDA 1 — INSTALACIÓN Y EJECUCIÓN EN WINDOWS LOCAL
# ─────────────────────────────────────────────────────────────────────
# Preparación inicial desde PowerShell:
# cd C:\Users\guillermo.ortega\Desktop\Guillermo\Grant-Radar
# poetry config virtualenvs.in-project true
# poetry add requests beautifulsoup4 anthropic playwright
# poetry run playwright install chromium
# poetry run python "Grant-Radar-prueba.py"
# poetry run python "Grant-Radar-prueba.py" --no-claude


# ─────────────────────────────────────────────────────────────────────
# CELDA 2 — IMPORTS, CREDENCIALES Y CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────

import os
import sys
import argparse
import calendar
import hashlib
import json
import time
import logging
import re
import unicodedata
from datetime import datetime, timezone
from collections import Counter
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import anthropic
from playwright.sync_api import BrowserContext, TimeoutError as PlaywrightTimeoutError, sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── TU API KEY DE CLAUDE (Anthropic) ─────────────────────────────────
# Generar, renovar o revocar: https://console.anthropic.com/settings/keys
CLAUDE_API_KEY = "placeholder"

# ── PUBLICACIÓN EN GITHUB PAGES ──────────────────────────────────────
# Generar, renovar o revocar el token: https://github.com/settings/tokens
# El token necesita permiso de escritura sobre el contenido del repositorio.
GITHUB_TOKEN = "placeholder"

GITHUB_USER = "GOrtega-KAL"
GITHUB_REPO = "Grant-Radar"
GITHUB_BRANCH = "main"

# ── MODELO Y PARÁMETROS ───────────────────────────────────────────────
CLAUDE_MODEL   = "claude-haiku-4-5"        # Haiku 4.5 — $1/$5 por millón de tokens
CLAUDE_SLEEP_S = 1                         # 1s entre llamadas (Claude no tiene RPM estricto)
# Incrementar esta versión cuando cambie el criterio o el prompt de análisis.
# El cambio invalida de forma intencionada los análisis anteriores.
ANALYSIS_PROMPT_VERSION = "2026-07-v1"
CACHE_SCHEMA_VERSION = 2

# ── RUTAS DE ARCHIVOS (Windows local) ────────────────────────────────
# El dashboard local y GitHub Pages consumen el mismo JSON junto a index.html.
# La caché interna, que no debe publicarse, permanece en grant_radar_data.
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_DIR, "grant_radar_data")
os.makedirs(DATA_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(PROJECT_DIR, "convocatorias.json")
CACHE_FILE = os.path.join(DATA_DIR, "grant_radar_cache.json")
AUDIT_FILE = os.path.join(DATA_DIR, "grant_radar_audit.json")
AUDIT_SCHEMA_VERSION = 1
AUDIT_MAX_RUNS = 365

# ── PERFIL DE KALFRISA (contexto para el análisis IA) ─────────────────
KALFRISA_PROFILE = """
Kalfrisa es una empresa industrial española con 60 años de experiencia, con sede en Zaragoza (Aragón).
El Centro de Diseño y Validación de Tecnologías Limpias de Kalfrisa Se especializa en soluciones de eficiencia energética y tratamiento de emisiones para
hornos industriales, con objetivos de descarbonización e hidrógeno como combustible.
CNAE principal: 2829 (fabricación de maquinaria industrial) y 7112 (ingeniería/consultoría técnica).

TECNOLOGÍAS CORE:
- Recuperación de calor residual en hornos industriales de alta temperatura (>400°C)
- Postcombustión térmica y catalítica para tratamiento de COVs, NOx y partículas
- Quemadores industriales H2-ready (mezclas H2/gas natural hasta 100% hidrógeno)
- Sistemas de control de emisiones: SCR, filtros de mangas, oxidación catalítica
- Monitorización y digitalización de procesos térmicos industriales (IIoT)

SECTORES CLIENTE PRINCIPALES:
- Industria cerámica (hornos túnel y discontinuos, temperaturas 900-1200°C)
- Industria siderúrgica y metalúrgica (tratamiento térmico, forja)
- Industria química y petroquímica (procesos con COVs y emisiones complejas)
- Industria del vidrio y refractarios

CAPACIDAD I+D:
- TRL habitual en proyectos: 4-7 (validación en entorno relevante a demo industrial)
- Experiencia en consorcios con centros tecnológicos (ITAINNOVA, CIRCE) y universidades (Unizar)
- Financiación previa: CDTI, IDAE, convocatorias autonómicas aragonesas

CRITERIOS DE EXCLUSIÓN ABSOLUTA:
- Eficiencia energética en edificios residenciales o sector terciario
- Transporte terrestre, aéreo o marítimo
- Energías renovables de generación eléctrica (solar FV, eólica) sin componente industrial térmico
- Agricultura, acuicultura, sector sanitario o educativo
- Tecnologías digitales/software sin aplicación directa a procesos térmicos industriales
"""

# ── KEYWORDS DE FILTRADO ──────────────────────────────────────────────
KEYWORDS = [
    "hidrógeno", "hydrogen", "eficiencia energética", "energy efficiency",
    "descarbonización", "decarbonisation", "decarbonization",
    "hornos industriales", "industrial furnaces", "emisiones industriales",
    "industrial emissions", "combustión limpia", "clean combustion",
    "calor residual", "waste heat", "NOx", "transición energética",
    "economía baja en carbono", "net zero", "industria 4.0",
    "eficiencia térmica", "thermal efficiency"
]

# ── LOGGING ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("grant_radar")
SOURCE_RUNTIME_METADATA = {}
DISCOVERY_AUDIT = []
IDENTITY_LANDINGS = []

print(f"✓ Ejecución local Windows — proyecto: {PROJECT_DIR}")
print(f"✓ Caché local: {CACHE_FILE}")
print(f"✓ JSON del dashboard: {OUTPUT_FILE}")
print(f"✓ Auditoría de descartes: {AUDIT_FILE}")
print("✓ Configuración cargada correctamente")


# ─────────────────────────────────────────────────────────────────────
# CELDA 3 — FUNCIONES AUXILIARES
# ─────────────────────────────────────────────────────────────────────

def keyword_match(text: str) -> list:
    """Devuelve las keywords encontradas en el texto."""
    text_lower = text.lower()
    return [kw for kw in KEYWORDS if kw.lower() in text_lower]

def is_relevant(text: str, min_matches: int = 1) -> bool:
    return len(keyword_match(text)) >= min_matches


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


def save_discovery_audit(
    run_started_at: str,
    status: str,
    source_counts: dict | None = None,
) -> None:
    """Añade una ejecución al histórico local de descartes."""
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
        "excluded": clean_entries,
    }

    history = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "description": (
            "Histórico local de oportunidades descubiertas pero excluidas "
            "antes o después del análisis."
        ),
        "runs": [],
    }
    if os.path.exists(AUDIT_FILE):
        try:
            with open(AUDIT_FILE, "r", encoding="utf-8") as audit_handle:
                loaded = json.load(audit_handle)
            if (
                isinstance(loaded, dict)
                and loaded.get("schema_version") == AUDIT_SCHEMA_VERSION
                and isinstance(loaded.get("runs"), list)
            ):
                history = loaded
        except (OSError, json.JSONDecodeError) as exc:
            log.warning(f"No se pudo leer la auditoría anterior; se recreará: {exc}")

    history["runs"].append(run_record)
    history["runs"] = history["runs"][-AUDIT_MAX_RUNS:]
    with open(AUDIT_FILE, "w", encoding="utf-8") as audit_handle:
        json.dump(history, audit_handle, ensure_ascii=False, indent=2)
    log.info(
        f"Auditoría guardada: {len(clean_entries)} exclusiones en {AUDIT_FILE}"
    )

class PlaywrightBrowser:
    """Una única sesión Chromium compartida por todas las fuentes web."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self.context: BrowserContext | None = None
        self._blocked_scopes = set()

    def __enter__(self):
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self.context = self._browser.new_context(
                locale="es-ES",
                timezone_id="Europe/Madrid",
                viewport={"width": 1440, "height": 1000},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                ignore_https_errors=True,
            )
            self.context.set_default_timeout(15_000)
            self.context.set_default_navigation_timeout(30_000)
            log.info("Chromium iniciado para las fuentes sin API")
        except Exception as exc:
            log.error(f"No se pudo iniciar Chromium; se usarán los respaldos disponibles: {exc}")
            if self._playwright:
                self._playwright.stop()
            self._playwright = None
            self._browser = None
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.context:
            self.context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self.context = None

    def html(self, url: str, wait_selector: str = "body") -> str:
        """Navega, espera al DOM renderizado y devuelve su HTML."""
        if not self.context:
            return ""
        parsed_url = urlparse(url)
        host = parsed_url.netloc.casefold()
        path = parsed_url.path.casefold().rstrip("/")
        block_scope = host
        if host.endswith("idae.es"):
            block_scope = (
                f"{host}:grant-details"
                if path.startswith("/ayudas-y-financiacion/")
                else ""
            )
        if block_scope and block_scope in self._blocked_scopes:
            return ""

        page = self.context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded")
            if response and response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}")
            # Para extraer HTML basta con que el nodo exista. Algunas vistas de
            # impresión mantienen body/html ocultos aunque el DOM esté completo.
            page.wait_for_selector(wait_selector, state="attached")
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except PlaywrightTimeoutError:
                # Varias webs públicas mantienen conexiones de analítica abiertas.
                pass
            html = page.content()
            page_title = page.title().casefold()
            visible_text = page.locator("body").inner_text(timeout=3_000).casefold()
            block_markers = (
                "the url you requested has been blocked",
                "access denied",
                "request rejected",
                "solicitud bloqueada",
            )
            if any(
                marker in page_title or marker in visible_text
                for marker in block_markers
            ):
                if block_scope:
                    self._blocked_scopes.add(block_scope)
                raise RuntimeError("respuesta de bloqueo/WAF")
            return html
        except Exception as exc:
            log.warning(f"Playwright no pudo cargar {url}: {exc}")
            return ""
        finally:
            page.close()

def _days_until(date_str: str) -> int:
    """Convierte una fecha ISO o formato europeo a días restantes."""
    if not date_str:
        return 90
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
        try:
            dt = datetime.strptime(date_str[:10], fmt[:10])
            return max(0, (dt.date() - datetime.now().date()).days)
        except Exception:
            pass
    return 90

def cache_key(conv: dict) -> str:
    """Genera una clave SHA-256 estable y sensible a la versión del análisis."""
    identity = {
        "prompt_version": ANALYSIS_PROMPT_VERSION,
        "source": re.sub(r"\s+", " ", str(conv.get("source", "")).strip().lower()),
        "title": re.sub(r"\s+", " ", str(conv.get("title", "")).strip().lower()),
        "url": str(conv.get("url", "")).strip(),
    }
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_save(cache: dict):
    """Guarda la caché con metadatos de esquema y versión del prompt."""
    payload = {
        "_meta": {
            "schema_version": CACHE_SCHEMA_VERSION,
            "prompt_version": ANALYSIS_PROMPT_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        },
        "entries": cache,
    }
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
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
        isinstance(analysis.get("match_score"), (int, float))
        and analysis.get("priority") in {"high", "medium", "low"}
        and isinstance(analysis.get("resumen"), str)
        and bool(analysis.get("resumen", "").strip())
        and isinstance(analysis.get("accion"), str)
        and isinstance(analysis.get("dimensiones"), list)
    )


def filter_usable_cache(entries: dict) -> dict:
    """Devuelve solo entradas con un análisis utilizable, sin alterar el archivo."""
    usable = {
        key: record
        for key, record in entries.items()
        if isinstance(record, dict)
        and analysis_is_usable(record.get("analysis"))
    }
    ignored = len(entries) - len(usable)
    if ignored:
        log.warning(
            f"Caché: ignorando {ignored} análisis fallidos o incompletos; "
            "se volverán a solicitar a Claude"
        )
    return usable


def cache_load() -> dict:
    """
    Carga la caché. El formato plano antiguo se migra una sola vez a claves
    SHA-256; después, cambiar ANALYSIS_PROMPT_VERSION invalida los análisis.
    """
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}

    if isinstance(payload, dict) and isinstance(payload.get("entries"), dict):
        return filter_usable_cache(payload["entries"])

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
        cache_save(migrated)
        log.info(f"Caché antigua migrada a SHA-256: {len(migrated)} análisis conservados")
    return filter_usable_cache(migrated)

print("✓ Funciones auxiliares cargadas")


# ─────────────────────────────────────────────────────────────────────
# CELDA 4 — FUNCIONES DE CONSULTA DE FUENTES
# ─────────────────────────────────────────────────────────────────────

def _sedia_meta(item: dict, key: str, default="") -> str:
    """
    Extrae un valor del dict metadata de la SEDIA API.
    Los valores son SIEMPRE listas — toma el primer elemento.
    """
    val = item.get("metadata", {}).get(key, default)
    if isinstance(val, list):
        val = val[0] if val else default
    return str(val) if val is not None else str(default)


def _sedia_values(item: dict, key: str) -> list[str]:
    """Devuelve todos los valores de un campo metadata de SEDIA."""
    value = item.get("metadata", {}).get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    return [str(item_value) for item_value in value if item_value not in (None, "")]


# Códigos numéricos de estado en la SEDIA API (validados con Facet API).
_SEDIA_STATUS_OPEN        = "31094502"
_SEDIA_STATUS_FORTHCOMING = "31094501"
_SEDIA_STATUS_CLOSED      = "31094503"
# frameworkProgramme Horizon Europe 2021-2027
_SEDIA_HORIZON_PROGRAMME  = "43108390"

# SEDIA solo busca de forma fiable en algunos campos. Por ello se enumera todo
# el universo Horizon abierto/próximo en inglés y la relevancia se evalúa
# localmente sobre título + descripción. Así no se pierden topics cuyo título
# no contiene las palabras técnicas que sí aparecen en su descripción.
_HORIZON_SEARCH_TEXT = "***"
_HORIZON_PAGE_SIZE = 100
_HORIZON_MAX_PAGES = 30


def fetch_horizon_europe() -> list:
    """
    Horizon Europe — SEDIA Search API (backend oficial del portal F&T de la CE).
    Envía el filtro oficial como JSON multipart y pagina todo el universo
    Horizon abierto/próximo en inglés. SEDIA mantiene algunos estados
    obsoletos, por lo que todas las fechas se vuelven a validar localmente.
    """
    log.info("Consultando Horizon Europe (SEDIA API oficial)...")
    results = []

    endpoint = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
    api_query = {
        "bool": {
            "must": [
                {"terms": {"type": ["1", "2", "8"]}},
                {"terms": {"status": [_SEDIA_STATUS_OPEN, _SEDIA_STATUS_FORTHCOMING]}},
                {"term": {"programmePeriod": "2021 - 2027"}},
                {"terms": {"frameworkProgramme": [_SEDIA_HORIZON_PROGRAMME]}},
                {"term": {"language": "en"}},
            ]
        }
    }
    query_json = json.dumps(api_query, ensure_ascii=False)
    all_docs = []
    raw_seen = set()

    collected = 0
    total_available = 0
    for page in range(1, _HORIZON_MAX_PAGES + 1):
        params = {
            "apiKey": "SEDIA",
            "text": _HORIZON_SEARCH_TEXT,
            "pageNumber": str(page),
            "pageSize": str(_HORIZON_PAGE_SIZE),
            "language": "en",
        }
        try:
            resp = requests.post(
                endpoint,
                params=params,
                files={"query": ("query.json", query_json, "application/json")},
                headers={
                    "Accept": "application/json",
                    "User-Agent": "GrantRadar-Bot/1.0",
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning(f"Horizon SEDIA error (inventario global, p{page}): {e}")
            break

        docs_page = data.get("results", [])
        total_available = int(data.get("totalResults", 0) or 0)
        if not docs_page:
            break

        collected += len(docs_page)
        for item in docs_page:
            identifier = _sedia_meta(item, "identifier")
            raw_key = (
                identifier
                or str(item.get("id", ""))
                or hashlib.sha256(
                    json.dumps(item.get("metadata", {}), sort_keys=True).encode("utf-8")
                ).hexdigest()
            )
            if raw_key in raw_seen:
                audit_exclusion(
                    {
                        "source": "HORIZON EUROPE",
                        "identifier": identifier,
                        "title": _sedia_meta(item, "title"),
                        "url": item.get("url", ""),
                    },
                    "duplicate_record",
                    "sedia_inventory",
                )
                continue
            raw_seen.add(raw_key)
            all_docs.append(item)

        log.info(
            f"  SEDIA inventario p{page}: {len(docs_page)} docs "
            f"({min(collected, total_available)}/{total_available})"
        )
        if collected >= total_available:
            break
        time.sleep(0.2)

    if total_available > collected and collected >= (
        _HORIZON_MAX_PAGES * _HORIZON_PAGE_SIZE
    ):
        log.warning(
            "Horizon SEDIA: inventario truncado por el límite defensivo de páginas "
            f"({collected}/{total_available})"
        )

    if not all_docs:
        log.warning("Horizon SEDIA: sin resultados en las consultas temáticas")
        return []
    log.info(f"  SEDIA: validando {len(all_docs)} documentos únicos...")

    seen = set()
    today = datetime.now().date()
    skipped_expired = 0
    for item in all_docs:
        # ── Filtro 1: solo Horizon Europe 2021-2027 ───────────────────
        programme = _sedia_meta(item, "frameworkProgramme")
        if programme and programme != _SEDIA_HORIZON_PROGRAMME:
            continue  # descarta H2020, TED, otros programas

        # ── Filtro 2: solo convocatorias ABIERTAS o PRÓXIMAS ──────────
        # El status está en metadata["status"] como código numérico string
        status = _sedia_meta(item, "status")
        if status not in (_SEDIA_STATUS_OPEN, _SEDIA_STATUS_FORTHCOMING):
            continue

        # ── Extraer campos desde metadata (todos son listas) ──────────
        title       = _sedia_meta(item, "title") or item.get("summary", "")
        description = _sedia_meta(item, "descriptionByte")
        # descriptionByte contiene HTML — limpiar etiquetas
        if description and "<" in description:
            description = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)

        combined = f"{title} {description}"
        if not combined.strip() or combined in seen:
            audit_exclusion(
                {
                    "source": "HORIZON EUROPE",
                    "identifier": _sedia_meta(item, "identifier"),
                    "title": title,
                    "url": item.get("url", ""),
                },
                "empty_or_duplicate_content",
                "local_prefilter",
            )
            continue

        # ── Filtro 3: relevancia por keywords ─────────────────────────
        if not is_relevant(combined):
            audit_exclusion(
                {
                    "source": "HORIZON EUROPE",
                    "identifier": _sedia_meta(item, "identifier"),
                    "title": title,
                    "url": item.get("url", ""),
                    "deadline_date": (
                        _sedia_values(item, "deadlineDate")[0][:10]
                        if _sedia_values(item, "deadlineDate")
                        else ""
                    ),
                },
                "not_relevant_local_filter",
                "local_prefilter",
                {"keywords_found": []},
            )
            continue
        seen.add(combined)

        # SEDIA puede mantener status OPEN/FORTHCOMING después del cierre.
        # Se evalúan todas las fechas (incluidas convocatorias en dos etapas)
        # y se toma la próxima fecha futura.
        deadline_values = _sedia_values(item, "deadlineDate")
        future_deadlines = []
        for raw_deadline in deadline_values:
            try:
                deadline_date = datetime.strptime(raw_deadline[:10], "%Y-%m-%d").date()
            except (TypeError, ValueError):
                continue
            if deadline_date > today:
                future_deadlines.append((deadline_date, raw_deadline))

        if deadline_values and not future_deadlines:
            skipped_expired += 1
            audit_exclusion(
                {
                    "source": "HORIZON EUROPE",
                    "identifier": _sedia_meta(item, "identifier"),
                    "title": title,
                    "url": item.get("url", ""),
                    "deadline_date": str(deadline_values[-1])[:10],
                },
                "deadline_closed",
                "deadline_validation",
                {"all_deadlines": [str(value)[:10] for value in deadline_values]},
            )
            continue

        if future_deadlines:
            deadline_date_value, deadline_raw = min(future_deadlines, key=lambda value: value[0])
            deadline_days = (deadline_date_value - today).days
            fecha_sin_confirmar = False
        else:
            # Convocatoria abierta/próxima sin fecha publicada.
            deadline_raw = ""
            deadline_days = 90
            fecha_sin_confirmar = True

        # startDate: fecha de apertura oficial de la convocatoria (campo SEDIA confirmado)
        open_raw  = _sedia_meta(item, "startDate")
        open_date = open_raw[:10] if open_raw else ""
        identifier    = _sedia_meta(item, "identifier") or item.get("reference", "")

        # Budget: dentro de budgetOverview (JSON string anidado)
        budget_raw = _sedia_meta(item, "budgetOverview")
        budget_str = "Ver convocatoria"
        if budget_raw and budget_raw != "{}":
            try:
                bo = json.loads(budget_raw)
                years = bo.get("budgetYearsColumns", [])
                budget_str = f"Presupuesto {'/'.join(years)}" if years else "Ver convocatoria"
            except Exception:
                pass

        results.append({
            "source":               "HORIZON EUROPE",
            "title":                title[:200],
            "description":          description[:800],
            "deadline_days":        deadline_days,
            "deadline_date":        deadline_raw[:10] if deadline_raw else "",
            "open_date":            open_date,
            "fecha_sin_confirmar":  fecha_sin_confirmar,
            "budget":               budget_str,
            "url":                  (item.get("url") or
                                    f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{identifier}"),
            "keywords_found":       keyword_match(combined),
            "org":                  "Comisión Europea / Horizon Europe",
            "source_type":          "SEDIA API",
            "_call_year":           (
                re.search(r"(?:^|-)(20\d{2})(?:-|$)", str(identifier)).group(1)
                if re.search(r"(?:^|-)(20\d{2})(?:-|$)", str(identifier))
                else (deadline_raw[:4] if deadline_raw else "")
            ),
        })

    # Algunos topics anuales comparten exactamente el mismo título. Se añade
    # el año solo cuando es necesario para diferenciarlos en el dashboard.
    title_counts = Counter(
        result["title"].strip().casefold() for result in results
    )
    for result in results:
        title_key = result["title"].strip().casefold()
        call_year = result.pop("_call_year", "")
        if (
            title_counts[title_key] > 1
            and call_year
            and not re.search(rf"\b{re.escape(call_year)}\b", result["title"])
        ):
            result["title"] = f"{result['title']} — {call_year}"

    log.info(
        f"  → {len(results)} convocatorias Horizon vigentes relevantes "
        f"({skipped_expired} estados obsoletos descartados por fecha)"
    )
    SOURCE_RUNTIME_METADATA["HORIZON EUROPE"] = {
        "inventory_total": total_available,
        "inventory_unique": len(all_docs),
        "relevant_active": len(results),
        "status": "ok" if collected >= total_available else "warn",
        "strategy": "inventario global Horizon en inglés + filtro local",
    }
    return results


def _fetch_horizon_rss_fallback() -> list:
    """
    Diagnóstico confirmó que los RSS del portal F&T devuelven bozo=1 (feed inválido).
    Se mantiene la función por compatibilidad pero devuelve lista vacía.
    Cuando hay convocatorias HE abiertas, la SEDIA API las encuentra con paginación.
    """
    log.warning("Horizon Europe: RSS no disponible (bozo=1 confirmado). "
                "Si SEDIA API falla, no hay fallback funcional.")
    return []


def _date_to_iso(raw: str) -> str:
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip()[:10], fmt).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            pass
    return ""


def _extract_date_range(text: str) -> tuple[str, str]:
    """Extrae apertura y cierre de texto renderizado, sin asumir un HTML concreto."""
    date_pattern = r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})"
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
    date_pattern = r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})"
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

    open_match = re.search(
        r"\b(?:fecha\s+de\s+)?(?:inicio|apertura)\b"
        r"[^.\n]{0,240}?" + date_pattern,
        folded,
        re.IGNORECASE,
    )
    close_match = re.search(
        r"\b(?:fecha\s+de\s+)?(?:finalizacion|cierre|fin)\b"
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
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("/"):
        return base.rstrip("/") + href
    return base.rstrip("/") + "/" + href


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


def _parse_cdti_calendar_date(
    raw: str,
    default_year: int,
    month_end: bool = False,
) -> tuple[str, bool]:
    """
    Convierte fechas del calendario CDTI a ISO.

    Devuelve (fecha_iso, es_estimada). Cuando CDTI solo publica el mes,
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


def _bdns_cdti_convocatorias() -> list:
    """
    BDNS (Base de Datos Nacional de Subvenciones) — portal oficial del Ministerio de Hacienda.
    URL: https://www.infosubvenciones.es

    IMPORTANTE — arquitectura real de la BDNS (verificada):
    La BDNS NO tiene una API REST stateless. Funciona con sesión de servidor:
      1. POST al buscador para establecer los criterios de filtro en sesión (cookie)
      2. GET a /bdnstrans/GE/es/convocatorias con params nd (timestamp) y rows
         → devuelve JSON con la propiedad "rows" (lista de convocatorias)

    Los parámetros de filtro (órgano, estado) viajan en el POST inicial,
    no en la URL de la petición de datos.

    Campos relevantes en cada fila JSON:
      numConvocatoria, descripcion, organo, fechaInicioSolicitud,
      fechaFinSolicitud, importe, urlBdns (o id para construirla)
    """
    results = []
    session = requests.Session()
    base    = "https://www.infosubvenciones.es"
    headers = {
        "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":       "application/json, text/javascript, */*; q=0.01",
        "Referer":      f"{base}/bdnstrans/GE/es/convocatorias",
        "X-Requested-With": "XMLHttpRequest",
    }

    try:
        # ── Paso 1: POST para establecer filtros en sesión ────────────
        # Filtrar por órgano "CDTI" (texto) y estado abierta
        post_data = {
            "tipoBusqueda":          "convocatorias",
            "descOrgano":            "CDTI",
            "estadoConvocatoria":    "ABIERTA",
            "vrb_accion":            "buscar",
        }
        r_post = session.post(
            f"{base}/bdnstrans/GE/es/convocatorias",
            data=post_data,
            headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        log.debug(f"  BDNS POST status: {r_post.status_code}, cookies: {dict(session.cookies)}")

        # ── Paso 2: GET de resultados JSON con la cookie de sesión ────
        import time as _time
        params_get = {
            "nd":   str(int(_time.time() * 1000)),  # timestamp milisegundos
            "rows": "100",
            "page": "1",
            "sidx": "fechaFinSolicitud",
            "sord": "asc",
        }
        r_get = session.get(
            f"{base}/bdnstrans/GE/es/convocatorias",
            params=params_get,
            headers=headers,
            timeout=30,
        )
        r_get.raise_for_status()

        # La respuesta puede ser HTML si la sesión no se estableció correctamente
        content_type = r_get.headers.get("content-type", "")
        if "html" in content_type or not r_get.text.strip().startswith("{"):
            log.warning(f"  BDNS: respuesta no-JSON (content-type={content_type}). "
                        f"Preview: {r_get.text[:200]}")
            return results

        data = r_get.json()

    except Exception as e:
        log.warning(f"  BDNS error: {e}")
        return results

    rows = data.get("rows", [])
    log.info(f"  BDNS: {len(rows)} filas recibidas (total={data.get('records','?')})")

    for item in rows:
        # La BDNS devuelve los campos en "cell" (array) o directamente como dict
        if isinstance(item, dict) and "cell" in item:
            cell = item["cell"]
            # Orden típico: id, numConvocatoria, organo, descripcion,
            #               fechaInicioSolicitud, fechaFinSolicitud, importe
            try:
                title      = str(cell[3]).strip() if len(cell) > 3 else ""
                open_raw   = str(cell[4]) if len(cell) > 4 else ""
                close_raw  = str(cell[5]) if len(cell) > 5 else ""
                importe    = cell[6] if len(cell) > 6 else None
                id_conv    = str(cell[0]) if cell else ""
            except (IndexError, TypeError):
                continue
        elif isinstance(item, dict):
            title     = item.get("descripcion", item.get("titulo", "")).strip()
            open_raw  = item.get("fechaInicioSolicitud", "")
            close_raw = item.get("fechaFinSolicitud", "")
            importe   = item.get("importe")
            id_conv   = str(item.get("id", item.get("numConvocatoria", "")))
        else:
            continue

        if not title or not _es_titulo_valido(title):
            continue
        if not is_relevant(title):
            continue

        # Parsear fechas
        def _parse_date(raw):
            if not raw or str(raw).strip() in ("", "null", "None"):
                return ""
            for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]:
                try:
                    return datetime.strptime(str(raw).strip()[:10], fmt).strftime("%Y-%m-%d")
                except Exception:
                    pass
            return ""

        open_date  = _parse_date(open_raw)
        close_date = _parse_date(close_raw)

        deadline_days = _days_until(close_date) if close_date else 90
        if deadline_days <= 0:
            continue

        budget   = f"€{float(importe):,.0f}".replace(",", ".") if importe else "Ver convocatoria"
        url_bdns = f"{base}/bdnstrans/GE/es/convocatorias/{id_conv}" if id_conv else f"{base}/bdnstrans/GE/es/convocatorias"

        results.append({
            "source":              "CDTI",
            "title":               title[:200],
            "description":         "",
            "deadline_days":       deadline_days,
            "deadline_date":       close_date,
            "open_date":           open_date,
            "fecha_sin_confirmar": not bool(close_date),
            "budget":              budget,
            "url":                 url_bdns,
            "keywords_found":      keyword_match(title),
            "org":                 "CDTI — Centro para el Desarrollo Tecnológico Industrial",
            "source_type":         "BDNS API",
        })

    log.info(f"  BDNS: {len(results)} convocatorias CDTI abiertas relevantes")
    return results


def _fetch_cdti_static() -> list:
    """
    CDTI — catálogo curado complementario.

    El calendario oficial se extrae automáticamente con Playwright. Este catálogo
    conserva programas permanentes, contexto técnico y excepciones que no figuran
    en la tabla anual. Sus fechas nunca sustituyen datos oficiales más recientes.
    """
    log.info("CDTI: cargando catálogo curado complementario...")

    # ── Catálogo estático de convocatorias CDTI relevantes para Kalfrisa ──
    # ESTADO: ★ = abierta confirmada | ◷ = fecha prevista (sujeta a PGE y disponibilidad)
    # Fuente: https://www.cdti.es/calendario-de-convocatorias (versión 7 abril 2026)
    #         URLs facilitadas directamente desde la web del CDTI
    # Última revisión: 2026-04-10
    _STATIC = [
        # ── VENTANILLA PERMANENTE ─────────────────────────────────────────────
        {
            "title":         "Proyectos de I+D — Línea PID (ventanilla abierta)",
            "description":   "Financiación de proyectos empresariales de investigación industrial y "
                             "desarrollo experimental para la creación o mejora significativa de "
                             "procesos productivos, productos o servicios. Presupuesto mínimo 175.000 €. "
                             "Ayuda parcialmente reembolsable hasta el 85% con tramo no reembolsable "
                             "del 10-33%. Modalidad individual, cooperación nacional e internacional. "
                             "Aplica directamente a proyectos de eficiencia térmica, control de "
                             "emisiones y combustión industrial H2-ready de Kalfrisa.",
            "open_date":     "",
            "deadline_date": "",
            "deadline_note": "ventanilla_permanente",
            "budget":        "Hasta 85% del presupuesto (mín. 175.000 €)",
            "url":           "https://www.cdti.es/ayudas/proyectos-de-i-d",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "eficiencia térmica", "descarbonización",
                              "calor residual", "emisiones industriales"],
        },
        {
            "title":         "Proyectos Transferencia Tecnológica Cervera (ventanilla abierta)",
            "description":   "Proyectos de I+D empresarial en colaboración obligatoria con Centros "
                             "Tecnológicos acreditados. Área prioritaria 'Transición Energética' "
                             "incluida. Subcontratación mínima 10% al Centro Tecnológico. Tramo "
                             "no reembolsable fijo del 33%. Máximo encaje para Kalfrisa dada su "
                             "relación con ITAINNOVA y CIRCE en Aragón.",
            "open_date":     "",
            "deadline_date": "",
            "deadline_note": "ventanilla_permanente",
            "budget":        "Hasta 85% · 33% no reembolsable (mín. 175.000 €)",
            "url":           "https://www.cdti.es/ayudas/proyectos-cervera",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "calor residual", "descarbonización",
                              "hidrógeno", "eficiencia térmica"],
        },
        {
            "title":         "Infraestructuras de Ensayo y Experimentación CDTI (ventanilla abierta)",
            "description":   "Ayudas para el desarrollo o mejora de infraestructuras de ensayo, "
                             "caracterización y demostración tecnológica en empresas. Abierto desde "
                             "16 de marzo de 2026 de forma permanente a través de la sede electrónica "
                             "del CDTI. Interesante para laboratorios de validación de quemadores "
                             "H2-ready y sistemas de medición de emisiones de Kalfrisa.",
            "open_date":     "2026-03-16",
            "deadline_date": "",
            "deadline_note": "ventanilla_permanente",
            "budget":        "Ver convocatoria",
            "url":           "https://www.cdti.es/ayudas/infraestructuras-ensayo-experimentacion",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "eficiencia térmica", "hidrógeno",
                              "emisiones industriales"],
        },
        # ── ABIERTAS CONFIRMADAS ──────────────────────────────────────────────
        {
            "title":         "PRIMA 2026 — Proyectos I+D ámbito mediterráneo",
            "description":   "Programa internacional de I+D para países del Mediterráneo. Convocatoria "
                             "abierta desde 20 marzo 2026. Cierre PRIMA: 15 mayo 2026. Requiere "
                             "consorcio de al menos 4 socios de 3 países. Presupuesto: 32,5M€ "
                             "(Sección 1, UE) + 36,1M€ (Sección 2, países). Las empresas españolas "
                             "deben presentar también solicitud PRI en sede CDTI antes del 15 mayo.",
            "open_date":     "2026-03-20",
            "deadline_date": "2026-05-15",
            "deadline_note": "★ abierta",
            "budget":        "32,5M€ Sec.1 + 36,1M€ Sec.2",
            "url":           "https://www.cdti.es/ayudas/prima",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "descarbonización", "hidrógeno",
                              "eficiencia térmica"],
        },
        {
            "title":         "Neotec 2026 — Empresas innovadoras de base tecnológica",
            "description":   "Subvenciones a fondo perdido para startups y pequeñas empresas "
                             "innovadoras de base tecnológica con antigüedad máxima de 3 años. "
                             "Presupuesto 20,38M€. Financiación hasta el 70% (o 85% con contratación "
                             "de doctor). Máximo 250.000 € (o 325.000 €). Relevante si Kalfrisa "
                             "tiene spin-offs tecnológicos con menos de 3 años de vida o vinculados "
                             "a tecnologías de combustión H2-ready o control de emisiones.",
            "open_date":     "2026-04-14",
            "deadline_date": "2026-05-14",
            "deadline_note": "★ abierta",
            "budget":        "Hasta 325.000 € por empresa · subvención a fondo perdido",
            "url":           "https://www.cdti.es/ayudas/neotec-2026",
            "url_generica":  False,
            "keywords":      ["eficiencia energética", "hidrógeno", "descarbonización",
                              "eficiencia térmica"],
        },
        {
            "title":         "Proyectos Bilaterales CDTI — 13ª convocatoria (todo 2026)",
            "description":   "Financiación de proyectos bilaterales de I+D en cooperación con socios "
                             "internacionales, con certificación y seguimiento unilateral CDTI. "
                             "Convocatoria permanente durante todo 2026 con dos fechas de corte. "
                             "Instrumento para proyectos de combustión industrial y eficiencia "
                             "térmica con partners europeos.",
            "open_date":     "2026-01-01",
            "deadline_date": "2026-12-31",
            "deadline_note": "★ abierta (dos fechas de corte)",
            "budget":        "Ver convocatoria · ayuda parcialmente reembolsable",
            "url":           "https://www.cdti.es/ayudas/proyectos-bilaterales",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "eficiencia térmica", "calor residual",
                              "descarbonización"],
        },
        # ── FECHAS PREVISTAS ─────────────────────────────────────────────────
        {
            "title":         "Sello de Excelencia + FEDER 2026",
            "description":   "Financiación nacional para proyectos que hayan obtenido el Sello de "
                             "Excelencia en convocatorias europeas competitivas (Horizon Europe EIC). "
                             "Subvención FEDER complementaria a la evaluación europea ya superada. "
                             "Apertura prevista abril 2026, cierre mayo 2026 según calendario CDTI.",
            "open_date":     "2026-04-01",
            "deadline_date": "2026-05-31",
            "deadline_note": "◷ fecha prevista",
            "budget":        "Ver convocatoria · subvención FEDER",
            "url":           "https://www.cdti.es/ayudas/sello-de-excelencia",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "descarbonización", "hidrógeno",
                              "eficiencia térmica"],
        },
        {
            "title":         "Misiones Ciencia e Innovación 2026",
            "description":   "Proyectos cooperativos de I+D de gran envergadura articulados en "
                             "consorcios empresariales, orientados a retos incluyendo transición "
                             "energética y descarbonización industrial. Presupuesto mínimo 3,5M€ "
                             "por proyecto. Apertura prevista mayo 2026, cierre junio 2026. "
                             "Kalfrisa puede participar como socio tecnológico en consorcios del "
                             "sector cerámico, siderúrgico o químico.",
            "open_date":     "2026-05-01",
            "deadline_date": "2026-06-30",
            "deadline_note": "◷ fecha prevista",
            "budget":        "~140M€ total (subvención FEDER) · mín. 3,5M€ por proyecto",
            "url":           "https://www.cdti.es/ayudas/misiones-ciencia-e-innovacion-2026",
            "url_generica":  False,
            "keywords":      ["descarbonización", "eficiencia energética", "hidrógeno",
                              "emisiones industriales", "transición energética"],
        },
        {
            "title":         "Cervera Centros 2026 — I+D con centros tecnológicos (prevista)",
            "description":   "Convocatoria competitiva anual de Proyectos Cervera para empresas "
                             "en colaboración con Centros Tecnológicos acreditados en áreas "
                             "tecnológicas prioritarias incluyendo 'Transición Energética'. "
                             "Apertura prevista mayo 2026, cierre junio 2026 según calendario CDTI. "
                             "Kalfrisa + ITAINNOVA/CIRCE son la combinación natural para esta línea.",
            "open_date":     "2026-05-01",
            "deadline_date": "2026-06-30",
            "deadline_note": "◷ fecha prevista",
            "budget":        "Ver convocatoria · 33% no reembolsable",
            "url":           "https://www.cdti.es/ayudas/proyectos-cervera",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "calor residual", "descarbonización",
                              "hidrógeno", "eficiencia térmica"],
        },
        {
            "title":         "CIIP Eurostars CoD10 2026 — Cooperación I+D internacional Eureka",
            "description":   "Instrumento nacional CDTI para financiar participación española en "
                             "proyectos aprobados en Eurostars-3 (red Eureka). Evaluación internacional "
                             "previa. 10ª fecha de corte prevista julio 2026. Dirigido a pymes "
                             "con proyectos colaborativos de I+D con socios de países Eureka.",
            "open_date":     "2026-07-01",
            "deadline_date": "2026-07-31",
            "deadline_note": "◷ fecha prevista",
            "budget":        "Ver convocatoria · subvención",
            "url":           "https://www.cdti.es/ayudas/eurostars",
            "url_generica":  True,
            "keywords":      ["eficiencia energética", "descarbonización", "eficiencia térmica",
                              "calor residual"],
        },
        {
            "title":         "Partenariados Pilar 2 SERA 2026 — Segunda llamada",
            "description":   "Instrumento de adjudicación directa CDTI para financiar entidades "
                             "españolas en proyectos internacionales seleccionados en partenariados "
                             "cofinanciados del Pilar 2 de Horizon Europe. Segunda llamada prevista "
                             "julio 2026. El proyecto debe aprobarse primero en el marco europeo.",
            "open_date":     "2026-07-01",
            "deadline_date": "2026-07-31",
            "deadline_note": "◷ fecha prevista",
            "budget":        "Ver convocatoria · adjudicación directa",
            "url":           "https://www.cdti.es/ayudas/partenariados-pilar-2-sera-2026-1",
            "url_generica":  False,
            "keywords":      ["eficiencia energética", "descarbonización", "hidrógeno",
                              "eficiencia térmica"],
        },
    ]

    results = []
    for c in _STATIC:
        # Calcular deadline_days
        if c["deadline_note"] == "ventanilla_permanente":
            deadline_days        = 365
            deadline_date        = ""
            open_date            = ""
            fecha_sin_confirmar  = True
            fecha_prevista       = False
        else:
            close_str   = c.get("deadline_date", "")
            open_str    = c.get("open_date", "")
            deadline_days = _days_until(close_str) if close_str else 180
            if deadline_days <= 0:
                log.debug(f"  CDTI estático: descartando cerrada: {c['title'][:60]}")
                continue
            deadline_date   = close_str
            open_date       = open_str
            es_prevista     = c["deadline_note"].startswith("◷")
            fecha_sin_confirmar = not bool(close_str) or es_prevista
            fecha_prevista  = es_prevista

        kw_found = [k for k in c.get("keywords", []) if k.lower() in " ".join(c["keywords"]).lower()]

        results.append({
            "source":              "CDTI",
            "title":               c["title"],
            "description":         c["description"],
            "deadline_days":       deadline_days,
            "deadline_date":       deadline_date,
            "open_date":           open_date,
            "fecha_sin_confirmar": fecha_sin_confirmar,
            "fecha_prevista":      fecha_prevista,
            "budget":              c["budget"],
            "url":                 c["url"],
            "url_generica":        c.get("url_generica", False),
            "keywords_found":      c["keywords"],
            "org":                 "CDTI — Centro para el Desarrollo Tecnológico Industrial",
            "source_type":         "Catálogo curado",
        })

    log.info(f"  → {len(results)} convocatorias CDTI vigentes en catálogo curado")
    return results


def _fetch_cdti_playwright(browser: PlaywrightBrowser) -> list:
    """Obtiene convocatorias desde el calendario y las fichas renderizadas de CDTI."""
    base = "https://www.cdti.es"
    calendar_url = f"{base}/calendario-de-convocatorias"
    html = browser.html(calendar_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    candidates = {}
    programme_terms = re.compile(
        r"(proyectos?(?: de)? i\+d|misiones|cervera|neotec|eurostars|prima|"
        r"infraestructuras? de ensayo|bilaterales|sello de excelencia|"
        r"partenariados?|sera\b|innterconecta|innoglobal|ecosistemas de innovaci[oó]n|"
        r"transici[oó]n energ[eé]tica|descarbonizaci[oó]n)",
        re.IGNORECASE,
    )

    page_text = soup.get_text(" ", strip=True)
    version_match = re.search(
        r"[ÚU]ltima versi[oó]n:\s*(\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+(20\d{2}))",
        page_text,
        re.IGNORECASE,
    )
    calendar_version_label = version_match.group(1) if version_match else ""
    calendar_year = int(version_match.group(2)) if version_match else datetime.now().year
    calendar_version, _ = _parse_cdti_calendar_date(
        calendar_version_label,
        calendar_year,
    )

    # La tabla oficial proporciona programa, apertura y cierre. Se procesa por
    # filas para no confundir fechas de resolución con plazos de solicitud.
    for row in soup.select("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 3:
            continue
        anchor = cells[0].find("a", href=True)
        if not anchor:
            continue
        href = anchor.get("href", "").strip()
        title = " ".join(anchor.get_text(" ", strip=True).split())
        title = re.sub(r"\s*\(\*\)\s*", "", title).strip()
        if "/ayudas/" not in href or len(title) < 8:
            continue
        row_text = " ".join(row.get_text(" ", strip=True).split())
        if not (
            is_relevant(row_text)
            or programme_terms.search(f"{title} {href}")
        ):
            continue
        open_date, open_estimated = _parse_cdti_calendar_date(
            cells[1].get_text(" ", strip=True),
            calendar_year,
            month_end=False,
        )
        deadline_date, deadline_estimated = _parse_cdti_calendar_date(
            cells[2].get_text(" ", strip=True),
            calendar_year,
            month_end=True,
        )
        candidates[_absolute_url(base, href)] = {
            "title": title,
            "open_date": open_date,
            "deadline_date": deadline_date,
            "fecha_prevista": open_estimated or deadline_estimated,
        }

    results = []
    for detail_url, calendar_data in list(candidates.items())[:40]:
        calendar_title = calendar_data["title"]
        detail_html = browser.html(detail_url)
        detail_soup = BeautifulSoup(detail_html, "html.parser") if detail_html else None
        if detail_soup:
            title = calendar_title
            main = detail_soup.find("main") or detail_soup
            description = main.get_text(" ", strip=True)
        else:
            title = calendar_title
            description = calendar_title

        combined = f"{title} {description}"
        if not (is_relevant(combined) or programme_terms.search(title)):
            continue
        detail_open_date, detail_deadline_date = _extract_date_range(description)
        open_date = calendar_data["open_date"] or detail_open_date
        deadline_date = calendar_data["deadline_date"] or detail_deadline_date
        deadline_days = _days_until(deadline_date) if deadline_date else 90
        if deadline_date and deadline_days <= 0:
            continue

        results.append({
            "source":              "CDTI",
            "title":               title[:240],
            "description":         description[:2_000],
            "deadline_days":       deadline_days,
            "deadline_date":       deadline_date,
            "open_date":           open_date,
            "fecha_sin_confirmar": not bool(deadline_date),
            "fecha_prevista":      calendar_data["fecha_prevista"],
            "budget":              "Ver convocatoria",
            "url":                 detail_url,
            "url_generica":        False,
            "keywords_found":      keyword_match(combined),
            "org":                 "CDTI — Centro para el Desarrollo Tecnológico Industrial",
            "source_type":         "Playwright CDTI (calendario oficial)",
            "source_version":      calendar_version,
            "source_version_label": calendar_version_label,
        })

    log.info(f"  CDTI Playwright: {len(results)} convocatorias relevantes")
    return results


def _cdti_program_key(item: dict) -> str:
    """Agrupa variantes de título/URL pertenecientes al mismo programa CDTI."""
    text = _fold_text(f"{item.get('title', '')} {item.get('url', '')}")
    aliases = (
        (r"eurostars.*cod\s*10|cod10.*eurostars", "eurostars_cod10"),
        (r"eurostars.*cod\s*9|cod9.*eurostars", "eurostars_cod9"),
        (r"sera.*segunda|sera-2026-2", "sera_segunda"),
        (r"sera.*primera|sera-2026-1", "sera_primera"),
        (r"cervera.*centros|centros.*cervera|ayudas-cervera-para-centros", "cervera_centros"),
        (r"transferencia tecnologica.*cervera|proyectos-cervera", "cervera_transferencia"),
        (r"proyectos?-de-i-d|proyectos? i\\+d.*linea pid|^proyectos? i\\+d\\b", "proyectos_id"),
        (r"infraestructuras?.*ensayo", "infraestructuras_ensayo"),
        (r"proyectos?.*bilaterales", "proyectos_bilaterales"),
        (r"misiones.*ciencia", "misiones"),
        (r"neotec", "neotec"),
        (r"sello.*excelencia", "sello_excelencia"),
        (r"innterconecta", "innterconecta"),
        (r"innoglobal", "innoglobal"),
        (r"ecosistemas.*innovacion", "ecosistemas_innovacion"),
        (r"prima", "prima"),
    )
    for pattern, key in aliases:
        if re.search(pattern, text):
            return key
    clean_url = re.sub(r"[?#].*$", "", str(item.get("url", "")).rstrip("/").casefold())
    return clean_url or re.sub(r"\W+", "_", text).strip("_")


def _merge_cdti_results(*result_groups: list) -> list:
    """
    Fusiona catálogo, calendario y API. Los datos vivos tienen prioridad y el
    catálogo solo completa campos ausentes. Las keywords se acumulan.
    """
    merged = {}
    for group in result_groups:
        for item in group:
            key = _cdti_program_key(item)
            previous = merged.get(key)
            if previous is None:
                merged[key] = dict(item)
                continue

            combined = dict(item)
            for field in (
                "description",
                "deadline_date",
                "open_date",
                "budget",
                "url",
                "org",
                "source_version",
                "source_version_label",
            ):
                if not combined.get(field) and previous.get(field):
                    combined[field] = previous[field]

            if not combined.get("deadline_date") and previous.get("deadline_date"):
                combined["deadline_days"] = previous.get("deadline_days", 90)
                combined["fecha_sin_confirmar"] = previous.get("fecha_sin_confirmar", True)
                combined["fecha_prevista"] = previous.get("fecha_prevista", False)

            combined["keywords_found"] = sorted(set(
                previous.get("keywords_found", []) + combined.get("keywords_found", [])
            ))
            source_types = {
                previous.get("source_type", ""),
                combined.get("source_type", ""),
            }
            combined["source_type"] = " + ".join(sorted(value for value in source_types if value))
            merged[key] = combined

    results = list(merged.values())
    results.sort(key=lambda item: (item.get("deadline_days", 9999), item.get("title", "")))
    log.info(f"  CDTI combinado: {len(results)} convocatorias únicas vigentes")
    return results


def fetch_cdti(browser: PlaywrightBrowser) -> list:
    """
    Combina sesión JSON de BDNS, calendario oficial renderizado y catálogo
    curado. El catálogo complementa programas permanentes y datos ausentes.
    """
    log.info("Consultando CDTI (BDNS + calendario Playwright + catálogo curado)...")
    api_results = _bdns_cdti_convocatorias()
    browser_results = _fetch_cdti_playwright(browser)
    curated_results = _fetch_cdti_static()
    if not api_results and not browser_results:
        log.warning("CDTI: fuentes en vivo sin resultados; cobertura solo mediante catálogo curado")
    # Prioridad creciente: catálogo < calendario oficial < BDNS.
    return _merge_cdti_results(curated_results, browser_results, api_results)


def _fetch_boa_static() -> list:
    """
    BOA (Boletín Oficial de Aragón) — catálogo estático de respaldo.

    MANTENIMIENTO del catálogo estático: revisar cuando se publiquen nuevas
    convocatorias del Gobierno de Aragón relevantes para industria/energía.
    Fuente: https://www.aragon.es/temas/industria-energia-mineria/ayudas-subvenciones
    y https://www.boa.aragon.es
    Última revisión: 2026-04-09
    """
    log.info("BOA: usando catálogo estático de respaldo...")
    results = []

    # ── Catálogo estático BOA/Aragón curado ──────────────────────────
    # ESTADO: ★ = abierta confirmada | ◷ = fecha prevista | ✗ = cerrada (no incluir)
    # Fuentes: BOA, aragon.es/tramitador, última revisión 2026-04-09
    _BOA_STATIC = [
        {
            # ★ ABIERTA: 06/02/2026 – 05/05/2026 (confirmado por el usuario)
            "title":        "Fondo de Transición Justa 2026 — Inversión PYME provincia de Teruel",
            "description":  "Subvenciones del Fondo de Transición Justa para proyectos de inversión "
                            "de pequeñas y medianas empresas en la provincia de Teruel. Incluye "
                            "transformación ecológica de la industria, eficiencia energética y "
                            "economía circular. Dotación 2,5 M€. Compatible con proyectos de "
                            "descarbonización de procesos industriales en Aragón.",
            "open_date":    "2026-02-06",
            "deadline_date": "2026-05-05",
            "fecha_prevista": False,
            "budget":       "2.500.000 € total · subvención a fondo perdido",
            "url":          "https://www.aragon.es/tramitador/-/tramite/ayudas-a-pequenas-y-medianas-empresas-de-la-provincia-de-teruel-para-proyectos-de-inversion-fondo-de-transicion-justa",
            "keywords":     ["descarbonización", "eficiencia energética", "emisiones industriales",
                             "transición energética", "economía baja en carbono"],
        },
        {
            # ◷ PREVISTA: PAIP cierra típicamente sep-oct 2026 (edición 2026 en preparación)
            # La convocatoria 2026 de diseño industrial aún no está publicada
            "title":        "PAIP 2026 — Programa de Ayudas a la Industria y PYME Aragón (prevista)",
            "description":  "Programa de ayudas del Gobierno de Aragón a la industria y PYME para "
                            "proyectos de transformación, innovación y competitividad industrial. "
                            "La convocatoria de diseño industrial 2026 (línea dentro del PAIP) "
                            "está en preparación — suele publicarse entre septiembre y octubre de "
                            "cada año. La edición anterior (2025/2026) cerró el 15 enero 2026.",
            "open_date":    "2026-09-01",
            "deadline_date": "2026-11-30",
            "fecha_prevista": True,
            "budget":       "Ver convocatoria (subvención a fondo perdido)",
            "url":          "https://www.aragon.es/tramitador/-/tramite/ayudas-industria-digital-integradora-sostenible-marco-programa-ayudas-industria-pyme-aragon-paip/convocatoria-2026-en-desarrollo",
            "keywords":     ["eficiencia energética", "eficiencia térmica", "hornos industriales"],
        },
    ]

    for c in _BOA_STATIC:
        close_str       = c.get("deadline_date", "")
        open_str        = c.get("open_date", "")
        es_prevista     = c.get("fecha_prevista", False)
        deadline_days   = _days_until(close_str) if close_str else 120
        if deadline_days <= 0 and not es_prevista:
            log.debug(f"  BOA estático: descartando cerrada: {c['title'][:60]}")
            audit_exclusion(
                {
                    "source": "BOA ARAGÓN",
                    "title": c["title"],
                    "url": c["url"],
                    "open_date": open_str,
                    "deadline_date": close_str,
                },
                "deadline_closed",
                "boa_static_filter",
            )
            continue
        results.append({
            "source":              "BOA ARAGÓN",
            "title":               c["title"],
            "description":         c["description"],
            "deadline_days":       deadline_days,
            "deadline_date":       close_str,
            "open_date":           open_str,
            "fecha_sin_confirmar": not bool(close_str) or es_prevista,
            "fecha_prevista":      es_prevista,
            "budget":              c["budget"],
            "url":                 c["url"],
            "keywords_found":      c["keywords"],
            "org":                 "Gobierno de Aragón",
            "source_type":         "Catálogo curado",
        })
    log.info(f"  → {len(results)} convocatorias BOA cargadas desde el respaldo")
    return results


def _fetch_boa_playwright(browser: PlaywrightBrowser) -> list:
    """Consulta con Chromium búsquedas BOA y ayudas del Gobierno de Aragón."""
    targets = [
        "https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI?CMD=VERDOC&BASE=BODA&DOCS=1-40&SEPARADOR=&&RANG-C=20250101-&TEXT-TEXT=eficiencia+energetica+industria",
        "https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI?CMD=VERDOC&BASE=BODA&DOCS=1-40&SEPARADOR=&&RANG-C=20250101-&TEXT-TEXT=hidrogeno+industria",
        "https://www.aragon.es/temas/industria-energia-mineria/ayudas-subvenciones-industria-energia-mineria",
    ]
    results = []
    seen = set()
    active_marker = re.compile(
        rf"(?:en plazo|plazo permanente|convocatoria\s+{datetime.now().year}|"
        rf"{datetime.now().year}\s+en desarrollo)",
        re.IGNORECASE,
    )
    excluded_scope = re.compile(
        r"(regad[ií]o|agropecuari|agricultur|ganader|vivienda|residencial|"
        r"movilidad|veh[ií]culo|transporte)",
        re.IGNORECASE,
    )

    for target_url in targets:
        html = browser.html(target_url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        base = "https://www.boa.aragon.es" if "boa.aragon.es" in target_url else "https://www.aragon.es"

        for anchor in soup.find_all("a", href=True):
            title = " ".join(anchor.get_text(" ", strip=True).split())
            href = anchor.get("href", "").strip()
            container = anchor.find_parent(["article", "li", "tr", "div"])
            context_text = container.get_text(" ", strip=True) if container else title
            combined = f"{title} {context_text}"
            if (
                len(title) < 20
                or title in seen
                or not _es_titulo_valido(title)
                or not is_relevant(combined)
                or "fuera de plazo" in combined.lower()
                or excluded_scope.search(combined)
                or not active_marker.search(combined)
            ):
                continue
            seen.add(title)
            open_date, deadline_date = _extract_date_range(context_text)
            deadline_days = _days_until(deadline_date) if deadline_date else 60
            if deadline_date and deadline_days <= 0:
                continue
            results.append({
                "source":              "BOA ARAGÓN",
                "title":               title[:240],
                "description":         context_text[:2_000],
                "deadline_days":       deadline_days,
                "deadline_date":       deadline_date,
                "open_date":           open_date,
                "fecha_sin_confirmar": not bool(deadline_date),
                "fecha_prevista":      False,
                "budget":              "Ver disposición",
                "url":                 _absolute_url(base, href),
                "keywords_found":      keyword_match(combined),
                "org":                 "Gobierno de Aragón",
                "source_type":         "Playwright BOA",
            })

    log.info(f"  BOA Playwright: {len(results)} convocatorias relevantes")
    return results


def fetch_boa(browser: PlaywrightBrowser) -> list:
    results = _fetch_boa_playwright(browser)
    if results:
        return results
    log.warning("BOA: navegación en vivo sin resultados; activando catálogo estático")
    return _fetch_boa_static()


def _scrape_idae_dates(browser: PlaywrightBrowser, url: str) -> tuple[str, str]:
    """
    Entra en la página de detalle de una convocatoria IDAE e intenta extraer
    las fechas de apertura y cierre del plazo.
    Devuelve (open_date, deadline_date) en formato YYYY-MM-DD o cadena vacía si no se encuentra.
    El IDAE publica estas fechas en distintos formatos según la página:
      - "Plazo de solicitud: DD/MM/YYYY al DD/MM/YYYY"
      - "Inicio del plazo: DD/MM/YYYY" / "Fin del plazo: DD/MM/YYYY"
      - Tablas con etiquetas "Fecha de inicio" / "Fecha de fin"
    """
    html = browser.html(url)
    if not html:
        return "", ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        return _extract_application_dates(text)
    except Exception:
        return "", ""


def fetch_idae(browser: PlaywrightBrowser) -> list:
    """Navega con Chromium por el portal IDAE y sus páginas de detalle."""
    log.info("Consultando IDAE (Playwright)...")
    results = []

    # Patrones de títulos que son documentos/guías/planes, no convocatorias activas
    _IDAE_NOISE = re.compile(
        r"^(guía|plan nacional|documento|informe|memoria|estudio|manual|"
        r"metodología|registro|nota|presentación|borrador|resolución de "
        r"la secretaría|instrucción técnica|real decreto|orden ministerial)",
        re.IGNORECASE
    )

    # URLs verificadas del IDAE — la estructura web cambió en 2025
    urls_to_try = [
        "https://www.idae.es/ayudas-y-financiacion",
        "https://www.idae.es/financiacion-y-ayudas",
        "https://www.idae.es/convocatorias",
    ]

    soup = None
    for url in urls_to_try:
        html = browser.html(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            log.info(f"  IDAE accesible: {url}")
            break

    if not soup:
        log.warning("IDAE: ninguna URL accesible")
        return results

    seen = set()
    skipped_closed = 0
    skipped_noise  = 0

    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if not title or len(title) < 15 or title in seen:
            continue

        link = a["href"]
        if not link.startswith("http"):
            link = "https://www.idae.es" + link
        grant_detail_path = any(
            marker in link.casefold()
            for marker in (
                "/ayudas-y-financiacion/",
                "/financiacion-y-ayudas/",
                "/convocatorias/",
            )
        )
        # Los nombres comerciales (p. ej. «Programa INNOVAE») pueden no incluir
        # ninguna keyword. Las páginas de detalle de ayudas se visitan siempre
        # y la relevancia se decide sobre su contenido completo.
        if not grant_detail_path and not is_relevant(title):
            continue
        if "/convocatorias-cerradas/" in link.casefold():
            audit_exclusion(
                {"source": "IDAE", "title": title, "url": link},
                "explicitly_closed_section",
                "idae_url_filter",
            )
            continue

        programme_key, _ = _programme_identity(title)
        if (
            programme_key
            and _fold_text(title).startswith("programa ")
        ):
            # La landing aporta el nombre comercial y la URL legible. Se usa
            # como dato de identidad y solo se publica si otra fuente oficial
            # aporta una convocatoria relevante con la misma identidad.
            seen.add(title)
            IDENTITY_LANDINGS.append({
                "source": "IDAE",
                "title": title,
                "description": "",
                "deadline_days": 30,
                "deadline_date": "",
                "open_date": "",
                "fecha_sin_confirmar": True,
                "budget": "Ver convocatoria",
                "url": link,
                "keywords_found": [],
                "org": (
                    "Instituto para la Diversificación y Ahorro de la Energía"
                ),
                "source_type": "Landing IDAE (identidad)",
                "identity_only": True,
            })
            continue
        if not is_relevant(title):
            continue

        # Filtrar documentos/guías que no son convocatorias
        if _IDAE_NOISE.match(title):
            skipped_noise += 1
            audit_exclusion(
                {"source": "IDAE", "title": title, "url": link},
                "document_not_call",
                "idae_prefilter",
            )
            continue
        seen.add(title)

        detail_html = browser.html(link)
        detail_text = ""
        if detail_html:
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            content_root = (
                detail_soup.select_one("article.general-content")
                or detail_soup.select_one(".region-content")
                or detail_soup.body
            )
            detail_text = (
                content_root.get_text(" ", strip=True)
                if content_root else ""
            )
        identity_only = False
        if not detail_text:
            audit_exclusion(
                {"source": "IDAE", "title": title, "url": link},
                "detail_page_unavailable",
                "idae_detail_fetch",
            )
            continue
        combined = f"{title} {detail_text}"
        if not identity_only and not is_relevant(combined):
            audit_exclusion(
                {"source": "IDAE", "title": title, "url": link},
                "not_relevant_local_filter",
                "idae_detail_filter",
            )
            continue

        # Extraer identidad y fechas desde la página de detalle ya renderizada.
        open_date, deadline_date = _extract_application_dates(detail_text)
        bdns_match = re.search(
            r"\bBDNS(?:\s*\(Identif\.?\))?\s*[:,]?\s*(\d{5,})",
            detail_text,
            re.IGNORECASE,
        )
        bdns_id = bdns_match.group(1) if bdns_match else ""
        folded_title = _fold_text(title)
        call_identity_evidence = bool(
            bdns_id
            or re.search(
                r"\b(convocatoria|programa|ayudas?\s+para)\b",
                folded_title,
            )
        )
        if not call_identity_evidence:
            audit_exclusion(
                {
                    "source": "IDAE",
                    "title": title,
                    "url": link,
                    "bdns_id": bdns_id,
                },
                "information_page_not_call",
                "idae_identity_validation",
            )
            continue
        deadline_days = _days_until(deadline_date) if deadline_date else None

        # Descartar convocatorias cuyo plazo ya haya cerrado
        if deadline_date and deadline_days is not None and deadline_days <= 0:
            log.debug(f"  IDAE: descartando cerrada (close={deadline_date}): {title[:60]}")
            skipped_closed += 1
            audit_exclusion(
                {
                    "source": "IDAE",
                    "title": title,
                    "url": link,
                    "open_date": open_date,
                    "deadline_date": deadline_date,
                    "bdns_id": bdns_id,
                },
                "deadline_closed",
                "idae_deadline_validation",
            )
            continue

        if not deadline_date and not identity_only:
            folded_detail = _fold_text(detail_text)
            active_evidence = (
                str(datetime.now().year) in folded_detail
                and bool(re.search(
                    r"\b(convocatoria|plazo|presentacion de solicitudes)\b",
                    folded_detail,
                ))
                and not re.search(
                    r"\b(fuera de plazo|convocatoria cerrada|plazo cerrado)\b",
                    folded_detail,
                )
            )
            if not active_evidence:
                audit_exclusion(
                    {
                        "source": "IDAE",
                        "title": title,
                        "url": link,
                        "bdns_id": bdns_id,
                    },
                    "no_active_deadline_evidence",
                    "idae_deadline_validation",
                )
                continue

        # Si no tenemos fecha de cierre, usamos fallback de 30 días
        # y marcamos que la fecha no está confirmada
        fecha_sin_confirmar = not bool(deadline_date)
        if deadline_days is None:
            deadline_days = 30

        results.append({
            "source":               "IDAE",
            "title":                title,
            "description":          detail_text[:2_500],
            "deadline_days":        deadline_days,
            "deadline_date":        deadline_date,
            "open_date":            open_date,
            "fecha_sin_confirmar":  fecha_sin_confirmar,
            "budget":               "Ver convocatoria",
            "url":                  link,
            "keywords_found":       keyword_match(combined),
            "org":                  "Instituto para la Diversificación y Ahorro de la Energía",
            "source_type":          "Playwright IDAE",
            "identity_only":        identity_only,
            "bdns_id":              bdns_id,
            "bdns_url":             (
                f"https://www.pap.hacienda.gob.es/bdnstrans/GE/es/convocatorias/{bdns_id}"
                if bdns_id else ""
            ),
        })

    log.info(f"  → {len(results)} convocatorias IDAE válidas "
             f"(descartadas: {skipped_closed} cerradas, {skipped_noise} documentos)")
    return results


_IDAE_CATALOG_INCLUDE = re.compile(
    r"(industria|industrial|investigaci[oó]n y desarrollo|i\+d|"
    r"eficiencia energ[eé]tica|descarbonizaci[oó]n|hidr[oó]geno|"
    r"calor residual|tecnolog[ií]as limpias|econom[ií]a circular|"
    r"transici[oó]n energ[eé]tica|emisiones)",
    re.IGNORECASE,
)
_IDAE_CATALOG_EXCLUDE = re.compile(
    r"(agricultur|ganader|agropecuari|regad[ií]o|vivienda|residencial|"
    r"edificios?|movilidad|veh[ií]cul|transporte|pobreza energ[eé]tica|"
    r"turismo|sanitari|hospital|educativ|colegio|universidad)",
    re.IGNORECASE,
)
_IDAE_CATALOG_CALL_MARKER = re.compile(
    r"(extracto|convoca|convocatoria)",
    re.IGNORECASE,
)


def _idae_catalog_scope(header: str) -> str:
    folded = _fold_text(header)
    if "estatal/ estatal" in folded:
        return "Estatal"
    if "autonomico/ aragon" in folded:
        return "Autonómico / Aragón"
    if "local/ zaragoza" in folded:
        return "Local / Zaragoza"
    return ""


def _idae_catalog_document_rank(record: dict) -> tuple:
    """Prioriza extractos/convocatorias sobre bases, correcciones y cambios."""
    title = _fold_text(record.get("title", ""))
    score = 0
    if "extracto" in title:
        score += 4
    if "convoca" in title or "convocatoria" in title:
        score += 4
    if "modifica" in title or "ampliacion" in title:
        score -= 2
    if "correccion de errores" in title:
        score -= 3
    if "bases reguladoras" in title:
        score -= 4
    return score, record.get("publication_date", "")


def _parse_idae_catalog_html(html: str) -> tuple[list, dict]:
    """Extrae y agrupa las tres secciones autorizadas del catálogo IDAE."""
    soup = BeautifulSoup(html, "html.parser")
    records = []
    section_counts = {
        "Estatal": 0,
        "Autonómico / Aragón": 0,
        "Local / Zaragoza": 0,
    }
    current_category = {}

    for page in soup.select("div.new-page"):
        header_node = page.select_one("div.contenido-cabecera")
        scope = _idae_catalog_scope(
            header_node.get_text(" ", strip=True) if header_node else ""
        )
        if not scope:
            continue

        category = current_category.get(scope, "")
        for child in page.find_all(recursive=False):
            classes = set(child.get("class", []))
            if "grupo-titulo" in classes:
                category = " ".join(child.get_text(" ", strip=True).split()).strip(" /")
                current_category[scope] = category
                continue
            if not {"item", "grupo-item"}.issubset(classes):
                continue

            section_counts[scope] += 1
            text_node = child.select_one("div.text")
            if not text_node:
                continue
            title = " ".join(text_node.get_text(" ", strip=True).split())
            combined = f"{category} {title}"
            core_category = bool(re.search(
                r"(industria|investigaci[oó]n y desarrollo|i\+d)",
                category,
                re.IGNORECASE,
            ))
            if (
                not (_IDAE_CATALOG_INCLUDE.search(title) or core_category)
                or _IDAE_CATALOG_EXCLUDE.search(combined)
            ):
                continue

            item_text = " ".join(child.get_text(" ", strip=True).split())
            bdns_match = re.search(r"\bBDNS:\s*(\d+)", item_text, re.IGNORECASE)
            ref_match = re.search(
                r"\bRef\.?:\s*([A-Za-z0-9./-]+)",
                item_text,
                re.IGNORECASE,
            )
            date_matches = re.findall(r"\b(\d{2}/\d{2}/20\d{2})\b", item_text)
            anchors = child.find_all("a", href=True)
            official_url = ""
            bdns_url = ""
            for anchor in anchors:
                href = _absolute_url("https://www.idae.es", anchor.get("href", "").strip())
                if "pap.hacienda.gob.es" in href or "infosubvenciones" in href:
                    bdns_url = href
                elif not official_url:
                    official_url = href

            records.append({
                "scope": scope,
                "category": category,
                "title": title,
                "official_url": official_url or bdns_url,
                "bdns_url": bdns_url,
                "bdns_id": bdns_match.group(1) if bdns_match else "",
                "catalog_ref": ref_match.group(1) if ref_match else "",
                "publication_date": (
                    _date_to_iso(date_matches[-1]) if date_matches else ""
                ),
            })

    grouped = {}
    for record in records:
        key = (
            f"bdns:{record['bdns_id']}"
            if record["bdns_id"]
            else f"url:{re.sub(r'[?#].*$', '', record['official_url']).rstrip('/')}"
        )
        if not key or key == "url:":
            key = f"title:{_fold_text(record['title'])}"
        grouped.setdefault(key, []).append(record)

    candidates = []
    for related in grouped.values():
        if not any(_IDAE_CATALOG_CALL_MARKER.search(item["title"]) for item in related):
            continue
        primary = max(related, key=_idae_catalog_document_rank)
        primary = dict(primary)
        primary["related_documents"] = related
        primary["related_documents_count"] = len(related)
        candidates.append(primary)

    return candidates, section_counts


def _verify_idae_catalog_deadline(
    browser: PlaywrightBrowser,
    candidate: dict,
) -> tuple[str, str]:
    """Contrasta hasta dos documentos oficiales relacionados para localizar el plazo."""
    documents = sorted(
        candidate.get("related_documents", []),
        key=_idae_catalog_document_rank,
        reverse=True,
    )
    checked_urls = set()
    for document in documents:
        for url in (document.get("official_url", ""), document.get("bdns_url", "")):
            clean_url = str(url).strip()
            if not clean_url or clean_url in checked_urls:
                continue
            checked_urls.add(clean_url)
            if len(checked_urls) > 2:
                return "", ""
            boe_id_match = re.search(
                r"/(?:pdfs/)?(BOE-[AB]-20\d{2}-\d+)\.pdf$",
                clean_url,
                re.IGNORECASE,
            )
            verification_url = (
                f"https://www.boe.es/diario_boe/txt.php?id={boe_id_match.group(1)}"
                if boe_id_match
                else clean_url
            )
            # VEROBJ inicia una descarga PDF; la BDNS relacionada se intenta
            # después y resulta más útil para buscar plazos.
            if "boa.aragon.es" in verification_url and "VEROBJ" in verification_url:
                continue
            html = browser.html(verification_url)
            if not html:
                continue
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
            open_date, deadline_date = _extract_application_dates(text)
            if deadline_date:
                return open_date, deadline_date
    return "", ""


def fetch_idae_catalog(browser: PlaywrightBrowser) -> list:
    """
    Usa el catálogo agregado IDAE como capa de descubrimiento para Estatal,
    Aragón y Zaragoza; conserva la fuente oficial y la trazabilidad.
    """
    log.info("Consultando catálogo agregado IDAE (Estatal, Aragón, Zaragoza)...")
    catalog_url = "https://www.idae.es/catalogo-de-ayudas-preview?page=25"
    # La vista preview oculta <body> mientras prepara la maquetación de
    # impresión; esperar a <html> permite recuperar el DOM ya descargado.
    html = browser.html(catalog_url, wait_selector="html")
    if not html:
        log.warning("  Catálogo IDAE no accesible")
        SOURCE_RUNTIME_METADATA["IDAE CATÁLOGO"] = {
            "section_counts": {},
            "catalog_url": catalog_url,
            "status": "warn",
        }
        return []

    candidates, section_counts = _parse_idae_catalog_html(html)
    SOURCE_RUNTIME_METADATA["IDAE CATÁLOGO"] = {
        "section_counts": section_counts,
        "catalog_url": catalog_url,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
    }
    log.info(
        "  Catálogo IDAE bruto por sección: "
        + ", ".join(f"{name}={count}" for name, count in section_counts.items())
    )
    log.info(f"  Catálogo IDAE: {len(candidates)} grupos relevantes tras prefiltro")

    today = datetime.now().date()
    results = []
    skipped_old_unconfirmed = 0
    skipped_closed = 0

    for candidate in candidates:
        open_date, deadline_date = _verify_idae_catalog_deadline(browser, candidate)
        if deadline_date:
            deadline_days = _days_until(deadline_date)
            if deadline_days <= 0:
                skipped_closed += 1
                audit_exclusion(
                    {
                        "source": (
                            "BOE / MITECO"
                            if candidate["scope"] == "Estatal"
                            else "BOA ARAGÓN"
                            if candidate["scope"] == "Autonómico / Aragón"
                            else "ZARAGOZA"
                        ),
                        "title": candidate["title"],
                        "url": candidate.get("official_url", ""),
                        "bdns_id": candidate.get("bdns_id", ""),
                        "catalog_ref": candidate.get("catalog_ref", ""),
                        "open_date": open_date,
                        "deadline_date": deadline_date,
                    },
                    "deadline_closed",
                    "idae_catalog_deadline_validation",
                    {"catalog_scope": candidate["scope"]},
                )
                continue
            fecha_sin_confirmar = False
        else:
            publication_raw = candidate.get("publication_date", "")
            try:
                publication_date = datetime.strptime(publication_raw, "%Y-%m-%d").date()
                publication_age = (today - publication_date).days
            except (TypeError, ValueError):
                publication_age = 9999
            if publication_age < 0 or publication_age > 90:
                skipped_old_unconfirmed += 1
                audit_exclusion(
                    {
                        "source": "IDAE CATÁLOGO",
                        "title": candidate["title"],
                        "url": candidate.get("official_url", ""),
                        "bdns_id": candidate.get("bdns_id", ""),
                        "catalog_ref": candidate.get("catalog_ref", ""),
                    },
                    "old_without_verified_deadline",
                    "idae_catalog_deadline_validation",
                    {
                        "catalog_scope": candidate["scope"],
                        "publication_date": publication_raw,
                    },
                )
                continue
            deadline_days = 30
            fecha_sin_confirmar = True

        scope = candidate["scope"]
        if scope == "Estatal":
            source = "BOE / MITECO"
            org = "Organismo estatal convocante"
        elif scope == "Autonómico / Aragón":
            source = "BOA ARAGÓN"
            org = "Gobierno de Aragón / organismo convocante"
        else:
            source = "ZARAGOZA"
            org = "Ayuntamiento de Zaragoza / organismo local convocante"

        related_titles = [
            item["title"] for item in candidate.get("related_documents", [])
        ]
        description = (
            f"Descubierta mediante el catálogo IDAE. Ámbito: {scope}. "
            f"Categoría: {candidate.get('category', '')}. "
            f"Documentos relacionados ({len(related_titles)}): "
            + " | ".join(related_titles)
        )
        combined = f"{candidate['title']} {description}"
        results.append({
            "source": source,
            "title": candidate["title"][:300],
            "description": description[:2_500],
            "deadline_days": deadline_days,
            "deadline_date": deadline_date,
            "open_date": open_date,
            "fecha_sin_confirmar": fecha_sin_confirmar,
            "fecha_prevista": False,
            "budget": "Ver disposición oficial",
            "url": candidate.get("official_url") or candidate.get("bdns_url"),
            "keywords_found": keyword_match(combined),
            "org": org,
            "source_type": "Catálogo IDAE + fuente oficial",
            "discovered_via": "IDAE Catálogo",
            "catalog_scope": scope,
            "catalog_category": candidate.get("category", ""),
            "catalog_ref": candidate.get("catalog_ref", ""),
            "bdns_id": candidate.get("bdns_id", ""),
            "bdns_url": candidate.get("bdns_url", ""),
            "related_documents_count": candidate.get("related_documents_count", 1),
        })

    log.info(
        f"  → {len(results)} convocatorias del catálogo IDAE incorporables "
        f"(cerradas={skipped_closed}, antiguas sin plazo={skipped_old_unconfirmed})"
    )
    return results


def _es_titulo_valido(title: str) -> bool:
    """Filtra entradas basura del scraping (referencias BOE, enlaces de navegación, etc.)"""
    if len(title) < 20:
        return False
    patrones_basura = [
        r"^ir al documento",
        r"^ref\.\s*boe",
        r"^boe-[ab]-\d{4}",
        r"^\d+$",
        r"^ver (más|todo|detalle)",
        r"^(anterior|siguiente|inicio|fin|buscar|acceder)$",
        r"^(descargar|imprimir|compartir|enviar)",
    ]
    title_lower = title.lower().strip()
    for patron in patrones_basura:
        if re.match(patron, title_lower):
            return False
    return True


def fetch_boe(browser: PlaywrightBrowser) -> list:
    """
    BOE — búsqueda en ayudas.php.
    Cada resultado renderizado es un ``li.resultado-busqueda`` con el texto
    descriptivo y un enlace «Ir al documento».
    """
    log.info("Consultando BOE con Playwright (ayudas.php)...")
    results = []
    html = browser.html("https://www.boe.es/buscar/ayudas.php")

    if not html:
        log.warning("BOE: página de ayudas no accesible")
        return results

    soup = BeautifulSoup(html, "html.parser")
    seen = set()

    # ── Parser principal: resultados renderizados ────────────────────
    bloques = soup.select("li.resultado-busqueda")
    log.info(f"  BOE: {len(bloques)} bloques ayuda encontrados")

    for bloque in bloques:
        texto_completo = bloque.get_text(separator=" ", strip=True)

        # Enlace al documento BOE real (contiene /diario/ o /buscar/doc)
        a_doc = None
        for a in bloque.find_all("a", href=True):
            href = a.get("href", "")
            if "/diario" in href or "/buscar/doc" in href or "/boe/" in href:
                a_doc = a
                break
        if not a_doc:
            a_doc = bloque.find("a", href=True)
        if not a_doc:
            continue

        # Título: buscar en clases descriptivas o limpiar texto del bloque
        title = ""
        for cls in ["nombre-organismo", "descripcion-organismo", "descripcion-idioma", "direccion-organismo"]:
            el = bloque.find(class_=cls)
            if el:
                title = el.get_text(strip=True)
                break
        if not title:
            title = re.sub(r"Ir al documento.*", "", texto_completo).strip()
            title = re.sub(r"Más\.\.\.\s*\(.*?\)", "", title).strip()[:200]

        combined = f"{title} {texto_completo}"
        if not title or title in seen or not _es_titulo_valido(title) or not is_relevant(combined):
            continue
        seen.add(title)

        href = a_doc.get("href", "")
        if not href.startswith("http"):
            href = "https://www.boe.es" + href

        # URL canónica por referencia BOE si está disponible
        ref_match = re.search(r"BOE-[AB]-\d{4}-\d+", href + " " + texto_completo)
        if ref_match and "/diario" not in href:
            href = f"https://www.boe.es/buscar/doc.php?id={ref_match.group()}"

        # Enriquecimiento general desde el documento oficial: BDNS, título
        # canónico y plazo. Esto permite relacionar extractos, bases y páginas
        # de programa sin depender de nombres introducidos manualmente.
        detail_html = browser.html(href)
        detail_text = ""
        bdns_id = ""
        open_date = ""
        deadline_date = ""
        if detail_html:
            detail_soup = BeautifulSoup(detail_html, "html.parser")
            detail_text = detail_soup.get_text(" ", strip=True)
            heading = detail_soup.find("h3")
            if heading:
                official_title = " ".join(heading.get_text(" ", strip=True).split())
                if len(official_title) >= 20:
                    title = official_title
            bdns_match = re.search(
                r"\bBDNS(?:\s*\(Identif\.?\))?\s*[:,]?\s*(\d{5,})",
                detail_text,
                re.IGNORECASE,
            )
            bdns_id = bdns_match.group(1) if bdns_match else ""
            open_date, deadline_date = _extract_application_dates(detail_text)

        deadline_days = _days_until(deadline_date) if deadline_date else 45
        results.append({
            "source":         "BOE / MITECO",
            "title":          title,
            "description":    (detail_text or texto_completo)[:2_500],
            "deadline_days":  deadline_days,
            "deadline_date":  deadline_date,
            "open_date":      open_date,
            "fecha_sin_confirmar": not bool(deadline_date),
            "budget":         "Ver disposición",
            "url":            href,
            "keywords_found": keyword_match(f"{combined} {detail_text}"),
            "org":            "Boletín Oficial del Estado",
            "source_type":    "Playwright BOE",
            "bdns_id":        bdns_id,
            "bdns_url":       (
                f"https://www.pap.hacienda.gob.es/bdnstrans/GE/es/convocatorias/{bdns_id}"
                if bdns_id else ""
            ),
        })

    # ── Fallback: enlaces directos a documentos BOE ───────────────────
    if not results:
        log.info("  BOE: sin coincidencias relevantes — fallback por enlaces directos")
        for a in soup.find_all("a", href=True):
            href  = a.get("href", "")
            title = a.get_text(strip=True)
            if not ("/diario" in href or "/buscar/doc" in href):
                continue
            if not title or title in seen or not _es_titulo_valido(title) or not is_relevant(title):
                continue
            seen.add(title)
            if not href.startswith("http"):
                href = "https://www.boe.es" + href
            results.append({
                "source":         "BOE / MITECO",
                "title":          title,
                "description":    "",
                "deadline_days":  45,
                "deadline_date":  "",
                "budget":         "Ver disposición",
                "url":            href,
                "keywords_found": keyword_match(title),
                "org":            "Boletín Oficial del Estado",
                "source_type":    "Playwright BOE",
            })

    log.info(f"  → {len(results)} convocatorias BOE relevantes")
    return results


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
ENTIDADES_CANONICAS = ["ITAINNOVA", "CIRCE", "Unizar", "CDTI", "IDAE"]


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


def post_procesar_texto(texto: str, whitelist: list = None) -> str:
    """
    Normaliza variantes cercanas (alucinadas) de nombres de entidad a su forma
    canónica, usando distancia de Levenshtein <= 2 sobre tokens alfabéticos de
    4+ caracteres. Se aplica SOLO a los campos "summary" y "action" generados
    por Claude Haiku (texto libre) — nunca a título, descripción, URL o
    cualquier campo que provenga directamente de la fuente original.
    """
    if not texto:
        return texto
    whitelist = whitelist or ENTIDADES_CANONICAS
    tokens = re.findall(r"[A-Za-zÀ-ÿ]+|[^A-Za-zÀ-ÿ]+", texto)
    corregido = []
    for tok in tokens:
        if tok.isalpha() and len(tok) >= 4:
            mejor = min(whitelist, key=lambda e: _levenshtein(tok.upper(), e.upper()))
            dist = _levenshtein(tok.upper(), mejor.upper())
            corregido.append(mejor if 0 < dist <= 2 else tok)
        else:
            corregido.append(tok)
    return "".join(corregido)

print("✓ Normalización determinista de entidades cargada")


class ClaudeAnalysisError(RuntimeError):
    """Error que impide continuar, generar el JSON o publicar resultados."""


def claude_key_format_is_valid() -> bool:
    """Validación local de formato; no realiza ninguna petición externa."""
    return (
        isinstance(CLAUDE_API_KEY, str)
        and CLAUDE_API_KEY == CLAUDE_API_KEY.strip()
        and CLAUDE_API_KEY.startswith("sk-ant-")
        and len(CLAUDE_API_KEY) >= 50
    )


def github_token_format_is_valid() -> bool:
    """Validación local de los formatos habituales de token de GitHub."""
    return (
        isinstance(GITHUB_TOKEN, str)
        and GITHUB_TOKEN == GITHUB_TOKEN.strip()
        and GITHUB_TOKEN.startswith(("github_pat_", "ghp_"))
        and len(GITHUB_TOKEN) >= 40
    )


def _programme_identity(title: str) -> tuple[str, str]:
    """Obtiene una identidad conservadora de programas con nombre/acrónimo."""
    original = " ".join(str(title).split())
    if not re.search(r"\bprograma\b", original, re.IGNORECASE):
        return "", ""
    candidates = re.findall(r"\(([^()]{3,80})\)", original)
    direct_match = re.search(
        r"\bprograma\s+([A-ZÁÉÍÓÚÜÑ0-9][A-ZÁÉÍÓÚÜÑ0-9-]{2,30})\b",
        original,
        re.IGNORECASE,
    )
    if direct_match:
        candidates.append(direct_match.group(1))

    rejected = {
        "idae",
        "miteco",
        "fnee",
        "boe",
        "mp",
        "ue",
        "union europea",
        "feder",
        "prtr",
    }
    for candidate in reversed(candidates):
        has_program_prefix = bool(re.match(
            r"^\s*programa(?:\s+de)?\s+",
            candidate,
            re.IGNORECASE,
        ))
        is_acronym = candidate == candidate.upper() and len(candidate) <= 35
        if not has_program_prefix and not is_acronym:
            continue
        display = re.sub(
            r"^\s*programa(?:\s+de)?\s+",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip(" .:-")
        folded = re.sub(r"[^a-z0-9]+", " ", _fold_text(display)).strip()
        if (
            folded
            and folded not in rejected
            and not folded.startswith(("feder ", "fnee ", "prtr "))
            and not re.fullmatch(r"20\d{2}(?:\s+20\d{2})?", folded)
            and len(folded.split()) <= 5
        ):
            return folded, display
    return "", ""


def _document_role(item: dict) -> str:
    folded = _fold_text(item.get("title", ""))
    url = str(item.get("url", "")).casefold()
    if (
        item.get("source") == "IDAE"
        and "/ayudas-y-financiacion/" in url
    ):
        return "program_landing"
    if "extracto" in folded:
        return "call_extract"
    if "convocatoria" in folded or "se convoca" in folded:
        return "call"
    if "bases reguladoras" in folded:
        return "regulatory_bases"
    if "modifica" in folded or "correccion" in folded:
        return "amendment"
    return "source_record"


def _document_rank(item: dict) -> tuple:
    role_scores = {
        "program_landing": 100,
        "call_extract": 80,
        "call": 75,
        "source_record": 50,
        "amendment": 30,
        "regulatory_bases": 20,
    }
    role = _document_role(item)
    return (
        role_scores.get(role, 0),
        int(bool(item.get("deadline_date"))) * 10,
        int(not bool(item.get("fecha_sin_confirmar", False))) * 5,
        len(str(item.get("description", ""))),
    )


def _deduplicate_raw_convocations(convocations: list) -> list:
    """
    Consolida documentos de una misma ayuda por BDNS y, cuando falta este,
    por un nombre de programa inequívoco. Conserva la trazabilidad de todos
    los documentos relacionados.
    """
    prepared = []
    programme_bdns = {}
    for raw_item in convocations:
        item = dict(raw_item)
        bdns_id = str(item.get("bdns_id", "")).strip()
        if not bdns_id:
            bdns_match = re.search(
                r"(?:BDNS|convocatorias?/)(?:\D{0,20})?(\d{5,})",
                " ".join(
                    str(item.get(field, ""))
                    for field in ("description", "url", "bdns_url")
                ),
                re.IGNORECASE,
            )
            bdns_id = bdns_match.group(1) if bdns_match else ""
        programme_key, programme_name = _programme_identity(item.get("title", ""))
        item["bdns_id"] = bdns_id
        item["document_role"] = _document_role(item)
        if programme_key:
            item["programme_key"] = programme_key
            item["programme_name"] = programme_name
            if bdns_id:
                programme_bdns.setdefault(programme_key, set()).add(bdns_id)
        prepared.append(item)

    # Propaga el BDNS a bases y páginas del mismo programa solo cuando la
    # relación es unívoca en la ejecución actual.
    for item in prepared:
        programme_key = item.get("programme_key", "")
        known_ids = programme_bdns.get(programme_key, set())
        if not item.get("bdns_id") and len(known_ids) == 1:
            item["bdns_id"] = next(iter(known_ids))
            item["bdns_url"] = (
                "https://www.pap.hacienda.gob.es/bdnstrans/GE/es/convocatorias/"
                + item["bdns_id"]
            )

    merged = {}
    for item in prepared:
        bdns_id = str(item.get("bdns_id", "")).strip()
        clean_url = re.sub(
            r"[?#].*$",
            "",
            str(item.get("url", "")).strip().rstrip("/").casefold(),
        )
        if bdns_id:
            key = f"bdns:{bdns_id}"
        elif item.get("programme_key"):
            key = f"programme:{item['programme_key']}"
        elif clean_url:
            key = f"url:{clean_url}"
        else:
            key = (
                f"title:{item.get('source', '')}:"
                f"{re.sub(r'\\W+', ' ', _fold_text(item.get('title', ''))).strip()}"
            )

        previous = merged.get(key)
        if previous is None:
            merged[key] = dict(item)
            continue

        previous_is_catalog = bool(previous.get("discovered_via"))
        item_is_catalog = bool(item.get("discovered_via"))
        has_strong_identity = bool(
            bdns_id or item.get("programme_key")
        )
        if not has_strong_identity and not previous_is_catalog and not item_is_catalog:
            # La deduplicación transversal se limita al agregador. Dos fuentes
            # directas pueden compartir una landing genérica y seguir siendo
            # convocatorias distintas.
            direct_key = (
                f"{key}|direct:{item.get('source', '')}:"
                f"{re.sub(r'\\W+', ' ', _fold_text(item.get('title', ''))).strip()}"
            )
            merged[direct_key] = dict(item)
            continue
        if _document_rank(item) > _document_rank(previous):
            primary, secondary = dict(item), previous
        else:
            primary, secondary = previous, item

        related_documents = []
        for document in (
            previous.get("related_documents_trace", [])
            + item.get("related_documents_trace", [])
            + [previous, item]
        ):
            trace = {
                "source": document.get("source", ""),
                "title": document.get("title", ""),
                "url": document.get("url", ""),
                "document_role": document.get(
                    "document_role", _document_role(document)
                ),
            }
            if trace not in related_documents:
                related_documents.append(trace)
        primary["related_documents_trace"] = related_documents
        primary["related_documents_count"] = len(related_documents)
        audit_exclusion(
            secondary,
            "merged_related_document",
            "identity_consolidation",
            {
                "identity": key,
                "primary_title": primary.get("title", ""),
            },
        )

        for field in (
            "discovered_via",
            "catalog_scope",
            "catalog_category",
            "catalog_ref",
            "bdns_id",
            "bdns_url",
            "related_documents_count",
            "programme_key",
            "programme_name",
        ):
            if not primary.get(field) and secondary.get(field):
                primary[field] = secondary[field]

        primary["keywords_found"] = sorted(set(
            primary.get("keywords_found", []) + secondary.get("keywords_found", [])
        ))
        if (
            primary.get("fecha_sin_confirmar", True)
            and not secondary.get("fecha_sin_confirmar", True)
        ):
            for field in (
                "deadline_days",
                "deadline_date",
                "open_date",
                "fecha_sin_confirmar",
                "fecha_prevista",
            ):
                primary[field] = secondary.get(field)
        if len(primary.get("description", "")) < 100 and secondary.get("description"):
            primary["description"] = secondary["description"]
        primary["identity_only"] = bool(
            primary.get("identity_only", False)
            and secondary.get("identity_only", False)
        )
        merged[key] = primary

    consolidated = []
    for item in merged.values():
        if item.get("identity_only"):
            audit_exclusion(
                item,
                "unmatched_identity_landing",
                "identity_consolidation",
            )
            continue
        consolidated.append(item)
    return consolidated


def analyze_with_claude(conv: dict, max_retries: int = 3) -> dict:
    """
    Envía la convocatoria a Claude Haiku 4.5 y obtiene análisis de encaje.
    Coste estimado: ~$0.002 por convocatoria con Haiku 4.5.

    CALIBRACIÓN (ajustada tras diagnóstico v4):
    - Prompt anterior demasiado conservador → todos los scores ≤78, ninguno ≥80.
    - Waste heat recovery / thermal industrial debe puntuar 85-95.
    - Balance: escéptico con exclusiones, generoso con alineación real.
    """
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    desc_extendida = conv['description']
    if not desc_extendida or len(desc_extendida) < 100:
        desc_extendida = "[Sin descripción detallada — valorar por título y keywords]"

    prompt = f"""
Eres un consultor senior en financiación de I+D industrial. Evalúa el encaje entre
esta convocatoria y el perfil de Kalfrisa.

PERFIL KALFRISA:
{KALFRISA_PROFILE}

CONVOCATORIA:
Título: {conv['title']}
Fuente: {conv['source']}
URL: {conv.get('url', 'N/D')}
Descripción: {desc_extendida}
Keywords detectadas: {', '.join(conv['keywords_found'])}

ESCALA DE PUNTUACIÓN — APLICA CON PRECISIÓN:

  90-100: Convocatoria diseñada para tecnologías térmicas industriales (recuperación calor
          residual, combustión industrial, emisiones hornos, quemadores H2). Kalfrisa puede
          liderar. EJEMPLO: "waste heat recovery industrial furnaces", "industrial combustion
          NOx emissions", "H2-ready burners high temperature processes"

  75-89:  Buena alineación con industria térmica aunque no exclusiva. Kalfrisa encaja como
          partner tecnológico experto.
          EJEMPLO: "energy efficiency industrial processes", "industrial decarbonization IA"

  50-74:  Alineación parcial. Toca el sector pero Kalfrisa no es el solicitante natural.
          EJEMPLO: "hydrogen value chain" sin componente térmico industrial específico

  20-49:  Alineación débil. Tema adyacente, foco principal no es el de Kalfrisa.
          EJEMPLO: "energy efficiency" genérico incluyendo edificios o transporte

  1-19:   Criterios de exclusión absoluta o completamente irrelevante.
          EJEMPLO: edificios residenciales, transporte, renovables eléctricas, agricultura

REGLAS:
- Si la descripción es corta, usa el título para inferir. NO penalices por falta de desc.
- Horizon Europe waste heat / thermal / industrial combustion / NOx → HIGH priority siempre.
- TRL 4-7 de Kalfrisa encaja con convocatorias de demostración industrial (IA/RIA/TRL5-7).
- priority: "high" si match≥75, "medium" si 40≤match<75, "low" si match<40.
- Al citar entidades u organismos técnicos en "resumen" o "accion", usa EXCLUSIVAMENTE
  estos nombres canónicos, escritos exactamente así: ITAINNOVA, CIRCE, Unizar, CDTI, IDAE.
  Prohibido generar variantes, abreviaturas no estándar o alterar la ortografía de estos
  nombres bajo ningún concepto.

Responde SOLO con JSON válido sin texto adicional ni backticks:
{{{{
  "match_score": <entero 0-100>,
  "priority": "<high|medium|low>",
  "descartada": <true solo si exclusión absoluta, false en caso contrario>,
  "motivo_descarte": "<razón si descartada=true, cadena vacía si false>",
  "trl_min": <entero 1-9>,
  "trl_max": <entero 1-9>,
  "socio_consorcio": "<centro tecnológico / universidad / empresa grande / N/A>",
  "resumen": "<2-3 frases concretas sobre encaje con Kalfrisa>",
  "accion": "<acción concreta: contactar ITAINNOVA/CIRCE, preparar propuesta, descartar, etc.>",
  "dimensiones": [
    {{{{"name": "Alineación tecnológica", "val": <0-100>}}}},
    {{{{"name": "Capacidad de consorcio",  "val": <0-100>}}}},
    {{{{"name": "Encaje TRL",             "val": <0-100>}}}},
    {{{{"name": "Oportunidad estratégica", "val": <0-100>}}}}
  ],
  "tags": [<tags aplicables: h2, ee, desc, emis, horn>]
}}}}
Tags: h2=hidrógeno, ee=eficiencia energética industrial, desc=descarbonización,
      emis=control emisiones NOx/COV, horn=hornos/procesos térmicos alta temperatura
"""
    last_error = None
    for attempt in range(max_retries):
        try:
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            analysis = json.loads(raw.strip())
            if not analysis_is_usable(analysis):
                raise ValueError("respuesta JSON incompleta o con campos no válidos")
            return analysis

        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            log.warning(
                f"Respuesta inválida de Claude para '{conv['title'][:50]}' "
                f"(intento {attempt + 1}/{max_retries}): {e}"
            )
            if attempt < max_retries - 1:
                time.sleep(CLAUDE_SLEEP_S)

        except Exception as e:
            last_error = e
            err_str = str(e)
            status_code = getattr(e, "status_code", None)
            if status_code in (401, 403) or "invalid x-api-key" in err_str.lower():
                raise ClaudeAnalysisError(
                    "Claude rechazó la autenticación. Revisa CLAUDE_API_KEY."
                ) from e
            if "529" in err_str or "overloaded" in err_str.lower() or "rate" in err_str.lower():
                wait_secs = 30 * (attempt + 1)
                log.warning(f"  Claude sobrecargado. Esperando {wait_secs}s (intento {attempt+1}/{max_retries})...")
                time.sleep(wait_secs)
            else:
                raise ClaudeAnalysisError(
                    f"Claude no pudo analizar '{conv['title'][:50]}': {e}"
                ) from e

    raise ClaudeAnalysisError(
        f"Claude no devolvió un análisis válido para '{conv['title'][:50]}' "
        f"tras {max_retries} intentos: {last_error}"
    )

print("✓ Función de análisis Claude Haiku 4.5 cargada")


# ─────────────────────────────────────────────────────────────────────
# CELDA 6 — FUNCIONES DE ENSAMBLADO DEL JSON FINAL
# ─────────────────────────────────────────────────────────────────────

def build_stats(
    convocatorias: list,
    detected_total: int = None,
    closed_total: int = 0,
) -> dict:
    """
    Separa cobertura, vigencia y relevancia para evitar que las descartadas por
    Claude se interpreten como oportunidades activas recomendadas.
    """
    active_items = [c for c in convocatorias if c.get("deadline", 0) > 0]
    relevant_items = [c for c in active_items if not c.get("descartada", False)]
    discarded = sum(1 for c in active_items if c.get("descartada", False))
    high = sum(1 for c in relevant_items if c.get("match", 0) >= 80)
    urgent = sum(1 for c in relevant_items if c.get("deadline", 99) < 30)
    budget = sum(
        float(str(c.get("budget_raw", 0)).replace("€", "").replace("M", "").strip() or 0)
        for c in relevant_items
    )
    return {
        "detected": detected_total if detected_total is not None else len(convocatorias),
        "active": len(active_items),
        "closed": closed_total,
        "discarded": discarded,
        "relevant": len(relevant_items),
        "high": high,
        "urgent": urgent,
        "budget": round(budget, 1),
    }


def build_source_status(
    results_by_source: dict,
    descartadas_por_fuente: dict = None,
    source_timings: dict = None,
) -> list:
    descartadas_por_fuente = descartadas_por_fuente or {}
    source_timings = source_timings or {}
    default_source_meta = {
        "HORIZON EUROPE": "API REST",
        "CDTI":           "BDNS + Playwright + catálogo curado",
        "IDAE":           "Playwright",
        "IDAE CATÁLOGO":  "Playwright (descubrimiento agregado)",
        "BOE / MITECO":   "Playwright",
        "BOA ARAGÓN":     "Playwright / respaldo",
    }
    now_str = datetime.now().strftime("%H:%M")
    status = []
    for name, default_type in default_source_meta.items():
        source_results = results_by_source.get(name, [])
        detected_types = sorted({
            item.get("source_type", "") for item in source_results
            if item.get("source_type")
        })
        source_versions = sorted({
            item.get("source_version", "") for item in source_results
            if item.get("source_version")
        })
        source_version_labels = sorted({
            item.get("source_version_label", "") for item in source_results
            if item.get("source_version_label")
        })
        source_status = {
            "name":   name,
            "type":   " + ".join(detected_types) if detected_types else default_type,
            "status": "ok" if source_results else "warn",
            "count":  len(source_results),
            # Encontradas por la fuente pero descartadas antes del análisis por
            # tener deadline_days <= 0 (plazo ya cerrado en el momento de la
            # ejecución). Si count > 0 y count == count_cerradas, la fuente SÍ
            # está funcionando pero no ofrece hoy ninguna convocatoria vigente.
            "count_cerradas": descartadas_por_fuente.get(name, 0),
            "duration_seconds": round(source_timings.get(name, 0.0), 2),
            "time":   f"actualizado {now_str}",
            "source_version": source_versions[-1] if source_versions else "",
            "source_version_label": (
                source_version_labels[-1] if source_version_labels else ""
            ),
        }
        source_status.update(SOURCE_RUNTIME_METADATA.get(name, {}))
        status.append(source_status)
    return status


def build_keywords(convs: list) -> list:
    counter = Counter()
    for c in convs:
        for kw in c.get("keywords_found", []):
            counter[kw] += 1
    colors = {
        "hidrógeno":            "var(--teal)",
        "hydrogen":             "var(--teal)",
        "eficiencia energética":"var(--accent)",
        "descarbonización":     "var(--blue)",
        "hornos industriales":  "#a080e0",
        "emisiones industriales":"var(--red)",
        "combustión limpia":    "var(--teal)",
    }
    return [
        {"name": kw, "count": cnt, "color": colors.get(kw, "var(--accent)")}
        for kw, cnt in counter.most_common(8)
    ]

print("✓ Funciones de ensamblado cargadas")


# ─────────────────────────────────────────────────────────────────────
# VERIFICACIÓN TÉCNICA DE URLs (HTTP, no IA)
# ─────────────────────────────────────────────────────────────────────
def verificar_urls(convocatorias: list, timeout: int = 8) -> None:
    """
    Comprueba que cada URL responde correctamente antes de publicar el JSON.
    NUNCA modifica, genera ni "corrige" la URL — solo la señaliza mediante el
    campo url_rota si no se puede confirmar una respuesta HTTP < 400.
    Esta comprobación es deliberadamente determinista (peticiones HTTP reales),
    no delegada en un LLM: un LLM no puede confirmar si una URL es correcta,
    solo si el servidor responde.
    """
    log.info("Verificando accesibilidad HTTP de URLs antes de publicar...")
    vistas = {}
    for c in convocatorias:
        url = c.get("url", "")
        if not url:
            c["url_rota"] = False
            continue
        if url in vistas:
            c["url_rota"] = vistas[url]
            continue
        ok = False
        try:
            r = requests.head(url, timeout=timeout, allow_redirects=True,
                               headers={"User-Agent": "GrantRadar-Bot/1.0"})
            if r.status_code >= 400:
                r = requests.get(url, timeout=timeout, allow_redirects=True,
                                  headers={"User-Agent": "GrantRadar-Bot/1.0"})
            ok = r.status_code < 400
        except Exception as e:
            log.warning(f"  URL no verificable ({url}): {e}")
            ok = False
        c["url_rota"] = not ok
        vistas[url] = c["url_rota"]

    n_rotas = sum(1 for c in convocatorias if c.get("url_rota"))
    if n_rotas:
        log.warning(f"  ⚠ {n_rotas} URL(s) no respondieron correctamente (marcadas url_rota=True)")
    else:
        log.info("  ✓ Todas las URLs respondieron correctamente")

print("✓ Verificación técnica de URLs cargada")


# ─────────────────────────────────────────────────────────────────────
# CELDA 6B — CONFIGURACIÓN GITHUB PAGES Y FUNCIÓN DE SUBIDA
# ─────────────────────────────────────────────────────────────────────

def github_upload(filepath: str):
    """
    Sube el convocatorias.json al repositorio GitHub usando la API REST.
    GitHub Pages servirá automáticamente el archivo actualizado.
    """
    if not github_token_format_is_valid():
        print("⚠ Formato de GITHUB_TOKEN no válido — se omite la publicación")
        return

    filename = os.path.basename(filepath)
    url      = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{filename}"
    headers  = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github.v3+json",
    }

    # Leer el archivo y codificarlo en base64 (requerido por GitHub API)
    import base64
    with open(filepath, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("utf-8")

    # Obtener el SHA actual del archivo (necesario para actualizar, no para crear)
    sha = None
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        sha = resp.json().get("sha")

    # Subir o actualizar el archivo
    payload = {
        "message": f"Grant-Radar: actualización automática {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC",
        "content": content_b64,
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha  # necesario para sobreescribir un archivo existente

    resp = requests.put(url, headers=headers, json=payload)

    if resp.status_code in (200, 201):
        print(f"✓ convocatorias.json subido a GitHub Pages")
        print(f"  URL pública: https://{GITHUB_USER}.github.io/{GITHUB_REPO}/convocatorias.json")
    else:
        print(f"⚠ Error subiendo a GitHub: {resp.status_code} — {resp.json().get('message','')}")

print("✓ Función GitHub Pages cargada")


# ─────────────────────────────────────────────────────────────────────
# CELDA 7 — PIPELINE PRINCIPAL
# Ejecuta todo el proceso: recolección → análisis → JSON
# ─────────────────────────────────────────────────────────────────────

def run_pipeline(no_claude: bool = False):
    pipeline_started = time.perf_counter()
    run_started_at = datetime.now(timezone.utc).isoformat()
    DISCOVERY_AUDIT.clear()
    IDENTITY_LANDINGS.clear()
    print("=" * 60)
    print("Grant-Radar — Iniciando pipeline")
    print("=" * 60)

    if not no_claude and not claude_key_format_is_valid():
        print("⚠ ERROR: el formato de CLAUDE_API_KEY no es válido.")
        print("  La ejecución se detiene antes de recopilar o modificar archivos.")
        return

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

    horizon_results = timed_fetch("HORIZON EUROPE", fetch_horizon_europe)
    browser_started = time.perf_counter()
    with PlaywrightBrowser(headless=True) as browser:
        browser_startup_seconds = time.perf_counter() - browser_started
        idae_results = timed_fetch("IDAE", fetch_idae, browser)
        boe_results = timed_fetch("BOE / MITECO", fetch_boe, browser)
        boa_results = timed_fetch("BOA ARAGÓN", fetch_boa, browser)
        idae_catalog_results = timed_fetch(
            "IDAE CATÁLOGO",
            fetch_idae_catalog,
            browser,
        )
        raw_by_source = {
            "HORIZON EUROPE": horizon_results,
            "CDTI":           timed_fetch("CDTI", fetch_cdti, browser),
            "IDAE":           idae_results,
            "IDAE CATÁLOGO":  idae_catalog_results,
            "BOE / MITECO":   boe_results,
            "BOA ARAGÓN":     boa_results,
        }
    collection_seconds = time.perf_counter() - pipeline_started

    print("\nTiempos de recopilación:")
    print(f"  {'Chromium (inicio)':<18} {browser_startup_seconds:>7.2f} s")
    for source_name in raw_by_source:
        print(f"  {source_name:<18} {source_timings.get(source_name, 0.0):>7.2f} s")
    print(f"  {'TOTAL RECOPILACIÓN':<18} {collection_seconds:>7.2f} s")

    all_raw_with_duplicates = [
        item for items in raw_by_source.values() for item in items
    ] + IDENTITY_LANDINGS
    all_raw = _deduplicate_raw_convocations(all_raw_with_duplicates)
    deduplicated_count = len(all_raw_with_duplicates) - len(all_raw)
    print(
        f"\nTotal convocatorias detectadas antes de filtros: {len(all_raw)} "
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
    print(f"Total tras filtrar cerradas: {len(all_raw)}")

    if not all_raw:
        save_discovery_audit(
            run_started_at,
            "completed_without_active_results",
            {name: len(items) for name, items in raw_by_source.items()},
        )
        print("⚠ No se detectaron convocatorias. Revisa conectividad y keywords.")
        return

    if no_claude:
        print("\n" + "=" * 60)
        print("MODO --no-claude — recopilación finalizada")
        for source_name in raw_by_source:
            valid_items = [
                item for item in all_raw
                if item.get("source") == source_name
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
        print("  No se llamó a Claude.")
        print("  No se modificó la caché.")
        print("  No se generó ni publicó convocatorias.json.")
        save_discovery_audit(
            run_started_at,
            "completed_no_claude",
            {name: len(items) for name, items in raw_by_source.items()},
        )
        print(f"  Auditoría de descartes actualizada: {AUDIT_FILE}")
        print("=" * 60)
        return all_raw

    # 2 ── ANÁLISIS CON CLAUDE HAIKU (solo convocatorias nuevas, las demás van de caché)
    cache = cache_load()
    nuevas    = [c for c in all_raw if cache_key(c) not in cache]
    en_cache  = [c for c in all_raw if cache_key(c) in cache]

    print(f"  → En caché (sin llamada a Claude Haiku): {len(en_cache)}")
    print(f"  → Nuevas (requieren análisis):     {len(nuevas)}")

    if nuevas:
        print(f"\nAnalizando {len(nuevas)} convocatorias nuevas con Claude Haiku 4.5...")
    
    for i, conv in enumerate(nuevas):
        print(f"  [{i+1}/{len(nuevas)}] {conv['title'][:65]}...")
        try:
            analysis = analyze_with_claude(conv)
        except ClaudeAnalysisError as e:
            log.error(str(e))
            save_discovery_audit(
                run_started_at,
                "aborted_claude_error",
                {name: len(items) for name, items in raw_by_source.items()},
            )
            print("\n" + "=" * 60)
            print("PIPELINE ABORTADO — no se generó ni publicó convocatorias.json")
            print("Los análisis completados correctamente sí permanecen en caché.")
            print("=" * 60)
            return
        key = cache_key(conv)
        cache[key] = {"conv": conv, "analysis": analysis, "cached_at": datetime.now().isoformat()}
        # Guardar caché tras cada análisis para no perder progreso si falla a mitad
        cache_save(cache)
        if i < len(nuevas) - 1:
            time.sleep(CLAUDE_SLEEP_S)  # pausa mínima entre llamadas

    # Ensamblar resultados: caché + nuevos análisis
    enriched = []
    for conv in all_raw:
        key      = cache_key(conv)
        analysis = cache[key]["analysis"] if key in cache else {
            "match_score": 50, "priority": "medium",
            "resumen": "Pendiente de análisis.", "accion": "Revisar manualmente.",
            "dimensiones": [{"name": n, "val": 50} for n in
                ["Alineación tecnológica","Capacidad de consorcio","Madurez TRL requerida","Oportunidad estratégica"]],
            "tags": ["ee"]
        }
        enriched.append({
            "id":                  len(enriched) + 1,
            "source":              conv["source"],
            "title":               conv["title"],
            "description":         conv["description"],
            "match":               analysis.get("match_score", 50),
            "priority":            analysis.get("priority", "medium"),
            "descartada":          analysis.get("descartada", False),
            "motivo_descarte":     analysis.get("motivo_descarte", ""),
            "trl_min":             analysis.get("trl_min", 4),
            "trl_max":             analysis.get("trl_max", 7),
            "socio_consorcio":     analysis.get("socio_consorcio", ""),
            "deadline":            conv["deadline_days"],
            "deadline_date":       conv["deadline_date"],
            "open_date":           conv.get("open_date", ""),
            "fecha_sin_confirmar": conv.get("fecha_sin_confirmar", False),
            "fecha_prevista":      conv.get("fecha_prevista", False),
            "budget_raw":          0,
            "url":                 conv["url"],
            "org":                 conv["org"],
            "tags":                analysis.get("tags", ["ee"]),
            "summary":             post_procesar_texto(analysis.get("resumen", "")),
            "action":              post_procesar_texto(analysis.get("accion", "")),
            "dims":                analysis.get("dimensiones", []),
            "keywords_found":      conv["keywords_found"],
            "source_type":         conv["source_type"],
            "discovered_via":      conv.get("discovered_via", ""),
            "catalog_scope":       conv.get("catalog_scope", ""),
            "catalog_category":    conv.get("catalog_category", ""),
            "catalog_ref":         conv.get("catalog_ref", ""),
            "bdns_id":             conv.get("bdns_id", ""),
            "bdns_url":            conv.get("bdns_url", ""),
            "related_documents_count": conv.get("related_documents_count", 0),
            "related_documents":   conv.get("related_documents_trace", []),
            "document_role":       conv.get("document_role", ""),
            "programme_key":       conv.get("programme_key", ""),
            "programme_name":      conv.get("programme_name", ""),
            "url_generica":        conv.get("url_generica", False),
            "url_rota":            False,  # se actualiza en verificar_urls() antes de publicar
        })
        if analysis.get("descartada", False):
            audit_exclusion(
                conv,
                "discarded_by_claude",
                "claude_analysis",
                {
                    "motivo_descarte": analysis.get("motivo_descarte", ""),
                    "match_score": analysis.get("match_score", 50),
                },
            )

    # 3 ── ORDENAR por match score
    enriched.sort(key=lambda x: x["match"], reverse=True)

    # 3B ── VERIFICACIÓN TÉCNICA DE URLs (antes de publicar)
    verificar_urls(enriched)

    # 4 ── GUARDAR JSON
    output = {
        "last_updated":  datetime.now(timezone.utc).isoformat(),
        "collection_seconds": round(collection_seconds, 2),
        "convocatorias": enriched,
        "stats":         build_stats(
            enriched,
            detected_total=all_raw_pre,
            closed_total=n_cerradas,
        ),
        "sources":       build_source_status(
            raw_by_source,
            conteo_cerradas_por_fuente,
            source_timings,
        ),
        "keywords":      build_keywords(enriched),
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    save_discovery_audit(
        run_started_at,
        "completed",
        {name: len(items) for name, items in raw_by_source.items()},
    )

    # 5 ── RESUMEN FINAL
    print("\n" + "=" * 60)
    print(f"✓ JSON generado: {OUTPUT_FILE}")
    print(f"  Convocatorias detectadas:   {output['stats']['detected']}")
    print(f"  Convocatorias vigentes:     {output['stats']['active']}")
    print(f"  Descartadas por Claude:     {output['stats']['discarded']}")
    print(f"  Relevantes para Kalfrisa:   {output['stats']['relevant']}")
    print(f"  Alta compatibilidad (≥80%): {output['stats']['high']}")
    print(f"  Cierre urgente (<30d):      {output['stats']['urgent']}")
    print("=" * 60)

    print(f"✓ Archivo guardado en: {os.path.abspath(OUTPUT_FILE)}")

    # ── SUBIDA AUTOMÁTICA A GITHUB PAGES ──────────────────────────────
    github_upload(OUTPUT_FILE)


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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_pipeline(no_claude=args.no_claude)
