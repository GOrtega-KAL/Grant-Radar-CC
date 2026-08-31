# -*- coding: utf-8 -*-
# staleness.py — cuánto se está quedando desfasada la información publicada
#
# Responde a una sola pregunta: ¿merece la pena pagar una ejecución con Claude
# hoy? Para eso hace falta saber cuántas convocatorias hay pendientes de
# analizar y desde cuándo, y ambas cosas ya están en la auditoría: cada
# recopilación `--no-claude` guarda su `claude_forecast` con las nuevas o
# cambiadas, y cada ejecución completa queda marcada como publicación.
#
# Por eso este módulo no recopila nada ni consulta ninguna fuente: solo lee el
# histórico. Es instantáneo, gratis y no toca la red.
#
# El uso previsto (decidido con el usuario el 21/08/2026, ver AGENTS.md sección
# 47) es una recopilación `--no-claude` diaria programada, con la llamada a
# Claude decidida a mano cuando el desfase lo justifique: en subvenciones el
# ciclo real es de días o semanas, no de horas.

from datetime import date, datetime

# Estado con el que la auditoría marca una ejecución que sí llamó a Claude y
# publicó. Las recopilaciones sin Claude usan "completed_no_claude".
PUBLISHED_RUN_STATUS = "completed"


def _parse_day(value: str) -> date | None:
    try:
        return datetime.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        return None


def build_staleness_report(runs: list, today: date | None = None) -> dict:
    """
    Resume el desfase a partir del histórico de ejecuciones de la auditoría.

    `pending` es el número de convocatorias nuevas o cambiadas que la última
    recopilación encontró sin analizar. `days_since_publication` cuenta desde la
    última ejecución que llamó a Claude y publicó, no desde la última
    recopilación.
    """
    today = today or date.today()
    serie = []
    ultima_publicacion = None
    momento_publicacion = ""
    for run in runs or []:
        if not isinstance(run, dict):
            continue
        inicio = str(run.get("started_at", "") or "")
        dia = _parse_day(inicio)
        if run.get("status", "") == PUBLISHED_RUN_STATUS and dia:
            ultima_publicacion = dia
            momento_publicacion = inicio
        forecast = (run.get("diagnostics") or {}).get("claude_forecast")
        if not isinstance(forecast, dict):
            # Las ejecuciones completas no dejan previsión: ya analizaron.
            continue
        serie.append({
            "day": dia.isoformat() if dia else "",
            "started_at": inicio,
            "candidates": forecast.get("candidates"),
            "pending": forecast.get("new_or_changed"),
            "estimated_cost_usd": forecast.get("estimated_cost_central_usd"),
        })

    # Solo cuenta lo medido DESPUÉS de la última publicación: una previsión
    # anterior ya la consumió esa ejecución, y darla por pendiente haría
    # parecer desfasado lo que se acaba de publicar.
    posteriores = [
        fila for fila in serie
        if not momento_publicacion or fila["started_at"] > momento_publicacion
    ]
    ultima = posteriores[-1] if posteriores else None
    return {
        "generated_on": today.isoformat(),
        "last_publication": ultima_publicacion.isoformat() if ultima_publicacion else "",
        "days_since_publication": (
            (today - ultima_publicacion).days if ultima_publicacion else None
        ),
        "candidates": ultima.get("candidates") if ultima else None,
        "pending": ultima.get("pending") if ultima else None,
        "estimated_cost_usd": ultima.get("estimated_cost_usd") if ultima else None,
        "measured_on": ultima.get("started_at", "")[:16].replace("T", " ") if ultima else "",
        "measured_since_publication": bool(ultima),
        "history": serie[-14:],
    }


