# -*- coding: utf-8 -*-
# Pruebas de grant_radar/product_watch.py con import estándar.
#
# `compare_funnels()` vigila la recopilación; esto vigila el otro extremo, el
# JSON publicado. Nace de un caso real del 31/08/2026: corregir una regla movió
# dieciséis análisis a «no elegible» de golpe —era lo correcto— y nada lo habría
# dicho si no llega a mirarse a mano (AGENTS.md 51.4).
#
# Lo que estas pruebas fijan es la distinción que da valor al aviso: una
# convocatoria que desaparece **con el plazo vencido** es el funcionamiento
# normal; una que desaparece **sin vencer** es que alguien dejó de encontrarla.

import unittest
from datetime import date

from grant_radar.product_watch import (
    compare_collection_against_product,
    compare_published_products,
    stable_identity,
    summarize_collection_changes,
    summarize_product_changes,
)

HOY = date(2026, 8, 31)


def convocatoria(identifier, **overrides):
    base = {
        "identifier": identifier,
        "source": "BDNS",
        "title": f"Convocatoria {identifier}",
        "deadline_date": "2026-12-31",
        "eligibility": "unknown",
        "objeto_y_actuaciones": "Financia inversiones industriales.",
        "summary": "Encaja con las capacidades térmicas.",
        "eligible_actions": ["Adquisición de equipos"],
        "url": "https://example.test/x",
    }
    base.update(overrides)
    return base


class DisappearanceTests(unittest.TestCase):
    def test_a_call_that_expired_is_not_an_alarm(self):
        informe = compare_published_products(
            [convocatoria("A", deadline_date="2026-08-01")], [], today=HOY
        )
        self.assertEqual(informe["gone"], 1)
        self.assertEqual(informe["gone_without_expiring"], [])

    def test_a_call_that_vanishes_with_time_left_is_reported(self):
        informe = compare_published_products(
            [convocatoria("A", deadline_date="2026-12-31")], [], today=HOY
        )
        self.assertEqual(len(informe["gone_without_expiring"]), 1)
        self.assertIn("Convocatoria A", informe["gone_without_expiring"][0]["title"])

    def test_a_call_without_a_deadline_counts_as_unexplained(self):
        """Sin fecha no se puede decir que caducara: mejor avisar."""
        informe = compare_published_products(
            [convocatoria("A", deadline_date="")], [], today=HOY
        )
        self.assertEqual(len(informe["gone_without_expiring"]), 1)

    def test_the_same_call_is_recognised_across_versions(self):
        antes = [convocatoria("A", title="Título viejo")]
        ahora = [convocatoria("A", title="Título nuevo tras una corrección")]
        informe = compare_published_products(antes, ahora, today=HOY)
        self.assertEqual(informe["gone"], 0)
        self.assertEqual(informe["new"], 0)

    def test_a_call_without_identifier_falls_back_to_its_title(self):
        item = {"source": "CDTI", "title": "Ventanilla abierta", "eligibility": "eligible"}
        informe = compare_published_products([item], [dict(item)], today=HOY)
        self.assertEqual(informe["gone"], 0)



