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


if __name__ == "__main__":
    unittest.main()
