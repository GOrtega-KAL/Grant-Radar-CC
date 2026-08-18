# Pruebas del módulo grant_radar/tech_taxonomy.py.
#
# Import estándar (sin runpy). No repite la cobertura de
# tests/fixtures/common_scope_filter_cases.json (que sigue viviendo en
# test_grant_radar.py y prueba el pipeline completo); aquí se prueban las
# funciones de esta taxonomía de forma aislada.

import unittest

from grant_radar.tech_taxonomy import (
    KEYWORDS,
    TECH_TAGS,
    _compat_tags_for,
    _contextual_term_present,
    _term_present,
    detect_tech_tags,
    has_technology_discovery_signal,
    is_relevant,
    keyword_match,
)


class TaxonomyDataTests(unittest.TestCase):
    def test_tech_tags_combines_strong_and_contextual_vocabulary(self):
        self.assertIn("waste_heat", TECH_TAGS)
        self.assertIn("calor residual", TECH_TAGS["waste_heat"])

    def test_keywords_is_derived_from_all_categories(self):
        self.assertIn("calor residual", KEYWORDS)
        self.assertIn("digital twin", KEYWORDS)


class MatchingTests(unittest.TestCase):
    def test_term_present_rejects_acronym_substring_false_positives(self):
        self.assertTrue(_term_present("un sistema RTO instalado", "rto"))
        self.assertFalse(_term_present("demonstration project", "rto"))

    def test_detect_tech_tags_finds_strong_terms_without_context(self):
        self.assertIn("waste_heat", detect_tech_tags("Recuperación de calor residual industrial"))

    def test_contextual_term_requires_nearby_industrial_signal(self):
        near_industrial = "digital twin para procesos industriales y hornos"
        far_from_industrial = "digital twin para videojuegos y ocio"
        self.assertTrue(_contextual_term_present(near_industrial, "digital twin"))
        self.assertFalse(_contextual_term_present(far_from_industrial, "digital twin"))

    def test_is_relevant_requires_industrial_context_for_energy_efficiency_alone(self):
        self.assertFalse(is_relevant("Eficiencia energética en viviendas residenciales"))
        self.assertTrue(is_relevant("Eficiencia energética en procesos industriales de fabricación"))

    def test_is_relevant_accepts_specific_technical_families_alone(self):
        self.assertTrue(is_relevant("Recuperación de calor residual en horno industrial"))

    def test_keyword_match_returns_only_matched_keywords(self):
        matches = keyword_match("Proyecto de recuperador de calor residual")
        self.assertIn("recuperador", matches)
        self.assertNotIn("digital twin", matches)

    def test_has_technology_discovery_signal_includes_discovery_only_terms(self):
        self.assertTrue(has_technology_discovery_signal(
            "Heat exchanger for industrial processes pilot"
        ))

    def test_compat_tags_translate_to_legacy_short_codes(self):
        self.assertEqual(_compat_tags_for(["hydrogen_combustion"]), ["desc", "h2"])
        self.assertEqual(_compat_tags_for(["unknown_tag"]), [])


if __name__ == "__main__":
    unittest.main()
