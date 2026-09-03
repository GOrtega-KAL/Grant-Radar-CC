# -*- coding: utf-8 -*-
# batch_analysis.py — el modo diferido: las mismas dos etapas, al 50 % de coste
#
# Por qué existe y por qué invierte el bucle
# ------------------------------------------
# El análisis instantáneo hace **dos llamadas encadenadas por convocatoria**:
# la evaluación se construye con lo que devolvió la extracción. En un lote eso
# no cabe, porque un lote se envía entero y se recoge entero. Así que el modo
# diferido recorre el problema por el otro eje: **un lote con todas las
# extracciones, y cuando termina, otro con todas las evaluaciones**.
#
# La Batches API cobra al 50 %: la ejecución completa de 83 convocatorias pasa
# de ~2,12 a ~1,06 USD. A cambio, el resultado tarda (casi siempre menos de una
# hora, con un máximo de 24), y por eso este modo **no espera**: envía, guarda
# el estado y termina. La recogida es otra invocación.
#
# Lo que este módulo NO hace, a propósito
# ---------------------------------------
# - **No arma prompts.** Los pide a `build_extraction_request()` y
#   `build_evaluation_request()`, que son los mismos que usa el modo
#   instantáneo. Es lo único que garantiza que los dos modos no diverjan.
# - **No reintenta dentro del lote.** El modo instantáneo reintenta al vuelo
#   con más tokens cuando el JSON no valida; aquí no se puede. Los fallos se
#   anotan y se informan, y como no entran en caché, la siguiente ejecución los
#   vuelve a seleccionar sin código nuevo. Inventar un reintento automático
#   dentro del lote escondería un problema que conviene ver.
# - **No decide qué se analiza.** Eso sigue en `claude_selection.py`, con su
#   orden y su barrera de coste.

import json
import logging
import os
from datetime import datetime, timezone

from grant_radar.analysis import (
    BATCH_PRICE_MULTIPLIER,
    CLAUDE_MODEL,
    build_evaluation_request,
    build_extraction_request,
    message_usage_record,
    structured_output_text,
)
from grant_radar.cache import cache_key
from grant_radar.versions import (
    ANALYSIS_PROMPT_VERSION,
    PARTNER_CATALOG_VERSION,
    PROFILE_VERSION,
)

log = logging.getLogger("grant_radar")

BATCH_STATE_SCHEMA_VERSION = 1

# Las dos fases, en el orden en que ocurren. Son números y no cadenas porque el
# panel enseña «fase 1 de 2» y conviene que la aritmética esté en un sitio.
PHASE_EXTRACTION = 1
PHASE_EVALUATION = 2
TOTAL_PHASES = 2

# Estados posibles del archivo de estado. Son explícitos —y no se deducen de
# qué campos estén rellenos— porque el panel y la consola tienen que poder
# decir en qué punto está el proceso sin interpretar nada.
STATE_PHASE1_RUNNING = "phase1_running"
STATE_PHASE1_DONE = "phase1_done"
STATE_PHASE2_RUNNING = "phase2_running"
STATE_DONE = "done"
STATE_FAILED = "failed"

# Un lote de la API caduca a las 24 h. Se guarda para poder decir «esto ya no
# va a llegar» en vez de sondear indefinidamente.
BATCH_MAX_HOURS = 24


class BatchStateError(RuntimeError):
    """El estado en disco no sirve para continuar, y hay que decir por qué."""


def current_versions() -> dict:
    """Las tres versiones que definen el criterio de un análisis."""
    return {
        "analysis": ANALYSIS_PROMPT_VERSION,
        "profile": PROFILE_VERSION,
        "partner_catalog": PARTNER_CATALOG_VERSION,
    }


# ─── El archivo de estado ────────────────────────────────────────────────────

def load_batch_state(state_file: str) -> dict | None:
    """Lee el estado, o `None` si no hay lote en vuelo."""
    if not os.path.exists(state_file):
        return None
    try:
        with open(state_file, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning(f"Estado de lote ilegible ({exc}); se ignora")
        return None
    if not isinstance(state, dict) or "state" not in state:
        log.warning("Estado de lote con forma inesperada; se ignora")
        return None
    return state


def save_batch_state(state: dict, state_file: str) -> None:
    directory = os.path.dirname(state_file)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)


def clear_batch_state(state_file: str) -> None:
    """Retira el estado cuando el ciclo termina, para que no quede fantasma."""
    try:
        if os.path.exists(state_file):
            os.remove(state_file)
    except OSError as exc:
        log.warning(f"No se pudo retirar el estado de lote: {exc}")


