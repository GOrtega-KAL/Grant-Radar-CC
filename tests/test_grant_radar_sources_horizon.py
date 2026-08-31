# -*- coding: utf-8 -*-
# Pruebas del conector Horizon Europe con import estándar.
#
# Se centran en lo que la SEDIA API entrega y el conector no estaba usando. El
# caso medido el 31/08/2026 (AGENTS.md 52.1): `budgetOverview` trae por topic
# cuánto se financia por proyecto, el presupuesto de la convocatoria, cuántos
# proyectos se esperan y si la presentación es en una o dos fases, y todo eso
# se reducía a la cadena «Presupuesto 2026». Resultado: las 19 convocatorias de
# Horizon llegaban a Haiku sin un solo dato económico y los declaraba ausentes.

import json
import unittest

from grant_radar.sources.horizon_europe import (
    _horizon_budget_facts,
    _horizon_budget_summary,
)

# Forma real de la respuesta, recortada: el mapa lista varias acciones porque un
# bloque presupuestario cubre topics hermanos.
BUDGET_OVERVIEW = json.dumps({
    "budgetYearsColumns": ["2026"],
    "budgetTopicActionMap": {
        "113409": [{
            "action": "HORIZON-CL5-2026-09-D4-03 - HORIZON-IA HORIZON Innovation Actions",
            "expectedGrants": 3,
            "minContribution": 5250000,
            "maxContribution": 5250000,
            "budgetYearMap": {"2026": "15750000"},
            "deadlineModel": "single-stage",
        }],
        "113410": [{
            "action": "HORIZON-CL5-2026-09-D4-08 - HORIZON-IA HORIZON Innovation Actions",
            "expectedGrants": 2,
            "minContribution": 9000000,
            "maxContribution": 9000000,
            "budgetYearMap": {"2026": "18000000"},
            "deadlineModel": "single-stage",
        }],
    },
})


class BudgetFactsTests(unittest.TestCase):
    def test_the_topic_takes_its_own_figures_not_its_neighbours(self):
        """El error que habría convertido esto en desinformación."""
        hechos = _horizon_budget_facts(BUDGET_OVERVIEW, "HORIZON-CL5-2026-09-D4-08")
        self.assertEqual(hechos["grant_max_eur"], 9000000)
        self.assertEqual(hechos["call_budget_eur"], 18000000)
        self.assertEqual(hechos["expected_grants"], 2)
        self.assertEqual(hechos["deadline_model"], "single-stage")

    def test_a_sibling_topic_gets_its_own(self):
        hechos = _horizon_budget_facts(BUDGET_OVERVIEW, "HORIZON-CL5-2026-09-D4-03")
        self.assertEqual(hechos["grant_max_eur"], 5250000)
        self.assertEqual(hechos["call_budget_eur"], 15750000)

    def test_a_topic_that_is_not_in_the_map_gets_nothing(self):
        """Mejor sin cifra que con la del vecino."""
        self.assertEqual(_horizon_budget_facts(BUDGET_OVERVIEW, "HORIZON-OTRO-2026-01"), {})

    def test_the_budget_of_several_years_is_added_up(self):
        overview = json.dumps({
            "budgetTopicActionMap": {"1": [{
                "action": "TOPIC-X - HORIZON-RIA",
                "budgetYearMap": {"2026": "10000000", "2027": "5000000"},
            }]},
        })
        self.assertEqual(_horizon_budget_facts(overview, "TOPIC-X")["call_budget_eur"], 15000000)

    def test_an_empty_or_broken_field_is_not_an_error(self):
        for bruto in ("", "{}", None, "esto no es json"):
            with self.subTest(bruto=str(bruto)[:12]):
                self.assertEqual(_horizon_budget_facts(bruto, "TOPIC-X"), {})


class BudgetSummaryTests(unittest.TestCase):
    def test_a_range_reads_as_a_range(self):
        resumen = _horizon_budget_summary(
            {"grant_min_eur": 15000000, "grant_max_eur": 25000000,
             "call_budget_eur": 125000000, "expected_grants": 8}, ["2026"]
        )
        self.assertIn("15.000.000-25.000.000 € por proyecto", resumen)
        self.assertIn("125.000.000 € en total", resumen)
        self.assertIn("8 proyectos previstos", resumen)

    def test_a_single_amount_is_not_written_as_a_range(self):
        resumen = _horizon_budget_summary(
            {"grant_min_eur": 9000000, "grant_max_eur": 9000000}, ["2026"]
        )
        self.assertIn("9.000.000 € por proyecto", resumen)
        self.assertNotIn("-", resumen)

    def test_a_single_project_is_written_in_singular(self):
        resumen = _horizon_budget_summary({"expected_grants": 1}, [])
        self.assertIn("1 proyecto previsto", resumen)
        self.assertNotIn("proyectos", resumen)

    def test_without_figures_it_falls_back_to_what_it_said_before(self):
        self.assertEqual(_horizon_budget_summary({}, ["2026", "2027"]), "Presupuesto 2026/2027")
        self.assertEqual(_horizon_budget_summary({}, []), "Ver convocatoria")


if __name__ == "__main__":
    unittest.main()
