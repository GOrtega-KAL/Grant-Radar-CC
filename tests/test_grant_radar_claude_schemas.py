# Pruebas de grant_radar/claude_schemas.py con import estándar (sin runpy).

import unittest

from grant_radar.claude_schemas import (
    BdnsHoldFacts,
    CallEvaluation,
    CallFacts,
    ClaudeAnalysisError,
    FundingLineFacts,
    STRUCTURED_SCHEMA_MAX_OPTIONAL_FIELDS,
    STRUCTURED_SCHEMA_MAX_UNION_FIELDS,
    normalize_call_facts,
    structured_schema_complexity,
    validate_structured_output_schema,
)


def _minimal_call_facts(**overrides) -> CallFacts:
    base = dict(
        call_status="open", programme="", action_type="",
        applicant_types=[], eligible_geographies=[], eligible_entity_types=[],
        eligibility_evidence=[], budget_total_eur=-1, funding_rate_percent=-1,
        project_budget_eur=-1, project_cost_min_eur=-1, grant_max_eur=-1,
        deadline_date="", trl_min=0, trl_max=0, trl_source="",
        consortium_required="unknown", consortium_evidence="",
        required_topics=[], eligible_actions=[], expected_outcomes=[],
        funding_lines=[], evidence=[], missing_fields=[],
    )
    base.update(overrides)
    return CallFacts(**base)


class SchemaComplianceTests(unittest.TestCase):
    """AGENTS.md exige cero opcionales y cero uniones en ambos esquemas
    principales; estos tests fallarían si un cambio futuro añadiera un
    campo `Optional`/`| None` sin darse cuenta de que rompe ese límite."""

    def test_call_facts_has_no_optional_or_union_fields(self):
        metrics = structured_schema_complexity(CallFacts)
        self.assertEqual(metrics["optional_fields"], 0)
        self.assertEqual(metrics["union_fields"], 0)

    def test_call_evaluation_has_no_optional_or_union_fields(self):
        metrics = structured_schema_complexity(CallEvaluation)
        self.assertEqual(metrics["optional_fields"], 0)
        self.assertEqual(metrics["union_fields"], 0)

    def test_bdns_hold_facts_has_no_optional_or_union_fields(self):
        metrics = structured_schema_complexity(BdnsHoldFacts)
        self.assertEqual(metrics["optional_fields"], 0)
        self.assertEqual(metrics["union_fields"], 0)

    def test_validate_passes_well_within_the_published_limits(self):
        for model in (CallFacts, CallEvaluation, BdnsHoldFacts):
            with self.subTest(model=model.__name__):
                metrics = validate_structured_output_schema(model)
                self.assertLessEqual(
                    metrics["optional_fields"], STRUCTURED_SCHEMA_MAX_OPTIONAL_FIELDS
                )
                self.assertLessEqual(
                    metrics["union_fields"], STRUCTURED_SCHEMA_MAX_UNION_FIELDS
                )


class SentinelNormalizationTests(unittest.TestCase):
    def test_empty_string_sentinels_become_none(self):
        facts = normalize_call_facts(_minimal_call_facts(programme=""))
        self.assertIsNone(facts["programme"])

    def test_negative_number_sentinels_become_none(self):
        facts = normalize_call_facts(_minimal_call_facts(budget_total_eur=-1))
        self.assertIsNone(facts["budget_total_eur"])

    def test_positive_values_are_preserved(self):
        facts = normalize_call_facts(_minimal_call_facts(
            programme="INNOVAE", budget_total_eur=50000, trl_min=4, trl_max=7,
        ))
        self.assertEqual(facts["programme"], "INNOVAE")
        self.assertEqual(facts["budget_total_eur"], 50000)
        self.assertEqual(facts["trl_min"], 4)

    def test_consortium_required_sentinel_maps_to_boolean_or_none(self):
        self.assertIsNone(
            normalize_call_facts(_minimal_call_facts(consortium_required="unknown"))
            ["consortium_required"]
        )
        self.assertTrue(
            normalize_call_facts(_minimal_call_facts(consortium_required="yes"))
            ["consortium_required"]
        )

    def test_funding_line_sentinels_are_normalized_too(self):
        line = FundingLineFacts(
            name="Línea A", scope="", applicant_types=[], eligible_entity_types=[],
            eligible_cnae=[], eligible_actions=[], requirements=[],
            budget_total_eur=-1, project_cost_min_eur=-1, grant_max_eur=-1,
            funding_rate_percent=-1, deadline_date="", consortium_required="no",
            evidence=[],
        )
        facts = normalize_call_facts(_minimal_call_facts(funding_lines=[line]))
        self.assertIsNone(facts["funding_lines"][0]["scope"])
        self.assertFalse(facts["funding_lines"][0]["consortium_required"])


class ClaudeAnalysisErrorTests(unittest.TestCase):
    def test_carries_partial_usages_for_billing_accounting(self):
        error = ClaudeAnalysisError("fallo", partial_usages=[{"input_tokens": 10}])
        self.assertEqual(error.partial_usages, [{"input_tokens": 10}])
        self.assertEqual(str(error), "fallo")

    def test_defaults_to_an_empty_usage_list(self):
        self.assertEqual(ClaudeAnalysisError("fallo").partial_usages, [])


if __name__ == "__main__":
    unittest.main()
