# public_output.py — construcción del JSON público que consume el dashboard
#
# Convierte una convocatoria analizada en el registro que se publica, y calcula
# lo que el panel necesita alrededor: estadísticas, estado por fuente, palabras
# clave y verificación técnica de URLs. Es la frontera con `index.html`: si
# cambia un nombre de campo aquí, hay que adaptar el frontend
# (`tests/test_grant_radar.py::FrontendContractTests` lo comprueba sobre
# `_assemble_public_record()` sin red ni Claude).
#
# `post_procesar_texto()` vive aquí porque es la última corrección determinista
# antes de publicar: normaliza variantes alucinadas de nombres propios contra
# una lista blanca conocida (ITAINNOVA, CIRCE...). No es verificación de
# veracidad ni una segunda llamada a IA.
#
# Sin red salvo `verificar_urls()`, que solo comprueba accesibilidad y nunca
# cambia el contenido publicado.

import logging
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from grant_radar.http_client import HTTP_USER_AGENT
from grant_radar.parsing_helpers import _fold_text, _levenshtein, _web_url_or_empty
from grant_radar.runtime_state import RUN_DIAGNOSTICS, SOURCE_RUNTIME_METADATA
from grant_radar.tech_taxonomy import TECH_TAGS, _compat_tags_for

log = logging.getLogger("grant_radar")

# Nombres propios que Claude Haiku tiende a deformar al redactar texto libre.
ENTIDADES_CANONICAS = ["ITAINNOVA", "CIRCE", "Unizar", "CDTI", "IDAE"]


def _public_deadline_values(conv: dict) -> tuple[int | None, str, bool]:
    """Impide publicar como plazo real el centinela interno de un hold BDNS."""
    deadline_date = str(conv.get("deadline_date", "") or "")
    bdns_status = str(conv.get("bdns_active_status", ""))
    if bdns_status in {"unverified_recent", "unverified_old"} and not deadline_date:
        return None, "", True
    deadline_days = conv.get("deadline_days")
    return (
        int(deadline_days) if isinstance(deadline_days, (int, float)) else None,
        deadline_date,
        bool(conv.get("fecha_sin_confirmar", False)),
    )


def _compact_eligible_action_values(values, limit: int = 6) -> list[str]:
    """Normaliza actuaciones sin convertir temas o resultados en hechos nuevos."""
    cleaned = []
    seen = set()
    for raw_value in values or []:
        value = " ".join(str(raw_value or "").split()).strip(" -–—;:.")
        if not value:
            continue
        if len(value) > 320:
            value = value[:317].rsplit(" ", 1)[0] + "…"
        key = _fold_text(value)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
        if len(cleaned) >= limit:
            break
    return cleaned


