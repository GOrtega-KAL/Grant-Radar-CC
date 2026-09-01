# -*- coding: utf-8 -*-
# gap_report.py — qué datos faltan, por fuente, en lo ya analizado
#
# Responde a una sola pregunta: ¿de qué fuente estamos sacando peor el dato?
# Nace de un método, no de un fallo. El 31/08/2026 se contaron a mano los
# campos ausentes por fuente y el recuento encontró en cinco minutos que las
# diecinueve convocatorias de Horizon llegaban al modelo sin una sola cifra
# económica, teniéndolas la respuesta que ya descargábamos (AGENTS.md 52).
# `SUGERENCIAS.MD` 14 lo resumió así: ese recuento «ha valido más que
# cualquier refactorización de hoy». Esto lo convierte en un comando, para que
# la próxima vez no dependa de que alguien se acuerde de hacerlo.
#
# Como `staleness.py`, no recopila nada ni consulta ninguna fuente: solo lee
# archivos que ya existen. Es instantáneo, gratis y no toca la red.
#
# Lee DOS orígenes, y la distinción importa:
#
#   - el producto publicado (`convocatorias.json`), que es lo que ve quien usa
#     la herramienta;
#   - la caché de análisis, que contiene lo ya pagado y todavía no publicado.
#
# El segundo es el que permite medir una prueba dirigida `--max-claude`, que
# guarda en caché y termina sin publicar: sin leer la caché no habría forma de
# comprobar el resultado de una prueba de pago sin pagar otra vez.

from collections import Counter

from grant_radar.versions import (
    ANALYSIS_PROMPT_VERSION,
    CACHE_SCHEMA_VERSION,
    CLAUDE_MODEL,
    EVALUATOR_VERSION,
    EXTRACTOR_VERSION,
    PARTNER_CATALOG_VERSION,
    PROFILE_VERSION,
)

# Los cuatro campos económicos que el plan de la sesión manda vigilar en la
# prueba dirigida de pago (AGENTS.md 53.2). Se destacan aparte porque son el
# criterio de aceptación de lo último que se tocó, no un dato más.
BUDGET_WATCH_FIELDS = (
    "budget_total_eur",
    "grant_max_eur",
    "project_budget_eur",
    "funding_rate_percent",
)

# Ausencias reales de la fuente, no fallos de extracción. Decisión cerrada del
# usuario el 31/08/2026 (AGENTS.md 53.3 y 36.6bis): en Horizon el TRL se
# anuncia y se recoge; en BDNS no se anuncia y no se recoge. Se marcan en el
# informe para que ningún recuento futuro las reabra como si fueran un
# pendiente.
ACCEPTED_ABSENCES = ("trl_source", "trl_min", "trl_max")

# Un análisis descartado no declara huecos: `_data_gap_reasons()` devuelve
# lista vacía en cuanto la decisión empieza por "discard_". Por eso el
# denominador de `data_gaps` no puede ser el total de fichas —lo haría parecer
# mucho mejor de lo que es—, sino solo las que siguen vivas.
DISCARD_PREFIX = "discard_"


def _unicos(valores) -> list[str]:
    """
    Nombres distintos, conservando el orden de aparición.

    Hace falta de verdad: el modelo repite a veces un campo dentro del mismo
    `missing_fields`, y contando menciones en vez de convocatorias el informe
    llegó a publicar «20/19» para `funding_rate_percent` en Horizon. Lo que se
    cuenta aquí es en cuántas convocatorias falta un campo, nunca cuántas veces
    se ha nombrado.
    """
    return list(dict.fromkeys(
        str(valor).strip() for valor in (valores or []) if str(valor).strip()
    ))


def _record(source: str, analysis: dict) -> dict:
    """Reduce un análisis a lo que este informe necesita, venga de donde venga."""
    call_facts = analysis.get("call_facts")
    if not isinstance(call_facts, dict):
        call_facts = {}
    return {
        "source": str(source or "?").strip() or "?",
        "decision": str(analysis.get("decision", "") or ""),
        "data_gaps": _unicos(analysis.get("data_gaps")),
        "missing_fields": _unicos(call_facts.get("missing_fields")),
    }


