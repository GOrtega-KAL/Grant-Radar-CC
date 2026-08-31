# CLAUDE.md — arranque en frío para esta copia de Grant-Radar

Este archivo es solo un punto de entrada rápido. La fuente de verdad del
proyecto es **`AGENTS.md`** (contexto completo, arquitectura, invariantes,
historial narrativo por secciones fechadas) y **`SUGERENCIAS.MD`**
(evaluación de mejoras y su estado de implementación). Léelos antes de tocar
código; este archivo no los sustituye ni los duplica, y puede quedarse
desactualizado si no se mantiene junto a ellos.

> **Arranque en frío: AGENTS.md secciones 48 a 51**, todas del 31/08/2026.
> La 48 es la modularización, la 49 el producto, la 50 los Anexos Generales de
> Horizon y la **51 es el cierre**: reutilización de lo leído y tres medidas
> (CDTI con sus bases, humo por conector, vigilancia del producto). Cifras de
> referencia en 48.8; backlog abierto en la sección 36.
> Las secciones 44 a 47 son la sesión del 21/08 y siguen vigentes como
> antecedente.
>
> **OJO CON EL COSTE:** la caché de análisis **está invalidada a propósito**
> desde el 21/08 (perfil, evaluador y prompt) y el 31/08 se subieron otra vez
> evaluador y prompt. La próxima ejecución completa reanaliza **las 80
> convocatorias: ~2,05 USD**, no ~0,2. Decisión del usuario, vigente: dejar los
> cambios listos y **no reanalizar hasta autorizarlo expresamente**. No lances
> una ejecución completa sin recordarle ese importe.
>
> **El producto está desfasado y conviene decirlo primero:**
> `convocatorias.json` sigue siendo el del **21/08/2026 12:12 UTC** —77
> convocatorias, versiones `fit-…v6` / prompt `v10` / perfil `v4`—. No incluye
> el arreglo de PowerUp NetZero (sección 47) ni nada de la sección 48, y tres de
> sus 77 fichas ya tienen el plazo vencido. Ponerlo al día es exactamente la
> ejecución de pago del párrafo anterior.
>
> **Último trabajo (31/08/2026, sección 51):** el anexo de Horizon ya no se
> reanaliza sin motivo: su huella entra en la clave de caché, así que se paga
> por leerlo una vez y solo se vuelve a pagar si cambia; y se guarda en disco
> como respaldo si el portal falla. Con ello, tres medidas más: CDTI ya trae
> las bases oficiales de sus fichas de ventanilla abierta —3 de 4, con 20.015
> caracteres de texto cada una—, hay prueba de humo
> por conector (10 pruebas en 0,2 s frente a 11 minutos de recopilación) y
> `product_watch.py` compara cada publicación con la anterior para avisar de
> convocatorias que desaparecen sin vencer o campos que se vacían.
>
> **Antes (31/08/2026, sección 50):** Horizon Europe ya llega con sus
> condiciones de elegibilidad. No estaban en el topic —viven en los Anexos
> Generales del programa— y en vez de teclearlas en un catálogo, el conector
> **lee el documento oficial que el propio topic enlaza**: una descarga por
> edición, tres extractos de 3.400 caracteres, ~850 tokens por convocatoria.
> Verificado en vivo: 30 de 30 con condiciones y un solo documento leído. Si el
> programa cambia, el enlace cambia con él y esto no necesita mantenimiento.
>
> **Antes (31/08/2026, sección 49):** tres encargos mirando el
> producto. La recopilación diaria ya se ve en el panel —publica
> `estado_recopilacion.json` y el dashboard avisa de cuántas convocatorias
> esperan análisis—; la elegibilidad dejó de imprimirse dos veces en cada
> ficha; y se encontró por qué 25 de 31 convocatorias salían «por confirmar»:
> una regla determinista decidía leyendo la prosa del modelo y disparaba en 1
> de cada 12 casos reales. Corregida sobre el campo oficial de regiones, 8
> convocatorias territoriales de otras comunidades dejan de pedir confirmación,
> **sin coste**. De las 14 restantes, las de Horizon se resolvieron en la
> sección 50; quedan las 3 de CDTI, que es el punto 36 del backlog.
>
> **Y antes (31/08/2026, sección 48):** se terminó la modularización que
> quedaba en el orden ya medido —auditoría, capa de análisis con Haiku y segunda
> mitad del dominio de holds—, con lo que el script baja de 4.086 a **2.140
> líneas** y el paquete pasa a **38 módulos**. En el script solo quedan la matriz
> de reglas y `run_pipeline()`. De paso se cerraron cuatro puntos del backlog: el
> 33 (el prompt de extracción ya es constante de módulo y tiene pruebas), el 24
> (la instrucción de `objeto_y_actuaciones` prohíbe ahora las presunciones
> declaradas), el 31 (una convocatoria publicaba una frase entera como URL) y el
> 22 (el test de la ventana de BDNS fijaba una densidad optimista).
>
> **Antecedente (21/08/2026, secciones 44 a 47):** dos avisos del usuario sobre
> el producto, los dos ciertos —seis URLs muertas en el catálogo de CDTI y un
> prefiltro que rechazaba 68 de las 71 fichas del IDAE—, el indicador de embudo
> que había que apagar para que no molestara, la publicación del día y el falso
> negativo de PowerUp NetZero, que costó un 35 % de encaje a una convocatoria a
> la que la empresa se presenta.

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
- `--no-claude` nunca debe llamar a Claude, modificar la caché IA ni generar o
  publicar `convocatorias.json`. Es el modo de validación por defecto tras un
  cambio de código: `poetry run python "Grant-Radar-prueba.py" --no-claude`.
  **Matiz desde el 31/08/2026 (AGENTS.md 49.5):** sí escribe y publica
  `estado_recopilacion.json`, un archivo aparte de ocho cifras que describe la
  recopilación —cuántas convocatorias esperan análisis y cuánto costaría— para
  que el panel pueda avisar. No toca el producto ni la caché de análisis.
