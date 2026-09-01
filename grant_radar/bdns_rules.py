# -*- coding: utf-8 -*-
# bdns_rules.py — la matriz de reglas previa a Claude
#
# Es la última pieza del orden de extracción medido en las secciones 37 y 38, y
# la que se dejó deliberadamente para el final: decide **qué convocatorias
# llegan a Claude** y, con ello, el coste de cada ejecución. Por eso vivió en
# `Grant-Radar-prueba.py` mucho después de que todo lo demás saliera, y por eso
# se extrajo en una sesión dedicada, sin mezclarla con ningún cambio de
# comportamiento (AGENTS.md 4.1 y 36.3, punto 8).
#
# **La extracción no cambió una sola regla.** El criterio de aceptación fue que
# el embudo saliera idéntico: `retain=34, ambiguous=7, hold_manual=75,
# reject=803` sobre 82 convocatorias vigentes.
#
# Siete niveles de precedencia, en este orden (el detalle, en AGENTS.md 4.1):
#
#   1. `_bdns_intrinsic_exclusion()`  — exclusiones intrínsecas de la ayuda:
#      territorio ajeno, sector sin relación, beneficiario que no es empresa,
#      presencia local previa exigida. Manda sobre todo lo demás.
#   2. `_bdns_structured_scope_exclusion()` — exclusiones leídas de los campos
#      estructurados de SNPSAP (finalidad, tipo de beneficiario), no del texto.
#   3. `_bdns_pre_claude_gate()` — la puerta propiamente dicha, que combina lo
#      anterior con estado, plazo, vocabulario tecnológico y rol documental.
#   4. `deterministic_prefilter()` — la decisión común a todas las fuentes, que
#      envuelve a la puerta de BDNS y aplica el ámbito del perfil.
#
# `_bdns_gate_result()` y `_bdns_applicant_section()` son los dos ayudantes:
# el primero da forma uniforme a cada veredicto, el segundo recorta la sección
# de solicitantes de un texto legal para no leerlo entero.
#
# **Disciplina obligatoria para tocar cualquier condición de aquí**
# (`SUGERENCIAS.MD` 3.3): ampliar primero `tests/fixtures/bdns_filter_cases.json`
# con casos reales y solo después la regla. Endurecer una condición aquí no
# ahorra dinero si además deja fuera una convocatoria que interesaba: el 91,9 %
# de las candidatas ya se descarta aquí sin llamar a Claude (AGENTS.md 27).
#
# Este módulo no lee el entorno, no toca la red y no escribe nada: recibe una
# convocatoria y devuelve un veredicto. `holds.py` y el conector ECCP reciben
# `_bdns_intrinsic_exclusion` y `deterministic_prefilter` **inyectados como
# parámetros**, no importados, que es justo lo que permitió extraer esto sin
# tocarlos.

import re
from datetime import datetime

from grant_radar.bdns_fields import (
    BDNS_NAMED_ACCESS_TERMS,
    BDNS_NEW_ESTABLISHMENT_MIN_DAYS,
    BDNS_TECHNOLOGY_TERMS,
    _bdns_company_eligible,
)
from grant_radar.call_text import FUNDING_CONTEXT_TERMS
from grant_radar.deterministic_rules import BDNS_DIRECT_OWN_INVESTMENT_TERMS
from grant_radar.parsing_helpers import _fold_text
from grant_radar.profile_scope import (
    _explicit_profile_incompatibility,
    _hard_out_of_scope,
)
from grant_radar.tech_taxonomy import (
    INDUSTRIAL_CONTEXT_TERMS,
    _term_present,
    detect_tech_tags,
)


INNOVATION_CONTEXT_TERMS = (
    "innovacion", "innovation", "investigacion", "research and development",
    "i+d", "r&d", "demostracion", "demonstration", "pilot", "piloto",
    "proof of concept", "poc", "escalado", "scale-up", "inversion productiva",
)
ENTERPRISE_CONTEXT_TERMS = (
    "empresa", "empresas", "business", "businesses", "sme", "smes", "pyme",
    "pymes", "startup", "start-up", "manufacturer", "fabricante", "industry",
)
EXPLICIT_INELIGIBLE_ONLY_TERMS = (
    "exclusivamente universidades", "only universities", "solo universidades",
    "exclusivamente administraciones publicas", "only public authorities",
    "exclusivamente personas fisicas", "individuals only",
    "solo entidades sin animo de lucro", "non-profit organisations only",
)
EXPLICIT_UNRELATED_SECTOR_TERMS = (
    "formacion profesional", "programas de empleo", "contratacion de personas",
    "actividades culturales", "artes escenicas", "patrimonio cultural",
    "festival", "fiestas", "biblioteca", "deporte", "deportivo", "deportiva",
    "servicios sociales", "ayuda humanitaria", "cooperacion al desarrollo",
    "cooperacion internacional", "alquiler de vivienda", "vivienda social",
    "comercio minorista", "bonos comercio", "promocion turistica",
    "sector turistico", "produccion agricola", "explotaciones ganaderas",
    "sector pesquero", "acuicultura", "becas de estudio",
)


