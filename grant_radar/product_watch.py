# -*- coding: utf-8 -*-
# product_watch.py — qué ha cambiado en lo que ve el usuario, entre una
# publicación y la siguiente
#
# `compare_funnels()` (source_health.py) vigila la recopilación: cuántas fichas
# entran, cuántas se abren, cuántas traen fecha. Nadie vigilaba el otro extremo,
# el JSON publicado, y ahí es donde el usuario mira. El 31/08/2026 una
# corrección de una regla movió dieciséis análisis a «no elegible» de golpe: era
# lo correcto, pero nada lo habría dicho si no llega a mirarse a mano
# (AGENTS.md 51.4).
#
# Qué compara y por qué solo eso. Cuatro cosas que, cuando cambian de golpe,
# significan casi siempre un cambio de código y no un cambio del mundo:
#
#   1. convocatorias que desaparecen **sin que su plazo haya vencido**: si se
#      cerró, es normal; si no, alguien dejó de encontrarla;
#   2. convocatorias nuevas, que no son un problema pero explican el resto;
#   3. movimientos de elegibilidad en bloque, con el detalle de qué pasó a qué;
#   4. campos publicados que se vacían: un `objeto_y_actuaciones` que estaba y
#      deja de estar es una regresión invisible en los recuentos.
#
# No decide nada ni bloquea nada: describe. La decisión de mirar es de quien lee
# el resumen, igual que con las regresiones de embudo.

from datetime import date, datetime

# Un cambio de elegibilidad o de campo que afecte a menos registros que esto no
# se resume: en un producto de ochenta convocatorias, dos o tres movimientos son
# el funcionamiento normal, no una señal.
PRODUCT_CHANGE_MIN_RECORDS = 3

# Campos cuya desaparición importa: los que el dashboard enseña como contenido.
WATCHED_FIELDS = (
    "objeto_y_actuaciones",
    "eligible_actions",
    "summary",
    "url",
)


def _identity(record: dict) -> str:
    """Cómo se reconoce la misma convocatoria entre dos publicaciones."""
    for key in ("identifier", "bdns_id", "url"):
        value = str(record.get(key, "") or "").strip()
        if value:
            return f"{record.get('source', '')}|{key}|{value}"
    return f"{record.get('source', '')}|title|{str(record.get('title', '')).strip()[:120]}"


def _deadline_passed(record: dict, today: date) -> bool:
    """Si su plazo ya venció, que desaparezca es lo esperable."""
    raw = str(record.get("deadline_date", "") or "")[:10]
    if not raw:
        return False
    try:
        return datetime.fromisoformat(raw).date() < today
    except ValueError:
        return False


def compare_published_products(
    previous: list,
    current: list,
    today: date | None = None,
    min_records: int = PRODUCT_CHANGE_MIN_RECORDS,
) -> dict:
    """Resume qué ha cambiado entre dos versiones del JSON publicado.

    `previous` y `current` son las listas de convocatorias de cada versión.
    Devuelve siempre la misma forma, aunque no haya nada que contar, para que
    el resumen y la auditoría no tengan que distinguir casos.
    """
    today = today or date.today()
    antes = {_identity(item): item for item in (previous or []) if isinstance(item, dict)}
    ahora = {_identity(item): item for item in (current or []) if isinstance(item, dict)}

    desaparecidas = []
    for clave, item in antes.items():
        if clave in ahora:
            continue
        desaparecidas.append({
            "title": str(item.get("title", ""))[:120],
            "source": item.get("source", ""),
            "deadline_date": str(item.get("deadline_date", "") or ""),
            "deadline_passed": _deadline_passed(item, today),
        })
    sin_explicacion = [item for item in desaparecidas if not item["deadline_passed"]]

    movimientos = {}
    campos_vaciados = {}
    for clave, item in ahora.items():
        anterior = antes.get(clave)
        if anterior is None:
            continue
        if anterior.get("eligibility") != item.get("eligibility"):
            paso = f"{anterior.get('eligibility')}→{item.get('eligibility')}"
            movimientos[paso] = movimientos.get(paso, 0) + 1
        for campo in WATCHED_FIELDS:
            tenia = bool(str(anterior.get(campo, "") or "").strip()) if not isinstance(
                anterior.get(campo), list
            ) else bool(anterior.get(campo))
            tiene = bool(str(item.get(campo, "") or "").strip()) if not isinstance(
                item.get(campo), list
            ) else bool(item.get(campo))
            if tenia and not tiene:
                campos_vaciados[campo] = campos_vaciados.get(campo, 0) + 1

    return {
        "previous_count": len(antes),
        "current_count": len(ahora),
        "new": len(set(ahora) - set(antes)),
        "gone": len(desaparecidas),
        # El recuento va aparte de la muestra: la lista se recorta a diez para
        # no inflar la auditoría, y confundir una cosa con otra haría que el
        # resumen dijera «10 desaparecen» cuando fueran diecisiete.
        "gone_without_expiring_count": len(sin_explicacion),
        "gone_without_expiring": sin_explicacion[:10],
        "eligibility_moves": {
            paso: total for paso, total in sorted(movimientos.items())
            if total >= min_records
        },
        "emptied_fields": {
            campo: total for campo, total in sorted(campos_vaciados.items())
            if total >= min_records
        },
    }


def summarize_product_changes(report: dict) -> str:
    """Una línea para el resumen de la ejecución, o el silencio si no hay nada."""
    if not isinstance(report, dict) or not report.get("previous_count"):
        return "Producto: primera publicación comparable; nada con que contrastar."
    partes = [f"{report['current_count']} publicadas"]
    if report.get("new"):
        partes.append(f"{report['new']} nuevas")
    perdidas = report.get("gone_without_expiring_count") or 0
    if perdidas:
        partes.append(f"⚠ {perdidas} desaparecen sin vencer su plazo")
    for paso, total in (report.get("eligibility_moves") or {}).items():
        partes.append(f"{total} pasan de {paso}")
    for campo, total in (report.get("emptied_fields") or {}).items():
        partes.append(f"⚠ {total} se quedan sin {campo}")
    return "Producto: " + " · ".join(partes) + "."
