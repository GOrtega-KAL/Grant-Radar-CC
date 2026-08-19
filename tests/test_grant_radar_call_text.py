# Pruebas de grant_radar/call_text.py con import estándar (sin runpy).

import unittest

from bs4 import BeautifulSoup

from grant_radar.call_text import (
    CALL_LINK_TERMS,
    FUNDING_CONTEXT_TERMS,
    _extract_deadline_from_text,
    _extract_funding_budget,
    _external_links,
    _funding_mechanism,
    _official_call_identifier,
)


class FundingMechanismTests(unittest.TestCase):
    def test_cascade_funding_wins_over_a_generic_grant_mention(self):
        self.assertEqual(
            _funding_mechanism("Open call for SMEs: cascade funding grant"), "cascade"
        )

    def test_financial_support_to_third_parties_is_cascade(self):
        self.assertEqual(
            _funding_mechanism("Financial support to third parties (FSTP)"), "cascade"
        )

    def test_a_plain_call_is_direct(self):
        self.assertEqual(
            _funding_mechanism("Convocatoria de ayuda a la inversión industrial"),
            "direct",
        )

    def test_text_without_funding_vocabulary_is_unknown(self):
        self.assertEqual(_funding_mechanism("Jornada técnica sobre hornos"), "unknown")


class OfficialCallIdentifierTests(unittest.TestCase):
    def test_recognises_a_horizon_topic_identifier(self):
        self.assertEqual(
            _official_call_identifier(
                "Topic HORIZON-CL5-2026-09-D4-08: heat upgrade"
            ),
            "HORIZON-CL5-2026-09-D4-08",
        )

    def test_recognises_an_eccp_competitive_call_path(self):
        self.assertEqual(
            _official_call_identifier(
                "https://www.clustercollaboration.eu/competitive-calls-cs/123456"
            ),
            "123456",
        )

    def test_recognises_a_eurostars_call_number(self):
        self.assertEqual(
            _official_call_identifier("Eurostars 3 Call 7 is now open"),
            "EUROSTARS-CALL-7",
        )

    def test_returns_empty_when_there_is_no_identifier(self):
        self.assertEqual(_official_call_identifier("Ayudas del Gobierno de Aragón"), "")


class DeadlineFromTextTests(unittest.TestCase):
    def test_reads_an_english_deadline(self):
        self.assertEqual(
            _extract_deadline_from_text("Deadline: 15 September 2026"), "2026-09-15"
        )

    def test_reads_a_spanish_deadline(self):
        self.assertEqual(
            _extract_deadline_from_text("Fecha límite: 30/11/2026"), "2026-11-30"
        )

    def test_reads_an_until_clause(self):
        self.assertEqual(
            _extract_deadline_from_text("Applications open until 01/03/2027"),
            "2027-03-01",
        )

    def test_returns_empty_when_there_is_no_parseable_date(self):
        self.assertEqual(_extract_deadline_from_text("Deadline: to be announced"), "")


class ExternalLinksTests(unittest.TestCase):
    def test_keeps_only_https_links_to_other_hosts_without_duplicates(self):
        html = """
        <a href="/interna">interna relativa</a>
        <a href="https://www.clustercollaboration.eu/otra">mismo host</a>
        <a href="http://proyecto.test/inseguro">http</a>
        <a href="https://proyecto.test/a">externa</a>
        <a href="https://proyecto.test/a">externa repetida</a>
        <a href="https://otro.test/b">otra externa</a>
        """
        links = _external_links(
            BeautifulSoup(html, "html.parser"),
            "https://www.clustercollaboration.eu/content/x",
        )
        self.assertEqual(links, ["https://proyecto.test/a", "https://otro.test/b"])


class FundingBudgetTests(unittest.TestCase):
    def test_reads_an_explicit_total_budget(self):
        self.assertEqual(
            _extract_funding_budget("Total available budget: EUR 2 500 000 for the call"),
            "EUR 2 500 000 total",
        )

    def test_reads_a_spanish_budget(self):
        self.assertEqual(
            _extract_funding_budget("Presupuesto total: 2.500.000 EUR"),
            "2.500.000 EUR total",
        )

    def test_reads_an_amount_in_millions_when_the_currency_follows_directly(self):
        self.assertEqual(
            _extract_funding_budget("Presupuesto: 2,5 millones EUR"),
            "2,5 millones EUR total",
        )

    def test_known_gap_millones_de_euros_is_not_recognised(self):
        # Limitación real del patrón, anterior a la extracción del módulo: la
        # preposición intermedia ("millones DE euros") rompe la coincidencia y
        # el importe se pierde. Se fija aquí para que quede visible; corregirlo
        # sería un cambio de comportamiento, no parte de esta extracción.
        self.assertEqual(
            _extract_funding_budget("Presupuesto: 2,5 millones de euros"),
            "Ver convocatoria",
        )

    def test_falls_back_without_inventing_an_amount(self):
        self.assertEqual(
            _extract_funding_budget("La dotación se publicará más adelante"),
            "Ver convocatoria",
        )


class SharedVocabularyTests(unittest.TestCase):
    def test_the_two_shared_term_tuples_are_non_empty_and_lowercase(self):
        for name, terms in (
            ("FUNDING_CONTEXT_TERMS", FUNDING_CONTEXT_TERMS),
            ("CALL_LINK_TERMS", CALL_LINK_TERMS),
        ):
            with self.subTest(name=name):
                self.assertTrue(terms)
                self.assertEqual(len(set(terms)), len(terms))
                self.assertTrue(all(term == term.casefold() for term in terms))


if __name__ == "__main__":
    unittest.main()