BDNS_POSITIVE_NACE_SECTIONS = {"C", "D", "E"}
# BDNS_NEW_ESTABLISHMENT_MIN_DAYS y BDNS_TECHNOLOGY_TERMS viven en
# grant_radar/bdns_fields.py: los comparten la matriz de reglas, que sigue
# aqui, y la resolucion de holds, que ya no.
BDNS_CLUSTER_TERMS = (
    "cluster", "clusteres", "clusters", "agrupacion empresarial innovadora",
    "agrupaciones empresariales innovadoras", "aei",
)
BDNS_CLUSTER_DOWNSTREAM_TERMS = (
    "empresas miembro", "miembros del cluster", "pymes participantes",
    "proyectos de las empresas", "piloto en empresa", "apoyo a terceros",
    "costes de las empresas", "ayudas a empresas miembro", "beneficiarios finales",
    "bonos para empresas miembro", "downstream support",
    "financial support to third parties", "pilot at member facility",
)
BDNS_CLUSTER_OPERATING_TERMS = (
    "gastos de funcionamiento", "costes de funcionamiento", "personal del cluster",
    "estructura del cluster", "representacion institucional", "organizacion de eventos",
    "alquiler de la sede", "funcionamiento de agrupaciones empresariales",
    "operating costs", "cluster staff",
)
BDNS_OWN_INVESTMENT_TERMS = (
    "adquisicion de maquinaria", "adquisicion de equipos", "equipamiento",
    "instalaciones", "ingenieria", "inversion productiva", "mejora de procesos",
    "modernizacion de procesos", "equipos industriales", "gasto elegible",
    "gasto subvencionable", "activos productivos", "ampliacion productiva",
    "transformacion productiva", "automatizacion", "digitalizacion industrial",
    "ahorro energetico", "eficiencia energetica", "reduccion de emisiones",
    "valorizacion de residuos", "tratamiento de residuos",
    "adquisicion de suelo industrial", "ampliacion de instalaciones",
    "ampliacion del centro empresarial", "aumento de superficie",
    "traslado a poligono", "traslado a area industrial",
)
BDNS_CONSORTIUM_TERMS = (
    "consorcio", "consorcios", "agrupacion de empresas",
    "agrupaciones de empresas", "proyecto en cooperacion",
    "proyectos en cooperacion", "grupo operativo", "grupos operativos",
    "collaborative project", "project consortium",
)
BDNS_CONSORTIUM_DIRECT_TERMS = (
    "miembro del consorcio", "miembros del consorcio", "socio del consorcio",
    "socios del consorcio", "cada miembro del consorcio",
    "costes de los miembros", "costes de cada socio", "presupuesto de cada socio",
    "paquete de trabajo", "work package", "cobeneficiario", "cobeneficiarios",
    "empresas participantes", "entidades participantes",
)
BDNS_ALWAYS_OUT_OF_SCOPE_TERMS = (
    "programa pyme global", "convocatoria pyme global",
    "mision comercial", "visita a la feria",
    "participacion en feria", "encuentros empresariales internacionales",
    "promocion turistica", "bonos comercio", "bonos de comercio",
    "bono comercio", "bono de comercio", "comercio minorista",
    "empresas turisticas", "sector turistico", "ambito turistico",
    "inversiones en sus tiendas",
    "edificios residenciales", "viviendas y edificios residenciales",
    "mejora energetica de las viviendas", "viviendas del municipio",
    "edificio municipal", "edificios municipales", "piscinas climatizadas municipales",
    "rehabilitacion, la mejora de la accesibilidad", "actuaciones relativas a la accesibilidad",
    "foment de la rehabilitacio", "millora de l accessibilitat",
    "aparatos electrodomesticos", "premios cultura", "premio de investigacion",
    "premios nacionales", "convocatoria de premios", "concurso de artesania",
    "premios a la excelencia", "startup awards", "hackathon",
    "beca de formacion", "becas de colaboracion", "acciones formativas",
    "beca de iniciacion", "movilidad para practicas",
    "plan wave plus", "personas trabajadoras prioritariamente ocupadas",
    "trabajos fin de grado", "trabajos de fin de grado",
    "trabajos fin de master", "trabajos de fin de master",
    "contratacion de personas", "contratacion de personal investigador",
    "contrato predoctoral", "programas de empleo", "fomento al empleo",
    "fomento del autoempleo",
    "relevo generacional en las empresas", "implantacion de planes de igualdad",
    "fomento de la movilidad sostenible de emisiones cero",
    "conciliacion de la vida personal", "conciliacion de la vida familiar",
    "conciliacion de la vida laboral", "conciliacion personal, familiar y laboral",
    "regimen especial de trabajadores por cuenta propia",
    "fomentar el conocimiento de la economia social",
    "empresas de economia social", "cooperacion al desarrollo",
    "programas de ensenanzas", "servicios de atencion",
    "sector minero", "actividad minera",
    "entidades colaboradoras en gestion de ayudas de icex",
)