def _eligible_actions_from_source_text(conv: dict) -> list[str]:
    """Recupera un extracto solo tras un epígrafe inequívoco de las bases.

    Es una salvaguarda para análisis antiguos sin el campo estructurado. No
    interpreta la relevancia ni infiere conceptos: conserva texto literal de la
    fuente alrededor de ``actuaciones/gastos elegibles``.
    """
    documents = [str(conv.get("description", ""))]
    documents.extend(
        str(document.get("description", ""))
        for document in conv.get("related_document_contents", [])
        if isinstance(document, dict)
    )
    heading = re.compile(
        r"(?:actuaciones?|inversiones?|gastos?|costes?)\s+"
        r"(?:subvencionables?|elegibles?|financiables?)|"
        r"financiaci[oó]n\s+de\s+(?:proyectos?|actuaciones?|inversiones?|costes?|gastos?)|"
        r"(?:ayudas?|subvenciones?)\s+(?:destinadas?\s+a|para)\s+|"
        r"(?:objeto|finalidad)\s*[.º°:;-]+\s*|"
        r"eligible\s+(?:activities|actions|investments|costs|expenditure)|"
        r"activities\s+eligible\s+for\s+funding",
        re.IGNORECASE,
    )
    for text in documents:
        match = heading.search(text)
        if not match:
            continue
        excerpt = BeautifulSoup(
            text[match.start():match.start() + 850], "html.parser"
        ).get_text(" ", strip=True)
        excerpt = " ".join(excerpt.split())
        # Evita arrastrar el epígrafe siguiente de unas bases largas.
        excerpt = re.split(
            r"\s+(?:Artículo|Article)\s+\d+[.º°]?\s+",
            excerpt,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        if len(excerpt) > 650:
            excerpt = excerpt[:647].rsplit(" ", 1)[0] + "…"
        return _compact_eligible_action_values([excerpt], limit=1)
    return []


def derive_eligible_actions(conv: dict, facts: dict) -> tuple[list[str], str]:
    """Obtiene actuaciones visibles con una precedencia factual auditable.

    ``explicit`` procede del nuevo campo del extractor; ``funding_lines`` de
    líneas alternativas; ``required_topics`` es un respaldo etiquetado como
    tema obligatorio, no como categoría de gasto; y ``source_excerpt`` conserva
    un fragmento literal cuando los hechos antiguos no ofrecen nada mejor.
    """
    facts = facts if isinstance(facts, dict) else {}
    explicit = _compact_eligible_action_values(facts.get("eligible_actions", []))
    if explicit:
        return explicit, "explicit"

    line_actions = []
    for line in facts.get("funding_lines", []):
        if not isinstance(line, dict):
            continue
        line_name = " ".join(str(line.get("name", "")).split())
        for action in line.get("eligible_actions", []):
            action_text = " ".join(str(action).split())
            line_actions.append(
                f"{line_name}: {action_text}" if line_name else action_text
            )
    line_actions = _compact_eligible_action_values(line_actions)
    if line_actions:
        return line_actions, "funding_lines"

    required_topics = _compact_eligible_action_values(
        facts.get("required_topics", [])
    )
    if required_topics:
        return required_topics, "required_topics"

    source_actions = _eligible_actions_from_source_text(conv)
    if source_actions:
        return source_actions, "source_excerpt"
    return [], "unavailable"


# Acrónimos del dominio que colisionan con la lista blanca y nunca deben
# reescribirse. `CNAE` está aquí por un caso real: se publicó "los IDAE
# elegibles" y "verificación de que IDAE 2899 esté incluido en el anexo",
# cuando la fuente decía CNAE (ver AGENTS.md sección 40).
ACRONIMOS_PROTEGIDOS = frozenset({
    "CNAE", "NACE", "PYME", "PYMES", "BDNS", "BOE", "BOA", "MRR", "PRTR",
    "FEDER", "TRL", "IVA", "SNPSAP", "CEDEC", "CIEMAT",
})


def post_procesar_texto(texto: str, whitelist: list = None) -> str:
    """
    Normaliza variantes alucinadas de nombres de entidad a su forma canónica.
    Se aplica SOLO a los campos "summary" y "action" generados por Claude Haiku
    (texto libre) — nunca a título, descripción, URL o cualquier campo que
    provenga directamente de la fuente original.

    **Dos restricciones deliberadas, ambas por daños reales observados.** La
    versión anterior comparaba cualquier token alfabético de 4+ caracteres con
    distancia de Levenshtein <= 2, y eso corrompía prosa española corriente:
    en las 49 convocatorias publicadas el 14/08/2026 aparecían "Plazo de
    CIRCE" (era *cierre*), "reference_IDAE" (era *date*), "fin de IDAE" (era
    *vida*) y "los IDAE elegibles" (era *CNAE*). Por eso ahora:

    1. Solo se consideran tokens que el modelo escribió **en mayúsculas**, que
       es la forma en la que aparece una entidad mal escrita (ITAINNOMA). Una
       palabra en minúsculas ya no puede convertirse en un acrónimo.
    2. El umbral de distancia depende de la longitud: 1 para tokens cortos, 2
       a partir de seis caracteres. Sin esto, `CNAE` seguiría cayendo en
       `IDAE`, que está a distancia 2.

    El precio es no corregir una entidad mal escrita en minúsculas o en
    capitalización de título ("Itainnoma"). Es preferible a reescribir texto
    correcto: una entidad mal escrita se lee igual, una fecha convertida en
    "IDAE" no.
    """
    if not texto:
        return texto
    whitelist = whitelist or ENTIDADES_CANONICAS
    tokens = re.findall(r"[A-Za-zÀ-ÿ]+|[^A-Za-zÀ-ÿ]+", texto)
    corregido = []
    for tok in tokens:
        if not (tok.isalpha() and len(tok) >= 4 and tok.isupper()):
            corregido.append(tok)
            continue
        if tok in ACRONIMOS_PROTEGIDOS:
            corregido.append(tok)
            continue
        mejor = min(whitelist, key=lambda e: _levenshtein(tok.upper(), e.upper()))
        dist = _levenshtein(tok.upper(), mejor.upper())
        limite = 1 if len(tok) <= 5 else 2
        corregido.append(mejor if 0 < dist <= limite else tok)
    return "".join(corregido)


def build_stats(
    convocatorias: list,
    detected_total: int = None,
    closed_total: int = 0,
) -> dict:
    """
    Separa cobertura, vigencia y relevancia para evitar que las descartadas por
    Claude se interpreten como oportunidades activas recomendadas.
    """
    active_items = [
        c for c in convocatorias
        if c.get("deadline") is None or c.get("deadline", 0) > 0
    ]
    relevant_items = [c for c in active_items if not c.get("descartada", False)]
    discarded = sum(1 for c in active_items if c.get("descartada", False))
    high = sum(1 for c in relevant_items if c.get("priority") == "high")
    urgent = sum(
        1 for c in relevant_items
        if isinstance(c.get("deadline"), (int, float))
        and 0 < c["deadline"] < 30
    )
    review = sum(1 for c in active_items if c.get("review_required", False))
    data_pending = sum(1 for c in relevant_items if c.get("data_pending", False))
    attention = sum(1 for c in relevant_items if c.get("monitoring_flags", []))
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
        "review": review,
        "data_pending": data_pending,
        "attention": attention,
        "budget": round(budget, 1),
    }


