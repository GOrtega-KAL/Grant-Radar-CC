# hold_evidence.py — evidencia oficial para resolver un hold de BDNS
#
# Cuando la matriz previa a Claude deja una convocatoria en espera por falta de
# datos —casi siempre el requisito de centro previo, que no aparece en la
# descripción corta de BDNS sino solo en las bases en PDF—, este módulo baja
# esos documentos oficiales, extrae su texto y lo devuelve acotado.
#
# Dos cosas que no son obvias:
#
# - Los PDF de `documentos` se recuperan por su identificador numérico contra
#   el endpoint oficial; el detalle de la convocatoria no trae su URL
#   (AGENTS.md sección 13, piloto v3).
# - La caché documental guarda solo texto de documentos oficiales estables, con
#   clave de URL, fecha y tipo. Nunca cachea sedes electrónicas mutables ni
#   decisiones de IA, y puede escribirse en `--no-claude`.
#
# **`intrinsic_exclusion` se recibe como parámetro.** Con los documentos
# completos delante conviene repetir el control de incompatibilidades
# intrínsecas —el límite de extractos existe para Claude y no debe ocultar un
# objeto o una lista exhaustiva de beneficiarios a una regla determinista—,
# pero esa regla es de la matriz, que sigue en `Grant-Radar-prueba.py`. El
# módulo pide la función y quien llama decide cuál pasa, igual que en el
# conector ECCP (AGENTS.md sección 35).

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone

import requests

from grant_radar.documents import (
    BDNS_HOLD_MAX_DOCUMENT_BYTES,
    BDNS_HOLD_MAX_EVIDENCE_CHARS,
    _hold_document_text,
    browser_document_text,
)
from grant_radar.http_client import _http_get, _is_safe_public_https_url
from grant_radar.parsing_helpers import _fold_text, select_evidence_excerpt

log = logging.getLogger("grant_radar")

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BDNS_DOCUMENT_CACHE_FILE = os.path.join(
    _PROJECT_DIR, "grant_radar_data", "bdns_document_cache.json"
)
BDNS_DOCUMENT_CACHE_VERSION = "bdns-document-text-2026-08-v1"
BDNS_HOLD_MAX_DOCUMENTS = 4
BDNS_HOLD_MAX_TOTAL_BYTES = 12 * 1024 * 1024


_BDNS_DOCUMENT_CACHE_STATE = {"path": "", "entries": {}}


def _load_bdns_document_cache() -> dict:
    """Carga texto oficial ya extraído; es independiente de la caché IA."""
    path = os.path.abspath(BDNS_DOCUMENT_CACHE_FILE)
    if _BDNS_DOCUMENT_CACHE_STATE["path"] == path:
        return _BDNS_DOCUMENT_CACHE_STATE["entries"]
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        payload = {}
    meta = payload.get("_meta", {}) if isinstance(payload, dict) else {}
    entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
    if meta.get("version") != BDNS_DOCUMENT_CACHE_VERSION or not isinstance(entries, dict):
        entries = {}
    _BDNS_DOCUMENT_CACHE_STATE["path"] = path
    _BDNS_DOCUMENT_CACHE_STATE["entries"] = entries
    return entries


def _save_bdns_document_cache(entries: dict) -> None:
    """Persiste atómicamente evidencia pública, sin mezclarla con decisiones IA."""
    payload = {
        "_meta": {
            "version": BDNS_DOCUMENT_CACHE_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "content": "public_bdns_document_text",
        },
        "entries": entries,
    }
    temporary = BDNS_DOCUMENT_CACHE_FILE + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporary, BDNS_DOCUMENT_CACHE_FILE)


