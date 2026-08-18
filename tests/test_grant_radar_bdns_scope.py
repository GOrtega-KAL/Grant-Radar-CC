# Pruebas de grant_radar/bdns_scope.py con import estándar (sin runpy).

import unittest

from grant_radar.bdns_scope import (
    _bdns_candidate_from_listing,
    _bdns_is_aragon_regional_administration,
    _bdns_is_prefilter_candidate,
)


class AragonRegionalAdministrationTests(unittest.TestCase):
    def test_autonomica_aragon_is_true(self):
        self.assertTrue(_bdns_is_aragon_regional_administration(
            {"nivel1": "AUTONOMICA", "nivel2": "ARAGÓN"}
        ))

    def test_case_and_accent_insensitive(self):
        self.assertTrue(_bdns_is_aragon_regional_administration(
            {"nivel1": "Autonómica", "nivel2": "aragon"}
        ))

    def test_local_aragon_entities_are_excluded(self):
        # Ayuntamientos/diputaciones de Aragón publican en el Boletín Oficial
        # de la Provincia, no en BOA: fuera de alcance deliberadamente.
        self.assertFalse(_bdns_is_aragon_regional_administration(
            {"nivel1": "LOCAL", "nivel2": "DIPUTACIÓN PROV. DE ZARAGOZA"}
        ))

    def test_autonomica_other_region_is_false(self):
        self.assertFalse(_bdns_is_aragon_regional_administration(
            {"nivel1": "AUTONOMICA", "nivel2": "CATALUÑA"}
        ))

    def test_missing_fields_do_not_raise(self):
        self.assertFalse(_bdns_is_aragon_regional_administration({}))


class CandidateFromListingTests(unittest.TestCase):
    def test_matches_a_broad_industrial_keyword(self):
        self.assertTrue(_bdns_candidate_from_listing(
            {"descripcion": "Subvenciones para digitalización industrial de pymes"}
        ))

    def test_unrelated_description_does_not_match(self):
        self.assertFalse(_bdns_candidate_from_listing(
            {"descripcion": "Becas de comedor escolar para familias numerosas"}
        ))


class PrefilterCandidateTests(unittest.TestCase):
    def test_keyword_match_without_aragon_still_passes(self):
        self.assertTrue(_bdns_is_prefilter_candidate({
            "descripcion": "Ayudas a la innovación industrial",
            "nivel1": "AUTONOMICA", "nivel2": "CATALUÑA",
        }))

    def test_aragon_administration_passes_even_without_a_keyword(self):
        # Caso crítico: antes de este cambio, esta fila se habría descartado
        # sin llegar siquiera a pedir el detalle.
        self.assertTrue(_bdns_is_prefilter_candidate({
            "descripcion": "Convenio de colaboración institucional ordinario",
            "nivel1": "AUTONOMICA", "nivel2": "ARAGÓN",
        }))

    def test_neither_keyword_nor_aragon_is_excluded(self):
        self.assertFalse(_bdns_is_prefilter_candidate({
            "descripcion": "Becas de comedor escolar para familias numerosas",
            "nivel1": "LOCAL", "nivel2": "AYUNTAMIENTO DE VIGO",
        }))


if __name__ == "__main__":
    unittest.main()
