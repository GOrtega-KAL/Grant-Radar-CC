import io
import json
import runpy
import tempfile
import unittest
import threading
import zipfile
from types import SimpleNamespace
from unittest import mock
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]
APP = runpy.run_path(str(ROOT / "Grant-Radar-prueba.py"))

# Estas funciones vivían en Grant-Radar-prueba.py y se probaban vía
# APP["nombre"]; ahora viven en módulos de grant_radar/ (ver SUGERENCIAS.MD
# 3.2). El script principal solo reimporta las que usa él mismo —los nombres
# públicos de cada conector, por ejemplo, pero no sus helpers privados—, así
# que no todas quedan en APP tras el runpy. Se añaden aquí para no reescribir
# los sitios de este archivo que ya las buscan por ese nombre; los tests
# nuevos de esos módulos (test_grant_radar_*.py) las importan de forma
# estándar.
#
# Ojo: los tests que sustituyen dependencias con
# `mock.patch.dict(APP["fn"].__globals__, ...)` siguen funcionando sin cambios
# tras mover una función a un módulo, porque `__globals__` apunta al módulo
# donde queda definida, no al script principal.
from grant_radar import cache as _cache_module
from grant_radar import deterministic_rules as _rules_module
from grant_radar import claude_selection as _selection_module
from grant_radar import claude_usage as _usage_module
from grant_radar import hold_quotes as _quotes_module
from grant_radar import coverage_watch as _coverage_module
from grant_radar import public_output as _public_output_module
from grant_radar import analysis as _analysis_module
from grant_radar import holds as _holds_module
from grant_radar import profile_scope as _profile_scope_module
from grant_radar import bdns_rules as _bdns_rules_module
from grant_radar.sources import bdns as _bdns_module
from grant_radar.sources import cdti as _cdti_module
from grant_radar.sources import eccp as _eccp_module
from grant_radar.sources import een as _een_module
from grant_radar.sources import idae as _idae_module

for _module in (
    _cache_module, _rules_module, _public_output_module,
    _selection_module, _coverage_module, _usage_module, _quotes_module,
    _analysis_module, _profile_scope_module, _holds_module, _bdns_rules_module,
    _bdns_module, _cdti_module, _eccp_module, _een_module, _idae_module,
):
    for _name in dir(_module):
        if not _name.startswith("_") or _name.startswith("__"):
            continue
        APP.setdefault(_name, getattr(_module, _name))
APP.setdefault("deterministic_prefilter", _bdns_rules_module.deterministic_prefilter)
APP.setdefault("apply_current_deterministic_rules", _rules_module.apply_current_deterministic_rules)
APP.setdefault("filter_usable_cache", _cache_module.filter_usable_cache)
APP.setdefault("analysis_is_usable", _cache_module.analysis_is_usable)
APP.setdefault("cache_key", _cache_module.cache_key)
APP.setdefault("cache_load", _cache_module.cache_load)
APP.setdefault("cache_save", _cache_module.cache_save)
APP.setdefault("source_hash", _cache_module.source_hash)
# Constantes públicas del conector BDNS: el bucle de arriba solo copia nombres
# privados, y el script principal no las reimporta porque no las usa él.
APP.setdefault("BDNS_LATEST_MAX_PAGES", _bdns_module.BDNS_LATEST_MAX_PAGES)
APP.setdefault("BDNS_PAGE_SIZE", _bdns_module.BDNS_PAGE_SIZE)
# Igual con las de la capa de análisis: el presupuesto de evidencia y el techo
# de salida son públicos y el script ya no los usa desde que la capa se extrajo
# (AGENTS.md, sección 48).
for _name in (
    "EVIDENCE_SOURCE_DESCRIPTION_BUDGET", "EVIDENCE_MAX_RELATED_DOCUMENTS",
    "EVIDENCE_PER_DOCUMENT_BUDGET", "EVIDENCE_TOTAL_DOCUMENT_BUDGET",
    "STRUCTURED_OUTPUT_TOKEN_CEILING", "STABLE_CACHED_DOCUMENT_ROLES",
    "BDNS_STRUCTURED_PROMPT_FIELDS",
):
    APP.setdefault(_name, getattr(_analysis_module, _name))
# Dos nombres que el script reimportaba sin usarlos y que solo necesita este
# arnés: se toman de su módulo, que es de donde vienen. Llegaban de rebote por
# el runpy, y eso ataba los imports del script a las pruebas.
from grant_radar.hold_evidence import retrieve_bdns_hold_evidence as _retrieve_evidence  # noqa: E402
from grant_radar.tech_taxonomy import TECH_TAGS as _TECH_TAGS  # noqa: E402

APP.setdefault("retrieve_bdns_hold_evidence", _retrieve_evidence)
APP.setdefault("TECH_TAGS", _TECH_TAGS)
# Y con las públicas del dominio de holds, extraído el 31/08/2026: el script
# solo reimporta las tres entradas que llama run_pipeline().
for _name in (
    "BDNS_HOLD_AI_VERSION", "BDNS_HOLD_CACHE_FILE", "BDNS_HOLD_REPORT_FILE",
    "BDNS_HOLD_REPLAY_FILE", "apply_verified_bdns_hold_resolution",
    "replay_bdns_hold_item", "replay_bdns_hold_report",
    "resolve_bdns_holds_for_pipeline", "resolve_hold_deterministically",
    "run_bdns_hold_pilot", "select_bdns_hold_pilot",
    "select_bdns_hold_qa_sample", "analyze_bdns_hold_with_claude",
):
    APP.setdefault(_name, getattr(_holds_module, _name))


