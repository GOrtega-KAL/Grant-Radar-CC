# Pruebas del módulo grant_radar/exclusion_terms.py.
#
# Import estándar (sin runpy): confirma que el JSON de listas de exclusión
# se carga bien y no ha perdido ni duplicado ninguna palabra por error de
# edición. No prueba la lógica de _hard_out_of_scope() en sí — eso lo cubre
# tests/fixtures/common_scope_filter_cases.json a través de
# test_grant_radar.py, que sigue pasando exactamente igual tras mover estas
# listas a JSON (ver SUGERENCIAS.MD 3.3).

import unittest

from grant_radar.exclusion_terms import (
    BUILDING_TERMS,
    CIVIL_SECURITY_TERMS,
    CYBERSECURITY_TERMS,
    EDUCATION_HEALTH_TERMS,
    GENERIC_DIGITAL_POLICY_TERMS,
    GOVERNANCE_PRIMARY_TERMS,
    MARINE_POLICY_TERMS,
    NUCLEAR_TERMS,
    RENEWABLE_GENERATION_TERMS,
    TRANSPORT_TERMS,
)

ALL_CATEGORIES = {
    "TRANSPORT_TERMS": TRANSPORT_TERMS,
    "BUILDING_TERMS": BUILDING_TERMS,
    "CYBERSECURITY_TERMS": CYBERSECURITY_TERMS,
    "CIVIL_SECURITY_TERMS": CIVIL_SECURITY_TERMS,
    "GOVERNANCE_PRIMARY_TERMS": GOVERNANCE_PRIMARY_TERMS,
    "RENEWABLE_GENERATION_TERMS": RENEWABLE_GENERATION_TERMS,
    "NUCLEAR_TERMS": NUCLEAR_TERMS,
    "MARINE_POLICY_TERMS": MARINE_POLICY_TERMS,
    "GENERIC_DIGITAL_POLICY_TERMS": GENERIC_DIGITAL_POLICY_TERMS,
    "EDUCATION_HEALTH_TERMS": EDUCATION_HEALTH_TERMS,
}


class ExclusionTermsLoadingTests(unittest.TestCase):
    def test_every_category_loaded_and_is_non_empty(self):
        for name, terms in ALL_CATEGORIES.items():
            with self.subTest(category=name):
                self.assertIsInstance(terms, tuple)
                self.assertGreater(len(terms), 0)

    def test_no_category_has_accidental_duplicate_terms(self):
        for name, terms in ALL_CATEGORIES.items():
            with self.subTest(category=name):
                self.assertEqual(len(terms), len(set(terms)))

    def test_known_terms_are_present_in_their_category(self):
        # Muestra representativa: confirma que el JSON no ha perdido
        # entradas conocidas al editarlo.
        self.assertIn("vessel", TRANSPORT_TERMS)
        self.assertIn("vivienda", BUILDING_TERMS)
        self.assertIn("ciberseguridad industrial", CYBERSECURITY_TERMS)
        self.assertIn("nuclear reactor", NUCLEAR_TERMS)
        self.assertIn("salud mental", EDUCATION_HEALTH_TERMS)


if __name__ == "__main__":
    unittest.main()
