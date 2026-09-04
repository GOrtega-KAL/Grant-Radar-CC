# -*- coding: utf-8 -*-
# Pruebas del cableado de --batch-poll en el script.
#
# El sondeo existe para poder MIRAR sin comprometerse a gastar. Antes de él, la
# unica forma de saber si un lote habia terminado era --batch-collect, que si la
# fase 1 estaba lista enviaba la fase 2 y pagaba (AGENTS.md 64.2).
#
# Esa propiedad —«sondear no cuesta»— no la garantiza ninguna prueba del modulo,
# porque vive en la funcion del script. Aqui se fija leyendo su codigo: si
# alguien anade una llamada que gasta dentro de run_batch_poll(), esto falla.
# Es la misma tecnica que test_grant_radar_source_selection.py.

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = (ROOT / "Grant-Radar-prueba.py").read_text(encoding="utf-8")
TREE = ast.parse(CODE)
BAT = (ROOT / "scripts" / "Grant-Radar diario.bat").read_text(encoding="utf-8")


def _funcion(nombre: str) -> str:
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and node.name == nombre:
            return ast.get_source_segment(CODE, node) or ""
    raise AssertionError(f"{nombre} no está definida en el script")


class BatchPollIsFreeTests(unittest.TestCase):
    """Lo que convierte al sondeo en algo que se puede automatizar."""

    # Todo lo que cuesta dinero. `poll_batch` y `list_recent_batches` no están:
    # son `retrieve` y `list`, sin tokens.
    QUE_GASTA = (
        "collect_batch", "submit_batch", "analyze_with_claude",
        "store_phase1_results", "save_batch_state", "clear_batch_state",
    )

    def test_the_poll_never_calls_anything_that_spends(self):
        cuerpo = _funcion("run_batch_poll")
        for llamada in self.QUE_GASTA:
            self.assertNotIn(
                llamada, cuerpo,
                f"run_batch_poll() no puede llamar a {llamada}: el sondeo tiene "
                "que poder ejecutarse a diario sin gastar ni decidir nada",
            )

    def test_the_poll_does_ask_anthropic_and_not_only_the_local_file(self):
        """Si solo leyera el archivo local seria --batch-status otra vez.

        El archivo esta en .gitignore: si se pierde, un sondeo que se fiara de
        el diria «no hay nada» con trabajo pagado esperando.
        """
        cuerpo = _funcion("run_batch_poll")
        self.assertIn("poll_batch(", cuerpo)
        self.assertIn("list_recent_batches(", cuerpo)

    def test_the_poll_never_fails_the_daily_run(self):
        """Va dentro de un .bat desatendido: no puede romper la recopilacion."""
        cuerpo = _funcion("run_batch_poll")
        self.assertIn("return 0", cuerpo)
        self.assertNotIn("return 1", cuerpo)
        self.assertIn("except Exception", cuerpo)


class BatchPollWiringTests(unittest.TestCase):
    def test_the_flag_is_declared(self):
        self.assertIn('"--batch-poll"', _funcion("parse_args"))

    def test_it_is_a_batch_mode_and_excludes_the_others(self):
        """Sin esto, --batch-poll --batch-collect sondearia y ademas pagaria."""
        parse = _funcion("parse_args")
        self.assertIn("args.batch_poll", parse)
        modos = parse[parse.index("modos_lote = ["):]
        self.assertIn("args.batch_poll", modos[:modos.index("]")])

    def test_it_is_dispatched_before_doing_anything_else(self):
        self.assertIn("if args.batch_poll:", CODE)
        self.assertIn("sys.exit(run_batch_poll())", CODE)


