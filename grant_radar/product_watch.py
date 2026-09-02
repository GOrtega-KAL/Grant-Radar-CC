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
# Desde el 02/09/2026 el módulo vigila dos cosas, no una:
# `compare_published_products()` compara producto contra producto, y
# `compare_collection_against_product()` compara la recopilación diaria contra
# el producto publicado. Son distintas a propósito y no se pueden intercambiar:
# lo recopilado no ha pasado por Haiku y no tiene resumen ni actuaciones, así
# que la primera lo leería como una regresión masiva de campos vacíos.
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


def stable_identity(record: dict) -> str:
    """Cómo se reconoce la misma convocatoria entre dos publicaciones.

    Era `_identity()`, privada, y solo la usaba la comparación de productos.
    Se hace pública el 02/09/2026 porque el JSON publicado la necesita como
    campo (`stable_key`): el `id` que se publicaba era un contador posicional,
    así que el 42 de hoy y el 42 de mañana son convocatorias distintas y nada
    externo al archivo —unos favoritos, un enlace profundo, una nota— podía
    referirse a una convocatoria sin equivocarse en silencio.

    **Una sola implementación, a propósito.** Publicar la clave por un lado y
    compararla por otro invita a que las dos se separen sin que nadie lo note,
    que es exactamente el fallo que esta función existe para evitar.

    Aviso para quien la llame desde el pipeline: espera el registro **tal y
    como se publica**. El `url` de una convocatoria recién recopilada todavía
    no ha pasado por `_normalize_public_url()`, y para las que resuelven su
    identidad por url —10 de las 77 del producto del 21/08— eso daría una
    clave distinta de la publicada. Para eso está `public_stable_key()` en
    `public_output.py`.
    """
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
    antes = {stable_identity(item): item for item in (previous or []) if isinstance(item, dict)}
    ahora = {stable_identity(item): item for item in (current or []) if isinstance(item, dict)}

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


# Qué se considera «cierra pronto». Catorce días es el plazo con el que
# AGENTS.md 54.2 midió el desfase del producto, y el mínimo con el que una
# propuesta de Horizon todavía se puede preparar sin heroicidades.
COLLECTION_SOON_DAYS = 14


