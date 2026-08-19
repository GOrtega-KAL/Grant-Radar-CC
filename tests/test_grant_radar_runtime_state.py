# Pruebas de grant_radar/runtime_state.py con import estándar (sin runpy).
#
# Lo que importa de este módulo no es su lógica —no tiene— sino su contrato:
# quien lo importa recibe el MISMO objeto mutable, no una copia. Si alguien
# reasignara uno de los cuatro contenedores en vez de mutarlo, las fuentes y
# run_pipeline() dejarían de verse entre sí sin que fallara nada visible.

import unittest

from grant_radar import runtime_state
from grant_radar.runtime_state import (
    COVERAGE_WATCH_RESULTS,
    IDENTITY_LANDINGS,
    RUN_DIAGNOSTICS,
    SOURCE_RUNTIME_METADATA,
)


class SharedRuntimeStateTests(unittest.TestCase):
    def setUp(self):
        for container in (
            SOURCE_RUNTIME_METADATA, IDENTITY_LANDINGS,
            COVERAGE_WATCH_RESULTS, RUN_DIAGNOSTICS,
        ):
            container.clear()

    tearDown = setUp

    def test_importing_a_name_binds_the_same_object(self):
        self.assertIs(SOURCE_RUNTIME_METADATA, runtime_state.SOURCE_RUNTIME_METADATA)
        self.assertIs(IDENTITY_LANDINGS, runtime_state.IDENTITY_LANDINGS)
        self.assertIs(COVERAGE_WATCH_RESULTS, runtime_state.COVERAGE_WATCH_RESULTS)
        self.assertIs(RUN_DIAGNOSTICS, runtime_state.RUN_DIAGNOSTICS)

    def test_a_mutation_through_one_binding_is_visible_in_the_other(self):
        SOURCE_RUNTIME_METADATA["BDNS"] = {"inventory_unique": 4_475}
        IDENTITY_LANDINGS.append({"source": "IDAE", "url": "https://example.test"})
        RUN_DIAGNOSTICS["web_source_health"] = {"CDTI": {"status": "healthy"}}
        COVERAGE_WATCH_RESULTS.append({"key": "programa_innovae", "found": True})

        self.assertEqual(
            runtime_state.SOURCE_RUNTIME_METADATA["BDNS"]["inventory_unique"], 4_475
        )
        self.assertEqual(len(runtime_state.IDENTITY_LANDINGS), 1)
        self.assertEqual(
            runtime_state.RUN_DIAGNOSTICS["web_source_health"]["CDTI"]["status"],
            "healthy",
        )
        self.assertEqual(len(runtime_state.COVERAGE_WATCH_RESULTS), 1)

    def test_clear_empties_the_shared_object_for_everyone(self):
        # Es lo que hace run_pipeline() al arrancar cada ejecución.
        SOURCE_RUNTIME_METADATA["ECCP"] = {"inventory_count": 6}
        runtime_state.SOURCE_RUNTIME_METADATA.clear()
        self.assertEqual(SOURCE_RUNTIME_METADATA, {})

    def test_the_four_containers_start_with_the_expected_types(self):
        self.assertIsInstance(SOURCE_RUNTIME_METADATA, dict)
        self.assertIsInstance(RUN_DIAGNOSTICS, dict)
        self.assertIsInstance(IDENTITY_LANDINGS, list)
        self.assertIsInstance(COVERAGE_WATCH_RESULTS, list)


if __name__ == "__main__":
    unittest.main()
