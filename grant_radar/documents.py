# documents.py — recuperación de documentos oficiales y su caché de texto
#
# Cuando una convocatoria enlaza sus bases, su extracto o una modificación, el
# análisis mejora mucho leyendo esos documentos y no solo la ficha. Este módulo
# los descarga, extrae el texto (HTML o PDF) y lo guarda en una caché propia,
# separada de la caché de análisis de Claude y de la documental de BDNS.
#
# Tres invariantes que conviene no romper:
#
# - La caché guarda solo texto de documentos oficiales estables, nunca
#   decisiones de IA, y puede escribirse en `--no-claude`: evita volver a
#   descargar y a extraer los mismos PDF en cada ejecución.
# - Una respuesta sin texto extraíble (un PDF escaneado, por ejemplo) se
#   registra como fallo durante `SOURCE_DOCUMENT_FAILURE_RETRY_DAYS` días, para
#   no reintentarla en cada ejecución; después se vuelve a intentar.
# - Los límites de tamaño son deliberados: un documento enorme no debe agotar
#   la memoria ni el tiempo de una recopilación.
#
# La ruta de la caché se calcula aquí, a partir de la posición del paquete, y
# el script principal la importa: así existe en un solo sitio, sin arriesgar
# que módulo y script escriban en ficheros distintos.

import hashlib
import io
import json
import logging
import os
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from grant_radar.cache import cache_key
from grant_radar.dedup import _document_role
from grant_radar.http_client import _http_get, _is_safe_public_https_url
from grant_radar.parsing_helpers import _fold_text, select_evidence_excerpt
from grant_radar.runtime_state import RUN_DIAGNOSTICS

log = logging.getLogger("grant_radar")

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DOCUMENT_CACHE_FILE = os.path.join(
    _PROJECT_DIR, "grant_radar_data", "source_document_cache.json"
)
SOURCE_DOCUMENT_CACHE_VERSION = "source-document-text-2026-08-v1"
SOURCE_DOCUMENT_MAX_PER_CALL = 3
SOURCE_DOCUMENT_MAX_BYTES = 12 * 1024 * 1024
SOURCE_DOCUMENT_MAX_TOTAL_BYTES = 16 * 1024 * 1024
SOURCE_DOCUMENT_FAILURE_RETRY_DAYS = 30
# Límites de extracción por documento, compartidos con la recuperación de
# evidencia para los holds de BDNS, que sigue en Grant-Radar-prueba.py.
BDNS_HOLD_MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
BDNS_HOLD_MAX_EVIDENCE_CHARS = 48_000


def _html_to_text(html: str, max_chars: int) -> str:
    """El texto legible de un documento HTML, sin navegación ni scripts.

    Se separó de `_hold_document_text()` el 02/09/2026 porque hay dos formas de
    llegar al mismo HTML: la normal, con `requests`, y el segundo intento con
    Chromium para hosts cuya cadena de certificados está incompleta
    (`browser_document_text()`). Las dos tienen que extraer igual, o el mismo
    documento daría textos distintos según por dónde entrara.
    """
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return " ".join(main.get_text(" ", strip=True).split())[:max_chars]


def browser_document_text(browser, url: str, max_chars: int) -> str:
    """Segundo intento con Chromium cuando `requests` no puede verificar el TLS.

    **Qué problema resuelve, medido el 02/09/2026** (punto 38 del backlog):
    `boletin.dpz.es` —el Boletín Oficial de la provincia de Zaragoza, la de la
    propia empresa— envía **un solo certificado**, el suyo, sin el intermedio
    que completa la cadena. `requests` no puede verificarlo y descarta el
    documento; Chromium, que lleva su propio almacén y sabe completar cadenas
    incompletas, abre las mismas dos URLs con **HTTP 200** y devuelve el texto
    oficial del edicto.

    El backlog planteaba esto como una elección entre añadir un paquete de CA
    —que hay que mantener— y relajar la verificación TLS —que contradice
    `_is_safe_public_https_url()` y es la peor idea de las dos—. La medición
    enseña una tercera vía que no exige ninguna de las dos cosas: **no se
    relaja nada**, se usa un cliente que verifica mejor.

    Dos límites, deliberados:

    - **`status()` antes que `html()`.** `html()` devuelve "" tanto ante un 404
      como ante un bloqueo, así que sin comprobar el código se colaría la
      página de error de un portal como si fuera evidencia oficial.
    - **Solo HTML.** Un PDF no se puede recuperar así, y un PDF servido tras
      una cadena rota sigue perdiéndose. Hoy los dos documentos afectados son
      HTML; si algún día son PDF, esto no los salva y hay que saberlo.
    """
    if browser is None:
        return ""
    try:
        if browser.status(url) != 200:
            return ""
        return _html_to_text(browser.html(url), max_chars)
    except Exception as exc:
        log.warning(f"Segundo intento con navegador fallido para {url}: {exc}")
        return ""


