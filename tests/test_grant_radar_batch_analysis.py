# Pruebas de grant_radar/batch_analysis.py con import estándar (sin runpy).
#
# El modo por lotes no se puede probar llamando a la API: cada ejecución
# costaría dinero y tardaría una hora. Lo que sí se puede —y es donde están los
# errores de verdad de este tipo de código— es sustituir el cliente por un
# doble que devuelva los resultados **desordenados** y con fallos mezclados,
# que es exactamente lo que hace la Batches API.

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from grant_radar.batch_analysis import (
    BATCH_PROCESSING_HOURS,
    BATCH_RESULTS_DAYS,
    PHASE_EVALUATION,
    PHASE_EXTRACTION,
    STATE_PHASE1_DONE,
    STATE_PHASE1_RUNNING,
    STATE_PHASE2_RUNNING,
    BatchStateError,
    assert_versions_match,
    batch_age_hours,
    batch_state_for_dashboard,
    build_batch_requests,
    clear_batch_state,
    collect_batch,
    current_versions,
    format_batch_poll,
    list_recent_batches,
    load_batch_state,
    save_batch_state,
    submit_batch,
    summarize_batch_state,
)
from grant_radar.cache import cache_key
from grant_radar.claude_schemas import CallFacts
from tests.test_grant_radar_claude_schemas import _minimal_call_facts


def _conv(titulo, **extra):
    base = {
        "title": titulo, "source": "BDNS", "url": f"https://x.test/{titulo[:6]}",
        "org": "Org", "description": "Eficiencia energética industrial. " * 12,
        "keywords_found": [], "source_type": "x",
    }
    base.update(extra)
    return base


class _Uso:
    def __init__(self, entrada=1000, salida=200):
        self.input_tokens = entrada
        self.output_tokens = salida
        self.cache_creation_input_tokens = 0
        self.cache_read_input_tokens = 0
        self.service_tier = "batch"


class _Bloque:
    def __init__(self, texto):
        self.type = "text"
        self.text = texto


class _Mensaje:
    def __init__(self, texto, entrada=1000, salida=200):
        self.content = [_Bloque(texto)]
        self.usage = _Uso(entrada, salida)


class _Resultado:
    def __init__(self, custom_id, tipo="succeeded", texto="{}"):
        self.custom_id = custom_id
        self.result = type("R", (), {
            "type": tipo,
            "message": _Mensaje(texto) if tipo == "succeeded" else None,
        })()


class _ClienteFalso:
    """Lo justo de la Batches API, y con la mala educación que tiene de verdad."""

    def __init__(self, resultados=None, estado="ended"):
        self._resultados = resultados or []
        self._estado = estado
        self.enviados = []
        self.messages = type("M", (), {"batches": self})()

    def create(self, requests):
        self.enviados.append(list(requests))
        return type("B", (), {"id": f"msgbatch_falso_{len(self.enviados)}"})()

    def retrieve(self, batch_id):
        return type("B", (), {
            "processing_status": self._estado,
            "request_counts": type("C", (), {
                "processing": 0, "succeeded": len(self._resultados),
                "errored": 0, "canceled": 0, "expired": 0,
            })(),
        })()

    def results(self, batch_id):
        return iter(self._resultados)


