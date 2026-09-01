# -*- coding: utf-8 -*-
# Pruebas de --source: la selección parcial de fuentes.
#
# La bandera existe para no recorrer las ocho fuentes cuando un cambio toca
# una: la recopilación completa tarda unos quince minutos y ocho ejecuciones
# en un día bastaron el 19/08/2026 para que boe.es respondiera 429
# (AGENTS.md 35; punto 5 del backlog). Medido al añadirla: BOA sola en 13,7 s
# y EEN sola en 81 s, frente a 937 s de las ocho.
#
# El riesgo que estas pruebas cubren no es que la selección falle, sino que se
# DESINCRONICE: si mañana se añade un conector y nadie toca el mapa de alias,
# `--source` seguiría funcionando y en silencio no ofrecería la fuente nueva.
# Por eso la prueba principal lee el propio script y compara.

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Grant-Radar-prueba.py"
CODE = SCRIPT.read_text(encoding="utf-8")
TREE = ast.parse(CODE)


def _source_aliases() -> dict:
    """Lee SOURCE_ALIASES del script sin ejecutarlo entero."""
    for node in TREE.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "SOURCE_ALIASES":
                return ast.literal_eval(node.value)
    raise AssertionError("SOURCE_ALIASES no está definido en el script")


ALIASES = _source_aliases()


class MapaDeAliasTests(unittest.TestCase):

    def test_estan_las_ocho_fuentes(self):
        self.assertEqual(set(ALIASES), {
            "horizon", "bdns", "eccp", "een", "cdti", "idae", "boe", "boa",
        })

    def test_los_alias_se_pueden_teclear_sin_comillas(self):
        # El motivo de que existan: los nombres internos llevan espacios y
        # acentos ("BOE / MITECO", "BOA ARAGÓN").
        for alias in ALIASES:
            self.assertRegex(alias, r"^[a-z]+$", f"alias poco práctico: {alias}")

    def test_idae_selecciona_sus_dos_mitades(self):
        # Fichas y catálogo son un solo conector partido en dos llamadas:
        # comprobar una sin la otra no dice nada.
        self.assertEqual(ALIASES["idae"], ["IDAE", "IDAE CATÁLOGO"])

    def test_ningun_nombre_interno_se_repite_en_dos_alias(self):
        todos = [nombre for nombres in ALIASES.values() for nombre in nombres]
        self.assertEqual(len(todos), len(set(todos)))


class SincroniaConElPipelineTests(unittest.TestCase):
    """El mapa de alias no puede quedarse atrás respecto a los conectores."""

    def _nombres_consultados(self) -> set:
        # Cada fuente del pipeline se pide con `wanted("NOMBRE")`.
        return set(re.findall(r'wanted\(\s*"([^"]+)"\s*\)', CODE))

    def _nombres_recopilados(self) -> set:
        # Y se guarda con `raw_by_source["NOMBRE"] = ...`.
        return set(re.findall(r'raw_by_source\[\s*"([^"]+)"\s*\]', CODE))

    def test_todo_lo_que_el_pipeline_consulta_es_seleccionable(self):
        declarados = {n for nombres in ALIASES.values() for n in nombres}
        faltan = self._nombres_consultados() - declarados
        self.assertFalse(
            faltan,
            f"fuentes del pipeline sin alias en SOURCE_ALIASES: {sorted(faltan)}",
        )

    def test_ningun_alias_apunta_a_una_fuente_inexistente(self):
        declarados = {n for nombres in ALIASES.values() for n in nombres}
        sobran = declarados - self._nombres_consultados()
        self.assertFalse(
            sobran,
            f"alias que no corresponden a ninguna fuente: {sorted(sobran)}",
        )

    def test_toda_fuente_consultada_acaba_en_raw_by_source(self):
        # Si se consulta y no se guarda, la fuente se recopila y se tira.
        self.assertTrue(
            self._nombres_consultados() <= self._nombres_recopilados(),
            "hay fuentes filtradas por wanted() que no llegan a raw_by_source",
        )


class SalvaguardasTests(unittest.TestCase):
    """Las dos condiciones que impiden que una selección parcial haga daño."""

    def _fuente_de(self, nombre: str) -> str:
        for node in ast.walk(TREE):
            if isinstance(node, ast.FunctionDef) and node.name == nombre:
                return ast.get_source_segment(CODE, node) or ""
        raise AssertionError(f"no se encontró {nombre}()")

    def test_source_exige_no_claude(self):
        # Una selección parcial produce un catálogo incompleto; dejarla llegar
        # al análisis publicaría un producto sin fuentes enteras.
        parse_args = self._fuente_de("parse_args")
        self.assertIn("args.source and not args.no_claude", parse_args)
        self.assertIn("--source exige --no-claude", parse_args)

    def test_la_vigilancia_de_recurrentes_se_apaga_en_parcial(self):
        # Con fuentes sin consultar daría por desaparecido todo lo que vive en
        # ellas: alarmas falsas garantizadas (AGENTS.md 46.4).
        pipeline = self._fuente_de("run_pipeline")
        patron = re.compile(
            r"if not partial:\s*\n\s*coverage_items", re.MULTILINE
        )
        self.assertRegex(pipeline, patron)

    def test_el_aviso_de_parcialidad_es_obligatorio(self):
        # Sin él, un "82 vigentes" parcial se compararía con el completo de
        # AGENTS.md 53.4 y parecería una avería donde solo hay una selección.
        pipeline = self._fuente_de("run_pipeline")
        self.assertIn("recopilación PARCIAL", pipeline)
        self.assertIn("NO son comparables", pipeline)

    def test_sin_seleccion_el_comportamiento_es_el_de_siempre(self):
        # `partial` es falso y `wanted()` deja pasar todo: la ejecución
        # completa no cambia de forma por haber añadido la bandera.
        pipeline = self._fuente_de("run_pipeline")
        self.assertIn("partial = bool(selected)", pipeline)
        self.assertIn("return not partial or source_name in selected", pipeline)


class ArranqueDelNavegadorTests(unittest.TestCase):
    """La otra mitad del ahorro: no pagar Chromium si nadie lo necesita."""

    CON_NAVEGADOR = {"IDAE", "BOE / MITECO", "BOA ARAGÓN", "IDAE CATÁLOGO", "CDTI"}
    SIN_NAVEGADOR = {"HORIZON EUROPE", "BDNS", "ECCP", "EEN"}

    def test_las_cuatro_fuentes_http_no_arrastran_chromium(self):
        declarados = {n for nombres in ALIASES.values() for n in nombres}
        self.assertEqual(
            self.CON_NAVEGADOR | self.SIN_NAVEGADOR, declarados,
            "el reparto entre fuentes con y sin navegador no cubre las ocho",
        )

    def test_el_pipeline_decide_el_navegador_por_la_seleccion(self):
        for node in ast.walk(TREE):
            if isinstance(node, ast.FunctionDef) and node.name == "run_pipeline":
                pipeline = ast.get_source_segment(CODE, node) or ""
                break
        else:
            self.fail("no se encontró run_pipeline()")
        self.assertIn("browser_sources = [", pipeline)
        self.assertIn("if browser_sources:", pipeline)
        # Y las cuatro de HTTP puro se piden fuera del bloque del navegador.
        antes, _, despues = pipeline.partition("if browser_sources:")
        for fuente in self.SIN_NAVEGADOR:
            self.assertIn(f'wanted("{fuente}")', antes,
                          f"{fuente} no debería depender de Chromium")


if __name__ == "__main__":
    unittest.main()
