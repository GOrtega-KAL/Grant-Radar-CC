# CLAUDE.md — arranque en frío para esta copia de Grant-Radar

Este archivo es solo un punto de entrada rápido. La fuente de verdad del
proyecto es **`AGENTS.md`** (contexto completo, arquitectura, invariantes,
historial narrativo por secciones fechadas) y **`SUGERENCIAS.MD`**
(evaluación de mejoras y su estado de implementación). Léelos antes de tocar
código; este archivo no los sustituye ni los duplica, y puede quedarse
desactualizado si no se mantiene junto a ellos.

> **Arranque en frío: AGENTS.md secciones 43 a 46.** La sesión del 21/08/2026 son
> la 44, la 45 y la **46, que es el cierre**. Cifras de referencia: 45.4
> (recopilación) y 46.2 (última publicación). Backlog abierto en la sección 36.
>
> **Producto al día:** `convocatorias.json` publicado el **21/08/2026 12:12 UTC**
> —956 detectadas, 77 vigentes, 31 relevantes, 7 con cierre urgente, 0,20 USD—
> con las URLs de CDTI ya corregidas. La caché queda al día: otra ejecución hoy
> costaría casi nada, salvo que se suba una versión de `versions.py`.
>
> **Último trabajo (21/08/2026, secciones 44 y 45):** dos avisos del usuario sobre el
> producto, los dos ciertos. Seis de las diez URLs del catálogo curado de CDTI
> eran 404 y `verificar_urls()` no podía verlo porque el WAF de cdti.es responde
> 200 a cualquier ruta; y el prefiltro temático rechazaba 68 de las 71 fichas del
> IDAE porque el vocabulario de contexto industrial no contenía «industria» ni
> «sector industrial» en ninguna forma.
>
> Después (45) se atacó **por qué ninguno se detectó solo**: el control de salud
> medía la cobertura de fecha contra el inventario completo, daba cifras absurdas
> y había que apagarlo. Ahora cada tasa va contra su denominador, hay umbrales en
> las cuatro fuentes y `compare_funnels()` compara cada etapa con la ejecución
> anterior —lo único que caza una avería cuyo síntoma es su estado normal—.
>
> **Antecedente (20/08/2026):** ronda de calidad del dato y primera ejecución
> completa publicada (AGENTS.md secciones 40-43). 76 convocatorias
> vigentes, 31 relevantes, 1,83 USD reales. Los «datos pendientes» bajan del
> 57 % al 38 %, y `objeto_y_actuaciones` y `eligible_actions` —que nunca se
> habían producido— se rellenan en 76/76 y 71/76. El coste está recalibrado con
> esos 76 análisis: la barrera pasa de 0,035 a 0,047 USD por análisis y su
> máximo efectivo de 142 a 106 (sección 11).
>
> La caché de análisis tiene hoy **76 entradas en las versiones actuales**: una
> ejecución completa ahora reutilizaría casi todo y apenas costaría. Lo que
> vuelve a hacerla cara es **subir cualquier versión de `grant_radar/versions.py`**,
> que invalida las 76.

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
  en este orden (el detalle en AGENTS.md 43.3; las cifras, en **45.4**):
  1. `poetry run python -m unittest tests.test_grant_radar_script_names`
     —un segundo, señala módulo y nombre exactos si falta un import;
  2. `poetry run python -m py_compile "Grant-Radar-prueba.py"`;
  3. `poetry run python -m unittest discover -s tests` —**448 pruebas**. Una,
     `FrontendLayoutTests::test_consortium_role_is_visible...`, es intermitente
     bajo carga porque conduce Chromium de verdad: repetir antes de investigar
     (AGENTS.md 44.7, nota sobre pruebas intermitentes);
  4. `poetry run python "Grant-Radar-prueba.py" --no-claude` al cerrar la
     ronda, comparando contra los números de referencia de AGENTS.md 45.4:
     956 detectadas, **77 vigentes** (21/08/2026). Ojo: ese recuento **ya no es un invariante fijo**, la
     ventana deslizante de BDNS lo mueve por causas externas; ante un desvío,
     mirar salud de fuentes y registros de exclusión antes que el código.
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

## Estructura actual (20/08/2026)