- Después de cualquier cambio en `Grant-Radar-prueba.py` o `grant_radar/`,
  en este orden (el detalle en AGENTS.md 43.3; las cifras, en **48.8**):
  1. `poetry run python -m unittest tests.test_grant_radar_script_names`
     —un segundo, señala módulo y nombre exactos si falta un import. Desde el
     31/08 comprueba también cada módulo del paquete, no solo el script;
  2. `poetry run python -m py_compile "Grant-Radar-prueba.py"`;
  3. `poetry run python -m unittest discover -s tests` —**566 pruebas**. Una,
     `FrontendLayoutTests::test_consortium_role_is_visible...`, es intermitente
     bajo carga porque conduce Chromium de verdad: repetir antes de investigar
     (AGENTS.md 44.7, nota sobre pruebas intermitentes);
  4. `poetry run python "Grant-Radar-prueba.py" --no-claude` al cerrar la
     ronda, comparando contra los números de referencia de AGENTS.md 48.8:
     916 detectadas, **81 vigentes** (31/08/2026). Ojo: ese recuento **ya no es un invariante fijo**, la
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
- **Flujo previsto desde el 21/08/2026** (decidido con el usuario, AGENTS.md
  47.5): una recopilación `--no-claude` diaria programada, y la llamada a
  Claude decidida a mano cuando el desfase lo justifique — en subvenciones el
  ciclo real es de días o semanas, no de horas. Para saber cuánto se está
  desfasando lo publicado, sin red y sin coste:
  `poetry run python "Grant-Radar-prueba.py" --staleness-report`.
  Desde el 31/08 ese mismo dato viaja al panel: cada recopilación publica
  `estado_recopilacion.json` y el dashboard muestra un aviso mientras haya
  convocatorias esperando análisis (AGENTS.md 49.5).
  El comando para programar la tarea diaria en Windows está en AGENTS.md 47.6.
  **Programarla es una acción pendiente del usuario, no del agente.** La tarea
  necesita `GITHUB_TOKEN` en el entorno para poder publicar ese estado; sin él
  la recopilación funciona igual y solo se salta la publicación.
- Al cerrar cada ronda de trabajo, dejar `AGENTS.md`, `CLAUDE.md` y
  `SUGERENCIAS.MD` al día para que otra sesión pueda arrancar en frío. Es
  requisito del usuario, no una cortesía.