class StableIdentityTests(unittest.TestCase):
    """La identidad que el JSON publica como `stable_key` desde el 02/09/2026.

    Antes solo servía para comparar dos publicaciones y podía ser privada.
    Ahora la referencian cosas que viven fuera del archivo —los favoritos del
    panel, y mañana un enlace profundo o una nota—, así que lo que estas
    pruebas fijan no es cómo se calcula sino **qué no debe moverla**.
    """

    VOLATILES = {
        # Cambia todos los días.
        "deadline": 3,
        # Cambia con cada análisis, y cambió de 75 a 85 en una prueba real
        # (AGENTS.md 54.4).
        "fit_score": 85,
        # El `id` publicado es un contador posicional: la ordenación por
        # `match` lo reasigna en cada ejecución. Es el motivo de todo esto.
        "id": 42,
        "match": 85,
        "eligibility": "eligible",
        "url_rota": True,
    }

    def test_the_key_survives_everything_that_changes_between_runs(self):
        base = convocatoria("BDNS-919481", id=7)
        movida = convocatoria("BDNS-919481", **self.VOLATILES)
        self.assertEqual(stable_identity(base), stable_identity(movida))

    def test_a_different_call_gets_a_different_key(self):
        self.assertNotEqual(
            stable_identity(convocatoria("A")), stable_identity(convocatoria("B"))
        )

    def test_the_same_identifier_in_two_sources_is_not_the_same_call(self):
        """La fuente forma parte de la clave, y tiene que formarla.

        Dos registros oficiales distintos pueden numerar igual: sin la fuente
        delante, un favorito marcado en BDNS aparecería marcado en CDTI.
        """
        self.assertNotEqual(
            stable_identity(convocatoria("2026-1", source="BDNS")),
            stable_identity(convocatoria("2026-1", source="CDTI")),
        )

    def test_the_fallback_order_is_identifier_then_bdns_id_then_url(self):
        con_ambos = {"source": "BDNS", "identifier": "ID-1", "bdns_id": "919481",
                     "url": "https://example.test/x", "title": "T"}
        self.assertEqual(stable_identity(con_ambos), "BDNS|identifier|ID-1")
        sin_identificador = dict(con_ambos, identifier="")
        self.assertEqual(stable_identity(sin_identificador), "BDNS|bdns_id|919481")
        solo_url = dict(sin_identificador, bdns_id="")
        self.assertEqual(stable_identity(solo_url), "BDNS|url|https://example.test/x")

    def test_the_last_resort_is_the_trimmed_title(self):
        largo = {"source": "CDTI", "title": "  " + "T" * 200 + "  "}
        clave = stable_identity(largo)
        self.assertTrue(clave.startswith("CDTI|title|"))
        self.assertEqual(len(clave.split("|", 2)[2]), 120)

    def test_a_zero_like_value_does_not_count_as_an_identifier(self):
        """`0` y `""` no identifican nada: hay que caer al siguiente campo.

        Importa porque el gemelo en JavaScript (`deriveStableKey()`) tendría
        aquí la divergencia más fácil de introducir sin verla: `String(0)` sí
        es una cadena no vacía.
        """
        registro = {"source": "BDNS", "identifier": 0, "bdns_id": "919481",
                    "url": "https://example.test/x", "title": "T"}
        self.assertEqual(stable_identity(registro), "BDNS|bdns_id|919481")


class EligibilityMovementTests(unittest.TestCase):
    def test_a_mass_movement_is_summarised(self):
        """El caso real: dieciséis análisis cambiando de veredicto a la vez."""
        antes = [convocatoria(str(n)) for n in range(6)]
        ahora = [convocatoria(str(n), eligibility="ineligible") for n in range(6)]
        informe = compare_published_products(antes, ahora, today=HOY)
        self.assertEqual(informe["eligibility_moves"], {"unknown→ineligible": 6})
        self.assertIn("6 pasan de unknown→ineligible", summarize_product_changes(informe))

    def test_two_isolated_changes_are_not_news(self):
        antes = [convocatoria(str(n)) for n in range(6)]
        ahora = [convocatoria(str(n), eligibility="eligible" if n < 2 else "unknown")
                 for n in range(6)]
        informe = compare_published_products(antes, ahora, today=HOY)
        self.assertEqual(informe["eligibility_moves"], {})


