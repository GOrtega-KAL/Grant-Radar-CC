# deterministic_rules.py — salvaguardas deterministas posteriores al modelo
#
# Estas funciones corrigen sesgos conocidos de Haiku sobre un análisis ya
# generado (o ya cacheado): por ejemplo, confundir un consorcio obligatorio
# con una incompatibilidad de entidad, o descartar una inversión propia solo
# porque no tiene componente de I+D. No deciden si una convocatoria entra en
# el pipeline (eso es `_bdns_pre_claude_gate()` y `deterministic_prefilter()`,
# que siguen en Grant-Radar-prueba.py): actúan después, sobre hechos y
# evaluación ya extraídos.
#
# Se extrajo junto con grant_radar/cache.py porque están acopladas:
# `filter_usable_cache()` (cache.py) llama a `apply_current_deterministic_rules()`
# (este archivo) cada vez que carga una entrada de caché, para reaplicar las
# reglas vigentes sin gastar una nueva llamada a Claude. Ver AGENTS.md,
# sección 4 y secciones 13-20, para el porqué de cada regla — están
# documentadas ahí con más detalle del que cabe en comentarios de código.
#
# `apply_current_deterministic_rules()` es la función que orquesta todo el
# módulo; es la única que se llama desde fuera.

import re
from datetime import datetime

from grant_radar.parsing_helpers import _fold_text
from grant_radar.tech_taxonomy import _compat_tags_for, detect_tech_tags

# Términos de inversión industrial propia (suelo, maquinaria, procesos...)
# que _own_industrial_investment_evidence() busca en los hechos extraídos.
# También la usa deterministic_prefilter() en Grant-Radar-prueba.py, antes
# de llegar a Claude; por eso vive aquí y se reimporta allí, en vez de
# duplicarla.
BDNS_DIRECT_OWN_INVESTMENT_TERMS = (
    "adquisicion de suelo industrial", "adquisicion de maquinaria",
    "adquisicion de equipos", "inversion en maquinaria", "inversion en equipos",
    "inversion en instalaciones", "inversion productiva", "activos productivos",
    "ampliacion productiva", "ampliacion de instalaciones",
    "ampliacion del centro empresarial", "aumento de superficie",
    "traslado a poligono", "traslado a area industrial", "mejora de procesos",
    "modernizacion de procesos", "transformacion productiva", "automatizacion",
    "digitalizacion industrial", "ahorro energetico", "eficiencia energetica",
    "reduccion de emisiones", "valorizacion de residuos",
    "tratamiento de residuos",
)


def _deterministic_call_status(conv: dict) -> str:
    """Estado de vigencia (abierta/cerrada/próxima/desconocida) sin IA."""
    bdns_status = str(conv.get("bdns_active_status", ""))
    if bdns_status == "closed":
        return "closed"
    if bdns_status in {"unverified_recent", "unverified_old"}:
        return "unknown"
    if bdns_status == "open_ended":
        return "open"
    deadline_days = conv.get("deadline_days")
    if isinstance(deadline_days, (int, float)) and deadline_days <= 0:
        return "closed"
    open_date = str(conv.get("open_date", ""))
    if open_date:
        try:
            if datetime.fromisoformat(open_date[:10]).date() > datetime.now().date():
                return "forthcoming"
        except ValueError:
            pass
    if conv.get("deadline_date") or (
        isinstance(deadline_days, (int, float)) and deadline_days > 0
    ):
        return "open"
    return "unknown"


def _derive_priority(actionability: int, confidence: int, decision: str) -> str:
    if decision.startswith("discard_"):
        return "low"
    if actionability >= 75 and confidence >= 60:
        return "high"
    if actionability >= 45:
        return "medium"
    return "low"


def _own_industrial_investment_evidence(facts: dict) -> bool:
    """Reconoce inversión directa en activos o capacidad industrial de Kalfrisa."""
    evidence_values = [
        facts.get("programme", ""),
        facts.get("action_type", ""),
        *facts.get("eligibility_evidence", []),
        *facts.get("required_topics", []),
        *facts.get("expected_outcomes", []),
        *facts.get("evidence", []),
    ]
    for line in facts.get("funding_lines", []):
        evidence_values.extend([
            line.get("name", ""), line.get("scope", ""),
            *line.get("requirements", []), *line.get("evidence", []),
        ])
    evidence = _fold_text(" ".join(str(value) for value in evidence_values))
    if not any(term in evidence for term in BDNS_DIRECT_OWN_INVESTMENT_TERMS):
        return False

    entities = _fold_text(" ".join(
        str(value) for value in (
            facts.get("eligible_entity_types", [])
            + facts.get("applicant_types", [])
        )
    ))
    company_markers = (
        "empresa", "company", "companies", "pyme", "pymes", "sme", "smes",
        "persona juridica", "entidad privada", "actividad economica",
    )
    if not any(marker in entities for marker in company_markers):
        return False

    geographies = _fold_text(" ".join(
        str(value) for value in facts.get("eligible_geographies", [])
    ))
    compatible_geography = (
        "aragon", "zaragoza", "espana", "spain", "nacional", "national",
        "union europea", "european union", "member state", "estados miembros",
    )
    if geographies and not any(marker in geographies for marker in compatible_geography):
        return False
    return True