def assert_versions_match(state: dict) -> None:
    """El criterio no puede cambiar entre el envío y la recogida.

    `cache_key()` incluye las versiones de prompt, perfil y catálogo, así que
    si alguien las toca mientras el lote vuela, los `custom_id` que vuelven ya
    no corresponden a ninguna convocatoria seleccionable y los resultados serían
    de otro criterio. Es preferible negarse a recoger —el lote no se pierde,
    basta con volver a las versiones de entonces— que mezclar dos criterios en
    el mismo producto sin que nadie lo vea.
    """
    guardadas = state.get("versions") or {}
    vigentes = current_versions()
    distintas = {
        nombre: (guardadas.get(nombre), valor)
        for nombre, valor in vigentes.items()
        if guardadas.get(nombre) != valor
    }
    if distintas:
        detalle = "; ".join(
            f"{nombre}: el lote se envió con «{antes}» y ahora rige «{ahora}»"
            for nombre, (antes, ahora) in sorted(distintas.items())
        )
        raise BatchStateError(
            "El criterio de análisis ha cambiado desde que se envió el lote, "
            f"así que sus resultados ya no son comparables. {detalle}. "
            "Vuelve a esas versiones para recogerlo, o descarta el lote con "
            "--batch-abandon."
        )


def batch_age_hours(state: dict, now: datetime | None = None) -> float | None:
    enviado = str(state.get("submitted_at", ""))
    if not enviado:
        return None
    try:
        marca = datetime.fromisoformat(enviado)
    except ValueError:
        return None
    if marca.tzinfo is None:
        marca = marca.replace(tzinfo=timezone.utc)
    ahora = now or datetime.now(timezone.utc)
    return round((ahora - marca).total_seconds() / 3600, 2)


# ─── Construcción y envío ────────────────────────────────────────────────────

def build_batch_requests(items: list[dict], phase: int, facts_by_key: dict | None = None):
    """Las peticiones de una fase, indexadas por `cache_key(conv)`.

    El `custom_id` es la clave de caché, que ya es un sha256 estable de 64
    caracteres: es válida como identificador de lote y además es la clave con
    la que se guardará el resultado, así que el mapeo de vuelta es directo y no
    hace falta una tabla intermedia que se pueda desincronizar.
    """
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    from anthropic.lib._parse._transform import transform_schema as anthropic_transform_schema

    peticiones = []
    for conv in items:
        clave = cache_key(conv)
        if phase == PHASE_EXTRACTION:
            solicitud = build_extraction_request(conv)
        else:
            hechos = (facts_by_key or {}).get(clave)
            if hechos is None:
                continue
            solicitud = build_evaluation_request(conv, hechos)
        peticiones.append(Request(
            custom_id=clave,
            params=MessageCreateParamsNonStreaming(
                model=CLAUDE_MODEL,
                max_tokens=solicitud.max_tokens,
                temperature=0,
                system=solicitud.system,
                messages=[{"role": "user", "content": solicitud.user}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": anthropic_transform_schema(
                            solicitud.schema.model_json_schema()
                        ),
                    }
                },
            ),
        ))
    return peticiones


def submit_batch(client, items: list[dict], phase: int, facts_by_key: dict | None = None) -> str:
    """Envía una fase y devuelve el identificador del lote."""
    peticiones = build_batch_requests(items, phase, facts_by_key)
    if not peticiones:
        raise BatchStateError("No hay ninguna petición que enviar en esta fase.")
    lote = client.messages.batches.create(requests=peticiones)
    log.info(
        f"  Lote de la fase {phase} enviado: {lote.id} "
        f"({len(peticiones)} peticiones)"
    )
    return lote.id


def poll_batch(client, batch_id: str) -> dict:
    """El estado del lote, sin interpretarlo."""
    lote = client.messages.batches.retrieve(batch_id)
    recuentos = getattr(lote, "request_counts", None)
    return {
        "id": batch_id,
        "processing_status": getattr(lote, "processing_status", "unknown"),
        "ended": getattr(lote, "processing_status", "") == "ended",
        "counts": {
            nombre: int(getattr(recuentos, nombre, 0) or 0)
            for nombre in ("processing", "succeeded", "errored", "canceled", "expired")
        } if recuentos else {},
    }


def collect_batch(client, batch_id: str, schema, stage: str) -> tuple[dict, dict, list]:
    """Recoge un lote terminado: `(modelos, consumos, fallos)`.

    Los resultados llegan **en cualquier orden**: se indexan siempre por
    `custom_id` y nunca por posición.
    """
    modelos, consumos, fallos = {}, {}, []
    for resultado in client.messages.batches.results(batch_id):
        clave = getattr(resultado, "custom_id", "")
        tipo = getattr(getattr(resultado, "result", None), "type", "unknown")
        if tipo != "succeeded":
            fallos.append({"custom_id": clave, "reason": tipo})
            continue
        mensaje = resultado.result.message
        consumos[clave] = message_usage_record(
            mensaje, stage, valid_output=False,
            price_multiplier=BATCH_PRICE_MULTIPLIER,
        )
        texto = structured_output_text(mensaje)
        if not texto:
            fallos.append({"custom_id": clave, "reason": "respuesta vacía"})
            continue
        try:
            modelos[clave] = schema.model_validate_json(texto)
            consumos[clave]["valid_output"] = True
        except Exception as exc:
            # El lote no reintenta: se anota y la próxima ejecución lo vuelve a
            # seleccionar, porque sin resultado válido no entra en caché.
            fallos.append({"custom_id": clave, "reason": f"salida inválida: {exc}"[:200]})
    return modelos, consumos, fallos


# ─── Construir el estado ─────────────────────────────────────────────────────