def gap_records_from_product(payload: dict) -> list[dict]:
    """Registros a partir de `convocatorias.json`, tal y como se publica."""
    if not isinstance(payload, dict):
        return []
    registros = []
    for ficha in payload.get("convocatorias") or []:
        if not isinstance(ficha, dict):
            continue
        # En el producto el análisis está aplanado dentro de la propia ficha.
        registros.append(_record(ficha.get("source", ""), ficha))
    return registros


def gap_records_from_cache(payload: dict) -> list[dict]:
    """
    Registros a partir del archivo de caché, leído en crudo.

    No se usa `cache_load()` a propósito: esa función devuelve `{}` cuando las
    versiones no coinciden, que es exactamente el estado en el que conviene
    poder mirar la caché para entender qué hay dentro. Aquí se lee lo que haya
    y se informa aparte de si corresponde a las versiones vigentes.
    """
    if not isinstance(payload, dict):
        return []
    entradas = payload.get("entries")
    if not isinstance(entradas, dict):
        return []
    registros = []
    for registro in entradas.values():
        if not isinstance(registro, dict):
            continue
        analysis = registro.get("analysis")
        if not isinstance(analysis, dict):
            continue
        documento = registro.get("raw_document") or registro.get("conv") or {}
        fuente = documento.get("source", "") if isinstance(documento, dict) else ""
        registros.append(_record(fuente, analysis))
    return registros


def cache_version_state(payload: dict) -> dict:
    """Compara las versiones del archivo de caché con las vigentes."""
    meta = payload.get("_meta") if isinstance(payload, dict) else None
    if not isinstance(meta, dict):
        return {"known": False, "matches": None, "mismatched": []}
    esperado = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "prompt_version": ANALYSIS_PROMPT_VERSION,
        "profile_version": PROFILE_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "evaluator_version": EVALUATOR_VERSION,
        "partner_catalog_version": PARTNER_CATALOG_VERSION,
        "model_version": CLAUDE_MODEL,
    }
    desajustados = sorted(
        clave for clave, valor in esperado.items() if meta.get(clave) != valor
    )
    return {
        "known": True,
        "matches": not desajustados,
        "mismatched": desajustados,
        "saved_at": str(meta.get("saved_at", "") or ""),
    }


def build_gap_report(records: list, *, origin: str, label: str = "",
                     version_state: dict | None = None) -> dict:
    """
    Agrupa por fuente los huecos declarados, con dos medidas distintas.

    `data_gaps` es la vista de producto: lo que al dashboard le falta para
    decidir, contado solo sobre las convocatorias vivas. `missing_fields` es la
    vista del extractor: lo que el modelo declaró ausente al leer la fuente,
    contado sobre todas. La primera dice cuánto duele; la segunda, dónde
    arreglarlo.
    """
    por_fuente: dict[str, dict] = {}
    for registro in records or []:
        if not isinstance(registro, dict):
            continue
        fuente = registro.get("source", "?") or "?"
        datos = por_fuente.setdefault(fuente, {
            "source": fuente,
            "total": 0,
            "live": 0,
            "data_gaps": Counter(),
            "missing_fields": Counter(),
        })
        datos["total"] += 1
        if not str(registro.get("decision", "")).startswith(DISCARD_PREFIX):
            datos["live"] += 1
            datos["data_gaps"].update(registro.get("data_gaps") or [])
        datos["missing_fields"].update(registro.get("missing_fields") or [])

    fuentes = []
    for datos in sorted(por_fuente.values(), key=lambda d: (-d["total"], d["source"])):
        fuentes.append({
            "source": datos["source"],
            "total": datos["total"],
            "live": datos["live"],
            "data_gaps": dict(datos["data_gaps"].most_common()),
            "missing_fields": dict(datos["missing_fields"].most_common()),
        })

    # Control específico del 53.2: los cuatro campos económicos, por fuente.
    # Se calcula aquí y no en la presentación para que una prueba pueda
    # afirmarlo sin leer texto formateado.
    presupuesto = {
        fuente["source"]: {
            campo: fuente["missing_fields"].get(campo, 0)
            for campo in BUDGET_WATCH_FIELDS
        }
        for fuente in fuentes
    }
    return {
        "origin": origin,
        "label": label,
        "total": sum(fuente["total"] for fuente in fuentes),
        "live": sum(fuente["live"] for fuente in fuentes),
        "sources": fuentes,
        "budget_watch": presupuesto,
        "version_state": version_state or {},
    }


