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
    BDNS_HOLD_MAX_EVIDENCE_CHARS,
    SOURCE_DOCUMENT_CACHE_FILE,
    _hold_document_text,
    _html_to_text,
    _official_document_priority,
    _source_document_cache_key,
    browser_document_text,
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


class BrowserDocumentFallbackTests(unittest.TestCase):
    """El segundo intento para un origen con la cadena de certificados rota.

    `boletin.dpz.es` —el Boletín Oficial de la provincia de la propia empresa—
    era el único host que fallaba de toda la recopilación: sirve **un solo
    certificado**, sin el intermedio, y OpenSSL no lo verifica. Chromium sí,
    porque va a buscar el que falta. Medido el 02/09/2026 con
    `ignore_https_errors` a `False` **y** a `True`: HTTP 200 en los dos casos.

    Que funcione con `False` es todo el argumento. Si solo funcionara con
    `True`, esto sería relajar TLS con otro nombre y no debería existir.
    """

    class NavegadorFalso:
        def __init__(self, estado=200, html="", explota=False):
            self.estado = estado
            self._html = html
            self.explota = explota
            self.visitas = []

        def status(self, url):
            self.visitas.append(("status", url))
            if self.explota:
                raise RuntimeError("Chromium caído")
            return self.estado

        def html(self, url):
            self.visitas.append(("html", url))
            return self._html

    def test_a_reachable_document_is_recovered(self):
        navegador = self.NavegadorFalso(
            html="<html><body><main>Extracto del acuerdo de la Junta de Gobierno. "
                 "Beneficiarios: pequeñas y medianas empresas industriales.</main></body></html>"
        )
        texto = browser_document_text(navegador, "https://boletin.dpz.es/x", 5_000)
        self.assertIn("Junta de Gobierno", texto)
        self.assertNotIn("<", texto, "debe salir texto, no marcado")

    def test_a_404_is_not_taken_as_evidence(self):
        """`html()` devuelve algo tanto en un 404 como en un bloqueo de WAF.

        Sin comprobar el código antes, la página de error de un portal
        entraría en la evidencia oficial como si fuera el documento.
        """
        navegador = self.NavegadorFalso(
            estado=404,
            html="<html><body>La página solicitada no existe en este portal oficial.</body></html>",
        )
        self.assertEqual(browser_document_text(navegador, "https://boletin.dpz.es/x", 5_000), "")
        self.assertEqual([tipo for tipo, _ in navegador.visitas], ["status"])

    def test_a_broken_browser_degrades_instead_of_raising(self):
        navegador = self.NavegadorFalso(explota=True)
        self.assertEqual(browser_document_text(navegador, "https://boletin.dpz.es/x", 5_000), "")

    def test_without_a_fallback_nothing_changes(self):
        self.assertEqual(browser_document_text(None, "https://boletin.dpz.es/x", 5_000), "")

    def test_both_routes_extract_the_same_text(self):
        """El motivo de que `_html_to_text()` se separara.

        Un mismo documento no puede dar textos distintos según entre por
        `requests` o por el navegador: la evidencia dejaría de ser comparable
        y la caché documental guardaría una cosa u otra según el día.
        """
        html = ("<html><head><title>t</title><script>var a=1;</script></head>"
                "<body><nav>menú</nav><main>Bases reguladoras de la convocatoria.</main></body></html>")

        class RespuestaFalsa:
            content = html.encode("utf-8")
            headers = {"content-type": "text/html; charset=utf-8"}
            encoding = "utf-8"
            text = html

        por_requests, formato = _hold_document_text(RespuestaFalsa(), "https://x.test/a")
        por_navegador = browser_document_text(
            self.NavegadorFalso(html=html), "https://x.test/a", BDNS_HOLD_MAX_EVIDENCE_CHARS
        )
        self.assertEqual(formato, "html")
        self.assertEqual(por_requests, por_navegador)
        self.assertIn("Bases reguladoras", por_requests)
        self.assertNotIn("var a=1", por_requests)


if __name__ == "__main__":
    unittest.main()
