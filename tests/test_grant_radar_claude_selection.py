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
    CLAUDE_OBSERVED_MEAN_USD_PER_ANALYSIS,
    CLAUDE_OBSERVED_P05_USD_PER_ANALYSIS,
    build_claude_analysis_selection,
    claude_safety_preflight,
    prioritize_claude_candidates,
)
from grant_radar.publishing import github_token_format_is_valid


class SafetyPreflightTests(unittest.TestCase):
    def test_a_normal_run_is_allowed(self):
        resultado = claude_safety_preflight(76)  # el volumen real del 20/08/2026
        self.assertTrue(resultado["allowed"])
        self.assertEqual(resultado["breaches"], [])
        self.assertAlmostEqual(resultado["estimated_upper_cost_usd"], 3.572, places=3)

    def test_the_cost_limit_bites_before_the_count_limit(self):
        """106 análisis pasan y 107 no, aunque el máximo nominal sean 200.

        Es la barrera efectiva tras la recalibración del 20/08/2026: con 0,047
        USD por análisis —el percentil 95 medido sobre 76 análisis reales—,
        107 estiman 5,029 USD. Antes eran 142, con un 0,035 que salía de una
        muestra de dos convocatorias y subestimaba la cola.
        """
        self.assertTrue(claude_safety_preflight(106)["allowed"])
        rechazado = claude_safety_preflight(107)
        self.assertFalse(rechazado["allowed"])
        self.assertEqual(rechazado["breaches"], ["estimated_cost_limit"])
        self.assertEqual(rechazado["effective_max_analyses"], 106)

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
        self.assertEqual(CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS, 0.047)

    def test_the_barrier_cost_is_above_the_observed_mean(self):
        # Una barrera calibrada con la media no protege de la cola: en los dos
        # corpus medidos el máximo superó la media con holgura (0,0550 el
        # 20/08 sobre 76 análisis; 0,0575 el 04/09 sobre 94).
        self.assertGreater(
            CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS,
            CLAUDE_OBSERVED_MEAN_USD_PER_ANALYSIS,
        )

    def test_the_calibration_is_the_one_measured_on_04_09_2026(self):
        """94 análisis reales con el prompt v17, a tarifa instantánea."""
        self.assertEqual(CLAUDE_OBSERVED_MEAN_USD_PER_ANALYSIS, 0.0314)
        self.assertEqual(CLAUDE_OBSERVED_P05_USD_PER_ANALYSIS, 0.0203)

    def test_the_forecast_matches_the_invoice_it_was_calibrated_against(self):
        """La prueba que da sentido a las otras dos.

        El 04/09 el panel anunció 1,18 USD por lotes para 92 convocatorias y la
        factura fue **1,4325**. Ese 22 % de desvío contribuyó a que se agotara
        el saldo a mitad de una ejecución. Con la calibración nueva la misma
        previsión da 1,4444: menos de un 1 % de error.

        Si alguien vuelve a tocar la media, esto falla y hay que justificarlo
        contra una factura, no contra una intuición.
        """
        prevision_por_lotes = 92 * CLAUDE_OBSERVED_MEAN_USD_PER_ANALYSIS / 2
        self.assertAlmostEqual(prevision_por_lotes, 1.4325, delta=0.05)

    def test_the_range_is_ordered_and_the_barrier_caps_it(self):
        self.assertLess(
            CLAUDE_OBSERVED_P05_USD_PER_ANALYSIS,
            CLAUDE_OBSERVED_MEAN_USD_PER_ANALYSIS,
        )
        self.assertLess(
            CLAUDE_OBSERVED_MEAN_USD_PER_ANALYSIS,
            CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS,
        )


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