def build_source_status(
    results_by_source: dict,
    descartadas_por_fuente: dict = None,
    source_timings: dict = None,
    consolidated_items: list[dict] | None = None,
) -> list:
    descartadas_por_fuente = descartadas_por_fuente or {}
    source_timings = source_timings or {}
    default_source_meta = {
        "HORIZON EUROPE": "API REST",
        "BDNS":           "API REST SNPSAP",
        "ECCP":           "Scraping HTML + webs de proyectos",
        "EEN":            "Scraping de noticias y Call details",
        "CDTI":           "Playwright + catálogo curado",
        "IDAE":           "Playwright",
        "IDAE CATÁLOGO":  "Playwright (descubrimiento agregado)",
        "BOE / MITECO":   "Playwright",
    }
    now_str = datetime.now().strftime("%H:%M")
    consolidated_items = consolidated_items or []

    def source_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", _fold_text(value))

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
        canonical_name = source_key(name)
        consolidated_count = sum(
            1 for item in consolidated_items
            if canonical_name in {
                source_key(value) for value in [
                    item.get("source", ""),
                    *item.get("discovery_sources", []),
                ] if value
            }
        )
        raw_count = len(source_results)
        source_status = {
            "name":   name,
            "type":   " + ".join(detected_types) if detected_types else default_type,
            "status": "ok" if source_results else "warn",
            # `count` se conserva como alias compatible del volumen bruto.
            "count":  raw_count,
            "raw_count": raw_count,
            "consolidated_count": consolidated_count,
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


def _normalize_public_url(url: str) -> str:
    """Anade HTTPS solo a dominios inequivocos sin esquema.

    No intenta reparar rutas, buscar destinos alternativos ni convertir correos
    electronicos: conserva el valor original cuando no es un host web claro.

    Lo que si hace, desde el 31/08/2026, es no publicar prosa como si fuera un
    enlace: si el valor ya trae esquema, solo sale del pipeline cuando es una
    URL http(s) de verdad (AGENTS.md, punto 31 del backlog). Una convocatoria
    publicaba como `url` una frase entera con el esquema mal escrito, y el
    campo viajaba asi al JSON y al export. El arreglo de fondo esta en el
    conector; esta es la red por si otra fuente hace lo mismo.
    """
    value = str(url or "").strip()
    if not value:
        return value
    if re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I):
        return _web_url_or_empty(value)
    if "@" in value or re.search(r"\s", value):
        return value
    if re.match(
        r"^(?:localhost|(?:[a-z0-9-]+\.)+[a-z]{2,})(?::\d+)?(?:[/?#].*)?$",
        value,
        re.I,
    ):
        return f"https://{value}"
    return value


# Ruta que no puede existir en ningún portal real. Sirve como control: si un
# host responde "correctamente" a esto, sus códigos HTTP no distinguen una URL
# válida de una inventada, y verificar por código es engañarse.
URL_CONTROL_INEXISTENTE = "/grant-radar-control-de-url-inexistente-9f3c2a7b"


