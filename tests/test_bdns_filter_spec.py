import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "bdns_filter_cases.json"


class BdnsFilterSpecificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.cases = cls.spec["cases"]
        cls.by_id = {case["id"]: case for case in cls.cases}

    def test_fixture_matches_the_production_filter(self):
        self.assertEqual(self.spec["spec_version"], 5)
        self.assertTrue(self.spec["production_filter_enabled"])
        self.assertGreaterEqual(len(self.cases), 25)

    def test_case_ids_are_unique_and_contract_is_complete(self):
        self.assertEqual(len(self.by_id), len(self.cases))
        allowed_decisions = {"retain", "hold_manual", "reject"}
        allowed_roles = {
            "direct_beneficiary", "consortium_partner", "cluster_route", "unknown",
        }
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["description"])
                self.assertIn(case["expected"]["decision"], allowed_decisions)
                self.assertIn(case["expected"]["opportunity_role"], allowed_roles)
                self.assertTrue(case["expected"]["reason_code"])
                self.assertIn("active_status", case["input"])

    def test_indirect_commercial_roles_are_never_retained(self):
        for case_id in (
            "indirect-commercial-funded-equipment",
            "primary-sector-indirect-commercial-role",
        ):
            with self.subTest(case=case_id):
                expected = self.by_id[case_id]["expected"]
                self.assertEqual(expected["decision"], "reject")
                self.assertEqual(expected["reason_code"], "indirect_commercial_role_only")
                self.assertEqual(expected["opportunity_role"], "unknown")

    def test_direct_investment_does_not_require_rd(self):
        for case_id in (
            "own-process-investment-without-rd",
            "own-energy-saving-investment-without-rd",
        ):
            with self.subTest(case=case_id):
                case = self.by_id[case_id]
                self.assertFalse(case["input"]["rd_required"])
                self.assertEqual(case["expected"]["decision"], "retain")
                self.assertEqual(
                    case["expected"]["opportunity_role"], "direct_beneficiary"
                )

    def test_consortium_partner_requires_direct_participation(self):
        case = self.by_id["consortium-partner-with-own-budget"]
        self.assertEqual(case["input"]["consortium_participation"], "own_work_and_budget")
        self.assertEqual(case["expected"]["decision"], "retain")
        self.assertEqual(case["expected"]["opportunity_role"], "consortium_partner")
        self.assertEqual(
            case["expected"]["visible_label"],
            self.spec["visible_labels"]["consortium_partner"],
        )

    def test_cluster_route_and_operations_are_distinguished(self):
        route = self.by_id["cluster-support-to-members"]["expected"]
        pilot = self.by_id["cluster-pilot-at-member-company"]["expected"]
        operating = self.by_id["cluster-operating-costs"]["expected"]
        unclear = self.by_id["cluster-role-unclear"]["expected"]
        self.assertEqual(route["opportunity_role"], "cluster_route")
        self.assertEqual(pilot["opportunity_role"], "cluster_route")
        self.assertEqual(operating["decision"], "reject")
        self.assertEqual(operating["reason_code"], "reject_cluster_operations")
        self.assertEqual(unclear["decision"], "hold_manual")

    def test_new_establishment_threshold_has_an_exact_boundary(self):
        threshold = self.spec["thresholds"]["new_establishment_min_execution_days"]
        below = self.by_id["new-centre-729-days"]
        boundary = self.by_id["new-centre-730-days"]
        unknown = self.by_id["new-centre-duration-unknown"]
        self.assertEqual(threshold, 730)
        self.assertEqual(below["input"]["project_execution_days"], threshold - 1)
        self.assertEqual(below["expected"]["decision"], "reject")
        self.assertEqual(boundary["input"]["project_execution_days"], threshold)
        self.assertEqual(boundary["expected"]["decision"], "retain")
        self.assertEqual(
            boundary["expected"]["visible_label"],
            self.spec["visible_labels"]["new_establishment"],
        )
        self.assertIsNone(unknown["input"]["project_execution_days"])
        self.assertEqual(unknown["expected"]["decision"], "hold_manual")

    def test_existing_establishment_requirement_precedes_long_duration(self):
        case = self.by_id["outside-aragon-existing-centre-required"]
        self.assertGreaterEqual(case["input"]["project_execution_days"], 730)
        self.assertEqual(case["expected"]["decision"], "reject")
        self.assertEqual(
            case["expected"]["reason_code"],
            "existing_establishment_required_outside_aragon",
        )

    def test_direct_award_mode_is_not_an_automatic_rejection(self):
        named = self.by_id["named-direct-grant"]
        open_scheme = self.by_id["open-direct-award-scheme"]
        instrumental = self.by_id["instrumental-direct-award"]
        self.assertEqual(named["expected"]["decision"], "reject")
        self.assertEqual(open_scheme["input"]["bdns_award_mode"], "direct")
        self.assertEqual(open_scheme["expected"]["decision"], "retain")
        self.assertEqual(instrumental["input"]["bdns_award_mode"], "direct_instrumental")
        self.assertEqual(instrumental["expected"]["reason_code"], "not_open_call")

    def test_sector_safeguards_cover_energy_waste_and_hydrogen(self):
        for case_id in (
            "energy-section-d", "waste-section-e",
            "extractive-plus-manufacturing", "tertiary-metadata-with-hydrogen",
        ):
            with self.subTest(case=case_id):
                self.assertEqual(self.by_id[case_id]["expected"]["decision"], "retain")
        self.assertEqual(
            self.by_id["extractive-section-b-only"]["expected"]["decision"],
            "reject",
        )

    def test_missing_active_evidence_never_becomes_a_synthetic_deadline(self):
        recent = self.by_id["recent-without-active-evidence"]["expected"]
        old = self.by_id["old-without-active-evidence"]["expected"]
        self.assertEqual(recent["decision"], "hold_manual")
        self.assertEqual(old["decision"], "reject")

    def test_intrinsic_exclusions_precede_vigency_and_stale_open_flags(self):
        stale = self.by_id["old-stale-api-open-flag"]
        residential = self.by_id["residential-before-vigency"]
        named = self.by_id["named-grant-before-vigency"]
        self.assertTrue(stale["input"]["api_open_flag"])
        self.assertEqual(stale["expected"]["reason_code"], "no_active_evidence")
        self.assertEqual(residential["input"]["active_status"], "unverified_recent")
        self.assertEqual(residential["expected"]["decision"], "reject")
        self.assertEqual(named["input"]["active_status"], "unverified_recent")
        self.assertEqual(named["expected"]["reason_code"], "not_open_call")


if __name__ == "__main__":
    unittest.main()