class SourceParserTests(unittest.TestCase):
    def test_boe_inventory_keeps_active_idae_call_and_records_health(self):
        inventory = """
        <ul><li class="resultado-busqueda">
          <p class="linea-dem">Ministerio para la Transición Ecológica y el Reto Demográfico (BOE 1 de 01/01/2099)</p>
          <p>Extracto del Instituto para la Diversificación y Ahorro de la Energía por el que se convoca el programa de proyectos singulares innovadores de ahorro y eficiencia energética (INNOVAE).</p>
          <a href="../buscar/doc.php?id=BOE-B-2099-100">Ir al documento</a>
        </li></ul>
        """
        detail = """
        <html><h3>Extracto de la convocatoria del Programa INNOVAE</h3><body>
        BDNS(Identif.): 990100. Las solicitudes podrán presentarse desde el
        1 de septiembre de 2099 hasta el 30 de noviembre de 2099.
        </body></html>
        """

        calls = []

        class FakeBrowser:
            def html(self, url, **kwargs):
                calls.append(url)
                return inventory if url.endswith("ayudas.php") else detail

        APP["SOURCE_RUNTIME_METADATA"].clear()
        APP["RUN_DIAGNOSTICS"].clear()
        results = APP["fetch_boe"](FakeBrowser())
        self.assertEqual(len(results), 1, {"audit": APP["DISCOVERY_AUDIT"], "calls": calls})
        self.assertEqual(results[0]["bdns_id"], "990100")
        self.assertEqual(results[0]["deadline_date"], "2099-11-30")
        self.assertTrue(results[0]["title"].startswith("Extracto de la convocatoria"))
        metadata = APP["SOURCE_RUNTIME_METADATA"]["BOE / MITECO"]
        self.assertEqual(metadata["inventory_count"], 1)
        self.assertEqual(metadata["detail_loaded"], 1)
        self.assertEqual(metadata["accepted_count"], 1)

    def test_public_url_normalization_only_adds_missing_web_scheme(self):
        normalize = APP["_normalize_public_url"]
        self.assertEqual(normalize("www.navarra.es"), "https://www.navarra.es")
        self.assertEqual(normalize("sede.uco.es/ruta"), "https://sede.uco.es/ruta")
        self.assertEqual(
            normalize("http://example.test/call"),
            "http://example.test/call",
        )
        self.assertEqual(normalize("contacto@example.test"), "contacto@example.test")
        self.assertEqual(normalize("Ver convocatoria"), "Ver convocatoria")

    def test_a_sentence_with_a_scheme_is_not_published_as_a_link(self):
        # Punto 31 del backlog: la BDNS 922117 publicó como `url` una frase
        # entera con el esquema mal escrito, y viajó así al JSON y al export.
        normalize = APP["_normalize_public_url"]
        self.assertEqual(
            normalize(
                "hhtp://www.aragon.es/tramites), incluyendo en el buscador de "
                "trámites el procedimiento número 11810"
            ),
            "",
        )
        self.assertEqual(
            normalize("https://example.test/bases y también en la sede"),
            "https://example.test/bases",
        )

    def test_bdns_falls_back_to_the_official_page_when_the_sede_is_prose(self):
        raw = APP["_bdns_detail_to_raw"](
            {
                "codigoBDNS": 922117,
                "descripcion": "Ayudas para certámenes feriales",
                "fechaFinSolicitud": "2026-09-17",
                "sedeElectronica": (
                    "hhtp://www.aragon.es/tramites), incluyendo en el buscador "
                    "de trámites el procedimiento número 11810"
                ),
                "tiposBeneficiarios": [{"descripcion": "Empresas"}],
            },
            {"numeroConvocatoria": 922117},
        )
        self.assertEqual(
            raw["url"],
            f"{APP['BDNS_PUBLIC_BASE']}/922117",
            "una sede electrónica ilegible debe caer al enlace oficial de BDNS",
        )

    def test_bdns_detail_keeps_strong_identity_and_documents(self):
        raw = APP["_bdns_detail_to_raw"](
            {
                "codigoBDNS": 900001,
                "descripcion": "Ayudas a proyectos de eficiencia energética industrial",
                "fechaInicioSolicitud": "2026-08-01",
                "fechaFinSolicitud": "2026-12-31",
                "presupuestoTotal": 2500000,
                "sedeElectronica": "https://example.test/apply",
                "tiposBeneficiarios": [{"descripcion": "Empresas"}],
                "documentos": [{
                    "nombre": "Bases reguladoras",
                    "url": "https://administracion.example/bases.pdf",
                }],
            },
            {"numeroConvocatoria": 900001},
        )
        self.assertEqual(raw["bdns_id"], "900001")
        self.assertEqual(raw["deadline_date"], "2026-12-31")
        self.assertEqual(raw["funding_mechanism"], "direct")
        self.assertIn("Bases reguladoras", raw["description"])
        self.assertTrue(raw["bdns_filter_ready"])
        self.assertTrue(raw["bdns_company_eligible"])
        self.assertEqual(raw["bdns_active_status"], "confirmed_deadline")
        self.assertEqual(
            raw["bdns_documents"][0]["url"],
            "https://administracion.example/bases.pdf",
        )

    def test_bdns_old_record_is_not_reopened_by_stale_api_flag(self):
        raw = APP["_bdns_detail_to_raw"](
            {
                "codigoBDNS": 900002,
                "descripcion": "Ayudas históricas de eficiencia energética industrial",
                "fechaRecepcion": "2022-05-10",
                "abierto": True,
                "tiposBeneficiarios": [{"descripcion": "Empresas"}],
            },
            {"numeroConvocatoria": 900002},
        )
        self.assertEqual(raw["bdns_active_status"], "unverified_old")
        self.assertTrue(raw["bdns_api_open_flag"])
        outcome = APP["_bdns_pre_claude_gate"](raw)
        self.assertEqual(outcome["decision"], "reject")
        self.assertEqual(outcome["reason_code"], "no_active_evidence")

    def test_bdns_text_fin_is_parsed_before_creating_a_hold(self):
        raw = APP["_bdns_detail_to_raw"](
            {
                "codigoBDNS": 900003,
                "descripcion": "Ayudas industriales",
                "textInicio": "01/09/2098",
                "textFin": "30/09/2099",
                "fechaRecepcion": "2098-08-01",
                "tiposBeneficiarios": [{"descripcion": "Empresas"}],
            },
            {"numeroConvocatoria": 900003},
        )
        self.assertEqual(raw["open_date"], "2098-09-01")
        self.assertEqual(raw["deadline_date"], "2099-09-30")
        self.assertEqual(raw["bdns_active_status"], "confirmed_deadline")

    def test_bdns_relative_deadline_uses_official_announcement_date(self):
        raw = APP["_bdns_detail_to_raw"](
            {
                "codigoBDNS": 900004,
                "descripcion": "Ayudas industriales",
                "textFin": "30 días naturales desde la publicación del extracto",
                "fechaRecepcion": "2099-01-01",
                "tiposBeneficiarios": [{"descripcion": "Empresas"}],
                "anuncios": [{"datPublicacion": "2099-01-01"}],
            },
            {"numeroConvocatoria": 900004},
        )
        self.assertEqual(raw["bdns_call_publication_date"], "2099-01-01")
        self.assertEqual(raw["deadline_date"], "2099-01-31")
        self.assertFalse(raw["fecha_sin_confirmar"])

    def test_bdns_relative_deadline_can_use_current_call_document_date(self):
        raw = APP["_bdns_detail_to_raw"](
            {
                "codigoBDNS": 900005,
                "descripcion": "Ayudas industriales",
                "textFin": "Un mes desde la publicación de la convocatoria",
                "fechaRecepcion": "2099-02-01",
                "tiposBeneficiarios": [{"descripcion": "Empresas"}],
                "documentos": [{
                    "id": 10,
                    "descripcion": "Texto en castellano de la convocatoria",
                    "datPublicacion": "2099-02-02",
                }],
            },
            {"numeroConvocatoria": 900005},
        )
        self.assertEqual(raw["bdns_call_publication_date"], "2099-02-02")
        self.assertEqual(raw["deadline_date"], "2099-03-02")

    def test_bdns_business_day_deadline_is_marked_estimated(self):
        deadline, estimated = APP["_bdns_relative_application_deadline"](
            "10 días hábiles desde el día siguiente a la publicación",
            "2099-01-01",
        )
        self.assertTrue(deadline)
        self.assertTrue(estimated)
        self.assertEqual(APP["_parse_flexible_date"]("26.08.2099"), "2099-08-26")

    def test_bdns_document_id_builds_the_official_download_endpoint(self):
        records = APP["_bdns_document_records"]({
            "documentos": [{
                "id": 1503373,
                "descripcion": "Texto de la convocatoria",
                "nombreFic": "CONVENIO PDF.pdf",
                "datPublicacion": "2026-07-31",
            }]
        })
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_key"], "id")
        self.assertIn("idDocumento=1503373", records[0]["url"])
        self.assertEqual(records[0]["published_date"], "2026-07-31")

    def test_bdns_official_document_text_is_reused_without_second_download(self):
        response = mock.Mock()
        response.url = (
            "https://www.infosubvenciones.es/bdnstrans/api/"
            "convocatorias/documentos?idDocumento=1503373"
        )
        response.content = (
            b"<html><main>Official industrial energy efficiency grant bases "
            b"for manufacturing companies with eligible productive investment."
            b"</main></html>"
        )
        response.headers = {"content-type": "text/html; charset=utf-8"}
        response.encoding = "utf-8"
        conv = {
            "bdns_id": "900001",
            "title": "Ayuda industrial",
            "bdns_documents": [{
                "title": "Bases",
                "url": response.url,
                "kind": "document",
                "source_key": "id",
                "published_date": "2026-08-01",
            }],
        }
        globals_dict = APP["retrieve_bdns_hold_evidence"].__globals__
        state = globals_dict["_BDNS_DOCUMENT_CACHE_STATE"]
        with tempfile.TemporaryDirectory() as temporary:
            cache_path = str(Path(temporary) / "documents.json")
            http_get = mock.Mock(return_value=response)
            with mock.patch.dict(state, {"path": "", "entries": {}}, clear=True), \
                    mock.patch.dict(globals_dict, {
                        "BDNS_DOCUMENT_CACHE_FILE": cache_path,
                        "_http_get": http_get,
                    }):
                # La regla intrínseca se inyecta: aquí no se prueba el
                # filtrado, solo que el texto ya descargado no se vuelve a pedir.
                sin_exclusion = lambda conv, texto="": None  # noqa: E731
                first = APP["retrieve_bdns_hold_evidence"](
                    conv, intrinsic_exclusion=sin_exclusion
                )
                second = APP["retrieve_bdns_hold_evidence"](
                    conv, intrinsic_exclusion=sin_exclusion
                )
            self.assertTrue(Path(cache_path).exists())
        self.assertEqual(http_get.call_count, 1)
        self.assertEqual(first["metrics"]["cache_misses"], 1)
        self.assertEqual(first["metrics"]["cache_hits"], 0)
        self.assertEqual(second["metrics"]["cache_hits"], 1)
        self.assertEqual(second["metrics"]["fetched_urls"], 0)
        self.assertEqual(second["metrics"]["bytes"], 0)

    def test_named_grant_title_is_classified_without_checking_vigency(self):
        raw = APP["_bdns_detail_to_raw"](
            {
                "codigoBDNS": 900006,
                "descripcion": "Subvención a favor del Ayuntamiento para obras",
                "fechaRecepcion": "2099-01-01",
                "tiposBeneficiarios": [{"descripcion": "Ayuntamiento"}],
            },
            {"numeroConvocatoria": 900006},
        )
        self.assertEqual(raw["bdns_call_access"], "named")
        self.assertEqual(
            APP["_bdns_pre_claude_gate"](raw)["reason_code"], "not_open_call"
        )

    def test_instrumental_award_mode_is_not_treated_as_a_consortium_route(self):
        raw = APP["_bdns_detail_to_raw"](
            {
                "codigoBDNS": 900008,
                "descripcion": "Financiación de Consorcio de infraestructuras",
                "fechaFinSolicitud": "2099-12-31",
                "tipoConvocatoria": "Concesión directa - instrumental",
                "tiposBeneficiarios": [{
                    "descripcion": "Personas jurídicas que no desarrollan actividad económica"
                }],
            },
            {"numeroConvocatoria": 900008},
        )
        self.assertEqual(raw["bdns_call_access"], "instrumental")
        outcome = APP["deterministic_prefilter"](raw)
        self.assertEqual((outcome["decision"], outcome["reason_code"]), (
            "reject", "not_open_call"
        ))

    def test_closed_detail_can_be_loaded_only_for_diagnostic_replay(self):
        detail = {
            "codigoBDNS": 900007,
            "descripcion": "Ayuda industrial cerrada",
            "fechaFinSolicitud": "2020-01-01",
            "tiposBeneficiarios": [{"descripcion": "Empresas"}],
        }
        self.assertIsNone(APP["_bdns_detail_to_raw"](
            detail, {"numeroConvocatoria": 900007}
        ))
        raw = APP["_bdns_detail_to_raw"](
            detail, {"numeroConvocatoria": 900007}, include_closed=True
        )
        self.assertEqual(raw["bdns_active_status"], "closed")
        self.assertEqual(
            APP["deterministic_prefilter"](raw)["reason_code"], "deadline_closed"
        )

    def test_eccp_powerup_regression_is_cascade_and_not_rejected(self):
        html = """
        <html><main><h1>PowerUp NetZero Open Call for Innovation Projects</h1>
        <p>Cascade funding for SMEs developing net-zero, hydrogen and industrial
        demonstration projects. Deadline: 15 September 2026.</p>
        <p>Total available budget: EUR 1,615,000.</p>
        <a href="https://example.test/powerup/apply">Apply for financial support</a>
        </main><footer><a href="https://social.example.test">Social</a></footer></html>
        """
        raw = APP["_eccp_call_from_html"](
            "https://www.clustercollaboration.eu/content/powerup-netzero-open-call-innovation-projects",
            html,
        )
        self.assertIsNotNone(raw)
        self.assertEqual(raw["deadline_date"], "2026-09-15")
        self.assertEqual(raw["funding_mechanism"], "cascade")
        self.assertEqual(raw["budget"], "EUR 1,615,000 total")
        self.assertEqual(
            raw["external_project_links"],
            ["https://example.test/powerup/apply"],
        )
        self.assertEqual(
            APP["_extract_funding_budget"](
                "The call has a total budget of €12.95 million."
            ),
            "€12.95 million total",
        )
        self.assertNotEqual(APP["deterministic_prefilter"](raw)["decision"], "reject")

    def test_eccp_inventory_parser_uses_current_accessible_pager_markup(self):
        html = """
        <html><body><div class="search-result-item">
          <a href="/content/open-call-one">Open call one</a>
        </div><nav class="pager"><a aria-label="Next page" rel="next"
          href="?type=eccp_calls&amp;page=1">Next</a></nav></body></html>
        """
        parsed = APP["_parse_eccp_inventory_html"](
            "https://www.clustercollaboration.eu/search-results?type=eccp_calls&page=0",
            html,
        )
        self.assertTrue(parsed["structure_ok"])
        self.assertEqual(parsed["detail_urls"], [
            "https://www.clustercollaboration.eu/content/open-call-one"
        ])
        self.assertEqual(
            parsed["next_url"],
            "https://www.clustercollaboration.eu/search-results?type=eccp_calls&page=1",
        )

    def test_een_partner_request_without_call_is_excluded(self):
        html = """<main><h1>Partner sought for heat exchanger distribution</h1>
        <p>A company seeks a commercial agreement and distributors.</p></main>"""
        self.assertIsNone(APP["_een_call_from_page"](
            "https://een.ec.europa.eu/partnering-opportunities/example", html, "profile"
        ))

    def test_een_historical_news_without_deadline_is_excluded(self):
        html = """<main><h1>The success of cascade funding</h1>
        <p>An EEN project provided financial support to SMEs in a past call.</p></main>"""
        self.assertIsNone(APP["_een_call_from_page"](
            "https://een.ec.europa.eu/news/historical-call", html, "news"
        ))

    def test_een_structured_call_separates_call_and_eoi_deadlines(self):
        html = """
        <main><h1>Research and Development Request</h1>
        <p>Call details</p>
        <p>Call title and identifier HORIZON-CL5-2026-01-D2-01 Industrial heat innovation
        Submission and evaluation scheme single stage</p>
        <p>Deadline for EoI 20 August 2026 Deadline of the call 30 September 2026
        Project duration 36 months</p>
        <p>Grant funding for industrial demonstration.</p>
        <a href="https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/HORIZON-CL5-2026-01-D2-01">Web link</a>
        </main>
        """
        raw = APP["_een_call_from_page"](
            "https://een.ec.europa.eu/partnering-opportunities/example", html, "profile"
        )
        self.assertIsNotNone(raw)
        self.assertEqual(raw["deadline_date"], "2026-09-30")
        self.assertEqual(raw["eoi_deadline_date"], "2026-08-20")
        self.assertEqual(raw["discovery_sources"], ["EEN"])

    def test_een_eurostars_call_number_becomes_strong_identity(self):
        self.assertEqual(
            APP["_official_call_identifier"]("Eurostars 3 Call 11"),
            "EUROSTARS-CALL-11",
        )

    def test_een_profiles_use_server_side_rd_request_filter(self):
        self.assertEqual(
            APP["_een_listing_params"]("profile", 4),
            {"page": 4, "f[0]": "p:4355"},
        )
        self.assertEqual(APP["_een_listing_params"]("news", 4), {"page": 4})

    def test_een_structured_profile_without_official_call_link_is_excluded(self):
        html = """
        <main><h1>Research and Development Request</h1>
        <p>Call details</p>
        <p>Call title and identifier HORIZON-CL5-2026-01-D2-01 Industrial heat
        Submission and evaluation scheme single stage</p>
        <p>Deadline of the call 30 September 2026 Project duration 36 months</p>
        <p>Grant funding for industrial demonstration.</p>
        <a href="https://example.test/company">Company website</a>
        </main>
        """
        self.assertIsNone(APP["_een_call_from_page"](
            "https://een.ec.europa.eu/partnering-opportunities/example", html, "profile"
        ))

    def test_een_generic_programme_homepage_does_not_verify_a_call(self):
        html = """
        <main><h1>Research and Development Request</h1>
        <p>Call details</p><p>Call title and identifier Eurostars 3
        Submission and evaluation scheme central evaluation</p>
        <p>Deadline of the call 10 September 2026 Project duration 36 months</p>
        <p>Grant funding for innovative SMEs.</p>
        <a href="https://www.eurekanetwork.org/programmes-and-calls/eurostars/">Web link to the call</a>
        </main>
        """
        self.assertIsNone(APP["_een_call_from_page"](
            "https://een.ec.europa.eu/partnering-opportunities/example", html, "profile"
        ))

    def test_stable_cached_documents_restore_only_strong_official_evidence(self):
        current = {
            "source": "IDAE",
            "bdns_id": "123456",
            "identifier": "TEST",
            "discovery_sources": ["IDAE"],
            "related_document_contents": [],
        }
        cached_raw = {
            "source": "IDAE",
            "bdns_id": "123456",
            "identifier": "TEST",
            "related_document_contents": [
                {
                    "source": "BOE / MITECO",
                    "title": "Extracto oficial",
                    "url": "https://boe.es/example",
                    "document_role": "call_extract",
                    "description": "Texto oficial estable.",
                },
                {
                    "source": "IDAE",
                    "title": "Landing mutable",
                    "url": "https://idae.es/example",
                    "document_role": "program_landing",
                    "description": "Contenido mutable.",
                },
            ],
        }
        diagnostics = APP["_hydrate_stable_cached_documents"](
            [current], {"cache-key": {"raw_document": cached_raw}}
        )
        self.assertEqual(diagnostics["documents_restored"], 1)
        self.assertEqual(len(current["related_document_contents"]), 1)
        self.assertEqual(current["related_document_contents"][0]["document_role"], "call_extract")
        self.assertIn("BOE / MITECO", current["discovery_sources"])

    def test_cdti_abbreviated_application_period_is_parsed(self):
        self.assertEqual(
            APP["_parse_cdti_application_period"](
                "Del 17 de junio al 16 de julio de 2026, a las 12:00 horas.",
                2026,
            ),
            ("2026-06-17", "2026-07-16"),
        )
        self.assertEqual(
            APP["_parse_cdti_application_period"](
                "Del 6 al 17 de julio de 2026.", 2026,
            ),
            ("2026-07-06", "2026-07-17"),
        )

    def test_cdti_visits_every_calendar_call_before_filtering(self):
        fixture_dir = ROOT / "tests" / "fixtures"
        calendar_html = (fixture_dir / "cdti_calendar_sample.html").read_text(
            encoding="utf-8"
        )
        active_html = (fixture_dir / "cdti_detail_active_sample.html").read_text(
            encoding="utf-8"
        )
        stale_html = (fixture_dir / "cdti_detail_stale_open_sample.html").read_text(
            encoding="utf-8"
        )
        calendar_url = "https://www.cdti.es/calendario-de-convocatorias"
        pages = {
            calendar_url: calendar_html,
            "https://www.cdti.es/ayudas/ayudas-neotec-2099": active_html,
            "https://www.cdti.es/ayudas/premios-navales-2099": active_html.replace(
                "Ayuda de prueba", "Premios tecnología plataformas navales"
            ),
            "https://www.cdti.es/ayudas/sera-antigua": stale_html,
        }

        class FakeBrowser:
            def __init__(self):
                self.visited = []

            def html(self, url, *args, **kwargs):
                self.visited.append(url)
                return pages.get(url, "")

        browser = FakeBrowser()
        parsed_calls, calendar_meta = APP["_parse_cdti_calendar_html"](
            calendar_html
        )
        self.assertEqual(len(parsed_calls), 3)
        self.assertEqual(calendar_meta["source_version"], "2099-08-07")
        globals_dict = APP["_fetch_cdti_playwright"].__globals__
        with mock.patch.dict(globals_dict, {
            "enrich_with_official_documents": lambda call, *_args, **_kwargs: call,
        }):
            results = APP["_fetch_cdti_playwright"](browser)
        diagnostics = APP["RUN_DIAGNOSTICS"]["cdti_scrape_audit"]
        self.assertEqual(browser.visited, [calendar_url, *list(pages)[1:]])
        self.assertEqual(diagnostics["calendar_calls"], 3)
        self.assertEqual(diagnostics["detail_attempted"], 3)
        self.assertEqual(diagnostics["detail_loaded"], 3)
        self.assertEqual(diagnostics["closed"], 1)
        self.assertEqual(diagnostics["status_conflicts"], 1)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["budget"], "30.250.000 euros total · Subvención")
        self.assertEqual(results[0]["related_documents_count"], 2)
        self.assertTrue(any(item["title"] == "Ayuda de prueba" for item in results))
        self.assertTrue(any("Premios" in item["title"] for item in results))

    def test_source_documents_are_selective_and_reused_from_separate_cache(self):
        response = SimpleNamespace(
            content=(
                b"<html><main>Official regulatory bases for industrial research "
                + b"and eligible companies. " * 12
                + b"</main></html>"
            ),
            headers={"content-type": "text/html"},
            encoding="utf-8",
            url="https://www.cdti.es/docs/orden_de_bases.pdf",
        )
        candidates = [
            {
                "source": "CDTI",
                "title": "Orden CNU/161/2024",
                "url": "https://www.cdti.es/docs/orden_de_bases.pdf",
            },
            {
                "source": "CDTI",
                "title": "Guía visual",
                "url": "https://www.cdti.es/docs/guia.pdf",
                "document_role": "source_record",
            },
        ]
        self.assertEqual(APP["_document_role"](candidates[0]), "regulatory_bases")
        with tempfile.TemporaryDirectory() as temporary:
            cache_path = str(Path(temporary) / "source_documents.json")
            http_get = mock.Mock(return_value=response)
            globals_dict = APP["enrich_with_official_documents"].__globals__
            with mock.patch.dict(globals_dict, {
                "SOURCE_DOCUMENT_CACHE_FILE": cache_path,
                "_SOURCE_DOCUMENT_CACHE_STATE": {"path": "", "entries": {}},
                "_http_get": http_get,
            }):
                first = APP["enrich_with_official_documents"](
                    {"title": "Ayuda CDTI", "related_document_contents": []},
                    candidates,
                    "CDTI",
                )
                second = APP["enrich_with_official_documents"](
                    {"title": "Ayuda CDTI", "related_document_contents": []},
                    candidates,
                    "CDTI",
                )
                cache_created = Path(cache_path).exists()
        self.assertEqual(http_get.call_count, 1)
        self.assertEqual(len(first["related_document_contents"]), 1)
        self.assertEqual(len(second["related_document_contents"]), 1)
        self.assertTrue(cache_created)

    def test_idae_inventory_and_split_sentence_deadline_are_general(self):
        html = """
        <a href="/ayudas-y-financiacion/programa-industrial">Programa industrial</a>
        <a href="/ayudas-y-financiacion/programa-industrial">Duplicado</a>
        <a href="/ayudas-y-financiacion/convocatorias-cerradas/antigua">Antigua</a>
        <a href="/noticias/otra">Noticia</a>
        """
        inventory = APP["_parse_idae_inventory_html"](
            "https://www.idae.es/ayudas-y-financiacion", html,
        )
        self.assertEqual(len(inventory), 2)
        self.assertFalse(inventory[0]["explicitly_closed"])
        self.assertTrue(inventory[1]["explicitly_closed"])
        self.assertEqual(
            APP["_extract_application_dates"](
                "El plazo para presentar solicitudes comenzará tras el BOE. "
                "Finalizará a las 14:00 h del 15 de julio de 2025."
            ),
            ("", "2025-07-15"),
        )

    def test_cdti_does_not_repeat_the_transversal_bdns_collection(self):
        globals_dict = APP["fetch_cdti"].__globals__
        with mock.patch.dict(globals_dict, {
            "_legacy_bdns_cdti_session_scraper": mock.Mock(
                side_effect=AssertionError("BDNS must be collected only by fetch_bdns")
            ),
            "_fetch_cdti_playwright": mock.Mock(return_value=[]),
            "_fetch_cdti_static": mock.Mock(return_value=[]),
        }):
            self.assertEqual(APP["fetch_cdti"](object()), [])

    def test_common_web_health_distinguishes_degraded_from_unhealthy(self):
        healthy = APP["assess_web_inventory_health"](
            "TEST HEALTHY",
            inventory_loaded=True,
            structure_ok=True,
            discovered_count=14,
            detail_attempted=14,
            detail_loaded=14,
            dated_count=14,
            expected_min_inventory=10,
            expected_date_coverage=0.8,
            source_version="2099-08-07",
            max_version_age_days=62,
        )
        degraded = APP["assess_web_inventory_health"](
            "TEST DEGRADED",
            inventory_loaded=True,
            structure_ok=True,
            discovered_count=10,
            detail_attempted=10,
            detail_loaded=8,
            dated_count=10,
            expected_min_inventory=10,
        )
        unhealthy = APP["assess_web_inventory_health"](
            "TEST UNHEALTHY",
            inventory_loaded=False,
            structure_ok=False,
            discovered_count=0,
            expected_min_inventory=1,
        )
        self.assertEqual(healthy["status"], "healthy")
        self.assertEqual(degraded["status"], "degraded")
        self.assertEqual(unhealthy["status"], "unhealthy")

    def test_fetch_bdns_includes_aragon_administration_without_a_keyword_match(self):
        national_keyword_row = {
            "numeroConvocatoria": "900101",
            "descripcion": "Ayudas a la digitalización industrial de pymes",
            "nivel1": "ESTADO", "nivel2": "MINISTERIO DE INDUSTRIA",
        }
        aragon_no_keyword_row = {
            "numeroConvocatoria": "900102",
            "descripcion": "Convenio de colaboración institucional ordinario",
            "nivel1": "AUTONOMICA", "nivel2": "ARAGÓN",
        }
        irrelevant_row = {
            "numeroConvocatoria": "900103",
            "descripcion": "Becas de comedor escolar para familias numerosas",
            "nivel1": "LOCAL", "nivel2": "AYUNTAMIENTO DE VIGO",
        }
        listing_rows = [national_keyword_row, aragon_no_keyword_row, irrelevant_row]
        detail_by_id = {
            "900101": {"descripcion": national_keyword_row["descripcion"], "codigoBDNS": "900101"},
            "900102": {"descripcion": aragon_no_keyword_row["descripcion"], "codigoBDNS": "900102"},
        }

        def fake_http_get(url, params=None, **kwargs):
            response = mock.Mock()
            endpoint = url.rsplit("/", 1)[-1]
            if endpoint == "ultimas":
                response.json.return_value = {"content": listing_rows, "last": True}
            elif endpoint == "busqueda":
                response.json.return_value = {"content": [], "last": True}
            elif endpoint == "convocatorias":
                num_conv = str((params or {}).get("numConv", ""))
                response.json.return_value = detail_by_id.get(num_conv, {})
            else:
                raise AssertionError(f"Unexpected BDNS endpoint: {url}")
            return response

        globals_dict = APP["fetch_bdns"].__globals__
        with mock.patch.dict(globals_dict, {"_http_get": mock.Mock(side_effect=fake_http_get)}):
            results = APP["fetch_bdns"]()

        self.assertEqual(sorted(r["bdns_id"] for r in results), ["900101", "900102"])
        metadata = APP["SOURCE_RUNTIME_METADATA"]["BDNS"]
        self.assertEqual(metadata["prefilter_candidates"], 2)
        self.assertEqual(metadata["aragon_admin_candidates"], 1)

    def test_bdns_latest_window_covers_at_least_sixty_days(self):
        # Punto 22 del backlog. La densidad de 44 filas/día que fijaba esta
        # prueba se midió el 17-18/08/2026 y quedó vieja enseguida: el 20/08
        # eran 54 y el 31/08, 52,2 (3.500 filas cubriendo 67 días, medido
        # contra la API). Con 44 la prueba daba 79 días de cobertura y no
        # habría detectado una caída por debajo del mínimo de negocio.
        #
        # Se fija la densidad MÁS ALTA observada, no la media ni la última:
        # lo que estrecha la ventana es que se publique más, así que el caso
        # que hay que resistir es el de más volumen (AGENTS.md 40.4).
        observed_daily_volume = 54
        minimum_required_days = 60
        covered_days = (
            APP["BDNS_LATEST_MAX_PAGES"] * APP["BDNS_PAGE_SIZE"] / observed_daily_volume
        )
        self.assertGreaterEqual(covered_days, minimum_required_days)


