# Pruebas de grant_radar/dedup.py con import estándar (sin runpy).
#
# tests/test_grant_radar.py ya cubre _deduplicate_raw_convocations() de punta a
# punta con fixtures reales. Aquí se prueban por separado las tres piezas del
# criterio de identidad, que antes solo se ejercitaban a través de ella.

import unittest

from grant_radar.audit import DISCOVERY_AUDIT
from grant_radar.dedup import (
    _add_discovery_source,
    _deduplicate_raw_convocations,
    _document_rank,
    _document_role,
    _programme_identity,
)


class ProgrammeIdentityTests(unittest.TestCase):
    def test_recognises_an_acronym_in_parentheses(self):
        folded, display = _programme_identity(
            "Extracto del programa de proyectos singulares (INNOVAE) 2026"
        )
        self.assertEqual(folded, "innovae")
        self.assertEqual(display, "INNOVAE")

    def test_recognises_a_named_programme_without_parentheses(self):
        # La identidad se queda en el acrónimo, sin el ordinal: es lo correcto
        # aquí, porque "MOVES III" y "MOVES III 2026" deben poder fusionarse.
        folded, _ = _programme_identity("Convocatoria del Programa MOVES III")
        self.assertEqual(folded, "moves")

    def test_a_title_without_the_word_programa_has_no_identity(self):
        self.assertEqual(_programme_identity("Ayudas a la industria de Aragón"), ("", ""))

    def test_generic_administrative_acronyms_are_rejected(self):
        # Fusionar por "FEDER" o "PRTR" uniría convocatorias sin relación.
        for titulo in (
            "Extracto del programa (FEDER)",
            "Resolución del programa (PRTR)",
            "Convocatoria del programa (IDAE)",
        ):
            with self.subTest(titulo=titulo):
                self.assertEqual(_programme_identity(titulo), ("", ""))

    def test_a_bare_year_is_not_an_identity(self):
        self.assertEqual(_programme_identity("Extracto del programa (2026)"), ("", ""))


class DocumentRoleTests(unittest.TestCase):
    def test_an_explicit_role_wins_over_any_inference(self):
        self.assertEqual(
            _document_role({"document_role": "regulatory_bases", "title": "Extracto"}),
            "regulatory_bases",
        )

    def test_infers_the_role_from_title_and_url(self):
        casos = {
            "Extracto de la convocatoria": "call_extract",
            "Se convoca la ayuda a la industria": "call",
            "Orden de bases reguladoras": "regulatory_bases",
            "Corrección de errores de la orden": "amendment",
            "Nota informativa": "source_record",
        }
        for titulo, esperado in casos.items():
            with self.subTest(titulo=titulo):
                self.assertEqual(_document_role({"title": titulo}), esperado)

    def test_an_idae_grant_page_is_a_programme_landing(self):
        self.assertEqual(
            _document_role({
                "source": "IDAE",
                "title": "Programa INNOVAE",
                "url": "https://www.idae.es/ayudas-y-financiacion/programa-innovae",
            }),
            "program_landing",
        )


class DocumentRankTests(unittest.TestCase):
    def test_a_landing_outranks_bases_regardless_of_length(self):
        landing = {
            "source": "IDAE",
            "url": "https://www.idae.es/ayudas-y-financiacion/x",
            "title": "Programa X",
        }
        bases = {"document_role": "regulatory_bases", "description": "x" * 5_000}
        self.assertGreater(_document_rank(landing), _document_rank(bases))

    def test_a_confirmed_deadline_breaks_the_tie_between_equal_roles(self):
        con_fecha = {"document_role": "call", "deadline_date": "2026-11-30"}
        sin_fecha = {"document_role": "call", "deadline_date": ""}
        self.assertGreater(_document_rank(con_fecha), _document_rank(sin_fecha))

    def test_an_unconfirmed_date_ranks_below_a_confirmed_one(self):
        confirmada = {"document_role": "call", "deadline_date": "2026-11-30"}
        prevista = {
            "document_role": "call",
            "deadline_date": "2026-11-30",
            "fecha_sin_confirmar": True,
        }
        self.assertGreater(_document_rank(confirmada), _document_rank(prevista))


class DiscoverySourceTests(unittest.TestCase):
    def test_accumulates_sources_without_repeating(self):
        item = {}
        _add_discovery_source(item, "BDNS")
        _add_discovery_source(item, "BOE / MITECO")
        _add_discovery_source(item, "BDNS")
        self.assertEqual(item["discovery_sources"], ["BDNS", "BOE / MITECO"])

    def test_an_empty_source_is_ignored_but_the_field_is_created(self):
        item = {}
        _add_discovery_source(item, "")
        self.assertEqual(item["discovery_sources"], [])


class DeduplicationTests(unittest.TestCase):
    def setUp(self):
        DISCOVERY_AUDIT.clear()

    tearDown = setUp

    def test_the_same_bdns_id_keeps_one_record_and_traces_both_sources(self):
        extracto = {
            "source": "BOE / MITECO", "bdns_id": "990100",
            "title": "Extracto de la convocatoria del Programa INNOVAE",
            "description": "Extracto oficial", "url": "https://boe.test/extracto",
            "deadline_date": "2026-11-18", "deadline_days": 90,
        }
        landing = {
            "source": "IDAE", "bdns_id": "990100", "title": "Programa INNOVAE",
            "description": "Ficha del programa en IDAE",
            "url": "https://www.idae.es/ayudas-y-financiacion/programa-innovae",
            "deadline_date": "2026-11-18", "deadline_days": 90,
        }
        resultado = _deduplicate_raw_convocations([extracto, landing])
        self.assertEqual(len(resultado), 1)
        self.assertCountEqual(
            resultado[0]["discovery_sources"], ["BOE / MITECO", "IDAE"]
        )

    def test_two_unrelated_calls_are_not_merged(self):
        a = {
            "source": "BDNS", "bdns_id": "1", "title": "Ayudas a la industria",
            "description": "a", "url": "https://a.test", "deadline_days": 30,
        }
        b = {
            "source": "BDNS", "bdns_id": "2", "title": "Ayudas a la eficiencia",
            "description": "b", "url": "https://b.test", "deadline_days": 30,
        }
        self.assertEqual(len(_deduplicate_raw_convocations([a, b])), 2)


if __name__ == "__main__":
    unittest.main()