`Grant-Radar-prueba.py` sigue siendo el punto de entrada — se ejecuta
directamente, no se importa (su nombre con guiones no es válido para
`import`). Recuento verificado con `wc -l` el 20/08/2026: **3.988 líneas en el
script y 8.901 en los 34 módulos del paquete** —más del doble de código en el
paquete que en el script—. El script tenía 9.199 líneas antes de las nueve
rondas del 19/08/2026 y bajó a 3.842; el 20/08 volvió a crecer un poco, porque
la ronda de calidad del dato enriqueció la capa de análisis con Haiku, que
sigue dentro del script. (La cifra "8.835" de una nota anterior de este archivo
estaba mal calculada — ver AGENTS.md sección 24, nota de discrepancia.)
Progresivamente movida a `grant_radar/` (paquete con nombre importable):

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
| `source_health.py` | Salud de inventarios web: `assess_web_inventory_health()` mide el embudo entero (selección, carga, fecha, publicación) y `compare_funnels()` lo contrasta con la ejecución anterior |
| `call_text.py` | Texto de convocatoria compartido: mecanismo, identificador oficial, deadline, presupuesto, enlaces externos |
| `sources/horizon_europe.py` | Conector Horizon Europe (SEDIA Search API) |
| `sources/een.py` | Conector EEN: noticias de financiación y perfiles I+D con call verificable |
| `browser.py` | `PlaywrightBrowser`: sesión Chromium única de las fuentes sin API. `status()` devuelve el código HTTP, que `html()` no puede distinguir de un bloqueo |
| `dedup.py` | Identidad de programa, rol documental y consolidación de duplicados |
| `sources/idae.py` | Conector IDAE: fichas de ayudas y catálogo por ámbito |
| `sources/boe_miteco.py` | Conector BOE/MITECO: extractos de convocatoria en ayudas.php. Quién entra lo decide `BOE_TRACKED_AUTHORITIES`, no la taxonomía: el listado son citas legales sin materia (sección 45.2) |
| `bdns_fields.py` | Lectura de campos de la API BDNS, compartida con la matriz de reglas |
| `sources/bdns.py` | Conector BDNS/SNPSAP: inventario transversal y detalle de convocatorias |
| `documents.py` | Documentos oficiales: descarga, extracción de texto y su caché |
| `sources/cdti.py` | Conector CDTI: calendario oficial con Chromium + catálogo curado, cuyas URLs se comprueban en cada ejecución (404/410 se apartan) |
| `sources/eccp.py` | Conector ECCP: calls y rastreo acotado de webs de proyectos |
| `public_output.py` | Registro público del dashboard, estadísticas, estado por fuente y URLs. Publica `objeto_y_actuaciones`; `post_procesar_texto()` ya solo corrige acrónimos (antes corrompía palabras comunes: «cierre» → «CIRCE») |
| `publishing.py` | Subida a GitHub Pages (credenciales como parámetros, nunca leídas aquí) |
| `claude_selection.py` | Qué se manda a Claude y la barrera de coste previa |
| `coverage_watch.py` | Vigilancia de programas recurrentes conocidos. `active_not_captured` es el único estado que significa avería: abierta en su landing y no encontrada (sección 46.4) |
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
ventana de `convocatorias/ultimas` ampliada. Esa ventana es **deslizante y se
estrecha cuando sube el volumen publicado**: medida en 79 días el 18/08 y en
**65 el 20/08** (densidad real 54 filas/día, no 44). Cumple el mínimo de
negocio de 60 días con 5 de margen, y explica por sí sola que el recuento de
vigentes se mueva entre ejecuciones. Detalle en AGENTS.md secciones 26 y 40.4;
queda como punto 22 del backlog.

Pendiente de modularizar, en el orden que tiene sentido moverlo (detalle en
AGENTS.md secciones 37, 38 y 43.5): `save_discovery_audit()` (encaja en
`audit.py`), la capa de análisis con Haiku (atada a `_hard_out_of_scope()`), la
segunda mitad del dominio de holds (resolución determinista, piloto y replay,
que necesitan reglas y Claude), la matriz de reglas (sesión dedicada) y, por
último, `run_pipeline()`.

**Antes que seguir modulando**, AGENTS.md 43.5 propone dos cosas más baratas y
con más valor: el punto 24 del backlog (endurecer el prompt contra presunciones
en `objeto_y_actuaciones`, agrupado con cualquier otro cambio de prompt para
pagar una sola invalidación de caché) y el punto 22 (la densidad optimista del
test de la ventana BDNS, sin coste).
**Los ocho conectores ya están en `grant_radar/sources/`.** ECCP recibe el
prefiltro como parámetro (`is_relevant_enough`) para no depender de las reglas:
quien lo llame debe pasárselo.

Medido antes de intentarlo: cuando el script tenía 68 funciones, extraer
`run_pipeline()` arrastraba 64 de ellas. Hoy quedan **35 funciones de nivel
superior** y la proporción no ha cambiado de naturaleza. El orquestador va el último, no el siguiente. El plan por etapas y el orden de dependencias están en
AGENTS.md sección 28. El filtro previo a Claude
(`_bdns_pre_claude_gate()`, `deterministic_prefilter()`, sección 4.1 de
`AGENTS.md`) sigue deliberadamente sin extraer: es la lógica más compleja y
ajustada del proyecto; no encadenarla detrás de otra tarea sin que el usuario
lo pida explícitamente. Es también lo único que le falta a ECCP, por eso ese
conector va el último. Detalle completo de cada ronda en `AGENTS.md`,
secciones 21-43, y en `SUGERENCIAS.MD` (3.2/3.3 y sección 6).

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

**No hace falta pedir permiso** para `commit` ni `push` en esta carpeta: el
usuario lo autorizó expresamente el 19/08/2026 por tratarse de una copia
paralela de iteración. (Una nota anterior de este archivo decía lo contrario;
manda la autorización del usuario.) Lo que sí sigue requiriendo autorización
expresa, siempre, es llamar a la API de Claude.

**`convocatorias.json` está en `.gitignore` y a la vez rastreado en el remoto.**
Lo publica el propio pipeline por la API de Contents de GitHub —así lo sirve
GitHub Pages— y `.gitignore` no afecta a un archivo ya rastreado. Dos
consecuencias, ambas vistas el 20/08:

1. Tras una ejecución completa aparece modificado en `git status` sin que nadie
   lo haya tocado a mano.
2. El pipeline crea commits propios en `origin/main` («actualización
   automática»), así que un `push` posterior puede ser rechazado. Se resuelve
   con `git rebase origin/main` y volver a empujar, **nunca con `--force`**.

Detalle en AGENTS.md 43.4; anotado como punto 25 del backlog.
