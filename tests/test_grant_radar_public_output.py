# Pruebas de grant_radar/public_output.py con import estándar (sin runpy).
#
# El foco está en post_procesar_texto(), que se aplica al resumen ejecutivo y a
# la acción recomendada, es decir al texto que el usuario lee primero. Su
# versión anterior corrompía prosa española corriente; los casos de esta clase
# son literales tomados del `convocatorias.json` publicado el 14/08/2026.

import unittest

from grant_radar.public_output import (
    ENTIDADES_CANONICAS,
    derive_eligible_actions,
    post_procesar_texto,
)


class EntityNormalisationTests(unittest.TestCase):
    def test_real_corruptions_no_longer_happen(self):
        """Los cuatro daños observados en el JSON publicado.

        Cada cadena estaba realmente publicada con la palabra sustituida por
        un acrónimo: cierre→CIRCE, date→IDAE, vida→IDAE y CNAE→IDAE.
        """
        casos = [
            "Plazo de cierre: 2027-02-02",
            "reference_date 2026-08-04 sugiere convocatoria abierta",
            "validación de opciones de fin de vida en dos sectores",
            "verificación de que CNAE 2899 esté incluido en el anexo 1.3.b",
            "los CNAE elegibles no coinciden con la actividad",
        ]
        for texto in casos:
            with self.subTest(texto=texto[:40]):
                self.assertEqual(post_procesar_texto(texto), texto)

    def test_common_spanish_words_are_left_alone(self):
        for texto in (
            "La idea del proyecto es reducir el consumo",
            "Aplica a la industria del cine y la cultura",
            "Se evalúa el corte de emisiones",
            "Las ideas deben concretarse antes del cierre",
        ):
            with self.subTest(texto=texto[:40]):
                self.assertEqual(post_procesar_texto(texto), texto)

    def test_a_misspelled_entity_in_capitals_is_still_corrected(self):
        # El caso real para el que se creó la función.
        self.assertEqual(
            post_procesar_texto("Colaborar con ITAINNOMA en el piloto"),
            "Colaborar con ITAINNOVA en el piloto",
        )
        self.assertEqual(
            post_procesar_texto("Socio CIRCEE del consorcio"),
            "Socio CIRCE del consorcio",
        )

    def test_a_correct_entity_is_not_touched(self):
        texto = "Participan CIRCE, ITAINNOVA y el CDTI"
        self.assertEqual(post_procesar_texto(texto), texto)

    def test_protected_domain_acronyms_are_never_rewritten(self):
        for acronimo in ("CNAE", "NACE", "PYME", "BDNS", "TRL", "PRTR"):
            with self.subTest(acronimo=acronimo):
                texto = f"Requisito {acronimo} aplicable"
                self.assertEqual(post_procesar_texto(texto), texto)

    def test_short_acronyms_need_a_closer_match_than_long_ones(self):
        # Cuatro letras a distancia 2 ya no se tocan; nueve letras a
        # distancia 1 sí, porque ahí la variante sí es una errata plausible.
        self.assertEqual(post_procesar_texto("El IDEA general"), "El IDEA general")
        self.assertEqual(
            post_procesar_texto("ITAINNOVE colabora"), "ITAINNOVA colabora"
        )

    def test_empty_text_is_returned_unchanged(self):
        self.assertEqual(post_procesar_texto(""), "")
        self.assertIsNone(post_procesar_texto(None))

    def test_the_whitelist_is_the_expected_one(self):
        self.assertEqual(
            ENTIDADES_CANONICAS, ["ITAINNOVA", "CIRCE", "Unizar", "CDTI", "IDAE"]
        )


class EligibleActionsPrecedenceTests(unittest.TestCase):
    """La precedencia factual de derive_eligible_actions(), sin red."""

    def test_the_explicit_field_wins(self):
        acciones, base = derive_eligible_actions(
            {}, {"eligible_actions": ["Adquisición de maquinaria"],
                 "required_topics": ["Eficiencia"]}
        )
        self.assertEqual(base, "explicit")
        self.assertEqual(acciones, ["Adquisición de maquinaria"])

    def test_funding_lines_are_used_when_there_is_no_explicit_field(self):
        acciones, base = derive_eligible_actions(
            {},
            {"eligible_actions": [], "funding_lines": [
                {"name": "Línea industrial", "eligible_actions": ["Hornos"]}
            ]},
        )
        self.assertEqual(base, "funding_lines")
        self.assertIn("Línea industrial: Hornos", acciones)

    def test_required_topics_are_the_labelled_fallback(self):
        acciones, base = derive_eligible_actions(
            {}, {"eligible_actions": [], "required_topics": ["Ahorro energético"]}
        )
        self.assertEqual(base, "required_topics")

    def test_nothing_usable_is_reported_as_unavailable(self):
        self.assertEqual(derive_eligible_actions({}, {}), ([], "unavailable"))


if __name__ == "__main__":
    unittest.main()
