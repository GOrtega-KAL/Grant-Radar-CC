# -*- coding: utf-8 -*-
# Pruebas de grant_radar/sources/cdti.py con import estándar (sin runpy).
#
# El foco está en la comprobación de las URLs del catálogo curado. Nace de un
# caso real (AGENTS.md, sección 44): seis de las diez fichas del catálogo
# apuntaban a rutas que ya no existen, y el usuario lo detectó antes que el
# programa porque `verificar_urls()` no podía verlo — cdti.es responde 200 a
# cualquier ruta cuando quien pregunta no parece un navegador.

import unittest
from unittest import mock

from grant_radar.audit import DISCOVERY_AUDIT
from grant_radar.sources.cdti import (
    CDTI_DEAD_URL_STATUSES,
    _attach_catalog_official_documents,
    _catalog_programme_document,
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

    def html(self, url: str, wait_selector: str = "body"):
        self.consultas.append(("html", url))
        return getattr(self, "paginas", {}).get(url, "")


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


FICHA_CON_BASES = """
<html><head><title>Proyectos de I+D | CDTI</title></head><body><main>
  <div class="ficha-field-wrapper">
    <div class="ficha-label">Estado de la convocatoria</div>
    <div class="text">Abierta</div>
  </div>
  <p>Ayudas para proyectos de investigacion y desarrollo.</p>
  <a href="https://www.cdti.es/sites/default/files/faq.pdf">FAQ Empresas en crisis</a>
  <a href="https://www.cdti.es/sites/default/files/bases-pid.pdf">Proyectos de I+D</a>
  <a href="https://www.cdti.es/contacto">Contacto</a>
</main></body></html>
"""


class CatalogDocumentsTests(unittest.TestCase):
    """Las fichas de ventanilla abierta llegaban sin una sola base oficial.

    Por eso salían con la elegibilidad «por confirmar»: 300 caracteres
    tecleados a mano y ningún documento que dijera quién puede solicitar
    (AGENTS.md 51.2). El calendario sí adjuntaba las suyas.
    """

    def setUp(self):
        # La descarga real de los documentos la prueba documents.py; aquí
        # interesa que la ficha se lea y el rastro se construya, sin red.
        parche = mock.patch(
            "grant_radar.sources.cdti.enrich_with_official_documents",
            side_effect=lambda call, documents, source: call,
        )
        self.enriquecer = parche.start()
        self.addCleanup(parche.stop)

    def test_the_official_documents_reach_the_curated_entry(self):
        navegador = NavegadorFalso({})
        navegador.paginas = {"https://www.cdti.es/ayudas/pid": FICHA_CON_BASES}
        entradas = _attach_catalog_official_documents(
            navegador,
            [_entrada("Proyectos de I+D — Línea PID", "https://www.cdti.es/ayudas/pid")],
        )
        rastro = entradas[0].get("related_documents_trace") or []
        urls = [d["url"] for d in rastro]
        self.assertIn("https://www.cdti.es/sites/default/files/bases-pid.pdf", urls)
        # El genérico de la página no viaja: solo el documento del programa.
        self.assertNotIn("https://www.cdti.es/sites/default/files/faq.pdf", urls)
        self.assertEqual(entradas[0]["related_documents_count"], len(rastro))
        self.assertEqual(self.enriquecer.call_count, 1)

    def test_a_page_without_documents_is_left_as_it_was(self):
        navegador = NavegadorFalso({})
        navegador.paginas = {"https://www.cdti.es/ayudas/x": "<html><main>Sin nada</main></html>"}
        original = _entrada("Sin documentos", "https://www.cdti.es/ayudas/x")
        entradas = _attach_catalog_official_documents(navegador, [original])
        self.assertEqual(entradas, [original])

    def test_a_programme_page_is_not_visited(self):
        """Una página de programa lista PDF de varias convocatorias."""
        navegador = NavegadorFalso({})
        entrada = _entrada(
            "Programa", "https://www.cdti.es/programas-de-cooperacion-tecnologica-pcti"
        )
        entradas = _attach_catalog_official_documents(navegador, [entrada])
        self.assertEqual(entradas, [entrada])
        self.assertEqual(navegador.consultas, [])

    def test_a_stale_generic_flag_does_not_block_a_real_ficha(self):
        """Las tres fichas corregidas el 21/08 seguían marcadas «genéricas».

        Decidir por esa marca dejaba la mejora sin efecto justo en las cuatro
        convocatorias que la necesitaban. Decide la ruta, que es comprobable.
        """
        navegador = NavegadorFalso({})
        navegador.paginas = {"https://www.cdti.es/ayudas/pid": FICHA_CON_BASES}
        entrada = {**_entrada("Proyectos de I+D — Línea PID", "https://www.cdti.es/ayudas/pid"),
                   "url_generica": True}
        entradas = _attach_catalog_official_documents(navegador, [entrada])
        self.assertTrue(entradas[0].get("related_documents_trace"))

    def test_a_browser_failure_never_loses_the_entry(self):
        class NavegadorRoto(NavegadorFalso):
            def html(self, url: str, wait_selector: str = "body"):
                raise RuntimeError("Chromium caído")

        original = _entrada("Con fallo", "https://www.cdti.es/ayudas/pid")
        entradas = _attach_catalog_official_documents(NavegadorRoto({}), [original])
        self.assertEqual(entradas, [original])

    def test_an_empty_catalog_needs_no_browser(self):
        navegador = NavegadorFalso({})
        self.assertEqual(_attach_catalog_official_documents(navegador, []), [])
        self.assertEqual(navegador.consultas, [])


class ProgrammeDocumentTests(unittest.TestCase):
    """Cuál de los PDF de una ficha es el que describe el programa.

    Medido sobre las páginas reales: cada ficha enlaza su documento y dos
    genéricos que salen en todas. La primera versión se los pasaba todos y no
    llegaba ni una línea de texto al modelo, porque
    `enrich_with_official_documents()` solo descarga bases y convocatorias
    (AGENTS.md 51.2).
    """

    RUIDO = [
        {"title": "FAQ Empresas en crisis", "url": "https://www.cdti.es/f/faq.pdf"},
        {"title": "Medidas de exención y minoración de garantías para PYMES",
         "url": "https://www.cdti.es/f/garantias.pdf"},
    ]

    def test_the_programme_document_is_recognised_by_its_title(self):
        documentos = _catalog_programme_document(
            "Proyectos Transferencia Tecnológica Cervera (ventanilla abierta)",
            [*self.RUIDO,
             {"title": "Proyectos de I+D de Transferencia Tecnológica Cervera",
              "url": "https://www.cdti.es/f/cervera.pdf"}],
        )
        self.assertEqual(len(documentos), 1)
        self.assertIn("Cervera", documentos[0]["title"])

    def test_it_is_relabelled_so_it_actually_gets_downloaded(self):
        documentos = _catalog_programme_document(
            "Proyectos de I+D — Línea PID (ventanilla abierta)",
            [{"title": "Proyectos de I+D", "url": "https://www.cdti.es/f/pid.pdf"}],
        )
        self.assertEqual(documentos[0]["document_role"], "regulatory_bases")

    def test_the_generic_documents_alone_are_not_taken(self):
        self.assertEqual(
            _catalog_programme_document("Infraestructuras de Ensayo", self.RUIDO), []
        )

    def test_words_that_appear_in_every_title_do_not_count(self):
        """«Línea», «ayudas» o «CDTI» están en todas: no distinguen nada."""
        self.assertEqual(
            _catalog_programme_document(
                "Línea de ayudas CDTI",
                [{"title": "Línea de ayudas CDTI para otra cosa distinta",
                  "url": "https://www.cdti.es/f/otra.pdf"}],
            ),
            [],
        )

    def test_no_documents_is_an_empty_answer(self):
        self.assertEqual(_catalog_programme_document("Cualquier cosa", []), [])


if __name__ == "__main__":
    unittest.main()
