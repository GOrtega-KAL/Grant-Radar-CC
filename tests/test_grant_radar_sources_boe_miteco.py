# Pruebas de grant_radar/sources/boe_miteco.py con import estándar (sin runpy).
#
# tests/test_grant_radar.py ya prueba el caso positivo completo (INNOVAE).
# Aquí se cubre lo contrario: qué hace el conector cuando el marcado del BOE
# cambia o el inventario no carga, que es el modo de fallo real documentado
# (el parser se rompió una vez por un cambio de `p.linea-dem`).

import unittest

from grant_radar.runtime_state import RUN_DIAGNOSTICS, SOURCE_RUNTIME_METADATA
from grant_radar.sources.boe_miteco import fetch_boe


class FakeBrowser:
    def __init__(self, inventory="", detail=""):
        self.inventory, self.detail = inventory, detail
        self.urls = []

    def html(self, url, **kwargs):
        self.urls.append(url)
        return self.inventory if url.endswith("ayudas.php") else self.detail


class BoeInventoryHealthTests(unittest.TestCase):
    def setUp(self):
        SOURCE_RUNTIME_METADATA.clear()
        RUN_DIAGNOSTICS.clear()

    tearDown = setUp

    def _health(self):
        return RUN_DIAGNOSTICS["web_source_health"]["BOE / MITECO"]

    def test_an_unreachable_inventory_yields_no_results_and_is_reported(self):
        self.assertEqual(fetch_boe(FakeBrowser(inventory="")), [])
        self.assertEqual(self._health()["status"], "unhealthy")
        self.assertIn("inventory_unreachable", self._health()["issues"])

    def test_an_empty_but_valid_result_list_is_not_confused_with_a_broken_page(self):
        vacio = '<ul><li class="resultado-busqueda"></li></ul>'
        self.assertEqual(fetch_boe(FakeBrowser(inventory=vacio)), [])
        # La página cargó: el fallo, si lo hay, no es de acceso.
        self.assertNotIn("inventory_unreachable", self._health()["issues"])

    def test_a_call_without_a_confirmed_deadline_is_not_published(self):
        inventory = """
        <ul><li class="resultado-busqueda">
          <p class="linea-dem">Ministerio para la Transición Ecológica (BOE 1 de 01/01/2099)</p>
          <p>Extracto de la convocatoria de ayudas a la eficiencia energética industrial.</p>
          <a href="../buscar/doc.php?id=BOE-B-2099-200">Ir al documento</a>
        </li></ul>
        """
        detalle = """
        <html><h3>Extracto de la convocatoria de ayudas a la eficiencia energética</h3>
        <body>El plazo se anunciará próximamente.</body></html>
        """
        resultados = fetch_boe(FakeBrowser(inventory=inventory, detail=detalle))
        self.assertEqual(
            [r for r in resultados if not r.get("deadline_date")], [],
            "no debe publicarse una convocatoria sin plazo confirmado",
        )

    def test_the_source_metadata_is_always_recorded_even_without_results(self):
        fetch_boe(FakeBrowser(inventory=""))
        self.assertIn("BOE / MITECO", SOURCE_RUNTIME_METADATA)


if __name__ == "__main__":
    unittest.main()


class BoeTrackedAuthorityTests(unittest.TestCase):
    """
    El listado del BOE son citas legales, no descripciones.

    Medido el 21/08/2026 sobre las 168 entradas reales: la taxonomía técnica
    admitía **cero**, y las 8 que el conector abre entran todas por la regla de
    autoridad. Por eso la lista de organismos vigilados es la que decide la
    cobertura de esta fuente, y le faltaba justo la parte industrial: el
    Ministerio de Industria y Turismo (5 entradas ese día) y SEPIDES (2), con
    convocatorias como las Agrupaciones Empresariales Innovadoras.
    """

    def setUp(self):
        SOURCE_RUNTIME_METADATA.clear()
        RUN_DIAGNOSTICS.clear()

    tearDown = setUp

    @staticmethod
    def _listado(organismo, titulo):
        return (
            '<ul><li class="resultado-busqueda">'
            f'<p class="linea-dem">{organismo}</p>'
            f"<p>{titulo}</p>"
            '<a href="/diario_boe/txt.php?id=BOE-B-2026-1">Ir al documento</a>'
            "</li></ul>"
        )

    def _abre_la_ficha(self, organismo, titulo):
        navegador = FakeBrowser(
            inventory=self._listado(organismo, titulo), detail="",
        )
        fetch_boe(navegador)
        return any("diario_boe" in url for url in navegador.urls)

    def test_industry_ministry_aid_is_opened(self):
        self.assertTrue(self._abre_la_ficha(
            "Ministerio de Industria y Turismo",
            "Extracto de la Orden de 26 de mayo por la que se efectúa la "
            "convocatoria correspondiente a 2026 de las ayudas de apoyo a "
            "Agrupaciones Empresariales Innovadoras",
        ))

    def test_sepides_aid_is_opened(self):
        self.assertTrue(self._abre_la_ficha(
            "Ministerio de Industria y Turismo",
            "Extracto de la Resolución de 12 de junio de 2026 de la Sociedad "
            "Estatal de Promoción Industrial y Desarrollo Empresarial, Entidad "
            "Pública Empresarial, por la que se convocan ayudas",
        ))

    def test_the_ecological_transition_authorities_still_work(self):
        self.assertTrue(self._abre_la_ficha(
            "Ministerio para la Transición Ecológica y el Reto Demográfico",
            "Extracto de la Orden por la que se convoca el programa de "
            "incentivos correspondiente a 2026",
        ))

    def test_an_unrelated_ministry_is_not_opened(self):
        """La lista de organismos es una excepción acotada, no una puerta abierta."""
        self.assertFalse(self._abre_la_ficha(
            "Ministerio de Cultura",
            "Extracto de la Resolución por la que se convocan subvenciones "
            "para la promoción del teatro y la danza",
        ))

    def test_an_authority_without_an_aid_word_is_not_opened(self):
        self.assertFalse(self._abre_la_ficha(
            "Ministerio de Industria y Turismo",
            "Resolución por la que se publica el listado de personal "
            "funcionario de carrera del cuerpo correspondiente",
        ))
