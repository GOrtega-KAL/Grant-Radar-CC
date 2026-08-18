# boa_aragon.py — conector BOA (Boletín Oficial de Aragón)
#
# Primer conector de fuente extraído del script principal (ver AGENTS.md,
# sección 25): Playwright sobre búsquedas BOA/aragon.es, con un catálogo
# estático curado como respaldo cuando la navegación en vivo no devuelve
# resultados. Sin dependencias de caché ni de Claude.
#
# `browser` se tipa como `Any` en vez de importar `PlaywrightBrowser`: esa
# clase vive en Grant-Radar-prueba.py, cuyo nombre con guiones no es un
# módulo importable. Solo se usa aquí `browser.html(url) -> str | None`.

import logging
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from grant_radar.audit import audit_exclusion
from grant_radar.parsing_helpers import (
    _absolute_url,
    _days_until,
    _es_titulo_valido,
    _extract_date_range,
)
from grant_radar.tech_taxonomy import is_relevant, keyword_match

log = logging.getLogger("grant_radar")


def _fetch_boa_static() -> list:
    """
    BOA (Boletín Oficial de Aragón) — catálogo estático de respaldo.

    MANTENIMIENTO del catálogo estático: revisar cuando se publiquen nuevas
    convocatorias del Gobierno de Aragón relevantes para industria/energía.
    Fuente: https://www.aragon.es/temas/industria-energia-mineria/ayudas-subvenciones
    y https://www.boa.aragon.es
    Última revisión: 2026-04-09
    """
    log.info("BOA: usando catálogo estático de respaldo...")
    results = []

    # ── Catálogo estático BOA/Aragón curado ──────────────────────────
    # ESTADO: ★ = abierta confirmada | ◷ = fecha prevista | ✗ = cerrada (no incluir)
    # Fuentes: BOA, aragon.es/tramitador, última revisión 2026-04-09
    _BOA_STATIC = [
        {
            # ★ ABIERTA: 06/02/2026 – 05/05/2026 (confirmado por el usuario)
            "title":        "Fondo de Transición Justa 2026 — Inversión PYME provincia de Teruel",
            "description":  "Subvenciones del Fondo de Transición Justa para proyectos de inversión "
                            "de pequeñas y medianas empresas en la provincia de Teruel. Incluye "
                            "transformación ecológica de la industria, eficiencia energética y "
                            "economía circular. Dotación 2,5 M€. Compatible con proyectos de "
                            "descarbonización de procesos industriales en Aragón.",
            "open_date":    "2026-02-06",
            "deadline_date": "2026-05-05",
            "fecha_prevista": False,
            "budget":       "2.500.000 € total · subvención a fondo perdido",
            "url":          "https://www.aragon.es/tramitador/-/tramite/ayudas-a-pequenas-y-medianas-empresas-de-la-provincia-de-teruel-para-proyectos-de-inversion-fondo-de-transicion-justa",
            "keywords":     ["descarbonización", "eficiencia energética", "emisiones industriales",
                             "transición energética", "economía baja en carbono"],
        },
        {
            # ✗ CERRADA: la convocatoria oficial TDI-Feder 2026 finalizó el
            # 15/01/2026. Se conserva para trazabilidad y el filtro la excluye.
            "title":        "PAIP — Convocatoria 2026 Línea TDI-Feder",
            "description":  "Programa de ayudas del Gobierno de Aragón a la industria y PYME para "
                            "proyectos empresariales de transformación y desarrollo industrial "
                            "en Aragón dentro de la línea TDI-Feder. Convocatoria cerrada.",
            "open_date":    "2025-10-25",
            "deadline_date": "2026-01-15",
            "fecha_prevista": False,
            "budget":       "Ver convocatoria (subvención a fondo perdido)",
            "url":          "https://www.aragon.es/tramitador/-/tramite/ayudas-industria-digital-integradora-sostenible-marco-programa-ayudas-industria-pyme-aragon-paip/convocatoria-2026-en-desarrollo",
            "keywords":     ["eficiencia energética", "eficiencia térmica", "hornos industriales"],
        },
    ]

    for c in _BOA_STATIC:
        close_str       = c.get("deadline_date", "")
        open_str        = c.get("open_date", "")
        es_prevista     = c.get("fecha_prevista", False)
        deadline_days   = _days_until(close_str) if close_str else 120
        if deadline_days <= 0 and not es_prevista:
            log.debug(f"  BOA estático: descartando cerrada: {c['title'][:60]}")
            audit_exclusion(
                {
                    "source": "BOA ARAGÓN",
                    "title": c["title"],
                    "url": c["url"],
                    "open_date": open_str,
                    "deadline_date": close_str,
                },
                "deadline_closed",
                "boa_static_filter",
            )
            continue
        results.append({
            "source":              "BOA ARAGÓN",
            "title":               c["title"],
            "description":         c["description"],
            "deadline_days":       deadline_days,
            "deadline_date":       close_str,
            "open_date":           open_str,
            "fecha_sin_confirmar": not bool(close_str) or es_prevista,
            "fecha_prevista":      es_prevista,
            "budget":              c["budget"],
            "url":                 c["url"],
            "keywords_found":      c["keywords"],
            "org":                 "Gobierno de Aragón",
            "source_type":         "Catálogo curado",
        })
    log.info(f"  → {len(results)} convocatorias BOA cargadas desde el respaldo")
    return results


