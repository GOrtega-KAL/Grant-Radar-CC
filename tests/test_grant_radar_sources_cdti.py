# -*- coding: utf-8 -*-
# Pruebas de grant_radar/sources/cdti.py con import estándar (sin runpy).
#
# El foco está en la comprobación de las URLs del catálogo curado. Nace de un
# caso real (AGENTS.md, sección 44): seis de las diez fichas del catálogo
# apuntaban a rutas que ya no existen, y el usuario lo detectó antes que el
# programa porque `verificar_urls()` no podía verlo — cdti.es responde 200 a
# cualquier ruta cuando quien pregunta no parece un navegador.

import unittest

from grant_radar.audit import DISCOVERY_AUDIT
from grant_radar.sources.cdti import (
    CDTI_DEAD_URL_STATUSES,
    _drop_catalog_entries_with_dead_urls,
)


class NavegadorFalso:
    """Devuelve el estado que se le indique, y cuenta cuántas veces se le pide."""

    def __init__(self, estados: dict):
        self.estados = estados
        self.consultas = []

    def status(self, url: str):
        self.consultas.append(url)
        return self.estados.get(url)


def _entrada(titulo: str, url: str) -> dict:
    return {"source": "CDTI", "title": titulo, "url": url, "description": ""}


class CatalogUrlCheckTests(unittest.TestCase):
    def test_a_404_entry_is_dropped_and_reported(self):
        curated = [
            _entrada("Viva", "https://www.cdti.es/ayudas/proyectos-de-i-d"),
            _entrada("Muerta", "https://www.cdti.es/ayudas/proyectos-bilaterales"),
        ]
        navegador = NavegadorFalso({
            "https://www.cdti.es/ayudas/proyectos-de-i-d": 200,
            "https://www.cdti.es/ayudas/proyectos-bilaterales": 404,
        })
        vivas, caidas = _drop_catalog_entries_with_dead_urls(navegador, curated)
        self.assertEqual([e["title"] for e in vivas], ["Viva"])
        self.assertEqual(len(caidas), 1)
        self.assertEqual(caidas[0]["status"], 404)
        self.assertEqual(caidas[0]["title"], "Muerta")

    def test_410_counts_as_dead_too(self):
        curated = [_entrada("Retirada", "https://www.cdti.es/ayudas/x")]
        navegador = NavegadorFalso({"https://www.cdti.es/ayudas/x": 410})
        vivas, caidas = _drop_catalog_entries_with_dead_urls(navegador, curated)
        self.assertEqual(vivas, [])
        self.assertEqual(len(caidas), 1)

    def test_an_unreachable_url_is_kept(self):
        """Un bloqueo de WAF o un fallo de red no vacía el catálogo curado."""
        curated = [
            _entrada("Bloqueada", "https://www.cdti.es/ayudas/a"),
            _entrada("Servidor caído", "https://www.cdti.es/ayudas/b"),
        ]
        navegador = NavegadorFalso({
            "https://www.cdti.es/ayudas/a": None,   # no concluyente
            "https://www.cdti.es/ayudas/b": 503,
        })
        vivas, caidas = _drop_catalog_entries_with_dead_urls(navegador, curated)
        self.assertEqual(len(vivas), 2)
        self.assertEqual(caidas, [])

    def test_the_same_url_is_only_checked_once(self):
        url = "https://www.cdti.es/ayudas/repetida"
        curated = [_entrada("Una", url), _entrada("Otra", url)]
        navegador = NavegadorFalso({url: 200})
        _drop_catalog_entries_with_dead_urls(navegador, curated)
        self.assertEqual(navegador.consultas, [url])

    def test_an_empty_catalog_needs_no_browser(self):
        navegador = NavegadorFalso({})
        vivas, caidas = _drop_catalog_entries_with_dead_urls(navegador, [])
        self.assertEqual((vivas, caidas), ([], []))
        self.assertEqual(navegador.consultas, [])

    def test_a_dropped_entry_leaves_a_trace_in_the_audit(self):
        antes = len(DISCOVERY_AUDIT)
        curated = [_entrada("Muerta", "https://www.cdti.es/ayudas/fantasma")]
        navegador = NavegadorFalso({"https://www.cdti.es/ayudas/fantasma": 404})
        _drop_catalog_entries_with_dead_urls(navegador, curated)
        self.assertGreater(len(DISCOVERY_AUDIT), antes)

    def test_only_definitive_codes_count_as_dead(self):
        self.assertIn(404, CDTI_DEAD_URL_STATUSES)
        self.assertIn(410, CDTI_DEAD_URL_STATUSES)
        self.assertNotIn(403, CDTI_DEAD_URL_STATUSES)
        self.assertNotIn(500, CDTI_DEAD_URL_STATUSES)


if __name__ == "__main__":
    unittest.main()
