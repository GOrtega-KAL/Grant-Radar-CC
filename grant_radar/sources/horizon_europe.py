# horizon_europe.py — conector Horizon Europe (SEDIA Search API)
#
# Fuente europea principal: el backend oficial del portal Funding & Tenders de
# la Comisión. Se enumera todo el universo Horizon abierto y próximo en inglés
# —la API solo busca de forma fiable en algunos campos— y la relevancia se
# decide localmente sobre título + descripción, para no perder topics cuyo
# título no lleva las palabras técnicas que sí aparecen en su descripción.
#
# El RSS del portal se conserva como respaldo nominal, pero devuelve un feed
# inválido (bozo=1) desde hace tiempo y no aporta nada: si SEDIA falla, no hay
# alternativa funcional.
#
# Sin Playwright, sin caché, sin reglas de negocio y sin Claude: solo API
# oficial, filtro de relevancia y registro de descartes.

import hashlib
import json
import logging
import re
import time
from collections import Counter
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from grant_radar.audit import audit_exclusion
from grant_radar.parsing_helpers import select_evidence_excerpt
from grant_radar.runtime_state import SOURCE_RUNTIME_METADATA
from grant_radar.tech_taxonomy import is_relevant, keyword_match

log = logging.getLogger("grant_radar")


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
# La API acepta 100, pero con ese tamaño se han observado saltos de
# identificadores entre páginas. El tamaño 50 es el usado por el portal y
# conserva los límites de página de forma estable.
_HORIZON_PAGE_SIZE = 50
_HORIZON_MAX_PAGES = 40
# ``identifier`` es estable y prácticamente único. Ordenar solo por
# ``sortStatus`` agrupa cientos de empates y provoca solapamientos entre páginas.
_HORIZON_SORT = {"field": "identifier", "order": "ASC"}


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
    all_docs = []
    raw_seen = set()

    collected = 0
    total_available = 0
    # La API agrupa internamente por ``sortStatus``. Si se mezclan estados en
    # una sola consulta, sus grupos pueden solaparse al paginar aunque se envíe
    # una ordenación. Se consulta cada estado por separado y se ordena por el
    # identificador estable: así el recorrido es determinista y genérico.
    for status_code, status_label in (
        (_SEDIA_STATUS_OPEN, "abiertas"),
        (_SEDIA_STATUS_FORTHCOMING, "próximas"),
    ):
        api_query = {
            "bool": {
                "must": [
                    {"terms": {"type": ["1", "2", "8"]}},
                    {"term": {"status": status_code}},
                    {"term": {"programmePeriod": "2021 - 2027"}},
                    {"terms": {"frameworkProgramme": [_SEDIA_HORIZON_PROGRAMME]}},
                    {"term": {"language": "en"}},
                ]
            }
        }
        query_json = json.dumps(api_query, ensure_ascii=False)
        status_collected = 0
        status_total = 0

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
                    files={
                        "query": ("query.json", query_json, "application/json"),
                        "languages": (
                            "languages.json",
                            json.dumps(["en"]),
                            "application/json",
                        ),
                        "sort": (
                            "sort.json",
                            json.dumps(_HORIZON_SORT),
                            "application/json",
                        ),
                    },
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "GrantRadar-Bot/1.0",
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.warning(
                    f"Horizon SEDIA error ({status_label}, p{page}): {e}"
                )
                break

            docs_page = data.get("results", [])
            status_total = int(data.get("totalResults", 0) or 0)
            if not docs_page:
                break

            status_collected += len(docs_page)
            for item in docs_page:
                identifier = _sedia_meta(item, "identifier")
                raw_key = (
                    identifier
                    or str(item.get("id", ""))
                    or hashlib.sha256(
                        json.dumps(
                            item.get("metadata", {}),
                            sort_keys=True,
                        ).encode("utf-8")
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
                f"  SEDIA {status_label} p{page}: {len(docs_page)} docs "
                f"({min(status_collected, status_total)}/{status_total})"
            )
            if status_collected >= status_total:
                break
            time.sleep(0.2)

        collected += status_collected
        total_available += status_total
        if status_total > status_collected and status_collected >= (
            _HORIZON_MAX_PAGES * _HORIZON_PAGE_SIZE
        ):
            log.warning(
                f"Horizon SEDIA: inventario {status_label} truncado por el "
                f"límite defensivo ({status_collected}/{status_total})"
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
            "identifier":           identifier,
            "title":                title[:200],
            # Se conserva suficiente alcance para la extracción factual. El
            # límite anterior de 800 caracteres cortaba requisitos, outcomes y
            # condiciones relevantes al inicio de muchos topics Horizon.
            "description":          select_evidence_excerpt(
                description, title, 20_000
            ),
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