def _correct_own_industrial_investment_scope(
    evaluation: dict,
    facts: dict,
) -> bool:
    """
    Evita descartar una inversión propia solo porque no contiene I+D.

    La regla no convierte en oportunidad una ayuda para clientes ni relaja una
    incompatibilidad territorial o de entidad: exige beneficiario empresarial,
    geografía compatible, elegibilidad positiva y evidencia factual del activo.
    """
    if (
        evaluation.get("decision") != "discard_out_of_scope"
        or evaluation.get("eligibility") != "eligible"
        or not _own_industrial_investment_evidence(facts)
    ):
        return False
    dismissal_text = _fold_text(" ".join([
        str(evaluation.get("resumen", "")),
        str(evaluation.get("summary", "")),
        str(evaluation.get("eligibility_reason", "")),
        str(evaluation.get("accion", "")),
        str(evaluation.get("action", "")),
        *[str(value) for value in evaluation.get("risks_and_unknowns", [])],
    ]))
    innovation_only_markers = (
        "no es de i+d", "no de i+d", "no en i+d", "fuera del foco de i+d",
        "sin i+d", "not r&d", "no hay componente de desarrollo",
        "sin innovacion", "without innovation", "no innovation",
        "no de desarrollo tecnologico", "sin desarrollo tecnologico",
    )
    if not any(marker in dismissal_text for marker in innovation_only_markers):
        return False

    evaluation["decision"] = "watch"
    evaluation["recommended_role"] = "leader"
    evaluation["fit_score"] = max(int(evaluation.get("fit_score", 0) or 0), 55)
    evaluation["match_score"] = evaluation["fit_score"]
    evaluation["match"] = evaluation["fit_score"]
    evaluation["actionability_score"] = max(
        int(evaluation.get("actionability_score", 0) or 0), 35
    )
    evaluation["confidence"] = max(int(evaluation.get("confidence", 0) or 0), 60)
    evaluation["resumen"] = (
        "Financia una inversión directa en activos, instalaciones o capacidad "
        "industrial de Kalfrisa. No requiere un componente de I+D para ser "
        "relevante; su utilidad depende de que exista una necesidad real de "
        "inversión compatible con los gastos y plazos de la convocatoria."
    )
    evaluation["accion"] = (
        "Contrastar la inversión elegible con el plan industrial de Kalfrisa y "
        "cuantificar coste, ayuda y calendario antes de decidir la solicitud."
    )
    scores = evaluation.get("scores")
    if isinstance(scores, dict):
        scores["strategic_fit"] = max(int(scores.get("strategic_fit", 0) or 0), 60)
        scores["role_fit"] = max(int(scores.get("role_fit", 0) or 0), 70)
    positive = list(evaluation.get("positive_evidence", []))
    positive.append(
        "La convocatoria financia inversión propia en capacidad o instalaciones industriales."
    )
    evaluation["positive_evidence"] = list(dict.fromkeys(positive))
    risks = [
        risk for risk in evaluation.get("risks_and_unknowns", [])
        if not any(marker in _fold_text(risk) for marker in innovation_only_markers)
    ]
    risks.append(
        "Confirmar que Kalfrisa tiene una necesidad real y presupuestada de la inversión elegible."
    )
    evaluation["risks_and_unknowns"] = list(dict.fromkeys(risks))
    return True


def _direct_funded_valorisation_evidence(
    conv: dict,
    facts: dict,
    tech_tags: list[str] | None = None,
) -> bool:
    """Prueba una vía financiada directa para aportar tecnología de valorización."""
    tags = set(tech_tags if tech_tags is not None else conv.get("tech_tags", []))
    if "thermal_waste" not in tags:
        return False
    evidence_values = [
        facts.get("programme", ""), facts.get("action_type", ""),
        *facts.get("applicant_types", []), *facts.get("eligible_entity_types", []),
        *facts.get("eligibility_evidence", []), *facts.get("required_topics", []),
        *facts.get("expected_outcomes", []), *facts.get("evidence", []),
    ]
    applicant_values = [
        *facts.get("applicant_types", []), *facts.get("eligible_entity_types", []),
        *facts.get("eligibility_evidence", []),
    ]
    for line in facts.get("funding_lines", []):
        evidence_values.extend([
            line.get("name", ""), line.get("scope", ""),
            *line.get("applicant_types", []),
            *line.get("eligible_entity_types", []),
            *line.get("requirements", []), *line.get("evidence", []),
        ])
        applicant_values.extend([
            *line.get("applicant_types", []),
            *line.get("eligible_entity_types", []),
        ])
    evidence = _fold_text(" ".join(str(value) for value in evidence_values))
    applicant_evidence = _fold_text(" ".join(
        str(value) for value in applicant_values
    ))
    valorisation_markers = (
        "valorizacion", "valorisation", "valorization", "waste", "residuo",
        "side-stream", "side stream", "by-product", "subproducto", "biomass",
        "biomasa",
    )
    direct_technology_applicant_patterns = (
        r"(?:sme|smes|pyme|pymes|empresa|companies).{0,100}"
        r"(?:offering|providing|aportan|ofrecen).{0,80}"
        r"(?:solution|technology|solucion|tecnolog)",
        r"(?:technology|solution|tecnolog|solucion).{0,80}"
        r"(?:provider|providers|supplier|empresa|sme|pyme)",
    )
    has_direct_applicant = any(
        re.search(pattern, applicant_evidence)
        for pattern in direct_technology_applicant_patterns
    )
    has_grant = any(
        isinstance(facts.get(field), (int, float)) and facts.get(field, 0) > 0
        for field in ("budget_total_eur", "grant_max_eur")
    ) or any(
        isinstance(line.get("grant_max_eur"), (int, float))
        and line.get("grant_max_eur", 0) > 0
        for line in facts.get("funding_lines", [])
    )
    return (
        any(marker in evidence for marker in valorisation_markers)
        and has_direct_applicant
        and has_grant
    )


