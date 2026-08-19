# Pruebas de grant_radar/sources/idae.py con import estándar (sin runpy).
#
# tests/test_grant_radar.py ya cubre el inventario y las fechas partidas en dos
# frases. Aquí se prueban los helpers del catálogo y de documentos oficiales,
# que hasta ahora solo se ejercitaban indirectamente.

import unittest

from bs4 import BeautifulSoup

from grant_radar.sources.idae import (
    _idae_catalog_document_rank,
    _idae_catalog_scope,
    _idae_official_document_links,
)


class CatalogScopeTests(unittest.TestCase):
    def test_recognises_the_three_scopes_regardless_of_accents_and_case(self):
        casos = {
            "ESTATAL/ Estatal": "Estatal",
            "Autonómico/ Aragón": "Autonómico / Aragón",
            "LOCAL/ zaragoza": "Local / Zaragoza",
        }
        for cabecera, esperado in casos.items():
            with self.subTest(cabecera=cabecera):
                self.assertEqual(_idae_catalog_scope(cabecera), esperado)

    def test_an_unknown_scope_returns_empty_instead_of_guessing(self):
        self.assertEqual(_idae_catalog_scope("Autonómico/ Cataluña"), "")
        self.assertEqual(_idae_catalog_scope(""), "")


class CatalogDocumentRankTests(unittest.TestCase):
    def test_an_extract_outranks_the_regulatory_bases(self):
        extracto = {"title": "Extracto de la convocatoria", "publication_date": "2026-01-01"}
        bases = {"title": "Bases reguladoras del programa", "publication_date": "2026-01-01"}
        self.assertGreater(
            _idae_catalog_document_rank(extracto), _idae_catalog_document_rank(bases)
        )

    def test_an_amendment_and_an_erratum_rank_below_the_call_itself(self):
        convocatoria = {"title": "Extracto de la convocatoria", "publication_date": ""}
        for titulo in ("Modificación de la convocatoria", "Corrección de errores"):
            with self.subTest(titulo=titulo):
                self.assertLess(
                    _idae_catalog_document_rank({"title": titulo, "publication_date": ""}),
                    _idae_catalog_document_rank(convocatoria),
                )

    def test_an_erratum_ranks_below_an_unrelated_document(self):
        neutro = {"title": "Resolución del programa", "publication_date": ""}
        erratum = {"title": "Corrección de errores", "publication_date": ""}
        self.assertLess(
            _idae_catalog_document_rank(erratum), _idae_catalog_document_rank(neutro)
        )

    def test_an_amendment_that_names_the_call_still_beats_an_unrelated_document(self):
        # "Modificación de la convocatoria" suma por nombrar la convocatoria
        # (+4) y resta por ser una modificación (-2): queda por encima de un
        # documento neutro. Es coherente —habla de la convocatoria— y en
        # cualquier caso pierde frente al extracto real, que es lo que importa.
        modificacion = {"title": "Modificación de la convocatoria", "publication_date": ""}
        neutro = {"title": "Resolución del programa", "publication_date": ""}
        self.assertGreater(
            _idae_catalog_document_rank(modificacion), _idae_catalog_document_rank(neutro)
        )

    def test_with_equal_score_the_newer_publication_wins(self):
        viejo = {"title": "Extracto", "publication_date": "2025-01-01"}
        nuevo = {"title": "Extracto", "publication_date": "2026-01-01"}
        self.assertGreater(
            _idae_catalog_document_rank(nuevo), _idae_catalog_document_rank(viejo)
        )


class OfficialDocumentLinksTests(unittest.TestCase):
    def _links(self, html):
        return _idae_official_document_links(
            BeautifulSoup(html, "html.parser"),
            "https://www.idae.es/ayudas-y-financiacion/programa-x",
        )

    def test_keeps_pdfs_official_hosts_and_titles_that_name_a_document(self):
        html = """
        <a href="https://www.idae.es/files/bases.pdf">Documento</a>
        <a href="https://www.boe.es/diario_boe/txt.php?id=BOE-B-2026-1">Extracto en BOE</a>
        <a href="https://ejemplo.test/x">Bases reguladoras</a>
        """
        urls = [d["url"] for d in self._links(html)]
        self.assertEqual(len(urls), 3, urls)
        self.assertIn("https://www.idae.es/files/bases.pdf", urls)

    def test_drops_unrelated_links_and_insecure_urls(self):
        html = """
        <a href="https://www.idae.es/contacto">Contacto</a>
        <a href="http://www.boe.es/inseguro">Extracto por http</a>
        <a href="https://localhost/bases.pdf">Bases en local</a>
        """
        self.assertEqual(self._links(html), [])

    def test_assigns_a_document_role_and_does_not_repeat_a_url(self):
        html = """
        <a href="https://www.idae.es/files/extracto.pdf">Extracto de la convocatoria</a>
        <a href="https://www.idae.es/files/extracto.pdf">Extracto de la convocatoria</a>
        """
        documentos = self._links(html)
        self.assertEqual(len(documentos), 1)
        self.assertEqual(documentos[0]["document_role"], "call_extract")
        self.assertEqual(documentos[0]["source"], "IDAE")


if __name__ == "__main__":
    unittest.main()