# En documentos largos solo se aplican expresiones que describen por sí mismas
# el objeto financiado. Términos como «feria» o «economía social» pueden aparecer
# incidentalmente en exclusiones, referencias legales o listas de beneficiarios.
BDNS_DOCUMENT_OUT_OF_SCOPE_TERMS = (
    "edificios residenciales", "viviendas y edificios residenciales",
    "mejora energetica de las viviendas", "viviendas del municipio",
    "edificio municipal", "edificios municipales", "piscinas climatizadas municipales",
    "plan wave plus", "personas trabajadoras prioritariamente ocupadas",
    "acciones formativas", "programas de empleo", "fomento al empleo",
    "destinadas a la contratacion de personas jovenes",
    "finalidad de estas subvenciones consiste en favorecer la insercion laboral",
    "contrataciones indefinidas", "transformaciones de contratos temporales",
    "transformacion de contratos temporales en indefinidos",
    "premios a la excelencia", "convocatoria de premios",
    "regimen especial de trabajadores por cuenta propia",
)
BDNS_DOCUMENT_NAMED_ACCESS_TERMS = (
    "subvencion directa excepcional", "convenio a suscribir con",
)

BDNS_PRIOR_LOCAL_PRESENCE_PATTERNS = (
    r"domicilio social y fiscal.{0,80}municipio.{0,180}actividad principal.{0,80}municipio",
    r"actividades economicas ubicadas en.{0,180}afectad[oa]s? por la dana",
    r"(?:empresas?|entidades|personas).{0,80}beneficiari[ao]s?.{0,160}"
    r"(?:contar|cuenten|disponer|dispongan|tener|tengan).{0,50}"
    r"(?:establecimiento operativo|centro de trabajo|centro productivo|"
    r"establecimiento productivo|domicilio social|domicilio fiscal)",
    r"(?:empresas?|entidades|personas).{0,120}"
    r"(?:con|que cuenten con|que dispongan de|que tengan).{0,40}"
    r"(?:establecimiento operativo|centro de trabajo|centro productivo|"
    r"establecimiento productivo).{0,100}(?:comunidad autonoma|municipio|provincia)",
    r"(?:beneficiari[oa]|solicitante).{0,100}(?:debera|deberan|debe).{0,50}"
    r"(?:estar )?dad[oa] de alta.{0,100}(?:censo de actividades economicas|"
    r"impuesto sobre actividades economicas).{0,120}(?:comunidad autonoma|"
    r"municipio|provincia)",
    r"(?:tener|tengan).{0,40}centros? de trabajo.{0,100}"
    r"(?:isla|municipio|provincia|comunidad autonoma)",
    r"domicilio social y/o fiscal.{0,50}municipio.{0,160}"
    r"(?:desarroll|ejerz|actividad)",
    r"centro de trabajo principal.{0,100}domicilio social.{0,100}"
    r"requisito.{0,100}beneficiari",
    r"(?:dispongan|disponer|cuenten|contar|tengan|tener) de (?:un )?"
    r"centro de actividad.{0,140}(?:comunidad autonoma|municipio|provincia)",
    r"(?:centro de actividad|centro de produccion).{0,120}"
    r"(?:comunidad autonoma|comunidad foral|municipio|provincia)",
    r"(?:figuren|estar|estaran|dadas?) de alta.{0,100}"
    r"impuesto de actividades economicas.{0,100}"
    r"(?:comunidad autonoma|comunidad foral|municipio|provincia|pais vasco)",
    r"actividad (?:economica|profesional).{0,80}(?:se )?"
    r"(?:desarrolle|desarrollarse) en.{0,160}"
    r"(?:establecimiento abierto|domicilio fiscal)",
    r"(?:establecimientos?|actividades?).{0,100}ubicad[oa]s?.{0,100}"
    r"(?:termino municipal|municipio).{0,180}censo.{0,80}fiscal",
)
BDNS_NEW_ESTABLISHMENT_ALTERNATIVE_TERMS = (
    "linea 1. emprende", "nuevas iniciativas empresariales",
    "implantacion de nuevas empresas", "puesta en marcha de proyectos empresariales",
    "nuevas actividades economicas",
)
BDNS_EXHAUSTIVE_APPLICANT_MARKERS = (
    "podran ser beneficiarias", "podran obtener la condicion de entidad beneficiaria",
    "podran acceder a las ayudas contempladas", "podran acceder a la condicion de beneficiarios",
    "entidades beneficiarias", "personas beneficiarias",
)
BDNS_NONCOMPANY_APPLICANT_MARKERS = (
    "ayuntamientos", "diputaciones", "centros escolares", "centros publicos",
    "centros privados concertados", "educacion infantil", "educacion primaria",
    "educacion secundaria obligatoria",
    "asociaciones de padres", "asociaciones de madres",
    "entidades sin animo de lucro", "organismos publicos",
    "universidades publicas", "administracion local",
)
BDNS_COMPANY_APPLICANT_MARKERS = (
    "empresas", "pymes", "sociedades mercantiles",
    "personas fisicas que desarrollan actividad economica",
)
BDNS_NEXT_SECTION_PATTERN = re.compile(
    r"\b(?:primera|segunda|tercera|cuarta|quinta|sexta|septima|octava|"
    r"novena|decima|undecima|duodecima|decimotercera|decimocuarta|"
    r"decimoquinta|decimosexta)\s*[.\-]+"
)


