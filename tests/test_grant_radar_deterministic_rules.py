# Pruebas de grant_radar/deterministic_rules.py con import estándar (sin
# runpy). test_grant_radar.py (clase DeterministicPostAnalysisTests) ya
# cubre casos detallados de negocio contra fixtures reales; aquí se
# confirma el comportamiento base de cada salvaguarda de forma aislada.

import unittest

from grant_radar.deterministic_rules import (
    _correct_own_industrial_investment_scope,
    _deterministic_call_status,
    _derive_priority,
    _enforce_temporal_consistency,
    _funding_restricts_company_size,
    _normalize_model_manual_review,
    _own_industrial_investment_evidence,
    _resolve_consortium_requirement,
    apply_current_deterministic_rules,
)


class CallStatusTests(unittest.TestCase):
    def test_closed_bdns_status_wins_over_a_positive_deadline(self):
        self.assertEqual(
            _deterministic_call_status({"bdns_active_status": "closed", "deadline_days": 30}),
            "closed",
        )

    def test_unverified_status_is_unknown_not_closed_or_open(self):
        self.assertEqual(
            _deterministic_call_status({"bdns_active_status": "unverified_recent"}),
            "unknown",
        )

    def test_future_open_date_is_forthcoming(self):
        self.assertEqual(
            _deterministic_call_status({"open_date": "2099-01-01"}),
            "forthcoming",
        )


class PriorityTests(unittest.TestCase):
    def test_discarded_decisions_are_always_low_priority(self):
        self.assertEqual(_derive_priority(95, 95, "discard_out_of_scope"), "low")

    def test_high_actionability_and_confidence_is_high_priority(self):
        self.assertEqual(_derive_priority(80, 70, "pursue"), "high")


class OwnInvestmentSafeguardTests(unittest.TestCase):
    def test_no_evidence_means_no_correction(self):
        self.assertFalse(_own_industrial_investment_evidence({"programme": "Investigación básica"}))

    def test_correction_requires_the_discard_and_eligible_combination(self):
        facts = {"programme": "Adquisicion de maquinaria", "eligible_entity_types": ["empresa"]}
        evaluation = {
            "decision": "watch",  # no es discard_out_of_scope: no debe corregir
            "eligibility": "eligible",
            "eligibility_reason": "no es de i+d",
        }
        self.assertFalse(_correct_own_industrial_investment_scope(evaluation, facts))


class ConsortiumRequirementTests(unittest.TestCase):
    def test_explicit_mandatory_language_sets_true(self):
        facts = {"applicant_types": ["consorcio obligatorio de empresas"]}
        _resolve_consortium_requirement(facts)
        self.assertTrue(facts["consortium_required"])

    def test_individual_or_consortium_language_sets_false(self):
        facts = {"applicant_types": ["empresa individualmente o en consorcio"]}
        _resolve_consortium_requirement(facts)
        self.assertFalse(facts["consortium_required"])

    def test_no_signal_leaves_it_unset(self):
        facts = {"applicant_types": ["ninguna mención relevante aquí"]}
        _resolve_consortium_requirement(facts)
        self.assertIsNone(facts.get("consortium_required"))


class CompanySizeTests(unittest.TestCase):
    def test_inclusive_language_is_not_a_restriction(self):
        facts = {"eligible_entity_types": ["micro pequena mediana y gran empresa"]}
        self.assertFalse(_funding_restricts_company_size(facts))

    def test_sme_only_language_is_a_restriction(self):
        facts = {"eligible_entity_types": ["exclusivamente pyme"]}
        self.assertTrue(_funding_restricts_company_size(facts))


class TemporalConsistencyTests(unittest.TestCase):
    def test_removes_stale_wait_for_opening_when_call_is_already_open(self):
        conv = {"deadline_days": 30}
        evaluation = {"accion": "Esperar a la apertura antes de preparar la memoria."}
        _enforce_temporal_consistency(conv, evaluation)
        self.assertNotIn("Esperar a la apertura", evaluation["accion"])
        self.assertIn("documentación oficial ya publicada", evaluation["accion"])


class ManualReviewNormalizationTests(unittest.TestCase):
    def test_manual_review_becomes_watch(self):
        evaluation = {"decision": "manual_review", "accion": "Revisión manual requerida."}
        self.assertTrue(_normalize_model_manual_review(evaluation))
        self.assertEqual(evaluation["decision"], "watch")


class ApplyCurrentDeterministicRulesTests(unittest.TestCase):
    def test_ignores_records_without_a_usable_analysis_or_raw_document(self):
        record = {"analysis": None, "raw_document": {"title": "X"}}
        apply_current_deterministic_rules(record)  # no debe lanzar excepción
        self.assertIsNone(record["analysis"])

    def test_recomputes_tech_tags_and_derived_priority(self):
        record = {
            "raw_document": {
                "title": "Recuperación de calor residual industrial",
                "description": "Proyecto de recuperadores de calor en horno industrial.",
            },
            "analysis": {
                "decision": "pursue", "eligibility": "eligible",
                "fit_score": 80, "actionability_score": 80, "confidence": 70,
                "call_facts": {}, "dims": [], "scores": {},
            },
        }
        apply_current_deterministic_rules(record)
        self.assertIn("waste_heat", record["analysis"]["tech_tags"])
        self.assertEqual(record["analysis"]["priority"], "high")


if __name__ == "__main__":
    unittest.main()
