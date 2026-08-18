# Pruebas de grant_radar/audit.py con import estándar (sin runpy).

import unittest

from grant_radar.audit import DISCOVERY_AUDIT, audit_exclusion


class AuditExclusionTests(unittest.TestCase):
    def setUp(self):
        DISCOVERY_AUDIT.clear()

    def test_records_a_new_exclusion(self):
        audit_exclusion(
            {"source": "BOA ARAGÓN", "title": "Convocatoria de prueba", "url": "https://example.test"},
            "deadline_closed",
            "boa_static_filter",
        )
        self.assertEqual(len(DISCOVERY_AUDIT), 1)
        entry = DISCOVERY_AUDIT[0]
        self.assertEqual(entry["source"], "BOA ARAGÓN")
        self.assertEqual(entry["reason"], "deadline_closed")
        self.assertEqual(entry["stage"], "boa_static_filter")

    def test_deduplicates_the_same_exclusion(self):
        item = {"source": "BOA ARAGÓN", "title": "Convocatoria repetida", "url": "https://example.test/repetida"}
        audit_exclusion(item, "deadline_closed", "boa_static_filter")
        audit_exclusion(item, "deadline_closed", "boa_static_filter")
        self.assertEqual(len(DISCOVERY_AUDIT), 1)

    def test_a_different_reason_is_a_separate_entry(self):
        item = {"source": "BOA ARAGÓN", "title": "Convocatoria X", "url": "https://example.test/x"}
        audit_exclusion(item, "deadline_closed", "boa_static_filter")
        audit_exclusion(item, "out_of_scope", "hard_out_of_scope")
        self.assertEqual(len(DISCOVERY_AUDIT), 2)


if __name__ == "__main__":
    unittest.main()