def _bdns_applicant_section(text: str, start: int, marker: str) -> str:
    """Acota una lista de solicitantes para no leer prohibiciones posteriores."""
    section = text[start:start + 5_000]
    search_from = min(len(section), len(marker) + 80)
    next_heading = BDNS_NEXT_SECTION_PATTERN.search(section, search_from)
    if next_heading:
        section = section[:next_heading.start()]
    return section

# Segunda capa de alcance basada en metadatos estructurados. Se ejecuta después
# de incompatibilidades intrínsecas y antes de vigencia/territorio; nunca
# convierte un dato ausente en rechazo.
BDNS_STRUCTURED_PRIMARY_FINALITIES = {
    "agricultura, pesca y alimentacion",
}
BDNS_STRUCTURED_DEVELOPMENT_FINALITIES = {
    "cooperacion internacional para el desarrollo y cultural",
}
BDNS_STRUCTURED_EMPLOYMENT_FINALITIES = {"fomento del empleo"}
BDNS_EXPLICIT_EMPLOYMENT_SCOPE_TERMS = (
    "busqueda de empleo", "orientacion para el empleo", "programa de empleo",
    "formacion y empleo", "acompanamiento sociolaboral", "apoyo sociolaboral",
    "contratacion de personal", "contratacion laboral", "puestos de trabajo",
    "personas desempleadas", "personas trabajadoras", "empresas de insercion",
    "centros especiales de trabajo", "contrato predoctoral", "beca de formacion",
)
BDNS_FORMAL_PARTICIPATION_ROUTE_TERMS = (
    "cluster", "clusteres", "agrupacion empresarial innovadora",
    "agrupaciones empresariales innovadoras", "grupo operativo",
    "grupos operativos", "agrupacion de empresas", "agrupaciones de empresas",
    "proyecto en cooperacion", "proyectos en cooperacion",
)
BDNS_PUBLIC_BENEFICIARY_SCOPE_TERMS = (
    "destinadas a los entes locales", "destinadas a entidades locales",
    "dirigidas a entidades locales", "para entidades locales",
    "subvenciones a los entes locales", "subvenciones a entidades locales",
    "convocatoria de subvenciones a entidades locales",
    "ayuntamientos y entidades locales", "mancomunidades y consorcios de la provincia",
)
BDNS_SPECIFIC_NON_INDUSTRIAL_SCOPE_TERMS = (
    "actividades feriales", "organizacion de eventos de estetica",
    "premio mujer empresaria", "nuevos autonomos",
    "empresas artesanas", "autonomos y empresas artesanas",
    "programa formacion y empleo", "acompanamiento sociolaboral",
    "industrias culturales y creativas", "industria cultural y creativa",
    "fomento de la actividad cultural", "proyectos de arte y educacion",
    "movilidad nacional e internacional de profesionales de las industrias culturales",
    "razas autoctonas", "bienestar animal", "semilla certificada",
    "inversiones a bordo de los buques pesqueros",
)


def _bdns_gate_result(
    decision: str,
    reason_code: str,
    reason: str,
    role: str = "unknown",
    labels: list[str] | None = None,
    details: dict | None = None,
) -> dict:
    return {
        "decision": decision,
        "reason_code": reason_code,
        "reason": reason,
        "opportunity_role": role,
        "opportunity_labels": labels or [],
        "details": details or {},
        "score": 0,
        "signals": {},
    }


