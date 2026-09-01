# -*- coding: utf-8 -*-
# Pruebas de grant_radar/gap_report.py con import estándar (sin runpy).
#
# El informe no arregla nada por sí mismo: sirve para decidir dónde mirar, y
# para aceptar o rechazar el resultado de una prueba de pago. Por eso lo que
# fijan estas pruebas es que sus cifras signifiquen exactamente lo que dicen.
#
# Dos errores reales, uno de diseño y otro encontrado al ejecutarlo por primera
# vez, quedan clavados aquí:
#
#   1. contar los huecos de producto sobre el total de fichas en vez de sobre
#      las vivas haría parecer sana una fuente cuyas convocatorias se descartan
#      casi todas, porque un análisis descartado no declara huecos;
#   2. contar menciones en vez de convocatorias publicó «20/19» para
#      `funding_rate_percent` en Horizon, porque el modelo repitió el campo
#      dentro del mismo `missing_fields`.

import unittest

from grant_radar.gap_report import (
    ACCEPTED_ABSENCES,
    BUDGET_WATCH_FIELDS,
    build_gap_report,
    cache_version_state,
    format_budget_watch,
    format_gap_report,
    gap_records_from_cache,
    gap_records_from_product,
)
from grant_radar.versions import (
    ANALYSIS_PROMPT_VERSION,
    CACHE_SCHEMA_VERSION,
    CLAUDE_MODEL,
    EVALUATOR_VERSION,
    EXTRACTOR_VERSION,
    PARTNER_CATALOG_VERSION,
    PROFILE_VERSION,
)


def _ficha(source, decision="watch", data_gaps=(), missing_fields=()):
    return {
        "source": source,
        "decision": decision,
        "data_gaps": list(data_gaps),
        "call_facts": {"missing_fields": list(missing_fields)},
    }


def _entrada_cache(source, **kwargs):
    return {
        "raw_document": {"source": source},
        "analysis": _ficha(source, **kwargs),
    }


def _meta_vigente(**cambios):
    meta = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "prompt_version": ANALYSIS_PROMPT_VERSION,
        "profile_version": PROFILE_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "evaluator_version": EVALUATOR_VERSION,
        "partner_catalog_version": PARTNER_CATALOG_VERSION,
        "model_version": CLAUDE_MODEL,
        "saved_at": "2026-09-01T10:00:00+00:00",
    }
    meta.update(cambios)
    return meta


class LecturaDeOrigenesTests(unittest.TestCase):
    """Los dos orígenes deben producir la misma forma de registro."""

    def test_producto_y_cache_producen_registros_equivalentes(self):
        producto = {"convocatorias": [
            _ficha("HORIZON EUROPE", data_gaps=["budget_missing"],
                   missing_fields=["grant_max_eur"]),
        ]}
        cache = {"entries": {"k": _entrada_cache(
            "HORIZON EUROPE", data_gaps=["budget_missing"],
            missing_fields=["grant_max_eur"],
        )}}
        self.assertEqual(
            gap_records_from_product(producto), gap_records_from_cache(cache)
        )

    def test_la_cache_acepta_el_nombre_antiguo_del_documento(self):
        # Las entradas migradas guardan `conv` en vez de `raw_document`.
        cache = {"entries": {"k": {
            "conv": {"source": "BDNS"}, "analysis": _ficha("BDNS"),
        }}}
        self.assertEqual(gap_records_from_cache(cache)[0]["source"], "BDNS")

    def test_entradas_ilegibles_no_rompen_la_lectura(self):
        cache = {"entries": {
            "a": None,
            "b": {"analysis": "no es un dict"},
            "c": _entrada_cache("CDTI"),
        }}
        self.assertEqual(len(gap_records_from_cache(cache)), 1)

    def test_archivos_ausentes_o_vacios_dan_lista_vacia(self):
        for vacio in ({}, None, [], {"convocatorias": None}):
            self.assertEqual(gap_records_from_product(vacio), [])
        for vacio in ({}, None, [], {"entries": None}):
            self.assertEqual(gap_records_from_cache(vacio), [])

    def test_una_ficha_sin_fuente_no_desaparece_del_recuento(self):
        registros = gap_records_from_product({"convocatorias": [_ficha("")]})
        self.assertEqual(registros[0]["source"], "?")


