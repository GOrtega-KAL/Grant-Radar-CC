# Pruebas de grant_radar/kalfrisa_profile.py y grant_radar/partner_catalog.py.
#
# Import estándar (sin runpy).

import unittest

from grant_radar.kalfrisa_profile import KALFRISA_PROFILE
from grant_radar.partner_catalog import PARTNER_CATALOG, preselect_partners


class KalfrisaProfileTests(unittest.TestCase):
    def test_profile_keeps_the_leading_blank_line_from_the_original_prompt(self):
        # El texto original era una cadena Python """...""" que empezaba con
        # un salto de línea; se conserva para no cambiar el prompt enviado a
        # Claude al mover el texto a un archivo aparte.
        self.assertTrue(KALFRISA_PROFILE.startswith("\nIDENTIDAD:"))

    def test_profile_contains_identity_and_scope_sections(self):
        # «PROGRAMAS Y SECTORES» se partió en dos el 02/09 y «EXPERIENCIA I+D»
        # ganó un paréntesis, al describir cada proyecto en vez de nombrarlo
        # (AGENTS.md 60.16). Las secciones nuevas entran aquí para que no se
        # puedan perder en una edición futura sin que nadie lo note.
        for section in (
            "IDENTIDAD:", "CAPACIDADES Y ACTIVOS TECNOLÓGICOS:",
            "SIMULACIÓN Y GEMELOS DIGITALES",
            "QUÉ APORTA KALFRISA COMO SOCIO INDUSTRIAL DE UN CONSORCIO:",
            "EXPERIENCIA I+D RELEVANTE",
            "QUÉ TIPO DE CONVOCATORIA INTERESA:", "SECTORES:",
            "FUERA DE FOCO SALVO CONEXIÓN INDUSTRIAL TÉRMICA EXPLÍCITA:",
        ):
            self.assertIn(section, KALFRISA_PROFILE)

    def test_profile_contains_the_registered_tax_id_and_cnae_codes(self):
        self.assertIn("NIF: A50013465.", KALFRISA_PROFILE)
        self.assertIn("CNAE principal declarado para el radar: 2899.", KALFRISA_PROFILE)


class PartnerCatalogTests(unittest.TestCase):
    def test_catalog_has_sixteen_partners_with_required_fields(self):
        self.assertEqual(len(PARTNER_CATALOG), 16)
        for partner in PARTNER_CATALOG:
            for field in ("id", "name", "region", "capabilities",
                          "eu_experience", "prior_collaboration"):
                self.assertIn(field, partner)

    def test_funders_are_not_listed_as_technical_partners(self):
        partner_ids = {partner["id"] for partner in PARTNER_CATALOG}
        self.assertNotIn("cdti", partner_ids)
        self.assertNotIn("idae", partner_ids)

    def test_preselect_partners_ranks_aragon_and_prior_collaboration_higher(self):
        ranked = preselect_partners(["waste_heat"], limit=3)
        self.assertGreater(len(ranked), 0)
        top = ranked[0]
        self.assertIn("waste_heat", top["matching_capabilities"])
        self.assertEqual(top["id"], "circe")  # Aragón + colaboración previa + waste_heat directo

    def test_preselect_partners_expands_related_capabilities(self):
        # "thermal_processes" también debe recuperar socios de "combustion",
        # "cfd" o "industrial_demo" por la expansión de capacidades.
        ranked = preselect_partners(["thermal_processes"], limit=16)
        matched_ids = {partner["id"] for partner in ranked}
        self.assertIn("liftec", matched_ids)  # cfd, combustion

    def test_preselect_partners_respects_the_limit(self):
        ranked = preselect_partners(["digital_thermal", "waste_heat"], limit=2)
        self.assertLessEqual(len(ranked), 2)


if __name__ == "__main__":
    unittest.main()