class IdentityAndFilterTests(unittest.TestCase):
    def structured_bdns_raw(self, **overrides):
        base = {
            "source": "BDNS",
            "title": "Ayuda industrial",
            "description": "Subvención a empresas manufactureras.",
            "org": "Administración del Estado",
            "bdns_filter_ready": True,
            "bdns_active_status": "confirmed_deadline",
            "bdns_call_access": "open_or_unknown",
            "bdns_company_eligible": True,
            "bdns_beneficiary_types": ["Empresas"],
            "bdns_admin_type": "ESTADO",
            "bdns_regions": ["España"],
            "bdns_nace_sections": ["C"],
            "bdns_territorial_requirement": "unknown",
            "bdns_project_execution_days": None,
            "bdns_finality": "Industria y Energía",
            "bdns_objectives": "",
        }
        base.update(overrides)
        return base

    def test_structured_scope_rejects_primary_but_defers_formal_route(self):
        primary = self.structured_bdns_raw(
            title="Ayudas a inversiones a bordo de buques pesqueros 2027",
            bdns_finality="Agricultura, Pesca y Alimentación",
            bdns_nace_sections=[],
        )
        candidate = APP["_bdns_structured_scope_exclusion"](primary)
        self.assertEqual(candidate["reason_code"], "structured_primary_sector_scope")
        production = APP["deterministic_prefilter"](dict(primary))
        self.assertEqual(production["reason_code"], "structured_primary_sector_scope")
        consortium = dict(primary)
        consortium["title"] = "Ayudas a grupos operativos de innovación agraria 2027"
        self.assertIsNone(APP["_bdns_structured_scope_exclusion"](consortium))
        consortium_outcome = APP["deterministic_prefilter"](consortium)
        self.assertNotEqual(
            consortium_outcome["reason_code"], "structured_primary_sector_scope"
        )

    def test_structured_scope_preserves_energy_waste_and_own_investment(self):
        for title, finality in (
            ("INNOVAE ahorro energético industrial", "Industria y Energía"),
            ("PAIP mejora de procesos y maquinaria", "Industria y Energía"),
            ("Valorización industrial de residuos", "Otras actuaciones de carácter económico"),
            ("(TEC) Economía circular y transición energética", "Fomento del Empleo"),
            ("Plan para adquirir suelo industrial en Zaragoza", "Fomento del Empleo"),
        ):
            with self.subTest(title=title):
                conv = self.structured_bdns_raw(
                    title=title, description=title, bdns_finality=finality,
                )
                self.assertIsNone(APP["_bdns_structured_scope_exclusion"](conv))

    def test_historical_rule_ignores_old_legal_reference_without_annuality_marker(self):
        conv = self.structured_bdns_raw(
            title="Convocatoria de innovación basada en la Ley 14/2011",
            bdns_active_status="unverified_recent",
        )
        self.assertIsNone(APP["_bdns_structured_scope_exclusion"](conv))

    def test_structured_scope_detects_public_and_historical_calls(self):
        public = self.structured_bdns_raw(
            title="Subvenciones destinadas a los entes locales para redes de agua",
        )
        historical = self.structured_bdns_raw(
            title="Programa de digitalización industrial 2025",
            bdns_active_status="unverified_recent",
        )
        self.assertEqual(
            APP["_bdns_structured_scope_exclusion"](public)["reason_code"],
            "structured_public_beneficiaries_only",
        )
        public_consortium = dict(public)
        public_consortium["title"] += " mediante proyectos en cooperación"
        self.assertIsNone(APP["_bdns_structured_scope_exclusion"](public_consortium))
        self.assertEqual(
            APP["_bdns_structured_scope_exclusion"](historical)["reason_code"],
            "historical_call_year_unverified",
        )

    def test_residual_bdns_wording_variants_are_rejected(self):
        cases = (
            "Campaña municipal de bonos de comercio 2026",
            "Convocatoria Pyme Global 2026 para participación en feria",
            "Ayudas para la conciliación de la vida personal, familiar y laboral",
            "Ayudas para el fomento de la actividad cultural en áreas rurales",
            "Convocatoria de subvenciones a entidades locales destinadas a residuos",
        )
        for title in cases:
            with self.subTest(title=title):
                outcome = APP["deterministic_prefilter"](
                    self.structured_bdns_raw(title=title, description=title)
                )
                self.assertEqual(outcome["decision"], "reject")

    def test_common_scope_rejects_education_health_without_technical_connection(self):
        unrelated = {
            "source": "EEN",
            "title": "Digital tools outside school, educational outcomes and mental health",
            "description": "Open call for research and innovation projects.",
            "org": "European Commission",
            "catalog_category": "",
        }
        outcome = APP["deterministic_prefilter"](unrelated)
        self.assertEqual(outcome["decision"], "reject")
        self.assertIn("salud mental", outcome["reason"].casefold())
        industrial = dict(unrelated)
        industrial["title"] = "School pilot for industrial waste heat recovery"
        industrial["description"] = "Waste heat recovery in an industrial process."
        self.assertNotEqual(
            APP["deterministic_prefilter"](industrial)["decision"], "reject"
        )

    def test_common_scope_fixture_preserves_only_explicit_thermal_overrides(self):
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "common_scope_filter_cases.json")
            .read_text(encoding="utf-8")
        )
        case_ids = [case["id"] for case in fixture["cases"]]
        self.assertEqual(fixture["spec_version"], 1)
        self.assertEqual(len(case_ids), len(set(case_ids)))
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                outcome = APP["deterministic_prefilter"]({
                    "source": "HORIZON EUROPE",
                    "title": case["title"],
                    "description": case["description"],
                    "org": "European Commission",
                    "deadline_days": 120,
                    "deadline_date": "2099-12-31",
                })
                self.assertEqual(
                    outcome["decision"] == "reject",
                    case["expected_reject"],
                    msg=outcome,
                )

    def test_eccp_eligibility_fixture_uses_mandatory_constraints_not_titles(self):
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "eccp_eligibility_filter_cases.json")
            .read_text(encoding="utf-8")
        )
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                outcome = APP["deterministic_prefilter"]({
                    "source": "ECCP",
                    "title": case["title"],
                    "description": case["description"],
                    "deadline_days": 120,
                    "deadline_date": "2099-12-31",
                })
                decision = outcome["decision"]
                if decision != "reject":
                    decision = "not_reject"
                self.assertEqual(decision, case["expected_decision"])

    def test_bdns_residual_fixture_requires_complete_scope_evidence(self):
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "bdns_residual_scope_cases.json")
            .read_text(encoding="utf-8")
        )
        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                conv = {
                    "source": "BDNS",
                    "title": case["title"],
                    "description": case["description"],
                    "org": "Administración local",
                    "bdns_filter_ready": True,
                    "bdns_active_status": "confirmed_deadline",
                    "bdns_call_access": "open_or_unknown",
                    "bdns_company_eligible": case.get("company_eligible", True),
                    "bdns_beneficiary_types": case.get(
                        "beneficiary_types", ["Empresas"]
                    ),
                    "bdns_admin_type": case.get("admin_type", "LOCAL"),
                    "bdns_regions": [case.get("region", "ES612 - Cádiz")],
                    "bdns_nace_sections": ["C"],
                    "bdns_territorial_requirement": "unknown",
                    "bdns_project_execution_days": case.get("execution_days"),
                    "deadline_date": "2099-12-31",
                    "deadline_days": 100,
                }
                if case["stage"] == "document":
                    result = APP["_bdns_intrinsic_exclusion"](
                        conv, case.get("evidence", "")
                    )
                    decision = result["decision"] if result else "not_reject"
                else:
                    decision = APP["deterministic_prefilter"](conv)["decision"]
                    if case["expected"] == "not_reject" and decision != "reject":
                        decision = "not_reject"
                self.assertEqual(decision, case["expected"])

    def test_no_claude_inventory_records_inclusion_and_cache_state(self):
        cached_conv = {
            "source": "HORIZON EUROPE", "identifier": "CALL-1",
            "title": "Industrial heat", "description": "Waste heat",
            "url": "https://example.test/call-1", "deterministic_prefilter": {
                "decision": "retain", "reason_code": "generic_prefilter",
                "reason": "Conexión industrial", "signals": {"tech_tags": ["waste_heat"]},
            },
        }
        changed = dict(cached_conv)
        changed["description"] = "Waste heat with updated eligibility"
        new_conv = {
            "source": "ECCP", "identifier": "CALL-2", "title": "New call",
            "description": "Industrial process innovation",
            "url": "https://example.test/call-2", "deterministic_prefilter": {
                "decision": "ambiguous", "reason_code": "generic_prefilter",
                "reason": "Evidencia insuficiente", "signals": {},
            },
        }
        cache = {
            APP["cache_key"](cached_conv): {
                "raw_document": cached_conv, "analysis": {},
            },
        }
        inventory = APP["build_no_claude_candidate_inventory"](
            [cached_conv, changed, new_conv], cache
        )
        self.assertEqual(inventory["count"], 3)
        self.assertEqual(
            inventory["cache_status_counts"],
            {"hit": 1, "content_changed": 1, "new": 1},
        )
        self.assertEqual(len(inventory["items"]), 3)
        self.assertTrue(all(item["inclusion"]["reason_code"] for item in inventory["items"]))
        self.assertTrue(all(item["cache"]["source_hash"] for item in inventory["items"]))

    def test_application_landing_clock_does_not_invalidate_factual_cache(self):
        def call(clock, deadline="15 de octubre de 2026"):
            return {
                "source": "BDNS", "bdns_id": "123", "title": "Ayuda industrial",
                "description": "Inversión productiva", "url": "https://example.test",
                "deadline_date": "2026-10-15", "open_date": "2026-08-01",
                "related_document_contents": [{
                    "title": "Sede", "url": "https://sede.example.test",
                    "document_role": "application_landing",
                    "description": (
                        f"SEDE ELECTRÓNICA Menú {clock} Catálogo de trámites. "
                        f"El plazo termina el {deadline}."
                    ),
                }],
            }

        first = call("13 de agosto 2026, 07:40:33")
        second = call("14 de agosto 2026, 11:07:57")
        changed_deadline = call(
            "14 de agosto 2026, 11:07:57", "16 de octubre de 2026"
        )
        self.assertEqual(APP["source_hash"](first), APP["source_hash"](second))
        self.assertNotEqual(
            APP["source_hash"](second), APP["source_hash"](changed_deadline)
        )

        reindexed = APP["_reindex_cache_entries"]({
            "old-a": {"raw_document": first, "cached_at": "2026-08-13T08:00:00"},
            "old-b": {"raw_document": second, "cached_at": "2026-08-14T12:00:00"},
        })
        self.assertEqual(list(reindexed), [APP["cache_key"](second)])
        self.assertEqual(
            reindexed[APP["cache_key"](second)]["cached_at"],
            "2026-08-14T12:00:00",
        )

    # La persistencia del inventario de candidatas se prueba ahora en
    # tests/test_grant_radar_audit.py, con import estándar: save_discovery_audit()
    # vive en grant_radar/audit.py desde el 31/08/2026 y recibe la ruta como
    # parámetro, así que ya no hace falta inyectar AUDIT_FILE en __globals__.

    def test_claude_safety_preflight_enforces_candidate_and_cost_limits(self):
        # 106/107 desde la recalibración del 20/08/2026 (antes 142/143, con un
        # coste unitario que salía de una muestra de dos convocatorias).
        within_budget = APP["claude_safety_preflight"](106)
        self.assertTrue(within_budget["allowed"])
        self.assertEqual(within_budget["effective_max_analyses"], 106)
        self.assertLessEqual(within_budget["estimated_upper_cost_usd"], 5.0)

        over_cost = APP["claude_safety_preflight"](107)
        self.assertFalse(over_cost["allowed"])
        self.assertEqual(over_cost["breaches"], ["estimated_cost_limit"])

        over_both = APP["claude_safety_preflight"](201)
        self.assertFalse(over_both["allowed"])
        self.assertEqual(
            over_both["breaches"],
            ["candidate_limit", "estimated_cost_limit"],
        )

    def bdns_case(self, **overrides):
        base = {
            "source": "BDNS",
            "title": "Ayuda industrial",
            "description": "Subvención a empresas manufactureras.",
            "org": "Administración del Estado",
            "bdns_filter_ready": True,
            "bdns_active_status": "confirmed_deadline",
            "bdns_call_access": "open_or_unknown",
            "bdns_company_eligible": True,
            "bdns_beneficiary_types": ["Empresas"],
            "bdns_admin_type": "ESTADO",
            "bdns_regions": ["España"],
            "bdns_nace_sections": ["C"],
            "bdns_territorial_requirement": "unknown",
            "bdns_project_execution_days": None,
        }
        base.update(overrides)
        return APP["deterministic_prefilter"](base)

    def test_bdns_unverified_records_do_not_reach_claude(self):
        self.assertEqual(
            self.bdns_case(bdns_active_status="unverified_recent")["decision"],
            "hold_manual",
        )
        old = self.bdns_case(bdns_active_status="unverified_old")
        self.assertEqual((old["decision"], old["reason_code"]), ("reject", "no_active_evidence"))

    def test_definitive_scope_and_access_exclusions_precede_unknown_vigency(self):
        named = self.bdns_case(
            bdns_active_status="unverified_recent", bdns_call_access="named"
        )
        residential = self.bdns_case(
            title="Plan de mejora energética de las viviendas del municipio",
            bdns_active_status="unverified_recent",
        )
        academic = self.bdns_case(
            title="Ayudas para trabajos de fin de máster en energías renovables",
            bdns_active_status="unverified_recent",
        )
        self.assertEqual(named["reason_code"], "not_open_call")
        self.assertEqual(residential["reason_code"], "explicit_non_industrial_scope")
        self.assertEqual(academic["reason_code"], "explicit_non_industrial_scope")

    def test_bdns_cluster_consortium_and_indirect_commercial_roles(self):
        cluster = self.bdns_case(
            description="Ayuda a clústeres para pilotos en empresas miembro.",
            bdns_company_eligible=False,
            bdns_beneficiary_types=["Agrupaciones empresariales innovadoras"],
        )
        self.assertEqual(cluster["opportunity_role"], "cluster_route")
        self.assertEqual(cluster["opportunity_labels"], ["Vía clúster"])
        operating = self.bdns_case(
            description="Gastos de funcionamiento y personal del clúster.",
            bdns_company_eligible=False,
            bdns_beneficiary_types=["Clústeres"],
        )
        self.assertEqual(operating["reason_code"], "reject_cluster_operations")
        indirect_commercial = self.bdns_case(
            description="Ayuda a entidades públicas para equipos industriales de depuración de gases.",
            bdns_company_eligible=False,
            bdns_beneficiary_types=["Entidades públicas"],
        )
        self.assertEqual(indirect_commercial["decision"], "reject")
        self.assertEqual(
            indirect_commercial["reason_code"], "indirect_commercial_role_only"
        )
        consortium = self.bdns_case(
            description=(
                "Proyecto en cooperación: cada miembro del consorcio tendrá "
                "presupuesto y costes elegibles propios."
            ),
            bdns_company_eligible=False,
            bdns_beneficiary_types=["Consorcios"],
        )
        self.assertEqual(
            (consortium["decision"], consortium["opportunity_role"]),
            ("retain", "consortium_partner"),
        )
        self.assertEqual(consortium["opportunity_labels"], ["Socio de consorcio"])

    def test_bdns_new_centre_boundary_is_730_days(self):
        common = {
            "bdns_admin_type": "AUTONÓMICA",
            "bdns_regions": ["Comunidad Valenciana"],
            "bdns_territorial_requirement": "new_establishment_allowed",
        }
        self.assertEqual(
            self.bdns_case(**common, bdns_project_execution_days=729)["decision"],
            "reject",
        )
        boundary = self.bdns_case(**common, bdns_project_execution_days=730)
        self.assertEqual(boundary["decision"], "retain")
        self.assertEqual(boundary["opportunity_labels"], ["Requiere nuevo centro"])
        self.assertEqual(
            self.bdns_case(**common, bdns_project_execution_days=None)["decision"],
            "hold_manual",
        )

    def test_bdns_other_administration_with_specific_region_is_not_treated_as_national(self):
        outcome = self.bdns_case(
            bdns_admin_type="OTROS",
            bdns_regions=["ES613 - Córdoba"],
            bdns_territorial_requirement="unknown",
        )
        self.assertEqual(outcome["decision"], "hold_manual")
        self.assertEqual(outcome["reason_code"], "territorial_eligibility_unverified")

    def test_bdns_indirect_commercial_role_is_rejected_even_with_eligible_equipment(self):
        outcome = self.bdns_case(
            description="Equipos industriales para depuración de gases como gasto elegible.",
            bdns_admin_type="LOCAL",
            bdns_regions=["ES211 - Araba/Álava"],
            bdns_company_eligible=False,
            bdns_beneficiary_types=["Entidades sin ánimo de lucro"],
            bdns_nace_sections=["E"],
        )
        self.assertEqual((outcome["decision"], outcome["opportunity_role"]), ("reject", "unknown"))
        self.assertEqual(outcome["reason_code"], "indirect_commercial_role_only")

    def test_bdns_own_productive_investment_does_not_require_rd(self):
        paip = self.bdns_case(
            title="PAIP para inversiones productivas",
            description=(
                "Ayuda a empresas manufactureras para adquisición de maquinaria "
                "y mejora de procesos productivos propios."
            ),
        )
        self.assertEqual(paip["decision"], "retain")
        self.assertEqual(paip["opportunity_role"], "direct_beneficiary")
        self.assertEqual(paip["reason_code"], "own_investment_connection_confirmed")
        innovae = self.bdns_case(
            title="Programa INNOVAE",
            description=(
                "Inversiones propias de empresas para ahorro energético y mejora "
                "de procesos, sin exigir un proyecto de I+D."
            ),
            bdns_nace_sections=["C", "D"],
        )
        self.assertEqual(innovae["decision"], "retain")
        self.assertEqual(innovae["opportunity_role"], "direct_beneficiary")

    def test_bdns_sector_matrix_keeps_energy_waste_and_technical_tertiary(self):
        self.assertEqual(self.bdns_case(bdns_nace_sections=["B"])["decision"], "reject")
        self.assertEqual(self.bdns_case(bdns_nace_sections=["A"])["decision"], "reject")
        self.assertEqual(
            self.bdns_case(
                bdns_nace_sections=["B"],
                description="Ahorro energético para la línea industrial y procesos industriales.",
            )["decision"],
            "retain",
        )
        for sections, description in (
            (["D"], "Ahorro energético para empresas."),
            (["E"], "Valorización de residuos y depuración de gases."),
            (["H", "T"], "Producción y demostración industrial de hidrógeno."),
        ):
            with self.subTest(sections=sections):
                self.assertEqual(
                    self.bdns_case(bdns_nace_sections=sections, description=description)["decision"],
                    "retain",
                )

    def test_bdns_commercial_residential_and_training_scopes_are_rejected(self):
        for description in (
            "Programa Pyme Global para visita a la feria internacional.",
            "Eficiencia energética en edificios residenciales.",
            "Acciones formativas para personas empleadas.",
            "Plan Wave Plus para personas trabajadoras prioritariamente ocupadas.",
            "Premios a la excelencia empresarial.",
            "Subvención para el fomento al empleo.",
            "Ayuda a empresas de economía social.",
            "Ayuda al régimen especial de trabajadores por cuenta propia.",
        ):
            with self.subTest(description=description):
                outcome = self.bdns_case(description=description)
                self.assertEqual(outcome["reason_code"], "explicit_non_industrial_scope")

    def test_identifier_merges_sources_and_provenance(self):
        base = {
            "identifier": "HORIZON-CL5-2026-01-D2-01",
            "title": "Industrial heat innovation",
            "description": "Grant for industrial heat demonstration",
            "deadline_date": "2026-09-30",
            "deadline_days": 57,
            "url": "https://example.test/call",
        }
        merged = APP["_deduplicate_raw_convocations"]([
            {**base, "source": "ECCP", "discovery_sources": ["ECCP"]},
            {**base, "source": "HORIZON EUROPE", "discovery_sources": ["EEN"]},
        ])
        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0]["discovery_sources"]), {"ECCP", "EEN", "HORIZON EUROPE"})

    def test_ambiguous_records_are_retained_for_claude(self):
        result = APP["deterministic_prefilter"]({
            "title": "Convocatoria de innovación",
            "description": "Ayuda a empresas para proyectos piloto.",
        })
        self.assertIn(result["decision"], {"retain", "ambiguous"})

    def test_unverified_bdns_deadline_sentinel_is_never_public_or_open(self):
        conv = {
            "source": "BDNS",
            "bdns_active_status": "unverified_recent",
            "deadline_days": 1,
            "deadline_date": "",
            "fecha_sin_confirmar": True,
        }
        self.assertEqual(APP["_deterministic_call_status"](conv), "unknown")
        self.assertEqual(APP["_public_deadline_values"](conv), (None, "", True))

    def test_unknown_public_deadline_is_active_but_never_urgent(self):
        stats = APP["build_stats"]([{
            "deadline": None,
            "descartada": False,
            "priority": "medium",
            "review_required": False,
            "budget_raw": 0,
        }])
        self.assertEqual(stats["active"], 1)
        self.assertEqual(stats["urgent"], 0)

    def test_known_positive_json_has_full_prefilter_recall(self):
        import json
        payload = json.loads((ROOT / "convocatorias.json").read_text(encoding="utf-8"))
        positives = [item for item in payload["convocatorias"] if not item.get("descartada")]
        rejected = [
            item["title"] for item in positives
            if APP["deterministic_prefilter"](item)["decision"] == "reject"
        ]
        self.assertEqual(rejected, [])

    def test_eccp_depth_chooses_first_useful_level_before_request_doubling(self):
        metrics = [
            {"depth": 0, "critical_fields": 20, "requests": 0,
             "irrelevant": 0, "median_requests_per_call": 0, "unique_call_gain_pct": 0},
            {"depth": 1, "critical_fields": 25, "requests": 6,
             "irrelevant": 1, "median_requests_per_call": 1, "unique_call_gain_pct": 100},
            {"depth": 2, "critical_fields": 41, "requests": 22,
             "irrelevant": 1, "median_requests_per_call": 3, "unique_call_gain_pct": 320},
        ]
        self.assertEqual(APP["_choose_eccp_depth"](metrics), 1)