class EmptiedFieldTests(unittest.TestCase):
    def test_a_field_that_stops_being_published_is_reported(self):
        """Una regresión que los recuentos no ven: siguen siendo 6 fichas."""
        antes = [convocatoria(str(n)) for n in range(6)]
        ahora = [convocatoria(str(n), objeto_y_actuaciones="") for n in range(6)]
        informe = compare_published_products(antes, ahora, today=HOY)
        self.assertEqual(informe["emptied_fields"], {"objeto_y_actuaciones": 6})

    def test_an_empty_list_also_counts_as_emptied(self):
        antes = [convocatoria(str(n)) for n in range(6)]
        ahora = [convocatoria(str(n), eligible_actions=[]) for n in range(6)]
        informe = compare_published_products(antes, ahora, today=HOY)
        self.assertEqual(informe["emptied_fields"], {"eligible_actions": 6})

    def test_a_field_that_appears_is_not_a_regression(self):
        antes = [convocatoria(str(n), objeto_y_actuaciones="") for n in range(6)]
        ahora = [convocatoria(str(n)) for n in range(6)]
        informe = compare_published_products(antes, ahora, today=HOY)
        self.assertEqual(informe["emptied_fields"], {})


class SummaryTests(unittest.TestCase):
    def test_the_first_publication_says_so_instead_of_inventing(self):
        informe = compare_published_products([], [convocatoria("A")], today=HOY)
        self.assertIn("primera publicación", summarize_product_changes(informe))

    def test_a_quiet_publication_reads_quietly(self):
        antes = [convocatoria(str(n)) for n in range(6)]
        linea = summarize_product_changes(
            compare_published_products(antes, [dict(x) for x in antes], today=HOY)
        )
        self.assertEqual(linea, "Producto: 6 publicadas.")

    def test_a_broken_publication_shouts(self):
        antes = [convocatoria(str(n)) for n in range(6)]
        linea = summarize_product_changes(
            compare_published_products(antes, antes[:1], today=HOY)
        )
        self.assertIn("5 desaparecen sin vencer su plazo", linea)

    def test_the_count_is_not_the_truncated_sample(self):
        """La muestra se recorta a diez; el recuento, no.

        Con quince desaparecidas, decir «10» sería quedarse corto justo cuando
        más importa el número.
        """
        antes = [convocatoria(str(n)) for n in range(15)]
        informe = compare_published_products(antes, [], today=HOY)
        self.assertEqual(informe["gone_without_expiring_count"], 15)
        self.assertEqual(len(informe["gone_without_expiring"]), 10)
        self.assertIn("15 desaparecen", summarize_product_changes(informe))