def _correct_direct_valorisation_scope(
    evaluation: dict,
    facts: dict,
    conv: dict,
    tech_tags: list[str] | None = None,
) -> bool:
    """
    Conserva la valorización cuando Kalfrisa puede ser participante financiado.

    No basta con poder vender equipos a un beneficiario. La convocatoria debe
    admitir expresamente proveedores tecnológicos como solicitantes o socios con
    subvención propia y debe existir conexión de valorización térmica.
    """
    if (
        evaluation.get("decision") != "discard_out_of_scope"
        or evaluation.get("eligibility") == "ineligible"
        or not _direct_funded_valorisation_evidence(conv, facts, tech_tags)
    ):
        return False
    reason_text = _fold_text(" ".join([
        str(evaluation.get("resumen", "")),
        str(evaluation.get("summary", "")),
        str(evaluation.get("eligibility_reason", "")),
        str(evaluation.get("accion", "")),
        str(evaluation.get("action", "")),
        *[str(value) for value in evaluation.get("risks_and_unknowns", [])],
    ]))
    mistaken_supplier_markers = (
        "proveedor marginal", "proveedor tecnologico", "proveedores de equipos",
        "technology provider", "technology supplier", "supplier role",
        "rol potencial como proveedor", "requeriria un beneficiario",
    )
    sector_mismatch_markers = (
        "no coincide con el perfil", "fuera del foco", "sector agroalimentario",
        "agri-food", "agroalimentaria", "biomasa",
    )
    if not any(marker in reason_text for marker in sector_mismatch_markers):
        return False

    evaluation["decision"] = "watch"
    evaluation["recommended_role"] = "technology_partner"
    evaluation["fit_score"] = max(int(evaluation.get("fit_score", 0) or 0), 60)
    evaluation["match_score"] = evaluation["fit_score"]
    evaluation["match"] = evaluation["fit_score"]
    evaluation["actionability_score"] = max(
        int(evaluation.get("actionability_score", 0) or 0), 45
    )
    evaluation["confidence"] = max(int(evaluation.get("confidence", 0) or 0), 65)
    evaluation["resumen"] = (
        "Convocatoria de valorización con conexión térmica explícita que admite "
        "a proveedores de soluciones o tecnología como participantes financiados. "
        "El sector de aplicación no excluye a Kalfrisa cuando aporta desarrollo, "
        "costes y trabajo propios al proyecto."
    )
    evaluation["accion"] = (
        "Definir una actuación propia de valorización térmica, confirmar la "
        "elegibilidad empresarial y comprobar que presupuesto, costes y resultados "
        "de Kalfrisa quedan financiados directamente."
    )
    scores = evaluation.get("scores")
    if isinstance(scores, dict):
        scores["technological_fit"] = max(
            int(scores.get("technological_fit", 0) or 0), 65
        )
        scores["role_fit"] = max(int(scores.get("role_fit", 0) or 0), 60)
    positive = list(evaluation.get("positive_evidence", []))
    positive.append(
        "La convocatoria admite expresamente proveedores tecnológicos como participantes financiados."
    )
    evaluation["positive_evidence"] = list(dict.fromkeys(positive))
    risks = [
        risk for risk in evaluation.get("risks_and_unknowns", [])
        if not any(marker in _fold_text(risk) for marker in mistaken_supplier_markers)
    ]
    risks.append(
        "La participación debe incluir actividad, costes y resultados propios; una venta de equipos no basta."
    )
    evaluation["risks_and_unknowns"] = list(dict.fromkeys(risks))
    return True


def _normalize_model_manual_review(evaluation: dict) -> bool:
    """Convierte la indecisión del modelo en monitorización, no en tarea humana."""
    if evaluation.get("decision") != "manual_review":
        return False
    evaluation["decision"] = "watch"
    action = str(evaluation.get("accion", ""))
    action = re.sub(
        r"^\s*(?:revisi[oó]n|comprobaci[oó]n) manual (?:requerida|necesaria)[.:]?\s*",
        "Monitorizar y completar automáticamente la evidencia pendiente. ",
        action,
        flags=re.IGNORECASE,
    )
    evaluation["accion"] = action.strip() or (
        "Monitorizar y completar automáticamente la evidencia pendiente antes "
        "de preparar la candidatura."
    )
    return True


