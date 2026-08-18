# audit.py — registro de descubrimientos excluidos durante la recopilación
#
# DISCOVERY_AUDIT es una lista mutable compartida por todo el pipeline: cada
# fuente registra en ella, vía audit_exclusion(), por qué se descartó una
# convocatoria candidata. El script principal importa este módulo y usa el
# mismo objeto lista (no una copia), así que source_hash/`.clear()`/lectura
# desde cualquier módulo ven las mismas entradas. No depende de caché, reglas
# ni Claude.

DISCOVERY_AUDIT: list[dict] = []


def audit_exclusion(
    item: dict,
    reason: str,
    stage: str,
    details: dict | None = None,
) -> None:
    """Registra un descubrimiento excluido sin guardar descripciones extensas."""
    source = str(item.get("source", "") or "DESCONOCIDA")
    identifier = str(
        item.get("identifier")
        or item.get("bdns_id")
        or item.get("catalog_ref")
        or ""
    ).strip()
    title = " ".join(str(item.get("title", "")).split())[:500]
    url = str(item.get("url", "") or item.get("official_url", "")).strip()
    record = {
        "source": source,
        "identifier": identifier,
        "title": title,
        "url": url,
        "reason": reason,
        "stage": stage,
        "deadline_date": str(item.get("deadline_date", "")),
        "open_date": str(item.get("open_date", "")),
        "bdns_id": str(item.get("bdns_id", "")),
    }
    if details:
        record["details"] = details

    key = (
        source.casefold(),
        identifier.casefold(),
        url.casefold(),
        title.casefold(),
        reason,
        stage,
    )
    if not any(entry.get("_key") == key for entry in DISCOVERY_AUDIT):
        record["_key"] = key
        DISCOVERY_AUDIT.append(record)
