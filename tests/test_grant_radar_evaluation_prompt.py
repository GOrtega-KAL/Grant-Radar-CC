# -*- coding: utf-8 -*-
# Pruebas del prompt de evaluación y del perfil de Kalfrisa.
#
# Nacen de un falso negativo real (AGENTS.md, sección 47): PowerUp NetZero
# recibió un encaje del 35 % y se descartó, siendo una convocatoria a la que la
# empresa sí se presenta. Las causas fueron de instrucción y de perfil, no de
# código, y ninguna de las tres redes de seguridad podía verlas porque el
# prompt de sistema era una variable local dentro de `analyze_with_claude()`.
#
# Por eso estas pruebas no comprueban comportamiento del modelo —eso solo se ve
# pagando— sino que las instrucciones que costó dinero descubrir siguen ahí y
# siguen enteras.

import re
import unittest

from grant_radar.kalfrisa_profile import KALFRISA_PROFILE
from grant_radar.versions import (
    ANALYSIS_PROMPT_VERSION,
    EVALUATOR_VERSION,
    PROFILE_VERSION,
)

from tests.test_grant_radar import APP  # noqa: E402  (carga el script con runpy)

SYSTEM_PROMPT = APP["CLAUDE_EVALUATION_SYSTEM_PROMPT"]


class EvaluationSystemPromptTests(unittest.TestCase):
    def test_the_consortium_sentence_is_not_split_in_half(self):
        """La regresión concreta que estuvo cuatro días sin detectarse.

        Al insertar la instrucción de `objeto_y_actuaciones` el 20/08/2026 se
        parti la frase de `consortium_required`, que quedó como «…admite
        solicitantes individuales además de objeto_y_actuaciones debe abrir el
        análisis…», con el resto huérfano cien palabras más abajo.
        """
        self.assertIn(
            "admite solicitantes individuales además de consorcios",
            SYSTEM_PROMPT,
        )
        self.assertNotIn(
            "además de objeto_y_actuaciones",
            SYSTEM_PROMPT,
            "la frase de consorcio vuelve a estar partida",
        )

    def test_no_instruction_runs_into_another_one(self):
        """Guarda genérica contra el mismo tipo de empalme.

        Un nombre de campo del esquema justo detrás de una preposición es la
        huella que dej la inserción mal puesta. No hay forma de detectar todos
        los empalmes posibles, pero sí este patrón, que es el que ocurrió.
        """
        campos = (
            "objeto_y_actuaciones", "resumen", "consortium_required",
            "deterministic_tech_tags", "fit_score", "actionability_score",
        )
        for campo in campos:
            with self.subTest(campo=campo):
                self.assertIsNone(
                    re.search(rf"\b(?:de|con|para|entre|además de)\s+{campo}\b",
                              SYSTEM_PROMPT),
                    f"«{campo}» aparece detrás de una preposición: posible empalme",
                )

    def test_consortium_experience_is_not_held_against_a_call(self):
        self.assertIn("experiencia acreditada en consorcios", SYSTEM_PROMPT)

    def test_empty_tech_tags_are_not_evidence_of_misalignment(self):
        self.assertIn("deterministic_tech_tags", SYSTEM_PROMPT)
        self.assertIn("no que no haya encaje", SYSTEM_PROMPT)

    def test_the_prompt_still_forbids_inventing_eligibility(self):
        """Lo que ya estaba y no debe perderse al añadir instrucciones."""
        self.assertIn("No conviertas ausencia de información en un hecho negativo",
                      SYSTEM_PROMPT)
        self.assertIn("Solo puedes recomendar partner_ids", SYSTEM_PROMPT)
        self.assertIn("CDTI e IDAE son financiadores, nunca socios", SYSTEM_PROMPT)


class KalfrisaProfileTests(unittest.TestCase):
    def test_simulation_is_an_autonomous_capability(self):
        """PowerUp NetZero encajaba por su tema de soluciones digitales.

        El perfil mencionaba gemelos digitales, pero en la misma frase que
        «vinculados a equipos y procesos térmicos», lo que invitaba a leerlos
        como capacidad subordinada. Ahora es línea propia.
        """
        self.assertIn("SIMULACIÓN Y GEMELOS DIGITALES", KALFRISA_PROFILE)
        self.assertIn("capacidad autónoma", KALFRISA_PROFILE)
        self.assertIn("EHAT", KALFRISA_PROFILE)

    def test_the_out_of_scope_list_does_not_exclude_a_whole_programme(self):
        """La cláusula describe el objeto de un proyecto, no la portada."""
        self.assertIn("no el paraguas temático de una", KALFRISA_PROFILE)
        self.assertIn("Lo que\n  se juzga es el tema concreto", KALFRISA_PROFILE)

    def test_the_out_of_scope_list_still_excludes_what_it_must(self):
        """Ampliar el criterio no puede convertirlo en un coladero."""
        for excluido in (
            "Edificios residenciales/terciarios y transporte",
            "Solar fotovoltaica, eólica o hidrógeno genérico sin uso térmico industrial",
            "Investigación básica TRL 1-3 sin ruta industrial",
        ):
            with self.subTest(excluido=excluido[:40]):
                self.assertIn(excluido, KALFRISA_PROFILE)

    def test_the_profile_still_refuses_to_invent_capabilities(self):
        self.assertIn("No atribuyas a Kalfrisa capacidades no incluidas aquí",
                      KALFRISA_PROFILE)

    def test_missing_partners_are_our_limitation_not_the_calls(self):
        self.assertIn(
            "la ausencia de\n  socios preidentificados en el radar no es un obstáculo",
            KALFRISA_PROFILE,
        )


class VersionBumpTests(unittest.TestCase):
    """Cambiar prompt o perfil sin subir versión deja la caché sirviendo lo viejo."""

    def test_the_three_versions_reflect_this_round(self):
        self.assertEqual(PROFILE_VERSION, "kalfrisa-2026-08-v5-simulation-line")
        self.assertEqual(EVALUATOR_VERSION, "fit-2026-08-v7-topic-and-scope")
        self.assertEqual(ANALYSIS_PROMPT_VERSION, "2026-08-v11-topic-and-scope")


if __name__ == "__main__":
    unittest.main()
