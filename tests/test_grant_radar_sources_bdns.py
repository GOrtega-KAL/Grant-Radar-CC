# -*- coding: utf-8 -*-
# Pruebas de grant_radar/sources/bdns.py con import estándar (sin runpy).
#
# Punto 20 del backlog. BDNS era el conector grande sin archivo propio: aporta
# 50 de las 82 convocatorias vigentes, más que las otras siete fuentes juntas,
# y hasta ahora solo se ejercitaba de refilón —por el camino feliz de la prueba
# de humo y por `runpy` desde tests/test_grant_radar.py—.
#
# Lo que se prueba aquí no es que el conector hable con la API, que ya cubre la
# prueba de humo, sino la aritmética con la que decide FECHAS, que es donde un
# error no se nota: un plazo mal calculado no rompe nada, solo publica una
# convocatoria como abierta cuando está cerrada, o al revés. Y esa aritmética
# tiene toda la casuística del BOE español —«quince días hábiles», «dos meses»,
# «el día del mes equivalente al de la publicación»— que es exactamente el tipo
# de cosa que se escribe una vez y nadie vuelve a mirar.

import unittest
from datetime import datetime

from grant_radar.sources.bdns import (
    _add_calendar_months,
    _bdns_call_publication_date,
    _bdns_relative_application_deadline,
)


class MesesNaturalesTests(unittest.TestCase):
    """`_add_calendar_months`: sumar meses no es sumar 30 días."""

    def test_suma_simple(self):
        self.assertEqual(
            _add_calendar_months(datetime(2026, 3, 10), 2),
            datetime(2026, 5, 10),
        )

    def test_cambia_de_ano(self):
        self.assertEqual(
            _add_calendar_months(datetime(2026, 11, 20), 3),
            datetime(2027, 2, 20),
        )

    def test_recorta_el_dia_cuando_el_mes_destino_es_mas_corto(self):
        # 31 de enero + 1 mes no existe: debe caer en el último día de febrero.
        self.assertEqual(
            _add_calendar_months(datetime(2026, 1, 31), 1),
            datetime(2026, 2, 28),
        )

    def test_respeta_el_ano_bisiesto(self):
        # 2028 sí es bisiesto; el recorte debe dar 29, no 28.
        self.assertEqual(
            _add_calendar_months(datetime(2028, 1, 31), 1),
            datetime(2028, 2, 29),
        )

    def test_diciembre_mas_un_mes_es_enero_del_siguiente(self):
        self.assertEqual(
            _add_calendar_months(datetime(2026, 12, 15), 1),
            datetime(2027, 1, 15),
        )


