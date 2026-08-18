# Pruebas del módulo grant_radar/parsing_helpers.py.
#
# A diferencia de tests/test_grant_radar.py, este archivo importa el módulo
# de forma normal (import estándar de Python) en vez de cargar todo
# `Grant-Radar-prueba.py` con runpy: es justo la ventaja de haber separado
# estas funciones a un paquete aparte (ver SUGERENCIAS.MD 3.2). Ejecutar
# solo estas pruebas es mucho más rápido que cargar el script completo.

import unittest

from grant_radar.parsing_helpers import (
    _absolute_url,
    _date_to_iso,
    _days_until,
    _extract_application_dates,
    _extract_date_range,
    _extract_spanish_application_dates,
    _fold_text,
    _levenshtein,
    _parse_cdti_calendar_date,
    _parse_flexible_date,
    _signed_days_until,
)


class DateParsingTests(unittest.TestCase):
    def test_date_to_iso_accepts_slash_and_dot_formats(self):
        self.assertEqual(_date_to_iso("30/09/2026"), "2026-09-30")
        self.assertEqual(_date_to_iso("30.09.2026"), "2026-09-30")
        self.assertEqual(_date_to_iso("no es una fecha"), "")

    def test_signed_days_until_can_be_negative_for_past_dates(self):
        self.assertLess(_signed_days_until("2000-01-01"), 0)
        self.assertIsNone(_signed_days_until(""))

    def test_days_until_never_returns_a_negative_number(self):
        self.assertEqual(_days_until("2000-01-01"), 0)
        self.assertEqual(_days_until(""), 90)  # respaldo documentado, no una fecha real

    def test_parse_flexible_date_understands_long_spanish_form(self):
        self.assertEqual(_parse_flexible_date("15 de septiembre de 2026"), "2026-09-15")
        self.assertEqual(_parse_flexible_date("2026-09-15"), "2026-09-15")

    def test_parse_cdti_calendar_date_estimates_month_only_dates(self):
        date_iso, estimated = _parse_cdti_calendar_date("septiembre 2026", 2026, month_end=True)
        self.assertEqual(date_iso, "2026-09-30")
        self.assertTrue(estimated)

    def test_extract_date_range_reads_a_dash_separated_range(self):
        open_date, close_date = _extract_date_range("Plazo: 01/09/2026 - 30/09/2026")
        self.assertEqual((open_date, close_date), ("2026-09-01", "2026-09-30"))

    def test_extract_spanish_application_dates_requires_the_request_phrase(self):
        text = (
            "El plazo de solicitudes comenzará el 1 de septiembre de 2026 y "
            "finalizará el 30 de septiembre de 2026."
        )
        self.assertEqual(
            _extract_spanish_application_dates(text),
            ("2026-09-01", "2026-09-30"),
        )

    def test_extract_application_dates_ignores_unrelated_dates(self):
        # "Fecha de inicio del proyecto" no es un plazo de solicitud: no debe
        # confundirse con la apertura de la convocatoria.
        text = "Fecha de inicio del proyecto: 01/01/2027. Sin plazo de solicitud indicado."
        self.assertEqual(_extract_application_dates(text), ("", ""))


class TextHelperTests(unittest.TestCase):
    def test_fold_text_removes_accents_and_lowercases(self):
        self.assertEqual(_fold_text("Descarbonización Térmica"), "descarbonizacion termica")

    def test_absolute_url_joins_relative_paths(self):
        self.assertEqual(
            _absolute_url("https://www.cdti.es", "/ayudas/neotec"),
            "https://www.cdti.es/ayudas/neotec",
        )
        self.assertEqual(
            _absolute_url("https://www.cdti.es", "https://otro.test/x"),
            "https://otro.test/x",
        )

    def test_levenshtein_distance_between_close_variants(self):
        self.assertEqual(_levenshtein("CDTI", "CDTI"), 0)
        self.assertEqual(_levenshtein("ITAINNOVA", "ITAINOVA"), 1)


if __name__ == "__main__":
    unittest.main()