# Marcadores de Aragón en un código NUTS o en su etiqueta. `es24` cubre también
# las provincias (`es241` Huesca, `es242` Teruel, `es243` Zaragoza) porque se
# busca como subcadena, no como código exacto.
_ARAGON_REGION_MARKERS = ("es24", "aragon", "zaragoza", "huesca", "teruel")


def _explicit_other_region_only(facts: dict, conv: dict) -> str:
    """Devuelve la región española excluyente declarada, o cadena vacía.

    Decide sobre el campo `regiones` de la API de BDNS —dato oficial— y, si no
    llega, sobre las geografías que extrajo el modelo. Nunca sobre la prosa:
    hasta el 31/08/2026 esta comprobación exigía que el razonamiento del modelo
    contuviera una de seis expresiones tecleadas a mano («restriccion
    geografica», «esta en zaragoza»…), y como el modelo redacta distinto cada
    vez, disparaba en 1 de cada 12 casos reales. Los otros 11 se publicaban
    como «elegibilidad por confirmar» diciendo en el propio texto que la
    convocatoria se limita a Navarra, Cataluña o Murcia.

    Dos guardas conservadoras, ambas medidas sobre el corpus real:
    `ES - ESPAÑA` (convocatoria nacional) no lleva código de región y no
    dispara; y si Aragón aparece entre las regiones admitidas, tampoco.
    """
    regions = conv.get("bdns_regions") or facts.get("eligible_geographies") or []
    folded = _fold_text(" ".join(str(value) for value in regions))
    # Un código más fino que el país: ES3, ES51, ES243... `ES` a secas es
    # ámbito nacional y queda fuera a propósito.
    if not re.search(r"\bes\d{1,3}\b", folded):
        return ""
    if any(marker in folded for marker in _ARAGON_REGION_MARKERS):
        return ""
    return ", ".join(str(value) for value in regions)


def _enforce_explicit_regional_ineligibility(
    evaluation: dict,
    facts: dict,
    conv: dict,
) -> bool:
    """Descarta una convocatoria territorial de otra comunidad autónoma."""
    if str(conv.get("source", "")).upper() != "BDNS":
        return False
    other_region = _explicit_other_region_only(facts, conv)
    if not other_region:
        return False
    evaluation["eligibility"] = "ineligible"
    # El motivo publicado debe decir por qué se descarta. Se antepone el hecho
    # territorial solo si no está ya: cuando el modelo lo explica —y suele
    # hacerlo, aunque luego no concluya— su redacción es mejor que esta, y
    # cuando no, aquí ya ha pasado _remove_unfounded_size_checks() y puede
    # haber dejado una frase genérica sobre requisitos pendientes.
    previous_reason = str(evaluation.get("eligibility_reason", "")).strip()
    region_tokens = [
        token for token in re.split(r"[^a-z0-9]+", _fold_text(other_region))
        if len(token) > 2
    ]
    if not any(token in _fold_text(previous_reason) for token in region_tokens):
        territorial_reason = (
            f"Convocatoria territorial limitada a {other_region}; Kalfrisa "
            "tiene su establecimiento en Zaragoza (ES243, Aragón)."
        )
        evaluation["eligibility_reason"] = (
            f"{territorial_reason} {previous_reason}".strip()
        )
    evaluation["decision"] = "discard_ineligible"
    evaluation["recommended_role"] = "not_applicable"
    evaluation["accion"] = (
        "Descartar por restricción regional expresa. Reconsiderar solo si unas "
        "bases futuras admiten ejecución en Aragón o participación financiada "
        "directa sin establecimiento previo en la región convocante."
    )
    return True


def _data_gap_reasons(facts: dict, evaluation: dict) -> list[str]:
    """Datos factuales ausentes; reducen certeza, pero no exigen decisión humana."""
    reasons = []
    if evaluation["decision"].startswith("discard_"):
        return reasons
    if evaluation["eligibility"] == "unknown":
        reasons.append("eligibility_unknown")
    if not any(
        isinstance(facts.get(field), (int, float)) and facts.get(field, 0) > 0
        for field in (
            "budget_total_eur", "project_budget_eur", "project_cost_min_eur",
            "grant_max_eur",
        )
    ):
        reasons.append("budget_missing")
    if (
        facts.get("consortium_required") is None
        and not _own_industrial_investment_evidence(facts)
    ):
        reasons.append("consortium_requirement_missing")
    return reasons


def _monitoring_flags(conv: dict, evaluation: dict) -> list[str]:
    """Prioridades automáticas que no representan revisión de compatibilidad."""
    flags = []
    if evaluation["decision"].startswith("discard_"):
        return flags
    if evaluation["fit_score"] >= 70 and evaluation["confidence"] < 60:
        flags.append("high_fit_low_confidence")
    deadline_days = conv.get("deadline_days")
    if isinstance(deadline_days, (int, float)) and 0 < deadline_days < 15:
        flags.append("deadline_under_15_days")
    if evaluation["fit_score"] >= 85:
        flags.append("strategic_high_fit")
    return flags


