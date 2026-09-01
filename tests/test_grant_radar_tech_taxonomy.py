# Pruebas del módulo grant_radar/tech_taxonomy.py.
#
# Import estándar (sin runpy). No repite la cobertura de
# tests/fixtures/common_scope_filter_cases.json (que sigue viviendo en
# test_grant_radar.py y prueba el pipeline completo); aquí se prueban las
# funciones de esta taxonomía de forma aislada.

import unittest

from grant_radar.tech_taxonomy import (
    KEYWORDS,
    TECH_TAGS,
    _compat_tags_for,
    _contextual_term_present,
    _term_present,
    detect_tech_tags,
    has_technology_discovery_signal,
    is_relevant,
    keyword_match,
)


class TaxonomyDataTests(unittest.TestCase):
    def test_tech_tags_combines_strong_and_contextual_vocabulary(self):
        self.assertIn("waste_heat", TECH_TAGS)
        self.assertIn("calor residual", TECH_TAGS["waste_heat"])

    def test_keywords_is_derived_from_all_categories(self):
        self.assertIn("calor residual", KEYWORDS)
        self.assertIn("digital twin", KEYWORDS)


class MatchingTests(unittest.TestCase):
    def test_term_present_rejects_acronym_substring_false_positives(self):
        self.assertTrue(_term_present("un sistema RTO instalado", "rto"))
        self.assertFalse(_term_present("demonstration project", "rto"))

    def test_detect_tech_tags_finds_strong_terms_without_context(self):
        self.assertIn("waste_heat", detect_tech_tags("Recuperación de calor residual industrial"))

    def test_contextual_term_requires_nearby_industrial_signal(self):
        near_industrial = "digital twin para procesos industriales y hornos"
        far_from_industrial = "digital twin para videojuegos y ocio"
        self.assertTrue(_contextual_term_present(near_industrial, "digital twin"))
        self.assertFalse(_contextual_term_present(far_from_industrial, "digital twin"))

    def test_is_relevant_requires_industrial_context_for_energy_efficiency_alone(self):
        self.assertFalse(is_relevant("Eficiencia energética en viviendas residenciales"))
        self.assertTrue(is_relevant("Eficiencia energética en procesos industriales de fabricación"))

    def test_is_relevant_accepts_industry_named_as_a_sector(self):
        """
        Casos reales del inventario del IDAE (AGENTS.md, sección 44).

        El vocabulario de contexto industrial nombraba el proceso ("procesos
        industriales", "horno", "fabricación") pero no el sector como tal, así
        que convocatorias dirigidas literalmente a la industria caían del
        prefiltro. Estas tres son títulos textuales del IDAE.
        """
        self.assertTrue(is_relevant("Para eficiencia energética en la industria"))
        self.assertTrue(is_relevant(
            "Ayudas para actuaciones de eficiencia energética en PYME y gran "
            "empresa del sector industrial (2026)"
        ))
        self.assertTrue(is_relevant(
            "Eficiencia energética en PYME y gran empresa del sector "
            "industrial. Convocatorias en las Comunidades Autónomas"
        ))

    def test_is_relevant_still_rejects_efficiency_outside_industry(self):
        """El contexto industrial sigue siendo obligatorio, no decorativo."""
        self.assertFalse(is_relevant("Eficiencia energética en viviendas residenciales"))
        self.assertFalse(is_relevant(
            "Ayudas de eficiencia energética para la rehabilitación de "
            "edificios del sector terciario"
        ))
        self.assertFalse(is_relevant(
            "Programa de eficiencia energética en explotaciones agropecuarias"
        ))

    def test_is_relevant_accepts_specific_technical_families_alone(self):
        self.assertTrue(is_relevant("Recuperación de calor residual en horno industrial"))

    def test_keyword_match_returns_only_matched_keywords(self):
        matches = keyword_match("Proyecto de recuperador de calor residual")
        self.assertIn("recuperador", matches)
        self.assertNotIn("digital twin", matches)

    def test_has_technology_discovery_signal_includes_discovery_only_terms(self):
        self.assertTrue(has_technology_discovery_signal(
            "Heat exchanger for industrial processes pilot"
        ))

    def test_compat_tags_translate_to_legacy_short_codes(self):
        self.assertEqual(_compat_tags_for(["hydrogen_combustion"]), ["desc", "h2"])
        self.assertEqual(_compat_tags_for(["unknown_tag"]), [])


