# CLAUDE.md — arranque en frío para esta copia de Grant-Radar

Este archivo es solo un punto de entrada rápido. La fuente de verdad del
proyecto es **`AGENTS.md`** (contexto completo, arquitectura, invariantes,
historial narrativo por secciones fechadas) y **`SUGERENCIAS.MD`**
(evaluación de mejoras y su estado de implementación). Léelos antes de tocar
código; este archivo no los sustituye ni los duplica, y puede quedarse
desactualizado si no se mantiene junto a ellos.

> **Estado a 20/08/2026:** hay una ronda de calidad del dato aplicada y
> **verificada solo con pruebas** (AGENTS.md sección 40): falta repetir
> `--no-claude` con red, porque el equipo la perdió durante la verificación.
> Hasta que esos números coincidan con los de referencia, no lanzar nada de pago.
>
> **Para retomar el trabajo, empezar por `AGENTS.md` sección 39**: cierra la
> sesión del 19/08/2026, resume las nueve rondas de modularización de ese día,
> el siguiente paso ya medido, lo que está pendiente y **los números de
> referencia con los que se verifica cualquier cambio**. La sección 36 reúne
> los hallazgos abiertos y las propuestas.

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
- Después de cualquier cambio en `Grant-Radar-prueba.py` o `grant_radar/`,
  en este orden (el detalle y los números de referencia, en AGENTS.md 39.5):
  1. `poetry run python -m unittest tests.test_grant_radar_script_names`
     —un segundo, señala módulo y nombre exactos si falta un import;
  2. `poetry run python -m py_compile "Grant-Radar-prueba.py"`;
  3. `poetry run python -m unittest discover -s tests` —381 pruebas;
  4. `poetry run python "Grant-Radar-prueba.py" --no-claude` al cerrar la
     ronda, comparando contra los números de referencia.
- Al extraer código a `grant_radar/`, comprobar que el script principal
  reimporta todo lo que sigue usando. `py_compile` no resuelve nombres y
  `--no-claude` no recorre la ruta de análisis, así que un `NameError` puede
  quedar latente hasta la primera ejecución de pago: pasó de verdad con
  catorce funciones de `deterministic_rules` (AGENTS.md sección 29).
  `tests/test_grant_radar_script_names.py` vigila justamente eso.
- **Llamar a Claude/Haiku por API requiere SIEMPRE autorización expresa del
  usuario**, sin excepción, porque cuesta dinero real. En cambio, el usuario
  autorizó el 19/08/2026 a ejecutar `--no-claude` sin preguntar (tarda 10-15
  min, no consume tokens) y a hacer `commit` y `push` a `Grant-Radar-CC` sin
  pedir permiso, por ser esta una carpeta paralela de iteración.
- Las ejecuciones `--no-claude` son gratis en tokens pero **no para las
  fuentes públicas**: el 19/08, tras ocho ejecuciones en un día, `boe.es`
  respondió con `HTTP 429`. Espaciarlas cuando se encadenen varias rondas.
- Al cerrar cada ronda de trabajo, dejar `AGENTS.md`, `CLAUDE.md` y
  `SUGERENCIAS.MD` al día para que otra sesión pueda arrancar en frío. Es
  requisito del usuario, no una cortesía.
- Este equipo tiene una variable de entorno `VIRTUAL_ENV` heredada que
  apunta al `.venv` de la carpeta original `Grant-Radar`, no al de esta
  copia. Antes de cualquier `poetry run`/`poetry install`/`poetry add` en
  PowerShell: `$env:VIRTUAL_ENV = $null` primero, o `poetry` puede ejecutar
  silenciosamente contra el entorno equivocado.

## Estructura actual (19/08/2026)

