# Pruebas de grant_radar/browser.py con import estándar (sin runpy).
#
# No arrancan Chromium: se sustituye `context` por un doble que devuelve
# páginas simuladas. Lo que se prueba es la lógica propia de la clase —cuándo
# devuelve "", cuándo marca un ámbito como bloqueado y cuándo deja de
# insistir—, no Playwright en sí.

import unittest
from unittest import mock

from grant_radar.browser import PlaywrightBrowser


class FakePage:
    def __init__(self, html="<html>ok</html>", title="", body_text="", status=200):
        self._html, self._title, self._body_text = html, title, body_text
        self.status = status
        self.closed = False

    def goto(self, url, **kwargs):
        return mock.Mock(status=self.status)

    def wait_for_selector(self, selector, **kwargs):
        return None

    def wait_for_load_state(self, state, **kwargs):
        return None

    def content(self):
        return self._html

    def title(self):
        return self._title

    def locator(self, selector):
        return mock.Mock(inner_text=mock.Mock(return_value=self._body_text))

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, *pages):
        self.pages = list(pages)
        self.served = []

    def new_page(self):
        page = self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]
        self.served.append(page)
        return page


def _browser(context):
    browser = PlaywrightBrowser()
    browser.context = context
    return browser


class HtmlTests(unittest.TestCase):
    def test_returns_empty_when_chromium_never_started(self):
        # __enter__ deja context a None si el arranque falla: cada fuente debe
        # poder caer a su respaldo en vez de romper la ejecución entera.
        self.assertEqual(PlaywrightBrowser().html("https://example.test"), "")

    def test_returns_the_rendered_html_and_always_closes_the_page(self):
        page = FakePage(html="<html>contenido</html>")
        browser = _browser(FakeContext(page))
        self.assertEqual(browser.html("https://example.test/a"), "<html>contenido</html>")
        self.assertTrue(page.closed)

    def test_an_http_error_yields_empty_without_raising(self):
        page = FakePage(status=503)
        self.assertEqual(_browser(FakeContext(page)).html("https://example.test/a"), "")
        self.assertTrue(page.closed)

    def test_a_waf_block_marks_the_host_and_skips_further_requests(self):
        bloqueada = FakePage(body_text="Access denied")
        siguiente = FakePage(html="<html>no debería pedirse</html>")
        context = FakeContext(bloqueada, siguiente)
        browser = _browser(context)

        self.assertEqual(browser.html("https://bloqueado.test/uno"), "")
        self.assertIn("bloqueado.test", browser._blocked_scopes)
        # La segunda petición al mismo host ni siquiera abre una página.
        self.assertEqual(browser.html("https://bloqueado.test/dos"), "")
        self.assertEqual(len(context.served), 1)

    def test_a_block_marker_in_the_page_title_also_counts(self):
        page = FakePage(title="Request Rejected")
        browser = _browser(FakeContext(page))
        self.assertEqual(browser.html("https://otro.test/x"), "")
        self.assertIn("otro.test", browser._blocked_scopes)

    def test_a_blocked_host_does_not_block_a_different_host(self):
        browser = _browser(FakeContext(FakePage(html="<html>libre</html>")))
        browser._blocked_scopes.add("bloqueado.test")
        self.assertEqual(browser.html("https://libre.test/x"), "<html>libre</html>")

    def test_idae_blocks_only_the_grant_details_scope(self):
        # IDAE responde con bloqueo en las fichas de detalle pero no en el
        # inventario: bloquear el host entero perdería la fuente completa.
        browser = _browser(FakeContext(FakePage(body_text="Access denied")))
        self.assertEqual(
            browser.html("https://www.idae.es/ayudas-y-financiacion/programa-x"), ""
        )
        self.assertEqual(browser._blocked_scopes, {"www.idae.es:grant-details"})

        libre = FakeContext(FakePage(html="<html>inventario</html>"))
        browser.context = libre
        self.assertEqual(
            browser.html("https://www.idae.es/ayudas-y-financiacion"),
            "<html>inventario</html>",
        )


if __name__ == "__main__":
    unittest.main()