def _host_distingue_urls(host: str, timeout: int, cache: dict) -> bool:
    """
    Comprueba una sola vez por host si sus códigos HTTP son informativos.

    Nace de un caso real (AGENTS.md, sección 44): `cdti.es` está tras un WAF
    que devuelve 200 a cualquier ruta pedida por un cliente sin apariencia de
    navegador, incluidas las inexistentes. Sin este control, `verificar_urls()`
    daba por buenas seis URLs de catálogo que llevaban a una página vacía.
    """
    if host in cache:
        return cache[host]
    informativo = True
    try:
        respuesta = requests.get(
            f"https://{host}{URL_CONTROL_INEXISTENTE}",
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": HTTP_USER_AGENT},
        )
        informativo = respuesta.status_code >= 400
    except Exception:
        # Si la sonda no llega, no hay motivo para desconfiar del host: se
        # mantiene el comportamiento anterior y cada URL responde por sí misma.
        informativo = True
    if not informativo:
        log.warning(
            f"  El host {host} responde {respuesta.status_code} incluso a una ruta "
            f"inexistente: sus URLs no se pueden verificar por código HTTP"
        )
    cache[host] = informativo
    return informativo


def verificar_urls(convocatorias: list, timeout: int = 8) -> None:
    """
    Comprueba que cada URL responde correctamente antes de publicar el JSON.
    NUNCA modifica, genera ni "corrige" la URL — solo la señaliza mediante el
    campo url_rota si no se puede confirmar una respuesta HTTP < 400.
    Esta comprobación es deliberadamente determinista (peticiones HTTP reales),
    no delegada en un LLM: un LLM no puede confirmar si una URL es correcta,
    solo si el servidor responde.

    Antes de creerse el resultado de un host, `_host_distingue_urls()` le pide
    una ruta imposible. Si la da por buena, sus códigos no distinguen una URL
    válida de una inventada y esta función lo dice en el diagnóstico
    (`url_verification.opaque_hosts`) en vez de informar de que todo está bien.
    Sin ese control daba por correctas seis fichas de CDTI que llevaban a una
    página inexistente (AGENTS.md, sección 44).

    Usa el mismo `HTTP_USER_AGENT` que el resto del pipeline: antes se
    identificaba aparte como "GrantRadar-Bot/1.0", sin motivo, y una sola
    identidad frente a las webs públicas es más fácil de explicar si alguna
    pregunta quién la está consultando.
    """
    log.info("Verificando accesibilidad HTTP de URLs antes de publicar...")
    vistas = {}
    hosts_informativos = {}
    hosts_opacos = set()
    # La verificabilidad no se publica: es metadato de la comprobación, no del
    # registro, y el esquema público solo debe crecer con lo que el dashboard
    # consume. Va al diagnóstico de la ejecución.
    n_sin_verificar = 0
    for c in convocatorias:
        url = c.get("url", "")
        if not url:
            c["url_rota"] = False
            continue
        if url in vistas:
            c["url_rota"] = vistas[url]
            continue
        host = urlparse(url).netloc.casefold()
        verificable = bool(host) and _host_distingue_urls(host, timeout, hosts_informativos)
        ok = False
        try:
            r = requests.head(url, timeout=timeout, allow_redirects=True,
                               headers={"User-Agent": HTTP_USER_AGENT})
            if r.status_code >= 400:
                r = requests.get(url, timeout=timeout, allow_redirects=True,
                                  headers={"User-Agent": HTTP_USER_AGENT})
            ok = r.status_code < 400
        except Exception as e:
            log.warning(f"  URL no verificable ({url}): {e}")
            ok = False
        # Un host que no distingue rutas puede decir "correcta" de una URL rota,
        # pero nunca inventa un error: un fallo suyo sigue siendo un fallo real.
        if ok and not verificable:
            hosts_opacos.add(host)
            n_sin_verificar += 1
        c["url_rota"] = not ok
        vistas[url] = c["url_rota"]

    n_rotas = sum(1 for c in convocatorias if c.get("url_rota"))
    RUN_DIAGNOSTICS["url_verification"] = {
        "checked": sum(1 for c in convocatorias if c.get("url")),
        "broken": n_rotas,
        "unverifiable": n_sin_verificar,
        "opaque_hosts": sorted(hosts_opacos),
    }
    if n_rotas:
        log.warning(f"  ⚠ {n_rotas} URL(s) no respondieron correctamente (marcadas url_rota=True)")
    if n_sin_verificar:
        log.warning(
            f"  ⚠ {n_sin_verificar} URL(s) en hosts que responden igual a "
            f"cualquier ruta ({', '.join(sorted(hosts_opacos))}): "
            f"«no rota» ahí no prueba que la ficha exista"
        )
    if not n_rotas and not n_sin_verificar:
        log.info("  ✓ Todas las URLs respondieron correctamente")