def _bdns_intrinsic_exclusion(conv: dict, extra_text: str = "") -> dict | None:
    """Descarta incompatibilidades inequívocas incluso si solo constan en bases."""
    metadata = " ".join(str(conv.get(field, "")) for field in (
        "title", "description", "org", "bdns_finality", "bdns_objectives",
    ))
    metadata_folded = _fold_text(metadata)
    evidence_folded = _fold_text(str(extra_text or ""))
    regions = [_fold_text(value) for value in conv.get("bdns_regions", [])]
    outside_aragon = bool(regions) and not any(
        "aragon" in value or "zaragoza" in value or "huesca" in value
        or "teruel" in value or "espana" in value or "nacional" in value
        or "todo el territorio" in value for value in regions
    )
    presence_text = f"{metadata_folded} {evidence_folded}"
    prior_presence = any(
        re.search(pattern, presence_text) for pattern in BDNS_PRIOR_LOCAL_PRESENCE_PATTERNS
    )
    new_establishment_alternative = any(
        term in presence_text for term in BDNS_NEW_ESTABLISHMENT_ALTERNATIVE_TERMS
    )
    beneficiary_types = [
        _fold_text(value) for value in conv.get("bdns_beneficiary_types", [])
        if str(value).strip()
    ]
    if beneficiary_types and all(
        "gran empresa" in value and "pyme" not in value
        for value in beneficiary_types
    ):
        return _bdns_gate_result(
            "reject", "large_enterprises_only",
            "Los metadatos oficiales limitan la convocatoria a grandes empresas; "
            "Kalfrisa es una empresa mediana.",
        )

    exclusive_new_microenterprise = bool(evidence_folded) and bool(re.search(
        r"(?:beneficiari[oa]s?|personas beneficiarias).{0,900}"
        r"(?:reta|cuenta propia|autonom[oa]s?).{0,500}microempresas.{0,350}"
        r"(?:siempre que|que).{0,100}(?:inicien|hayan iniciado|inicio de)"
        r".{0,80}actividad",
        evidence_folded,
    ))
    if exclusive_new_microenterprise:
        return _bdns_gate_result(
            "reject", "new_microenterprise_only",
            "Las bases reservan la ayuda a personas autonomas o microempresas "
            "que inician actividad; Kalfrisa es una empresa mediana preexistente.",
        )

    if outside_aragon and prior_presence and not new_establishment_alternative:
        return _bdns_gate_result(
            "reject", "existing_establishment_outside_aragon",
            "La convocatoria exige actividad o domicilio empresarial previo en "
            "una región distinta de Aragón; no es una nueva implantación evaluable.",
        )

    execution_days = conv.get("bdns_project_execution_days")
    if (
        outside_aragon
        and prior_presence
        and new_establishment_alternative
        and isinstance(execution_days, int)
        and 0 <= execution_days < BDNS_NEW_ESTABLISHMENT_MIN_DAYS
    ):
        return _bdns_gate_result(
            "reject", "new_establishment_period_too_short",
            "La alternativa de nueva implantacion tiene un periodo confirmado "
            "inferior a 730 dias; las demas vias exigen presencia local previa.",
            details={"execution_days": execution_days},
        )

    admin_type = _fold_text(conv.get("bdns_admin_type", ""))
    local_target_outside_zaragoza = bool(re.search(
        r"(?:termino municipal|municipio)\s+de(?:l| la)?\s+"
        r"(?!zaragoza\b)[a-z][a-z -]{2,45}?"
        r"(?=[,.;]|\s+(?:en|y|para|por|durante|con)\b|$)",
        presence_text,
    ))
    if (
        "local" in admin_type
        and local_target_outside_zaragoza
        and prior_presence
        and not new_establishment_alternative
    ):
        return _bdns_gate_result(
            "reject", "existing_establishment_outside_kalfrisa_location",
            "La ayuda local exige que la actividad o establecimiento ya figure "
            "en un municipio distinto de la ubicacion conocida de Kalfrisa.",
        )

    if evidence_folded:
        for marker in BDNS_EXHAUSTIVE_APPLICANT_MARKERS:
            start = evidence_folded.find(marker)
            if start < 0:
                continue
            applicant_section = _bdns_applicant_section(
                evidence_folded, start, marker
            )
            noncompany_count = sum(
                term in applicant_section for term in BDNS_NONCOMPANY_APPLICANT_MARKERS
            )
            has_company_route = any(
                term in applicant_section for term in BDNS_COMPANY_APPLICANT_MARKERS
            )
            if noncompany_count >= 2 and not has_company_route:
                return _bdns_gate_result(
                    "reject", "documented_noncompany_applicants_only",
                    "La relación exhaustiva de solicitantes en las bases no incluye "
                    "empresas privadas ni una vía financiada para Kalfrisa.",
                )
    if (
        any(term in metadata_folded for term in BDNS_ALWAYS_OUT_OF_SCOPE_TERMS)
        or any(term in evidence_folded for term in BDNS_DOCUMENT_OUT_OF_SCOPE_TERMS)
    ):
        return _bdns_gate_result(
            "reject", "explicit_non_industrial_scope",
            "La convocatoria financia una actividad comercial, residencial, "
            "formativa, laboral o un premio ajeno al uso industrial.",
        )
    call_access = conv.get("bdns_call_access", "open_or_unknown")
    if (
        call_access in {"named", "preselected", "instrumental"}
        or any(term in metadata_folded for term in BDNS_NAMED_ACCESS_TERMS)
        or any(term in evidence_folded for term in BDNS_DOCUMENT_NAMED_ACCESS_TERMS)
        or bool(re.match(r"^sn\s+a(?:l|\s+la)?\b", _fold_text(str(conv.get("title", "")))))
    ):
        return _bdns_gate_result(
            "reject", "not_open_call",
            "La ayuda identifica al beneficiario o financia una selección previa; "
            "no es una convocatoria abierta.",
        )
    return None


