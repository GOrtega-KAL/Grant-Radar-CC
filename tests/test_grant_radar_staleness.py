# -*- coding: utf-8 -*-
# Pruebas de grant_radar/staleness.py con import estándar (sin runpy).
#
# El informe existe para responder a una sola pregunta —¿merece la pena pagar
# una ejecución con Claude hoy?— y su respuesta puede costar dinero, así que lo
# que más importa aquí es que no exagere ni el desfase ni la calma.
#
# El error que estas pruebas fijan apareció en la primera versión: contaba como
# pendientes una previsión ANTERIOR a la última publicación, de modo que
# declaraba ocho convocatorias esperando análisis justo después de haberlas
# analizado y publicado.

import unittest
from datetime import date

from grant_radar.staleness import (
    COLLECTION_STATE_SCHEMA_VERSION,
    build_collection_state,
    build_staleness_report,
    format_staleness_report,
    summarize_staleness,
)

HOY = date(2026, 8, 21)


def _recopilacion(momento, candidatas, pendientes, coste=0.2):
    return {
        "started_at": momento,
        "status": "completed_no_claude",
        "diagnostics": {"claude_forecast": {
            "candidates": candidatas,
            "new_or_changed": pendientes,
            "estimated_cost_central_usd": coste,
        }},
    }


def _publicacion(momento):
    return {"started_at": momento, "status": "completed", "diagnostics": {}}


class StalenessReportTests(unittest.TestCase):
    def test_a_forecast_before_the_publication_is_not_pending_work(self):
        """El fallo original: esa previsión ya la consumió la publicación."""
        informe = build_staleness_report([
            _recopilacion("2026-08-21T05:40:00", 77, 8),
            _publicacion("2026-08-21T11:51:00"),
        ], today=HOY)
        self.assertIsNone(informe["pending"])
        self.assertFalse(informe["measured_since_publication"])
        self.assertEqual(informe["last_publication"], "2026-08-21")

    def test_a_forecast_after_the_publication_does_count(self):
        informe = build_staleness_report([
            _publicacion("2026-08-21T11:51:00"),
            _recopilacion("2026-08-22T05:40:00", 79, 3, coste=0.08),
        ], today=date(2026, 8, 22))
        self.assertEqual(informe["pending"], 3)
        self.assertEqual(informe["candidates"], 79)
        self.assertEqual(informe["estimated_cost_usd"], 0.08)
        self.assertTrue(informe["measured_since_publication"])

    def test_the_most_recent_measurement_after_publication_wins(self):
        informe = build_staleness_report([
            _publicacion("2026-08-18T09:00:00"),
            _recopilacion("2026-08-19T05:40:00", 77, 4),
            _recopilacion("2026-08-20T05:40:00", 78, 9),
        ], today=HOY)
        self.assertEqual(informe["pending"], 9)
        self.assertEqual(informe["days_since_publication"], 3)

    def test_days_are_counted_from_the_publication_not_the_last_check(self):
        """Recopilar a diario no rejuvenece lo publicado."""
        informe = build_staleness_report([
            _publicacion("2026-08-14T09:00:00"),
            _recopilacion("2026-08-20T05:40:00", 77, 12),
            _recopilacion("2026-08-21T05:40:00", 77, 12),
        ], today=HOY)
        self.assertEqual(informe["days_since_publication"], 7)

    def test_with_no_publication_at_all_the_age_is_unknown(self):
        informe = build_staleness_report([
            _recopilacion("2026-08-21T05:40:00", 77, 8),
        ], today=HOY)
        self.assertIsNone(informe["days_since_publication"])
        self.assertEqual(informe["last_publication"], "")
        self.assertEqual(informe["pending"], 8)

    def test_an_empty_or_broken_history_does_not_raise(self):
        for entrada in ([], None, [None, "basura", {}], [{"status": "completed"}]):
            with self.subTest(entrada=str(entrada)[:30]):
                informe = build_staleness_report(entrada, today=HOY)
                self.assertIsNone(informe["pending"])

    def test_the_history_keeps_the_last_fourteen_measurements(self):
        muchas = [
            _recopilacion(f"2026-07-{dia:02d}T05:00:00", 70, dia)
            for dia in range(1, 26)
        ]
        informe = build_staleness_report(muchas, today=HOY)
        self.assertEqual(len(informe["history"]), 14)
        self.assertEqual(informe["history"][-1]["pending"], 25)


