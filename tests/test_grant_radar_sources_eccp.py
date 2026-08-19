# Pruebas de grant_radar/sources/eccp.py con import estándar (sin runpy).
#
# El foco está en la costura nueva de este módulo: `is_relevant_enough` se
# recibe como parámetro para que el conector no conozca las reglas de negocio
# (ver AGENTS.md sección 35). Estas pruebas usan predicados de mentira, así que
# ejercitan el rastreo sin depender de la matriz previa a Claude.

import unittest
from unittest import mock

from grant_radar.sources.eccp import _choose_eccp_depth, _crawl_project_domain


def _acepta_todo(conv):
    return {"decision": "retain"}


def _rechaza_todo(conv):
    return {"decision": "reject"}


def _respuesta(html, content_type="text/html; charset=utf-8"):
    response = mock.Mock()
    response.text = html
    response.content = html.encode("utf-8")
    response.headers = {"content-type": content_type}
    return response


class InjectedRelevanceTests(unittest.TestCase):
    """El predicado inyectado decide qué páginas se conservan."""

    PAGINA = (
        "<html><head><title>Open call for SMEs</title></head>"
        "<body>Cascade funding open call. Apply before 30/11/2026.</body></html>"
    )

    def _rastrea(self, predicado):
        with mock.patch("grant_radar.sources.eccp._robots_allows", return_value=True), \
             mock.patch("grant_radar.sources.eccp._http_get",
                        return_value=_respuesta(self.PAGINA)):
            return _crawl_project_domain(
                "https://proyecto.test/call", 1, mock.Mock(), predicado,
            )

    def test_a_permissive_predicate_keeps_the_page_as_a_call_document(self):
        resultado = self._rastrea(_acepta_todo)
        self.assertEqual(len(resultado["documents"]), 1)
        self.assertEqual(
            resultado["documents"][0]["document_role"], "beneficiary_project_call"
        )

    def test_a_rejecting_predicate_discards_it_and_counts_it_as_noise(self):
        resultado = self._rastrea(_rechaza_todo)
        self.assertEqual(resultado["documents"], [])
        self.assertEqual(resultado["irrelevant"], 1)

    def test_the_predicate_receives_the_page_title_and_text(self):
        visto = []

        def espia(conv):
            visto.append(conv)
            return {"decision": "retain"}

        self._rastrea(espia)
        self.assertEqual(visto[0]["title"], "Open call for SMEs")
        self.assertIn("Cascade funding", visto[0]["description"])

    def test_robots_disallow_stops_the_crawl_before_any_request(self):
        with mock.patch("grant_radar.sources.eccp._robots_allows", return_value=False), \
             mock.patch("grant_radar.sources.eccp._http_get") as http_get:
            resultado = _crawl_project_domain(
                "https://proyecto.test/call", 1, mock.Mock(), _acepta_todo,
            )
        http_get.assert_not_called()
        self.assertEqual(resultado["documents"], [])
        self.assertEqual(resultado["errors"], 1)

    def test_a_non_html_document_is_kept_by_its_url_without_the_predicate(self):
        # Un PDF con "call" en la ruta entra por señal de URL: no hay texto que
        # pasar al predicado, así que este no debe llegar a invocarse.
        predicado = mock.Mock(side_effect=AssertionError("no debe consultarse"))
        with mock.patch("grant_radar.sources.eccp._robots_allows", return_value=True), \
             mock.patch("grant_radar.sources.eccp._http_get",
                        return_value=_respuesta("%PDF-1.4", "application/pdf")):
            resultado = _crawl_project_domain(
                "https://proyecto.test/open-call.pdf", 1, mock.Mock(), predicado,
            )
        self.assertEqual(len(resultado["documents"]), 1)


class CrawlDepthTests(unittest.TestCase):
    """La profundidad se elige midiendo, no por configuración fija."""

    def test_depth_stops_when_requests_double_without_enough_gain(self):
        metrics = [
            {"depth": 0, "critical_fields": 20, "requests": 6, "irrelevant": 0},
            {"depth": 1, "critical_fields": 30, "requests": 6, "irrelevant": 0,
             "unique_call_gain_pct": 20, "median_requests_per_call": 1},
            {"depth": 2, "critical_fields": 31, "requests": 22, "irrelevant": 0,
             "unique_call_gain_pct": 3, "median_requests_per_call": 4},
        ]
        self.assertEqual(_choose_eccp_depth(metrics), 1)

    def test_too_much_noise_stops_the_experiment(self):
        metrics = [
            {"depth": 0, "critical_fields": 20, "requests": 6, "irrelevant": 0},
            {"depth": 1, "critical_fields": 40, "requests": 10, "irrelevant": 6,
             "unique_call_gain_pct": 50, "median_requests_per_call": 1},
        ]
        self.assertEqual(_choose_eccp_depth(metrics), 0)

    def test_no_metrics_means_no_crawling(self):
        self.assertEqual(_choose_eccp_depth([]), 0)


if __name__ == "__main__":
    unittest.main()