- Este equipo tiene una variable de entorno `VIRTUAL_ENV` heredada que
  apunta al `.venv` de la carpeta original `Grant-Radar`, no al de esta
  copia. Antes de cualquier `poetry run`/`poetry install`/`poetry add` en
  PowerShell: `$env:VIRTUAL_ENV = $null` primero, o `poetry` puede ejecutar
  silenciosamente contra el entorno equivocado.

## Estructura actual (31/08/2026)

`Grant-Radar-prueba.py` sigue siendo el punto de entrada — se ejecuta
directamente, no se importa (su nombre con guiones no es válido para
`import`). Recuento verificado con `wc -l` el 31/08/2026: **2.140 líneas en el
script y 11.660 en los 38 módulos del paquete**. El script tenía 9.199 líneas
antes de las nueve rondas del 19/08/2026, 4.086 al empezar el 31/08, y hoy
conserva **solo ocho funciones**: las seis de la matriz de reglas previa a
Claude (526 líneas) y `run_pipeline()` con su `parse_args()` (912). (La cifra "8.835" de una nota anterior de
este archivo estaba mal calculada — ver AGENTS.md sección 24, nota de
discrepancia.)
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
| `audit.py` | `DISCOVERY_AUDIT` y `audit_exclusion()` (usado por las 8 fuentes) **y el histórico en disco**: `save_discovery_audit()` / `load_audit_runs()`, que reciben la ruta como parámetro |
| `analysis.py` | **La capa de análisis con Haiku**: las dos etapas (extracción factual y evaluación de encaje), sus dos prompts de sistema como constantes de módulo, el presupuesto de evidencia y la llamada estructurada con reintentos. Recibe la clave de API como parámetro; no lee el entorno |
| `programme_annexes.py` | Las condiciones generales del programa, leídas del documento oficial que **la propia convocatoria enlaza**: un topic de Horizon no dice quién puede solicitar, y esto lo saca de sus Anexos Generales sin catálogo que mantener (AGENTS.md 50) |
| `product_watch.py` | Qué cambia en el JSON publicado respecto a la versión anterior: convocatorias que desaparecen sin vencer su plazo, elegibilidades que se mueven en bloque y campos que se vacían (AGENTS.md 51.4) |
| `profile_scope.py` | Exclusiones de ámbito del perfil (`_hard_out_of_scope()`, `_explicit_profile_incompatibility()`). Viven aparte porque las usan **los dos lados**: la matriz de reglas antes de Claude y `_build_compatible_analysis()` después |
| `holds.py` | Segunda mitad del dominio de holds: resolución determinista, validación de citas, piloto, replay y reincorporación al pipeline. **Recibe la matriz de reglas inyectada** (`intrinsic_exclusion`, `prefilter`), que es lo que permitió extraerlo sin tocarla |
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
| `staleness.py` | Cuánto se está desfasando lo publicado, leyendo solo la auditoría (`--staleness-report`). Sin red y sin coste |
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

**Del orden de extracción ya solo quedan dos piezas**, y las dos por decisión,
no por descuido (detalle en AGENTS.md 48.8):

1. **La matriz de reglas** (`_bdns_pre_claude_gate()`,
   `deterministic_prefilter()`, `_bdns_intrinsic_exclusion()`,
   `_bdns_structured_scope_exclusion()` y dos ayudantes): 526 líneas y siete
   niveles de precedencia. Sigue deliberadamente sin extraer porque es la lógica
   más ajustada del proyecto —decide qué llega a Claude y, con ello, el coste—.
   **No encadenarla detrás de otra tarea sin que el usuario lo pida
   explícitamente**; merece sesión propia (sección 4.1 de `AGENTS.md`).
2. **`run_pipeline()`**, que va el último por definición: es el orquestador y
   arrastra lo que quede.

`holds.py` y el conector ECCP reciben ya lo que necesitan de la matriz como
parámetro (`intrinsic_exclusion`, `prefilter`, `is_relevant_enough`), así que
extraerla no obliga a tocarlos. **Los ocho conectores están en
`grant_radar/sources/`.** Detalle completo de cada ronda en `AGENTS.md`,
secciones 21-48, y en `SUGERENCIAS.MD` (3.2/3.3 y secciones 6 y 11).

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
