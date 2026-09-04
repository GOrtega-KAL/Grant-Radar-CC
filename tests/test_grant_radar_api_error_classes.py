# -*- coding: utf-8 -*-
# Pruebas de classify_api_error(): que repetir sirva o no.
#
# Escrito el 04/09/2026 despues de que un rechazo por saldo agotado tumbara una
# ejecucion de pago a mitad. La clasificacion anterior solo reconocia como
# transitorios `529`, `overloaded` y `rate`, con dos consecuencias:
#
#   - un 500 o una conexion cortada -que se arreglan repitiendo- abortaban la
#     ejecucion en el primer intento;
#   - un saldo agotado -que no se arregla nunca- abortaba sin decir por que, y
#     costo media hora de diagnostico sobre la auditoria.
#
# La funcion es pura, asi que cada familia se prueba sin red y sin gastar.

import unittest

from grant_radar.analysis import (
    AUTH_API_STATUS,
    CREDIT_API_STATUS,
    TRANSIENT_API_STATUS,
    classify_api_error,
)


class _ErrorFalso(Exception):
    """Un error de la API con su `status_code`, como los del SDK."""

    def __init__(self, mensaje, status_code=None):
        super().__init__(mensaje)
        self.status_code = status_code


class TransientErrorsAreRetriedTests(unittest.TestCase):
    """Los que se arreglan repitiendo. Antes solo se reconocian tres."""

    def test_the_three_that_were_already_recognised(self):
        for mensaje, estado in (
            ("overloaded_error", 529),
            ("rate_limit_error", 429),
            ("Overloaded", None),
        ):
            with self.subTest(mensaje=mensaje):
                self.assertEqual(classify_api_error(_ErrorFalso(mensaje, estado)),
                                 "transient")

    def test_server_errors_are_transient_and_used_not_to_be(self):
        """El hueco real: un 500 tumbaba una ejecucion entera."""
        for estado in (500, 502, 503, 504):
            with self.subTest(estado=estado):
                self.assertEqual(
                    classify_api_error(_ErrorFalso("Internal server error", estado)),
                    "transient",
                )

    def test_network_failures_are_transient(self):
        for mensaje in (
            "Connection reset by peer",
            "Request timed out",
            "read timeout",
            "Service temporarily unavailable",
        ):
            with self.subTest(mensaje=mensaje):
                self.assertEqual(classify_api_error(_ErrorFalso(mensaje)), "transient")


class CreditErrorsAreFatalButNamedTests(unittest.TestCase):
    """No se reintentan -repetir no recarga la clave- pero se nombran."""

    def test_the_message_anthropic_actually_returns(self):
        error = _ErrorFalso(
            "Your credit balance is too low to access the Anthropic API", 400
        )
        self.assertEqual(classify_api_error(error), "credit")

    def test_payment_required_by_status_alone(self):
        self.assertEqual(classify_api_error(_ErrorFalso("", 402)), "credit")

    def test_credit_wins_over_transient_wording(self):
        """Un mensaje de saldo que dijera «try again» no debe reintentarse.

        Es el motivo de que el orden del clasificador importe: reintentar un
        saldo agotado gasta tiempo y no arregla nada.
        """
        error = _ErrorFalso("Insufficient credit, please try again later", None)
        self.assertEqual(classify_api_error(error), "credit")


class AuthErrorsComeFirstTests(unittest.TestCase):
    def test_bad_key(self):
        for mensaje, estado in (("invalid x-api-key", 401), ("Unauthorized", 403)):
            with self.subTest(mensaje=mensaje):
                self.assertEqual(classify_api_error(_ErrorFalso(mensaje, estado)),
                                 "auth")


class UnknownErrorsStayFatalTests(unittest.TestCase):
    """Lo que no se reconoce no se reintenta: repetir a ciegas gasta."""

    def test_a_client_error_is_fatal(self):
        self.assertEqual(
            classify_api_error(_ErrorFalso("model not found", 404)), "fatal"
        )

    def test_a_plain_bug_is_fatal(self):
        self.assertEqual(classify_api_error(ValueError("algo raro")), "fatal")


class TheFamiliesDoNotOverlapTests(unittest.TestCase):
    def test_no_status_code_belongs_to_two_families(self):
        """Si un codigo cayera en dos listas, el orden decidiria en silencio."""
        todos = list(AUTH_API_STATUS) + list(CREDIT_API_STATUS) + list(TRANSIENT_API_STATUS)
        self.assertEqual(len(todos), len(set(todos)))

    def test_429_is_transient_not_credit(self):
        """Un limite de ritmo se pasa esperando; un saldo agotado, no."""
        self.assertIn(429, TRANSIENT_API_STATUS)
        self.assertNotIn(429, CREDIT_API_STATUS)


if __name__ == "__main__":
    unittest.main()
