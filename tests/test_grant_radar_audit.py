# Pruebas de grant_radar/audit.py con import estándar (sin runpy).
#
# Cubren las dos mitades del módulo: audit_exclusion(), que solo toca memoria,
# y save_discovery_audit()/load_audit_runs(), que escriben y leen el histórico
# de grant_radar_audit.json. La segunda mitad se extrajo del script el
# 31/08/2026 (AGENTS.md, sección 48) y trajo consigo estas pruebas.

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grant_radar.audit import (
    AUDIT_MAX_RUNS,
    AUDIT_SCHEMA_VERSION,
    DISCOVERY_AUDIT,
    audit_exclusion,
    load_audit_runs,
    save_discovery_audit,
)
from grant_radar.runtime_state import COVERAGE_WATCH_RESULTS, RUN_DIAGNOSTICS


class AuditExclusionTests(unittest.TestCase):
    def setUp(self):
        DISCOVERY_AUDIT.clear()

    def test_records_a_new_exclusion(self):
        audit_exclusion(
            {"source": "IDAE CATÁLOGO", "title": "Convocatoria de prueba", "url": "https://example.test"},
            "deadline_closed",
            "idae_catalog_filter",
        )
        self.assertEqual(len(DISCOVERY_AUDIT), 1)
        entry = DISCOVERY_AUDIT[0]
        self.assertEqual(entry["source"], "IDAE CATÁLOGO")
        self.assertEqual(entry["reason"], "deadline_closed")
        self.assertEqual(entry["stage"], "idae_catalog_filter")

    def test_deduplicates_the_same_exclusion(self):
        item = {"source": "BOA ARAGÓN", "title": "Convocatoria repetida", "url": "https://example.test/repetida"}
        audit_exclusion(item, "deadline_closed", "idae_catalog_filter")
        audit_exclusion(item, "deadline_closed", "idae_catalog_filter")
        self.assertEqual(len(DISCOVERY_AUDIT), 1)

    def test_a_different_reason_is_a_separate_entry(self):
        item = {"source": "BOA ARAGÓN", "title": "Convocatoria X", "url": "https://example.test/x"}
        audit_exclusion(item, "deadline_closed", "idae_catalog_filter")
        audit_exclusion(item, "out_of_scope", "hard_out_of_scope")
        self.assertEqual(len(DISCOVERY_AUDIT), 2)


class SaveDiscoveryAuditTests(unittest.TestCase):
    """El histórico es la única memoria entre ejecuciones que hay hoy."""

    def setUp(self):
        DISCOVERY_AUDIT.clear()
        RUN_DIAGNOSTICS.clear()
        COVERAGE_WATCH_RESULTS.clear()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(DISCOVERY_AUDIT.clear)
        self.addCleanup(RUN_DIAGNOSTICS.clear)
        self.addCleanup(COVERAGE_WATCH_RESULTS.clear)
        self.audit_file = str(Path(self.temporary.name) / "audit.json")

    def guardar(self, status="completed_no_claude", **kwargs):
        save_discovery_audit(
            "2026-08-11T00:00:00+00:00", status, audit_file=self.audit_file, **kwargs
        )
        return json.loads(Path(self.audit_file).read_text(encoding="utf-8"))

    def test_the_candidate_inventory_travels_inside_the_diagnostics(self):
        inventory = {"schema_version": 1, "count": 1, "items": [{"title": "Call"}]}
        RUN_DIAGNOSTICS["candidate_inventory"] = inventory
        payload = self.guardar()
        stored = payload["runs"][-1]["diagnostics"]["candidate_inventory"]
        self.assertEqual(stored, inventory)

    def test_an_exclusion_is_stored_once_and_referenced_by_id(self):
        audit_exclusion(
            {"source": "BDNS", "title": "Convocatoria", "url": "https://example.test"},
            "deadline_closed",
            "bdns_filter",
        )
        payload = self.guardar()
        run = payload["runs"][-1]
        self.assertEqual(payload["schema_version"], AUDIT_SCHEMA_VERSION)
        self.assertEqual(len(run["excluded_ids"]), 1)
        self.assertEqual(len(payload["exclusions"]), 1)
        # El identificador es el puente entre la ejecución y el catálogo: si
        # deja de coincidir, el histórico queda con exclusiones huérfanas.
        self.assertIn(run["excluded_ids"][0], payload["exclusions"])
        # La clave interna de deduplicación no debe llegar al archivo.
        self.assertNotIn("_key", payload["exclusions"][run["excluded_ids"][0]])

    def test_the_history_keeps_the_last_runs_and_drops_orphan_exclusions(self):
        """Rotación: AUDIT_MAX_RUNS ejecuciones, y sin exclusiones colgando."""
        audit_exclusion(
            {"source": "BDNS", "title": "Vieja", "url": "https://example.test/vieja"},
            "deadline_closed",
            "bdns_filter",
        )
        self.guardar()
        DISCOVERY_AUDIT.clear()
        with mock.patch("grant_radar.audit.AUDIT_MAX_RUNS", 2):
            self.guardar()
            payload = self.guardar()
        self.assertEqual(len(payload["runs"]), 2)
        # La exclusión de la primera ejecución ya no la referencia nadie.
        self.assertEqual(payload["exclusions"], {})

    def test_a_v1_history_is_migrated_instead_of_discarded(self):
        Path(self.audit_file).write_text(
            json.dumps({
                "schema_version": 1,
                "runs": [{
                    "started_at": "2026-08-01T00:00:00+00:00",
                    "status": "completed",
                    "excluded": [{"source": "BOE", "title": "Antigua"}],
                }],
            }),
            encoding="utf-8",
        )
        payload = self.guardar()
        self.assertEqual(payload["schema_version"], AUDIT_SCHEMA_VERSION)
        self.assertEqual(len(payload["runs"]), 2)
        migrada = payload["runs"][0]
        self.assertEqual(len(migrada["excluded_ids"]), 1)
        self.assertEqual(
            payload["exclusions"][migrada["excluded_ids"][0]]["title"], "Antigua"
        )

    def test_an_unreadable_history_is_recreated_without_stopping_the_run(self):
        Path(self.audit_file).write_text("{esto no es JSON", encoding="utf-8")
        payload = self.guardar()
        self.assertEqual(len(payload["runs"]), 1)


class LoadAuditRunsTests(unittest.TestCase):
    """Nunca debe interrumpir una ejecución: ante la duda, lista vacía."""

    def test_reads_only_the_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            ruta = Path(temporary) / "audit.json"
            ruta.write_text(
                json.dumps({"runs": [{"status": "completed"}], "exclusions": {}}),
                encoding="utf-8",
            )
            self.assertEqual(load_audit_runs(str(ruta)), [{"status": "completed"}])

    def test_a_missing_file_is_an_empty_history(self):
        self.assertEqual(load_audit_runs("no-existe-este-archivo.json"), [])

    def test_a_history_with_another_shape_is_an_empty_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            ruta = Path(temporary) / "audit.json"
            ruta.write_text(json.dumps({"runs": "no es una lista"}), encoding="utf-8")
            self.assertEqual(load_audit_runs(str(ruta)), [])


if __name__ == "__main__":
    unittest.main()
