# Pruebas de grant_radar/cache.py con import estándar (sin runpy).
#
# No repite la cobertura de test_grant_radar.py (migración de caché plana,
# reindexado tras normalización, invalidación por versión...); aquí se
# confirma que el módulo funciona de forma aislada, con un archivo de caché
# temporal propio, sin tocar grant_radar_data/.

import json
import tempfile
import unittest
from pathlib import Path

from grant_radar.cache import (
    analysis_is_usable,
    cache_key,
    cache_load,
    cache_save,
    filter_usable_cache,
    source_hash,
)


def _usable_analysis(**overrides):
    # decision/eligibility no los exige analysis_is_usable(), pero sí los lee
    # sin valor por defecto apply_current_deterministic_rules() (los pone
    # siempre el esquema CallEvaluation real); se incluyen aquí por lo mismo.
    base = {
        "fit_score": 70, "actionability_score": 60, "confidence": 80,
        "priority": "high", "resumen": "Resumen de prueba", "accion": "Actuar",
        "dimensiones": [], "call_facts": {},
        "decision": "watch", "eligibility": "unknown",
    }
    base.update(overrides)
    return base


class HashingTests(unittest.TestCase):
    def test_source_hash_is_stable_for_identical_content(self):
        conv = {"source": "BDNS", "title": "Convocatoria", "url": "https://example.test"}
        self.assertEqual(source_hash(conv), source_hash(dict(conv)))

    def test_source_hash_changes_when_description_changes(self):
        conv = {"source": "BDNS", "title": "Convocatoria", "description": "A"}
        other = {**conv, "description": "B"}
        self.assertNotEqual(source_hash(conv), source_hash(other))

    def test_cache_key_is_a_deterministic_sha256(self):
        conv = {"source": "BDNS", "title": "Convocatoria"}
        key = cache_key(conv)
        self.assertEqual(len(key), 64)
        self.assertEqual(key, cache_key(dict(conv)))


class UsabilityTests(unittest.TestCase):
    def test_pending_analysis_placeholder_is_not_usable(self):
        self.assertFalse(analysis_is_usable({"resumen": "Pendiente de análisis."}))

    def test_complete_analysis_is_usable(self):
        self.assertTrue(analysis_is_usable(_usable_analysis()))

    def test_filter_usable_cache_drops_incomplete_entries_without_raising(self):
        entries = {
            "a": {"analysis": _usable_analysis(), "raw_document": {"source": "BDNS", "title": "X"}},
            "b": {"analysis": {"resumen": ""}, "raw_document": {"source": "BDNS", "title": "Y"}},
        }
        usable = filter_usable_cache(entries)
        self.assertEqual(list(usable), ["a"])


class CacheFileRoundTripTests(unittest.TestCase):
    def test_save_then_load_returns_the_same_usable_entries(self):
        conv = {"source": "BDNS", "title": "Convocatoria de prueba"}
        entries = {
            cache_key(conv): {
                "analysis": _usable_analysis(),
                "raw_document": conv,
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = str(Path(tmp) / "cache.json")
            cache_save(entries, cache_file)
            loaded = cache_load(cache_file)
        self.assertEqual(list(loaded), list(entries))

    def test_load_missing_file_returns_empty_cache_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = str(Path(tmp) / "no-existe.json")
            self.assertEqual(cache_load(cache_file), {})

    def test_version_mismatch_invalidates_the_whole_cache(self):
        conv = {"source": "BDNS", "title": "Convocatoria"}
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = str(Path(tmp) / "cache.json")
            payload = {
                "_meta": {"schema_version": 999999},  # versión imposible
                "entries": {cache_key(conv): {"analysis": _usable_analysis(), "raw_document": conv}},
            }
            Path(cache_file).write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(cache_load(cache_file), {})


if __name__ == "__main__":
    unittest.main()