class BuildRequestsTests(unittest.TestCase):
    def test_the_custom_id_is_the_cache_key(self):
        """No hay tabla intermedia que se pueda desincronizar.

        El `custom_id` es la misma clave con la que se guardará el resultado,
        así que un resultado nunca puede acabar guardado en la ficha de otra
        convocatoria.
        """
        convs = [_conv("Recuperación de calor"), _conv("Hornos de hidrógeno")]
        peticiones = build_batch_requests(convs, PHASE_EXTRACTION)
        self.assertEqual(
            [p["custom_id"] for p in peticiones],
            [cache_key(c) for c in convs],
        )

    def test_the_batch_sends_exactly_what_the_builders_produce(self):
        """El lote no puede armar un prompt distinto al del modo instantáneo."""
        from grant_radar.analysis import build_extraction_request

        conv = _conv("Descarbonización industrial")
        peticion = build_batch_requests([conv], PHASE_EXTRACTION)[0]
        esperado = build_extraction_request(conv)
        self.assertEqual(peticion["params"]["system"], esperado.system)
        self.assertEqual(
            peticion["params"]["messages"][0]["content"], esperado.user,
        )
        self.assertEqual(peticion["params"]["max_tokens"], esperado.max_tokens)
        self.assertEqual(peticion["params"]["temperature"], 0)
        self.assertIn("json_schema", json.dumps(peticion["params"]["output_config"]))

    def test_phase_two_skips_what_phase_one_did_not_return(self):
        """Una convocatoria cuya extracción falló no puede evaluarse.

        Sin esto se enviaría una evaluación sin hechos, que produciría una
        ficha con apariencia normal y contenido inventado.
        """
        con_hechos, sin_hechos = _conv("Con hechos"), _conv("Sin hechos")
        hechos = {cache_key(con_hechos): _minimal_call_facts()}
        peticiones = build_batch_requests(
            [con_hechos, sin_hechos], PHASE_EVALUATION, hechos,
        )
        self.assertEqual([p["custom_id"] for p in peticiones],
                         [cache_key(con_hechos)])

    def test_submitting_nothing_is_an_error_not_a_silent_no_op(self):
        with self.assertRaises(BatchStateError):
            submit_batch(_ClienteFalso(), [], PHASE_EXTRACTION)


class CollectTests(unittest.TestCase):
    VALIDO = json.dumps({
        "call_status": "open", "programme": "", "action_type": "",
        "applicant_types": [], "eligible_geographies": [],
        "eligible_entity_types": [], "eligibility_evidence": [],
        "budget_total_eur": -1, "funding_rate_percent": -1,
        "project_budget_eur": -1, "project_cost_min_eur": -1, "grant_max_eur": -1,
        "deadline_date": "", "trl_min": 0, "trl_max": 0, "trl_source": "",
        "consortium_required": "unknown", "consortium_evidence": "",
        "required_topics": [], "eligible_actions": [], "expected_outcomes": [],
        "funding_lines": [], "evidence": [], "missing_fields": [],
    })

    def test_results_are_indexed_by_id_never_by_position(self):
        """La API los devuelve en cualquier orden. Es su comportamiento normal.

        Si se indexaran por posición, el análisis de una convocatoria acabaría
        publicado en la ficha de otra — sin error y sin que ningún recuento lo
        delatara.
        """
        cliente = _ClienteFalso([
            _Resultado("clave_c", texto=self.VALIDO),
            _Resultado("clave_a", texto=self.VALIDO),
            _Resultado("clave_b", texto=self.VALIDO),
        ])
        modelos, consumos, fallos = collect_batch(
            cliente, "msgbatch_x", CallFacts, "extracción factual",
        )
        self.assertEqual(sorted(modelos), ["clave_a", "clave_b", "clave_c"])
        self.assertEqual(fallos, [])
        self.assertEqual(sorted(consumos), ["clave_a", "clave_b", "clave_c"])

    def test_failures_are_recorded_and_do_not_abort_the_rest(self):
        cliente = _ClienteFalso([
            _Resultado("buena", texto=self.VALIDO),
            _Resultado("errada", tipo="errored"),
            _Resultado("vacia", texto="   "),
            _Resultado("rota", texto="{no es json"),
            _Resultado("caducada", tipo="expired"),
        ])
        modelos, _, fallos = collect_batch(
            cliente, "msgbatch_x", CallFacts, "extracción factual",
        )
        self.assertEqual(list(modelos), ["buena"])
        self.assertEqual(
            sorted(f["custom_id"] for f in fallos),
            ["caducada", "errada", "rota", "vacia"],
        )

    def test_batch_pricing_is_half(self):
        """El descuento del 50 % tiene que verse en el coste publicado."""
        from grant_radar.analysis import message_usage_record

        mensaje = _Mensaje(self.VALIDO)
        instantaneo = message_usage_record(mensaje, "extracción factual")
        cliente = _ClienteFalso([_Resultado("k", texto=self.VALIDO)])
        _, consumos, _ = collect_batch(
            cliente, "msgbatch_x", CallFacts, "extracción factual",
        )
        self.assertAlmostEqual(
            consumos["k"]["estimated_cost_usd"],
            instantaneo["estimated_cost_usd"] / 2,
            places=6,
        )
        # Los tokens NO se dividen: lo que cambia es la tarifa, no el consumo.
        self.assertEqual(
            consumos["k"]["total_tokens"], instantaneo["total_tokens"],
        )