def _fetch_boa_playwright(browser: Any) -> list:
    """Consulta con Chromium búsquedas BOA y ayudas del Gobierno de Aragón."""
    targets = [
        "https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI?CMD=VERDOC&BASE=BODA&DOCS=1-40&SEPARADOR=&&RANG-C=20250101-&TEXT-TEXT=eficiencia+energetica+industria",
        "https://www.boa.aragon.es/cgi-bin/EBOA/BRSCGI?CMD=VERDOC&BASE=BODA&DOCS=1-40&SEPARADOR=&&RANG-C=20250101-&TEXT-TEXT=hidrogeno+industria",
        "https://www.aragon.es/temas/industria-energia-mineria/ayudas-subvenciones-industria-energia-mineria",
    ]
    results = []
    seen = set()
    active_marker = re.compile(
        rf"(?:en plazo|plazo permanente|convocatoria\s+{datetime.now().year}|"
        rf"{datetime.now().year}\s+en desarrollo)",
        re.IGNORECASE,
    )
    excluded_scope = re.compile(
        r"(regad[ií]o|agropecuari|agricultur|ganader|vivienda|residencial|"
        r"movilidad|veh[ií]culo|transporte)",
        re.IGNORECASE,
    )

    for target_url in targets:
        html = browser.html(target_url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        base = "https://www.boa.aragon.es" if "boa.aragon.es" in target_url else "https://www.aragon.es"

        for anchor in soup.find_all("a", href=True):
            title = " ".join(anchor.get_text(" ", strip=True).split())
            href = anchor.get("href", "").strip()
            container = anchor.find_parent(["article", "li", "tr", "div"])
            context_text = container.get_text(" ", strip=True) if container else title
            combined = f"{title} {context_text}"
            if (
                len(title) < 20
                or title in seen
                or not _es_titulo_valido(title)
                or not is_relevant(combined)
                or "fuera de plazo" in combined.lower()
                or excluded_scope.search(combined)
                or not active_marker.search(combined)
            ):
                continue
            seen.add(title)
            open_date, deadline_date = _extract_date_range(context_text)
            deadline_days = _days_until(deadline_date) if deadline_date else 60
            if deadline_date and deadline_days <= 0:
                continue
            results.append({
                "source":              "BOA ARAGÓN",
                "title":               title[:240],
                "description":         context_text[:2_000],
                "deadline_days":       deadline_days,
                "deadline_date":       deadline_date,
                "open_date":           open_date,
                "fecha_sin_confirmar": not bool(deadline_date),
                "fecha_prevista":      False,
                "budget":              "Ver disposición",
                "url":                 _absolute_url(base, href),
                "keywords_found":      keyword_match(combined),
                "org":                 "Gobierno de Aragón",
                "source_type":         "Playwright BOA",
            })

    log.info(f"  BOA Playwright: {len(results)} convocatorias relevantes")
    return results


def fetch_boa(browser: Any) -> list:
    results = _fetch_boa_playwright(browser)
    if results:
        return results
    log.warning("BOA: navegación en vivo sin resultados; activando catálogo estático")
    return _fetch_boa_static()
