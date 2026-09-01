# Pruebas de grant_radar/source_health.py con import estándar (sin runpy).

import unittest

from grant_radar.runtime_state import RUN_DIAGNOSTICS
from grant_radar.source_health import assess_web_inventory_health


class WebInventoryHealthTests(unittest.TestCase):
    def setUp(self):
        RUN_DIAGNOSTICS.clear()

    tearDown = setUp

    def test_a_complete_inventory_is_healthy_and_is_recorded(self):
        health = assess_web_inventory_health(
            "CDTI",
            inventory_loaded=True,
            structure_ok=True,
            discovered_count=40,
            detail_attempted=40,
            detail_loaded=40,
            dated_count=40,
            expected_min_inventory=10,
            expected_date_coverage=0.8,
        )
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["issues"], [])
        self.assertIs(RUN_DIAGNOSTICS["web_source_health"]["CDTI"], health)

    def test_an_unreachable_inventory_is_unhealthy(self):
        health = assess_web_inventory_health(
            "IDAE", inventory_loaded=False, structure_ok=False, discovered_count=0,
        )
        self.assertEqual(health["status"], "unhealthy")
        self.assertIn("inventory_unreachable", health["issues"])

    def test_broken_structure_is_reported_when_the_page_did_load(self):
        health = assess_web_inventory_health(
            "BOE / MITECO",
            inventory_loaded=True, structure_ok=False, discovered_count=5,
        )
        self.assertEqual(health["status"], "unhealthy")
        self.assertIn("expected_structure_missing", health["issues"])

    def test_volume_below_the_expected_minimum_is_critical(self):
        health = assess_web_inventory_health(
            "ECCP",
            inventory_loaded=True, structure_ok=True,
            discovered_count=3, expected_min_inventory=10,
        )
        self.assertEqual(health["status"], "unhealthy")
        self.assertIn("inventory_below_expected_minimum", health["issues"])

    def test_a_detail_load_rate_between_50_and_90_pct_only_degrades(self):
        health = assess_web_inventory_health(
            "CDTI",
            inventory_loaded=True, structure_ok=True, discovered_count=10,
            detail_attempted=10, detail_loaded=7,
        )
        self.assertEqual(health["status"], "degraded")
        self.assertIn("detail_load_rate_below_90pct", health["issues"])

    def test_a_detail_load_rate_below_50_pct_is_critical(self):
        health = assess_web_inventory_health(
            "CDTI",
            inventory_loaded=True, structure_ok=True, discovered_count=10,
            detail_attempted=10, detail_loaded=4,
        )
        self.assertEqual(health["status"], "unhealthy")
        self.assertIn("detail_load_rate_below_50pct", health["issues"])

    def test_date_coverage_below_expectation_degrades_and_far_below_is_critical(self):
        degraded = assess_web_inventory_health(
            "CDTI",
            inventory_loaded=True, structure_ok=True, discovered_count=10,
            detail_attempted=10, detail_loaded=10,
            dated_count=7, expected_date_coverage=0.9,
        )
        self.assertEqual(degraded["status"], "degraded")
        self.assertIn("date_coverage_below_expected", degraded["issues"])

        critical = assess_web_inventory_health(
            "CDTI",
            inventory_loaded=True, structure_ok=True, discovered_count=10,
            detail_attempted=10, detail_loaded=10,
            dated_count=2, expected_date_coverage=0.9,
        )
        self.assertEqual(critical["status"], "unhealthy")
        self.assertIn("date_coverage_critically_low", critical["issues"])

    def test_date_coverage_is_measured_over_loaded_pages_not_the_inventory(self):
        """El denominador correcto (AGENTS.md 45.1).

        Una fecha solo puede encontrarse en una ficha que se haya cargado. Con
        el denominador antiguo —el inventario completo— una fuente que abre 8
        de 168 fichas y les saca fecha a 3 daba 1,8 % y pareceria rota, asi que
        hubo que apagarle el umbral. Sobre las cargadas da 37,5 %, que es lo
        que de verdad describe a esa fuente.
        """
        health = assess_web_inventory_health(
            "BOE / MITECO",
            inventory_loaded=True, structure_ok=True, discovered_count=168,
            detail_attempted=8, detail_loaded=8, dated_count=3,
        )
        self.assertEqual(health["date_coverage"], 0.375)

    def test_selection_rate_catches_a_source_that_stops_opening_records(self):
        """Si una fuente deja de abrir fichas, el embudo se hunde en silencio."""
        sano = assess_web_inventory_health(
            "IDAE",
            inventory_loaded=True, structure_ok=True, discovered_count=100,
            detail_attempted=70, detail_loaded=70, expected_selection_rate=0.5,
        )
        self.assertEqual(sano["status"], "healthy")
        self.assertEqual(sano["selection_rate"], 0.7)

        hundida = assess_web_inventory_health(
            "IDAE",
            inventory_loaded=True, structure_ok=True, discovered_count=100,
            detail_attempted=10, detail_loaded=10, expected_selection_rate=0.5,
        )
        self.assertEqual(hundida["status"], "unhealthy")
        self.assertIn("selection_rate_critically_low", hundida["issues"])

    def test_publication_rate_catches_a_source_that_stops_producing(self):
        """El caso del IDAE: 71 fichas cargadas y una sola convocatoria."""
        health = assess_web_inventory_health(
            "IDAE",
            inventory_loaded=True, structure_ok=True, discovered_count=97,
            detail_attempted=71, detail_loaded=71, published_count=1,
            expected_publication_rate=0.05,
        )
        self.assertIn("publication_rate_critically_low", health["issues"])
        self.assertEqual(health["status"], "unhealthy")

    def test_rates_are_none_when_there_is_nothing_to_divide_by(self):
        health = assess_web_inventory_health(
            "IDAE CATÁLOGO",
            inventory_loaded=True, structure_ok=True, discovered_count=0,
        )
        self.assertIsNone(health["selection_rate"])
        self.assertIsNone(health["publication_rate"])
        self.assertEqual(health["date_coverage"], 0.0)

    def test_an_unset_expectation_never_raises_an_issue(self):
        """Un umbral en 0 sigue significando «no lo compruebes»."""
        health = assess_web_inventory_health(
            "BOE / MITECO",
            inventory_loaded=True, structure_ok=True, discovered_count=168,
            detail_attempted=8, detail_loaded=8, dated_count=0, published_count=0,
        )
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["issues"], [])

    def test_a_stale_or_missing_source_version_degrades(self):
        stale = assess_web_inventory_health(
            "CDTI",
            inventory_loaded=True, structure_ok=True, discovered_count=10,
            source_version="2020-01-01", max_version_age_days=62,
        )
        self.assertEqual(stale["status"], "degraded")
        self.assertIn("source_version_stale", stale["issues"])

        missing = assess_web_inventory_health(
            "CDTI",
            inventory_loaded=True, structure_ok=True, discovered_count=10,
            source_version="", max_version_age_days=62,
        )
        self.assertIn("source_version_missing", missing["issues"])

    def test_each_source_keeps_its_own_entry_in_the_diagnostics(self):
        assess_web_inventory_health(
            "CDTI", inventory_loaded=True, structure_ok=True, discovered_count=10,
        )
        assess_web_inventory_health(
            "IDAE", inventory_loaded=True, structure_ok=True, discovered_count=10,
        )
        self.assertEqual(
            sorted(RUN_DIAGNOSTICS["web_source_health"]), ["CDTI", "IDAE"]
        )


if __name__ == "__main__":
    unittest.main()
