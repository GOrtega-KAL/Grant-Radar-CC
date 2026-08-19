# Pruebas de grant_radar/bdns_fields.py con import estándar (sin runpy).
#
# Estas primitivas las comparten el conector BDNS y la matriz de reglas previa
# a Claude, así que un cambio aquí afecta a las dos. No deciden elegibilidad:
# solo leen lo que la fuente entrega, con las formas variables que SNPSAP usa
# de verdad (cadena suelta, lista, o lista de dicts con claves distintas).

import unittest

from grant_radar.bdns_fields import (
    BDNS_NAMED_ACCESS_TERMS,
    _bdns_codes,
    _bdns_company_eligible,
    _bdns_descriptions,
    _bdns_execution_days,
    _nace_section,
)


class DescriptionsTests(unittest.TestCase):
    def test_accepts_the_three_shapes_that_the_api_returns(self):
        self.assertEqual(_bdns_descriptions("Empresas"), ["Empresas"])
        self.assertEqual(_bdns_descriptions(["Empresas", "PYME"]), ["Empresas", "PYME"])
        self.assertEqual(
            _bdns_descriptions([{"descripcion": "Empresas"}, {"nombre": "PYME"}]),
            ["Empresas", "PYME"],
        )

    def test_falls_back_through_the_key_order_and_normalises_whitespace(self):
        self.assertEqual(
            _bdns_descriptions([{"codigo": "  C  25 "}]), ["C 25"]
        )

    def test_drops_empties_and_duplicates(self):
        self.assertEqual(
            _bdns_descriptions([{"descripcion": "Empresas"}, "Empresas", "", None]),
            ["Empresas"],
        )

    def test_none_is_an_empty_list_not_an_error(self):
        self.assertEqual(_bdns_descriptions(None), [])


class CodesTests(unittest.TestCase):
    def test_extracts_only_entries_that_carry_a_code(self):
        self.assertEqual(
            _bdns_codes([{"codigo": "25.11"}, {"descripcion": "sin codigo"}, "texto"]),
            ["25.11"],
        )

    def test_a_non_list_value_does_not_break(self):
        self.assertEqual(_bdns_codes(None), [])
        self.assertEqual(_bdns_codes("25.11"), [])


class NaceSectionTests(unittest.TestCase):
    def test_an_explicit_section_wins_over_the_division_number(self):
        self.assertEqual(_nace_section("Sección C - división 01"), "C")

    def test_maps_the_division_to_its_section(self):
        casos = {"01 Agricultura": "A", "25.11 Fabricación": "C",
                 "35 Suministro de energía": "D", "38 Residuos": "E",
                 "43 Construcción": "F", "85 Educación": "P"}
        for texto, seccion in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(_nace_section(texto), seccion)

    def test_text_without_a_division_returns_empty(self):
        self.assertEqual(_nace_section("Actividades varias"), "")
        self.assertEqual(_nace_section(""), "")


