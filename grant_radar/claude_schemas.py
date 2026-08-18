# claude_schemas.py — esquemas de salida estructurada de Claude
#
# Define lo que Claude debe devolver (CallFacts, CallEvaluation...) y lo
# valida contra los límites publicados de Anthropic para salidas
# estructuradas (24 campos opcionales, 16 uniones) sin necesidad de hacer
# una petición real. AGENTS.md exige mantener ambos esquemas en cero
# opcionales y cero uniones: por eso los campos usan centinelas ("", -1,
# "unknown") en vez de `None`/`Optional`; `normalize_call_facts()` convierte
# esos centinelas a `None` para el resto del pipeline justo después de
# recibir la respuesta.
#
# No depende de nada más del proyecto — solo de pydantic y la librería
# estándar — por lo que fue un candidato de bajo riesgo para extraer.

import json
from typing import Literal

from pydantic import BaseModel, Field

# Límite publicado por Anthropic para salidas estructuradas. Ver AGENTS.md,
# sección 4: "actualmente ambos esquemas deben mantener cero opcionales y
# cero uniones", con margen respecto a este límite.
STRUCTURED_SCHEMA_MAX_OPTIONAL_FIELDS = 24
STRUCTURED_SCHEMA_MAX_UNION_FIELDS = 16


class ClaudeAnalysisError(RuntimeError):
    """Error fatal con trazabilidad opcional de llamadas ya completadas."""

    def __init__(self, message: str, partial_usages: list[dict] | None = None):
        super().__init__(message)
        self.partial_usages = list(partial_usages or [])


class FundingLineFacts(BaseModel):
    name: str
    scope: str
    applicant_types: list[str]
    eligible_entity_types: list[str]
    eligible_cnae: list[str]
    eligible_actions: list[str]
    requirements: list[str]
    budget_total_eur: float = Field(ge=-1)
    project_cost_min_eur: float = Field(ge=-1)
    grant_max_eur: float = Field(ge=-1)
    funding_rate_percent: float = Field(ge=-1, le=100)
    deadline_date: str
    consortium_required: Literal["yes", "no", "unknown"]
    evidence: list[str]


class CallFacts(BaseModel):
    """Hechos generales y líneas con centinelas no anulables."""
    call_status: Literal["open", "forthcoming", "closed", "unknown"]
    programme: str
    action_type: str
    applicant_types: list[str]
    eligible_geographies: list[str]
    eligible_entity_types: list[str]
    eligibility_evidence: list[str]
    budget_total_eur: float = Field(ge=-1)
    funding_rate_percent: float = Field(ge=-1, le=100)
    project_budget_eur: float = Field(ge=-1)
    project_cost_min_eur: float = Field(ge=-1)
    grant_max_eur: float = Field(ge=-1)
    deadline_date: str
    trl_min: int = Field(ge=0, le=9)
    trl_max: int = Field(ge=0, le=9)
    trl_source: str
    consortium_required: Literal["yes", "no", "unknown"]
    consortium_evidence: str
    required_topics: list[str]
    eligible_actions: list[str]
    expected_outcomes: list[str]
    funding_lines: list[FundingLineFacts]
    evidence: list[str]
    missing_fields: list[str]


class EvaluationScores(BaseModel):
    technological_fit: int = Field(ge=0, le=100)
    strategic_fit: int = Field(ge=0, le=100)
    role_fit: int = Field(ge=0, le=100)
    trl_fit: int = Field(ge=0, le=100)
    consortium_readiness: int = Field(ge=0, le=100)


class CallEvaluation(BaseModel):
    fit_score: int = Field(ge=0, le=100)
    actionability_score: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    decision: Literal[
        "pursue", "watch", "manual_review",
        "discard_out_of_scope", "discard_ineligible",
    ]
    eligibility: Literal["eligible", "ineligible", "unknown"]
    eligibility_reason: str
    recommended_role: Literal[
        "leader", "technology_partner", "industrial_demonstrator",
        "consortium_partner", "not_applicable", "unknown",
    ]
    scores: EvaluationScores
    evidence_quality: Literal["high", "medium", "low"]
    positive_evidence: list[str]
    risks_and_unknowns: list[str]
    partner_needs: list[str]
    recommended_partner_ids: list[str]
    resumen: str
    accion: str
    tags: list[str]


