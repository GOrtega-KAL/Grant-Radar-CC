# dedup.py — identidad de convocatoria y consolidación de familias documentales
#
# Una misma ayuda llega varias veces al radar: el extracto en el BOE, las bases
# reguladoras en PDF, la ficha de la sede electrónica, el registro en BDNS y a
# veces la landing del programa. Este módulo decide cuándo dos registros son la
# misma convocatoria y cuál de ellos manda, en vez de publicar duplicados o de
# quedarse con el documento menos informativo.
#
# Las tres piezas del criterio:
#
# - `_programme_identity()` reconoce programas con nombre o acrónimo propio de
#   forma conservadora: prefiere no fusionar a fusionar de más.
# - `_document_role()` clasifica cada registro (convocatoria, bases, extracto,
#   modificación, landing...) y `_document_rank()` los ordena por autoridad,
#   para que el superviviente sea el documento con más valor probatorio.
# - `_deduplicate_raw_convocations()` aplica ambas y conserva la trazabilidad:
#   lo fusionado queda en `related_document_contents` y las fuentes que
#   descubrieron cada convocatoria, en `discovery_sources`.
#
# Sin red, sin caché, sin reglas de elegibilidad y sin Claude: solo identidad
# documental.

import re

from grant_radar.audit import audit_exclusion
from grant_radar.call_text import _official_call_identifier
from grant_radar.parsing_helpers import _fold_text, select_evidence_excerpt


def _add_discovery_source(item: dict, source: str) -> None:
    values = list(item.get("discovery_sources", []))
    if source and source not in values:
        values.append(source)
    item["discovery_sources"] = values


