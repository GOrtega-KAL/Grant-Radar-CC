# -*- coding: utf-8 -*-
# Pruebas de grant_radar/coverage_watch.py con import estándar (sin runpy).
#
# Este módulo era el hueco de cobertura más incoherente del proyecto (punto 18
# del backlog de AGENTS.md): es la alarma que avisa cuando un programa
# recurrente conocido deja de aparecer —o sea, la red que vigila que no se
# pierda nada— y no tenía ni una prueba. Ninguna de las tres redes de seguridad
# habría notado que dejara de funcionar.
#
# Lo que más importa aquí es `active_not_captured`: la convocatoria está
# abierta en su landing oficial y el pipeline no la ha encontrado. Ese es el
# único estado que significa "hay una regresión real", frente a los demás, que
# solo significan "todavía no toca".

import unittest
from unittest import mock

from grant_radar.coverage_watch import (
    RECURRENT_COVERAGE_WATCH,
    build_recurrent_coverage_watch,
    probe_missing_recurrent_coverage,
)

# Configuración propia para no atar las pruebas al catálogo real, que cambia
# cuando cambian los programas vigilados.
VIGILANCIA_DE_PRUEBA = [
    {
        "key": "programa_ejemplo",
        "label": "Programa Ejemplo",
        "aliases": ["programa ejemplo", "PRGEJ-2026"],
        "url": "https://ejemplo.test/programa",
    },
]

VIGILANCIA_ANUAL = [
    {
        "key": "programa_anual",
        "label": "Programa Anual",
        "aliases": ["programa anual"],
        "url": "https://ejemplo.test/anual",
        "recurrence": "annual",
        "expected_start_month": 9,
    },
]


def _convocatoria(**campos):
    base = {
        "identifier": "",
        "title": "",
        "description": "",
        "url": "",
        "source": "BDNS",
    }
    base.update(campos)
    return base


class NavegadorFalso:
    def __init__(self, paginas=None):
        self.paginas = paginas or {}
        self.pedidas = []

    def html(self, url, **kwargs):
        self.pedidas.append(url)
        return self.paginas.get(url, "")


class BuildWatchTests(unittest.TestCase):
    def _construir(self, items, config=VIGILANCIA_DE_PRUEBA):
        with mock.patch(
            "grant_radar.coverage_watch.RECURRENT_COVERAGE_WATCH", config
        ):
            return build_recurrent_coverage_watch(items)

    def test_a_real_call_counts_as_captured(self):
        checks = self._construir([
            _convocatoria(title="Convocatoria 2026 del Programa Ejemplo"),
        ])
        self.assertEqual(checks[0]["status"], "active_captured")
        self.assertEqual(checks[0]["matches"], 1)
        self.assertEqual(checks[0]["sources"], ["BDNS"])

    def test_only_a_landing_is_not_a_captured_call(self):
        """Una landing de programa no prueba que haya convocatoria abierta."""
        checks = self._construir([
            _convocatoria(title="Programa Ejemplo", identity_only=True),
        ])
        self.assertEqual(checks[0]["status"], "landing_only")
        self.assertEqual(checks[0]["matches"], 1)

    def test_nothing_found_raises_the_alarm(self):
        checks = self._construir([_convocatoria(title="Otra cosa distinta")])
        self.assertEqual(checks[0]["status"], "not_observed")
        self.assertEqual(checks[0]["matches"], 0)

    def test_a_real_call_wins_over_a_landing_for_the_same_programme(self):
        checks = self._construir([
            _convocatoria(title="Programa Ejemplo", identity_only=True),
            _convocatoria(title="Convocatoria del Programa Ejemplo", source="BOE"),
        ])
        self.assertEqual(checks[0]["status"], "active_captured")
        self.assertEqual(checks[0]["matches"], 2)
        self.assertEqual(checks[0]["sources"], ["BDNS", "BOE"])

    def test_matching_ignores_case_and_accents(self):
        """`_fold_text` normaliza los dos lados, así que la tilde no separa.

        Importa porque las fuentes escriben el mismo programa de formas
        distintas —«Aragón» y «Aragon» conviven en los alias reales— y una
        alarma que fallara por una tilde avisaría de pérdidas inexistentes.
        """
        for titulo in (
            "PROGRAMA EJÉMPLO convocatoria",
            "programa ejemplo convocatoria",
            "Programa Ejemplo Convocatoria",
        ):
            with self.subTest(titulo=titulo):
                checks = self._construir([_convocatoria(title=titulo)])
                self.assertEqual(checks[0]["status"], "active_captured")

    def test_an_unrelated_programme_does_not_match(self):
        checks = self._construir([
            _convocatoria(title="Programa Distinto de otra cosa"),
        ])
        self.assertEqual(checks[0]["status"], "not_observed")

    def test_the_identifier_the_description_and_the_url_are_searched_too(self):
        for campo in ("identifier", "description", "url"):
            with self.subTest(campo=campo):
                checks = self._construir([
                    _convocatoria(**{campo: "PRGEJ-2026"}),
                ])
                self.assertEqual(checks[0]["status"], "active_captured", campo)

    def test_one_check_per_configured_programme(self):
        checks = self._construir([])
        self.assertEqual(len(checks), len(VIGILANCIA_DE_PRUEBA))
        self.assertEqual(checks[0]["key"], "programa_ejemplo")
        self.assertEqual(checks[0]["label"], "Programa Ejemplo")


