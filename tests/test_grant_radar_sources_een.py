# -*- coding: utf-8 -*-
# Pruebas de grant_radar/sources/een.py con import estándar (sin runpy).
#
# Punto 20 del backlog. EEN era el otro conector sin archivo propio.
#
# Su problema característico no es la red, sino la AMBIGÜEDAD de lo que lee:
# la Enterprise Europe Network publica noticias de financiación y perfiles de
# búsqueda de socios, y en una página de perfil conviven el enlace a la
# convocatoria real y el enlace a la web del socio que la busca. Publicar el
# segundo como si fuera una convocatoria es el fallo que este conector tiene
# que evitar, y es silencioso: la ficha sale con una URL que carga bien y no
# lleva a ninguna ayuda.
#
# Por eso lo que se prueba aquí es la discriminación de enlaces y el descarte
# de páginas que no acreditan ser una convocatoria.

import unittest

from bs4 import BeautifulSoup

from grant_radar.sources.een import (
    EEN_RD_REQUEST_FILTER,
    _een_call_from_page,
    _een_listing_params,
    _een_profile_call_links,
)

PAGINA = "https://een.ec.europa.eu/partners/algo"


def _sopa(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


class ParametrosDeListadoTests(unittest.TestCase):

    def test_el_canal_de_perfiles_aplica_el_filtro_de_i_mas_d(self):
        params = _een_listing_params("profile", 3)
        self.assertEqual(params["page"], 3)
        self.assertEqual(params["f[0]"], EEN_RD_REQUEST_FILTER)

    def test_el_canal_de_noticias_no_lo_aplica(self):
        params = _een_listing_params("news", 1)
        self.assertEqual(params, {"page": 1})


class EnlacesDeConvocatoriaTests(unittest.TestCase):
    """Distinguir la convocatoria de la web del socio que la busca."""

    def test_reconoce_el_portal_de_la_comision(self):
        html = '<a href="https://ec.europa.eu/info/funding-tenders/opportunities/x">Call</a>'
        self.assertEqual(
            _een_profile_call_links(_sopa(html), PAGINA),
            ["https://ec.europa.eu/info/funding-tenders/opportunities/x"],
        )

    def test_reconoce_las_rutas_habituales_de_convocatoria(self):
        rutas = [
            "https://x.org/open-call",
            "https://x.org/calls/2026",
            "https://x.org/call-for-proposals",
            "https://x.org/programa/call/detalle",
        ]
        html = "".join(f'<a href="{r}">enlace</a>' for r in rutas)
        self.assertEqual(_een_profile_call_links(_sopa(html), PAGINA), rutas)

    def test_descarta_la_web_del_propio_socio(self):
        # El fallo que importa: publicar la web de la empresa que busca socios
        # como si fuera la convocatoria.
        html = (
            '<a href="https://empresa-socia.example/quienes-somos">Partner</a>'
            '<a href="https://empresa-socia.example/contacto">Contacto</a>'
        )
        self.assertEqual(_een_profile_call_links(_sopa(html), PAGINA), [])

    def test_descarta_enlaces_del_propio_een(self):
        # Un enlace interno no es la convocatoria externa que se busca.
        html = f'<a href="{PAGINA}/otra-seccion/call">interno</a>'
        self.assertEqual(_een_profile_call_links(_sopa(html), PAGINA), [])

    def test_descarta_lo_que_no_sea_https(self):
        html = (
            '<a href="http://inseguro.example/open-call">http</a>'
            '<a href="mailto:alguien@example.org">correo</a>'
        )
        self.assertEqual(_een_profile_call_links(_sopa(html), PAGINA), [])

    def test_no_confunde_call_dentro_de_otra_palabra(self):
        # "callback" o "recall" no son convocatorias: el patrón exige que
        # `call` vaya delimitado.
        html = (
            '<a href="https://x.org/callback-api">callback</a>'
            '<a href="https://x.org/recall/2026">recall</a>'
        )
        self.assertEqual(_een_profile_call_links(_sopa(html), PAGINA), [])

    def test_no_repite_un_mismo_enlace(self):
        html = (
            '<a href="https://x.org/open-call">uno</a>'
            '<a href="https://x.org/open-call">otra vez</a>'
        )
        self.assertEqual(_een_profile_call_links(_sopa(html), PAGINA), 1 * [
            "https://x.org/open-call"
        ])

    def test_resuelve_enlaces_relativos_contra_la_pagina(self):
        # Un relativo se resuelve sobre el propio dominio de EEN, así que debe
        # quedar descartado por interno, no colarse a medias.
        html = '<a href="/algo/open-call">relativo</a>'
        self.assertEqual(_een_profile_call_links(_sopa(html), PAGINA), [])


class AcreditacionDeConvocatoriaTests(unittest.TestCase):
    """Una página solo pasa si acredita ser una convocatoria."""

    def test_un_perfil_sin_bloque_call_details_se_descarta(self):
        html = "<h1>Búsqueda de socio tecnológico</h1><main>Empresa alemana busca socio.</main>"
        self.assertIsNone(_een_call_from_page(PAGINA, html, "profile"))

    def test_una_pagina_sin_contexto_de_financiacion_se_descarta(self):
        html = "<h1>Noticias de la red</h1><main>Resumen de actividades del trimestre.</main>"
        self.assertIsNone(_een_call_from_page(PAGINA, html, "news"))

    def _perfil(self, plazo: str) -> str:
        # Un perfil completo exige las tres cosas: bloque Call details, plazo
        # futuro parseable y enlace externo a la convocatoria.
        return (
            "<h1>Perfil de I+D</h1><main>Call details "
            f"Deadline of the call {plazo} Web link "
            '<a href="https://ec.europa.eu/info/funding-tenders/opportunities/topic">'
            "convocatoria</a></main>"
        )

    def test_un_perfil_completo_se_acepta(self):
        call = _een_call_from_page(PAGINA, self._perfil("31 December 2099"), "profile")
        self.assertIsNotNone(call)
        self.assertEqual(call["deadline_date"], "2099-12-31")
        self.assertEqual(call["org"], "Enterprise Europe Network")
        # El enlace publicado debe ser el de la convocatoria, no el del perfil.
        self.assertNotEqual(call["url"], PAGINA)
        self.assertIn("funding-tenders", call["url"])

    def test_un_perfil_con_el_plazo_vencido_se_descarta(self):
        self.assertIsNone(
            _een_call_from_page(PAGINA, self._perfil("1 January 2020"), "profile")
        )

    def test_un_perfil_sin_plazo_se_descarta(self):
        html = (
            "<h1>Perfil</h1><main>Call details sin fecha alguna "
            '<a href="https://x.org/open-call">enlace</a></main>'
        )
        self.assertIsNone(_een_call_from_page(PAGINA, html, "profile"))

    def test_un_perfil_sin_enlace_externo_se_descarta(self):
        # Sin enlace no hay dónde solicitar: publicarlo sería una ficha muerta.
        html = "<h1>Perfil</h1><main>Call details Deadline of the call 31 December 2099</main>"
        self.assertIsNone(_een_call_from_page(PAGINA, html, "profile"))

    def test_un_topic_de_horizon_se_atribuye_a_horizon_no_a_een(self):
        # EEN es el canal por el que se descubre, no la fuente de la ayuda.
        html = (
            "<h1>Perfil</h1><main>Call details Call title and identifier "
            "HORIZON-CL5-2026-01-D2-01 Deadline of the call 31 December 2099 Web link "
            '<a href="https://ec.europa.eu/info/funding-tenders/opportunities/t">c</a></main>'
        )
        call = _een_call_from_page(PAGINA, html, "profile")
        self.assertIsNotNone(call)
        self.assertEqual(call["source"], "HORIZON EUROPE")


if __name__ == "__main__":
    unittest.main()
