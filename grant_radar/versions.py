# versions.py — versiones que identifican un análisis en caché
#
# Estas constantes se leen tanto en Grant-Radar-prueba.py (prompts, informes,
# barrera de coste) como en grant_radar/cache.py (para invalidar la caché al
# cambiar). Viven en un módulo propio, sin lógica, precisamente para que
# ambos las compartan sin que uno tenga que importar del otro. Subir
# cualquiera de estos valores invalida de forma intencionada los análisis
# anteriores (ver AGENTS.md, sección 5).

# Incrementar esta versión cuando cambie el criterio o el prompt de análisis.
PROFILE_VERSION = "kalfrisa-2026-08-v5-simulation-line"
EXTRACTOR_VERSION = "facts-2026-08-v7-official-structured-data"
EVALUATOR_VERSION = "fit-2026-08-v8-no-presumption"
PARTNER_CATALOG_VERSION = "2026-07-v2"
ANALYSIS_PROMPT_VERSION = "2026-08-v12-no-presumption"
CACHE_SCHEMA_VERSION = 3
CLAUDE_MODEL = "claude-haiku-4-5"  # Haiku 4.5 — $1/$5 por millón de tokens
