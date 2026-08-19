# runtime_state.py — estado compartido de una ejecución del pipeline
#
# Cuatro contenedores mutables que las fuentes rellenan durante la
# recopilación y que `run_pipeline()` consume después para la auditoría, el
# panel de fuentes y los diagnósticos. No guardan decisiones de negocio: son
# el sitio donde cada conector deja "qué encontré y en qué estado", sin tener
# que devolverlo por la cadena de llamadas.
#
# Mismo patrón que `grant_radar/audit.py` (DISCOVERY_AUDIT): quien los importa
# recibe el MISMO objeto, no una copia, así que `.clear()`, `.append()` o
# `d[clave] = valor` desde cualquier módulo son visibles para todos los demás.
# Por eso nunca deben reasignarse (`SOURCE_RUNTIME_METADATA = {}` dentro de una
# función rompería el enlace): para vaciarlos, `.clear()`, como ya hace
# `run_pipeline()` al empezar cada ejecución.
#
# Sin dependencias: ni caché, ni reglas, ni Claude, ni red.

# Volumen y salud declarados por cada fuente, indexados por su nombre público
# ("BDNS", "HORIZON EUROPE", "BOE / MITECO"...). Alimenta build_source_status()
# y, con ello, el panel "Fuentes monitorizadas" del dashboard.
SOURCE_RUNTIME_METADATA: dict[str, dict] = {}

# Landings oficiales descubiertas al vuelo (hoy solo IDAE) que sirven para
# identificar una convocatoria aunque no lleguen como candidata propia.
IDENTITY_LANDINGS: list[dict] = []

# Resultado de la vigilancia de programas recurrentes conocidos: avisa si un
# programa que aparecía en ejecuciones anteriores deja de encontrarse.
COVERAGE_WATCH_RESULTS: list[dict] = []

# Diagnósticos por etapa de la ejecución (salud web, auditorías de scraping,
# recuentos del prefiltro, previsión y barrera de coste de Claude...). Se
# serializa dentro de la auditoría al terminar.
RUN_DIAGNOSTICS: dict[str, object] = {}