def empty_stage_usage(stage: str) -> dict:
    """Consumo cero para una etapa que no dejó registro.

    Ocurre cuando una fase se recoge de un estado antiguo o cuando un resultado
    llegó sin bloque de uso. Preferimos publicar un coste **infravalorado y
    visible** a que la suma reviente y se pierda un análisis ya pagado.
    """
    return {
        "stage": stage, "attempt": 1, "valid_output": True,
        "api_calls": 1, "retry_api_calls": 0,
        "input_tokens": 0, "output_tokens": 0,
        "cache_write_tokens": 0, "cache_read_tokens": 0,
        "total_tokens": 0, "estimated_cost_usd": 0.0,
    }


def new_batch_state(items: list[dict], batch_id: str) -> dict:
    """El estado tras enviar la fase 1.

    **Guarda las convocatorias enteras, no un resumen.** La fase 2 tiene que
    evaluar exactamente la misma convocatoria que extrajo la fase 1: si se
    volviera a recopilar para recuperarlas, una fuente que haya cambiado el
    texto entre medias daría otro `cache_key` y el resultado ya pagado se
    quedaría huérfano. Son unos pocos megas en local, que es un precio barato
    por esa garantía —y es lo mismo que ya hace la caché con `raw_document`—.
    """
    return {
        "schema_version": BATCH_STATE_SCHEMA_VERSION,
        "state": STATE_PHASE1_RUNNING,
        "batch_id": batch_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "model": CLAUDE_MODEL,
        "versions": current_versions(),
        "items": {cache_key(conv): conv for conv in items},
        "facts": {},
        "usage": {},
        "failures": [],
    }


def store_phase1_results(state: dict, facts_by_key: dict, usage: dict, failures: list) -> dict:
    """Anota lo que devolvió la fase 1 y deja el estado listo para la fase 2.

    Los hechos se guardan **serializados** (`model_dump`), no como objetos
    Pydantic: el estado viaja por un archivo JSON entre dos invocaciones
    distintas del programa.
    """
    state["facts"] = {
        clave: modelo.model_dump() for clave, modelo in facts_by_key.items()
    }
    # Indexado por clave, no aplanado: en la recogida final hay que sumar el
    # consumo de las dos fases **de cada convocatoria**, no el del lote entero.
    state["usage"] = {**(state.get("usage") or {}), **usage}
    state["failures"] = list(state.get("failures") or []) + list(failures)
    state["state"] = STATE_PHASE1_DONE
    return state


def restore_facts(state: dict, schema) -> dict:
    """Rehidrata los hechos de la fase 1 desde el archivo de estado."""
    restaurados = {}
    for clave, volcado in (state.get("facts") or {}).items():
        try:
            restaurados[clave] = schema.model_validate(volcado)
        except Exception as exc:
            log.warning(f"Hechos ilegibles para {clave[:12]}…: {exc}")
    return restaurados


def batch_items(state: dict) -> list[dict]:
    """Las convocatorias del lote, en orden estable."""
    return [state["items"][clave] for clave in sorted(state.get("items") or {})]


# ─── Lo que ven la consola y el panel ────────────────────────────────────────

def summarize_batch_state(state: dict | None, now: datetime | None = None) -> str:
    if not state:
        return "No hay ningún lote en vuelo."
    fase = PHASE_EVALUATION if state["state"] in (
        STATE_PHASE1_DONE, STATE_PHASE2_RUNNING
    ) else PHASE_EXTRACTION
    horas = batch_age_hours(state, now)
    partes = [
        f"Lote en estado «{state['state']}»",
        f"fase {fase} de {TOTAL_PHASES}",
        f"{len(state.get('items') or {})} convocatorias",
    ]
    if horas is not None:
        partes.append(f"enviado hace {horas:.1f} h")
        if horas > BATCH_MAX_HOURS:
            partes.append("CADUCADO: la API descarta los lotes a las 24 h")
    return " · ".join(partes)


def batch_state_for_dashboard(
    state: dict | None,
    pending_keys: set | None = None,
    now: datetime | None = None,
) -> dict:
    """El bloque `batch` de `estado_recopilacion.json`.

    `pending_keys` son las candidatas que la recopilación de hoy analizaría.
    Las que **no** estén en el lote se cuentan como `waiting_outside`: es el
    caso que pidió el usuario, cuando entre el envío y la recogida aparece una
    convocatoria nueva. No se añade al lote en vuelo —eso obligaría a
    reenviarlo entero— pero tiene que verse que está esperando.
    """
    if not state:
        return {}
    en_lote = set((state.get("items") or {}).keys())
    fuera = sorted((pending_keys or set()) - en_lote)
    fase = PHASE_EVALUATION if state["state"] in (
        STATE_PHASE1_DONE, STATE_PHASE2_RUNNING
    ) else PHASE_EXTRACTION
    return {
        "state": state["state"],
        "phase": fase,
        "of_phases": TOTAL_PHASES,
        "items": len(en_lote),
        "submitted_at": state.get("submitted_at", ""),
        "age_hours": batch_age_hours(state, now),
        "waiting_outside": len(fuera),
    }