class PlazosRelativosTests(unittest.TestCase):
    """
    `_bdns_relative_application_deadline`: muchas convocatorias no publican una
    fecha, sino un plazo contado desde la publicación.
    """

    PUB = "2026-09-01"  # martes

    def _calc(self, texto, publicacion=None):
        return _bdns_relative_application_deadline(texto, publicacion or self.PUB)

    def test_dias_naturales_se_suman_tal_cual(self):
        fecha, estimada = self._calc("El plazo será de 20 días naturales")
        self.assertEqual(fecha, "2026-09-21")
        self.assertFalse(estimada, "un plazo natural es exacto, no estimado")

    def test_dias_habiles_saltan_fines_de_semana_y_se_marcan_estimados(self):
        # Desde el martes 01/09, cinco hábiles son 2, 3, 4, 7 y 8.
        fecha, estimada = self._calc("El plazo será de 5 días hábiles")
        self.assertEqual(fecha, "2026-09-08")
        self.assertTrue(
            estimada,
            "los hábiles ignoran festivos locales: deben declararse estimados",
        )

    def test_admite_el_numero_escrito_con_letra(self):
        # El BOE escribe «quince días naturales» tan a menudo como «15».
        con_letra, _ = self._calc("quince días naturales desde la publicación")
        con_cifra, _ = self._calc("15 días naturales desde la publicación")
        self.assertEqual(con_letra, con_cifra)
        self.assertEqual(con_letra, "2026-09-16")

    def test_meses_usan_calendario_no_treinta_dias(self):
        fecha, estimada = self._calc("El plazo será de dos meses")
        self.assertEqual(fecha, "2026-11-01")
        self.assertFalse(estimada)

    def test_la_formula_del_dia_equivalente_es_un_mes(self):
        fecha, _ = self._calc(
            "hasta el día del mes equivalente al del día de la publicación"
        )
        self.assertEqual(fecha, "2026-10-01")

    def test_sin_plazo_reconocible_no_inventa_fecha(self):
        for texto in ("", "según se determine", "plazo abierto"):
            self.assertEqual(self._calc(texto), ("", False))

    def test_sin_fecha_de_publicacion_no_se_puede_calcular(self):
        self.assertEqual(
            _bdns_relative_application_deadline("20 días naturales", ""),
            ("", False),
        )

    def test_una_publicacion_ilegible_no_revienta(self):
        self.assertEqual(
            _bdns_relative_application_deadline("20 días naturales", "no-es-fecha"),
            ("", False),
        )

    def test_los_dias_tienen_prioridad_sobre_los_meses(self):
        # Un texto que menciona ambos: manda el plazo en días, que es el que
        # las bases usan como plazo de solicitud.
        fecha, _ = self._calc(
            "10 días naturales para solicitar; la resolución se dicta en seis meses"
        )
        self.assertEqual(fecha, "2026-09-11")


class FechaDePublicacionTests(unittest.TestCase):
    """
    `_bdns_call_publication_date`: la fecha del anuncio, no la del PDF.

    Importa porque de ella cuelgan todos los plazos relativos de arriba: si se
    toma la fecha de un documento reeditado, el plazo entero se desplaza.
    """

    def test_toma_el_anuncio_mas_antiguo(self):
        detalle = {"anuncios": [
            {"datPublicacion": "2026-07-15"},
            {"datPublicacion": "2026-06-01"},
            {"datPublicacion": "2026-08-20"},
        ]}
        self.assertEqual(_bdns_call_publication_date(detalle), "2026-06-01")

    def test_ignora_anuncios_mal_formados(self):
        detalle = {"anuncios": [
            "esto no es un dict",
            {"datPublicacion": ""},
            {"datPublicacion": "2026-06-01"},
        ]}
        self.assertEqual(_bdns_call_publication_date(detalle), "2026-06-01")

    def test_sin_anuncios_cae_a_los_documentos_de_convocatoria(self):
        detalle = {
            "anuncios": [],
            "fechaRecepcion": "2026-06-01",
            "documentos": [
                {"datPublicacion": "2026-06-03", "descripcion": "Extracto de la convocatoria"},
            ],
        }
        self.assertEqual(_bdns_call_publication_date(detalle), "2026-06-03")

    def test_descarta_documentos_que_no_son_la_convocatoria(self):
        # Un anexo o un formulario no fechan la convocatoria.
        detalle = {
            "anuncios": [],
            "fechaRecepcion": "2026-06-01",
            "documentos": [
                {"datPublicacion": "2026-06-02", "descripcion": "Anexo II formulario"},
            ],
        }
        self.assertEqual(_bdns_call_publication_date(detalle), "")

    def test_descarta_documentos_muy_alejados_de_la_recepcion(self):
        # La ventana de 45 días evita tomar la fecha de una reedición
        # posterior, que desplazaría todos los plazos relativos.
        detalle = {
            "anuncios": [],
            "fechaRecepcion": "2026-06-01",
            "documentos": [
                {"datPublicacion": "2026-10-15", "descripcion": "Extracto de la convocatoria"},
            ],
        }
        self.assertEqual(_bdns_call_publication_date(detalle), "")

    def test_sin_nada_utilizable_devuelve_cadena_vacia(self):
        self.assertEqual(_bdns_call_publication_date({}), "")


if __name__ == "__main__":
    unittest.main()