def _bdns_structured_scope_exclusion(conv: dict) -> dict | None:
    """Exclusiones autosuficientes apoyadas en metadatos oficiales SNPSAP."""
    if not conv.get("bdns_filter_ready"):
        return None
    combined = " ".join(str(conv.get(field, "")) for field in (
        "title", "description", "org", "bdns_finality", "bdns_objectives",
    ))
    folded = _fold_text(combined)
    title_folded = _fold_text(str(conv.get("title", "")))
    finality = _fold_text(str(conv.get("bdns_finality", ""))).strip()
    active_status = str(conv.get("bdns_active_status", ""))
    formal_route = any(
        _term_present(folded, term) for term in BDNS_FORMAL_PARTICIPATION_ROUTE_TERMS
    )

    # Una anualidad histórica explícita sin plazo confirmado no debe sobrevivir
    # por una fecha de recepción reciente o por el indicador API ``abierto``.
    year_markers = (
        r"(?:convocatoria|programa|anualidad|ejercicio|ayudas?|subvenciones?)"
        r".{0,90}?(?<!/)\b(20\d{2})\b",
        r"(?<!/)\b(20\d{2})\b.{0,25}?(?:convocatoria|anualidad|ejercicio)",
    )
    title_years = [
        int(value) for pattern in year_markers for value in re.findall(pattern, title_folded)
    ]
    current_year = datetime.now().year
    title_years = [year for year in title_years if current_year - 2 <= year < current_year]
    if (
        title_years
        and active_status not in {"confirmed_deadline", "open_ended"}
    ):
        return _bdns_gate_result(
            "reject", "historical_call_year_unverified",
            "La anualidad más reciente del título ya pasó y no existe un plazo vigente confirmado.",
            details={"latest_title_year": max(title_years)},
        )

    # En sector primario Kalfrisa solo tendría una venta comercial indirecta.
    # Se difiere, en cambio, cualquier vía formal de grupo operativo, consorcio
    # o clúster porque podría asignarle actividad y costes propios.
    if finality in BDNS_STRUCTURED_PRIMARY_FINALITIES and not formal_route:
        return _bdns_gate_result(
            "reject", "structured_primary_sector_scope",
            "La finalidad oficial limita la ayuda al sector primario y no consta una vía formal de participación.",
        )

    if finality in BDNS_STRUCTURED_DEVELOPMENT_FINALITIES or (
        finality in BDNS_STRUCTURED_EMPLOYMENT_FINALITIES
        and any(term in title_folded for term in BDNS_EXPLICIT_EMPLOYMENT_SCOPE_TERMS)
    ):
        return _bdns_gate_result(
            "reject", "structured_employment_or_development_scope",
            "La finalidad oficial corresponde a empleo o cooperación al desarrollo, fuera del alcance del radar.",
        )

    if (
        not formal_route
        and any(term in title_folded for term in BDNS_PUBLIC_BENEFICIARY_SCOPE_TERMS)
    ):
        return _bdns_gate_result(
            "reject", "structured_public_beneficiaries_only",
            "El propio título dirige la ayuda a entidades públicas locales, no a Kalfrisa.",
        )

    if (
        any(term in title_folded for term in BDNS_SPECIFIC_NON_INDUSTRIAL_SCOPE_TERMS)
        or bool(re.search(r"\bpremios?\b", title_folded))
    ):
        return _bdns_gate_result(
            "reject", "structured_specific_non_industrial_scope",
            "El objeto expresamente identificado es agrario, laboral, ferial, artesanal, cultural o un premio.",
        )
    return None


