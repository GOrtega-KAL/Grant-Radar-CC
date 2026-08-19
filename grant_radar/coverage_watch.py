# coverage_watch.py — vigilancia de programas recurrentes conocidos
#
# Comprueba que las oportunidades estratégicas que ya aparecieron en
# ejecuciones anteriores siguen apareciendo. No crea convocatorias ni altera la
# relevancia de nada: si un programa conocido deja de encontrarse, lo dice, que
# es la señal de que un parser se ha roto o una fuente ha cambiado.
#
# Es deliberadamente asimétrica: vigila que no se pierdan programas relevantes,
# no recuerda descartes de programas irrelevantes (ver AGENTS.md sección 27,
# donde se evaluó reutilizarla para lo segundo y se descartó).

import logging
from datetime import datetime

from bs4 import BeautifulSoup

from grant_radar.parsing_helpers import (
    _days_until,
    _extract_application_dates,
    _fold_text,
)
from grant_radar.runtime_state import IDENTITY_LANDINGS

log = logging.getLogger("grant_radar")


RECURRENT_COVERAGE_WATCH = [
    {
        "key": "programa_innovae",
        "label": "Programa INNOVAE",
        "aliases": [
            "innovae",
            "proyectos singulares innovadores de ahorro y eficiencia energética",
        ],
        "url": "https://www.idae.es/ayudas-y-financiacion/programa-innovae",
    },
    {
        "key": "aragon_tecnologias_limpias",
        "label": "Ayudas Aragón para inversiones productivas en tecnologías limpias",
        "aliases": [
            "inversiones productivas en tecnologías limpias",
            "inversiones productivas en tecnologias limpias",
        ],
        "url": (
            "https://www.aragon.es/tramitador/-/tramite/"
            "ayudas-para-el-fomento-de-inversiones-productivas-en-tecnologias-"
            "limpias-y-eficientes-en-el-uso-de-los-recursos/convocatoria-2026"
        ),
    },
    {
        "key": "paip_aragon",
        "label": "PAIP Aragón",
        "aliases": [
            "programa de ayudas a la industria y la pyme en aragón",
            "programa de ayudas a la industria y la pyme en aragon",
            "paip",
        ],
        "url": (
            "https://www.aragon.es/tramitador/-/tramite/"
            "ayudas-industria-digital-integradora-sostenible-marco-programa-"
            "ayudas-industria-pyme-aragon-paip/convocatoria-2026-en-desarrollo"
        ),
        "recurrence": "annual",
        "expected_start_month": 9,
    },
    {
        "key": "horizon_heat_upgrade",
        "label": "HORIZON-CL5-2026-09-D4-08",
        "aliases": [
            "horizon-cl5-2026-09-d4-08",
            "full-scale demonstration of heat upgrade solutions in industrial processes",
        ],
        "url": (
            "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
            "screen/opportunities/topic-details/HORIZON-CL5-2026-09-D4-08"
        ),
    },
]


def build_recurrent_coverage_watch(items: list[dict]) -> list[dict]:
    """
    Comprueba identidades recurrentes sin introducir datos manuales en el radar.

    ``active_captured`` indica que una fuente produjo una convocatoria;
    ``landing_only`` que solo se observó su página de programa; ``not_observed``
    activa una advertencia para revisar si cambió una fuente o aún no se publicó.
    """
    checks = []
    for expected in RECURRENT_COVERAGE_WATCH:
        matches = []
        for item in items:
            searchable = _fold_text(" ".join(str(value) for value in (
                item.get("identifier", ""),
                item.get("title", ""),
                item.get("description", ""),
                item.get("url", ""),
            )))
            if any(_fold_text(alias) in searchable for alias in expected["aliases"]):
                matches.append(item)

        active = [item for item in matches if not item.get("identity_only", False)]
        if active:
            status = "active_captured"
        elif matches:
            status = "landing_only"
        else:
            status = "not_observed"

        checks.append({
            "key": expected["key"],
            "label": expected["label"],
            "status": status,
            "matches": len(matches),
            "sources": sorted({
                str(item.get("source", "")) for item in matches
                if item.get("source")
            }),
            "url": expected.get("url", ""),
            "deadline_date": "",
            "recurrence": expected.get("recurrence", ""),
            "expected_start_month": expected.get("expected_start_month"),
        })
    return checks


def probe_missing_recurrent_coverage(browser, items: list[dict]) -> list[dict]:
    """
    Verifica las landings conocidas solo cuando el descubrimiento general falla.

    Es un control de calidad: no añade esas páginas a las convocatorias. Permite
    distinguir una convocatoria cerrada conocida de una regresión real.
    """
    checks = build_recurrent_coverage_watch(items)
    for check in checks:
        if check["status"] != "not_observed" or not check.get("url"):
            continue
        html = browser.html(check["url"])
        if not html:
            continue
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        _, deadline_date = _extract_application_dates(text)
        check["deadline_date"] = deadline_date
        folded = _fold_text(text)
        if (
            (deadline_date and (_days_until(deadline_date) or 0) <= 0)
            or "fuera de plazo" in folded
            or "plazo cerrado" in folded
        ):
            if check.get("recurrence") == "annual":
                expected_month = int(check.get("expected_start_month") or 1)
                check["status"] = (
                    "seasonal_pending"
                    if datetime.now().month < expected_month
                    else "republication_not_observed"
                )
            else:
                check["status"] = "closed_observed"
        elif deadline_date and (_days_until(deadline_date) or 0) > 0:
            check["status"] = "active_not_captured"
        else:
            check["status"] = "landing_observed"
    return checks
