# -*- coding: utf-8 -*-
# Pruebas de grant_radar/programme_annexes.py con import estándar.
#
# El módulo existe porque un topic de Horizon no dice quién puede solicitar:
# eso vive en los Anexos Generales del programa de trabajo (AGENTS.md 49.7).
# Lo que estas pruebas protegen es la propiedad que hace que esto no envejezca:
# el enlace sale del propio topic, así que cuando cambie el programa, cambia el
# documento que se lee, sin tocar código.
#
# Los fragmentos de texto son literales de la edición 2026-2027 del documento
# oficial, recortados: si la Comisión reescribe esos encabezados, estas pruebas
# fallan y es exactamente lo que debe pasar.

import unittest

from grant_radar.programme_annexes import (
    ELIGIBILITY_SECTIONS,
    annexes_url_from_conditions,
    clean_annexes_text,
    eligibility_sections,
    fetch_programme_eligibility,
)

CONDICIONES_HTML = (
    '<div>General conditions 1. Admissibility Conditions: described in '
    '<a href="https://ec.europa.eu/info/funding-tenders/opportunities/docs/'
    '2021-2027/horizon/wp-call/2026-2027/wp-15-general-annexes_horizon-2026-2027_en.pdf">'
    'Annex A</a> and <a href="https://ec.europa.eu/info/funding-tenders/'
    'opportunities/docs/2021-2027/horizon/guidance/programme-guide_horizon_en.pdf">'
    'Programme Guide</a>.</div>'
)

ANEXOS_TEXTO = (
    "Financial and operational capacity and exclusion. "
    "Entities eligible to participate Any legal entity, regardless of its place "
    "of establishment, including legal entities from non-associated third "
    "countries or international organisations is eligible to participate "
    "(whether it is eligible for funding or not), provided that the conditions "
    "laid down in the Horizon Europe Regulation have been met. "
    "Horizon Europe - Work programme 2026-2027 General Annexes Part 15 - Page 12 of 46 "
    "Entities eligible for funding To become a beneficiary, legal entities must "
    "be eligible for funding. To be eligible for funding, applicants must be "
    "established in one of the following countries: the Member States of the "
    "European Union, including Spain, Sweden. "
    "Consortium composition Unless otherwise provided for in the specific "
    "call/topic conditions, only legal entities forming a consortium are "
    "eligible to participate in actions provided that the consortium includes, "
    "as beneficiaries, three legal entities independent from each other and "
    "each established in a different country as follows: at least one "
    "independent legal entity established in a Member State; and at least two "
    "other independent legal entities, each established in different Member "
    "States or Associated Countries."
)


class Respuesta:
    """Lo mínimo que el módulo mira de una respuesta HTTP."""

    def __init__(self, status_code=200):
        self.status_code = status_code


class AnnexesUrlTests(unittest.TestCase):
    def test_the_link_comes_from_the_topic_itself(self):
        """La propiedad que evita otro catálogo escrito a mano."""
        url = annexes_url_from_conditions(CONDICIONES_HTML)
        self.assertIn("general-annexes", url)
        self.assertIn("2026-2027", url)

    def test_the_programme_guide_is_not_confused_with_the_annexes(self):
        """En el bloque real hay 32 enlaces; solo uno es el que buscamos."""
        self.assertNotIn(
            "programme-guide", annexes_url_from_conditions(CONDICIONES_HTML)
        )

    def test_no_link_is_an_empty_answer_not_a_guess(self):
        for html in ("", None, "<div>sin enlaces</div>", '<a href="otro.pdf">x</a>'):
            with self.subTest(html=str(html)[:20]):
                self.assertEqual(annexes_url_from_conditions(html), "")


class EligibilitySectionsTests(unittest.TestCase):
    def test_the_three_sections_that_decide_are_found(self):
        secciones = eligibility_sections(ANEXOS_TEXTO)
        self.assertEqual(
            sorted(secciones), sorted(clave for clave, _, _ in ELIGIBILITY_SECTIONS)
        )

    def test_the_consortium_minimum_survives_whole(self):
        """El dato por el que se hace todo esto: tres socios de tres países."""
        texto = eligibility_sections(ANEXOS_TEXTO)["consortium_composition"]
        self.assertIn("three legal entities independent from each other", texto)
        self.assertIn("at least one independent legal entity established in a Member State", texto)

    def test_spain_stays_inside_the_funding_countries(self):
        texto = eligibility_sections(ANEXOS_TEXTO)["entities_eligible_for_funding"]
        self.assertIn("Spain", texto)

    def test_the_page_header_does_not_break_the_sentences(self):
        limpio = clean_annexes_text(ANEXOS_TEXTO)
        self.assertNotIn("Page 12 of 46", limpio)
        self.assertNotIn("Part 15", limpio)

    def test_the_excerpts_stay_small_enough_to_be_worth_sending(self):
        """El documento entero son ~33.000 tokens; esto debe ser marginal."""
        total = sum(len(v) for v in eligibility_sections(ANEXOS_TEXTO).values())
        self.assertLess(total, 4_000)

    def test_a_document_with_another_structure_returns_what_it_finds(self):
        secciones = eligibility_sections("Un documento cualquiera sin secciones.")
        self.assertEqual(secciones, {})


class FetchProgrammeEligibilityTests(unittest.TestCase):
    def _fetch(self, html=CONDICIONES_HTML, status=200, texto=ANEXOS_TEXTO, cache=None):
        llamadas = []

        def http_get(url, **kwargs):
            llamadas.append(url)
            return Respuesta(status) if status else None

        def document_text(response, url, **kwargs):
            return texto, "pdf"

        resultado = fetch_programme_eligibility(
            html, http_get=http_get, document_text=document_text, cache=cache
        )
        return resultado, llamadas

    def test_a_topic_gets_its_programme_conditions(self):
        resultado, _ = self._fetch()
        self.assertIn("general-annexes", resultado["source_url"])
        self.assertIn("consortium_composition", resultado)

    def test_the_document_is_downloaded_once_per_edition(self):
        """19 topics de Horizon en una ejecución, una sola descarga."""
        cache = {}
        _, primeras = self._fetch(cache=cache)
        _, segundas = self._fetch(cache=cache)
        self.assertEqual(len(primeras), 1)
        self.assertEqual(len(segundas), 0, "la segunda vez debe salir de la caché")

    def test_an_unreachable_document_leaves_the_data_absent(self):
        """Nunca se supone: si no se puede leer, no hay condiciones."""
        resultado, _ = self._fetch(status=404)
        self.assertEqual(resultado, {})

    def test_a_topic_without_link_does_not_reach_the_network(self):
        resultado, llamadas = self._fetch(html="<div>sin enlaces</div>")
        self.assertEqual(resultado, {})
        self.assertEqual(llamadas, [])

    def test_a_failure_is_also_remembered_so_it_is_not_retried(self):
        cache = {}
        self._fetch(status=404, cache=cache)
        _, segundas = self._fetch(status=404, cache=cache)
        self.assertEqual(segundas, [])


if __name__ == "__main__":
    unittest.main()