class DenominadorTests(unittest.TestCase):
    """El error de diseño: descartadas y vivas no comparten denominador."""

    def test_los_huecos_de_producto_se_cuentan_solo_sobre_las_vivas(self):
        registros = gap_records_from_product({"convocatorias": [
            _ficha("BDNS", decision="watch", data_gaps=["eligibility_unknown"]),
            _ficha("BDNS", decision="discard_ineligible"),
            _ficha("BDNS", decision="discard_out_of_scope"),
        ]})
        informe = build_gap_report(registros, origin="prueba")
        fuente = informe["sources"][0]
        self.assertEqual(fuente["total"], 3)
        self.assertEqual(fuente["live"], 1)
        # 1 de 1 viva, no 1 de 3: la fuente no está sana en dos tercios.
        self.assertEqual(fuente["data_gaps"]["eligibility_unknown"], 1)

    def test_una_descartada_no_aporta_huecos_aunque_los_traiga(self):
        registros = gap_records_from_product({"convocatorias": [
            _ficha("BDNS", decision="discard_ineligible",
                   data_gaps=["eligibility_unknown"]),
        ]})
        informe = build_gap_report(registros, origin="prueba")
        self.assertEqual(informe["sources"][0]["data_gaps"], {})

    def test_los_campos_del_extractor_si_cuentan_las_descartadas(self):
        # `missing_fields` describe la lectura de la fuente, que ocurrió
        # igualmente: descartar la convocatoria después no la deshace.
        registros = gap_records_from_product({"convocatorias": [
            _ficha("BDNS", decision="discard_ineligible",
                   missing_fields=["grant_max_eur"]),
        ]})
        informe = build_gap_report(registros, origin="prueba")
        self.assertEqual(informe["sources"][0]["missing_fields"]["grant_max_eur"], 1)


class RecuentoPorConvocatoriaTests(unittest.TestCase):
    """El error real: contar menciones producía «20/19»."""

    def test_un_campo_repetido_en_la_misma_ficha_cuenta_una_vez(self):
        registros = gap_records_from_product({"convocatorias": [
            _ficha("HORIZON EUROPE", missing_fields=[
                "funding_rate_percent", "funding_rate_percent",
            ]),
        ]})
        informe = build_gap_report(registros, origin="prueba")
        self.assertEqual(
            informe["sources"][0]["missing_fields"]["funding_rate_percent"], 1
        )

    def test_ningun_recuento_supera_nunca_su_denominador(self):
        registros = gap_records_from_product({"convocatorias": [
            _ficha("HORIZON EUROPE",
                   data_gaps=["budget_missing", "budget_missing"],
                   missing_fields=["grant_max_eur", "grant_max_eur",
                                   "grant_max_eur"]),
            _ficha("HORIZON EUROPE", missing_fields=["grant_max_eur"]),
        ]})
        informe = build_gap_report(registros, origin="prueba")
        fuente = informe["sources"][0]
        for veces in fuente["missing_fields"].values():
            self.assertLessEqual(veces, fuente["total"])
        for veces in fuente["data_gaps"].values():
            self.assertLessEqual(veces, fuente["live"])

    def test_los_nombres_se_normalizan_sin_espacios_sobrantes(self):
        registros = gap_records_from_product({"convocatorias": [
            _ficha("CDTI", missing_fields=["  grant_max_eur  ", "", "   "]),
        ]})
        informe = build_gap_report(registros, origin="prueba")
        self.assertEqual(
            informe["sources"][0]["missing_fields"], {"grant_max_eur": 1}
        )


class ControlDePresupuestoTests(unittest.TestCase):
    """El control concreto que pide AGENTS.md 53.2."""

    def test_vigila_los_cuatro_campos_del_53_2(self):
        self.assertEqual(BUDGET_WATCH_FIELDS, (
            "budget_total_eur", "grant_max_eur",
            "project_budget_eur", "funding_rate_percent",
        ))

    def test_declara_cero_para_un_campo_que_no_falta_en_ninguna(self):
        registros = gap_records_from_product({"convocatorias": [
            _ficha("HORIZON EUROPE", missing_fields=["grant_max_eur"]),
        ]})
        informe = build_gap_report(registros, origin="prueba")
        vigilancia = informe["budget_watch"]["HORIZON EUROPE"]
        self.assertEqual(vigilancia["grant_max_eur"], 1)
        # Un campo presente debe salir como 0, no ausente del diccionario:
        # el criterio de aceptación se lee comparando las cuatro columnas.
        self.assertEqual(vigilancia["budget_total_eur"], 0)
        self.assertEqual(set(vigilancia), set(BUDGET_WATCH_FIELDS))

    def test_el_estado_de_horizon_hoy_es_el_documentado_en_la_seccion_52(self):
        # 19 de 19 sin una sola cifra: es la línea base contra la que se acepta
        # o se rechaza la prueba de pago.
        registros = [
            _ficha("HORIZON EUROPE", missing_fields=BUDGET_WATCH_FIELDS)
            for _ in range(19)
        ]
        registros = gap_records_from_product({"convocatorias": registros})
        informe = build_gap_report(registros, origin="prueba")
        for campo in BUDGET_WATCH_FIELDS:
            self.assertEqual(informe["budget_watch"]["HORIZON EUROPE"][campo], 19)