def _bdns_pre_claude_gate(conv: dict) -> dict | None:
    """Matriz BDNS aprobada: reduce coste sin sacrificar casos dudosos."""
    if not conv.get("bdns_filter_ready"):
        return None
    combined = " ".join(str(conv.get(field, "")) for field in (
        "title", "description", "org", "bdns_finality", "bdns_objectives",
    ))
    folded = _fold_text(combined)
    intrinsic = _bdns_intrinsic_exclusion(conv)
    if intrinsic:
        return intrinsic
    structured_scope = _bdns_structured_scope_exclusion(conv)
    if structured_scope:
        return structured_scope

    sections = set(conv.get("bdns_nace_sections", [])) - {""}
    beneficiaries = conv.get("bdns_beneficiary_types", [])
    company_eligible = bool(conv.get("bdns_company_eligible", _bdns_company_eligible(beneficiaries)))
    technology_fit = bool(detect_tech_tags(combined)) or any(term in folded for term in BDNS_TECHNOLOGY_TERMS)
    cluster = any(_term_present(folded, term) for term in BDNS_CLUSTER_TERMS)
    cluster_downstream = bool(conv.get("bdns_verified_cluster_downstream")) or any(
        term in folded for term in BDNS_CLUSTER_DOWNSTREAM_TERMS
    )
    cluster_operations = any(term in folded for term in BDNS_CLUSTER_OPERATING_TERMS)
    consortium = any(
        _term_present(folded, term) for term in BDNS_CONSORTIUM_TERMS
    )
    consortium_direct = bool(
        conv.get("bdns_verified_consortium_participation")
    ) or (
        consortium and any(term in folded for term in BDNS_CONSORTIUM_DIRECT_TERMS)
    )
    own_investment_fit = technology_fit or any(
        term in folded for term in BDNS_OWN_INVESTMENT_TERMS
    )

    if cluster and cluster_operations and not cluster_downstream:
        return _bdns_gate_result(
            "reject", "reject_cluster_operations",
            "La ayuda cubre el funcionamiento del cluster, no proyectos o apoyo transferido a sus empresas.",
        )
    if not company_eligible and not cluster and not consortium:
        if own_investment_fit:
            return _bdns_gate_result(
                "reject", "indirect_commercial_role_only",
                "Kalfrisa no puede recibir la ayuda ni participar formalmente; solo podría vender al beneficiario.",
            )
        return _bdns_gate_result(
            "reject", "incompatible_beneficiary_type",
            "Los beneficiarios descritos no incluyen a Kalfrisa ni una participacion financiada directa.",
        )

    role = "direct_beneficiary"
    manufacturing_evidence = any(term in folded for term in (
        "industria manufacturera", "sector manufacturero", "procesos industriales",
        "inversion industrial", "linea industrial", "cnae division 28",
    ))
    if company_eligible and sections == {"B"} and not manufacturing_evidence:
        return _bdns_gate_result(
            "reject", "extractive_sector_only",
            "La convocatoria se limita a industrias extractivas.", role,
        )
    if company_eligible and sections == {"A"} and not (cluster or consortium):
        return _bdns_gate_result(
            "reject", "primary_sector_only",
            "La convocatoria directa se limita al sector primario.", role,
        )
    if company_eligible and sections == {"F"} and not technology_fit:
        return _bdns_gate_result(
            "reject", "building_without_industrial_connection",
            "Construccion sin conexion termica o industrial explicita.", role,
        )
    if (
        company_eligible and sections
        and sections.isdisjoint(BDNS_POSITIVE_NACE_SECTIONS | {"B", "F"})
        and not technology_fit
    ):
        return _bdns_gate_result(
            "reject", "no_industrial_or_technology_connection",
            "Sectores terciarios sin conexion tecnologica relevante acreditada.", role,
        )

    hard_scope_reason = _hard_out_of_scope(conv, detect_tech_tags(combined))
    if hard_scope_reason:
        return _bdns_gate_result(
            "reject", "explicit_sector_out_of_scope", hard_scope_reason, role,
        )

    # Solo después de excluir incompatibilidades intrínsecas se verifica la
    # vigencia. Así no se descargan bases ni se paga Haiku para ayudas que nunca
    # podrían ser relevantes aunque estuvieran abiertas.
    active_status = conv.get("bdns_active_status", "unverified_recent")
    if active_status == "closed":
        return _bdns_gate_result("reject", "deadline_closed", "El cierre confirmado ya ha vencido.")
    if active_status == "unverified_old":
        return _bdns_gate_result(
            "reject", "no_active_evidence",
            "Registro antiguo sin plazo ni evidencia documental de apertura vigente.",
        )
    if active_status == "unverified_recent":
        return _bdns_gate_result(
            "hold_manual", "active_status_unverified",
            "No consta un plazo futuro ni una ventanilla indefinida verificable.",
        )

    if cluster and cluster_downstream:
        return _bdns_gate_result(
            "retain", "cluster_route_confirmed",
            "El cluster canaliza costes, financiacion o un piloto ejecutado por empresas miembro.",
            "cluster_route", ["Vía clúster"],
        )
    if consortium and consortium_direct:
        return _bdns_gate_result(
            "retain", "consortium_participation_confirmed",
            "Kalfrisa puede participar formalmente con actividad o costes elegibles propios.",
            "consortium_partner", ["Socio de consorcio"],
        )
    if cluster and not company_eligible:
        return _bdns_gate_result(
            "hold_manual", "cluster_role_unverified",
            "El cluster es elegible, pero no consta si canaliza financiacion, costes o pilotos a Kalfrisa.",
        )
    if consortium and not company_eligible:
        return _bdns_gate_result(
            "hold_manual", "consortium_role_unverified",
            "No consta si Kalfrisa puede ser socio financiado o solo contratista del consorcio.",
        )
    if not company_eligible:
        return _bdns_gate_result(
            "reject", "incompatible_beneficiary_type",
            "Los beneficiarios descritos no incluyen a Kalfrisa ni una participacion financiada directa.",
        )

    admin_type = _fold_text(conv.get("bdns_admin_type", ""))
    regions = [_fold_text(value) for value in conv.get("bdns_regions", [])]
    outside_aragon = bool(conv.get("bdns_explicit_outside_aragon")) or bool(regions) and not any(
        "aragon" in value or "espana" in value or "nacional" in value
        or "todo el territorio" in value for value in regions
    )
    subnational = (
        "autonom" in admin_type or "local" in admin_type
        or bool(conv.get("bdns_explicit_outside_aragon"))
        or (outside_aragon and "estado" not in admin_type)
    )
    territory = conv.get("bdns_territorial_requirement", "unknown")
    duration = conv.get("bdns_project_execution_days")
    if subnational and outside_aragon:
        if territory == "existing_establishment":
            return _bdns_gate_result(
                "reject", "existing_establishment_required_outside_aragon",
                "Se exige un centro ya existente en la comunidad convocante.", role,
            )
        if territory == "new_establishment_allowed":
            if duration is None:
                return _bdns_gate_result(
                    "hold_manual", "new_establishment_duration_unknown",
                    "Se permite implantar un centro, pero falta un periodo de ejecucion confirmado.", role,
                )
            if duration < BDNS_NEW_ESTABLISHMENT_MIN_DAYS:
                return _bdns_gate_result(
                    "reject", "new_establishment_period_too_short",
                    "El periodo confirmado es inferior a 730 dias y no hace viable abrir un centro.", role,
                    details={"execution_days": duration},
                )
            return _bdns_gate_result(
                "retain", "new_establishment_period_sufficient",
                "La convocatoria permite implantar el centro y confirma al menos 730 dias de ejecucion.",
                role, ["Requiere nuevo centro"], {"execution_days": duration},
            )
        if territory == "project_location_only":
            return _bdns_gate_result(
                "retain", "project_location_without_prior_establishment",
                "La ejecucion debe localizarse fuera de Aragon, sin exigir un centro previo al solicitar.", role,
            )
        if territory == "no_restriction":
            return _bdns_gate_result(
                "retain", "territorial_access_confirmed",
                "La evidencia verificada no exige un centro previo en la comunidad convocante.", role,
            )
        return _bdns_gate_result(
            "hold_manual", "territorial_eligibility_unverified",
            "Convocatoria subnacional fuera de Aragon sin requisito territorial suficientemente claro.", role,
        )

    if own_investment_fit:
        conv["opportunity_role"] = role
        return _bdns_gate_result(
            "retain", "own_investment_connection_confirmed",
            "Kalfrisa puede financiar una inversion industrial, productiva, energetica o ambiental propia.",
            role,
        )
    conv["opportunity_role"] = role
    return None


