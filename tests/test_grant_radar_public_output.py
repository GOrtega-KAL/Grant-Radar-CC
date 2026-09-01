# Pruebas de grant_radar/public_output.py con import estándar (sin runpy).
#
# El foco está en post_procesar_texto(), que se aplica al resumen ejecutivo y a
# la acción recomendada, es decir al texto que el usuario lee primero. Su
# versión anterior corrompía prosa española corriente; los casos de esta clase
# son literales tomados del `convocatorias.json` publicado el 14/08/2026.

import unittest
from unittest import mock

from grant_radar.public_output import (
    DEFAULT_KEYWORD_COLOR,
    ENTIDADES_CANONICAS,
    TECH_CATEGORY_COLORS,
    URL_CONTROL_INEXISTENTE,
    build_keywords,
    derive_eligible_actions,
    post_procesar_texto,
    verificar_urls,
)
from grant_radar.runtime_state import RUN_DIAGNOSTICS
from grant_radar.tech_taxonomy import TECH_TAGS


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


class RespuestaFalsa:
    def __init__(self, status_code):
        self.status_code = status_code


class UrlVerificationTests(unittest.TestCase):
    """
    `verificar_urls()` daba por buenas seis URLs de CDTI que llevaban a una
    página inexistente (AGENTS.md, sección 44): el WAF de cdti.es responde 200
    a cualquier ruta pedida por un cliente que no parece un navegador. La
    sonda de control detecta ese tipo de host preguntando por una ruta
    imposible antes de creerse ningún resultado.
    """

    def _verificar(self, convocatorias, respuestas):
        """`respuestas` mapea URL -> código; lo no listado responde 404."""
        def falso(url, **kwargs):
            return RespuestaFalsa(respuestas.get(url, 404))

        with mock.patch.object(
            __import__("grant_radar.public_output", fromlist=["requests"]),
            "requests",
            mock.Mock(head=falso, get=falso),
        ):
            verificar_urls(convocatorias, timeout=1)

    def test_a_host_that_answers_anything_is_reported_as_unverifiable(self):
        convocatorias = [{"url": "https://waf.example/ayudas/inventada"}]
        self._verificar(convocatorias, {
            f"https://waf.example{URL_CONTROL_INEXISTENTE}": 200,
            "https://waf.example/ayudas/inventada": 200,
        })
        self.assertFalse(convocatorias[0]["url_rota"])
        diagnostico = RUN_DIAGNOSTICS["url_verification"]
        self.assertEqual(diagnostico["unverifiable"], 1)
        self.assertEqual(diagnostico["opaque_hosts"], ["waf.example"])

    def test_a_well_behaved_host_needs_no_warning(self):
        convocatorias = [{"url": "https://sana.example/ayudas/real"}]
        self._verificar(convocatorias, {
            "https://sana.example/ayudas/real": 200,
        })
        self.assertFalse(convocatorias[0]["url_rota"])
        diagnostico = RUN_DIAGNOSTICS["url_verification"]
        self.assertEqual(diagnostico["unverifiable"], 0)
        self.assertEqual(diagnostico["opaque_hosts"], [])

    def test_a_real_failure_counts_even_on_an_opaque_host(self):
        """Un host permisivo puede tapar una URL rota, pero nunca inventa un error."""
        convocatorias = [{"url": "https://waf.example/caida"}]
        self._verificar(convocatorias, {
            f"https://waf.example{URL_CONTROL_INEXISTENTE}": 200,
            "https://waf.example/caida": 500,
        })
        self.assertTrue(convocatorias[0]["url_rota"])
        self.assertEqual(RUN_DIAGNOSTICS["url_verification"]["broken"], 1)
        self.assertEqual(RUN_DIAGNOSTICS["url_verification"]["unverifiable"], 0)

    def test_a_record_without_url_is_not_broken(self):
        convocatorias = [{"url": ""}]
        self._verificar(convocatorias, {})
        self.assertFalse(convocatorias[0]["url_rota"])
        self.assertEqual(RUN_DIAGNOSTICS["url_verification"]["checked"], 0)

    def test_the_public_record_never_grows_a_verifiability_field(self):
        """El esquema público solo crece con lo que el dashboard consume."""
        convocatorias = [{"url": "https://sana.example/ayudas/real"}]
        self._verificar(convocatorias, {"https://sana.example/ayudas/real": 200})
        self.assertNotIn("url_verificada", convocatorias[0])

    def test_the_control_probe_runs_once_per_host(self):
        convocatorias = [
            {"url": "https://sana.example/a"},
            {"url": "https://sana.example/b"},
        ]
        pedidas = []

        def falso(url, **kwargs):
            pedidas.append(url)
            return RespuestaFalsa(200 if not url.endswith(URL_CONTROL_INEXISTENTE) else 404)

        with mock.patch.object(
            __import__("grant_radar.public_output", fromlist=["requests"]),
            "requests",
            mock.Mock(head=falso, get=falso),
        ):
            verificar_urls(convocatorias, timeout=1)

        controles = [u for u in pedidas if u.endswith(URL_CONTROL_INEXISTENTE)]
        self.assertEqual(len(controles), 1, pedidas)