def _review_reasons(evaluation: dict) -> list[str]:
    """Reserva la revisión real para contradicciones entre modelo y reglas."""
    return list(dict.fromkeys(
        reason for reason in evaluation.get("review_reasons", [])
        if reason == "rule_model_discrepancy"
    ))


def _required_consortium_member_category(facts: dict) -> str:
    """
    Detecta una categoria que debe estar representada en el consorcio.

    No equivale a restringir todos los beneficiarios a esa categoria. Se exige
    lenguaje compositivo explicito para no relajar requisitos de solicitante.
    """
    if facts.get("consortium_required") is not True:
        return ""
    evidence_values = list(facts.get("eligibility_evidence", []))
    evidence_values.extend([
        facts.get("consortium_evidence", ""),
        *facts.get("evidence", []),
    ])
    for line in facts.get("funding_lines", []):
        evidence_values.extend(line.get("evidence", []))
        evidence_values.extend(line.get("requirements", []))
    evidence = _fold_text(" ".join(str(value) for value in evidence_values))
    composition_patterns = (
        r"\bat least one\b.{0,180}\b(?:must|shall|should)\b.{0,100}"
        r"\b(?:part|member) of (?:the )?consorti",
        r"\b(?:consortium|consortia)\b.{0,80}\b(?:must|shall|should)\b"
        r".{0,80}\b(?:include|comprise|involve)\b",
        r"\b(?:organisation|organization|entity)\b.{0,120}"
        r"\b(?:must|shall|should) be part of (?:the )?consorti",
        r"\bal menos (?:una|un)\b.{0,180}\bdebera?\b.{0,100}"
        r"\b(?:formar parte|integrarse)\b.{0,50}\bconsorcio",
        r"\bconsorcio\b.{0,80}\bdebera?\b.{0,80}"
        r"\b(?:incluir|estar integrado|contar con)\b",
    )
    if not any(re.search(pattern, evidence) for pattern in composition_patterns):
        return ""
    entity_types = [
        str(value).strip()
        for value in facts.get("eligible_entity_types", [])
        if str(value).strip()
    ]
    return entity_types[0] if len(entity_types) == 1 else "miembro especializado"


def _hard_ineligibility(facts: dict) -> str | None:
    """Descarta solo exclusiones de tipo de entidad expresas y conservadoras."""
    entity_types = [
        _fold_text(value)
        for value in facts.get("eligible_entity_types", [])
        + facts.get("applicant_types", [])
        if str(value).strip()
    ]
    if not entity_types:
        return None
    company_markers = (
        "empresa", "empresas", "company", "companies", "sme", "smes",
        "pyme", "pymes", "private entity", "entidad privada",
    )
    if any(marker in value for value in entity_types for marker in company_markers):
        return None
    if _required_consortium_member_category(facts):
        return None
    excluded_markers = (
        "persona fisica", "individual", "municip", "ayuntamiento",
        "public authorit", "administracion publica", "universit",
        "research organisation", "organismo de investigacion",
        "non-profit", "sin animo de lucro",
    )
    if all(any(marker in value for marker in excluded_markers) for value in entity_types):
        return (
            "Los tipos de solicitante extraídos no incluyen empresas privadas; "
            "Kalfrisa queda fuera de la elegibilidad expresa."
        )
    return None


def _funding_restricts_company_size(facts: dict) -> bool:
    """Detecta restricciones de tamaño expresas; nunca las infiere del perfil."""
    values = (
        facts.get("eligible_entity_types", [])
        + facts.get("applicant_types", [])
        + facts.get("eligibility_evidence", [])
    )
    for line in facts.get("funding_lines", []):
        values.extend(line.get("eligible_entity_types", []))
        values.extend(line.get("applicant_types", []))
        values.extend(line.get("requirements", []))
    text = _fold_text(" ".join(str(value) for value in values))
    inclusive_markers = (
        "micro pequena mediana y gran empresa",
        "micro small medium and large",
        "all company sizes",
        "con independencia de su tamano",
    )
    if any(marker in text for marker in inclusive_markers):
        return False
    restrictive_markers = (
        "exclusivamente pyme", "solo pyme", "unicamente pyme",
        "sme only", "only smes", "small and medium sized enterprises only",
        "consortia of smes", "provided they are smes",
    )
    if (
        any(marker in text for marker in restrictive_markers)
        or re.search(r"\bmust be\b.{0,120}\bsmes?\b", text)
    ):
        return True
    entity_values = [
        _fold_text(value)
        for value in facts.get("eligible_entity_types", [])
        + facts.get("applicant_types", [])
        if str(value).strip()
    ]
    return bool(
        entity_values
        and all(
            ("pyme" in value or "sme" in value)
            and not any(marker in value for marker in ("gran empresa", "large compan"))
            for value in entity_values
        )
    )


