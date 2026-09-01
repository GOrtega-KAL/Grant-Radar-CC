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
import importlib
import runpy
import unittest
from textwrap import dedent
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Grant-Radar-prueba.py"
PACKAGE = ROOT / "grant_radar"


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
            if isinstance(child, ast.Lambda):
                # Una lambda sí es parte de esta expresión: sus parámetros
                # deben verse aquí (`min(x, key=lambda e: f(e))`).
                for arg in (*child.args.posonlyargs, *child.args.args,
                            *child.args.kwonlyargs):
                    names.add(arg.arg)
                for extra in (child.args.vararg, child.args.kwarg):
                    if extra is not None:
                        names.add(extra.arg)
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
    """Recorre los ámbitos encadenando los nombres visibles en cada nivel.

    Comprueba **todo** nombre leído, no solo el de una llamada directa. La
    primera versión solo miraba `ast.Call` con `func` de tipo `ast.Name`, y por
    eso dejó pasar `statistics.median(...)` al extraer el conector ECCP: ahí el
    nombre que falta, `statistics`, es el objeto de un atributo, no el de la
    llamada. Lo cazó la ejecución `--no-claude`, ya en producción (AGENTS.md
    sección 35).
    """
    scope = visible | _own_names(node)
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _missing_called_names(child, scope, missing)
            continue
        for inner in ast.walk(child):
            if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load):
                if inner.id not in scope:
                    owner = getattr(node, "name", "<módulo>")
                    missing.setdefault(inner.id, []).append(f"{owner}:{inner.lineno}")
        for grandchild in ast.iter_child_nodes(child):
            if isinstance(grandchild, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                _missing_called_names(grandchild, scope, missing)


class DetectorSanityTests(unittest.TestCase):
    """El detector no debe pasar en vacío: se prueba contra código sintético."""

    def _missing(self, code: str) -> dict:
        missing = {}
        _missing_called_names(
            ast.parse(dedent(code)), set(dir(builtins)), missing
        )
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

    def test_detects_a_missing_module_used_through_an_attribute(self):
        # El hueco que dejó pasar `statistics.median(...)` en el conector ECCP:
        # el nombre que falta es el objeto del atributo, no el de la llamada.
        self.assertEqual(
            self._missing("""
                def f(valores):
                    return statistics.median(valores)
            """),
            {"statistics": ["f:3"]},
        )

    def test_a_lambda_parameter_is_not_reported(self):
        self.assertEqual(
            self._missing("""
                def f(opciones):
                    return min(opciones, key=lambda e: len(e))
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
            "fetch_bdns", "fetch_boe", "fetch_cdti", "fetch_eccp",
            "fetch_een_funding", "fetch_horizon_europe", "fetch_idae",
            "fetch_idae_catalog",
        ):
            with self.subTest(name=name):
                self.assertTrue(
                    callable(self.script_globals.get(name)),
                    f"{name} no está disponible en el script principal",
                )


class PackageModuleNamesTests(unittest.TestCase):
    """La misma comprobación, aplicada a cada módulo de grant_radar/.

    Al mover un bloque al paquete es fácil llevarse una función y dejar atrás
    el import del helper que usa. El módulo se importa igual (Python no
    resuelve nombres hasta ejecutarlos) y el fallo solo aparece cuando algo
    llama a esa función. Pasó de verdad al extraer `bdns_fields.py`, que se
    quedó sin `_fold_text`: la suite lo detectó, pero como 27 errores en
    pruebas de otra cosa. Esta comprobación lo señala en el sitio exacto.
    """

    def test_every_module_resolves_the_names_it_calls(self):
        problemas = {}
        for archivo in sorted(PACKAGE.rglob("*.py")):
            if archivo.name == "__init__.py":
                continue
            nombre = ".".join(archivo.relative_to(ROOT).with_suffix("").parts)
            module = importlib.import_module(nombre)
            visible = set(vars(module)) | set(dir(builtins))
            missing = {}
            _missing_called_names(
                ast.parse(archivo.read_text(encoding="utf-8")), visible, missing
            )
            if missing:
                problemas[nombre] = missing
        self.assertEqual(
            problemas, {},
            "Un módulo llama a nombres que no tiene: falta un import tras mover código.",
        )


if __name__ == "__main__":
    unittest.main()