class VersionesDeCacheTests(unittest.TestCase):
    """Sin esto, una caché vieja se leería como si fuera el resultado nuevo."""

    def test_reconoce_una_cache_con_las_versiones_vigentes(self):
        estado = cache_version_state({"_meta": _meta_vigente(), "entries": {}})
        self.assertTrue(estado["known"])
        self.assertTrue(estado["matches"])
        self.assertEqual(estado["mismatched"], [])

    def test_indica_exactamente_que_version_no_cuadra(self):
        estado = cache_version_state({
            "_meta": _meta_vigente(prompt_version="2026-08-v10-antiguo"),
        })
        self.assertFalse(estado["matches"])
        self.assertEqual(estado["mismatched"], ["prompt_version"])

    def test_una_cache_sin_metadatos_no_se_da_por_buena(self):
        estado = cache_version_state({"entries": {}})
        self.assertFalse(estado["known"])
        self.assertIsNone(estado["matches"])

    def test_la_cache_se_lee_aunque_las_versiones_no_cuadren(self):
        # A propósito: `cache_load()` devuelve {} en ese caso, y este informe
        # existe justamente para poder mirar qué hay dentro.
        cache = {
            "_meta": _meta_vigente(prompt_version="antigua"),
            "entries": {"k": _entrada_cache("BDNS", missing_fields=["trl_min"])},
        }
        self.assertEqual(len(gap_records_from_cache(cache)), 1)


class PresentacionTests(unittest.TestCase):

    def _informe(self):
        registros = gap_records_from_product({"convocatorias": [
            _ficha("HORIZON EUROPE", data_gaps=["budget_missing"],
                   missing_fields=["grant_max_eur", "trl_source"]),
            _ficha("BDNS", decision="discard_ineligible"),
        ]})
        return build_gap_report(registros, origin="Prueba", label="etiqueta")

    def test_el_informe_nombra_su_origen_y_sus_fuentes(self):
        texto = format_gap_report([self._informe()], "2026-09-01")
        self.assertIn("2026-09-01", texto)
        self.assertIn("Prueba", texto)
        self.assertIn("etiqueta", texto)
        self.assertIn("HORIZON EUROPE", texto)
        self.assertIn("grant_max_eur", texto)

    def test_las_ausencias_aceptadas_se_marcan_para_no_reabrirlas(self):
        # Decisión cerrada del usuario (AGENTS.md 53.3): el TRL no se persigue.
        texto = format_gap_report([self._informe()], "2026-09-01")
        self.assertIn("trl_source", texto)
        self.assertIn("ausencia aceptada", texto)
        self.assertEqual(
            ACCEPTED_ABSENCES, ("trl_source", "trl_min", "trl_max")
        )

    def test_avisa_cuando_la_cache_es_de_otras_versiones(self):
        informe = build_gap_report(
            [], origin="Caché",
            version_state=cache_version_state({
                "_meta": _meta_vigente(evaluator_version="vieja"),
            }),
        )
        texto = format_gap_report([informe], "2026-09-01")
        self.assertIn("AVISO", texto)
        self.assertIn("evaluator_version", texto)

    def test_sin_analisis_lo_dice_en_vez_de_romper(self):
        informe = build_gap_report([], origin="Vacío")
        texto = format_gap_report([informe], "2026-09-01")
        self.assertIn("Sin análisis que medir", texto)
        self.assertIn("Sin análisis que medir", format_budget_watch([informe]))

    def test_la_tabla_de_presupuesto_nombra_su_objetivo(self):
        texto = format_budget_watch([self._informe()])
        self.assertIn("CONTROL 53.2", texto)
        self.assertIn("HORIZON EUROPE", texto)

    def test_formatear_sin_informes_no_rompe(self):
        self.assertIn("CAMPOS AUSENTES", format_gap_report([], "2026-09-01"))
        self.assertIn("CONTROL 53.2", format_budget_watch([]))


class OrdenTests(unittest.TestCase):

    def test_las_fuentes_salen_de_mayor_a_menor_volumen(self):
        registros = gap_records_from_product({"convocatorias": (
            [_ficha("CDTI")] + [_ficha("BDNS")] * 5 + [_ficha("HORIZON EUROPE")] * 3
        )})
        informe = build_gap_report(registros, origin="prueba")
        self.assertEqual(
            [fuente["source"] for fuente in informe["sources"]],
            ["BDNS", "HORIZON EUROPE", "CDTI"],
        )

    def test_los_campos_salen_del_mas_ausente_al_menos(self):
        registros = gap_records_from_product({"convocatorias": (
            [_ficha("BDNS", missing_fields=["grant_max_eur", "trl_min"])] * 3
            + [_ficha("BDNS", missing_fields=["trl_min"])] * 2
        )})
        informe = build_gap_report(registros, origin="prueba")
        self.assertEqual(
            list(informe["sources"][0]["missing_fields"]),
            ["trl_min", "grant_max_eur"],
        )


if __name__ == "__main__":
    unittest.main()