class KeywordPanelTests(unittest.TestCase):
    """
    `build_keywords()`: el panel de palabras clave del dashboard.

    Era la única función del backlog sin ninguna prueba (punto 19), y tenía un
    fallo: siete colores tecleados a mano contra palabras concretas, de los
    cuales **cuatro estaban muertos** porque el vocabulario escribe esas
    palabras de otra forma («hidrógeno» frente a la forma sin tilde de
    KEYWORDS, «hornos industriales» frente a `horno industrial`). Nunca podían
    coincidir, así que las palabras que de verdad se publican caían todas al
    color por defecto.

    Ahora el color se deriva de la CATEGORÍA técnica, que es lo que impide que
    vuelva a caducar (AGENTS.md 59).
    """

    def _fichas(self, *listas):
        return [{"keywords_found": list(l)} for l in listas]

    def test_cuenta_las_apariciones_y_ordena_por_frecuencia(self):
        panel = build_keywords(self._fichas(
            ["waste heat"], ["waste heat"], ["waste heat"],
            ["calor residual"], ["calor residual"],
            ["heat recovery"],
        ))
        self.assertEqual([(k["name"], k["count"]) for k in panel], [
            ("waste heat", 3), ("calor residual", 2), ("heat recovery", 1),
        ])

    def test_nunca_devuelve_mas_de_ocho(self):
        panel = build_keywords(self._fichas(*[[f"termino {i}"] for i in range(20)]))
        self.assertEqual(len(panel), 8)

    def test_una_palabra_del_vocabulario_recibe_el_color_de_su_categoria(self):
        panel = build_keywords(self._fichas(["waste heat"]))
        self.assertEqual(panel[0]["color"], TECH_CATEGORY_COLORS["waste_heat"])

    def test_las_dos_grafias_del_mismo_concepto_comparten_color(self):
        # El fallo que esto cierra: «descarbonización» tenía un color tecleado
        # a mano y «decarbonisation» no, para el mismo concepto.
        panel = build_keywords(self._fichas(["decarbonisation"], ["descarbonizacion"]))
        colores = {k["color"] for k in panel}
        self.assertEqual(len(colores), 1, f"colores distintos: {colores}")

    def test_ningun_color_declarado_apunta_a_una_categoria_inexistente(self):
        # La prueba que habría detectado el fallo original: que las claves del
        # mapa existan de verdad en la taxonomía.
        for categoria in TECH_CATEGORY_COLORS:
            self.assertIn(
                categoria, TECH_TAGS,
                f"{categoria} no existe en la taxonomía: color muerto",
            )

    def test_todas_las_categorias_de_la_taxonomia_tienen_color(self):
        # Y la simétrica: que no quede ninguna categoría sin colorear.
        faltan = sorted(set(TECH_TAGS) - set(TECH_CATEGORY_COLORS))
        self.assertFalse(faltan, f"categorías sin color asignado: {faltan}")

    def test_una_palabra_ajena_al_vocabulario_cae_al_color_por_defecto(self):
        panel = build_keywords(self._fichas(["algo que no es de la taxonomia"]))
        self.assertEqual(panel[0]["color"], DEFAULT_KEYWORD_COLOR)

    def test_sin_convocatorias_devuelve_lista_vacia(self):
        self.assertEqual(build_keywords([]), [])
        self.assertEqual(build_keywords([{"keywords_found": []}]), [])

    def test_una_ficha_sin_el_campo_no_rompe(self):
        self.assertEqual(build_keywords([{}]), [])


if __name__ == "__main__":
    unittest.main()