def _assemble_public_record(record_id: int, conv: dict, analysis: dict) -> dict:
    """Construye el registro público (una fila de `convocatorias.json`) a
    partir de una convocatoria recopilada (`conv`) y su análisis (`analysis`,
    de caché o recién calculado). Es el único sitio del backend que decide
    los nombres de campo publicados; `index.html` (`normalizeConv()`) debe
    seguir entendiéndolos. Se separó de `run_pipeline()` para poder probarla
    de forma aislada, sin recopilar fuentes ni llamar a Claude — ver
    `tests/test_grant_radar.py::test_backend_record_fields_are_understood_by_frontend`.
    """
    public_deadline, public_deadline_date, public_deadline_unconfirmed = (
        _public_deadline_values(conv)
    )
    eligible_actions, eligible_actions_basis = derive_eligible_actions(
        conv, analysis.get("call_facts", {})
    )
    return {
        "id":                  record_id,
        "source":              conv["source"],
        "identifier":          conv.get("identifier", ""),
        "discovery_sources":   conv.get("discovery_sources", [conv["source"]]),
        "funding_mechanism":   conv.get("funding_mechanism", "unknown"),
        "opportunity_role":    conv.get("opportunity_role", "unknown"),
        "opportunity_labels":  conv.get("opportunity_labels", []),
        "title":               conv["title"],
        "description":         conv["description"],
        "match":               analysis.get("match_score", 50),
        "fit_score":           analysis.get("fit_score", 50),
        "actionability_score": analysis.get("actionability_score", 0),
        "confidence":          analysis.get("confidence", 0),
        "priority":            analysis.get("priority", "medium"),
        "descartada":          analysis.get("descartada", False),
        "motivo_descarte":     analysis.get("motivo_descarte", ""),
        "decision":            analysis.get("decision", "manual_review"),
        "eligibility":         analysis.get("eligibility", "unknown"),
        "eligibility_reason":  analysis.get("eligibility_reason", ""),
        "recommended_role":    analysis.get("recommended_role", "unknown"),
        "scores":              analysis.get("scores", {}),
        "evidence_quality":    analysis.get("evidence_quality", "low"),
        "positive_evidence":   analysis.get("positive_evidence", []),
        "risks_and_unknowns":  analysis.get("risks_and_unknowns", []),
        "partner_needs":       analysis.get("partner_needs", []),
        "recommended_partners": analysis.get("recommended_partners", []),
        "review_required":     analysis.get("review_required", False),
        "review_reasons":      analysis.get("review_reasons", []),
        "data_pending":        analysis.get("data_pending", False),
        "data_gaps":           analysis.get("data_gaps", []),
        "monitoring_flags":    analysis.get("monitoring_flags", []),
        "token_usage":         analysis.get("token_usage", {}),
        "call_facts":          analysis.get("call_facts", {}),
        "eligible_actions":    eligible_actions,
        "eligible_actions_basis": eligible_actions_basis,
        "trl_min":             analysis.get("trl_min"),
        "trl_max":             analysis.get("trl_max"),
        "socio_consorcio":     analysis.get("socio_consorcio", ""),
        "deadline":            public_deadline,
        "deadline_date":       public_deadline_date,
        "eoi_deadline_date":   conv.get("eoi_deadline_date", ""),
        "open_date":           conv.get("open_date", ""),
        "fecha_sin_confirmar": public_deadline_unconfirmed,
        "fecha_prevista":      conv.get("fecha_prevista", False),
        "budget":              conv.get("budget", "Ver convocatoria"),
        "budget_raw":          0,
        "url":                 _normalize_public_url(conv["url"]),
        "org":                 conv["org"],
        "tags":                analysis.get("tags", ["ee"]),
        "tech_tags":           analysis.get("tech_tags", []),
        # Qué financia la convocatoria, antes que ninguna valoración. Los
        # análisis en caché anteriores al esquema que lo introdujo no lo
        # traen: se publica vacío y el frontend cae al resumen.
        "objeto_y_actuaciones": post_procesar_texto(
            analysis.get("objeto_y_actuaciones", "")
        ),
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
    }
