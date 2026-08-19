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
            dated_count=7, expected_date_coverage=0.9,
        )
        self.assertEqual(degraded["status"], "degraded")
        self.assertIn("date_coverage_below_expected", degraded["issues"])

        critical = assess_web_inventory_health(
            "CDTI",
            inventory_loaded=True, structure_ok=True, discovered_count=10,
            dated_count=2, expected_date_coverage=0.9,
        )
        self.assertEqual(critical["status"], "unhealthy")
        self.assertIn("date_coverage_critically_low", critical["issues"])

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