def _hold_document_text(
    response: requests.Response,
    url: str,
    max_bytes: int = BDNS_HOLD_MAX_DOCUMENT_BYTES,
    max_chars: int = BDNS_HOLD_MAX_EVIDENCE_CHARS,
) -> tuple[str, str]:
    """
    Extrae texto acotado de HTML, texto plano o PDF oficial.

    `max_chars` existe porque un documento puede ser mucho mayor que la
    evidencia que interesa de él, y el corte por defecto es el adecuado para
    las bases de una convocatoria. Los Anexos Generales de Horizon son la
    excepción medida: 46 páginas y 124.411 caracteres, con las tasas de
    financiación en la página 32 —muy por detrás del corte de 48.000— aunque
    las condiciones de elegibilidad estén en las primeras (AGENTS.md 59).
    Quien necesite leer más lejos lo pide explícitamente; nadie hereda un
    documento más grande sin saberlo.
    """
    content = response.content[:max_bytes]
    content_type = response.headers.get("content-type", "").casefold()
    is_pdf = "pdf" in content_type or content.startswith(b"%PDF")
    if is_pdf:
        try:
            reader = PdfReader(io.BytesIO(content), strict=False)
            pages = []
            for page in reader.pages[:80]:
                page_text = " ".join(str(page.extract_text() or "").split())
                if page_text:
                    pages.append(page_text)
                if sum(len(value) for value in pages) >= max_chars:
                    break
            return " ".join(pages)[:max_chars], "pdf"
        except Exception as exc:
            log.warning(f"No se pudo extraer PDF de {url}: {exc}")
            return "", "pdf_error"
    if "html" in content_type or b"<html" in content[:500].lower():
        encoding = response.encoding or "utf-8"
        return _html_to_text(content.decode(encoding, errors="replace"), max_chars), "html"
    if "text" in content_type or "json" in content_type or "xml" in content_type:
        return " ".join(response.text.split())[:max_chars], "text"
    return "", "unsupported"


_SOURCE_DOCUMENT_CACHE_STATE = {"path": "", "entries": {}}


def _load_source_document_cache() -> dict:
    """Carga evidencia estable de fuentes web, separada de BDNS y de la IA."""
    path = os.path.abspath(SOURCE_DOCUMENT_CACHE_FILE)
    if _SOURCE_DOCUMENT_CACHE_STATE["path"] == path:
        return _SOURCE_DOCUMENT_CACHE_STATE["entries"]
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        payload = {}
    meta = payload.get("_meta", {}) if isinstance(payload, dict) else {}
    entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
    if (
        meta.get("version") != SOURCE_DOCUMENT_CACHE_VERSION
        or not isinstance(entries, dict)
    ):
        entries = {}
    _SOURCE_DOCUMENT_CACHE_STATE["path"] = path
    _SOURCE_DOCUMENT_CACHE_STATE["entries"] = entries
    return entries


def _save_source_document_cache(entries: dict) -> None:
    payload = {
        "_meta": {
            "version": SOURCE_DOCUMENT_CACHE_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "content": "public_official_source_document_text",
        },
        "entries": entries,
    }
    temporary = SOURCE_DOCUMENT_CACHE_FILE + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporary, SOURCE_DOCUMENT_CACHE_FILE)


