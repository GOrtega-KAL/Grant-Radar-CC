# -*- coding: utf-8 -*-
# Prueba de humo por conector: que cada fetch_*() recorra su camino entero sin
# tropezar con un nombre que no existe.
#
# Punto 17 del backlog, abierto desde el 19/08/2026. Tapa el hueco más caro del
# mapa de redes de seguridad (AGENTS.md 36.5): un `NameError` en un conector no
# lo ve `py_compile` —no resuelve nombres— ni la suite —que prueba las piezas,
# no el recorrido— y aparecía a los once minutos de recopilación o, peor, en
# una ejecución de pago. Pasó de verdad con `statistics` en el conector ECCP
# (sección 35): se descubrió en producción.
#
# Qué hace y qué no. Sustituye la red y el navegador por dobles que devuelven
# respuestas vacías pero bien formadas, y comprueba que el conector llega hasta
# el final y devuelve una lista. **No comprueba que extraiga bien**: eso lo
# hacen las pruebas de cada fuente con HTML real. Aquí lo que se protege es que
# el camino exista después de mover código, que es justo lo que las rondas de
# modularización rompen.
#
# Y un límite que conviene decir: con respuestas vacías no se recorren las ramas
# que solo existen cuando la fuente trae datos. Esta prueba reduce el hueco, no
# lo cierra; la ejecución `--no-claude` sigue siendo obligatoria al cerrar una
# ronda.

import unittest
from contextlib import ExitStack
from unittest import mock

from grant_radar import runtime_state
from grant_radar.audit import DISCOVERY_AUDIT
from grant_radar.sources import (
    bdns as bdns_module,
    boa_aragon as boa_module,
    boe_miteco as boe_module,
    cdti as cdti_module,
    eccp as eccp_module,
    een as een_module,
    horizon_europe as horizon_module,
    idae as idae_module,
)


class RespuestaVacia:
    """Lo que devuelve una fuente que responde bien y no trae nada."""

    status_code = 200
    headers = {"content-type": "application/json"}
    content = b"{}"
    text = "{}"
    encoding = "utf-8"
    url = "https://example.test/vacio"
    ok = True

    def json(self):
        return {}

    def raise_for_status(self):
        return None


class NavegadorVacio:
    """Un Chromium que carga y no encuentra nada, sin abrir Chromium."""

    def status(self, url: str):
        return 200

    def html(self, url: str, wait_selector: str = "body"):
        return "<html><body><main></main></body></html>"


def _sin_red(*args, **kwargs):
    return RespuestaVacia()


class SourceSmokeTests(unittest.TestCase):
    """Cada conector, de principio a fin, con la red sustituida."""

    def setUp(self):
        DISCOVERY_AUDIT.clear()
        runtime_state.SOURCE_RUNTIME_METADATA.clear()
        runtime_state.IDENTITY_LANDINGS.clear()
        self.addCleanup(DISCOVERY_AUDIT.clear)
        self.addCleanup(runtime_state.SOURCE_RUNTIME_METADATA.clear)

    def _correr(self, modulo, funcion, *args):
        """Ejecuta un conector con todo lo que sale a la red sustituido.

        Los conectores que solo usan el navegador no tienen `_http_get` ni
        `requests`: en ese caso no hay nada que sustituir y basta el navegador
        de mentira que reciben como parámetro.
        """
        sesion_falsa = mock.Mock(
            get=mock.Mock(side_effect=_sin_red),
            post=mock.Mock(side_effect=_sin_red),
        )
        dobles = {
            "_http_get": mock.Mock(side_effect=_sin_red),
            "requests": mock.Mock(
                get=mock.Mock(side_effect=_sin_red),
                post=mock.Mock(side_effect=_sin_red),
                Session=mock.Mock(return_value=sesion_falsa),
            ),
        }
        with ExitStack() as pila:
            for nombre, doble in dobles.items():
                if hasattr(modulo, nombre):
                    pila.enter_context(mock.patch.object(modulo, nombre, doble))
            return funcion(*args)

    def test_bdns(self):
        self.assertIsInstance(self._correr(bdns_module, bdns_module.fetch_bdns), list)

    def test_horizon_europe(self):
        self.assertIsInstance(
            self._correr(horizon_module, horizon_module.fetch_horizon_europe), list
        )

    def test_een(self):
        self.assertIsInstance(self._correr(een_module, een_module.fetch_een_funding), list)

    def test_eccp(self):
        # ECCP recibe el prefiltro como parámetro para no depender de las
        # reglas: quien lo llame debe pasárselo (AGENTS.md sección 35).
        self.assertIsInstance(
            self._correr(eccp_module, eccp_module.fetch_eccp, lambda item: True), list
        )

    def test_boe_miteco(self):
        self.assertIsInstance(
            self._correr(boe_module, boe_module.fetch_boe, NavegadorVacio()), list
        )

    def test_boa_aragon(self):
        self.assertIsInstance(
            self._correr(boa_module, boa_module.fetch_boa, NavegadorVacio()), list
        )

    def test_idae(self):
        self.assertIsInstance(
            self._correr(idae_module, idae_module.fetch_idae, NavegadorVacio()), list
        )

    def test_idae_catalog(self):
        self.assertIsInstance(
            self._correr(idae_module, idae_module.fetch_idae_catalog, NavegadorVacio()),
            list,
        )

    def test_cdti(self):
        self.assertIsInstance(
            self._correr(cdti_module, cdti_module.fetch_cdti, NavegadorVacio()), list
        )

    def test_the_smoke_test_would_have_caught_the_real_case(self):
        """Sin esta comprobación, el detector podría no detectar nada.

        El caso real: el conector ECCP llamaba a `statistics.median()` sin que
        `statistics` estuviera importado tras una extracción. Se simula
        quitando el nombre del módulo y comprobando que el humo se ve.
        """
        with mock.patch.object(eccp_module, "_parse_eccp_inventory_html",
                               side_effect=NameError("name 'statistics' is not defined")):
            with self.assertRaises(NameError):
                self._correr(eccp_module, eccp_module.fetch_eccp, lambda item: True)


if __name__ == "__main__":
    unittest.main()