class CollectionAgainstProductTests(unittest.TestCase):
    """Lo que la recopilación diaria encuentra y el producto no tiene.

    El aviso diario decía cuántas convocatorias esperaban análisis y nada más:
    nadie se enteraba de que hoy habían aparecido cinco nuevas ni de cuál
    cerraba en doce días.
    """

    def recopilada(self, identifier, **overrides):
        base = {
            "identifier": identifier,
            "source": "BDNS",
            "title": f"Convocatoria {identifier}",
            "url": "https://example.test/x",
            "deadline_date": "2026-12-31",
        }
        base.update(overrides)
        return base

    def test_what_is_new_is_what_the_product_does_not_have(self):
        informe = compare_collection_against_product(
            [convocatoria("A")],
            [self.recopilada("A"), self.recopilada("B")],
            today=HOY,
        )
        self.assertEqual(informe["new_since_publication"], 1)
        self.assertEqual(informe["new_sample"][0]["title"], "Convocatoria B")

    def test_nothing_new_is_reported_when_nothing_is_new(self):
        informe = compare_collection_against_product(
            [convocatoria("A")], [self.recopilada("A")], today=HOY
        )
        self.assertEqual(informe["new_since_publication"], 0)
        self.assertIn("sin novedades", summarize_collection_changes(informe))

    def test_the_unanalysed_fields_are_not_read_as_a_regression(self):
        """El motivo de que esta función exista y no se reutilice la otra.

        Lo recopilado no ha pasado por Haiku: no tiene `summary`, ni
        `objeto_y_actuaciones`, ni `eligible_actions`. Pasarlo por
        `compare_published_products()` marcaría los tres como «vaciados» en
        todas las fichas, y el aviso diario abriría con una regresión
        inventada. Aquí se comprueba las dos cosas: que la función nueva no lo
        hace, y que la vieja sí lo haría.
        """
        publicadas = [convocatoria(str(n)) for n in range(6)]
        recopiladas = [self.recopilada(str(n)) for n in range(6)]

        informe = compare_collection_against_product(publicadas, recopiladas, today=HOY)
        self.assertNotIn("emptied_fields", informe)
        self.assertEqual(informe["new_since_publication"], 0)

        equivocado = compare_published_products(publicadas, recopiladas, today=HOY)
        self.assertEqual(
            equivocado["emptied_fields"],
            {"eligible_actions": 6, "objeto_y_actuaciones": 6, "summary": 6},
        )

    def test_expiring_and_expired_describe_the_published_product(self):
        """No la recopilación: son las fichas que el usuario tiene delante."""
        publicadas = [
            convocatoria("vencida", deadline_date="2026-08-01"),
            convocatoria("cierra-ya", deadline_date="2026-09-05"),
            convocatoria("cierra-justo", deadline_date="2026-09-14"),
            convocatoria("holgada", deadline_date="2026-12-31"),
            convocatoria("sin-fecha", deadline_date=""),
        ]
        informe = compare_collection_against_product(publicadas, [], today=HOY)
        self.assertEqual(informe["expired"], 1)
        self.assertEqual(informe["expiring_soon"], 2)
        self.assertEqual(
            [item["title"] for item in informe["expiring_soon_sample"]],
            ["Convocatoria cierra-ya", "Convocatoria cierra-justo"],
        )

    def test_a_call_without_a_deadline_is_left_out_of_both_counts(self):
        """Sin fecha no se puede decir ni que caduque ni que aguante."""
        informe = compare_collection_against_product(
            [convocatoria("A", deadline_date="")], [], today=HOY
        )
        self.assertEqual(informe["expired"], 0)
        self.assertEqual(informe["expiring_soon"], 0)

    def test_injected_keys_are_the_ones_used(self):
        """El pipeline inyecta las claves ya normalizadas.

        Una convocatoria recopilada sin identificador trae la url tal cual la
        dio la fuente; la publicada, la que salió de `_normalize_public_url()`.
        Comparar las dos sin normalizar daría un alta falsa por cada ficha que
        se identifica por url —diez de las setenta y siete del producto—.
        """
        publicada = {"source": "CDTI", "title": "Ventanilla",
                     "url": "https://ejemplo.test/ficha", "deadline_date": ""}
        cruda = {"source": "CDTI", "title": "Ventanilla",
                 "url": "ejemplo.test/ficha", "deadline_date": ""}

        ingenuo = compare_collection_against_product([publicada], [cruda], today=HOY)
        self.assertEqual(ingenuo["new_since_publication"], 1, "sin normalizar, alta falsa")

        correcto = compare_collection_against_product(
            [publicada], [cruda],
            collected_keys=[stable_identity(publicada)],
            today=HOY,
        )
        self.assertEqual(correcto["new_since_publication"], 0)

    def test_the_summary_never_calls_them_opportunities(self):
        """Han pasado el filtro determinista, no el de Haiku."""
        informe = compare_collection_against_product(
            [], [self.recopilada("A")], today=HOY
        )
        linea = summarize_collection_changes(informe)
        self.assertIn("detectadas, sin analizar", linea)
        self.assertNotIn("oportunidad", linea.lower())

    def test_the_sample_is_truncated_but_the_count_is_not(self):
        informe = compare_collection_against_product(
            [], [self.recopilada(str(n)) for n in range(15)], today=HOY
        )
        self.assertEqual(informe["new_since_publication"], 15)
        self.assertEqual(len(informe["new_sample"]), 10)


if __name__ == "__main__":
    unittest.main()