def _source_document_cache_key(source: str, document: dict) -> str:
    identity = {
        "source": _fold_text(source),
        "url": re.sub(r"#.*$", "", str(document.get("url", "")).strip()),
    }
    return hashlib.sha256(json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _official_document_priority(document: dict) -> tuple:
    role = _document_role(document)
    scores = {
        "call": 100,
        "call_extract": 95,
        "amendment": 90,
        "regulatory_bases": 80,
    }
    return scores.get(role, 0), str(document.get("title", ""))


def enrich_with_official_documents(
    call: dict,
    candidates: list[dict],
    source: str,
    session: requests.Session | None = None,
) -> dict:
    """Añade, con límites y caché, bases/convocatoria/modificaciones oficiales.

    Solo se invoca después de demostrar que la convocatoria está vigente o
    próxima. No descarga guías, fichas comerciales ni todos los adjuntos de una
    página. La ausencia o el fallo de un documento no elimina la convocatoria.
    """
    allowed_roles = {"call", "call_extract", "amendment", "regulatory_bases"}
    selected = []
    seen_urls = set()
    for document in sorted(candidates, key=_official_document_priority, reverse=True):
        url = re.sub(r"#.*$", "", str(document.get("url", "")).strip())
        role = _document_role(document)
        if (
            role not in allowed_roles
            or not _is_safe_public_https_url(url)
            or url in seen_urls
        ):
            continue
        seen_urls.add(url)
        selected.append({**document, "url": url, "document_role": role})
        if len(selected) >= SOURCE_DOCUMENT_MAX_PER_CALL:
            break

    metrics = RUN_DIAGNOSTICS.setdefault(
        "official_document_enrichment", {}
    ).setdefault(source, {
        "calls_considered": 0,
        "documents_selected": 0,
        "cache_hits": 0,
        "negative_cache_hits": 0,
        "network_fetches": 0,
        "documents_attached": 0,
        "errors": 0,
        "bytes_downloaded": 0,
    })
    metrics["calls_considered"] += 1
    metrics["documents_selected"] += len(selected)
    if not selected:
        return call

    cache = _load_source_document_cache()
    client = session or requests.Session()
    cache_changed = False
    downloaded_bytes = 0
    contents = list(call.get("related_document_contents", []))
    content_urls = {str(item.get("url", "")) for item in contents}
    for document in selected:
        if downloaded_bytes >= SOURCE_DOCUMENT_MAX_TOTAL_BYTES:
            break
        url = document["url"]
        cache_key = _source_document_cache_key(source, document)
        cached = cache.get(cache_key, {})
        if not isinstance(cached, dict):
            cached = {}
        text = cached.get("text", "")
        document_format = cached.get("format", "")
        response_bytes = cached.get("bytes", 0)
        if isinstance(text, str) and len(text) >= 80:
            metrics["cache_hits"] += 1
        else:
            failed_at = cached.get("failed_at", "")
            try:
                failure_age = (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(failed_at)
                ).days
            except (TypeError, ValueError):
                failure_age = SOURCE_DOCUMENT_FAILURE_RETRY_DAYS
            if (
                cached.get("status") == "no_extractable_text"
                and failure_age < SOURCE_DOCUMENT_FAILURE_RETRY_DAYS
            ):
                metrics["negative_cache_hits"] += 1
                metrics["errors"] += 1
                continue
            response = _http_get(
                url,
                session=client,
                timeout=20,
                retries=2,
                headers={
                    "Accept": "application/pdf,text/html,text/plain;q=0.9,*/*;q=0.2"
                },
                max_bytes=min(
                    SOURCE_DOCUMENT_MAX_BYTES,
                    SOURCE_DOCUMENT_MAX_TOTAL_BYTES - downloaded_bytes,
                ),
            )
            metrics["network_fetches"] += 1
            if response is None or not _is_safe_public_https_url(str(response.url)):
                metrics["errors"] += 1
                continue
            response_bytes = len(response.content)
            downloaded_bytes += response_bytes
            metrics["bytes_downloaded"] += response_bytes
            text, document_format = _hold_document_text(
                response, url, SOURCE_DOCUMENT_MAX_BYTES,
            )
            if len(text) < 80:
                metrics["errors"] += 1
                cache[cache_key] = {
                    "source": source,
                    "url": url,
                    "title": document.get("title", ""),
                    "document_role": document["document_role"],
                    "format": document_format,
                    "bytes": response_bytes,
                    "text": "",
                    "status": "no_extractable_text",
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                }
                cache_changed = True
                continue
            cache[cache_key] = {
                "source": source,
                "url": url,
                "title": document.get("title", ""),
                "document_role": document["document_role"],
                "format": document_format,
                "bytes": response_bytes,
                "text": text,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            cache_changed = True

        if url in content_urls:
            continue
        excerpt = select_evidence_excerpt(
            text, call.get("title", ""), 20_000,
        )
        if not excerpt:
            metrics["errors"] += 1
            continue
        contents.append({
            "source": source,
            "title": document.get("title", "Documento oficial"),
            "url": url,
            "document_role": document["document_role"],
            "description": excerpt,
        })
        content_urls.add(url)
        metrics["documents_attached"] += 1

    if cache_changed:
        _save_source_document_cache(cache)
    call["related_document_contents"] = contents
    call["related_documents_count"] = max(
        int(call.get("related_documents_count", 0) or 0),
        len(call.get("related_documents_trace", [])),
    )
    return call