`Grant-Radar-prueba.py` sigue siendo el punto de entrada — se ejecuta
directamente, no se importa (su nombre con guiones no es válido para
`import`). Recuento verificado con `wc -l`: 3.842 líneas
en el script y 8.847 en los 34 módulos del paquete —más del doble de código en
el paquete que en el script—, tras las nueve rondas del 19/08/2026
(el script tenía 9.199 al empezar el día; la cifra
"8.835" de una nota anterior de este archivo estaba mal calculada — ver
AGENTS.md sección 24, nota de discrepancia). Progresivamente movida a `grant_radar/` (paquete con nombre
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
| `runtime_state.py` | Estado compartido de la ejecución (metadatos por fuente, diagnósticos, landings, coverage watch) |
| `http_client.py` | `_http_get()` con reintentos y límite de bytes + `_is_safe_public_https_url()` |
| `source_health.py` | `assess_web_inventory_health()`: control común de salud de inventarios web |
| `call_text.py` | Texto de convocatoria compartido: mecanismo, identificador oficial, deadline, presupuesto, enlaces externos |
| `sources/horizon_europe.py` | Conector Horizon Europe (SEDIA Search API) |
| `sources/een.py` | Conector EEN: noticias de financiación y perfiles I+D con call verificable |
| `browser.py` | `PlaywrightBrowser`: sesión Chromium única de las fuentes sin API |
| `dedup.py` | Identidad de programa, rol documental y consolidación de duplicados |
| `sources/idae.py` | Conector IDAE: fichas de ayudas y catálogo por ámbito |
| `sources/boe_miteco.py` | Conector BOE/MITECO: extractos de convocatoria en ayudas.php |
| `bdns_fields.py` | Lectura de campos de la API BDNS, compartida con la matriz de reglas |
| `sources/bdns.py` | Conector BDNS/SNPSAP: inventario transversal y detalle de convocatorias |
| `documents.py` | Documentos oficiales: descarga, extracción de texto y su caché |
| `sources/cdti.py` | Conector CDTI: calendario oficial con Chromium + catálogo curado |
| `sources/eccp.py` | Conector ECCP: calls y rastreo acotado de webs de proyectos |
| `public_output.py` (actualizado) | Publica `objeto_y_actuaciones`; `post_procesar_texto()` ya solo toca acrónimos |
| `public_output.py` | Registro público del dashboard, estadísticas, estado por fuente y URLs |
| `publishing.py` | Subida a GitHub Pages (credenciales como parámetros, nunca leídas aquí) |
| `claude_selection.py` | Qué se manda a Claude y la barrera de coste previa |
| `coverage_watch.py` | Vigilancia de programas recurrentes conocidos |
| `hold_quotes.py` | Validación de que una cita prueba la conclusión de un hold |
| `claude_usage.py` | Recuento de tokens y coste, incluidos los intentos fallidos |
| `hold_evidence.py` | Documentos oficiales de un hold BDNS y su caché documental |

Lo que se ha descubierto y aún no se ha hecho —hallazgos abiertos y propuestas,
con su motivo y lo que costaría retomarlos— está reunido en **AGENTS.md
sección 36**, para no tener que releer todas las rondas. Consultarla antes de
proponer trabajo nuevo, y actualizarla al cerrar cualquiera de sus puntos.

Comportamientos concretos ya verificados con código (identidad de programa,
extracción de presupuesto, bloqueo por ámbito del navegador, y por qué el
patrón `__globals__` de los tests sobrevive a las extracciones) están
recogidos en AGENTS.md sección 31: consultarla antes de deducirlos otra vez
leyendo expresiones regulares.

El descubrimiento automático principal de convocatorias autonómicas de
Aragón ya no es el conector BOA (su scraper en vivo no encuentra nada y su
catálogo estático está vencido), sino un filtro estructurado `nivel1`/
`nivel2` dentro de `fetch_bdns()` (`grant_radar/bdns_scope.py`), con la
ventana de `convocatorias/ultimas` ampliada a ~79 días. Detalle completo de
la investigación y de los números reales de verificación en AGENTS.md
sección 26.

Pendiente, en el orden que tiene sentido moverlo (detalle en AGENTS.md
secciones 37 y 38): `save_discovery_audit()` (encaja en `audit.py`), la capa de
análisis con Haiku (~545 líneas, atada a `_hard_out_of_scope()`), la segunda
mitad del dominio de holds (resolución determinista, piloto y replay, que
necesitan reglas y Claude), la matriz de reglas (sesión dedicada) y, por
último, `run_pipeline()`.
**Los ocho conectores ya están en `grant_radar/sources/`.** ECCP recibe el
prefiltro como parámetro (`is_relevant_enough`) para no depender de las reglas:
quien lo llame debe pasárselo.

Medido antes de intentarlo: extraer `run_pipeline()` hoy arrastraría 64 de las
68 funciones restantes. El orquestador va el último, no el siguiente. El plan por etapas y el orden de dependencias están en
AGENTS.md sección 28. El filtro previo a Claude
(`_bdns_pre_claude_gate()`, `deterministic_prefilter()`, sección 4.1 de
`AGENTS.md`) sigue deliberadamente sin extraer: es la lógica más compleja y
ajustada del proyecto; no encadenarla detrás de otra tarea sin que el usuario
lo pida explícitamente. Es también lo único que le falta a ECCP, por eso ese
conector va el último. Detalle completo de cada ronda en `AGENTS.md`,
secciones 21-32, y en `SUGERENCIAS.MD` (3.2/3.3).

**Auditoría del embudo determinista (18/08/2026, sin cambios de código):**
tras ampliar la ventana de BDNS, se comprobó con datos reales si
`_bdns_pre_claude_gate()` necesitaba endurecerse. No: descarta el 91,9 % de
las candidatas sin llamar a Claude y sin revisión manual; el resto es
ambiguo de verdad, no un filtro laxo. Decisión explícita del usuario: no
tocarlo por ahora. Dos vías quedan documentadas para retomar en el futuro,
si hace falta — ver AGENTS.md sección 27 y SUGERENCIAS.MD 3.3 punto 5.

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