class CollectWithoutSubmittingTests(unittest.TestCase):
    """La separacion del 04/09/2026 entre recoger (gratis) y enviar (paga).

    Estaban soldadas: la rama de la fase 1 recogia los hechos y en la linea
    siguiente enviaba la fase 2. Mientras fue asi, la recogida no podia entrar
    en un .bat diario sin arriesgarse a lanzar una peticion de pago.
    """

    def test_submitting_is_guarded_by_the_flag(self):
        cuerpo = _funcion("run_batch_collect")
        self.assertIn("allow_submit", cuerpo)
        antes = cuerpo.index("if not allow_submit")
        self.assertLess(
            antes, cuerpo.index("submit_batch("),
            "la guarda tiene que ir ANTES del envio, no despues",
        )

    def test_the_paid_facts_are_saved_before_deciding(self):
        """Si el proceso muriera entre recoger y decidir, se perderian.

        Los hechos de la fase 1 ya estan pagados cuando llegan: se guardan
        primero y se decide despues.
        """
        cuerpo = _funcion("run_batch_collect")
        self.assertLess(
            cuerpo.index("store_phase1_results("),
            cuerpo.index("if not allow_submit"),
        )

    def test_the_flag_requires_batch_collect(self):
        """Sola no significa nada, y en silencio no haria lo que parece."""
        parse = _funcion("parse_args")
        self.assertIn("--no-submit solo tiene sentido junto a --batch-collect", parse)

    def test_the_default_still_submits(self):
        """La ejecucion manual autorizada no cambia de comportamiento."""
        self.assertIn("def run_batch_collect(allow_submit: bool = True)", CODE)
        self.assertIn("allow_submit=not args.no_submit", CODE)


class DailyBatFileTests(unittest.TestCase):
    """La red diaria que pidio el usuario el 04/09/2026."""

    def test_the_daily_script_polls(self):
        self.assertIn("--batch-poll", BAT)

    def test_the_daily_script_still_never_pays(self):
        """El .bat es de coste cero por contrato. Ninguna bandera que gaste."""
        for bandera in ("--max-claude", "--hold-pilot", "--force-reanalysis"):
            self.assertNotIn(bandera, BAT)
        self.assertIn("--no-claude", BAT)

    def test_the_daily_script_collects_but_never_submits(self):
        """Lo que pidio el usuario el 04/09: recoger lo pagado, no lanzar nada.

        `--batch-collect` a secas envia la fase 2 si la 1 acaba de terminar, y
        eso cuesta dinero. En el .bat tiene que ir SIEMPRE con `--no-submit`.
        """
        invocaciones = [
            linea.strip() for linea in BAT.splitlines()
            if linea.strip().startswith('"%PYTHON%"')
        ]
        recogidas = [l for l in invocaciones if "--batch-collect" in l]
        self.assertTrue(recogidas, "el .bat diario tiene que recoger lo pagado")
        for linea in recogidas:
            self.assertIn(
                "--no-submit", linea,
                "--batch-collect sin --no-submit enviaria la fase 2 y pagaria",
            )

    def test_the_daily_script_never_opens_a_batch(self):
        """`--batch` a secas recopila y ENVIA la fase 1. Nunca desde aqui."""
        for linea in BAT.splitlines():
            if not linea.strip().startswith('"%PYTHON%"'):
                continue
            self.assertNotIn(
                "--batch ", linea + " ",
                "el .bat no puede abrir un lote: eso es una peticion de pago",
            )

    def test_the_poll_runs_before_the_long_collection(self):
        """La recopilacion tarda 11-15 min y el usuario se va de la ventana.

        Si el aviso de «lote terminado sin recoger» saliera despues, no lo
        leeria nadie.

        Se miran las INVOCACIONES, no el texto: la cabecera del .bat menciona
        las dos banderas al explicarse, y comparar posiciones en el texto entero
        mediria el orden de los comentarios.
        """
        invocaciones = [
            linea.strip() for linea in BAT.splitlines()
            if linea.strip().startswith('"%PYTHON%"')
        ]
        self.assertTrue(invocaciones, "el .bat no invoca al interprete")
        primera = invocaciones[0]
        self.assertIn("--batch-poll", primera)
        self.assertTrue(
            any("--no-claude" in linea for linea in invocaciones[1:]),
            "la recopilacion tiene que ir despues del sondeo",
        )


if __name__ == "__main__":
    unittest.main()
