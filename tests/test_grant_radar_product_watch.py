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
    compare_published_products,
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


if __name__ == "__main__":
    unittest.main()