class BdnsHoldFacts(BaseModel):
    """Respuesta factual mínima para resolver una única causa `hold_manual`."""
    call_status: Literal["open", "forthcoming", "open_ended", "closed", "unknown"]
    deadline_date: str
    territorial_condition: Literal[
        "existing_establishment", "project_location_only",
        "new_establishment_allowed", "no_restriction", "unknown",
    ]
    execution_days: int = Field(ge=-1)
    consortium_participation: Literal["yes", "no", "unknown"]
    cluster_support_to_members: Literal["yes", "no", "unknown"]
    evidence_quote: str
    evidence_source_url: str
    confidence: int = Field(ge=0, le=100)
    explanation: str


def structured_schema_complexity(output_model: type[BaseModel]) -> dict:
    """Cuenta límites explícitos de Anthropic sin realizar una petición API."""
    schema = output_model.model_json_schema()
    optional_fields = 0
    union_fields = 0

    def walk(value) -> None:
        nonlocal optional_fields, union_fields
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                required = set(value.get("required", []))
                optional_fields += sum(
                    property_name not in required
                    for property_name in properties
                )
            if isinstance(value.get("anyOf"), list):
                union_fields += 1
            if isinstance(value.get("type"), list):
                union_fields += 1
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(schema)
    return {
        "model": output_model.__name__,
        "optional_fields": optional_fields,
        "union_fields": union_fields,
        "schema_characters": len(json.dumps(schema, ensure_ascii=False)),
    }


def validate_structured_output_schema(output_model: type[BaseModel]) -> dict:
    """Falla localmente si el esquema supera los límites publicados."""
    metrics = structured_schema_complexity(output_model)
    violations = []
    if metrics["optional_fields"] > STRUCTURED_SCHEMA_MAX_OPTIONAL_FIELDS:
        violations.append(
            f"{metrics['optional_fields']} campos opcionales "
            f"(máximo {STRUCTURED_SCHEMA_MAX_OPTIONAL_FIELDS})"
        )
    if metrics["union_fields"] > STRUCTURED_SCHEMA_MAX_UNION_FIELDS:
        violations.append(
            f"{metrics['union_fields']} campos con uniones "
            f"(máximo {STRUCTURED_SCHEMA_MAX_UNION_FIELDS})"
        )
    if violations:
        raise ClaudeAnalysisError(
            f"Esquema estructurado {metrics['model']} incompatible con Claude: "
            + "; ".join(violations)
        )
    return metrics


def normalize_call_facts(facts_model: CallFacts) -> dict:
    """Convierte los centinelas del esquema compacto al contrato interno."""
    facts = facts_model.model_dump()
    for field_name in (
        "programme", "action_type", "deadline_date", "trl_source",
        "consortium_evidence",
    ):
        if not str(facts.get(field_name, "")).strip():
            facts[field_name] = None
    for field_name in (
        "budget_total_eur", "funding_rate_percent", "project_budget_eur",
        "project_cost_min_eur", "grant_max_eur",
    ):
        if facts.get(field_name, -1) < 0:
            facts[field_name] = None
    for field_name in ("trl_min", "trl_max"):
        if facts.get(field_name, 0) <= 0:
            facts[field_name] = None
    facts["consortium_required"] = {
        "yes": True,
        "no": False,
        "unknown": None,
    }[facts["consortium_required"]]

    for line in facts.get("funding_lines", []):
        if not str(line.get("scope", "")).strip():
            line["scope"] = None
        if not str(line.get("deadline_date", "")).strip():
            line["deadline_date"] = None
        for field_name in (
            "budget_total_eur", "project_cost_min_eur", "grant_max_eur",
            "funding_rate_percent",
        ):
            if line.get(field_name, -1) < 0:
                line[field_name] = None
        line["consortium_required"] = {
            "yes": True,
            "no": False,
            "unknown": None,
        }[line["consortium_required"]]
    return facts