class ProbeMissingCoverageTests(unittest.TestCase):
    def _sondear(self, navegador, items=(), config=VIGILANCIA_DE_PRUEBA):
        with mock.patch(
            "grant_radar.coverage_watch.RECURRENT_COVERAGE_WATCH", config
        ):
            return probe_missing_recurrent_coverage(navegador, list(items))

    def test_a_captured_programme_is_never_probed(self):
        """La sonda es un recurso de última hora, no una comprobación rutinaria."""
        navegador = NavegadorFalso()
        checks = self._sondear(navegador, [
            _convocatoria(title="Convocatoria del Programa Ejemplo"),
        ])
        self.assertEqual(navegador.pedidas, [])
        self.assertEqual(checks[0]["status"], "active_captured")

    def test_an_open_call_we_failed_to_find_is_the_real_alarm(self):
        navegador = NavegadorFalso({
            "https://ejemplo.test/programa":
                "<p>Plazo de presentación: del 01/01/2099 al 31/12/2099</p>",
        })
        checks = self._sondear(navegador)
        self.assertEqual(checks[0]["status"], "active_not_captured")
        self.assertEqual(checks[0]["deadline_date"], "2099-12-31")

    def test_a_closed_deadline_is_not_a_regression(self):
        navegador = NavegadorFalso({
            "https://ejemplo.test/programa":
                "<p>Plazo de presentación: del 01/01/2020 al 31/12/2020</p>",
        })
        self.assertEqual(self._sondear(navegador)[0]["status"], "closed_observed")

    def test_an_explicit_out_of_deadline_notice_is_enough(self):
        navegador = NavegadorFalso({
            "https://ejemplo.test/programa": "<p>Convocatoria fuera de plazo</p>",
        })
        self.assertEqual(self._sondear(navegador)[0]["status"], "closed_observed")

    def test_a_landing_without_dates_says_only_that(self):
        navegador = NavegadorFalso({
            "https://ejemplo.test/programa": "<p>Información sobre el programa</p>",
        })
        self.assertEqual(self._sondear(navegador)[0]["status"], "landing_observed")

    def test_an_unreachable_landing_leaves_the_alarm_untouched(self):
        """Si la sonda no llega, no se puede concluir nada: sigue sin observarse."""
        navegador = NavegadorFalso()
        checks = self._sondear(navegador)
        self.assertEqual(checks[0]["status"], "not_observed")
        self.assertEqual(navegador.pedidas, ["https://ejemplo.test/programa"])

    def test_an_annual_programme_before_its_month_is_only_pending(self):
        navegador = NavegadorFalso({
            "https://ejemplo.test/anual": "<p>Convocatoria fuera de plazo</p>",
        })
        with mock.patch("grant_radar.coverage_watch.datetime") as reloj:
            reloj.now.return_value.month = 7   # antes del mes 9 esperado
            checks = self._sondear(navegador, config=VIGILANCIA_ANUAL)
        self.assertEqual(checks[0]["status"], "seasonal_pending")

    def test_an_annual_programme_past_its_month_is_a_missing_republication(self):
        navegador = NavegadorFalso({
            "https://ejemplo.test/anual": "<p>Convocatoria fuera de plazo</p>",
        })
        with mock.patch("grant_radar.coverage_watch.datetime") as reloj:
            reloj.now.return_value.month = 11  # ya pasó el mes 9 esperado
            checks = self._sondear(navegador, config=VIGILANCIA_ANUAL)
        self.assertEqual(checks[0]["status"], "republication_not_observed")


class RealWatchListTests(unittest.TestCase):
    """El catálogo real es configuración: se comprueba su forma, no su contenido."""

    def test_every_entry_is_usable(self):
        self.assertTrue(RECURRENT_COVERAGE_WATCH)
        claves = [entry["key"] for entry in RECURRENT_COVERAGE_WATCH]
        self.assertEqual(len(claves), len(set(claves)), "hay claves repetidas")
        for entry in RECURRENT_COVERAGE_WATCH:
            with self.subTest(key=entry["key"]):
                self.assertTrue(entry["label"])
                self.assertTrue(entry["aliases"])
                self.assertTrue(all(entry["aliases"]))
                # Sin URL la sonda no puede distinguir una regresión de un cierre.
                self.assertTrue(entry.get("url", "").startswith("https://"))

    def test_an_annual_entry_declares_the_month_it_is_expected(self):
        for entry in RECURRENT_COVERAGE_WATCH:
            if entry.get("recurrence") == "annual":
                with self.subTest(key=entry["key"]):
                    mes = entry.get("expected_start_month")
                    self.assertIsInstance(mes, int)
                    self.assertIn(mes, range(1, 13))


if __name__ == "__main__":
    unittest.main()