def _programme_identity(title: str) -> tuple[str, str]:
    """Obtiene una identidad conservadora de programas con nombre/acrónimo."""
    original = " ".join(str(title).split())
    if not re.search(r"\bprograma\b", original, re.IGNORECASE):
        return "", ""
    candidates = re.findall(r"\(([^()]{3,80})\)", original)
    direct_match = re.search(
        r"\bprograma\s+([A-ZÁÉÍÓÚÜÑ0-9][A-ZÁÉÍÓÚÜÑ0-9-]{2,30})\b",
        original,
        re.IGNORECASE,
    )
    if direct_match:
        candidates.append(direct_match.group(1))

    rejected = {
        "idae",
        "miteco",
        "fnee",
        "boe",
        "mp",
        "ue",
        "union europea",
        "feder",
        "prtr",
    }
    for candidate in reversed(candidates):
        has_program_prefix = bool(re.match(
            r"^\s*programa(?:\s+de)?\s+",
            candidate,
            re.IGNORECASE,
        ))
        is_acronym = candidate == candidate.upper() and len(candidate) <= 35
        if not has_program_prefix and not is_acronym:
            continue
        display = re.sub(
            r"^\s*programa(?:\s+de)?\s+",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip(" .:-")
        folded = re.sub(r"[^a-z0-9]+", " ", _fold_text(display)).strip()
        if (
            folded
            and folded not in rejected
            and not folded.startswith(("feder ", "fnee ", "prtr "))
            and not re.fullmatch(r"20\d{2}(?:\s+20\d{2})?", folded)
            and len(folded.split()) <= 5
        ):
            return folded, display
    return "", ""


def _document_role(item: dict) -> str:
    explicit_role = str(item.get("document_role", "")).strip()
    if explicit_role:
        return explicit_role
    url = str(item.get("url", "")).casefold()
    folded = re.sub(
        r"[_-]+", " ", _fold_text(f"{item.get('title', '')} {url}")
    )
    if (
        item.get("source") == "IDAE"
        and "/ayudas-y-financiacion/" in url
    ):
        return "program_landing"
    if "extracto" in folded:
        return "call_extract"
    if "convocatoria" in folded or "se convoca" in folded:
        return "call"
    if "bases reguladoras" in folded or "orden de bases" in folded:
        return "regulatory_bases"
    if "modifica" in folded or "correccion" in folded:
        return "amendment"
    return "source_record"


def _document_rank(item: dict) -> tuple:
    role_scores = {
        "beneficiary_project_call": 95,
        "external_call_landing": 90,
        "program_landing": 100,
        "call_extract": 80,
        "call": 75,
        "source_record": 50,
        "amendment": 30,
        "regulatory_bases": 20,
    }
    role = _document_role(item)
    return (
        role_scores.get(role, 0),
        int(bool(item.get("deadline_date"))) * 10,
        int(not bool(item.get("fecha_sin_confirmar", False))) * 5,
        len(str(item.get("description", ""))),
    )


def _deduplicate_raw_convocations(convocations: list) -> list:
    """
    Consolida documentos de una misma ayuda por BDNS y, cuando falta este,
    por un nombre de programa inequívoco. Conserva la trazabilidad de todos
    los documentos relacionados.
    """
    prepared = []
    programme_bdns = {}
    for raw_item in convocations:
        item = dict(raw_item)
        bdns_id = str(item.get("bdns_id", "")).strip()
        if not bdns_id:
            bdns_match = re.search(
                r"(?:BDNS|convocatorias?/)(?:\D{0,20})?(\d{5,})",
                " ".join(
                    str(item.get(field, ""))
                    for field in ("description", "url", "bdns_url")
                ),
                re.IGNORECASE,
            )
            bdns_id = bdns_match.group(1) if bdns_match else ""
        programme_key, programme_name = _programme_identity(item.get("title", ""))
        item["bdns_id"] = bdns_id
        item["identifier"] = str(item.get("identifier", "")).strip()
        if not item["identifier"]:
            item["identifier"] = _official_call_identifier(" ".join(
                str(item.get(field, "")) for field in ("title", "description", "url")
            ))
        item["document_role"] = _document_role(item)
        _add_discovery_source(item, str(item.get("source", "")))
        if programme_key:
            item["programme_key"] = programme_key
            item["programme_name"] = programme_name
            if bdns_id:
                programme_bdns.setdefault(programme_key, set()).add(bdns_id)
        prepared.append(item)

    # Propaga el BDNS a bases y páginas del mismo programa solo cuando la
    # relación es unívoca en la ejecución actual.
    for item in prepared:
        programme_key = item.get("programme_key", "")
        known_ids = programme_bdns.get(programme_key, set())
        if not item.get("bdns_id") and len(known_ids) == 1:
            item["bdns_id"] = next(iter(known_ids))
            item["bdns_url"] = (
                "https://www.pap.hacienda.gob.es/bdnstrans/GE/es/convocatorias/"
                + item["bdns_id"]
            )

    merged = {}
    for item in prepared:
        bdns_id = str(item.get("bdns_id", "")).strip()
        clean_url = re.sub(
            r"[?#].*$",
            "",
            str(item.get("url", "")).strip().rstrip("/").casefold(),
        )
        identifier = str(item.get("identifier", "")).strip().casefold()
        if bdns_id:
            key = f"bdns:{bdns_id}"
        elif identifier:
            key = f"identifier:{identifier}"
        elif item.get("programme_key"):
            key = f"programme:{item['programme_key']}"
        elif clean_url:
            key = f"url:{clean_url}"
        else:
            key = (
                f"title:{item.get('source', '')}:"
                f"{re.sub(r'\\W+', ' ', _fold_text(item.get('title', ''))).strip()}"
            )

        previous = merged.get(key)
        if previous is None:
            merged[key] = dict(item)
            continue

        previous_is_catalog = bool(previous.get("discovered_via"))
        item_is_catalog = bool(item.get("discovered_via"))
        has_strong_identity = bool(
            bdns_id or identifier or item.get("programme_key")
        )
        if not has_strong_identity and not previous_is_catalog and not item_is_catalog:
            # La deduplicación transversal se limita al agregador. Dos fuentes
            # directas pueden compartir una landing genérica y seguir siendo
            # convocatorias distintas.
            direct_key = (
                f"{key}|direct:{item.get('source', '')}:"
                f"{re.sub(r'\\W+', ' ', _fold_text(item.get('title', ''))).strip()}"
            )
            merged[direct_key] = dict(item)
            continue
        if _document_rank(item) > _document_rank(previous):
            primary, secondary = dict(item), previous
        else:
            primary, secondary = previous, item

        related_documents = []
        for document in (
            previous.get("related_documents_trace", [])
            + item.get("related_documents_trace", [])
            + [previous, item]
        ):
            trace = {
                "source": document.get("source", ""),
                "title": document.get("title", ""),
                "url": document.get("url", ""),
                "document_role": document.get(
                    "document_role", _document_role(document)
                ),
            }
            if trace not in related_documents:
                related_documents.append(trace)
        primary["related_documents_trace"] = related_documents
        primary["related_documents_count"] = len(related_documents)

        related_contents = []
        for document in (
            previous.get("related_document_contents", [])
            + item.get("related_document_contents", [])
            + [previous, item]
        ):
            content = {
                "source": document.get("source", ""),
                "title": document.get("title", ""),
                "url": document.get("url", ""),
                "document_role": document.get(
                    "document_role", _document_role(document)
                ),
                "description": select_evidence_excerpt(
                    document.get("description", ""),
                    document.get("title", ""),
                    12_000,
                ),
            }
            content_key = (
                content["source"].casefold(),
                content["title"].casefold(),
                content["url"].casefold(),
            )
            if not any(
                (
                    existing["source"].casefold(),
                    existing["title"].casefold(),
                    existing["url"].casefold(),
                ) == content_key
                for existing in related_contents
            ):
                related_contents.append(content)
        primary["related_document_contents"] = related_contents
        audit_exclusion(
            secondary,
            "merged_related_document",
            "identity_consolidation",
            {
                "identity": key,
                "primary_title": primary.get("title", ""),
            },
        )

        for field in (
            "discovered_via",
            "catalog_scope",
            "catalog_category",
            "catalog_ref",
            "bdns_id",
            "bdns_url",
            "related_documents_count",
            "programme_key",
            "programme_name",
            "identifier",
            "bdns_filter_ready",
            "bdns_active_status",
            "bdns_received_date",
            "bdns_admin_type",
            "bdns_admin_levels",
            "bdns_regions",
            "bdns_beneficiary_types",
            "bdns_company_eligible",
            "bdns_nace_codes",
            "bdns_nace_sections",
            "bdns_finality",
            "bdns_objectives",
            "bdns_instruments",
            "bdns_award_mode",
            "bdns_call_access",
            "bdns_territorial_requirement",
            "bdns_explicit_outside_aragon",
            "bdns_project_execution_days",
            "bdns_is_open_ended",
            "bdns_state_aid_reference",
            "bdns_is_mrr",
            "bdns_documents",
        ):
            if not primary.get(field) and secondary.get(field):
                primary[field] = secondary[field]

        if (
            primary.get("opportunity_role", "unknown") == "unknown"
            and secondary.get("opportunity_role", "unknown") != "unknown"
        ):
            primary["opportunity_role"] = secondary["opportunity_role"]
        primary["opportunity_labels"] = sorted(set(
            primary.get("opportunity_labels", [])
            + secondary.get("opportunity_labels", [])
        ))

        primary["keywords_found"] = sorted(set(
            primary.get("keywords_found", []) + secondary.get("keywords_found", [])
        ))
        primary["discovery_sources"] = sorted(set(
            primary.get("discovery_sources", [])
            + secondary.get("discovery_sources", [])
            + [str(primary.get("source", "")), str(secondary.get("source", ""))]
        ) - {""})
        mechanisms = {
            primary.get("funding_mechanism", "unknown"),
            secondary.get("funding_mechanism", "unknown"),
        }
        primary["funding_mechanism"] = (
            "cascade" if "cascade" in mechanisms
            else "direct" if "direct" in mechanisms
            else "unknown"
        )
        if (
            primary.get("fecha_sin_confirmar", True)
            and not secondary.get("fecha_sin_confirmar", True)
        ):
            for field in (
                "deadline_days",
                "deadline_date",
                "open_date",
                "fecha_sin_confirmar",
                "fecha_prevista",
            ):
                primary[field] = secondary.get(field)
        if len(primary.get("description", "")) < 100 and secondary.get("description"):
            primary["description"] = secondary["description"]
        primary["identity_only"] = bool(
            primary.get("identity_only", False)
            and secondary.get("identity_only", False)
        )
        merged[key] = primary

    consolidated = []
    for item in merged.values():
        if item.get("identity_only"):
            audit_exclusion(
                item,
                "unmatched_identity_landing",
                "identity_consolidation",
            )
            continue
        consolidated.append(item)
    return consolidated