class CompanyEligibleTests(unittest.TestCase):
    def test_recognises_the_usual_business_wordings(self):
        for beneficiario in (
            "Empresas", "PYME", "Pequeña y mediana empresa", "Gran empresa",
            "Empresas privadas y entidades sin ánimo de lucro",
        ):
            with self.subTest(beneficiario=beneficiario):
                self.assertTrue(_bdns_company_eligible([beneficiario]))

    def test_a_public_or_non_profit_only_list_is_not_company_eligible(self):
        self.assertFalse(_bdns_company_eligible(
            ["Ayuntamientos", "Universidades públicas", "Entidades sin ánimo de lucro"]
        ))

    def test_a_self_employed_person_with_economic_activity_counts(self):
        self.assertTrue(_bdns_company_eligible(
            ["Persona física que desarrolla actividad económica"]
        ))

    def test_known_inconsistency_singular_and_plural_never_meet(self):
        """La vía de autónomos está partida entre singular y plural.

        La condición positiva busca "persona fisica" (singular) y el guardián
        que la anula busca "no desarrollan" (plural verbal). Ninguna cadena
        real puede cumplir las dos a la vez, así que el guardián nunca llega a
        aplicarse: una categoría en singular con "no desarrolla" se considera
        elegible, y el plural correcto de SNPSAP no entra por esta vía.

        Se deja como está a propósito. Es la matriz previa a Claude, fuera del
        alcance de la modularización, y tocarla cambia qué convocatorias
        llegan a Haiku, o sea el coste. Su efecto práctico hoy es pequeño: el
        catálogo de SNPSAP usa el plural, que devuelve False —la respuesta
        conservadora—, y en cuanto la lista incluye "Empresas", que es el caso
        habitual, la regla general ya la reconoce. Queda anotado en AGENTS.md
        sección 31.5 como candidato a revisar con fixtures primero.
        """
        # El plural del catálogo real no entra solo...
        self.assertFalse(_bdns_company_eligible(
            ["Personas físicas que desarrollan actividad económica"]
        ))
        # ...pero sí en cuanto aparece "Empresas" en la lista.
        self.assertTrue(_bdns_company_eligible(
            ["Personas físicas que desarrollan actividad económica", "Empresas"]
        ))
        # Y el guardián de exclusión, en singular, no llega a aplicarse.
        self.assertTrue(_bdns_company_eligible(
            ["Persona física que no desarrolla actividad económica"]
        ))
        # En plural devuelve False, pero porque falla el positivo, no el guardián.
        self.assertFalse(_bdns_company_eligible(
            ["Personas físicas que no desarrollan actividad económica"]
        ))

    def test_the_four_real_snpsap_categories_are_classified_correctly(self):
        """Las únicas categorías que la fuente entrega de verdad.

        Recuento sobre los artefactos locales: 644, 264, 134 y 20 apariciones
        respectivamente. Con datos reales la función acierta en las cuatro, y
        por eso la incoherencia singular/plural de la prueba anterior no tiene
        efecto observable (ver AGENTS.md 31.5).
        """
        casos = {
            "PYME Y PERSONAS FÍSICAS QUE DESARROLLAN ACTIVIDAD ECONÓMICA": True,
            "GRAN EMPRESA": True,
            "PERSONAS JURÍDICAS QUE NO DESARROLLAN ACTIVIDAD ECONÓMICA": False,
            "PERSONAS FÍSICAS QUE NO DESARROLLAN ACTIVIDAD ECONÓMICA": False,
        }
        for categoria, esperado in casos.items():
            with self.subTest(categoria=categoria):
                self.assertEqual(_bdns_company_eligible([categoria]), esperado)

    def test_an_empty_list_is_not_a_yes(self):
        self.assertFalse(_bdns_company_eligible([]))


class ExecutionDaysTests(unittest.TestCase):
    def test_reads_a_period_expressed_in_months_or_years(self):
        self.assertIsNotNone(_bdns_execution_days("plazo de ejecución de 24 meses"))
        self.assertIsNotNone(_bdns_execution_days("periodo de ejecución de 2 años"))

    def test_returns_none_when_no_period_is_declared(self):
        self.assertIsNone(_bdns_execution_days("La convocatoria se publicará en breve"))


class NamedAccessTermsTests(unittest.TestCase):
    def test_the_shared_vocabulary_is_folded_and_without_duplicates(self):
        self.assertTrue(BDNS_NAMED_ACCESS_TERMS)
        self.assertEqual(len(set(BDNS_NAMED_ACCESS_TERMS)), len(BDNS_NAMED_ACCESS_TERMS))
        for term in BDNS_NAMED_ACCESS_TERMS:
            with self.subTest(term=term):
                # Se comparan contra texto ya plegado: sin tildes ni mayúsculas.
                self.assertEqual(term, term.casefold())
                self.assertNotRegex(term, r"[áéíóúñ]")


if __name__ == "__main__":
    unittest.main()