def compare_collection_against_product(
    previous_published: list,
    collected: list,
    collected_keys: list | None = None,
    today: date | None = None,
    soon_days: int = COLLECTION_SOON_DAYS,
) -> dict:
    """Qué ha encontrado la recopilación diaria que el producto no tiene.

    Nace de un hueco del flujo acordado el 21/08/2026: la recopilación
    `--no-claude` corre a diario y publica `estado_recopilacion.json`, pero ese
    archivo solo decía **cuántas** convocatorias esperaban análisis. Nadie se
    enteraba de que hoy habían aparecido cinco nuevas, ni de cuál cerraba en
    doce días.

    **Por qué no vale `compare_published_products()`**, que a primera vista
    calcula justo esto. Aquella compara producto contra producto. Aquí el lado
    derecho es la recopilación **cruda**: convocatorias que han pasado el
    filtro determinista pero no el análisis, y que por tanto no tienen
    `summary`, ni `objeto_y_actuaciones`, ni `eligible_actions`. Pasarlas por
    la otra función marcaría esos tres campos como «vaciados» en las setenta y
    siete fichas, y el aviso diario abriría con una regresión inventada.

    Los tres números no salen del mismo sitio, y conviene saberlo al leerlos:

    - `new_since_publication` es la diferencia real entre los dos lados. Son
      **detectadas, sin analizar**: han pasado el filtro determinista, no el de
      Haiku. Venderlas como oportunidades sería contar como encontrado lo que
      todavía no se ha evaluado.
    - `expiring_soon` y `expired` describen **el producto publicado**, no la
      recopilación: son las fichas que el usuario está mirando ahora mismo y
      cuyo plazo se acaba o se acabó. Es lo que hace útil el aviso — el desfase
      duele cuando lo que caduca es lo que ya está en pantalla.

    `collected_keys` deja inyectar las claves ya calculadas con
    `public_stable_key()`. Sin ellas se usa `stable_identity()` directamente
    sobre lo recopilado, que para las convocatorias que se identifican por url
    daría una clave distinta de la publicada —el `url` todavía no ha pasado por
    `_normalize_public_url()`— y produciría altas y bajas falsas.
    """
    today = today or date.today()
    publicadas = [item for item in (previous_published or []) if isinstance(item, dict)]
    recopiladas = [item for item in (collected or []) if isinstance(item, dict)]

    antes = {stable_identity(item) for item in publicadas}
    if collected_keys is None:
        claves = [stable_identity(item) for item in recopiladas]
    else:
        claves = [str(clave) for clave in collected_keys]

    nuevas = []
    for clave, item in zip(claves, recopiladas):
        if clave in antes:
            continue
        nuevas.append({
            "title": " ".join(str(item.get("title", "")).split())[:120],
            "source": str(item.get("source", "")),
            "deadline_date": str(item.get("deadline_date", "") or ""),
        })

    proximas = []
    vencidas = 0
    for item in publicadas:
        dias = _days_to_deadline(item, today)
        if dias is None:
            continue
        if dias < 0:
            vencidas += 1
        elif dias <= soon_days:
            proximas.append({
                "title": " ".join(str(item.get("title", "")).split())[:120],
                "source": str(item.get("source", "")),
                "deadline_date": str(item.get("deadline_date", "") or "")[:10],
                "days_left": dias,
            })
    proximas.sort(key=lambda entry: entry["days_left"])

    return {
        "new_since_publication": len(nuevas),
        # La muestra va aparte del recuento y recortada, por la misma razón que
        # en `compare_published_products()`: decir «3 nuevas» cuando son once
        # sería quedarse corto justo donde importa.
        "new_sample": nuevas[:10],
        "expiring_soon": len(proximas),
        "expiring_soon_sample": proximas[:3],
        "expired": vencidas,
        "soon_days": soon_days,
    }


def _days_to_deadline(record: dict, today: date) -> int | None:
    """Días hasta el cierre publicado, o None si la ficha no trae fecha.

    Sin fecha no se puede decir ni que caduque ni que aguante: quedarse fuera
    del recuento es más honesto que suponerle un plazo.
    """
    raw = str(record.get("deadline_date", "") or "")[:10]
    if not raw:
        return None
    try:
        return (datetime.fromisoformat(raw).date() - today).days
    except ValueError:
        return None

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


def summarize_collection_changes(report: dict) -> str:
    """Una línea para la consola de la recopilación diaria.

    «Detectadas, sin analizar» no es una cortesía de redacción: han pasado el
    filtro determinista y no el de Haiku, y llamarlas oportunidades sería
    vender como encontrado lo que todavía no se ha evaluado.
    """
    if not isinstance(report, dict):
        return "Recopilación: sin comparación con lo publicado."
    partes = []
    nuevas = report.get("new_since_publication") or 0
    if nuevas:
        partes.append(
            f"{nuevas} sin publicar (detectadas, sin analizar)"
        )
    proximas = report.get("expiring_soon") or 0
    if proximas:
        dias = report.get("soon_days", COLLECTION_SOON_DAYS)
        partes.append(f"{proximas} publicadas cierran en {dias} días o menos")
    vencidas = report.get("expired") or 0
    if vencidas:
        partes.append(f"{vencidas} publicadas ya vencidas")
    if not partes:
        return "Recopilación: sin novedades respecto a lo publicado."
    # La más cercana, con nombre: quien lanza el .bat diario lee esta línea y
    # «doce cierran pronto» no dice cuál hay que mirar hoy.
    muestra = report.get("expiring_soon_sample") or []
    if muestra:
        primera = muestra[0]
        partes.append(
            f"la primera en {primera.get('days_left')} días: "
            f"{primera.get('title', '')}"
        )
    return "Recopilación: " + " · ".join(partes) + "."
