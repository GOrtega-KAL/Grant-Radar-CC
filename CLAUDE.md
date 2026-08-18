# CLAUDE.md — arranque en frío para esta copia de Grant-Radar

Este archivo es solo un punto de entrada rápido. La fuente de verdad del
proyecto es **`AGENTS.md`** (contexto completo, arquitectura, invariantes,
historial narrativo por secciones fechadas) y **`SUGERENCIAS.MD`**
(evaluación de mejoras y su estado de implementación). Léelos antes de tocar
código; este archivo no los sustituye ni los duplica, y puede quedarse
desactualizado si no se mantiene junto a ellos.

## Qué es esto

Grant-Radar-CC monitoriza subvenciones para Kalfrisa (PYME industrial de
Zaragoza). Backend Python (`Grant-Radar-prueba.py` + paquete `grant_radar/`)
recopila convocatorias de 8 fuentes oficiales, las filtra con reglas
deterministas, evalúa las ambiguas con Claude Haiku 4.5, y publica un JSON
que consume un dashboard estático (`index.html`).

Es una **copia de trabajo** de la carpeta original `Grant-Radar` (carpeta
hermana en `Desktop\Guillermo\`), con su propio repositorio git y su propio
remoto: `https://github.com/GOrtega-KAL/Grant-Radar-CC`.

## Invariantes que no se deben romper

- Nunca leer, mostrar ni copiar `API KEYs.txt` (si existe) ni el contenido
  de `.env` salvo petición expresa y justificada del usuario.
- `.env` (credenciales reales) nunca se lee para mostrarlo, solo para
  operaciones puntuales como `git push` (ver más abajo). Nunca imprimir su
  contenido ni incluirlo en un comando cuyo texto quede en el historial.
- Antes de cualquier `git add`/commit, verificar que no hay patrones de
  clave real (`sk-ant-...`, `ghp_...`, `github_pat_...`) en los archivos
  staged — hay un hook en `.git/hooks/pre-commit` que ya lo hace, pero no
  hay que confiar solo en eso si se edita algo manualmente.
- No modificar `Obsoleto/` ni `Frontend alternativo/` salvo petición expresa.
- `--no-claude` nunca debe llamar a Claude, modificar la caché IA, generar
  JSON ni publicar. Es el modo de validación por defecto tras un cambio de
  código: `poetry run python "Grant-Radar-prueba.py" --no-claude`.
- Después de cualquier cambio en `Grant-Radar-prueba.py` o `grant_radar/`:
  `poetry run python -m py_compile "Grant-Radar-prueba.py"` y
  `poetry run python -m unittest discover -s tests` deben terminar en
  verde antes de dar el cambio por bueno.
- Este equipo tiene una variable de entorno `VIRTUAL_ENV` heredada que
  apunta al `.venv` de la carpeta original `Grant-Radar`, no al de esta
  copia. Antes de cualquier `poetry run`/`poetry install`/`poetry add` en
  PowerShell: `$env:VIRTUAL_ENV = $null` primero, o `poetry` puede ejecutar
  silenciosamente contra el entorno equivocado.

## Estructura actual (18/08/2026)

`Grant-Radar-prueba.py` sigue siendo el punto de entrada — se ejecuta
directamente, no se importa (su nombre con guiones no es válido para
`import`). Recuento verificado con `wc -l`: 9.426 líneas antes de la ronda
de hoy, 9.202 después (la cifra "8.835" de una nota anterior de este
archivo estaba mal calculada — ver AGENTS.md sección 24, nota de
discrepancia). Progresivamente movida a `grant_radar/` (paquete con nombre
importable):

| Módulo | Contiene |
|---|---|
| `parsing_helpers.py` | Fechas y texto puros (sin estado), incl. `_es_titulo_valido` |
| `exclusion_terms.py` (+ `.json`) | Vocabulario de `_hard_out_of_scope()` |
| `tech_taxonomy.py` (+ `.json`) | Categorías técnicas y su clasificación |
| `kalfrisa_profile.py` (+ `.txt`) | Perfil de cliente enviado a Claude |
| `partner_catalog.py` (+ `.json`) | Socios técnicos y su preselección |
| `versions.py` | Versiones que invalidan la caché de análisis |
| `cache.py` | Caché de análisis de Claude (`grant_radar_cache.json`) |
| `deterministic_rules.py` | Salvaguardas deterministas post-modelo |
| `claude_schemas.py` | Esquemas Pydantic de Claude y su validación |
| `audit.py` | `DISCOVERY_AUDIT` y `audit_exclusion()` (usado por las 8 fuentes) |
| `sources/boa_aragon.py` | Conector BOA Aragón (señal secundaria/backup, ver sección 26) |
| `bdns_scope.py` | Filtro de candidatas BDNS: palabras clave + administración autonómica de Aragón |

El descubrimiento automático principal de convocatorias autonómicas de
Aragón ya no es el conector BOA (su scraper en vivo no encuentra nada y su
catálogo estático está vencido), sino un filtro estructurado `nivel1`/
`nivel2` dentro de `fetch_bdns()` (`grant_radar/bdns_scope.py`), con la
ventana de `convocatorias/ultimas` ampliada a ~79 días. Detalle completo de
la investigación y de los números reales de verificación en AGENTS.md
sección 26.

Pendiente: el resto de `sources/` (7 conectores: Horizon, CDTI, IDAE,
BOE/MITECO, ECCP, EEN, BDNS — BOA ya se extrajo como prueba, ver AGENTS.md
sección 25) y `pipeline.py` (`run_pipeline()`). El filtro previo a Claude
(`_bdns_pre_claude_gate()`, `deterministic_prefilter()`, sección 4.1 de
`AGENTS.md`) sigue deliberadamente sin extraer: es la lógica más compleja y
ajustada del proyecto: no encadenarla detrás de otra tarea sin que el
usuario lo pida explícitamente. Detalle completo de cada ronda en
`AGENTS.md`, secciones 21-26, y en `SUGERENCIAS.MD` (3.2/3.3).

## Publicar cambios (git push)

El repositorio remoto usa un token fine-grained guardado en `.env`
(`GITHUB_TOKEN`, permiso "Contents: Read and write" sobre
`Grant-Radar-CC`). Un `git push` normal falla en modo no interactivo. Patrón
usado en esta sesión — lee el token del archivo sin exponerlo en el texto
del comando ni en la salida:

```powershell
$envLines = Get-Content ".env"
$tokenLine = $envLines | Where-Object { $_ -match '^GITHUB_TOKEN=' }
$token = ($tokenLine -replace '^GITHUB_TOKEN=', '').Trim()
$authHeader = "Authorization: Basic " + [Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes("x-access-token:$token"))
git -c http.extraheader="$authHeader" push origin main
$token = $null; $authHeader = $null
```

Como con cualquier `git push`, confirmar con el usuario antes de hacerlo
salvo que ya lo haya pedido explícitamente en el turno actual.