def deterministic_prefilter(conv: dict) -> dict:
    """Clasificador conservador y auditable previo a Claude.

    Solo ``reject`` elimina una oportunidad. La ausencia de evidencia produce
    ``ambiguous`` para proteger el recall.
    """
    bdns_outcome = _bdns_pre_claude_gate(conv)
    if bdns_outcome is not None:
        conv["opportunity_role"] = bdns_outcome["opportunity_role"]
        conv["opportunity_labels"] = bdns_outcome["opportunity_labels"]
        return bdns_outcome

    explicit_profile_reason = _explicit_profile_incompatibility(conv)
    if explicit_profile_reason:
        return {
            "decision": "reject",
            "reason_code": "explicit_profile_incompatibility",
            "reason": explicit_profile_reason,
            "score": 0,
            "signals": {"explicit_profile_incompatibility": True},
            "opportunity_role": "unknown",
            "opportunity_labels": [],
        }

    combined = " ".join(str(conv.get(field, "")) for field in (
        "title", "description", "org", "catalog_category",
    ))
    folded = _fold_text(combined)
    tags = detect_tech_tags(combined)
    signals = {
        "tech_tags": tags,
        "industrial": sorted({
            term for term in INDUSTRIAL_CONTEXT_TERMS if _term_present(folded, term)
        }),
        "funding": sorted({
            term for term in FUNDING_CONTEXT_TERMS if _term_present(folded, term)
        }),
        "innovation": sorted({
            term for term in INNOVATION_CONTEXT_TERMS if _term_present(folded, term)
        }),
        "enterprise": sorted({
            term for term in ENTERPRISE_CONTEXT_TERMS if _term_present(folded, term)
        }),
        "own_investment": sorted({
            term for term in BDNS_DIRECT_OWN_INVESTMENT_TERMS if term in folded
        }),
        "explicit_ineligible": sorted({
            term for term in EXPLICIT_INELIGIBLE_ONLY_TERMS if term in folded
        }),
        "unrelated_sector": sorted({
            term for term in EXPLICIT_UNRELATED_SECTOR_TERMS if term in folded
        }),
    }
    score = (
        len(tags) * 3
        + min(len(signals["industrial"]), 2) * 2
        + min(len(signals["funding"]), 2) * 2
        + min(len(signals["innovation"]), 2) * 2
        + min(len(signals["enterprise"]), 2)
        + min(len(signals["own_investment"]), 2) * 2
    )
    hard_scope_reason = _hard_out_of_scope(conv, tags)
    if signals["explicit_ineligible"]:
        decision = "reject"
        reason = "La fuente limita expresamente los beneficiarios a entidades incompatibles."
    elif hard_scope_reason:
        decision = "reject"
        reason = hard_scope_reason
    elif (
        signals["unrelated_sector"] and not tags
        and not signals["industrial"] and not signals["innovation"]
        and not signals["own_investment"]
    ):
        decision = "reject"
        reason = "Sector explícitamente ajeno sin conexión industrial o innovadora."
    elif tags and (signals["industrial"] or signals["innovation"] or len(tags) >= 2):
        decision = "retain"
        reason = "Conexión tecnológica e industrial suficiente."
    elif signals["industrial"] and signals["innovation"]:
        decision = "retain"
        reason = "Contexto industrial y de innovación suficiente."
    elif (
        signals["own_investment"] and signals["funding"]
        and signals["enterprise"]
    ):
        decision = "retain"
        reason = "Financiación empresarial directa de inversión industrial propia."
    elif (
        signals["funding"] and signals["innovation"]
        and signals["enterprise"] and score >= 8
    ):
        decision = "retain"
        reason = "Financiación empresarial e innovación expresas."
    else:
        decision = "ambiguous"
        reason = "Evidencia insuficiente para excluir con seguridad."
    return {
        "decision": decision,
        "score": score,
        "signals": signals,
        "reason": reason,
        "reason_code": "generic_deterministic_reject" if decision == "reject" else "generic_prefilter",
    }