def _resolve_consortium_requirement(facts: dict) -> None:
    """Distingue consorcio opcional de obligatorio usando solicitantes expresos."""

    def resolve(container: dict) -> None:
        if container.get("consortium_required") is not None:
            return
        entity_values = [
            _fold_text(value)
            for value in (
                container.get("applicant_types", [])
                + container.get("eligible_entity_types", [])
            )
            if str(value).strip()
        ]
        evidence_values = [
            _fold_text(value)
            for value in (
                container.get("eligibility_evidence", [])
                + container.get("requirements", [])
                + container.get("evidence", [])
            )
            if str(value).strip()
        ]
        combined = " ".join([*entity_values, *evidence_values])
        required_markers = (
            "consorcio obligatorio", "consortium required",
            "must form a consortium", "minimum consortium",
            "consorcio de al menos", "agrupacion obligatoria",
        )
        if any(marker in combined for marker in required_markers):
            container["consortium_required"] = True
            return
        optional_markers = (
            "individualmente o en consorcio", "individual applicant",
            "single applicant", "consortium optional",
            "solicitud individual", "modalidad individual",
            "individual mode", "individual legal entit",
        )
        consortium_markers = (
            "consorcio", "consorcios", "consortium", "consortia",
            "agrupacion empresarial", "agrupaciones empresariales",
        )
        standalone_markers = (
            "empresa", "company", "companies", "persona fisica",
            "universidad", "university", "centro de investigacion",
            "research centre", "sector publico", "public sector",
            "entidad sin animo", "non-profit",
        )
        consortium_is_option = any(
            any(marker in value for marker in consortium_markers)
            for value in entity_values
        )
        standalone_is_option = any(
            any(marker in value for marker in standalone_markers)
            and not any(marker in value for marker in consortium_markers)
            for value in entity_values
        )
        if (
            any(marker in combined for marker in optional_markers)
            or (consortium_is_option and standalone_is_option)
        ):
            container["consortium_required"] = False

    resolve(facts)
    general_requirement = facts.get("consortium_required")
    for funding_line in facts.get("funding_lines", []):
        resolve(funding_line)
        if (
            funding_line.get("consortium_required") is None
            and general_requirement is False
        ):
            line_entities = " ".join(
                _fold_text(value)
                for value in (
                    funding_line.get("applicant_types", [])
                    + funding_line.get("eligible_entity_types", [])
                )
            )
            if any(
                marker in line_entities
                for marker in (
                    "empresa", "company", "persona fisica", "universidad",
                    "centro de investigacion", "sector publico", "entidad",
                )
            ):
                funding_line["consortium_required"] = False


def _remove_unfounded_size_checks(evaluation: dict, facts: dict) -> None:
    """Elimina dudas de PYME cuando la fuente no restringe por tamaño."""
    if _funding_restricts_company_size(facts):
        return

    explicit_size_pattern = re.compile(
        r"\b(pymes?|smes?|small and medium|umbral(?:es)? de tamaño|"
        r"restricci[oó]n(?:es)? de tamaño|tamaño empresarial|"
        r"empresas vinculadas)\b",
        re.IGNORECASE,
    )
    financial_size_pattern = re.compile(
        r"\b(?:balance|facturación)\b[^.]{0,100}"
        r"\b(?:pyme|sme|tamaño|empresa vinculada)\b|"
        r"\b(?:pyme|sme|tamaño|empresa vinculada)\b[^.]{0,100}"
        r"\b(?:balance|facturación)\b",
        re.IGNORECASE,
    )

    def is_size_check(value: str) -> bool:
        text = str(value or "")
        return bool(
            explicit_size_pattern.search(text)
            or financial_size_pattern.search(text)
        )

    enumerated_size_clause = re.compile(
        r"(?:,\s*|\s+)(?:y\s+)?\([a-z]\)\s*[^().;]{0,160}"
        r"(?:pymes?|smes?|small and medium|tamaño empresarial|de tamaño)",
        re.IGNORECASE,
    )

    def clean_text(value: str) -> str:
        text = enumerated_size_clause.sub("", str(value or ""))
        text = re.sub(
            r"(\b(?:tipos? de entidad elegibles?|eligible entity types?))"
            r"\s+(?:o|y|or|and)\s+(?:el\s+)?"
            r"(?:tamaño(?:\s+empresarial)?|company size)\b",
            r"\1",
            text,
            flags=re.IGNORECASE,
        )
        sentences = re.split(r"(?<=[.!?;])\s+", text)
        kept = [sentence for sentence in sentences if not is_size_check(sentence)]
        return " ".join(kept).strip()

    evaluation["risks_and_unknowns"] = [
        risk for risk in evaluation.get("risks_and_unknowns", [])
        if not is_size_check(str(risk))
    ]
    cleaned_reason = clean_text(evaluation.get("eligibility_reason", ""))
    if not cleaned_reason and evaluation.get("eligibility") == "unknown":
        cleaned_reason = (
            "La elegibilidad permanece pendiente por requisitos específicos "
            "distintos del tamaño empresarial que no constan en la evidencia."
        )
    evaluation["eligibility_reason"] = cleaned_reason
    cleaned_summary = clean_text(evaluation.get("resumen", ""))
    if cleaned_summary:
        evaluation["resumen"] = cleaned_summary
    cleaned_action = clean_text(evaluation.get("accion", ""))
    evaluation["accion"] = cleaned_action or (
        "Verificar los requisitos de elegibilidad todavía ausentes en la "
        "documentación disponible."
    )


