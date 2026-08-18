# Pruebas de grant_radar/sources/boa_aragon.py con import estándar (sin
# runpy). Primer conector de fuente extraído a paquete propio (ver
# AGENTS.md, sección 25); confirma que puede probarse de forma aislada,
# igual que parsing_helpers, tech_taxonomy, cache y deterministic_rules.

import unittest
from unittest import mock

from grant_radar.audit import DISCOVERY_AUDIT
from grant_radar.sources.boa_aragon import (
    _fetch_boa_playwright,
    _fetch_boa_static,
    fetch_boa,
)


class FakeBrowser:
    """Doble de PlaywrightBrowser: solo expone .html(url) -> str | None."""

    def __init__(self, pages: dict):
        self._pages = pages

    def html(self, url):
        return self._pages.get(url)


class StaticCatalogTests(unittest.TestCase):
    def setUp(self):
        DISCOVERY_AUDIT.clear()

    def test_discards_entries_past_their_deadline(self):
        # El catálogo estático tiene fechas fijas en el código; en vez de
        # depender de qué día se ejecute el test, se fija _days_until para
        # que una de las dos entradas quede "abierta" y la otra "cerrada",
        # que es la rama de comportamiento que este test cubre.
        with mock.patch(
            "grant_radar.sources.boa_aragon._days_until",
            side_effect=lambda date_str: 30 if date_str == "2026-05-05" else 0,
        ):
            results = _fetch_boa_static()

        self.assertEqual(len(results), 1, {"audit": DISCOVERY_AUDIT})
        self.assertEqual(results[0]["deadline_date"], "2026-05-05")
        self.assertEqual(results[0]["source"], "BOA ARAGÓN")
        self.assertTrue(
            any(entry["reason"] == "deadline_closed" for entry in DISCOVERY_AUDIT)
        )


class PlaywrightParsingTests(unittest.TestCase):
    def setUp(self):
        DISCOVERY_AUDIT.clear()

    def test_extracts_an_active_relevant_call_and_skips_the_rest(self):
        boa_page = """
        <div>
          <a href="/tramite/ayudas-eficiencia-industrial">Ayudas a la eficiencia
          energetica en procesos industriales de fabricacion metalica</a>
          <p>En plazo. Convocatoria abierta desde el 01/01/2099 al 30/11/2099.</p>
        </div>
        <div>
          <a href="/tramite/ayudas-regadio">Ayudas al regadio y modernizacion agraria
          en explotaciones agropecuarias de Aragon</a>
          <p>En plazo. Desde el 01/01/2099 al 30/11/2099.</p>
        </div>
        <div>
          <a href="/tramite/cerrada">Programa industrial de eficiencia energetica ya
          fuera de plazo para empresas de Aragon</a>
          <p>Convocatoria fuera de plazo. Cerrada desde el 01/01/2020.</p>
        </div>
        """
        pages = {
            "https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI?CMD=VERDOC&BASE=BODA&DOCS=1-40&SEPARADOR=&&RANG-C=20250101-&TEXT-TEXT=eficiencia+energetica+industria": boa_page,
        }
        results = _fetch_boa_playwright(FakeBrowser(pages))

        self.assertEqual(len(results), 1, {"audit": DISCOVERY_AUDIT, "results": results})
        result = results[0]
        self.assertTrue(result["title"].startswith("Ayudas a la eficiencia"))
        self.assertEqual(result["open_date"], "2099-01-01")
        self.assertEqual(result["deadline_date"], "2099-11-30")
        self.assertEqual(result["source"], "BOA ARAGÓN")
        self.assertEqual(
            result["url"],
            "https://www.boa.aragon.es/tramite/ayudas-eficiencia-industrial",
        )

    def test_returns_nothing_when_no_target_page_is_reachable(self):
        self.assertEqual(_fetch_boa_playwright(FakeBrowser({})), [])


class FetchBoaFallbackTests(unittest.TestCase):
    def setUp(self):
        DISCOVERY_AUDIT.clear()

    def test_falls_back_to_the_static_catalog_when_live_navigation_finds_nothing(self):
        results = fetch_boa(FakeBrowser({}))
        # No se fija aquí la fecha del sistema: solo se comprueba que, sin
        # resultados en vivo, cae al catálogo estático (misma función que
        # StaticCatalogTests prueba a fondo), no al catálogo de otra fuente.
        self.assertEqual(results, _fetch_boa_static())


if __name__ == "__main__":
    unittest.main()
