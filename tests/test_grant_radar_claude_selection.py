# Pruebas de grant_radar/claude_selection.py y grant_radar/publishing.py con
# import estándar (sin runpy).
#
# Las dos son fronteras con dinero real: una decide cuánto se puede gastar en
# Haiku antes de empezar, la otra publica el JSON con un token de escritura.

import unittest

from grant_radar.claude_selection import (
    CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS,
    CLAUDE_MAX_ANALYSES_PER_RUN,
    CLAUDE_MAX_ESTIMATED_COST_USD,
    claude_safety_preflight,
)
from grant_radar.publishing import github_token_format_is_valid


class SafetyPreflightTests(unittest.TestCase):
    def test_a_normal_run_is_allowed(self):
        resultado = claude_safety_preflight(77)  # el volumen real del 19/08/2026
        self.assertTrue(resultado["allowed"])
        self.assertEqual(resultado["breaches"], [])
        self.assertAlmostEqual(resultado["estimated_upper_cost_usd"], 2.695, places=3)

    def test_the_cost_limit_bites_before_the_count_limit(self):
        """142 análisis pasan y 143 no, aunque el máximo nominal sean 200.

        Es la barrera efectiva documentada en AGENTS.md sección 11: con 0,035
        USD por análisis, 143 estiman 5,005 USD.
        """
        self.assertTrue(claude_safety_preflight(142)["allowed"])
        rechazado = claude_safety_preflight(143)
        self.assertFalse(rechazado["allowed"])
        self.assertEqual(rechazado["breaches"], ["estimated_cost_limit"])
        self.assertEqual(rechazado["effective_max_analyses"], 142)

    def test_a_huge_volume_breaches_both_limits(self):
        resultado = claude_safety_preflight(500)
        self.assertFalse(resultado["allowed"])
        self.assertEqual(
            sorted(resultado["breaches"]), ["candidate_limit", "estimated_cost_limit"]
        )

    def test_zero_and_negative_are_treated_as_nothing_to_analyse(self):
        for valor in (0, -5):
            with self.subTest(valor=valor):
                resultado = claude_safety_preflight(valor)
                self.assertTrue(resultado["allowed"])
                self.assertEqual(resultado["planned_analyses"], 0)
                self.assertEqual(resultado["estimated_upper_cost_usd"], 0)

    def test_the_published_limits_are_the_authorised_ones(self):
        # Si alguien los sube, que sea una decisión consciente y no un descuido.
        self.assertEqual(CLAUDE_MAX_ANALYSES_PER_RUN, 200)
        self.assertEqual(CLAUDE_MAX_ESTIMATED_COST_USD, 5.0)
        self.assertEqual(CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS, 0.035)


class GithubTokenFormatTests(unittest.TestCase):
    def test_accepts_the_two_supported_prefixes(self):
        for token in ("github_pat_" + "x" * 40, "ghp_" + "y" * 40):
            with self.subTest(token=token[:12]):
                self.assertTrue(github_token_format_is_valid(token))

    def test_rejects_the_placeholder_and_anything_too_short(self):
        for token in ("Placeholder", "", "ghp_corto", "github_pat_" + "x" * 5):
            with self.subTest(token=token):
                self.assertFalse(github_token_format_is_valid(token))

    def test_rejects_surrounding_whitespace(self):
        self.assertFalse(github_token_format_is_valid(" ghp_" + "y" * 40))

    def test_rejects_a_non_string(self):
        self.assertFalse(github_token_format_is_valid(None))

    def test_a_well_formed_token_is_not_a_valid_one(self):
        # Solo comprueba forma: la validez real se conoce al autenticar.
        self.assertTrue(github_token_format_is_valid("ghp_" + "0" * 40))


if __name__ == "__main__":
    unittest.main()