def _correct_consortium_participation_ineligibility(
    evaluation: dict,
    facts: dict,
) -> bool:
    """Un consorcio obligatorio es una forma de solicitud, no una exclusión."""
    already_corrected = bool(
        evaluation.get("eligibility") == "unknown"
        and evaluation.get("decision") == "manual_review"
        and str(evaluation.get("eligibility_reason", "")).startswith(
            "La convocatoria admite empresas y exige"
        )
    )
    if facts.get("consortium_required") is not True or (
        evaluation.get("eligibility") != "ineligible" and not already_corrected
    ):
        return False
    entities = [
        _fold_text(value)
        for value in facts.get("eligible_entity_types", [])
        + facts.get("applicant_types", [])
        if str(value).strip()
    ]
    company_markers = (
        "empresa", "company", "companies", "sme", "smes", "pyme", "pymes",
        "start-up", "startup", "private entity", "entidad privada",
    )
    if not any(marker in value for value in entities for marker in company_markers):
        return False
    reason = _fold_text(evaluation.get("eligibility_reason", ""))
    applies_alone_markers = (
        "entidad unica", "individual", "solicitante individual", "applying alone",
        "single applicant", "no puede presentarse", "cannot apply alone",
        "no admite solicitantes individuales", "does not admit individual",
    )
    if not already_corrected and ("consor" not in reason or not any(
        marker in reason for marker in applies_alone_markers
    )):
        return False
    if evaluation.get("recommended_role") not in {
        "consortium_partner", "technology_partner", "industrial_demonstrator",
    }:
        return False

    size_pending = _funding_restricts_company_size(facts)
    evaluation["eligibility"] = "unknown"
    evaluation["decision"] = "manual_review"
    evaluation["eligibility_reason"] = (
        "La convocatoria admite empresas y exige presentar la propuesta mediante "
        "un consorcio. Esa obligación no excluye a Kalfrisa: implica concurrir "
        "como socia, no como solicitante individual. "
        + (
            "Debe confirmarse que cumple la definición jurídica de PYME aplicable."
            if size_pending else
            "No consta otra incompatibilidad expresa de tipo de entidad."
        )
    )
    risks = list(evaluation.get("risks_and_unknowns", []))
    risks.append("Es obligatorio formar un consorcio conforme a las bases.")
    if size_pending:
        risks.append("Confirmar la condición jurídica de PYME de Kalfrisa.")
    evaluation["risks_and_unknowns"] = list(dict.fromkeys(risks))
    current_action = str(evaluation.get("accion", ""))
    if already_corrected and not any(
        marker in _fold_text(current_action)
        for marker in ("consorcio", "socio", "participacion")
    ):
        evaluation["accion"] = (
            "Confirmar la condición jurídica de PYME e identificar "
            "los socios necesarios para formar el consorcio exigido."
        )
        return True
    evaluation["accion"] = re.sub(
        r"^\s*descartar(?:\s+como\s+solicitante\s+principal)?[.:]?\s*",
        "Preparar la participación como socio de consorcio. ",
        str(evaluation.get("accion", "")),
        flags=re.IGNORECASE,
    ).strip() or "Identificar socios y confirmar los requisitos del consorcio."
    return True


def _correct_required_consortium_member_ineligibility(
    evaluation: dict,
    facts: dict,
) -> bool:
    """Evita convertir un miembro obligatorio en requisito para cada socio."""
    category = _required_consortium_member_category(facts)
    if not category or evaluation.get("eligibility") != "ineligible":
        return False
    reason = _fold_text(evaluation.get("eligibility_reason", ""))
    category_folded = _fold_text(category)
    entity_exclusion_markers = (
        "tipo de entidad", "solicitantes sean", "requires applicants",
        "required applicant", "no es una", "is not a", "does not qualify as",
        "no encaja", "no cumple esta condicion",
    )
    if category_folded not in reason or not any(
        marker in reason for marker in entity_exclusion_markers
    ):
        return False
    unrelated_barriers = (
        "requisito geografico", "geografia es", "ubicacion geografica",
        "cnae", "sector restringido", "tamano es determinante",
    )
    if any(marker in reason for marker in unrelated_barriers):
        return False

    evaluation["eligibility"] = "unknown"
    evaluation["decision"] = "manual_review"
    evaluation["recommended_role"] = "consortium_partner"
    evaluation["eligibility_reason"] = (
        f"La evidencia exige que el consorcio incluya a {category}, pero no "
        "establece que todos sus miembros deban pertenecer a esa categoría. "
        "Kalfrisa puede participar como socio tecnológico si cumple las "
        "condiciones generales de Horizon y se forma el consorcio requerido."
    )
    risks = list(evaluation.get("risks_and_unknowns", []))
    risks.extend([
        f"Incorporar al consorcio el miembro obligatorio: {category}.",
        "Confirmar las condiciones generales de elegibilidad de los demás socios.",
    ])
    evaluation["risks_and_unknowns"] = list(dict.fromkeys(risks))
    evaluation["accion"] = (
        "Verificar las condiciones generales de beneficiarios e identificar un "
        f"consorcio que incluya a {category}, ciudades o regiones demostradoras "
        "y el resto de perfiles exigidos."
    )
    return True