class VersionGuardTests(unittest.TestCase):
    """El criterio no puede cambiar entre el envío y la recogida."""

    def test_matching_versions_pass(self):
        assert_versions_match({"versions": current_versions()})

    def test_a_changed_version_refuses_and_says_which(self):
        estado = {"versions": {**current_versions(), "profile": "kalfrisa-vieja"}}
        with self.assertRaises(BatchStateError) as ctx:
            assert_versions_match(estado)
        mensaje = str(ctx.exception)
        self.assertIn("profile", mensaje)
        self.assertIn("kalfrisa-vieja", mensaje)
        self.assertIn("--batch-abandon", mensaje)


class StateFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ruta = os.path.join(self.dir, "batch_state.json")

    def test_round_trip(self):
        estado = {
            "schema_version": 1, "state": STATE_PHASE1_RUNNING,
            "batch_id": "msgbatch_x", "versions": current_versions(),
            "items": {"a": {"title": "A"}},
        }
        save_batch_state(estado, self.ruta)
        self.assertEqual(load_batch_state(self.ruta), estado)
        clear_batch_state(self.ruta)
        self.assertIsNone(load_batch_state(self.ruta))

    def test_a_corrupt_state_is_ignored_not_fatal(self):
        with open(self.ruta, "w", encoding="utf-8") as handle:
            handle.write("{esto no es json")
        self.assertIsNone(load_batch_state(self.ruta))

    def test_missing_state_is_simply_no_batch(self):
        self.assertIsNone(load_batch_state(self.ruta))


