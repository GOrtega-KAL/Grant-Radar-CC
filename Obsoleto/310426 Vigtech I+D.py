# ╔══════════════════════════════════════════════════════════════════╗
# ║  VigTech I+D — Backend Kalfrisa · Versión Google Colab          ║
# ║  Ejecuta cada celda en orden de arriba a abajo                  ║
# ╚══════════════════════════════════════════════════════════════════╝


# ─────────────────────────────────────────────────────────────────────
# CELDA 1 — INSTALACIÓN DE LIBRERÍAS Y CONFIGURACIÓN DEL ENTORNO
# ⚠ EJECUTAR ESTA CELDA PRIMERO, ANTES QUE CUALQUIER OTRA
# ─────────────────────────────────────────────────────────────────────

#Ejecutar en el terminal de VSCode para usar Poetry como interprete
#cd C:\Users\guillermo.ortega\Desktop\Guillermo\Grant-Radar
#poetry config virtualenvs.in-project true
#poetry add requests feedparser beautifulsoup4 anthropic

#Para ejecutar el código en VSCode:
#poetry run python "260402 vigtech_colab.py"


# ─────────────────────────────────────────────────────────────────────
# CELDA 2 — IMPORTS Y CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────

import os
import json
import time
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from collections import Counter

import requests
import feedparser
from bs4 import BeautifulSoup
import anthropic

# ── MONTAR GOOGLE DRIVE (para caché persistente entre sesiones) ───────
try:
    from google.colab import drive
    if not os.path.exists("/content/drive/MyDrive"):
        print("Montando Google Drive para caché persistente...")
        drive.mount("/content/drive", force_remount=False)
except Exception:
    pass  # Fuera de Colab o ya montado — continuar sin Drive

# ── TU API KEY DE CLAUDE (Anthropic) ─────────────────────────────────
# Obtén la tuya en: https://console.anthropic.com/settings/keys
CLAUDE_API_KEY = "Placeholder"
# ── MODELO Y PARÁMETROS ───────────────────────────────────────────────
CLAUDE_MODEL   = "claude-haiku-4-5"        # Haiku 4.5 — $1/$5 por millón de tokens
CLAUDE_SLEEP_S = 1                         # 1s entre llamadas (Claude no tiene RPM estricto)

# ── RUTAS DE ARCHIVOS ─────────────────────────────────────────────────
# Rutas adaptadas automáticamente a Colab, Windows y Linux/Mac local
_DRIVE = "/content/drive/MyDrive/VigTech"

if os.path.exists("/content/drive/MyDrive"):       # Colab + Drive montado
    BASE_DIR = _DRIVE
elif os.path.exists("/content"):                   # Colab sin Drive
    BASE_DIR = "/content"
else:                                               # Local (Windows/Linux/Mac)
    BASE_DIR = os.path.join(os.getcwd(), "vigtech_data")

os.makedirs(BASE_DIR, exist_ok=True)
DRIVE_AVAILABLE = os.path.exists("/content/drive/MyDrive")
OUTPUT_FILE     = os.path.join(BASE_DIR, "convocatorias.json")
CACHE_FILE      = os.path.join(BASE_DIR, "vigtech_cache.json")

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
log = logging.getLogger("vigtech")

# Mensaje de inicio según entorno detectado
if DRIVE_AVAILABLE:
    print(f"✓ Google Drive montado — archivos en {BASE_DIR}")
elif os.path.exists("/content"):
    print(f"⚠ Google Drive no montado — usando almacenamiento local Colab (no persiste)")
    print("  Para persistencia: Entorno → Conectar con Google Drive")
else:
    print(f"✓ Ejecución local — archivos en: {BASE_DIR}")

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

def safe_get(url: str, timeout: int = 15) -> Optional[requests.Response]:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "VigTech-Bot/1.0"})
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning(f"Error fetching {url}: {e}")
        return None

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