def _enforce_temporal_consistency(conv: dict, evaluation: dict) -> None:
    """Impide recomendar esperar una apertura o publicación que ya ocurrió."""
    if _deterministic_call_status(conv) != "open":
        return
    stale_wait = re.compile(
        r"\b(?:aguardar|esperar|wait for)\b\s+(?:a\s+)?(?:la\s+)?"
        r"(?:publicaci[oó]n(?:\s+oficial)?|apertura|opening|publication)"
        r"(?:\s+de\s+la\s+convocatoria)?",
        re.IGNORECASE,
    )
    action = str(evaluation.get("accion", ""))
    if stale_wait.search(action):
        action = stale_wait.sub(
            "Usar la documentación oficial ya publicada",
            action,
        )
    stale_condition = re.compile(
        r"\b(?:una vez|cuando)\s+(?:se\s+)?"
        r"(?:publicad[oa]|publique|abiert[oa]|abra)\b",
        re.IGNORECASE,
    )
    if stale_condition.search(action):
        action = stale_condition.sub(
            "Con la documentación oficial ya publicada",
            action,
        )
    evaluation["accion"] = " ".join(action.split())


def apply_current_deterministic_rules(record: dict) -> None:
    """Actualiza en memoria salvaguardas sobre análisis válidos ya cacheados."""
    analysis = record.get("analysis")
    conv = record.get("raw_document")
    if not isinstance(analysis, dict) or not isinstance(conv, dict):
        return
    facts = analysis.get("call_facts")
    if not isinstance(facts, dict):
        return
    public_action_alias = "action" in analysis and "accion" not in analysis
    public_summary_alias = "summary" in analysis and "resumen" not in analysis
    if public_action_alias:
        analysis["accion"] = analysis.get("action", "")
    if public_summary_alias:
        analysis["resumen"] = analysis.get("summary", "")
    taxonomy_text = " ".join([
        str(conv.get("title", "")), str(conv.get("description", "")),
        *[
            str(document.get("description", ""))
            for document in conv.get("related_document_contents", [])
            if isinstance(document, dict)
        ],
    ])
    current_tech_tags = detect_tech_tags(taxonomy_text)
    analysis["tech_tags"] = current_tech_tags
    analysis["tags"] = _compat_tags_for(current_tech_tags)
    _resolve_consortium_requirement(facts)
    _remove_unfounded_size_checks(analysis, facts)
    _correct_consortium_participation_ineligibility(analysis, facts)
    _correct_required_consortium_member_ineligibility(analysis, facts)
    _correct_own_industrial_investment_scope(analysis, facts)
    _correct_direct_valorisation_scope(analysis, facts, conv, current_tech_tags)
    _enforce_explicit_regional_ineligibility(analysis, facts, conv)
    _normalize_model_manual_review(analysis)
    _enforce_temporal_consistency(conv, analysis)
    public_dimensions = analysis.get("dims")
    scores = analysis.get("scores", {})
    if isinstance(public_dimensions, list) and isinstance(scores, dict):
        dimension_score_keys = {
            "alineacion tecnologica": "technological_fit",
            "capacidad de consorcio": "consortium_readiness",
            "encaje trl": "trl_fit",
            "encaje de rol": "role_fit",
            "oportunidad estrategica": "strategic_fit",
        }
        for dimension in public_dimensions:
            if not isinstance(dimension, dict):
                continue
            score_key = dimension_score_keys.get(_fold_text(dimension.get("name", "")))
            if score_key in scores:
                dimension["val"] = scores[score_key]
    analysis["call_facts"] = facts
    analysis["descartada"] = analysis.get("decision", "").startswith("discard_")
    analysis["motivo_descarte"] = (
        analysis.get("eligibility_reason", "") if analysis["descartada"] else ""
    )
    analysis["priority"] = _derive_priority(
        int(analysis.get("actionability_score", 0) or 0),
        int(analysis.get("confidence", 0) or 0),
        str(analysis.get("decision", "manual_review")),
    )
    analysis["data_gaps"] = _data_gap_reasons(facts, analysis)
    analysis["data_pending"] = bool(analysis["data_gaps"])
    analysis["monitoring_flags"] = _monitoring_flags(conv, analysis)
    analysis["review_reasons"] = _review_reasons(analysis)
    analysis["review_required"] = bool(analysis["review_reasons"])
    if public_action_alias:
        analysis["action"] = analysis.pop("accion", analysis.get("action", ""))
    if public_summary_alias:
        analysis["summary"] = analysis.pop("resumen", analysis.get("summary", ""))
