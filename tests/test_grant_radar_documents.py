# Pruebas de grant_radar/documents.py con import estándar (sin runpy).
#
# tests/test_grant_radar.py ya cubre enrich_with_official_documents() de punta
# a punta. Aquí se prueban por separado la extracción de texto y las dos
# funciones de identidad/prioridad, más la invariante de que la ruta de la
# caché sigue siendo la misma tras mover el módulo al paquete.

import os
import unittest
from unittest import mock

from grant_radar.documents import (
    SOURCE_DOCUMENT_CACHE_FILE,
    _hold_document_text,
    _official_document_priority,
    _source_document_cache_key,
)


def _response(content=b"", content_type="", encoding="utf-8", text=""):
    response = mock.Mock()
    response.content = content
    response.headers = {"content-type": content_type}
    response.encoding = encoding
    response.text = text
    return response


class CachePathTests(unittest.TestCase):
    def test_the_cache_path_is_the_project_data_directory(self):
        """La ruta se calcula en el módulo, no en el script.

        Si esta comprobación falla, el módulo y el script estarían leyendo y
        escribiendo cachés distintas sin que nada más avise.
        """
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assertEqual(
            os.path.abspath(SOURCE_DOCUMENT_CACHE_FILE),
            os.path.join(raiz, "grant_radar_data", "source_document_cache.json"),
        )


class HoldDocumentTextTests(unittest.TestCase):
    def test_extracts_the_main_content_of_an_html_document(self):
        html = (
            b"<html><head><style>p{color:red}</style></head>"
            b"<body><script>var x=1</script>"
            b"<main>  Bases   reguladoras de la ayuda  </main></body></html>"
        )
        texto, formato = _hold_document_text(
            _response(content=html, content_type="text/html"), "https://x.test/a"
        )
        self.assertEqual(formato, "html")
        self.assertEqual(texto, "Bases reguladoras de la ayuda")

    def test_html_is_detected_by_content_even_without_a_content_type(self):
        html = b"<html><body><main>Convocatoria</main></body></html>"
        _, formato = _hold_document_text(_response(content=html), "https://x.test/a")
        self.assertEqual(formato, "html")

    def test_a_corrupt_pdf_reports_the_error_instead_of_raising(self):
        texto, formato = _hold_document_text(
            _response(content=b"%PDF-1.4 roto", content_type="application/pdf"),
            "https://x.test/roto.pdf",
        )
        self.assertEqual((texto, formato), ("", "pdf_error"))

    def test_plain_text_is_normalised(self):
        texto, formato = _hold_document_text(
            _response(content=b"x", content_type="text/plain", text="  hola   mundo "),
            "https://x.test/a.txt",
        )
        self.assertEqual((texto, formato), ("hola mundo", "text"))

    def test_an_unsupported_type_yields_no_text_and_says_so(self):
        self.assertEqual(
            _hold_document_text(
                _response(content=b"\x00\x01", content_type="image/png"),
                "https://x.test/a.png",
            ),
            ("", "unsupported"),
        )

    def test_the_byte_limit_is_applied_before_parsing(self):
        # Un documento enorme no debe llegar entero al parser.
        grande = b"<html><body><main>" + b"a" * 10_000 + b"</main></body></html>"
        texto, _ = _hold_document_text(
            _response(content=grande, content_type="text/html"),
            "https://x.test/grande.html",
            max_bytes=100,
        )
        self.assertLess(len(texto), 200)


class CacheKeyTests(unittest.TestCase):
    def test_the_fragment_does_not_change_the_identity(self):
        base = {"url": "https://x.test/bases.pdf"}
        con_ancla = {"url": "https://x.test/bases.pdf#pagina-3"}
        self.assertEqual(
            _source_document_cache_key("CDTI", base),
            _source_document_cache_key("CDTI", con_ancla),
        )

    def test_a_different_source_is_a_different_entry(self):
        documento = {"url": "https://x.test/bases.pdf"}
        self.assertNotEqual(
            _source_document_cache_key("CDTI", documento),
            _source_document_cache_key("IDAE", documento),
        )


class DocumentPriorityTests(unittest.TestCase):
    def test_the_call_and_its_extract_outrank_the_regulatory_bases(self):
        convocatoria = {"title": "Se convoca la ayuda"}
        extracto = {"title": "Extracto de la convocatoria"}
        bases = {"document_role": "regulatory_bases", "title": "Bases"}
        self.assertGreater(_official_document_priority(convocatoria),
                           _official_document_priority(bases))
        self.assertGreater(_official_document_priority(extracto),
                           _official_document_priority(bases))

    def test_an_unclassified_document_ranks_last(self):
        self.assertEqual(_official_document_priority({"title": "Nota"})[0], 0)


if __name__ == "__main__":
    unittest.main()