class BdnsHoldPilotTests(unittest.TestCase):
    def hold_pair(self, reason, index):
        return (
            {
                "source": "BDNS",
                "bdns_filter_ready": True,
                "bdns_id": str(800000 + index),
                "title": f"Ayuda industrial energética {index}",
                "description": "Convocatoria para eficiencia energética industrial.",
            },
            {"decision": "hold_manual", "reason_code": reason},
        )

    def test_pilot_selection_is_stratified_and_capped_at_twenty(self):
        holds = (
            [self.hold_pair("active_status_unverified", i) for i in range(30)]
            + [self.hold_pair("territorial_eligibility_unverified", 100 + i) for i in range(10)]
            + [self.hold_pair("consortium_role_unverified", 200 + i) for i in range(4)]
            + [self.hold_pair("cluster_role_unverified", 300)]
        )
        selected = APP["select_bdns_hold_pilot"](holds, 20)
        counts = {}
        for _, outcome in selected:
            reason = outcome["reason_code"]
            counts[reason] = counts.get(reason, 0) + 1
        self.assertEqual(len(selected), 20)
        self.assertEqual(counts, {
            "active_status_unverified": 12,
            "territorial_eligibility_unverified": 5,
            "consortium_role_unverified": 2,
            "cluster_role_unverified": 1,
        })

    def test_document_links_reject_local_or_insecure_urls(self):
        records = APP["_bdns_document_records"]({
            "documentos": [
                {"nombre": "Bases", "url": "https://administracion.example/bases.pdf"},
                {"nombre": "Inseguro", "url": "http://example.test/file.pdf"},
                {"nombre": "Local", "url": "https://127.0.0.1/private"},
            ]
        })
        self.assertEqual([item["title"] for item in records], ["Bases"])

    def test_html_document_text_is_extracted_without_scripts(self):
        class Response:
            content = b"<html><body><main><h1>Bases</h1><p>Plazo de solicitud hasta 30/09/2026.</p><script>ignore()</script></main></body></html>"
            headers = {"content-type": "text/html; charset=utf-8"}
            encoding = "utf-8"
            text = content.decode("utf-8")

        text, document_format = APP["_hold_document_text"](
            Response(), "https://example.test/bases"
        )
        self.assertEqual(document_format, "html")
        self.assertIn("30/09/2026", text)
        self.assertNotIn("ignore", text)

    def test_bounded_http_download_stops_before_oversized_body(self):
        class Response:
            status_code = 200
            headers = {"content-length": "11"}
            closed = False

            def raise_for_status(self):
                return None

            def close(self):
                self.closed = True

        response = Response()
        session = mock.Mock()
        session.get.return_value = response
        result = APP["_http_get"](
            "https://example.test/large.pdf",
            session=session,
            retries=1,
            max_bytes=10,
        )
        self.assertIsNone(result)
        self.assertTrue(response.closed)
        self.assertTrue(session.get.call_args.kwargs["stream"])

    def test_active_status_is_resolved_deterministically_from_evidence(self):
        evidence = {
            "documents": [{
                "url": "https://example.test/bases",
                "text": "El plazo de presentación de solicitudes finaliza el 30/09/2026.",
            }]
        }
        result = APP["resolve_hold_deterministically"](
            {}, "active_status_unverified", evidence,
            APP["_bdns_intrinsic_exclusion"],
        )
        self.assertEqual(result["decision"], "retain")
        self.assertEqual(result["facts"]["deadline_date"], "2026-09-30")

    def test_unscoped_date_does_not_resolve_active_status(self):
        evidence = {
            "documents": [{
                "url": "https://example.test/bases",
                "text": "El proyecto podrá ejecutarse hasta el 30/09/2026.",
            }]
        }
        result = APP["resolve_hold_deterministically"](
            {}, "active_status_unverified", evidence,
            APP["_bdns_intrinsic_exclusion"],
        )
        self.assertEqual(result["decision"], "unresolved")

    def test_intrinsic_scope_found_in_downloaded_bases_avoids_haiku(self):
        evidence = {
            "documents": [{
                "url": "https://example.test/bases",
                "text": "Las actuaciones se realizarán en viviendas del municipio.",
            }]
        }
        result = APP["resolve_hold_deterministically"](
            {"title": "Programa de ahorro energético"},
            "territorial_eligibility_unverified",
            evidence,
            APP["_bdns_intrinsic_exclusion"],
        )
        self.assertEqual(result["decision"], "reject")
        self.assertEqual(result["reason_code"], "explicit_non_industrial_scope")
        self.assertEqual(result["resolved_by"], "deterministic_evidence")

    def test_full_document_scope_precedes_the_claude_excerpt(self):
        full_scope = {
            "decision": "reject",
            "reason_code": "explicit_non_industrial_scope",
            "reason": "Objeto laboral inequívoco en las bases completas.",
        }
        evidence = {
            "documents": [{
                "url": "https://example.test/bases",
                "text": "Extracto limitado a presupuesto y beneficiarios.",
            }],
            "deterministic_scope_exclusion": full_scope,
        }
        result = APP["resolve_hold_deterministically"](
            {"title": "Ayuda para iniciativas de investigación"},
            "territorial_eligibility_unverified",
            evidence,
            APP["_bdns_intrinsic_exclusion"],
        )
        self.assertEqual((result["decision"], result["reason_code"]), (
            "reject", "explicit_non_industrial_scope"
        ))

    def test_incidental_terms_in_long_bases_do_not_reject_energy_aid(self):
        evidence = {"documents": [{
            "text": (
                "Ayuda para eficiencia energética industrial. No son elegibles "
                "los gastos de participación en feria ni ciertas empresas de economía social."
            )
        }]}
        result = APP["resolve_hold_deterministically"](
            {"title": "Eficiencia energética para empresas"},
            "territorial_eligibility_unverified",
            evidence,
            APP["_bdns_intrinsic_exclusion"],
        )
        self.assertEqual(result["decision"], "unresolved")

    def test_named_access_found_in_downloaded_bases_avoids_haiku(self):
        evidence = {
            "documents": [{
                "url": "https://example.test/convenio",
                "text": "Convenio a suscribir con la universidad beneficiaria.",
            }]
        }
        result = APP["resolve_hold_deterministically"](
            {"title": "Programa de innovación"},
            "active_status_unverified",
            evidence,
            APP["_bdns_intrinsic_exclusion"],
        )
        self.assertEqual((result["decision"], result["reason_code"]), (
            "reject", "not_open_call"
        ))

    def test_haiku_quote_must_exist_in_the_declared_document(self):
        facts = APP["BdnsHoldFacts"](
            call_status="unknown",
            deadline_date="",
            territorial_condition="existing_establishment",
            execution_days=-1,
            consortium_participation="unknown",
            cluster_support_to_members="unknown",
            evidence_quote="Debe disponer de centro de trabajo en la comunidad.",
            evidence_source_url="https://example.test/bases",
            confidence=90,
            explanation="Requisito territorial explícito.",
        )
        evidence = {"documents": [{
            "url": "https://example.test/bases",
            "text": "No consta ese texto en las bases.",
        }]}
        result = APP["_validated_hold_resolution"](
            {}, "territorial_eligibility_unverified", facts, evidence
        )
        self.assertEqual(result["decision"], "unresolved")
        self.assertEqual(result["reason_code"], "insufficient_verified_evidence")

    def test_quote_whitespace_and_pdf_punctuation_are_normalized(self):
        quote = "cuenten con establecimiento operativo en La Rioja"
        facts = APP["BdnsHoldFacts"](
            call_status="unknown", deadline_date="",
            territorial_condition="existing_establishment", execution_days=-1,
            consortium_participation="unknown", cluster_support_to_members="unknown",
            evidence_quote=quote, evidence_source_url="https://example.test/bases",
            confidence=95, explanation="Requisito territorial explícito.",
        )
        evidence = {"documents": [{
            "url": "https://example.test/bases",
            "text": "Las empresas deberán acreditar que cuenten con\n"
                    "establecimiento operativo en La Rioja.",
        }]}
        result = APP["_validated_hold_resolution"](
            {}, "territorial_eligibility_unverified", facts, evidence
        )
        self.assertEqual(result["decision"], "reject")

    def test_pdf_word_splits_do_not_invalidate_a_long_cluster_quote(self):
        quote = (
            "fomentar la acción colaborativa de las empresas de sectores estratégicos "
            "y su participación en proyectos para mejorar su competitividad a través "
            "de asociaciones tipo clúster"
        )
        pdf_text = (
            "fomentar la accion colaborativa de las empresas de sectores estra tegicos "
            "y su participacion en proyectos para mejorar su competitividad a traves "
            "de aso ciaciones tipo cluster"
        )
        facts = APP["BdnsHoldFacts"](
            call_status="unknown", deadline_date="", territorial_condition="unknown",
            execution_days=-1, consortium_participation="unknown",
            cluster_support_to_members="yes", evidence_quote=quote,
            evidence_source_url="https://example.test/cluster.pdf",
            confidence=90, explanation="Apoyo a proyectos empresariales.",
        )
        result = APP["_validated_hold_resolution"](
            {}, "cluster_role_unverified", facts,
            {"documents": [{"url": facts.evidence_source_url, "text": pdf_text}]},
        )
        self.assertEqual(result["decision"], "retain")

    def test_project_location_quote_cannot_prove_existing_establishment(self):
        quote = "Son subvencionables las actuaciones que se realicen en las Islas Baleares"
        facts = APP["BdnsHoldFacts"](
            call_status="unknown", deadline_date="",
            territorial_condition="existing_establishment", execution_days=-1,
            consortium_participation="unknown", cluster_support_to_members="unknown",
            evidence_quote=quote, evidence_source_url="https://example.test/bases",
            confidence=85, explanation="Clasificación propuesta por el modelo.",
        )
        result = APP["_validated_hold_resolution"](
            {}, "territorial_eligibility_unverified", facts,
            {"documents": [{"url": facts.evidence_source_url, "text": quote}]},
        )
        self.assertEqual(result["decision"], "unresolved")
        self.assertEqual(
            result["reason_code"], "territorial_condition_not_supported_by_quote"
        )

    def test_execution_period_quote_cannot_prove_call_is_closed(self):
        quote = "El plazo máximo de ejecución será de 30 meses desde la concesión."
        facts = APP["BdnsHoldFacts"](
            call_status="closed", deadline_date="",
            territorial_condition="unknown", execution_days=30,
            consortium_participation="unknown", cluster_support_to_members="unknown",
            evidence_quote=quote, evidence_source_url="https://example.test/bases",
            confidence=85, explanation="La ejecución se vincula a la concesión.",
        )
        result = APP["_validated_hold_resolution"](
            {}, "active_status_unverified", facts,
            {"documents": [{"url": facts.evidence_source_url, "text": quote}]},
        )
        self.assertEqual(result["decision"], "unresolved")
        self.assertEqual(result["reason_code"], "closed_status_not_verified")

    def test_negative_consortium_answer_never_causes_automatic_rejection(self):
        quote = "No consta información detallada sobre la participación en consorcio."
        facts = APP["BdnsHoldFacts"](
            call_status="unknown", deadline_date="",
            territorial_condition="unknown", execution_days=-1,
            consortium_participation="no", cluster_support_to_members="unknown",
            evidence_quote=quote, evidence_source_url="https://example.test/bases",
            confidence=90, explanation="No se acredita participación formal.",
        )
        result = APP["_validated_hold_resolution"](
            {}, "consortium_role_unverified", facts,
            {"documents": [{"url": facts.evidence_source_url, "text": quote}]},
        )
        self.assertEqual(result["decision"], "unresolved")

    def test_commercial_subcontractor_is_not_a_consortium_partner(self):
        quote = (
            "El consorcio podrá contratar proveedores externos y subcontratistas "
            "para el suministro de equipos."
        )
        facts = APP["BdnsHoldFacts"](
            call_status="unknown", deadline_date="",
            territorial_condition="unknown", execution_days=-1,
            consortium_participation="yes", cluster_support_to_members="unknown",
            evidence_quote=quote, evidence_source_url="https://example.test/bases",
            confidence=95, explanation="Solo se describe contratación comercial.",
        )
        result = APP["_validated_hold_resolution"](
            {}, "consortium_role_unverified", facts,
            {"documents": [{"url": facts.evidence_source_url, "text": quote}]},
        )
        self.assertEqual(result["decision"], "unresolved")

    def test_verified_consortium_participation_reenters_as_formal_partner(self):
        conv = {
            "source": "BDNS",
            "bdns_filter_ready": True,
            "title": "Proyecto industrial en consorcio",
            "description": "Convocatoria para consorcios de descarbonización.",
            "bdns_company_eligible": False,
            "bdns_beneficiary_types": ["Consorcios"],
            "bdns_active_status": "confirmed_deadline",
            "deadline_date": "2099-12-31",
            "deadline_days": 1000,
            "bdns_regions": ["España"],
            "bdns_admin_type": "ESTADO",
            "bdns_nace_sections": ["C"],
        }
        resolution = {
            "decision": "retain",
            "reason_code": "haiku_consortium_participation_confirmed",
            "facts": {"consortium_participation": "yes"},
        }
        updated, outcome = APP["apply_verified_bdns_hold_resolution"](
            conv, "consortium_role_unverified", resolution,
            APP["deterministic_prefilter"],
        )
        self.assertTrue(updated["bdns_verified_consortium_participation"])
        self.assertEqual(outcome["decision"], "retain")
        self.assertEqual(outcome["opportunity_role"], "consortium_partner")
        self.assertEqual(outcome["opportunity_labels"], ["Socio de consorcio"])

    def test_verified_new_centre_rule_uses_the_730_day_boundary(self):
        common = {
            "call_status": "unknown", "deadline_date": "",
            "territorial_condition": "new_establishment_allowed",
            "consortium_participation": "unknown",
            "cluster_support_to_members": "unknown",
            "evidence_source_url": "https://example.test/bases",
            "confidence": 90, "explanation": "Implantación posterior permitida.",
        }
        below_quote = (
            "Se permite establecer un centro tras la concesión; el plazo de ejecución será de 729 días."
        )
        boundary_quote = (
            "Se permite establecer un centro tras la concesión; el plazo de ejecución será de 730 días."
        )
        below = APP["BdnsHoldFacts"](
            **common, execution_days=729, evidence_quote=below_quote
        )
        boundary = APP["BdnsHoldFacts"](
            **common, execution_days=730, evidence_quote=boundary_quote
        )
        self.assertEqual(APP["_validated_hold_resolution"](
            {}, "territorial_eligibility_unverified", below,
            {"documents": [{"url": common["evidence_source_url"], "text": below_quote}]},
        )["decision"], "reject")
        self.assertEqual(APP["_validated_hold_resolution"](
            {}, "territorial_eligibility_unverified", boundary,
            {"documents": [{"url": common["evidence_source_url"], "text": boundary_quote}]},
        )["decision"], "retain")

    def test_hold_schema_has_no_optional_fields_or_unions(self):
        metrics = APP["validate_structured_output_schema"](APP["BdnsHoldFacts"])
        self.assertEqual(metrics["optional_fields"], 0)
        self.assertEqual(metrics["union_fields"], 0)

    def test_verified_active_resolution_reenters_the_full_gate(self):
        conv = {
            "source": "BDNS",
            "bdns_filter_ready": True,
            "title": "Ayudas a eficiencia energética industrial",
            "description": "Inversiones para ahorro energético en empresas.",
            "bdns_company_eligible": True,
            "bdns_active_status": "unverified_recent",
            "bdns_regions": ["Aragón"],
            "bdns_admin_type": "Comunidad Autónoma",
        }
        resolution = {
            "decision": "retain",
            "reason_code": "verified_future_deadline",
            "facts": {"call_status": "open", "deadline_date": "2099-09-30"},
        }
        updated, outcome = APP["apply_verified_bdns_hold_resolution"](
            conv, "active_status_unverified", resolution,
            APP["deterministic_prefilter"],
        )
        self.assertEqual(updated["deadline_date"], "2099-09-30")
        self.assertEqual(updated["bdns_active_status"], "confirmed_deadline")
        self.assertEqual(outcome["decision"], "retain")
        self.assertEqual(outcome["resolved_hold_reason"], "active_status_unverified")

    def test_verified_project_location_resolution_does_not_require_prior_centre(self):
        conv = {
            "source": "BDNS",
            "bdns_filter_ready": True,
            "title": "Ayudas a descarbonización industrial",
            "description": "Inversiones industriales para empresas.",
            "bdns_company_eligible": True,
            "bdns_active_status": "confirmed_deadline",
            "deadline_date": "2099-12-31",
            "deadline_days": 1000,
            "bdns_regions": ["La Rioja"],
            "bdns_admin_type": "Comunidad Autónoma",
            "bdns_territorial_requirement": "unknown",
        }
        resolution = {
            "decision": "retain",
            "reason_code": "verified_project_location_only",
            "facts": {
                "territorial_condition": "project_location_only",
                "execution_days": -1,
            },
        }
        updated, outcome = APP["apply_verified_bdns_hold_resolution"](
            conv, "territorial_eligibility_unverified", resolution,
            APP["deterministic_prefilter"],
        )
        self.assertEqual(
            updated["bdns_territorial_requirement"], "project_location_only"
        )
        self.assertEqual(outcome["decision"], "retain")
        self.assertEqual(
            outcome["reason_code"], "project_location_without_prior_establishment"
        )

    def test_unresolved_verified_hold_becomes_ambiguous_not_manual_or_reject(self):
        updated, outcome = APP["apply_verified_bdns_hold_resolution"](
            {"source": "BDNS", "bdns_id": "900100"},
            "consortium_role_unverified",
            {"decision": "unresolved", "reason_code": "insufficient_evidence"},
            APP["deterministic_prefilter"],
        )
        self.assertEqual(updated["bdns_id"], "900100")
        self.assertEqual(outcome["decision"], "ambiguous")
        self.assertEqual(outcome["reason_code"], "verified_hold_still_unresolved")

    def test_replay_prefers_current_document_rule_over_historical_answer(self):
        conv = {
            "source": "BDNS", "bdns_filter_ready": True,
            "title": "Ayuda de ahorro energético", "description": "Ayuda a empresas.",
            "bdns_company_eligible": True, "bdns_active_status": "unverified_recent",
            "bdns_call_access": "open_or_unknown", "bdns_beneficiary_types": ["Empresas"],
            "bdns_admin_type": "ESTADO", "bdns_regions": ["España"],
            "bdns_nace_sections": ["C"],
        }
        old = {
            "hold_reason": "active_status_unverified",
            "resolution": {"decision": "unresolved"},
        }
        evidence = {"documents": [{
            "text": "La actuación consiste en un programa de empleo y acciones formativas."
        }]}
        _, outcome, resolved_by = APP["replay_bdns_hold_item"](conv, old, evidence, APP["deterministic_prefilter"], APP["_bdns_intrinsic_exclusion"])
        self.assertEqual(outcome["decision"], "reject")
        self.assertEqual(outcome["reason_code"], "explicit_non_industrial_scope")
        self.assertEqual(resolved_by, "current_document_rules")

    def test_verified_reject_is_preserved_without_reentering_the_gate(self):
        resolution = {
            "decision": "reject",
            "reason_code": "verified_existing_establishment",
            "reason": "Se exige un centro previo fuera de Aragón.",
        }
        _, outcome = APP["apply_verified_bdns_hold_resolution"](
            {"source": "BDNS", "bdns_id": "900101"},
            "territorial_eligibility_unverified",
            resolution,
            APP["deterministic_prefilter"],
        )
        self.assertEqual(outcome["decision"], "reject")
        self.assertEqual(outcome["reason_code"], "verified_existing_establishment")
        self.assertEqual(outcome["stage"], "verified_bdns_hold_resolution")

    def test_qa_sample_covers_decisions_before_filling_remaining_slots(self):
        results = [
            {
                "order": index,
                "hold_reason": reason,
                "resolution": {"decision": decision},
            }
            for index, reason, decision in (
                (1, "active_status_unverified", "retain"),
                (2, "territorial_eligibility_unverified", "retain"),
                (3, "consortium_role_unverified", "reject"),
                (4, "cluster_role_unverified", "unresolved"),
            )
        ]
        sample = APP["select_bdns_hold_qa_sample"](results, limit=3)
        self.assertEqual(sample, [1, 3, 4])

    def test_cli_rejects_more_than_twenty_hold_cases(self):
        with mock.patch("sys.argv", ["Grant-Radar-prueba.py", "--hold-pilot", "21"]):
            with self.assertRaises(SystemExit):
                APP["parse_args"]()

    def test_replay_mode_cannot_be_combined_with_ai_or_collection_modes(self):
        for extra in ("--no-claude", "--hold-pilot"):
            argv = ["Grant-Radar-prueba.py", "--replay-hold-report", extra]
            if extra == "--hold-pilot":
                argv.append("1")
            with self.subTest(extra=extra), mock.patch("sys.argv", argv):
                with self.assertRaises(SystemExit):
                    APP["parse_args"]()

    def test_production_hold_reentry_sends_unresolved_case_to_general_analysis(self):
        hold = self.hold_pair("territorial_eligibility_unverified", 50)
        evidence = {
            "documents": [{
                "title": "Bases oficiales",
                "url": "https://example.test/bases",
                "kind": "regulatory_bases",
                "text": "Ayudas para inversiones de eficiencia energética industrial.",
            }],
            "metrics": {"documents_with_text": 1, "fetched_urls": 1},
        }
        globals_dict = APP["resolve_bdns_holds_for_pipeline"].__globals__
        with mock.patch.dict(globals_dict, {
            "retrieve_bdns_hold_evidence": mock.Mock(return_value=evidence),
        }):
            result = APP["resolve_bdns_holds_for_pipeline"]([hold], APP["_bdns_intrinsic_exclusion"], APP["deterministic_prefilter"])
        self.assertEqual(result["counts"], {"ambiguous": 1})
        self.assertEqual(result["rejected"], [])
        self.assertEqual(len(result["retained"]), 1)
        conv = result["retained"][0]
        self.assertEqual(conv["deterministic_prefilter"]["decision"], "ambiguous")
        self.assertEqual(
            conv["deterministic_prefilter"]["reason_code"],
            "verified_hold_still_unresolved",
        )
        self.assertEqual(
            conv["related_document_contents"][0]["title"], "Bases oficiales"
        )

    def test_production_hold_reentry_rejects_intrinsic_document_scope_locally(self):
        hold = self.hold_pair("active_status_unverified", 51)
        evidence = {
            "documents": [{
                "title": "Bases oficiales", "url": "https://example.test/bases",
                "kind": "regulatory_bases",
                "text": "Programa de empleo y acciones formativas para trabajadores.",
            }],
            "metrics": {"documents_with_text": 1},
        }
        globals_dict = APP["resolve_bdns_holds_for_pipeline"].__globals__
        with mock.patch.dict(globals_dict, {
            "retrieve_bdns_hold_evidence": mock.Mock(return_value=evidence),
        }):
            result = APP["resolve_bdns_holds_for_pipeline"]([hold], APP["_bdns_intrinsic_exclusion"], APP["deterministic_prefilter"])
        self.assertEqual(result["counts"], {"reject": 1})
        self.assertEqual(result["retained"], [])
        self.assertEqual(
            result["rejected"][0][1]["reason_code"],
            "explicit_non_industrial_scope",
        )

    def test_hold_pipeline_collects_only_bdns(self):
        fetch_bdns = mock.Mock(return_value=[])
        forbidden = mock.Mock(side_effect=AssertionError("Fuente ajena a BDNS"))
        report = {
            "selected": 0,
            "counts": {},
            "cache_hits": 0,
            "deterministic_resolutions": 0,
            "usage": {},
        }
        replacements = {
            "claude_key_format_is_valid": mock.Mock(return_value=True),
            "fetch_bdns": fetch_bdns,
            "fetch_horizon_europe": forbidden,
            "fetch_eccp": forbidden,
            "fetch_een_funding": forbidden,
            "PlaywrightBrowser": forbidden,
            "run_bdns_hold_pilot": mock.Mock(return_value=report),
            "save_discovery_audit": mock.Mock(),
        }
        with mock.patch.dict(APP["run_pipeline"].__globals__, replacements):
            APP["run_pipeline"](hold_pilot=1)
        fetch_bdns.assert_called_once_with()
        forbidden.assert_not_called()

    def test_deterministic_pilot_writes_report_without_ai_cache(self):
        hold = self.hold_pair("active_status_unverified", 1)
        evidence = {
            "documents": [{
                "url": "https://administracion.example/bases",
                "text": "El plazo de solicitud finaliza el 30/09/2099.",
            }],
            "evidence_hash": "evidence",
            "metrics": {"documents_with_text": 1},
        }
        forbidden_ai = mock.Mock(side_effect=AssertionError("No debía llamar a Haiku"))
        globals_dict = APP["run_bdns_hold_pilot"].__globals__
        with tempfile.TemporaryDirectory() as temporary:
            report_path = str(Path(temporary) / "report.json")
            cache_path = str(Path(temporary) / "cache.json")
            replacements = {
                "BDNS_HOLD_REPORT_FILE": report_path,
                "BDNS_HOLD_CACHE_FILE": cache_path,
                "retrieve_bdns_hold_evidence": mock.Mock(return_value=evidence),
                "analyze_bdns_hold_with_claude": forbidden_ai,
            }
            with mock.patch.dict(globals_dict, replacements):
                report = APP["run_bdns_hold_pilot"]([hold], 1, "clave-no-usada-el-piloto-no-llama", APP["_bdns_intrinsic_exclusion"])
            self.assertEqual(report["counts"], {"retain": 1})
            self.assertEqual(report["usage"]["completed_api_calls"], 0)
            self.assertTrue(Path(report_path).exists())
            self.assertFalse(Path(cache_path).exists())
            forbidden_ai.assert_not_called()

    def test_previous_pilot_report_is_archived_on_version_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            path.write_text(json.dumps({
                "pilot_version": "bdns-hold-old", "status": "completed"
            }), encoding="utf-8")
            APP["_archive_previous_hold_artifact"](
                str(path), None, "pilot_version"
            )
            archive = Path(temporary) / "report.bdns-hold-old.json"
            self.assertFalse(path.exists())
            self.assertTrue(archive.exists())


class FrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_schema_three_controls_are_present(self):
        for marker in (
            'id="source-dropdown-button"', 'id="title-search-input"',
            'id="sort-tooltip"', 'id="footer-updated"', "discovery_sources", "funding_mechanism",
        ):
            self.assertIn(marker, self.html)

    def test_the_eligibility_reason_is_printed_once(self):
        """El motivo salía dos veces: en el aviso y en la nota de la tarjeta.

        Además de repetirse, el texto largo estiraba la tarjeta de ELEGIBILIDAD
        y descuadraba la fila de indicadores. La tarjeta pasa a decir qué dato
        falta; el razonamiento se queda solo en el aviso superior.
        """
        self.assertIn("ov-eligibility-note').textContent = eligibilityNote(c)", self.html)
        self.assertNotIn(
            "ov-eligibility-note').textContent = c.eligibility_reason", self.html
        )
        # La nota corta se construye con los campos que deciden elegibilidad.
        for campo in ("applicant_types", "eligible_geographies", "eligibility_evidence"):
            self.assertIn(campo, self.html)

    def test_all_four_sort_explanations_are_present(self):
        for term in ("Compatibilidad", "Accionabilidad", "Tiempo restante", "Confianza"):
            self.assertIn(term, self.html)

    def test_header_radar_uses_six_subtle_rings_and_a_softer_beam(self):
        for marker in (
            "width: 288px", "transparent 0 22px",
            "rgba(21, 86, 168, .11) 23px 24px",
            "rgba(21, 86, 168, .21) 358deg",
            "clip-path: circle(50% at 50% 50%)", "border: 0",
        ):
            self.assertIn(marker, self.html)

    def test_metric_help_and_spreadsheet_exports_are_present(self):
        for marker in (
            'id="metric-help-active"', 'id="metric-help-discarded"',
            'id="metric-help-review"', "function toggleInfoTooltip",
            "function buildFilteredCSV", "function buildFilteredXLSX", "sep=;",
            "Ayuda máxima EUR", "Siguiente acción", 'state="frozen"',
            "<autoFilter", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ):
            self.assertIn(marker, self.html)
        self.assertNotIn("'Tokens entrada'", self.html)

    def test_unknown_deadlines_are_rendered_without_a_fake_day_count(self):
        for marker in (
            "? null : (Number.isFinite(Number(raw.deadline))",
            "function deadlineText(days",
            "return Number.isFinite(days) ? `${days}${suffix}` : 'Sin fecha'",
        ):
            self.assertIn(marker, self.html)

    def test_opportunity_roles_have_visible_card_labels(self):
        for marker in (
            "opportunity_labels", ".status-label.consortium", "Socio de consorcio",
            ".status-label.cluster", ".status-label.establishment",
        ):
            self.assertIn(marker, self.html)
        self.assertNotIn("opportunity_role === 'supplier'", self.html)
        self.assertNotIn(".status-label.supplier", self.html)

    def test_cards_expose_the_official_link_from_the_main_view(self):
        for marker in (
            "card-external-link", "openConvUrl", "Abrir convocatoria oficial",
            "event.stopPropagation()",
        ):
            self.assertIn(marker, self.html)

    def test_executive_summary_exposes_eligible_actions(self):
        for marker in (
            'id="ov-eligible-actions"', "deriveEligibleActions",
            "Actuaciones elegibles", "eligible_actions_basis",
        ):
            self.assertIn(marker, self.html)

    def test_backend_record_fields_are_understood_by_frontend(self):
        # Contrato backend-frontend: construye un registro público real con
        # `_assemble_public_record()` (la misma función que usa run_pipeline()
        # para cada fila de convocatorias.json, sin recopilar fuentes ni
        # llamar a Claude) y comprueba que el frontend menciona cada campo.
        # Si un campo cambia de nombre en el backend sin actualizar
        # index.html, este test lo detecta.
        conv = {
            "source": "BDNS", "title": "Convocatoria de prueba",
            "description": "Descripción de prueba", "url": "https://example.test/call",
            "org": "Entidad convocante", "keywords_found": ["hidrógeno"],
            "source_type": "BDNS API",
        }
        analysis = {
            "match_score": 70, "fit_score": 70, "actionability_score": 60,
            "confidence": 80, "priority": "high", "descartada": False,
            "decision": "pursue", "eligibility": "eligible",
            "eligibility_reason": "Cumple requisitos", "recommended_role": "direct_beneficiary",
            "scores": {"technology": 80}, "evidence_quality": "high",
            "positive_evidence": ["Evidencia 1"], "risks_and_unknowns": ["Riesgo 1"],
            "partner_needs": ["Socio tecnológico"], "recommended_partners": [],
            "review_required": False, "review_reasons": [], "data_pending": False,
            "data_gaps": [], "monitoring_flags": [],
            "token_usage": {"total_tokens": 100, "estimated_cost_usd": 0.01},
            "call_facts": {"grant_max_eur": 50000}, "trl_min": 4, "trl_max": 7,
            "socio_consorcio": "", "tags": ["ee"], "tech_tags": ["energy_efficiency"],
            "resumen": "Resumen de prueba", "accion": "Acción de prueba",
            "dimensiones": [{"name": "Alineación tecnológica", "val": 80}],
        }
        # Campos de trazabilidad interna que el backend publica pero el
        # frontend, de forma deliberada, no muestra hoy (procedencia de
        # catálogos estáticos y URL alternativa BDNS): quedan fuera del
        # contrato hasta que se decida exponerlos.
        backend_only_fields = {
            "catalog_scope", "catalog_category", "catalog_ref",
            "related_documents_count", "bdns_url",
        }
        record = APP["_assemble_public_record"](1, conv, analysis)
        missing = [
            field for field in record
            if field not in backend_only_fields and field not in self.html
        ]
        self.assertEqual(missing, [])