class DashboardStateTests(unittest.TestCase):
    """La carrera que pidió el usuario el 03/09/2026.

    Entre el envío de un lote y su recogida, un `--no-claude` puede encontrar
    convocatorias nuevas. No se añaden al lote en vuelo —eso obligaría a
    reenviarlo entero— pero **tienen que verse esperando**, o alguien creerá
    que están analizándose.
    """

    def _estado(self, claves, estado=STATE_PHASE1_RUNNING, hace_horas=0.5):
        enviado = datetime.now(timezone.utc) - timedelta(hours=hace_horas)
        return {
            "schema_version": 1, "state": estado, "batch_id": "msgbatch_x",
            "submitted_at": enviado.isoformat(),
            "versions": current_versions(),
            "items": {c: {"title": c} for c in claves},
        }

    def test_new_calls_appear_as_waiting_outside_the_batch(self):
        estado = self._estado(["a", "b", "c"])
        bloque = batch_state_for_dashboard(estado, pending_keys={"a", "b", "c", "d", "e"})
        self.assertEqual(bloque["items"], 3)
        self.assertEqual(bloque["waiting_outside"], 2)
        self.assertEqual(bloque["phase"], PHASE_EXTRACTION)
        self.assertEqual(bloque["of_phases"], 2)

    def test_nothing_new_means_nothing_waiting(self):
        estado = self._estado(["a", "b"])
        bloque = batch_state_for_dashboard(estado, pending_keys={"a", "b"})
        self.assertEqual(bloque["waiting_outside"], 0)

    def test_a_call_already_in_the_batch_is_never_double_counted(self):
        estado = self._estado(["a", "b"])
        bloque = batch_state_for_dashboard(estado, pending_keys={"a"})
        self.assertEqual(bloque["waiting_outside"], 0)

    def test_phase_two_is_reported_as_phase_two(self):
        for estado in (STATE_PHASE1_DONE, STATE_PHASE2_RUNNING):
            with self.subTest(estado=estado):
                bloque = batch_state_for_dashboard(self._estado(["a"], estado))
                self.assertEqual(bloque["phase"], PHASE_EVALUATION)

    def test_without_a_batch_the_block_is_empty(self):
        self.assertEqual(batch_state_for_dashboard(None), {})
        self.assertEqual(summarize_batch_state(None), "No hay ningún lote en vuelo.")

    def test_a_batch_still_processing_past_its_window_is_flagged(self):
        """Las 24 h son de PROCESAMIENTO, no de recogida.

        Medido contra un lote real el 03/09/2026: `expires_at` sale a creación
        + 24 h, el lote terminó en 3 min 48 s y sus resultados se siguen
        recuperando después. Lo que caduca es lo que Anthropic no haya
        procesado; lo terminado dura 29 días.

        Así que el aviso solo tiene sentido cuando el lote **sigue corriendo**
        pasada su ventana. Decirlo de uno ya terminado asustaría sin motivo, y
        con ejecuciones manuales eso empujaría a recoger con prisa.
        """
        corriendo = self._estado(["a"], hace_horas=BATCH_PROCESSING_HOURS + 2)
        self.assertIn("AVISO", summarize_batch_state(corriendo))

        for estado in (STATE_PHASE1_DONE, "done"):
            with self.subTest(estado=estado):
                terminado = self._estado(
                    ["a"], estado=estado, hace_horas=BATCH_PROCESSING_HOURS + 48,
                )
                self.assertNotIn("AVISO", summarize_batch_state(terminado))

    def test_a_recent_batch_is_never_flagged(self):
        self.assertNotIn("AVISO", summarize_batch_state(self._estado(["a"], hace_horas=3)))

    def test_the_results_window_is_much_longer_than_the_processing_one(self):
        """El dato que quita la prisa: 29 días para recoger, 24 h para procesar."""
        self.assertGreater(BATCH_RESULTS_DAYS * 24, BATCH_PROCESSING_HOURS * 20)

    def test_age_is_measured_in_hours(self):
        estado = self._estado(["a"], hace_horas=3)
        self.assertAlmostEqual(batch_age_hours(estado), 3.0, places=1)