class PluralMatchingTests(unittest.TestCase):
    """
    El plural, añadido el 01/09/2026 tras medirlo dos veces (AGENTS.md 56.2).

    El español administrativo de las convocatorias escribe casi siempre en
    plural, y la coincidencia exacta lo perdía. El caso que decidió el asunto
    es el primero: «recuperación de calores residuales» es el negocio central
    de Kalfrisa y no activaba nada por una «s».
    """

    def test_el_plural_del_negocio_central_ya_se_detecta(self):
        self.assertTrue(_term_present(
            "recuperacion de calores residuales en la industria", "calor residual"
        ))
        self.assertIn(
            "waste_heat",
            detect_tech_tags("recuperacion de calores residuales industriales"),
        )

    def test_el_singular_sigue_detectandose(self):
        self.assertTrue(_term_present("recuperacion de calor residual", "calor residual"))

    def test_admite_las_dos_formas_de_plural_espanol(self):
        # -s en la palabra llana, -es en la aguda: «hornos industriales».
        self.assertTrue(_term_present(
            "sustitucion de hornos industriales", "horno industrial"
        ))
        self.assertTrue(_term_present(
            "inversiones en tratamientos termicos", "tratamiento termico"
        ))

    def test_el_plural_ingles_tambien(self):
        self.assertTrue(_term_present(
            "high-temperature processes in industry", "high-temperature process"
        ))

    def test_el_guardian_de_siglas_sigue_intacto(self):
        # Era la razón de ser del patrón original y no debe haberse aflojado.
        self.assertFalse(_term_present("demonstration of the technology", "rto"))

    def test_las_siglas_no_se_pluralizan(self):
        """
        El fallo que costó ocho convocatorias irrelevantes (AGENTS.md 59.4).

        `RTO` es, en el vocabulario de Kalfrisa, un *Regenerative Thermal
        Oxidizer*. En la letra pequeña de Horizon, «RTOs» son las *Research and
        Technology Organisations*, y aparecen en casi todos los topics. La
        primera versión del plural las hacía casar, y entraron al embudo
        infraestructura cuántica, mundos virtuales y software de automoción.
        """
        boilerplate = (
            "Universities, RTOs and SMEs are encouraged to participate in "
            "this quantum computing infrastructure topic"
        )
        self.assertFalse(_term_present(boilerplate, "rto"))
        # Y la sigla exacta debe seguir detectándose donde sí toca.
        self.assertTrue(_term_present("instalacion de un RTO para COV", "rto"))

    def test_ninguna_palabra_corta_del_vocabulario_se_pluraliza(self):
        # La regla, comprobada sobre el vocabulario real: todo lo de tres
        # letras o menos es sigla («cfd», «cov», «voc») o partícula («de»,
        # «of», «en»). Ninguna admite plural.
        for sigla in ("rto", "voc", "cov", "cfd"):
            with self.subTest(sigla=sigla):
                self.assertFalse(_term_present(f"los {sigla}s del sector", sigla))

    def test_no_casa_dentro_de_otra_palabra(self):
        # ALDEHORNO es un municipio de Segovia; apareció de verdad en los
        # documentos oficiales al investigar el chip «Hornos» (AGENTS.md 55.1).
        self.assertFalse(_term_present("aldehorno industrializado", "horno industrial"))
        self.assertFalse(_term_present(
            "la empresa procesa termicamente los residuos", "proceso termico"
        ))

    def test_no_se_admite_variacion_de_genero(self):
        # Decisión medida, no descuido: el género no cambia ni una
        # clasificación sobre 368 textos reales y añade concordancias
        # incorrectas (AGENTS.md 58). Esta prueba existe para que no se
        # reabra sin volver a medir.
        self.assertFalse(_term_present(
            "optimizacion de procesos termicas", "proceso termico"
        ))

    def test_un_termino_vacio_no_casa_con_nada(self):
        self.assertFalse(_term_present("cualquier texto", ""))
        self.assertFalse(_term_present("cualquier texto", "   "))


if __name__ == "__main__":
    unittest.main()