class DeterministicPostAnalysisTests(unittest.TestCase):
    def test_eligible_actions_prefer_explicit_facts_and_keep_provenance(self):
        actions, basis = APP["derive_eligible_actions"](
            {"description": "Texto general"},
            {
                "eligible_actions": [
                    "Adquisición de maquinaria productiva",
                    "Mejora de procesos industriales",
                ],
                "required_topics": ["Economía circular"],
            },
        )
        self.assertEqual(basis, "explicit")
        self.assertEqual(actions[0], "Adquisición de maquinaria productiva")

    def test_eligible_actions_do_not_present_required_topics_as_costs(self):
        actions, basis = APP["derive_eligible_actions"](
            {"description": "Convocatoria de demostración industrial"},
            {"required_topics": ["Demostrar recuperación de calor residual"]},
        )
        self.assertEqual(actions, ["Demostrar recuperación de calor residual"])
        self.assertEqual(basis, "required_topics")

    def test_eligible_actions_can_reuse_literal_section_from_old_analysis(self):
        actions, basis = APP["derive_eligible_actions"](
            {
                "description": (
                    "Artículo 4. Actuaciones subvencionables: adquisición de "
                    "equipos y modernización de procesos. Artículo 5. Beneficiarios."
                )
            },
            {},
        )
        self.assertEqual(basis, "source_excerpt")
        self.assertIn("adquisición de equipos", actions[0])

    def test_taxonomy_separates_strong_contextual_and_discovery_terms(self):
        self.assertIn(
            "waste-to-energy",
            APP["TECH_TAG_STRONG_TERMS"]["thermal_waste"],
        )
        self.assertIn(
            "digital twin",
            APP["TECH_TAG_CONTEXTUAL_TERMS"]["digital_thermal"],
        )
        self.assertNotIn("oxidación", [
            term for values in APP["TECH_TAGS"].values() for term in values
        ])
        discovery_only = "Industrial process optimisation for a new factory"
        self.assertTrue(APP["has_technology_discovery_signal"](discovery_only))
        self.assertEqual(APP["detect_tech_tags"](discovery_only), [])

    def test_contextual_digital_and_efficiency_terms_need_industrial_context(self):
        self.assertNotIn(
            "digital_thermal",
            APP["detect_tech_tags"]("A digital twin of the ocean ecosystem"),
        )
        self.assertIn(
            "digital_thermal",
            APP["detect_tech_tags"](
                "Digital twin for monitoring an industrial furnace and process heat"
            ),
        )
        self.assertNotIn(
            "energy_efficiency",
            APP["detect_tech_tags"]("Energy efficiency in residential buildings"),
        )
        self.assertIn(
            "energy_efficiency",
            APP["detect_tech_tags"](
                "Energy efficiency investment in industrial process equipment"
            ),
        )

    def test_biomass_flow_mapping_is_not_thermal_valorisation(self):
        self.assertNotIn(
            "thermal_waste",
            APP["detect_tech_tags"](
                "Understanding biomass flows, availability and business data in Europe"
            ),
        )
        self.assertIn(
            "thermal_waste",
            APP["detect_tech_tags"](
                "Open call for technology for valorisation of biomass side-streams"
            ),
        )

    def test_source_status_separates_raw_and_consolidated_counts(self):
        status = APP["build_source_status"](
            {"BOE / MITECO": [{"title": "Documento 1"}, {"title": "Documento 2"}]},
            {},
            {},
            [{
                "title": "Programa consolidado", "source": "IDAE",
                "discovery_sources": ["BOE/MITECO", "IDAE"],
            }],
        )
        boe = next(item for item in status if item["name"] == "BOE / MITECO")
        self.assertEqual(boe["count"], 2)
        self.assertEqual(boe["raw_count"], 2)
        self.assertEqual(boe["consolidated_count"], 1)

    def test_direct_funded_thermal_valorisation_is_not_a_supplier_only_route(self):
        facts = {
            "programme": "Circular valorisation programme",
            "action_type": "Innovation grant",
            "applicant_types": [
                "SMEs offering solutions and/or technology for the valorisation of biomass side-streams",
            ],
            "eligible_entity_types": ["SME"],
            "eligible_geographies": ["EU Member States"],
            "eligibility_evidence": ["Applicants must be SMEs"],
            "budget_total_eur": 2000000,
            "grant_max_eur": 90000,
            "consortium_required": False,
            "required_topics": ["Technologies that maximise biomass valorisation"],
            "expected_outcomes": ["Implementation of a new process"],
            "funding_lines": [], "evidence": [],
        }
        analysis = {
            "fit_score": 35, "actionability_score": 25, "confidence": 50,
            "decision": "discard_out_of_scope", "eligibility": "unknown",
            "eligibility_reason": (
                "El sector agroalimentario no coincide con el perfil; Kalfrisa "
                "solo tendría un rol potencial como proveedor tecnológico."
            ),
            "recommended_role": "not_applicable", "risks_and_unknowns": [
                "Kalfrisa requeriría un beneficiario agroalimentario líder."
            ],
            "positive_evidence": [], "scores": {
                "technological_fit": 35, "strategic_fit": 30, "role_fit": 20,
                "trl_fit": 60, "consortium_readiness": 40,
            },
            "summary": "Fuera del foco de Kalfrisa por tratar biomasa agroalimentaria.",
            "action": "Descartar como proveedor de equipos.",
            "call_facts": facts, "review_reasons": [],
        }
        APP["apply_current_deterministic_rules"]({
            "raw_document": {
                "deadline_days": 60,
                "title": (
                    "Open call for valorisation of agri-food biomass side-streams"
                ),
                "description": (
                    "Funding for SMEs implementing technology for the "
                    "valorisation of biomass side-streams."
                ),
            },
            "analysis": analysis,
        })
        self.assertEqual(analysis["decision"], "watch")
        self.assertFalse(analysis["descartada"])
        self.assertEqual(analysis["recommended_role"], "technology_partner")
        self.assertGreaterEqual(analysis["fit_score"], 60)
        self.assertIn("participantes financiados", analysis["summary"])
        self.assertIn("eligibility_unknown", analysis["data_gaps"])
        self.assertTrue(analysis["data_pending"])
        self.assertFalse(analysis["review_required"])

    def test_valorisation_for_a_customer_is_not_recovered(self):
        facts = {
            "applicant_types": ["Agri-food manufacturers"],
            "eligible_entity_types": ["SME"],
            "budget_total_eur": 1000000, "grant_max_eur": 50000,
            "required_topics": ["Biomass valorisation"],
            "eligibility_evidence": [], "expected_outcomes": [],
            "funding_lines": [], "evidence": [],
        }
        evaluation = {
            "decision": "discard_out_of_scope", "eligibility": "unknown",
            "eligibility_reason": (
                "Kalfrisa solo podría actuar como proveedor tecnológico para un beneficiario."
            ),
        }
        self.assertFalse(APP["_correct_direct_valorisation_scope"](
            evaluation, facts, {"tech_tags": ["thermal_waste"]},
        ))

    def test_explicit_non_aragon_regional_barrier_remains_ineligible(self):
        facts = {
            "eligible_geographies": ["ES53 - Illes Balears"],
            "eligible_entity_types": ["Empresas"],
            "funding_lines": [], "evidence": [],
        }
        analysis = {
            "fit_score": 62, "actionability_score": 28, "confidence": 86,
            "decision": "manual_review", "eligibility": "ineligible",
            "eligibility_reason": (
                "La restricción geográfica a ES53 es determinante: Kalfrisa "
                "está en Zaragoza y no es elegible."
            ),
            "recommended_role": "technology_partner",
            "risks_and_unknowns": [], "positive_evidence": [],
            "scores": {}, "summary": "Existe encaje técnico, no territorial.",
            "action": "Revisar.", "call_facts": facts,
        }
        APP["apply_current_deterministic_rules"]({
            "raw_document": {
                "source": "BDNS", "deadline_days": 90,
                "title": "Ayuda regional para inversión industrial",
            },
            "analysis": analysis,
        })
        self.assertEqual(analysis["decision"], "discard_ineligible")
        self.assertEqual(analysis["eligibility"], "ineligible")
        self.assertFalse(analysis["data_pending"])
        self.assertFalse(analysis["review_required"])

    def _regional_analysis(self, **overrides):
        """Análisis mínimo con el que probar la regla territorial."""
        facts = {
            "eligible_geographies": overrides.pop("geographies", []),
            "eligible_entity_types": ["Empresas"],
            "funding_lines": [], "evidence": [],
        }
        analysis = {
            "fit_score": 55, "actionability_score": 30, "confidence": 70,
            "decision": "watch", "eligibility": "unknown",
            "eligibility_reason": overrides.pop("reason", ""),
            "recommended_role": "technology_partner",
            "risks_and_unknowns": [], "positive_evidence": [],
            "scores": {}, "summary": "", "action": "", "call_facts": facts,
        }
        raw = {
            "source": "BDNS", "deadline_days": 90,
            "title": "Ayuda a la inversión industrial",
        }
        raw.update(overrides)
        APP["apply_current_deterministic_rules"]({"raw_document": raw, "analysis": analysis})
        return analysis

    def test_a_territorial_call_is_discarded_whatever_the_model_wrote(self):
        """La causa de que 25 de 31 convocatorias salieran «por confirmar».

        La regla exigía que el razonamiento del modelo contuviera una de seis
        expresiones tecleadas a mano. Medido sobre el corpus real del 21/08:
        disparaba en 1 de 12 casos. En los otros 11 el propio texto decía «la
        convocatoria limita a ES22 (Navarra)» y aun así se publicaba como
        pendiente de confirmar. Ahora decide el campo `regiones` de la API.
        """
        analysis = self._regional_analysis(
            bdns_regions=["ES22 - COMUNIDAD FORAL DE NAVARRA"],
            reason="Kalfrisa es empresa mediana; requiere confirmación geográfica.",
        )
        self.assertEqual(analysis["eligibility"], "ineligible")
        self.assertEqual(analysis["decision"], "discard_ineligible")

    def test_province_level_codes_also_count_as_another_region(self):
        """`\\bes\\d{2}\\b` no casaba con ES212 ni ES614: media España se escapaba."""
        for region in ("ES212 - Gipuzkoa", "ES614 - Granada", "ES3 - COMUNIDAD DE MADRID"):
            with self.subTest(region=region):
                analysis = self._regional_analysis(bdns_regions=[region])
                self.assertEqual(analysis["eligibility"], "ineligible")

    def test_a_national_call_is_not_discarded_as_territorial(self):
        analysis = self._regional_analysis(bdns_regions=["ES - ESPAÑA"])
        self.assertEqual(analysis["eligibility"], "unknown")
        self.assertNotEqual(analysis["decision"], "discard_ineligible")

    def test_aragon_in_any_form_keeps_the_call(self):
        for region in ("ES24 - ARAGON", "ES243 - Zaragoza", "ES241 - Huesca"):
            with self.subTest(region=region):
                analysis = self._regional_analysis(bdns_regions=[region])
                self.assertEqual(analysis["eligibility"], "unknown")

    def test_a_call_open_to_several_regions_including_aragon_is_kept(self):
        analysis = self._regional_analysis(
            bdns_regions=["ES51 - CATALUÑA", "ES24 - ARAGON"],
        )
        self.assertEqual(analysis["eligibility"], "unknown")

    def test_the_official_field_wins_over_the_model_extraction(self):
        """`bdns_regions` viene de la API; `eligible_geographies`, del modelo."""
        analysis = self._regional_analysis(
            bdns_regions=["ES - ESPAÑA"], geographies=["ES22 - Navarra"],
        )
        self.assertEqual(analysis["eligibility"], "unknown")

    def test_without_the_official_field_the_extracted_geographies_decide(self):
        analysis = self._regional_analysis(geographies=["ES51 - CATALUÑA"])
        self.assertEqual(analysis["eligibility"], "ineligible")

    def test_a_discarded_call_explains_why_even_if_the_model_said_nothing(self):
        analysis = self._regional_analysis(bdns_regions=["ES120 - Asturias"], reason="")
        self.assertIn("ES120 - Asturias", analysis["eligibility_reason"])
        self.assertIn("Zaragoza", analysis["eligibility_reason"])

    def test_own_industrial_investment_is_not_discarded_for_lacking_rd(self):
        facts = {
            "programme": "Plan provincial de suelo industrial",
            "action_type": "Adquisición de suelo industrial",
            "applicant_types": ["Personas jurídicas con actividad económica"],
            "eligible_entity_types": ["Empresas"],
            "eligible_geographies": ["ES243 - Zaragoza"],
            "eligibility_evidence": [
                "Destino a actividad empresarial durante cinco años",
            ],
            "required_topics": [
                "Ampliación o aumento de superficie del centro empresarial",
            ],
            "budget_total_eur": 300000,
            "consortium_required": None,
            "funding_lines": [],
            "evidence": [],
            "expected_outcomes": [],
        }
        analysis = {
            "fit_score": 15, "actionability_score": 10, "confidence": 25,
            "decision": "discard_out_of_scope", "eligibility": "eligible",
            "eligibility_reason": (
                "Kalfrisa es elegible en Zaragoza, pero la convocatoria no es de I+D."
            ),
            "recommended_role": "not_applicable",
            "risks_and_unknowns": ["No hay componente de desarrollo tecnológico."],
            "positive_evidence": [], "scores": {
                "technological_fit": 0, "strategic_fit": 5, "role_fit": 0,
                "trl_fit": 0, "consortium_readiness": 0,
            },
            "summary": "Fuera del foco de I+D.",
            "action": "Descartar.", "call_facts": facts, "review_reasons": [],
        }
        APP["apply_current_deterministic_rules"]({
            "raw_document": {"deadline_days": 60}, "analysis": analysis,
        })
        self.assertEqual(analysis["decision"], "watch")
        self.assertFalse(analysis["descartada"])
        self.assertEqual(analysis["recommended_role"], "leader")
        self.assertGreaterEqual(analysis["fit_score"], 55)
        self.assertIn("inversión directa", analysis["summary"])
        self.assertFalse(analysis["review_required"])
        self.assertNotIn("accion", analysis)
        self.assertNotIn("resumen", analysis)

    def test_own_investment_safeguard_does_not_relax_other_regions(self):
        facts = {
            "action_type": "Adquisición de suelo industrial",
            "applicant_types": ["Empresas"],
            "eligible_entity_types": ["Empresas"],
            "eligible_geographies": ["ES230 - La Rioja"],
            "eligibility_evidence": [], "required_topics": [],
            "expected_outcomes": [], "evidence": [], "funding_lines": [],
        }
        evaluation = {
            "decision": "discard_out_of_scope", "eligibility": "eligible",
            "eligibility_reason": "No es de I+D.",
        }
        changed = APP["_correct_own_industrial_investment_scope"](
            evaluation, facts,
        )
        self.assertFalse(changed)
        self.assertEqual(evaluation["decision"], "discard_out_of_scope")

    def test_own_investment_safeguard_requires_direct_business_eligibility(self):
        facts = {
            "action_type": "Adquisición de equipos industriales",
            "applicant_types": ["Ayuntamientos"],
            "eligible_entity_types": ["Entidades locales"],
            "eligible_geographies": ["Aragón"],
            "eligibility_evidence": [], "required_topics": [],
            "expected_outcomes": [], "evidence": [], "funding_lines": [],
        }
        evaluation = {
            "decision": "discard_out_of_scope", "eligibility": "eligible",
            "eligibility_reason": "No es de I+D.",
        }
        self.assertFalse(APP["_correct_own_industrial_investment_scope"](
            evaluation, facts,
        ))

    def test_mandatory_consortium_is_not_an_entity_exclusion(self):
        analysis = {
            "fit_score": 72, "actionability_score": 60, "confidence": 45,
            "decision": "discard_ineligible", "eligibility": "ineligible",
            "eligibility_reason": (
                "La convocatoria exige consorcio y Kalfrisa como entidad individual "
                "no puede presentarse."
            ),
            "recommended_role": "consortium_partner",
            "risks_and_unknowns": [], "accion": "DESCARTAR como solicitante principal.",
            "call_facts": {
                "eligible_entity_types": ["SMEs"], "applicant_types": ["SMEs"],
                "eligibility_evidence": ["Consortia of SMEs"],
                "consortium_required": True, "budget_total_eur": 1000000,
            },
            "review_reasons": [],
        }
        record = {
            "raw_document": {"deadline_days": 30},
            "analysis": analysis,
        }
        APP["apply_current_deterministic_rules"](record)
        self.assertEqual(analysis["eligibility"], "unknown")
        self.assertEqual(analysis["decision"], "watch")
        self.assertFalse(analysis["descartada"])
        self.assertEqual(analysis["motivo_descarte"], "")
        self.assertIn("consorcio", analysis["eligibility_reason"].lower())
        self.assertIn("eligibility_unknown", analysis["data_gaps"])
        self.assertFalse(analysis["review_required"])

    def test_public_only_applicants_are_not_recovered_by_consortium_rule(self):
        evaluation = {
            "eligibility": "ineligible", "decision": "discard_ineligible",
            "eligibility_reason": "Solo ayuntamientos en consorcio.",
            "recommended_role": "consortium_partner", "risks_and_unknowns": [],
        }
        changed = APP["_correct_consortium_participation_ineligibility"](
            evaluation,
            {
                "eligible_entity_types": ["Ayuntamientos"],
                "applicant_types": ["Entidades locales"],
                "consortium_required": True,
            },
        )
        self.assertFalse(changed)
        self.assertEqual(evaluation["eligibility"], "ineligible")

    def test_required_consortium_member_is_not_required_of_every_partner(self):
        facts = {
            "eligible_entity_types": ["local water management organisations"],
            "applicant_types": [], "consortium_required": True,
            "consortium_evidence": "Each project must involve four cities.",
            "eligibility_evidence": [
                "In participating cities the local water management organisation "
                "should be part of the consortium."
            ],
            "budget_total_eur": None,
        }
        analysis = {
            "fit_score": 55, "actionability_score": 35, "confidence": 20,
            "decision": "discard_ineligible", "eligibility": "ineligible",
            "eligibility_reason": (
                "La convocatoria requires applicants to be local water management "
                "organisations y Kalfrisa no es una organizaciÃ³n de ese tipo."
            ),
            "recommended_role": "not_applicable", "risks_and_unknowns": [],
            "accion": "Descartar.", "call_facts": facts, "review_reasons": [],
        }
        APP["apply_current_deterministic_rules"]({
            "raw_document": {"deadline_days": 400}, "analysis": analysis,
        })
        self.assertEqual(analysis["eligibility"], "unknown")
        self.assertEqual(analysis["decision"], "watch")
        self.assertEqual(analysis["recommended_role"], "consortium_partner")
        self.assertFalse(analysis["descartada"])

    def test_public_action_alias_is_updated_without_leaking_internal_field(self):
        facts = {
            "eligible_entity_types": ["specialist organisation"],
            "applicant_types": [], "consortium_required": True,
            "consortium_evidence": "The consortium must involve four regions.",
            "eligibility_evidence": [
                "At least one specialist organisation should be part of the consortium."
            ],
            "budget_total_eur": None,
        }
        item = {
            "fit_score": 55, "actionability_score": 35, "confidence": 20,
            "decision": "discard_ineligible", "eligibility": "ineligible",
            "eligibility_reason": (
                "The call requires applicants to be specialist organisation and "
                "Kalfrisa is not a specialist organisation."
            ),
            "recommended_role": "not_applicable", "risks_and_unknowns": [],
            "action": "Discard.", "call_facts": facts, "review_reasons": [],
            "deadline_days": 400,
        }
        APP["apply_current_deterministic_rules"]({
            "raw_document": item, "analysis": item,
        })
        self.assertNotIn("accion", item)
        self.assertIn("consorcio", item["action"].lower())
        self.assertFalse(item["descartada"])

    def test_exclusive_applicant_type_is_not_relaxed_without_composition_language(self):
        facts = {
            "eligible_entity_types": ["local water management organisations"],
            "applicant_types": [], "consortium_required": True,
            "consortium_evidence": "Applications must be submitted by a consortium.",
            "eligibility_evidence": [
                "Applicants must be local water management organisations."
            ],
        }
        self.assertEqual(APP["_required_consortium_member_category"](facts), "")
        evaluation = {
            "eligibility": "ineligible", "decision": "discard_ineligible",
            "eligibility_reason": (
                "Applicants must be local water management organisations."
            ),
        }
        self.assertFalse(
            APP["_correct_required_consortium_member_ineligibility"](
                evaluation, facts
            )
        )
        self.assertEqual(evaluation["eligibility"], "ineligible")


