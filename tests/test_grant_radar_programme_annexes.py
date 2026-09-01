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

from datetime import date

from grant_radar.cache import source_hash
from grant_radar.programme_annexes import (
    ELIGIBILITY_SECTIONS,
    annexes_url_from_conditions,
    clean_annexes_text,
    eligibility_sections,
    fetch_programme_eligibility,
    sections_fingerprint,
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
    "States or Associated Countries. "
    # Sección G del documento real, página 32. Texto literal de la edición
    # 2026-2027: es el dato que dice cuánto del gasto cubre la ayuda.
    "Horizon Europe - Work programme 2026-2027 General Annexes Part 15 - Page 32 of 46 "
    "Form of grant, funding rate and maximum grant amount The grant parameters "
    "(maximum grant amount, funding rate, total eligible costs, etc.) will be "
    "fixed in the grant agreement. The costs will be reimbursed at the funding "
    "rate fixed in the specific call/topic conditions and in the grant "
    "agreement. The maximum Horizon Europe funding rates are as follows: "
    "Research and innovation action: 100% "
    "Innovation action: 70% (except for non-profit legal entities, where a "
    "rate of up to 100% applies) "
    "Coordination and support action: 100% "
    "Programme co-fund action: between 30% and 70% "
    "Training and mobility action: 100% "
    "Pre-commercial procurement action: 100% "
    "Public procurement of innovative solutions action: 50%"
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

    def test_the_funding_rates_survive_whole(self):
        """
        El dato que decide si una convocatoria interesa de verdad.

        Vive en la página 32 del mismo documento, más allá del corte de
        caracteres por defecto de la capa documental, y por eso no se leía
        hasta el 01/09/2026 (AGENTS.md 59). Con `types_of_action`, que la API
        ya entrega, el modelo puede cruzar el tipo de acción con su tasa.
        """
        texto = eligibility_sections(ANEXOS_TEXTO)["funding_rates"]
        # Las dos que importan a una PYME con ánimo de lucro: 100 % en una RIA
        # y 70 % en una IA. En un proyecto de 3 M€ son 900.000 € de diferencia.
        self.assertIn("Research and innovation action: 100%", texto)
        self.assertIn("Innovation action: 70%", texto)
        # La excepción de las entidades sin ánimo de lucro no debe perderse:
        # sin ella, un 70 % parecería aplicable a cualquiera.
        self.assertIn("non-profit legal entities", texto)
        # Y la lista debe llegar entera hasta la última tasa.
        self.assertIn("Public procurement of innovative solutions action: 50%", texto)

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
        """
        El documento entero son ~31.000 tokens; esto debe seguir siendo marginal.

        El tope subió de 4.000 a 5.000 caracteres el 01/09/2026 al añadir la
        sección de tasas de financiación (AGENTS.md 59). Son unos 175 tokens
        más por convocatoria de Horizon: con 37 topics, del orden de 6.500
        tokens de entrada por ejecución completa, menos de un céntimo. La
        guardia sigue existiendo porque el riesgo real no es este añadido sino
        que alguien suba un límite de sección sin mirar lo que arrastra.
        """
        total = sum(len(v) for v in eligibility_sections(ANEXOS_TEXTO).values())
        self.assertLess(total, 5_000)

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


class ReuseBetweenRunsTests(unittest.TestCase):
    """Lo que evita pagar dos veces por leer el mismo anexo.

    La caché de análisis reutiliza un análisis mientras la huella del documento
    fuente no cambie. Si el texto del anexo no entrara en esa huella, dos cosas
    saldrían mal a la vez: una corrección de la Comisión no se notaría, y para
    forzar la relectura habría que subir una versión a mano e invalidar todo.
    """

    HOY = date(2026, 8, 31)

    def _fetch(self, *, status=200, texto=ANEXOS_TEXTO, stored=None, hoy=None, llamadas=None):
        registro = llamadas if llamadas is not None else []

        def http_get(url, **kwargs):
            registro.append(url)
            return Respuesta(status) if status else None

        return fetch_programme_eligibility(
            CONDICIONES_HTML,
            http_get=http_get,
            document_text=lambda response, url, **kwargs: (texto, "pdf"),
            stored=stored,
            today=hoy or self.HOY,
        ), registro

    def test_the_sections_carry_their_own_fingerprint(self):
        resultado, _ = self._fetch()
        self.assertEqual(len(resultado["fingerprint"]), 16)

    def test_the_same_annexes_give_the_same_call_fingerprint(self):
        """Mientras el anexo no cambie, el análisis pagado se reutiliza."""
        resultado, _ = self._fetch()
        convocatoria = {"source": "HORIZON EUROPE", "title": "Topic", "programme_eligibility": resultado}
        self.assertEqual(source_hash(convocatoria), source_hash(dict(convocatoria)))

    def test_a_changed_annex_forces_a_new_analysis(self):
        antes, _ = self._fetch()
        despues, _ = self._fetch(texto=ANEXOS_TEXTO.replace("three legal entities", "four legal entities"))
        self.assertNotEqual(antes["fingerprint"], despues["fingerprint"])
        base = {"source": "HORIZON EUROPE", "title": "Topic"}
        self.assertNotEqual(
            source_hash({**base, "programme_eligibility": antes}),
            source_hash({**base, "programme_eligibility": despues}),
        )

    def test_a_call_without_annexes_keeps_the_hash_it_always_had(self):
        """Añadir esto no puede invalidar la caché de las demás fuentes."""
        base = {"source": "BDNS", "title": "Ayuda industrial", "description": "x"}
        self.assertEqual(
            source_hash(base), source_hash({**base, "programme_eligibility": {}})
        )

    def test_a_recent_document_is_not_downloaded_again(self):
        stored = {}
        _, primeras = self._fetch(stored=stored)
        self.assertEqual(len(primeras), 1)
        _, segundas = self._fetch(stored=stored, hoy=date(2026, 9, 3))
        self.assertEqual(segundas, [], "tres días después no hace falta releerlo")

    def test_an_old_document_is_read_again(self):
        stored = {}
        self._fetch(stored=stored)
        _, segundas = self._fetch(stored=stored, hoy=date(2026, 9, 30))
        self.assertEqual(len(segundas), 1, "pasado el margen hay que releerlo")

    def test_a_failed_download_falls_back_to_what_was_read_before(self):
        """Sin esto, un portal caído dejaría 30 convocatorias sin elegibilidad."""
        stored = {}
        antes, _ = self._fetch(stored=stored)
        despues, _ = self._fetch(status=503, stored=stored, hoy=date(2026, 9, 30))
        self.assertEqual(despues["fingerprint"], antes["fingerprint"])

    def test_nothing_stored_and_nothing_downloaded_is_an_empty_answer(self):
        resultado, _ = self._fetch(status=503, stored={})
        self.assertEqual(resultado, {})


if __name__ == "__main__":
    unittest.main()