def _tabla(titulo: str, conteos: dict, denominador: int, sangria: str = "     ") -> list:
    if not conteos:
        return [f"{sangria}{titulo}: ninguno"]
    lineas = [f"{sangria}{titulo}:"]
    for campo, veces in conteos.items():
        marca = "  (ausencia aceptada)" if campo in ACCEPTED_ABSENCES else ""
        proporcion = f"{veces:3d}/{denominador:<3d}"
        lineas.append(f"{sangria}  {proporcion}  {campo}{marca}")
    return lineas


def format_gap_report(reports: list, generated_on: str = "") -> str:
    """Rinde uno o varios informes para consola. Sin colores ni dependencias."""
    lineas = ["=" * 68, f"CAMPOS AUSENTES POR FUENTE — {generated_on}", "=" * 68]
    for informe in reports or []:
        lineas.append("")
        lineas.append(f"  {informe.get('origin', '')}")
        if informe.get("label"):
            lineas.append(f"  {informe['label']}")
        estado = informe.get("version_state") or {}
        if estado.get("known") and not estado.get("matches"):
            lineas.append(
                "  AVISO: versiones distintas de las vigentes ("
                + ", ".join(estado.get("mismatched") or [])
                + "). Estos análisis se repetirán en la próxima ejecución."
            )
        if not informe.get("sources"):
            lineas.append("  Sin análisis que medir.")
            continue
        lineas.append(
            f"  {informe.get('total', 0)} análisis · "
            f"{informe.get('live', 0)} sin descartar"
        )
        for fuente in informe["sources"]:
            lineas.append("")
            lineas.append(
                f"   {fuente['source']}  (analizadas {fuente['total']}, "
                f"vivas {fuente['live']})"
            )
            lineas.extend(_tabla(
                "huecos de producto", fuente["data_gaps"], fuente["live"]
            ))
            lineas.extend(_tabla(
                "campos que el extractor declaró ausentes",
                fuente["missing_fields"], fuente["total"]
            ))
    lineas.append("")
    lineas.append("  Los huecos de producto se cuentan solo sobre las vivas: una")
    lineas.append("  convocatoria descartada no declara ninguno.")
    lineas.append("=" * 68)
    return "\n".join(lineas)


def format_budget_watch(reports: list) -> str:
    """
    El control concreto que pide AGENTS.md 53.2, en su propia tabla.

    Existe porque «revisar que el presupuesto se extrae bien» es la aceptación
    de lo último que se tocó, y conviene poder mirarlo sin recorrer el informe
    entero ni fiarse de una impresión.
    """
    lineas = ["=" * 68, "CONTROL 53.2 — CIFRAS ECONÓMICAS AUSENTES", "=" * 68]
    for informe in reports or []:
        lineas.append("")
        lineas.append(f"  {informe.get('origin', '')}")
        vigilancia = informe.get("budget_watch") or {}
        if not vigilancia:
            lineas.append("    Sin análisis que medir.")
            continue
        totales = {
            fuente["source"]: fuente["total"] for fuente in informe.get("sources", [])
        }
        cabecera = "    {:<16}".format("fuente") + "".join(
            f"{campo[:18]:>20}" for campo in BUDGET_WATCH_FIELDS
        )
        lineas.append(cabecera)
        for fuente, campos in vigilancia.items():
            fila = "    {:<16}".format(fuente[:16])
            for campo in BUDGET_WATCH_FIELDS:
                fila += f"{f'{campos[campo]}/{totales.get(fuente, 0)}':>20}"
            lineas.append(fila)
    lineas.append("")
    lineas.append("  Objetivo del 53.2: que estas cuatro columnas caigan a 0 en")
    lineas.append("  HORIZON EUROPE, donde faltaban en 19 de 19.")
    lineas.append("=" * 68)
    return "\n".join(lineas)
