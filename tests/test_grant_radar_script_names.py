# Red de seguridad para la división en módulos: comprueba que Grant-Radar-prueba.py
# no llama a ningún nombre global que ya no exista en él.
#
# Motivo: al extraer un bloque a `grant_radar/`, es fácil olvidarse de
# reimportar en el script alguna función que se seguía usando desde otro punto.
# `py_compile` no lo detecta (no resuelve nombres) y `--no-claude` tampoco si la
# ruta afectada solo se ejecuta con Claude. Peor aún: el bloque de fusión de
# `APP` de tests/test_grant_radar.py inyecta los nombres que faltan en los
# propios globals del script —`runpy.run_path()` devuelve ese diccionario—, así
# que repara el fallo justo antes de probarlo.
#
# Por eso este archivo hace su propio `runpy.run_path()`: unos globals limpios,
# sin la fusión. Así encontró 14 funciones de `deterministic_rules` que
# `_build_compatible_analysis()` llamaba sin que el script las importara desde
# la ronda de la sección 23 de AGENTS.md.

import ast
import builtins
import runpy
import unittest
from textwrap import dedent
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Grant-Radar-prueba.py"


def _own_names(node: ast.AST) -> set[str]:
    """Nombres que este ámbito define por sí mismo.

    No desciende al cuerpo de las funciones anidadas —esos son otro ámbito—,
    pero sí registra su nombre, para que dos anidadas hermanas se vean entre
    sí igual que en tiempo de ejecución.
    """
    names = {getattr(node, "name", "")}
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        args = node.args
        for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
            names.add(arg.arg)
        for extra in (args.vararg, args.kwarg):
            if extra is not None:
                names.add(extra.arg)

    def visit(current: ast.AST) -> None:
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(child.name)
                continue  # su cuerpo es otro ámbito
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                names.add(child.id)
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                for alias in child.names:
                    names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(child, ast.ExceptHandler) and child.name:
                names.add(child.name)
            visit(child)

    visit(node)
    names.discard("")
    return names


def _missing_called_names(node: ast.AST, visible: set[str], missing: dict) -> None:
    """Recorre los ámbitos encadenando los nombres visibles en cada nivel."""
    scope = visible | _own_names(node)
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _missing_called_names(child, scope, missing)
            continue
        for inner in ast.walk(child):
            if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                name = inner.func.id
                if name not in scope:
                    owner = getattr(node, "name", "<módulo>")
                    missing.setdefault(name, []).append(f"{owner}:{inner.lineno}")
        for grandchild in ast.iter_child_nodes(child):
            if isinstance(grandchild, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                _missing_called_names(grandchild, scope, missing)


class DetectorSanityTests(unittest.TestCase):
    """El detector no debe pasar en vacío: se prueba contra código sintético."""

    def _missing(self, code: str) -> dict:
        missing = {}
        _missing_called_names(ast.parse(dedent(code)), {"print", "len"}, missing)
        return missing

    def test_detects_a_call_to_a_name_that_does_not_exist(self):
        self.assertEqual(
            self._missing("""
                def f(x):
                    return _extraida(x)
            """),
            {"_extraida": ["f:3"]},
        )

    def test_a_name_defined_at_module_level_is_not_reported(self):
        self.assertEqual(
            self._missing("""
                def _extraida(x):
                    return x

                def f(x):
                    return _extraida(x)
            """),
            {},
        )

    def test_a_parameter_of_a_nested_function_is_not_reported(self):
        self.assertEqual(
            self._missing("""
                def outer():
                    def inner(callback):
                        return callback()
                    return inner
            """),
            {},
        )

    def test_two_sibling_nested_functions_see_each_other(self):
        self.assertEqual(
            self._missing("""
                def outer():
                    def a():
                        return 1

                    def b():
                        return a()
                    return b
            """),
            {},
        )

    def test_a_recursive_nested_function_is_not_reported(self):
        self.assertEqual(
            self._missing("""
                def outer(v):
                    def walk(node):
                        return walk(node)
                    return walk(v)
            """),
            {},
        )

    def test_a_dangling_call_inside_a_nested_function_is_still_detected(self):
        self.assertEqual(
            self._missing("""
                def outer():
                    def inner():
                        return _movida()
                    return inner
            """),
            {"_movida": ["inner:4"]},
        )


class ScriptGlobalNamesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Globals limpios, sin el bloque de fusión de test_grant_radar.py.
        cls.script_globals = runpy.run_path(str(SCRIPT))
        cls.tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))

    def test_every_called_global_name_exists_in_the_script(self):
        visible = set(self.script_globals) | set(dir(builtins))
        missing = {}
        _missing_called_names(self.tree, visible, missing)
        self.assertEqual(
            missing, {},
            "El script llama a nombres que no existen en sus globals; "
            "probablemente falte reimportar algo extraído a grant_radar/.",
        )

    def test_the_public_entry_points_of_every_extracted_source_are_reachable(self):
        for name in (
            "fetch_bdns", "fetch_boa", "fetch_boe", "fetch_cdti", "fetch_eccp",
            "fetch_een_funding", "fetch_horizon_europe", "fetch_idae",
            "fetch_idae_catalog",
        ):
            with self.subTest(name=name):
                self.assertTrue(
                    callable(self.script_globals.get(name)),
                    f"{name} no está disponible en el script principal",
                )


if __name__ == "__main__":
    unittest.main()