class ClaudePriorityTests(unittest.TestCase):
    """En qué orden se gasta el presupuesto cuando no llega para todas.

    Antes del 02/09/2026, `--max-claude N` se quedaba con las N primeras en
    orden de recopilación, es decir, en el orden en que respondieron las
    fuentes. Eso convertía una ejecución parcial barata en un sorteo.
    """

    def candidata(self, identifier, decision="ambiguous", days=100, keywords=0, score=0):
        return {
            "identifier": identifier,
            "source": "BDNS",
            "title": f"Convocatoria {identifier}",
            "url": f"https://example.test/{identifier}",
            "deadline_days": days,
            "keywords_found": [f"kw{n}" for n in range(keywords)],
            "deterministic_prefilter": {"decision": decision, "score": score},
        }

    def orden(self, candidatas):
        return [c["identifier"] for c in prioritize_claude_candidates(candidatas)]

    def test_retain_goes_before_ambiguous(self):
        """`retain` superó una regla positiva; `ambiguous` solo sobrevivió."""
        self.assertEqual(
            self.orden([
                self.candidata("dudosa", decision="ambiguous", days=5),
                self.candidata("firme", decision="retain", days=90),
            ]),
            ["firme", "dudosa"],
        )

    def test_within_the_same_verdict_the_nearest_deadline_wins(self):
        self.assertEqual(
            self.orden([
                self.candidata("lejana", decision="retain", days=200),
                self.candidata("urgente", decision="retain", days=9),
                self.candidata("media", decision="retain", days=45),
            ]),
            ["urgente", "media", "lejana"],
        )

    def test_more_keywords_break_a_deadline_tie(self):
        self.assertEqual(
            self.orden([
                self.candidata("floja", decision="retain", days=30, keywords=1),
                self.candidata("rica", decision="retain", days=30, keywords=4),
            ]),
            ["rica", "floja"],
        )

    def test_the_prefilter_score_breaks_the_next_tie(self):
        self.assertEqual(
            self.orden([
                self.candidata("baja", decision="retain", days=30, keywords=2, score=3),
                self.candidata("alta", decision="retain", days=30, keywords=2, score=11),
            ]),
            ["alta", "baja"],
        )

    def test_a_call_without_a_deadline_does_not_jump_the_queue(self):
        """Sin fecha no se puede decir que urja: va al final, no al principio.

        Es el error fácil aquí — tratar el hueco como un 0 y colocar delante
        justamente lo que no se sabe cuándo cierra.
        """
        self.assertEqual(
            self.orden([
                self.candidata("sin-fecha", decision="retain", days=None),
                self.candidata("con-fecha", decision="retain", days=300),
            ]),
            ["con-fecha", "sin-fecha"],
        )

    def test_an_unknown_verdict_goes_last_instead_of_first(self):
        candidatas = [
            {"identifier": "sin-prefiltro", "source": "BDNS", "title": "T",
             "url": "https://example.test/s", "deadline_days": 1},
            self.candidata("normal", decision="ambiguous", days=300),
        ]
        self.assertEqual(
            [c["identifier"] for c in prioritize_claude_candidates(candidatas)],
            ["normal", "sin-prefiltro"],
        )

    def test_the_order_is_reproducible_between_runs(self):
        """El desempate por identidad estable.

        Sin él, dos candidatas idénticas en todo lo demás cambiarían de sitio
        según cómo las devolviera la fuente, y una prueba `--max-claude N`
        dejaría fuera una distinta cada vez. Es exactamente el fallo que hace
        irreproducible una medición.
        """
        candidatas = [self.candidata(str(n), decision="retain", days=30) for n in range(8)]
        primera = self.orden(candidatas)
        segunda = self.orden(list(reversed(candidatas)))
        self.assertEqual(primera, segunda)

    def test_nothing_is_added_or_lost_in_the_reordering(self):
        candidatas = [self.candidata(str(n), days=n) for n in range(12)]
        reordenadas = prioritize_claude_candidates(candidatas)
        self.assertEqual(len(reordenadas), len(candidatas))
        self.assertEqual(
            {id(c) for c in reordenadas}, {id(c) for c in candidatas},
            "reordenar no puede clonar ni descartar candidatas",
        )

    def test_the_selection_hands_over_candidates_already_ordered(self):
        """Truncar en el pipeline debe bastar: el orden llega hecho.

        Si la ordenación viviera en quien trunca, `--no-claude` enseñaría un
        orden y la ejecución de pago usaría otro, que es la peor variante:
        revisarlo gratis dejaría de significar nada.
        """
        seleccion = build_claude_analysis_selection(
            [
                self.candidata("tarde", decision="retain", days=250),
                self.candidata("pronto", decision="retain", days=4),
            ],
            {},
            None,
        )
        self.assertEqual(
            [c["identifier"] for c in seleccion["candidates"]], ["pronto", "tarde"]
        )


if __name__ == "__main__":
    unittest.main()