class ClaudeUsageAccountingTests(unittest.TestCase):
    class TinyOutput(BaseModel):
        value: str

    @staticmethod
    def message(text, input_tokens, output_tokens):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(
                input_tokens=input_tokens, output_tokens=output_tokens,
                cache_creation_input_tokens=0, cache_read_input_tokens=0,
                service_tier="standard",
            ),
        )

    def test_invalid_output_retry_counts_both_billable_responses(self):
        client = SimpleNamespace(messages=SimpleNamespace(create=mock.Mock(
            side_effect=[
                self.message('{"value":', 100, 20),
                self.message('{"value":"ok"}', 110, 10),
            ]
        )))
        globals_dict = APP["_structured_claude_call"].__globals__
        with mock.patch.dict(globals_dict, {"CLAUDE_SLEEP_S": 0}):
            parsed, usage = APP["_structured_claude_call"](
                client, self.TinyOutput, "system", "user", 100,
                "Fixture", "evaluation", 2,
            )
        self.assertEqual(parsed.value, "ok")
        self.assertEqual(usage["api_calls"], 2)
        self.assertEqual(usage["retry_api_calls"], 1)
        self.assertEqual(usage["total_tokens"], 240)
        self.assertFalse(usage["attempts"][0]["valid_output"])
        self.assertTrue(usage["attempts"][1]["valid_output"])

    def test_aborted_run_includes_prior_completed_analyses_and_failed_attempt(self):
        completed = [{
            "api_calls": 2, "retry_api_calls": 0, "input_tokens": 100,
            "output_tokens": 20, "cache_write_tokens": 0,
            "cache_read_tokens": 0, "total_tokens": 120,
            "estimated_cost_usd": 0.0002,
        }]
        failed = [{
            "stage": "evaluation", "api_calls": 1, "retry_api_calls": 0,
            "input_tokens": 50, "output_tokens": 10,
            "cache_write_tokens": 0, "cache_read_tokens": 0,
            "total_tokens": 60, "estimated_cost_usd": 0.0001,
        }]
        usage = APP["aggregate_aborted_run_usage"](completed, failed)
        self.assertEqual(usage["analyzed_convocations"], 1)
        self.assertEqual(usage["failed_convocations"], 1)
        self.assertEqual(usage["api_calls"], 3)
        self.assertEqual(usage["total_tokens"], 180)

    def test_api_error_is_counted_even_without_token_usage(self):
        error = RuntimeError("credit balance too low")
        client = SimpleNamespace(messages=SimpleNamespace(create=mock.Mock(
            side_effect=error
        )))
        with self.assertRaises(APP["ClaudeAnalysisError"]) as caught:
            APP["_structured_claude_call"](
                client, self.TinyOutput, "system", "user", 100,
                "Fixture", "evaluation", 1,
            )
        partial = APP["aggregate_partial_token_usage"](
            caught.exception.partial_usages
        )
        self.assertEqual(partial["completed_api_calls"], 1)
        self.assertEqual(partial["total_tokens"], 0)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


class FrontendLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise unittest.SkipTest(f"Playwright no disponible: {exc}")
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(_QuietHandler, directory=str(ROOT))
        )
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception as exc:
            cls.playwright.stop()
            cls.server.shutdown()
            raise unittest.SkipTest(f"Chromium de Playwright no disponible: {exc}")
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/index.html"

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.close()
        if hasattr(cls, "playwright"):
            cls.playwright.stop()
        if hasattr(cls, "server"):
            cls.server.shutdown()
            cls.server.server_close()

    def test_the_daily_collection_state_is_shown_when_analyses_are_pending(self):
        """El aviso que cierra el circuito de la recopilación diaria.

        `--no-claude` publica `estado_recopilacion.json` sin llamar a Claude, y
        el panel lo lee aparte para decir cuántas convocatorias esperan un
        análisis que todavía no se ha pagado (AGENTS.md 47.5 y 49).
        """
        page = self.browser.new_page(viewport={"width": 1080, "height": 720})
        page.goto(self.url, wait_until="networkidle")
        banner = page.locator("#collection-state")
        estado = json.loads(
            (ROOT / "estado_recopilacion.json").read_text(encoding="utf-8")
        )
        if not estado.get("pending_analyses"):
            self.assertFalse(banner.is_visible(), "sin pendientes no debe avisar")
        else:
            self.assertTrue(banner.is_visible(), "con pendientes debe avisar")
            texto = banner.inner_text()
            self.assertIn(str(estado["pending_analyses"]), texto)
            self.assertIn("espera", texto)
        page.close()

    def test_requested_viewports_have_no_horizontal_overflow(self):
        for width, height in ((912, 368), (1080, 720), (820, 900), (390, 844)):
            with self.subTest(viewport=(width, height)):
                page = self.browser.new_page(viewport={"width": width, "height": height})
                page.goto(self.url, wait_until="networkidle")
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth - document.documentElement.clientWidth"
                )
                self.assertLessEqual(overflow, 1)
                for selector in (
                    "#source-dropdown-button", "#title-search-input", "#sort-help-button"
                ):
                    self.assertTrue(page.locator(selector).is_visible(), selector)
                page.close()

    def test_source_search_and_touch_tooltip_interactions(self):
        page = self.browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        page.goto(self.url, wait_until="networkidle")
        page.click("#source-dropdown-button")
        self.assertTrue(page.locator("#source-menu").get_attribute("class").endswith("open"))
        page.fill("#title-search-input", "INNOVAE")
        page.press("#title-search-input", "Enter")
        self.assertGreaterEqual(page.locator(".conv-item").count(), 1)
        page.click("#sort-help-button")
        self.assertIn("open", page.locator("#sort-tooltip").get_attribute("class"))
        self.assertTrue(page.locator("#sort-tooltip").is_visible())
        page.press("#sort-help-button", "Escape")
        self.assertNotIn("open", page.locator("#sort-tooltip").get_attribute("class"))
        schema_three = page.evaluate("""normalizeConv({
            title: 'Schema 3 call', source: 'HORIZON EUROPE',
            discovery_sources: ['ECCP', 'EEN'], funding_mechanism: 'cascade'
        }, 0)""")
        self.assertEqual(schema_three["discovery_sources"], ["ECCP", "EEN"])
        self.assertEqual(schema_three["funding_mechanism"], "cascade")
        obsolete_role = page.evaluate("""normalizeConv({
            title: 'Antiguo papel comercial', source: 'BDNS',
            opportunity_role: 'supplier', opportunity_labels: ['Rol: proveedor']
        }, 0)""")
        self.assertEqual(obsolete_role["opportunity_role"], "unknown")
        self.assertEqual(obsolete_role["opportunity_labels"], [])
        page.close()

    def test_source_count_remains_visible_and_boe_alias_filters_innovae(self):
        page = self.browser.new_page(viewport={"width": 912, "height": 900})
        page.goto(self.url, wait_until="networkidle")
        page.evaluate("""() => {
          convocatorias = [normalizeConv({
            id: 901, title: 'Programa INNOVAE', source: 'IDAE',
            discovery_sources: ['IDAE', 'BOE/MITECO'], deadline: 90,
            match: 70, priority: 'medium', org: 'IDAE', tags: [],
            url: 'https://example.test/innovae'
          })];
          sources = [{
            name: 'BOE / MITECO', type: 'API BOE', status: 'ok',
            raw_count: 2, count: 2, time: 'fixture'
          }];
          filterState.source = 'all';
          filterState.query = '';
          filterState.showDiscarded = false;
          filterState.onlyReview = false;
          buildSourceMenu();
          renderConvs();
          renderSources();
        }""")
        page.click("#source-dropdown-button")
        boe = page.locator(".source-option", has_text="BOE / MITECO")
        self.assertEqual(boe.locator(".source-count").text_content(), "1")
        boe.click()
        self.assertEqual(page.locator(".conv-title").all_text_contents(), ["Programa INNOVAE"])
        page.click("#source-dropdown-button")
        active_count = page.locator(".source-option.active .source-count")
        self.assertTrue(active_count.is_visible())
        self.assertEqual(active_count.text_content(), "1")
        self.assertEqual(active_count.evaluate("el => getComputedStyle(el).color"), "rgb(255, 255, 255)")
        self.assertTrue(page.evaluate("convHasSource({source:'IDAE', discovery_sources:['BOE/MITECO']}, 'BOE / MITECO')"))
        source_row = page.locator(".source-item", has_text="BOE / MITECO")
        self.assertEqual(source_row.locator(".source-raw-count").text_content(), "2")
        self.assertEqual(source_row.locator(".source-consolidated-count").text_content(), "1")
        self.assertIn("registros → convocatorias", source_row.text_content())
        page.close()

    def test_download_format_has_clear_separation_from_description(self):
        page = self.browser.new_page(viewport={"width": 912, "height": 900})
        page.goto(self.url, wait_until="networkidle")
        values = page.locator(".toolbar-actions .download-option").first.evaluate(
            "el => ({gap:getComputedStyle(el).columnGap, columns:getComputedStyle(el).gridTemplateColumns})"
        )
        self.assertEqual(values["gap"], "10px")
        self.assertTrue(values["columns"].startswith("44px"), values["columns"])
        page.close()

    def test_card_external_link_opens_official_url_without_opening_detail(self):
        page = self.browser.new_page(viewport={"width": 912, "height": 900})
        page.goto(self.url, wait_until="networkidle")
        page.evaluate("window.__openedUrl = ''; window.open = url => { window.__openedUrl = url; }")
        link = page.locator(".conv-item .card-external-link").first
        score = page.locator(".conv-item .score-value").first
        self.assertTrue(link.is_visible())
        self.assertLess(link.bounding_box()["x"], score.bounding_box()["x"])
        expected = page.locator(".conv-item").first.evaluate(
            "el => convocatorias.find(item => item.id === Number(el.querySelector('.card-external-link').getAttribute('onclick').match(/\\d+/)[0])).url"
        )
        link.click()
        self.assertEqual(page.evaluate("window.__openedUrl"), expected)
        self.assertFalse(page.locator(".overlay.open").is_visible())
        page.evaluate("window.__openedUrl = ''")
        link.press("Enter")
        self.assertEqual(page.evaluate("window.__openedUrl"), expected)
        self.assertFalse(page.locator(".overlay.open").is_visible())
        page.close()

    def test_toolbar_and_metrics_are_not_visually_clipped(self):
        for width, height in ((912, 900), (1080, 900), (1366, 900)):
            with self.subTest(viewport=(width, height)):
                page = self.browser.new_page(viewport={"width": width, "height": height})
                page.goto(self.url, wait_until="networkidle")
                toolbar_box = page.locator(".toolbar").bounding_box()
                self.assertIsNotNone(toolbar_box)
                for chip in page.locator(".filter-chip").all():
                    self.assertTrue(chip.is_visible(), chip.text_content())
                    box = chip.bounding_box()
                    self.assertGreaterEqual(box["x"], toolbar_box["x"] - 1)
                    self.assertLessEqual(
                        box["x"] + box["width"],
                        toolbar_box["x"] + toolbar_box["width"] + 1,
                        chip.text_content(),
                    )
                for metric in page.locator(".mini-metric").all():
                    clipped = metric.evaluate(
                        "el => el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1"
                    )
                    self.assertFalse(clipped, metric.text_content())
                page.close()

    def test_help_tooltips_open_on_click_and_escape(self):
        page = self.browser.new_page(viewport={"width": 912, "height": 900})
        page.goto(self.url, wait_until="networkidle")
        page.click("#sort-help-button")
        self.assertTrue(page.locator("#sort-tooltip").is_visible())
        box = page.locator("#sort-tooltip").bounding_box()
        self.assertGreaterEqual(box["x"], 0)
        self.assertLessEqual(box["x"] + box["width"], 912)
        page.press("#sort-help-button", "Escape")
        self.assertFalse(page.locator("#sort-tooltip").is_visible())
        metric_button = page.locator('[aria-describedby="metric-help-active"]')
        metric_button.click()
        self.assertTrue(page.locator("#metric-help-active").is_visible())
        box = page.locator("#metric-help-active").bounding_box()
        self.assertGreaterEqual(box["x"], 0)
        self.assertLessEqual(box["x"] + box["width"], 912)
        page.press('[aria-describedby="metric-help-active"]', "Escape")
        self.assertFalse(page.locator("#metric-help-active").is_visible())
        page.close()

    def test_csv_exports_filtered_business_fields_safely(self):
        page = self.browser.new_page(viewport={"width": 912, "height": 900})
        page.goto(self.url, wait_until="networkidle")
        csv = page.evaluate("""() => buildFilteredCSV([normalizeConv({
          id: 7, identifier: 'CALL-7', title: '=RIESGO', source: 'ECCP',
          discovery_sources: ['ECCP', 'EEN'], org: 'Entidad', deadline: 45,
          deadline_date: '2026-09-30', fit_score: 72, actionability_score: 64,
          confidence: 80, priority: 'high', eligibility: 'eligible',
          decision: 'pursue', summary: 'Resumen útil', action: 'Preparar memoria',
          call_facts: { grant_max_eur: 50000, consortium_required: false },
          url: 'https://example.test/call'
        })])""")
        self.assertTrue(csv.startswith("\ufeffsep=;\r\n"))
        self.assertIn('"Ayuda máxima EUR"', csv)
        self.assertIn('"Siguiente acción"', csv)
        self.assertIn('"\'=RIESGO"', csv)
        self.assertNotIn("Tokens entrada", csv)
        page.close()

    def test_download_menu_offers_xlsx_and_csv(self):
        page = self.browser.new_page(viewport={"width": 1366, "height": 900})
        page.goto(self.url, wait_until="networkidle")
        button = page.locator(".toolbar-actions .download-button")
        button.click()
        menu = page.locator(".toolbar-actions .download-menu")
        self.assertTrue(menu.is_visible())
        self.assertEqual(menu.locator(".download-format").all_text_contents(), ["XLSX", "CSV"])
        page.press(".toolbar-actions .download-option", "Escape")
        self.assertFalse(menu.is_visible())
        page.close()

    def test_filter_icon_is_inside_source_control_and_radar_centres_on_logo(self):
        for width in (390, 1366):
            with self.subTest(width=width):
                page = self.browser.new_page(viewport={"width": width, "height": 900})
                page.goto(self.url, wait_until="networkidle")
                source_button = page.locator("#source-dropdown-button")
                self.assertEqual(source_button.locator("svg.source-dropdown-icon").count(), 1)
                self.assertEqual(
                    source_button.locator("svg.source-dropdown-icon path").get_attribute("stroke-width"),
                    "1.4",
                )
                centres = page.evaluate("""() => {
                  const header = document.querySelector('.app-header');
                  const logo = document.querySelector('.brand-logo').getBoundingClientRect();
                  const headerBox = header.getBoundingClientRect();
                  const radar = getComputedStyle(header, '::before');
                  return {
                    logo: logo.left + logo.width / 2,
                    radar: headerBox.left + parseFloat(radar.left) + parseFloat(radar.width) / 2,
                    radarWidth: parseFloat(radar.width),
                    logoRadius: getComputedStyle(document.querySelector('.brand-logo')).borderRadius,
                    logoClip: getComputedStyle(document.querySelector('.brand-logo')).clipPath
                  };
                }""")
                # El borde de 1 px del header separa los sistemas de referencia;
                # el cambio respecto a la posición CSS anterior es 0,8 px.
                self.assertAlmostEqual(centres["logo"] - centres["radar"], 1.8, delta=0.25)
                self.assertEqual(centres["radarWidth"], 288)
                self.assertEqual(centres["logoRadius"], "50%")
                self.assertIn("circle(50%", centres["logoClip"])
                page.close()

    def test_overview_tints_and_footer_data_timestamp(self):
        page = self.browser.new_page(viewport={"width": 1366, "height": 900})
        page.goto(self.url, wait_until="networkidle")
        colors = page.evaluate("""() => ({
          high: getComputedStyle(document.querySelector('.overview-main')).backgroundColor,
          urgent: getComputedStyle(document.querySelector('.overview-urgent')).backgroundColor
        })""")
        self.assertEqual(colors["high"], "rgb(237, 244, 252)")
        self.assertEqual(colors["urgent"], "rgb(253, 241, 243)")
        timestamp = page.evaluate("""() => {
          dashboardMeta.generated_at = '2026-08-13T12:34:00Z';
          updateGeneratedTimestamp();
          const footer = document.getElementById('footer-updated');
          return { text: footer.textContent, datetime: footer.getAttribute('datetime') };
        }""")
        self.assertIn("Última actualización de datos: 13/08/2026", timestamp["text"])
        self.assertEqual(timestamp["datetime"], "2026-08-13T12:34:00.000Z")
        page.close()

    def test_xlsx_export_is_a_styled_filtered_workbook(self):
        page = self.browser.new_page(viewport={"width": 912, "height": 900})
        page.goto(self.url, wait_until="networkidle")
        result = page.evaluate("""() => {
          const bytes = buildFilteredXLSX([normalizeConv({
            id: 7, identifier: 'CALL-7', title: '=RIESGO', source: 'ECCP',
            discovery_sources: ['ECCP', 'EEN'], org: 'Entidad', deadline: 45,
            deadline_date: '2026-09-30', fit_score: 72, actionability_score: 64,
            confidence: 80, priority: 'high', eligibility: 'eligible',
            decision: 'pursue', summary: 'Resumen útil', action: 'Preparar memoria',
            call_facts: { grant_max_eur: 50000, consortium_required: false },
            url: 'https://example.test/call'
          })]);
          const clearText = new TextDecoder().decode(bytes);
          return {
            payload: Array.from(bytes),
            signature: Array.from(bytes.slice(0, 4)),
            hasWorksheet: clearText.includes('xl/worksheets/sheet1.xml'),
            hasFrozenHeader: clearText.includes('state="frozen"'),
            hasAutoFilter: clearText.includes('<autoFilter'),
            hasColumnWidths: clearText.includes('<cols>'),
            neutralizesFormula: clearText.includes('&apos;=RIESGO'),
            excludesTokens: !clearText.includes('Tokens entrada')
          };
        }""")
        self.assertEqual(result["signature"], [80, 75, 3, 4])
        with zipfile.ZipFile(io.BytesIO(bytes(result["payload"]))) as workbook:
            self.assertEqual(workbook.testzip(), None)
            self.assertIn("xl/worksheets/sheet1.xml", workbook.namelist())
            self.assertIn("xl/styles.xml", workbook.namelist())
        for key in (
            "hasWorksheet", "hasFrozenHeader", "hasAutoFilter", "hasColumnWidths",
            "neutralizesFormula", "excludesTokens",
        ):
            self.assertTrue(result[key], key)
        page.close()

    def test_xlsx_and_csv_export_columns_match_the_expected_contract(self):
        # Test de regresión: fija la lista exacta de columnas de exportación
        # (compartida por XLSX y CSV a través de buildExportTable()). Si
        # alguien añade, quita o reordena una columna en index.html sin
        # actualizar esta lista, este test falla y avisa del cambio en vez
        # de dejarlo pasar silenciosamente.
        expected_headers = [
            'Identificador', 'Título', 'Fuente principal', 'Fuentes de descubrimiento', 'Organismo', 'Programa',
            'Mecanismo de financiación', 'Estado', 'Apertura', 'Cierre', 'Días restantes', 'Fecha sin confirmar',
            'Compatibilidad %', 'Accionabilidad %', 'Confianza %', 'Prioridad', 'Elegibilidad', 'Motivo de elegibilidad',
            'Decisión', 'Papel de oportunidad', 'Rol recomendado', 'Presupuesto publicado', 'Presupuesto total EUR',
            'Coste mínimo de proyecto EUR', 'Ayuda máxima EUR', 'Financiación %', 'TRL mínimo', 'TRL máximo',
            'Consorcio obligatorio', 'Geografías elegibles', 'Tipos de solicitante', 'Actuaciones elegibles', 'Temas requeridos', 'Temáticas',
            'Taxonomía tecnológica', 'Objeto y actuaciones', 'Resumen', 'Siguiente acción', 'Evidencias positivas', 'Riesgos e incógnitas',
            'Datos pendientes', 'Datos no localizados', 'Contradicción reglas-modelo',
            'Motivos de contradicción', 'Alertas de seguimiento', 'Socios recomendados', 'Necesidades de socio',
            'Calidad de evidencia', 'Descartada', 'URL oficial',
        ]
        page = self.browser.new_page(viewport={"width": 912, "height": 600})
        page.goto(self.url, wait_until="networkidle")
        actual_headers = page.evaluate("""() => {
          const conv = normalizeConv({
            id: 1, identifier: 'CALL-1', title: 'Prueba', source: 'BDNS',
            org: 'Entidad', deadline: 30, url: 'https://example.test/call'
          });
          return buildExportTable([conv]).headers;
        }""")
        self.assertEqual(actual_headers, expected_headers)
        page.close()

    def test_consortium_role_is_visible_on_the_card_without_opening_it(self):
        page = self.browser.new_page(viewport={"width": 912, "height": 600})
        page.goto(self.url, wait_until="networkidle")
        page.evaluate("""() => {
          convocatorias = [normalizeConv({
            id: 991, title: 'Proyecto de descarbonización', source: 'BDNS',
            opportunity_role: 'consortium_partner', opportunity_labels: ['Socio de consorcio'],
            deadline: 60, match: 70, priority: 'medium', org: 'Entidad convocante',
            tags: [], url: 'https://example.test/call'
          })];
          filterState.showDiscarded = false;
          filterState.onlyReview = false;
          filterState.query = '';
          filterState.source = 'all';
          renderConvs();
        }""")
        label = page.locator(".conv-item .status-label.consortium")
        self.assertTrue(label.is_visible())
        self.assertEqual(label.text_content(), "Socio de consorcio")
        page.close()