def format_staleness_report(report: dict) -> str:
    """Rinde el informe para consola. Sin colores ni dependencias."""
    lineas = ["=" * 60, f"DESFASE DE LA INFORMACIÓN — {report.get('generated_on', '')}", "=" * 60]
    publicacion = report.get("last_publication") or "nunca"
    dias = report.get("days_since_publication")
    antiguedad = (
        "hoy" if dias == 0
        else f"hace {dias} día{'s' if dias != 1 else ''}" if isinstance(dias, int)
        else "sin registro"
    )
    lineas.append(f"  Última publicación con Claude: {publicacion} ({antiguedad})")

    if report.get("pending") is None:
        lineas.append("  Sin recopilación --no-claude posterior a esa publicación:")
        lineas.append("  ejecuta una para saber cuántas convocatorias esperan análisis.")
        lineas.append("=" * 60)
        return "\n".join(lineas)

    pendientes = report.get("pending") or 0
    coste = report.get("estimated_cost_usd")
    lineas.append(f"  Convocatorias vigentes:        {report.get('candidates')}")
    lineas.append(f"  Pendientes de analizar:        {pendientes}")
    if coste is not None:
        lineas.append(f"  Coste de ponerse al día:       {coste:.4f} USD")
    lineas.append(f"  Medido en la recopilación de:  {report.get('measured_on') or '—'}")

    historia = report.get("history") or []
    if len(historia) > 1:
        lineas.append("")
        lineas.append("  Recopilaciones recientes:")
        lineas.append(f"    {'fecha':<17} {'vigentes':>9} {'pendientes':>11} {'coste USD':>10}")
        for fila in historia:
            coste_fila = fila.get("estimated_cost_usd")
            momento = str(fila.get("started_at") or "")[:16].replace("T", " ")
            lineas.append(
                f"    {momento:<17} "
                f"{str(fila.get('candidates') if fila.get('candidates') is not None else '—'):>9} "
                f"{str(fila.get('pending') if fila.get('pending') is not None else '—'):>11} "
                f"{(f'{coste_fila:.4f}' if coste_fila is not None else '—'):>10}"
            )

    lineas.append("")
    if pendientes == 0:
        lineas.append("  Nada pendiente: lo publicado está al día.")
    else:
        lineas.append(
            f"  Llamar a Claude analizaría {pendientes} convocatoria"
            f"{'s' if pendientes != 1 else ''}. Requiere autorización expresa."
        )
    lineas.append("=" * 60)
    return "\n".join(lineas)


def summarize_staleness(report: dict) -> str:
    """Una sola línea, para cerrar una recopilación `--no-claude`."""
    pendientes = report.get("pending")
    if pendientes is None:
        return "Desfase: sin datos suficientes en la auditoría."
    dias = report.get("days_since_publication")
    antiguedad = (
        f"{dias} día{'s' if dias != 1 else ''} desde la última publicación"
        if isinstance(dias, int) else "sin publicación registrada"
    )
    if not pendientes:
        return f"Desfase: 0 convocatorias pendientes de analizar · {antiguedad}."
    coste = report.get("estimated_cost_usd")
    importe = f" · {coste:.4f} USD" if coste is not None else ""
    return (
        f"Desfase: {pendientes} convocatoria"
        f"{'s' if pendientes != 1 else ''} pendiente"
        f"{'s' if pendientes != 1 else ''} de analizar{importe} · {antiguedad}."
    )


# Versión del archivo de estado que publica cada recopilación diaria. El
# dashboard lo lee aparte de convocatorias.json y tolera que no exista.
COLLECTION_STATE_SCHEMA_VERSION = 1


def build_collection_state(
    report: dict,
    *,
    detected: int,
    active: int,
    generated_at: str,
) -> dict:
    """Estado que publica una recopilación `--no-claude` para el dashboard.

    Nace del flujo acordado el 21/08/2026 (AGENTS.md 47.5): una recopilación
    diaria sin coste que sirva para decidir a mano cuándo pagar un análisis.
    Hasta ahora ese dato solo se veía en consola, así que quien mira el panel
    no tenía forma de saber si lo publicado seguía al día.

    Es deliberadamente pequeño —seis cifras y dos fechas— y no repite nada de
    `convocatorias.json`: describe la ÚLTIMA RECOPILACIÓN, no el producto.
    """
    return {
        "schema_version": COLLECTION_STATE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "collected_on": report.get("generated_on", ""),
        "detected": detected,
        "active": active,
        "pending_analyses": report.get("pending"),
        "estimated_cost_usd": report.get("estimated_cost_usd"),
        "last_publication": report.get("last_publication", ""),
        "days_since_publication": report.get("days_since_publication"),
    }