def _bdns_document_cache_key(candidate: dict) -> str:
    """Identifica una revisión concreta de un documento oficial estable."""
    identity = {
        "url": re.sub(r"#.*$", "", str(candidate.get("url", "")).strip()),
        "published_date": str(candidate.get("published_date", "") or ""),
        "source_key": str(candidate.get("source_key", "") or ""),
        "kind": str(candidate.get("kind", "") or ""),
    }
    return hashlib.sha256(json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _is_cacheable_bdns_document(candidate: dict) -> bool:
    """Limita la caché a documentos de inventario, no a landings mutables."""
    if not candidate.get("_from_bdns_inventory"):
        return False
    return candidate.get("kind") in {"document", "announcement"}


def retrieve_bdns_hold_evidence(
    conv: dict,
    session: requests.Session | None = None,
    *,
    intrinsic_exclusion,
    browser_fallback=None,
) -> dict:
    """Recupera evidencia oficial acotada para una causa BDNS en espera.

    `browser_fallback` es un segundo intento opcional para los documentos que
    `requests` no consigue traer: recibe la url y devuelve texto, o "" si
    tampoco puede. Existe por `boletin.dpz.es`, que sirve la cadena de
    certificados incompleta y era el único host que fallaba de toda la
    recopilación (punto 38 del backlog, medido el 02/09/2026). Si nadie lo
    inyecta, el comportamiento es exactamente el de antes.

    Lo inyecta solo `resolve_bdns_holds_for_pipeline()`, que es el camino
    diario. El piloto y el replay siguen sin él a propósito: son herramientas
    de diagnóstico que se lanzan a mano, y no compensa que arranquen Chromium.
    """
    client = session or requests.Session()
    documents = []
    structured_metadata = {
        "codigo_bdns": conv.get("bdns_id", ""),
        "titulo": conv.get("title", ""),
        "fecha_recepcion": conv.get("bdns_received_date", ""),
        "fecha_publicacion_convocatoria": conv.get("bdns_call_publication_date", ""),
        "fecha_inicio_solicitud": conv.get("open_date", ""),
        "fecha_fin_solicitud": conv.get("deadline_date", ""),
        "estado_calculado": conv.get("bdns_active_status", ""),
        "indicador_abierto_api_no_concluyente": conv.get("bdns_api_open_flag", False),
        "tipo_administracion": conv.get("bdns_admin_type", ""),
        "regiones": conv.get("bdns_regions", []),
        "beneficiarios": conv.get("bdns_beneficiary_types", []),
        "modo_concesion": conv.get("bdns_award_mode", ""),
        "instrumentos": conv.get("bdns_instruments", []),
        "finalidad": conv.get("bdns_finality", ""),
        "objetivos": conv.get("bdns_objectives", ""),
    }
    narrative_excerpt = select_evidence_excerpt(
        str(conv.get("description", "")), conv.get("title", ""), 10_000
    )
    metadata_text = (
        "METADATOS SNPSAP CON ETIQUETAS:\n"
        + json.dumps(structured_metadata, ensure_ascii=False, sort_keys=True)
        + ("\nCONTENIDO ADICIONAL:\n" + narrative_excerpt if narrative_excerpt else "")
    )[:16_000]
    if metadata_text:
        documents.append({
            "title": "Metadatos estructurados SNPSAP",
            "url": conv.get("bdns_url") or conv.get("url", ""),
            "kind": "bdns_metadata",
            "format": "text",
            "text": metadata_text,
            "bytes": len(metadata_text.encode("utf-8")),
        })
    for related in conv.get("related_document_contents", []):
        related_text = select_evidence_excerpt(
            str(related.get("description", "")), related.get("title", ""), 10_000
        )
        if related_text:
            documents.append({
                "title": related.get("title", "Documento relacionado"),
                "url": related.get("url", ""),
                "kind": related.get("document_role", "related_document"),
                "format": "text",
                "text": related_text,
                "bytes": len(related_text.encode("utf-8")),
            })

    candidates = [
        {**item, "_from_bdns_inventory": True}
        for item in conv.get("bdns_documents", [])
        if isinstance(item, dict)
    ]
    for fallback in (conv.get("url", ""),):
        if _is_safe_public_https_url(fallback) and not any(
            item.get("url") == fallback for item in candidates
        ):
            candidates.append({
                "title": "Sede electrónica",
                "url": fallback,
                "kind": "application_landing",
            })
    fetched = 0
    processed = 0
    errors = 0
    total_bytes = 0
    source_bytes = 0
    cache_hits = 0
    cache_misses = 0
    # Documentos que `requests` no pudo traer y el navegador sí. Va a métricas
    # para que quede rastro en la auditoría: si un día sube, es que otra fuente
    # ha empezado a servir mal sus certificados.
    browser_rescues = 0
    document_cache = _load_bdns_document_cache()
    cache_changed = False
    for candidate in candidates:
        if processed >= BDNS_HOLD_MAX_DOCUMENTS or source_bytes >= BDNS_HOLD_MAX_TOTAL_BYTES:
            break
        url = str(candidate.get("url", ""))
        if not _is_safe_public_https_url(url):
            continue
        processed += 1
        cacheable = _is_cacheable_bdns_document(candidate)
        cache_key = _bdns_document_cache_key(candidate) if cacheable else ""
        cached = document_cache.get(cache_key, {}) if cache_key else {}
        cached_text = cached.get("text", "") if isinstance(cached, dict) else ""
        cached_bytes = cached.get("bytes", 0) if isinstance(cached, dict) else 0
        if (
            isinstance(cached_text, str)
            and len(cached_text) >= 80
            and isinstance(cached_bytes, int)
            and 0 <= cached_bytes <= BDNS_HOLD_MAX_DOCUMENT_BYTES
            and source_bytes + cached_bytes <= BDNS_HOLD_MAX_TOTAL_BYTES
        ):
            cache_hits += 1
            source_bytes += cached_bytes
            documents.append({
                "title": candidate.get("title", "Documento oficial"),
                "url": url,
                "kind": candidate.get("kind", "document"),
                "format": cached.get("format", "text"),
                "text": cached_text,
                "bytes": cached_bytes,
            })
            continue
        if cacheable:
            cache_misses += 1
        response = _http_get(
            url,
            session=client,
            timeout=20,
            retries=2,
            headers={"Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.2"},
            max_bytes=min(
                BDNS_HOLD_MAX_DOCUMENT_BYTES,
                BDNS_HOLD_MAX_TOTAL_BYTES - source_bytes,
            ),
        )
        fetched += 1
        if response is None:
            # Segundo intento con el navegador, solo si alguien lo ha
            # inyectado. Es lo que rescata los edictos de `boletin.dpz.es`:
            # su cadena de certificados está incompleta —el servidor manda un
            # único certificado— y Chromium la completa. No se relaja ninguna
            # verificación: se usa un cliente que verifica mejor.
            texto_navegador = (
                browser_document_text(
                    browser_fallback, url, BDNS_HOLD_MAX_EVIDENCE_CHARS
                )
                if callable(browser_fallback) or browser_fallback is not None
                else ""
            )
            if len(texto_navegador) < 80:
                errors += 1
                continue
            browser_rescues += 1
            documento_bytes = len(texto_navegador.encode("utf-8"))
            source_bytes += documento_bytes
            total_bytes += documento_bytes
            documents.append({
                "title": candidate.get("title", "Documento oficial"),
                "url": url,
                "kind": candidate.get("kind", "document"),
                "format": "html_browser",
                "text": texto_navegador,
                "bytes": documento_bytes,
            })
            if cacheable:
                document_cache[cache_key] = {
                    "url": url,
                    "published_date": candidate.get("published_date", ""),
                    "kind": candidate.get("kind", "document"),
                    "format": "html_browser",
                    "bytes": documento_bytes,
                    "text": texto_navegador,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                }
                cache_changed = True
            continue
        if not _is_safe_public_https_url(str(response.url)):
            errors += 1
            continue
        response_bytes = len(response.content)
        total_bytes += response_bytes
        source_bytes += response_bytes
        if response_bytes > BDNS_HOLD_MAX_DOCUMENT_BYTES:
            errors += 1
            continue
        text, document_format = _hold_document_text(response, url)
        if len(text) < 80:
            errors += 1
            continue
        documents.append({
            "title": candidate.get("title", "Documento oficial"),
            "url": url,
            "kind": candidate.get("kind", "document"),
            "format": document_format,
            "text": text,
            "bytes": response_bytes,
        })
        if cacheable:
            document_cache[cache_key] = {
                "url": url,
                "published_date": candidate.get("published_date", ""),
                "kind": candidate.get("kind", "document"),
                "format": document_format,
                "bytes": response_bytes,
                "text": text,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            cache_changed = True

    if cache_changed:
        _save_bdns_document_cache(document_cache)

    prompt_documents = []
    remaining = BDNS_HOLD_MAX_EVIDENCE_CHARS
    for document in documents:
        if remaining <= 0:
            break
        excerpt = select_evidence_excerpt(
            document.get("text", ""), conv.get("title", ""), min(remaining, 16_000)
        )
        if not excerpt:
            continue
        prompt_documents.append({
            "title": document.get("title", ""),
            "url": document.get("url", ""),
            "kind": document.get("kind", ""),
            "format": document.get("format", ""),
            "text": excerpt,
        })
        remaining -= len(excerpt)
    evidence_hash = hashlib.sha256(json.dumps(
        prompt_documents, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    # El prefiltro local inspecciona los documentos oficiales completos. El
    # límite de extractos existe para Claude, no debe ocultar un objeto o una
    # lista exhaustiva de beneficiarios a una regla determinista auditable.
    deterministic_scope_exclusion = intrinsic_exclusion(
        conv,
        " ".join(str(item.get("text", "")) for item in documents),
    )
    return {
        "documents": prompt_documents,
        "deterministic_scope_exclusion": deterministic_scope_exclusion,
        "evidence_hash": evidence_hash,
        "metrics": {
            "candidate_urls": len(candidates),
            "processed_urls": processed,
            "fetched_urls": fetched,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "errors": errors,
            "browser_rescues": browser_rescues,
            "bytes": total_bytes,
            "source_bytes": source_bytes,
            "documents_with_text": len(prompt_documents),
            "characters": sum(len(item["text"]) for item in prompt_documents),
        },
    }