class StalenessRenderingTests(unittest.TestCase):
    def test_nothing_pending_reads_as_up_to_date(self):
        informe = build_staleness_report([
            _publicacion("2026-08-20T09:00:00"),
            _recopilacion("2026-08-21T05:40:00", 77, 0, coste=0.0),
        ], today=HOY)
        texto = format_staleness_report(informe)
        self.assertIn("Nada pendiente", texto)
        self.assertIn("0 convocatorias pendientes", summarize_staleness(informe))

    def test_pending_work_says_it_needs_authorisation(self):
        informe = build_staleness_report([
            _publicacion("2026-08-18T09:00:00"),
            _recopilacion("2026-08-21T05:40:00", 77, 8),
        ], today=HOY)
        texto = format_staleness_report(informe)
        self.assertIn("Requiere autorización expresa", texto)
        resumen = summarize_staleness(informe)
        self.assertIn("8 convocatorias pendientes", resumen)
        self.assertIn("3 días desde la última publicación", resumen)

    def test_one_pending_call_is_written_in_singular(self):
        informe = build_staleness_report([
            _publicacion("2026-08-20T09:00:00"),
            _recopilacion("2026-08-21T05:40:00", 77, 1),
        ], today=HOY)
        resumen = summarize_staleness(informe)
        self.assertIn("1 convocatoria pendiente", resumen)
        self.assertNotIn("convocatorias", resumen)
        self.assertIn("1 día desde", resumen)

    def test_a_report_with_no_measurement_asks_for_a_collection(self):
        informe = build_staleness_report([_publicacion("2026-08-21T11:00:00")], today=HOY)
        texto = format_staleness_report(informe)
        self.assertIn("Sin recopilación --no-claude posterior", texto)
        self.assertIn("sin datos suficientes", summarize_staleness(informe))

    def test_the_rendered_report_never_raises_on_partial_data(self):
        informe = build_staleness_report([
            {"started_at": "2026-08-21T05:00:00", "status": "completed_no_claude",
             "diagnostics": {"claude_forecast": {}}},
            {"started_at": "2026-08-21T06:00:00", "status": "completed_no_claude",
             "diagnostics": {"claude_forecast": {"new_or_changed": 2}}},
        ], today=HOY)
        self.assertIsInstance(format_staleness_report(informe), str)
        self.assertIsInstance(summarize_staleness(informe), str)


class CollectionStateTests(unittest.TestCase):
    """El archivo que publica la recopilación diaria para el panel.

    Cierra el circuito acordado el 21/08/2026: una recopilación sin coste al
    día, y la llamada de pago decidida a mano cuando el desfase la justifique.
    Hasta el 31/08 ese número solo salía por consola.
    """

    def informe(self, **overrides):
        base = {
            "generated_on": "2026-08-31",
            "pending": 80,
            "estimated_cost_usd": 2.048,
            "last_publication": "2026-08-21",
            "days_since_publication": 10,
        }
        base.update(overrides)
        return base

    def test_the_state_carries_what_the_banner_needs(self):
        estado = build_collection_state(
            self.informe(), detected=915, active=80, generated_at="2026-08-31T07:00:00+00:00"
        )
        self.assertEqual(estado["schema_version"], COLLECTION_STATE_SCHEMA_VERSION)
        self.assertEqual(estado["pending_analyses"], 80)
        self.assertEqual(estado["estimated_cost_usd"], 2.048)
        self.assertEqual(estado["days_since_publication"], 10)
        self.assertEqual(estado["detected"], 915)
        self.assertEqual(estado["active"], 80)
        self.assertEqual(estado["collected_on"], "2026-08-31")

    def test_it_does_not_repeat_the_published_product(self):
        """Describe la recopilación, no las convocatorias: si crece, se acopla.

        El tope subió de 9 a 10 el 02/09/2026, por un solo campo:
        `new_since_publication`. La primera versión del cambio metía además
        `expiring_soon`, `expired` y una muestra con el título y la fecha de
        tres convocatorias publicadas — y esta prueba la paró. Tenía razón:
        eso es el producto, el panel ya lo tiene cargado y puede derivarlo.
        Subir el número sin más habría convertido el guardián en un trámite.

        Y de 10 a 11 el 03/09/2026, por `batch`, que describe el estado de un
        lote diferido en curso: en qué fase va, cuántas convocatorias lleva y
        cuántas esperan fuera. Son recuentos y marcas de tiempo, ningún título,
        y por eso la comprobación baja ahora también dentro de ese diccionario:
        un campo anidado puede colar el producto igual que uno de primer nivel.
        """
        estado = build_collection_state(
            self.informe(), detected=1, active=1, generated_at="2026-08-31T07:00:00+00:00",
            batch={"state": "phase1_running", "phase": 1, "of_phases": 2,
                   "items": 83, "submitted_at": "2026-09-03T09:00:00+00:00",
                   "age_hours": 0.5, "waiting_outside": 4},
        )
        self.assertNotIn("convocatorias", estado)
        self.assertLessEqual(len(estado), 11)

        def sin_listas(valores, prefijo=""):
            for clave, valor in valores.items():
                ruta = f"{prefijo}{clave}"
                self.assertNotIsInstance(valor, list, f"{ruta} repite el producto")
                if isinstance(valor, dict):
                    sin_listas(valor, f"{ruta}.")

        sin_listas(estado)
        # Y el bloque del lote no puede traer texto largo: eso sería una ficha.
        for clave, valor in (estado["batch"] or {}).items():
            if isinstance(valor, str):
                self.assertLess(len(valor), 60, f"batch.{clave} parece contenido")

    def test_nothing_pending_is_a_valid_state_not_an_absence(self):
        estado = build_collection_state(
            self.informe(pending=0, estimated_cost_usd=0.0),
            detected=915, active=80, generated_at="2026-08-31T07:00:00+00:00",
        )
        self.assertEqual(estado["pending_analyses"], 0)

    def test_an_audit_without_measurements_does_not_invent_a_number(self):
        estado = build_collection_state(
            self.informe(pending=None, estimated_cost_usd=None, days_since_publication=None),
            detected=915, active=80, generated_at="2026-08-31T07:00:00+00:00",
        )
        self.assertIsNone(estado["pending_analyses"])
        self.assertIsNone(estado["estimated_cost_usd"])


if __name__ == "__main__":
    unittest.main()