class BatchPollTests(unittest.TestCase):
    """El sondeo de solo lectura, que es la red diaria del 04/09/2026.

    Existe por un fallo concreto: `--batch-status` lee solo el archivo local,
    que dice lo que se sabía al enviar y nadie actualiza. Un lote pasó 16,5 h
    marcado «phase1_running» habiendo terminado a los 2 min 29 s, y descubrirlo
    obligaba a llamar a `--batch-collect`, que **paga** (AGENTS.md 64.2).

    `format_batch_poll()` es pura, así que aquí se prueban las situaciones que
    no se pueden provocar en vivo sin gastar: el lote terminado sin recoger, el
    que devuelve errores y el huérfano que el archivo local no conoce.
    """

    def _estado(self, estado=STATE_PHASE1_RUNNING, hace_horas=16.5, lote="msgbatch_x"):
        enviado = datetime.now(timezone.utc) - timedelta(hours=hace_horas)
        return {
            "schema_version": 1, "state": estado, "batch_id": lote,
            "submitted_at": enviado.isoformat(),
            "versions": current_versions(),
            "items": {"a": {"title": "A"}, "b": {"title": "B"}},
        }

    def _remoto(self, estado="ended", **recuentos):
        base = {"processing": 0, "succeeded": 2, "errored": 0,
                "canceled": 0, "expired": 0}
        base.update(recuentos)
        return {
            "id": "msgbatch_x", "processing_status": estado,
            "ended": estado == "ended", "counts": base,
            "created_at": datetime(2026, 9, 3, 13, 23, tzinfo=timezone.utc),
            "ended_at": datetime(2026, 9, 3, 13, 26, tzinfo=timezone.utc),
            "expires_at": datetime(2026, 9, 4, 13, 23, tzinfo=timezone.utc),
        }

    def test_a_finished_batch_nobody_collected_is_said_out_loud(self):
        """El caso exacto que motivó el comando: dinero pagado y parado."""
        texto = "\n".join(format_batch_poll(self._estado(), self._remoto()))
        self.assertIn("LOTE TERMINADO Y SIN RECOGER", texto)
        self.assertIn("--batch-collect", texto)
        self.assertIn("2026-09-03 13:26", texto)

    def test_a_batch_still_processing_does_not_shout(self):
        texto = "\n".join(format_batch_poll(
            self._estado(), self._remoto("in_progress", processing=2, succeeded=0)
        ))
        self.assertNotIn("SIN RECOGER", texto)
        self.assertIn("Sigue procesándose", texto)
        self.assertIn(str(BATCH_RESULTS_DAYS), texto)

    def test_errors_and_expiries_are_reported_when_collecting_is_due(self):
        texto = "\n".join(format_batch_poll(
            self._estado(), self._remoto(succeeded=0, errored=1, expired=1)
        ))
        self.assertIn("1 con error", texto)
        self.assertIn("1 caducadas", texto)

    def test_a_batch_the_local_file_does_not_know_is_flagged(self):
        """El caso de `batch_state.json` perdido: está en .gitignore.

        Es el motivo de preguntar a la API en vez de fiarse del archivo: si el
        marcador local desaparece, el trabajo pagado sigue en Anthropic y nadie
        sabría recogerlo.
        """
        recientes = [{
            "id": "msgbatch_huerfano", "processing_status": "in_progress",
            "counts": {"processing": 40},
            "created_at": datetime(2026, 9, 4, 6, 0, tzinfo=timezone.utc),
            "ended_at": None,
        }]
        texto = "\n".join(format_batch_poll(None, None, recientes))
        self.assertIn("QUE EL ARCHIVO LOCAL NO CONOCE", texto)
        self.assertIn("msgbatch_huerfano", texto)

    def test_the_batch_we_already_know_is_not_reported_as_orphan(self):
        """Sin esto, el lote propio se denunciaría a sí mismo cada día."""
        recientes = [{
            "id": "msgbatch_x", "processing_status": "in_progress",
            "counts": {"processing": 2}, "created_at": None, "ended_at": None,
        }]
        texto = "\n".join(format_batch_poll(
            self._estado(), self._remoto("in_progress"), recientes
        ))
        self.assertNotIn("NO CONOCE", texto)

    def test_an_ended_unknown_batch_is_not_an_alarm(self):
        """Un lote terminado y ya recogido sigue existiendo 29 días.

        Denunciarlo daría una alarma falsa cada día, y una alarma que siempre
        suena deja de leerse. Solo se avisa de los que siguen procesándose.
        """
        recientes = [{
            "id": "msgbatch_viejo", "processing_status": "ended",
            "counts": {"succeeded": 2}, "created_at": None, "ended_at": None,
        }]
        texto = "\n".join(format_batch_poll(None, None, recientes))
        self.assertNotIn("NO CONOCE", texto)

    def test_no_batch_at_all_is_a_clean_report(self):
        texto = "\n".join(format_batch_poll(None, None, []))
        self.assertIn("No hay ningún lote en vuelo", texto)
        self.assertNotIn(">>>", texto)

    def test_an_unreachable_api_says_so_without_losing_the_batch(self):
        """El sondeo diario no puede convertir un fallo de red en una alarma."""
        texto = "\n".join(format_batch_poll(self._estado(), None, []))
        self.assertIn("No se pudo consultar", texto)
        self.assertIn("NO se pierde", texto)

    def test_listing_failures_are_swallowed_not_raised(self):
        """`list_recent_batches` se llama a diario y sin vigilancia."""
        class ClienteRoto:
            class messages:
                class batches:
                    @staticmethod
                    def list(limit=20):
                        raise RuntimeError("sin red")
        self.assertEqual(list_recent_batches(ClienteRoto()), [])


if __name__ == "__main__":
    unittest.main()