class StructuredCallRetryTests(unittest.TestCase):
    """Un JSON truncado no se arregla repitiendo la misma petición.

    Con temperature=0 la respuesta es idéntica, así que los reintentos solo
    gastaban. Ocurrió con el Programa INNOVAE el 20/08/2026: tres intentos
    fallando en la misma columna, $0,0896 y una ejecución abortada.
    """

    def _cliente_que_trunca(self, techos):
        """Devuelve siempre un JSON cortado a la mitad, como el caso real."""

        class FakeMessages:
            def create(self, **kwargs):
                techos.append(kwargs["max_tokens"])
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text='{"call_status": "open"')],
                    usage=SimpleNamespace(
                        input_tokens=1_000, output_tokens=kwargs["max_tokens"],
                        cache_creation_input_tokens=0, cache_read_input_tokens=0,
                        service_tier="standard",
                    ),
                )

        return SimpleNamespace(messages=FakeMessages())

    def test_each_retry_raises_the_output_ceiling(self):
        techos = []
        with mock.patch.dict(APP["_structured_claude_call"].__globals__,
                             {"CLAUDE_SLEEP_S": 0}):
            with self.assertRaises(APP["ClaudeAnalysisError"]):
                APP["_structured_claude_call"](
                    self._cliente_que_trunca(techos), APP["CallFacts"],
                    "sistema", "prompt", 2_000,
                    "Convocatoria de prueba", "extracción factual", 3,
                )
        self.assertEqual(len(techos), 3, techos)
        self.assertEqual(techos[0], 2_000)
        self.assertGreater(techos[1], techos[0])
        self.assertGreater(techos[2], techos[1])

    def test_the_ceiling_is_bounded(self):
        techos = []
        with mock.patch.dict(APP["_structured_claude_call"].__globals__,
                             {"CLAUDE_SLEEP_S": 0}):
            with self.assertRaises(APP["ClaudeAnalysisError"]):
                APP["_structured_claude_call"](
                    self._cliente_que_trunca(techos), APP["CallFacts"],
                    "sistema", "prompt", 9_000,
                    "Convocatoria de prueba", "extracción factual", 3,
                )
        for techo in techos:
            self.assertLessEqual(techo, APP["STRUCTURED_OUTPUT_TOKEN_CEILING"])

    def test_the_partial_spend_of_failed_attempts_is_reported(self):
        # El aborto debe poder explicar qué se gastó sin resultado.
        techos = []
        with mock.patch.dict(APP["_structured_claude_call"].__globals__,
                             {"CLAUDE_SLEEP_S": 0}):
            try:
                APP["_structured_claude_call"](
                    self._cliente_que_trunca(techos), APP["CallFacts"],
                    "sistema", "prompt", 2_000,
                    "Convocatoria de prueba", "extracción factual", 3,
                )
            except APP["ClaudeAnalysisError"] as exc:
                self.assertEqual(len(exc.partial_usages), 3)
                self.assertTrue(all(not u["valid_output"] for u in exc.partial_usages))
            else:
                self.fail("debería haber abortado")

    def test_extraction_has_more_room_than_evaluation(self):
        # La extracción es la etapa que recibió la evidencia enriquecida y la
        # que se truncó en producción: necesita más techo, no menos.
        # Se lee grant_radar/analysis.py, donde vive la capa desde el
        # 31/08/2026 (AGENTS.md, sección 48).
        fuente = (ROOT / "grant_radar" / "analysis.py").read_text(encoding="utf-8")
        self.assertIn("extraction_prompt, 5000,", fuente)
        self.assertIn("evaluation_prompt, 3000,", fuente)


class HaikuPayloadTests(unittest.TestCase):
    """Qué evidencia viaja realmente a Haiku.

    Antes de la ronda del 20/08/2026, el pipeline extraía 21 campos
    estructurados de la API de SNPSAP, los usaba en la matriz de reglas y no se
    los pasaba al modelo: se le preguntaba quién puede solicitar cuando la
    respuesta oficial ya estaba en casa. Y las bases recuperadas de un hold
    llegaban con `document_role` = "document", valor que el orden de prioridad
    documental no reconoce, así que se ordenaban las últimas.
    """

    def test_official_structured_fields_travel_to_the_prompt(self):
        conv = {
            "bdns_id": "900123",
            "bdns_beneficiary_types": ["PYME Y PERSONAS FÍSICAS QUE DESARROLLAN ACTIVIDAD ECONÓMICA"],
            "bdns_nace_codes": ["25.11"],
            "bdns_nace_sections": ["C"],
            "bdns_regions": ["ARAGÓN"],
            "bdns_finality": "Industria y energía",
            "bdns_instruments": ["SUBVENCIÓN"],
            "bdns_project_execution_days": 730,
        }
        facts = APP["_official_structured_facts"](conv)
        self.assertEqual(
            facts["tipos_de_beneficiario"],
            ["PYME Y PERSONAS FÍSICAS QUE DESARROLLAN ACTIVIDAD ECONÓMICA"],
        )
        self.assertEqual(facts["codigos_cnae"], ["25.11"])
        self.assertEqual(facts["regiones"], ["ARAGÓN"])
        self.assertEqual(facts["dias_de_ejecucion"], 730)

    def test_the_programme_conditions_travel_with_their_source_document(self):
        """Sin esto, Horizon llegaba a Haiku sin decir quién puede solicitar.

        Las condiciones generales no son de la convocatoria sino del programa,
        así que viajan etiquetadas y con el documento del que se leyeron, para
        que el modelo pueda citarlo y para que se vea de dónde salen
        (AGENTS.md 49.7).
        """
        facts = APP["_official_structured_facts"]({
            "source": "HORIZON EUROPE",
            "types_of_action": "HORIZON Innovation Actions",
            "programme_eligibility": {
                "source_url": "https://ec.europa.eu/…/wp-15-general-annexes_horizon-2026-2027_en.pdf",
                "consortium_composition": "three legal entities independent from each other",
            },
        })
        programa = facts["condiciones_generales_del_programa"]
        self.assertIn("general-annexes", programa["documento"])
        self.assertIn("three legal entities", programa["consortium_composition"])
        self.assertEqual(facts["tipo_de_accion"], "HORIZON Innovation Actions")

    def test_a_call_without_programme_conditions_carries_no_empty_block(self):
        facts = APP["_official_structured_facts"]({
            "source": "BDNS", "bdns_regions": ["ARAGÓN"], "programme_eligibility": {},
        })
        self.assertNotIn("condiciones_generales_del_programa", facts)
        self.assertNotIn("tipo_de_accion", facts)

    def test_pipeline_conclusions_are_not_sent_as_if_they_were_source_facts(self):
        # bdns_company_eligible y bdns_call_access son decisiones de la matriz,
        # no datos de la fuente: mezclarlas difuminaría esa frontera.
        conv = {
            "bdns_beneficiary_types": ["GRAN EMPRESA"],
            "bdns_company_eligible": True,
            "bdns_call_access": "named",
            "bdns_territorial_requirement": "existing_establishment",
        }
        facts = APP["_official_structured_facts"](conv)
        for prohibido in ("bdns_company_eligible", "bdns_call_access",
                          "bdns_territorial_requirement"):
            self.assertNotIn(prohibido, facts)
        self.assertEqual(facts["tipos_de_beneficiario"], ["GRAN EMPRESA"])

    def test_a_call_without_structured_data_yields_nothing(self):
        # Horizon, ECCP o EEN no traen estos campos: el bloque no debe añadirse.
        self.assertEqual(APP["_official_structured_facts"]({"title": "x"}), {})

    def test_recovered_bases_keep_a_role_the_ranking_understands(self):
        conv = {"related_document_contents": []}
        evidence = {"documents": [
            {"title": "Bases reguladoras", "url": "https://x.test/bases.pdf",
             "kind": "document", "text": "Beneficiarios: empresas. " * 40},
            {"title": "Anuncio", "url": "https://x.test/anuncio",
             "kind": "announcement", "text": "Extracto de la convocatoria. " * 40},
        ]}
        actualizado = APP["_attach_bdns_hold_evidence"](conv, evidence)
        roles = [d["document_role"] for d in actualizado["related_document_contents"]]
        self.assertEqual(roles, ["regulatory_bases", "call_extract"])

    def test_the_document_budget_is_shared_and_bounded(self):
        presupuesto = {"remaining": APP["EVIDENCE_TOTAL_DOCUMENT_BUDGET"]}
        documento = {
            "title": "Bases", "url": "https://x.test/a",
            "document_role": "regulatory_bases",
            "description": "Requisitos de los beneficiarios. " * 2_000,
        }
        primero = APP["_related_document_evidence"](documento, presupuesto)
        self.assertIsNotNone(primero)
        self.assertLessEqual(
            len(primero["description"]), APP["EVIDENCE_PER_DOCUMENT_BUDGET"]
        )
        self.assertLess(
            presupuesto["remaining"], APP["EVIDENCE_TOTAL_DOCUMENT_BUDGET"]
        )

    def test_a_document_is_dropped_when_the_budget_is_exhausted(self):
        presupuesto = {"remaining": 100}
        self.assertIsNone(APP["_related_document_evidence"](
            {"title": "Bases", "description": "texto " * 500}, presupuesto
        ))

    def test_recovered_bases_get_more_room_than_before(self):
        # La regresión concreta: se guardaban 12.000 caracteres y el prompt los
        # recortaba a 6.000, perdiendo la mitad de la evidencia recuperada.
        self.assertGreater(APP["EVIDENCE_PER_DOCUMENT_BUDGET"], 6_000)


if __name__ == "__main__":
    unittest.main()
