# Pruebas de grant_radar/http_client.py con import estándar (sin runpy).

import unittest
from unittest import mock

import requests

from grant_radar.http_client import (
    HTTP_USER_AGENT,
    _http_get,
    _is_safe_public_https_url,
)


def _response(status_code=200, headers=None, content=b"", chunks=None):
    response = mock.Mock(spec=requests.Response)
    response.status_code = status_code
    response.headers = headers or {}
    response.content = content
    response.iter_content.return_value = chunks or [content]
    response.raise_for_status.return_value = None
    return response


class HttpGetTests(unittest.TestCase):
    def test_sends_the_project_user_agent(self):
        session = mock.Mock()
        session.get.return_value = _response()
        _http_get("https://example.test/a", session=session)
        headers = session.get.call_args.kwargs["headers"]
        self.assertEqual(headers["User-Agent"], HTTP_USER_AGENT)

    def test_extra_headers_override_the_defaults(self):
        session = mock.Mock()
        session.get.return_value = _response()
        _http_get("https://example.test/a", session=session, headers={"Accept-Language": "en"})
        self.assertEqual(session.get.call_args.kwargs["headers"]["Accept-Language"], "en")

    def test_retries_on_server_error_and_then_gives_up_returning_none(self):
        session = mock.Mock()
        session.get.return_value = _response(status_code=503)
        with mock.patch("grant_radar.http_client.time.sleep"):
            result = _http_get("https://example.test/a", session=session, retries=3)
        self.assertIsNone(result)
        self.assertEqual(session.get.call_count, 3)

    def test_a_429_is_retried_like_a_server_error(self):
        session = mock.Mock()
        session.get.side_effect = [_response(status_code=429), _response(status_code=200)]
        with mock.patch("grant_radar.http_client.time.sleep"):
            result = _http_get("https://example.test/a", session=session, retries=3)
        self.assertIsNotNone(result)
        self.assertEqual(session.get.call_count, 2)

    def test_skips_the_download_when_content_length_exceeds_the_limit(self):
        session = mock.Mock()
        session.get.return_value = _response(headers={"content-length": "999"})
        self.assertIsNone(
            _http_get("https://example.test/big.pdf", session=session, max_bytes=100)
        )

    def test_stops_streaming_when_the_body_exceeds_the_limit(self):
        session = mock.Mock()
        session.get.return_value = _response(chunks=[b"x" * 80, b"x" * 80])
        self.assertIsNone(
            _http_get("https://example.test/big.pdf", session=session, max_bytes=100)
        )

    def test_a_body_within_the_limit_is_returned_whole(self):
        session = mock.Mock()
        session.get.return_value = _response(chunks=[b"ab", b"cd"])
        result = _http_get("https://example.test/ok.pdf", session=session, max_bytes=100)
        self.assertIsNotNone(result)
        self.assertEqual(result._content, b"abcd")


class SafePublicHttpsUrlTests(unittest.TestCase):
    def test_accepts_a_public_https_url(self):
        self.assertTrue(_is_safe_public_https_url("https://www.infosubvenciones.es/x.pdf"))

    def test_rejects_plain_http(self):
        self.assertFalse(_is_safe_public_https_url("http://www.infosubvenciones.es/x.pdf"))

    def test_rejects_localhost_and_local_domains(self):
        self.assertFalse(_is_safe_public_https_url("https://localhost/x"))
        self.assertFalse(_is_safe_public_https_url("https://impresora.local/x"))

    def test_rejects_private_and_loopback_addresses(self):
        for host in ("127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254"):
            with self.subTest(host=host):
                self.assertFalse(_is_safe_public_https_url(f"https://{host}/x"))

    def test_accepts_a_global_literal_address(self):
        self.assertTrue(_is_safe_public_https_url("https://8.8.8.8/x"))

    def test_rejects_empty_or_malformed_values(self):
        for value in ("", "   ", "not-a-url", "https://"):
            with self.subTest(value=value):
                self.assertFalse(_is_safe_public_https_url(value))


if __name__ == "__main__":
    unittest.main()
