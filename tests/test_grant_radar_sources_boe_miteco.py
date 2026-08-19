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