def cache_load() -> dict:
    """Carga la caché de convocatorias ya analizadas por Claude Haiku."""
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def cache_save(cache: dict):
    """Guarda la caché actualizada."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"No se pudo guardar caché: {e}")

def cache_key(conv: dict) -> str:
    """Genera una clave única para cada convocatoria basada en título y fuente."""
    raw = f"{conv['source']}::{conv['title'][:80]}".lower()
    # Hash simple para clave corta
    return str(abs(hash(raw)) % 10**10)

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


# Códigos numéricos de estado en la SEDIA API (confirmados en celda F)
_SEDIA_STATUS_OPEN        = "31094501"
_SEDIA_STATUS_FORTHCOMING = "31094502"
_SEDIA_STATUS_CLOSED      = "31094503"
# frameworkProgramme Horizon Europe 2021-2027
_SEDIA_HORIZON_PROGRAMME  = "43108390"


def fetch_horizon_europe() -> list:
    """
    Horizon Europe — SEDIA Search API (backend oficial del portal F&T de la CE).
    NOTA ESTRUCTURA (verificada en diagnóstico):
    - Los datos reales están en item["metadata"], no en item directamente.
    - Todos los valores de metadata son LISTAS → usar _sedia_meta() para extraer.
    - El filtro de status debe hacerse en Python por código numérico (el parámetro
      facets de la API no filtra correctamente — devuelve igual todos los estados).
    - item["title"] es siempre None; el título real está en metadata["title"].
    """
    log.info("Consultando Horizon Europe (SEDIA API oficial)...")
    results = []

    # Búsqueda amplia — el filtrado real se hace en Python por status y keywords
    search_text = (
        "hydrogen industrial furnaces decarbonization "
        "energy efficiency thermal industrial emissions NOx "
        "waste heat combustion clean combustion industrial process"
    )

    # PAGINACIÓN MULTI-PÁGINA (diagnóstico confirmó que la SEDIA API no filtra por status).
    # La API ordena por relevancia textual → topics cerrados dominan las primeras páginas.
    # Paginamos hasta MAX_PAGES para barrer más resultados y filtrar open en Python.
    # Fuera de periodos de convocatoria activa (sept-nov, feb-abr) es normal obtener 0.
    MAX_PAGES = 10
    all_docs = []
    for page in range(1, MAX_PAGES + 1):
        params = {
            "apiKey":     "SEDIA",
            "text":       search_text,
            "pageNumber": str(page),
            "pageSize":   "100",
            "language":   "en",
        }
        try:
            resp = requests.post(
                "https://api.tech.ec.europa.eu/search-api/prod/rest/search",
                params=params,
                headers={"Accept": "application/json", "User-Agent": "VigTech-Bot/1.0"},
                timeout=25,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning(f"Horizon SEDIA API error (p{page}): {e}")
            break
        docs_page = data.get("results", [])
        if not docs_page:
            break
        all_docs.extend(docs_page)
        total = data.get("totalResults", 0)
        log.info(f"  SEDIA p{page}: {len(docs_page)} docs ({len(all_docs)}/{total} acumulados)")
        if len(all_docs) >= total:
            break
        time.sleep(0.3)

    if not all_docs:
        log.warning("Horizon SEDIA: sin resultados en ninguna página")
        return []
    log.info(f"  SEDIA: filtrando {len(all_docs)} docs para status open/forthcoming...")

    seen = set()
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
            continue

        # ── Filtro 3: relevancia por keywords ─────────────────────────
        if not is_relevant(combined):
            continue
        seen.add(combined)

        deadline_raw  = _sedia_meta(item, "deadlineDate")
        deadline_days = _days_until(deadline_raw[:10] if deadline_raw else "")
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
            "fecha_sin_confirmar":  False,
            "budget":               budget_str,
            "url":                  (item.get("url") or
                                    f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{identifier}"),
            "keywords_found":       keyword_match(combined),
            "org":                  "Comisión Europea / Horizon Europe",
            "source_type":          "SEDIA API",
        })

    log.info(f"  → {len(results)} convocatorias Horizon abiertas relevantes")
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


def _scrape_cdti_deadline(url: str) -> int:
    """Intenta extraer días restantes scrapeando la página de la convocatoria CDTI."""
    if not url:
        return 90
    resp = safe_get(url)
    if not resp:
        return 90
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup.find_all(["span", "div", "p"]):
            text = tag.get_text()
            if "cierre" in text.lower() or "plazo" in text.lower():
                matches = re.findall(r"\d{2}[/-]\d{2}[/-]\d{4}", text)
                for m in matches:
                    try:
                        dt = datetime.strptime(m.replace("-", "/"), "%d/%m/%Y")
                        return max(0, (dt.date() - datetime.now().date()).days)
                    except Exception:
                        pass
    except Exception as e:
        log.debug(f"No se pudo extraer deadline CDTI: {e}")
    return 90


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


def fetch_cdti() -> list:
    """
    CDTI — datos estáticos actualizados manualmente.

    CONTEXTO TÉCNICO: cdti.es, infosubvenciones.es (BDNS) y sede.cdti.gob.es
    son SPAs Angular que requieren ejecución de JavaScript para renderizar contenido.
    requests+BeautifulSoup solo obtiene el HTML shell vacío. Sin Playwright/Selenium
    no es posible el scraping automatizado.

    MANTENIMIENTO: Revisar y actualizar esta función cuando:
      - Se abra una nueva convocatoria CDTI relevante para Kalfrisa
      - Cambie el estado (abierta/cerrada) de alguna de las listadas
      - Se publique el calendario definitivo de convocatorias del año en curso
    Fuente de referencia: https://www.cdti.es/calendario-de-convocatorias
    Última revisión: 2026-04-09
    """
    log.info("Cargando convocatorias CDTI (datos estáticos curados)...")

    today = datetime.now().date()

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
            "fecha_prevista":      fecha_prevista if 'fecha_prevista' in dir() else False,
            "budget":              c["budget"],
            "url":                 c["url"],
            "keywords_found":      c["keywords"],
            "org":                 "CDTI — Centro para el Desarrollo Tecnológico Industrial",
            "source_type":         "Catálogo curado",
        })

    log.info(f"  → {len(results)} convocatorias CDTI cargadas (datos curados)")
    return results


def fetch_boa() -> list:
    """
    BOA (Boletín Oficial de Aragón) — datos estáticos + intento de scraping.

    El dominio boa.aragon.es resuelve en ejecución local pero el motor de búsqueda
    CGI devuelve resultados en formato tabla sin keywords relevantes en la mayoría
    de ejecuciones. Se mantiene el intento de scraping como primera estrategia
    y se añaden datos estáticos curados como garantía de cobertura.

    MANTENIMIENTO del catálogo estático: revisar cuando se publiquen nuevas
    convocatorias del Gobierno de Aragón relevantes para industria/energía.
    Fuente: https://www.aragon.es/temas/industria-energia-mineria/ayudas-subvenciones
    y https://www.boa.aragon.es
    Última revisión: 2026-04-09
    """
    log.info("Consultando BOA/Aragón (scraping + datos curados)...")
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

    # Cargar datos estáticos primero como base garantizada
    for c in _BOA_STATIC:
        close_str       = c.get("deadline_date", "")
        open_str        = c.get("open_date", "")
        es_prevista     = c.get("fecha_prevista", False)
        deadline_days   = _days_until(close_str) if close_str else 120
        if deadline_days <= 0 and not es_prevista:
            log.debug(f"  BOA estático: descartando cerrada: {c['title'][:60]}")
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
    log.info(f"  BOA: {len(results)} convocatorias cargadas (datos curados)")

    # ── Intento de scraping en vivo (complementario) ──────────────────
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Referer": "https://www.aragon.es/",
    }

    boa_targets = [
        {
            "url": "https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI?CMD=VERDOC&BASE=BODA&DOCS=1-20&SEPARADOR=&&RANG-C=20240101-&TEXT-TEXT=eficiencia+energetica+industria",
            "type": "boa_tabla",
            "base": "https://www.boa.aragon.es",
        },
        {
            "url": "https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI?CMD=VERDOC&BASE=BODA&DOCS=1-20&SEPARADOR=&&RANG-C=20240101-&TEXT-TEXT=hidrogeno+industria",
            "type": "boa_tabla",
            "base": "https://www.boa.aragon.es",
        },
    ]

    seen_titles = {r["title"] for r in results}
    scraping_found = 0

    for target in boa_targets:
        try:
            resp = requests.get(target["url"], timeout=12, headers=headers)
            if resp.status_code != 200 or len(resp.text) < 500:
                continue
        except Exception as e:
            log.warning(f"  BOA scraping no accesible: {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            title = cells[0].get_text(strip=True)
            a_tag = cells[0].find("a")
            link  = (target["base"] + a_tag["href"]) if a_tag else target["base"]
            if not title or title in seen_titles or not is_relevant(title):
                continue
            seen_titles.add(title)
            results.append({
                "source":              "BOA ARAGÓN",
                "title":               title,
                "description":         "",
                "deadline_days":       60,
                "deadline_date":       "",
                "open_date":           "",
                "fecha_sin_confirmar": True,
                "budget":              "Ver disposición",
                "url":                 link,
                "keywords_found":      keyword_match(title),
                "org":                 "Gobierno de Aragón",
                "source_type":         "Web Scraping BOA",
            })
            scraping_found += 1

    if scraping_found:
        log.info(f"  BOA scraping: {scraping_found} convocatorias adicionales")

    log.info(f"  → {len(results)} convocatorias BOA totales")
    return results


def _scrape_idae_dates(url: str) -> tuple[str, str]:
    """
    Entra en la página de detalle de una convocatoria IDAE e intenta extraer
    las fechas de apertura y cierre del plazo.
    Devuelve (open_date, deadline_date) en formato YYYY-MM-DD o cadena vacía si no se encuentra.
    El IDAE publica estas fechas en distintos formatos según la página:
      - "Plazo de solicitud: DD/MM/YYYY al DD/MM/YYYY"
      - "Inicio del plazo: DD/MM/YYYY" / "Fin del plazo: DD/MM/YYYY"
      - Tablas con etiquetas "Fecha de inicio" / "Fecha de fin"
    """
    resp = safe_get(url)
    if not resp:
        return "", ""
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator=" ", strip=True)

        # Patrón 1: "del DD/MM/YYYY al DD/MM/YYYY" o "DD/MM/YYYY - DD/MM/YYYY"
        range_match = re.search(
            r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})\s*(?:al|a|-|–)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
            text
        )
        if range_match:
            def to_iso(s):
                for fmt in ["%d/%m/%Y", "%d-%m-%Y"]:
                    try:
                        return datetime.strptime(s.replace("-", "/"), "%d/%m/%Y").strftime("%Y-%m-%d")
                    except Exception:
                        pass
                return ""
            return to_iso(range_match.group(1)), to_iso(range_match.group(2))

        # Patrón 2: etiquetas explícitas
        dates = {}
        for label, key in [
            (r"(?:inicio|apertura|comienzo).*?(\d{1,2}[/-]\d{1,2}[/-]\d{4})", "open"),
            (r"(?:fin|cierre|plazo|vencimiento).*?(\d{1,2}[/-]\d{1,2}[/-]\d{4})", "close"),
        ]:
            m = re.search(label, text, re.IGNORECASE)
            if m:
                try:
                    dates[key] = datetime.strptime(
                        m.group(1).replace("-", "/"), "%d/%m/%Y"
                    ).strftime("%Y-%m-%d")
                except Exception:
                    pass
        return dates.get("open", ""), dates.get("close", "")
    except Exception:
        return "", ""


def fetch_idae() -> list:
    """Web scraping del portal del IDAE con URLs actualizadas."""
    log.info("Consultando IDAE (web scraping)...")
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
        resp = safe_get(url)
        if resp:
            soup = BeautifulSoup(resp.text, "html.parser")
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
        if not is_relevant(title):
            continue
        # Filtrar documentos/guías que no son convocatorias
        if _IDAE_NOISE.match(title):
            skipped_noise += 1
            continue
        seen.add(title)

        link = a["href"]
        if not link.startswith("http"):
            link = "https://www.idae.es" + link

        # Extraer fechas de apertura y cierre de la página de detalle
        open_date, deadline_date = _scrape_idae_dates(link)
        deadline_days = _days_until(deadline_date) if deadline_date else None

        # Descartar convocatorias cuyo plazo ya haya cerrado
        if deadline_date and deadline_days is not None and deadline_days <= 0:
            log.debug(f"  IDAE: descartando cerrada (close={deadline_date}): {title[:60]}")
            skipped_closed += 1
            continue

        # Si no tenemos fecha de cierre, usamos fallback de 30 días
        # y marcamos que la fecha no está confirmada
        fecha_sin_confirmar = not bool(deadline_date)
        if deadline_days is None:
            deadline_days = 30

        results.append({
            "source":               "IDAE",
            "title":                title,
            "description":          "",
            "deadline_days":        deadline_days,
            "deadline_date":        deadline_date,
            "open_date":            open_date,
            "fecha_sin_confirmar":  fecha_sin_confirmar,
            "budget":               "Ver convocatoria",
            "url":                  link,
            "keywords_found":       keyword_match(title),
            "org":                  "Instituto para la Diversificación y Ahorro de la Energía",
            "source_type":          "Web Scraping",
        })

    log.info(f"  → {len(results)} convocatorias IDAE válidas "
             f"(descartadas: {skipped_closed} cerradas, {skipped_noise} documentos)")
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


def fetch_boe() -> list:
    """
    BOE — búsqueda en ayudas.php.
    Estructura HTML verificada en diagnóstico (celda E/F):
    - Clases reales: 'ayuda', 'ayudaBD' (no 'resultado' como se asumía antes)
    - Cada bloque .ayuda contiene el texto descriptivo y un enlace 'Ir al documento'
    - listadoResult tiene hijos NavigableString, no tags directos — no iterar sobre él
    """
    log.info("Consultando BOE (ayudas.php)...")
    results = []
    resp = safe_get("https://www.boe.es/buscar/ayudas.php")

    if not resp:
        log.warning("BOE: página de ayudas no accesible")
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    seen = set()

    # ── Parser principal: bloques con clase "ayuda" o "ayudaBD" ──────
    bloques = soup.find_all(class_=lambda c: c and "ayuda" in (c if isinstance(c, str) else " ".join(c)).split())
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

        results.append({
            "source":         "BOE / MITECO",
            "title":          title,
            "description":    texto_completo[:600],
            "deadline_days":  45,
            "deadline_date":  "",
            "budget":         "Ver disposición",
            "url":            href,
            "keywords_found": keyword_match(combined),
            "org":            "Boletín Oficial del Estado",
            "source_type":    "Web BOE",
        })

    # ── Fallback: enlaces directos a documentos BOE ───────────────────
    if not results:
        log.info("  BOE: clase 'ayuda' no encontrada — fallback por enlaces a documentos")
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
                "source_type":    "Web BOE",
            })

    log.info(f"  → {len(results)} convocatorias BOE relevantes")
    return results


print("✓ Funciones de fuentes cargadas")


# ─────────────────────────────────────────────────────────────────────
# CELDA 5 — ANÁLISIS CON CLAUDE HAIKU 4.5 (Anthropic)
# ─────────────────────────────────────────────────────────────────────

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
            return json.loads(raw.strip())

        except json.JSONDecodeError as e:
            log.error(f"JSON inválido de Claude para '{conv['title'][:50]}': {e}")
            break  # JSON inválido no se resuelve reintentando

        except Exception as e:
            err_str = str(e)
            if "529" in err_str or "overloaded" in err_str.lower() or "rate" in err_str.lower():
                wait_secs = 30 * (attempt + 1)
                log.warning(f"  Claude sobrecargado. Esperando {wait_secs}s (intento {attempt+1}/{max_retries})...")
                time.sleep(wait_secs)
            else:
                log.error(f"Error Claude para '{conv['title'][:50]}': {e}")
                break

    # Fallback si todos los intentos fallan
    return {
        "match_score": 50,
        "priority":    "medium",
        "resumen":     "Análisis no disponible temporalmente.",
        "accion":      "Revisar manualmente.",
        "dimensiones": [
            {"name": "Alineación tecnológica", "val": 50},
            {"name": "Capacidad de consorcio",  "val": 50},
            {"name": "Madurez TRL requerida",   "val": 50},
            {"name": "Oportunidad estratégica", "val": 50},
        ],
        "tags": ["ee"]
    }

print("✓ Función de análisis Claude Haiku 4.5 cargada")


# ─────────────────────────────────────────────────────────────────────
# CELDA 6 — FUNCIONES DE ENSAMBLADO DEL JSON FINAL
# ─────────────────────────────────────────────────────────────────────

def build_stats(convocatorias: list) -> dict:
    active = len(convocatorias)
    high   = sum(1 for c in convocatorias if c.get("match", 0) >= 80)
    urgent = sum(1 for c in convocatorias if c.get("deadline", 99) < 30)
    budget = sum(
        float(str(c.get("budget_raw", 0)).replace("€", "").replace("M", "").strip() or 0)
        for c in convocatorias
    )
    return {"active": active, "high": high, "urgent": urgent, "budget": round(budget, 1)}


def build_source_status(results_by_source: dict) -> list:
    source_meta = {
        "HORIZON EUROPE": "API REST",
        "CDTI":           "Catálogo curado",
        "IDAE":           "Web Scraping",
        "BOE / MITECO":   "API BOE",
        "BOA ARAGÓN":     "Catálogo curado",
    }
    now_str = datetime.now().strftime("%H:%M")
    return [
        {
            "name":   name,
            "type":   stype,
            "status": "ok" if len(results_by_source.get(name, [])) > 0 else "warn",
            "count":  len(results_by_source.get(name, [])),
            "time":   f"actualizado {now_str}",
        }
        for name, stype in source_meta.items()
    ]


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
# CELDA 6B — CONFIGURACIÓN GITHUB PAGES Y FUNCIÓN DE SUBIDA
# ─────────────────────────────────────────────────────────────────────

# ── CONFIGURACIÓN GITHUB ──────────────────────────────────────────────
GITHUB_TOKEN = "Placeholder"  # ⚠ Revoca el anterior en github.com/settings/tokens y pon el nuevo aquí
GITHUB_USER  = "GOrtega-KAL"            # Tu usuario de GitHub
GITHUB_REPO  = "Grant-Radar"                   # Nombre del repositorio
GITHUB_BRANCH = "main"                  # Rama donde está GitHub Pages

def github_upload(filepath: str):
    """
    Sube el convocatorias.json al repositorio GitHub usando la API REST.
    GitHub Pages servirá automáticamente el archivo actualizado.
    """
    if GITHUB_TOKEN == "TU_GITHUB_TOKEN_AQUI":
        print("⚠ GitHub Token no configurado — saltar subida automática")
        print("  Configura GITHUB_TOKEN en la CELDA 6B para activar GitHub Pages")
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
        "message": f"VigTech: actualización automática {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC",
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

def run_pipeline():
    print("=" * 60)
    print("VigTech I+D — Iniciando pipeline")
    print("=" * 60)

    if CLAUDE_API_KEY == "TU_API_KEY_AQUI":
        print("⚠ ERROR: Pon tu API key de Claude en la CELDA 2 antes de continuar.")
        print("  Obtén la tuya en: https://console.anthropic.com/settings/keys")
        return

    # 1 ── RECOLECCIÓN DE FUENTES
    raw_by_source = {
        "HORIZON EUROPE": fetch_horizon_europe(),
        "CDTI":           fetch_cdti(),
        "IDAE":           fetch_idae(),
        "BOE / MITECO":   fetch_boe(),
        "BOA ARAGÓN":     fetch_boa(),
    }

    all_raw = [item for items in raw_by_source.values() for item in items]
    print(f"\nTotal convocatorias detectadas antes de filtros: {len(all_raw)}")

    # ── Filtro defensivo: eliminar convocatorias con plazo ya cerrado ──
    # Puede ocurrir si la caché contiene topics cerrados de ejecuciones
    # anteriores o si el scraper extrae páginas históricas.
    all_raw_pre = len(all_raw)
    all_raw = [c for c in all_raw if c.get("deadline_days", 1) > 0]
    n_cerradas = all_raw_pre - len(all_raw)
    if n_cerradas:
        log.info(f"  Filtradas {n_cerradas} convocatorias con plazo cerrado (deadline_days ≤ 0)")
    print(f"Total tras filtrar cerradas: {len(all_raw)}")

    if not all_raw:
        print("⚠ No se detectaron convocatorias. Revisa conectividad y keywords.")
        return

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
        analysis = analyze_with_claude(conv)
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
            "summary":             analysis.get("resumen", ""),
            "action":              analysis.get("accion", ""),
            "dims":                analysis.get("dimensiones", []),
            "keywords_found":      conv["keywords_found"],
            "source_type":         conv["source_type"],
        })

    # 3 ── ORDENAR por match score
    enriched.sort(key=lambda x: x["match"], reverse=True)

    # 4 ── GUARDAR JSON
    output = {
        "last_updated":  datetime.now(timezone.utc).isoformat(),
        "convocatorias": enriched,
        "stats":         build_stats(enriched),
        "sources":       build_source_status(raw_by_source),
        "keywords":      build_keywords(enriched),
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 5 ── RESUMEN FINAL
    print("\n" + "=" * 60)
    print(f"✓ JSON generado: {OUTPUT_FILE}")
    print(f"  Convocatorias totales:      {output['stats']['active']}")
    print(f"  Alta compatibilidad (≥80%): {output['stats']['high']}")
    print(f"  Cierre urgente (<30d):      {output['stats']['urgent']}")
    print("=" * 60)

    # Descarga del JSON y subida automática a GitHub Pages
    try:
        from google.colab import files
        files.download(OUTPUT_FILE)
        print("✓ Descarga de convocatorias.json iniciada")
    except ImportError:
        print(f"✓ Archivo guardado en: {os.path.abspath(OUTPUT_FILE)}")

    # ── SUBIDA AUTOMÁTICA A GITHUB PAGES ──────────────────────────────
    github_upload(OUTPUT_FILE)


# ── EJECUTAR ──────────────────────────────────────────────────────────
run_pipeline()
