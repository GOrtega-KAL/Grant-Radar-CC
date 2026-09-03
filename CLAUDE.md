# CLAUDE.md — arranque en frío para esta copia de Grant-Radar

Este archivo es solo un punto de entrada rápido. La fuente de verdad del
proyecto es **`AGENTS.md`** (contexto completo, arquitectura, invariantes,
historial narrativo por secciones fechadas) y **`SUGERENCIAS.MD`**
(evaluación de mejoras y su estado de implementación). Léelos antes de tocar
código; este archivo no los sustituye ni los duplica, y puede quedarse
desactualizado si no se mantiene junto a ellos.

> ## PRIORIDAD, fijada por el usuario el 01/09/2026: depurar antes que publicar
>
> **La herramienta sigue en desarrollo. El foco es depurarla y minimizar
> fallos, no encadenar análisis de pago.** Es una decisión explícita del
> usuario y manda sobre cualquier cálculo de urgencia que haga una sesión.
>
> Conviene decir cuánto lleva el producto sin actualizarse —es información
> útil y `--staleness-report` la da gratis— pero **decirlo no es lo mismo que
> proponer pagar**. Una sesión anterior (esta misma, antes de la corrección)
> convirtió el desfase en una fecha límite y empujó a publicar; el usuario lo
> corrigió. **No conviertas el desfase en urgencia por tu cuenta.**
>
> El desfase, para informar sin empujar: producto del **21/08**, cuatro fichas
> ya vencidas y doce que vencen en catorce días; entre ellas tres topics de
> Horizon de máximo encaje que cierran el 15/09. Detalle en AGENTS.md 54.2.
> Cuando el usuario decida publicar, cuesta **~2,07 USD sobre 81
> convocatorias** y requiere autorización expresa.
>
> ### Qué hacer mientras tanto: trabajo gratis que reduce fallos
>
> Todo esto no cuesta tokens y es lo que encaja con la prioridad fijada:
>
> - `--gap-report` — qué campos faltan por fuente, leyendo el JSON publicado y
>   la caché. Es la comprobación de regresión de todo lo hecho el 31/08 y el
>   01/09 (AGENTS.md 54.3).
> - `--source horizon|bdns|eccp|een|cdti|idae|boe` — recopila una fuente en vez
>   de las siete: `--source een` 81 s frente a 513-937 s. Exige `--no-claude`
>   (54.6). El alias `boa` se retiró con su conector (56.1).
> - `--staleness-report` — cuánto se desfasa lo publicado, sin red.
> - **`--no-claude` imprime desde el 02/09 el orden en que se analizarían las
>   candidatas** (AGENTS.md 60.6): veredicto del prefiltro, días al cierre y
>   palabras clave, las quince primeras. Es la forma de revisar gratis en qué se
>   gastaría el dinero **antes** de gastarlo, y es el mismo orden que usaría la
>   ejecución de pago. También dice qué ha encontrado hoy que el producto no
>   tiene, etiquetado «detectadas, sin analizar» (60.5).
> - **La recopilación diaria: doble clic en `scripts/Grant-Radar diario.bat`.**
>   Abre VS Code con el proyecto y lanza `--no-claude` en la misma ventana.
>   Admite `/q` (sin VS Code, para el Programador de tareas) y `/log` (guarda
>   además la salida). Es la solución acordada con el usuario **hasta alojar la
>   herramienta en un servidor, previsto para dentro de unos meses**. El
>   análisis con Claude sigue siendo manual y discrecional: ningún script lo
>   lanza. Existe también `scripts/Recopilacion diaria.ps1`, equivalente en
>   PowerShell y sin VS Code, si algún día se programa la tarea.
> - El backlog de la **sección 36**. Los puntos 8, 10, 11, 19, 27, 28, 38, 39 y
>   40 se cerraron el 01-02/09; queda sobre todo vigilancia de fuentes (4, 6, 7,
>   29, 30, 32) y tres reglas de negocio que exigen decisión (1, 2, 3).
>
> ---
>
> **Estado del código al cerrar el 03/09/2026:** 42 módulos, **744 pruebas en
> verde**. Verificación `--no-claude` completa: 922 detectadas, **86 vigentes**,
> prefiltro `retain=38, ambiguous=5, hold_manual=77, reject=802`. Pendientes de
> analizar **83** (~2,12 USD). Cifras de referencia en **AGENTS.md 60.10**.
>
> **Cada ficha publicada lleva ahora `stable_key`** (AGENTS.md 60.2), y es lo
> que hay que usar para referirse a una convocatoria desde fuera del JSON. El
> `id` es un contador posicional asignado después de ordenar por encaje: el 42
> de hoy y el 42 de mañana son convocatorias distintas. Los favoritos del panel
> se guardan contra `stable_key`; usar el `id` habría sido un fallo silencioso.
>
> **El Worker de favoritos está desplegado y conectado** (AGENTS.md 60.13):
> `grant-radar-favoritos.favoritos-worker.workers.dev`. La URL y el id del
> namespace KV van versionados y no son secretos.
>
> ## POR DÓNDE SEGUIR, al cerrar el 02/09/2026
>
> **El perfil se reescribió con el criterio que dio el usuario** (AGENTS.md
> 60.16): PYME afirmada, los diez proyectos de I+D descritos uno a uno, qué
> aporta como socio industrial, y qué tipo de convocatoria interesa de verdad.
> Versiones subidas, así que **toda la caché de análisis está invalidada**.
>
> **Se midió (0,1244 USD, tres convocatorias) y el resultado está en 60.16.**
> Acierto claro: PYME INNOVA Granada pasa a `ineligible` y se descarta por
> territorio, así que ya no empata con una convocatoria a la que la empresa se
> presenta. Pero **PowerUp e INNOVAE no suben: siguen en 45**.
>
> ## LO PRIMERO DE MAÑANA, y no es «afinar más el prompt»
>
> **`fit_score` no se deriva de las cinco sub-puntuaciones**: son campos
> independientes del esquema `CallEvaluation` y los rellena el modelo por
> separado. Se midió: con el perfil nuevo, la alineación tecnológica de PowerUp
> **se dobla** (25 → 50), la estratégica sube (30 → 45) y la de rol también
> (40 → 55) — **y el `fit_score` se queda clavado en 45**.
>
> O sea que el perfil funcionó y el número global no se enteró. Seguir tocando
> el prompt sin resolver esto es gastar dinero contra una pared. Hay dos vías, y
> **la elección es del usuario**: derivar el encaje de las dimensiones con pesos
> que él decida —auditable y sin coste por llamada— o exigir al modelo que sea
> coherente con las puntuaciones que él mismo da. Las dos respetan su condición
> de no deformar el criterio para alcanzar una cifra.
>
> **Las cifras de referencia del usuario son termómetro, NO objetivo.** Lo dijo
> expresamente: «no quiero que los criterios se deformen para alcanzar dicha
> cifra artificialmente». PowerUp 75-85 en consorcio, INNOVAE 65-75, PYME INNOVA
> baja por territorio. **La señal buena no es ninguna de las tres, sino que las
> tres estaban en 45**: una convocatoria a la que la empresa se presenta y otra
> excluida por territorio puntuaban igual, y esa distancia sí es un criterio que
> no se puede falsear.
>
> **El modo por lotes está IMPLEMENTADO Y VERIFICADO** (AGENTS.md 61):
> `--batch`, `--batch-collect`, `--batch-status` y `--batch-abandon`. El lote de
> humo pasó el 03/09 (61.9): la API acepta salidas estructuradas en lote, 2 de 2
> extracciones válidas, y **el descuento del 50 % es exacto** —0,00481 frente a
> 0,00961 USD—. Lo que no se ha ejercitado todavía es un lote **grande** de
> verdad: la ejecución completa de las 84 pendientes costaría ~1,08 USD por
> lotes en vez de ~2,15, y **requiere tu autorización**.
>
> **CRITERIO DE DISEÑO que fijaste el 03/09 y manda sobre lo demás:** nada de
> reglas deterministas en la puntuación, ni ajuste artificial para alcanzar una
> cifra. El camino es estudiar qué motiva una nota baja y ajustar los criterios
> **generales**. Eso descartó derivar `fit_score` con pesos, y descartó también
> rellenar el prompt para desbloquear la caché (61.6).
>
> **La caché de prompt NO se pone todavía, y está medido por qué:** Haiku 4.5
> exige un prefijo mínimo de **4.096 tokens** y el nuestro son ~3.447. Por
> debajo no avisa, simplemente no cachea. Llegar al umbral exigiría meter
> contenido que no hace falta — el ajuste artificial que descartaste. Se
> reevalúa después de la fase de calidad, y si se pone será **condicional**:
> con un solo análisis la caché **pierde** dinero, y el equilibrio está en dos.
>
> **El panel RECALCULA el plazo, no lo lee** (AGENTS.md 60.14). El backend
> publica `deadline` como los días que quedaban **el día de la recopilación**,
> y eso es correcto; leerlo como si fuera de hoy no lo era. Con el producto del
> 21/08 leído el 02/09, las 73 fichas con fecha iban doce días optimistas y
> **cuatro convocatorias ya vencidas se ofrecían como vivas**. `deadlineDays()`
> lo deriva de `deadline_date`. **No lo simplifiques** volviendo a leer
> `raw.deadline`.
>
> **Dos cosas más que no hay que romper.** `FAVORITES_ENDPOINT` usa `??` y no `||`
> a propósito: con `||`, una prueba que fuerce la cadena vacía caería a
> producción y la suite escribiría favoritos de verdad en cada ejecución.
> Y el panel **reconcilia** en vez de sustituir la lista, porque el `list()` de
> KV tarda **~30 s** en ver un alta (y 0,1 s en ver una baja): sustituir hacía
> desaparecer de tu pantalla la estrella que acababas de poner.
>
> Antes de cada `wrangler deploy`, `npm test` y `npm run check` en
> `scripts/favoritos-worker/`. **No están en `unittest`**: se lanzan a mano.
>
> **El chip de Favoritos es excluyente** (AGENTS.md 60.12): al activarlo apaga
> fuente, temática, búsqueda y los dos conmutadores, y cualquiera de ellos lo
> apaga a él. La primera versión dejaba combinarlo y el usuario lo corrigió tras
> usarlo: los demás controles enseñan una selección cada uno, así que uno que se
> acumule se lee como si estuviera roto. **No lo reabras** para «hacerlo más
> potente».
>
> **Un aviso de método que costó caro y no conviene reaprender** (AGENTS.md
> 59.1): al medir el impacto del plural se usó el corpus que había en disco
> —documentos de BDNS y fichas publicadas— y **Horizon no estaba ahí**, porque
> se descarga en vivo. La estimación salió ocho veces corta y el cambio coló
> ocho convocatorias irrelevantes, por una sigla (`RTO`) que significa una cosa
> en el vocabulario del cliente y otra en la letra pequeña de Horizon. **Un
> cambio que toca la clasificación se mide llamando al conector, no sobre la
> muestra cómoda.**
>
> **Y su hermano, del 02/09 por la tarde (AGENTS.md 60.3):** un plan escrito
> leyendo solo la documentación tiene el mismo problema. Cuatro de sus
> afirmaciones eran falsas al contrastarlas con el código, y las cuatro habrían
> fallado en silencio. **Verifica contra el código antes de empezar**, no
> después. Media hora, cuatro fallos evitados.
>
> **El conector BOA se retiró el 01/09 (AGENTS.md 56.1), así que las fuentes son
> SIETE, no ocho.** Se comprobó antes lo que el usuario pidió: BDNS encuentra el
> PAIP por su cuenta —`active_captured`, 12 coincidencias, `sources=["BDNS"]`— y
> su caché documental trae el texto oficial del PAIP, 24 documentos de Transición
> Justa y 4 con Teruel. Verificado tras retirarlo: **82 vigentes, las mismas**.
>
> **Dos hallazgos de la tarde del 01/09 que conviene no reabrir a ciegas**
> (AGENTS.md 55): el chip «Hornos» **se retiró a propósito** —filtraba por
> equipo mientras las convocatorias se describen por objetivo, y ensanchar su
> vocabulario habría llenado el filtro de ayudas a alfarería y de un municipio
> llamado ALDEHORNO—; y **el catálogo curado de CDTI no es deuda técnica**:
> aporta 4 de sus 5 convocatorias vigentes, porque la ventanilla permanente no
> tiene fecha y el calendario oficial solo publica lo fechado.
>
> **Lo que se validó pagando el 01/09 (0,1271 USD en total, dos pruebas
> dirigidas). Los tres controles de 53.2 están ejercitados y no queda
> validación pendiente.** El territorial de Navarra (BDNS 919481) sale
> `ineligible` con `review_required: False`, decidido sobre el campo oficial
> `ES22` y no sobre la prosa del modelo, que sigue titubeando sin que eso
> cambie nada (AGENTS.md 54.10). `HORIZON-CL5-2026-09-D4-08` pasó de `unknown` con tres huecos a
> **`eligible` con cero**: 18.000.000 € totales y 9.000.000 € por proyecto,
> coincidiendo con el `budgetOverview` oficial, consorcio resuelto con cita
> literal del anexo, y el encaje de 75 a 85 (AGENTS.md 54.4).
>
> **Tres suposiciones nuestras que esa prueba corrigió** (AGENTS.md 54.5):
>
> 1. El criterio de 53.2 pedía que los **cuatro** campos económicos dejaran de
>    faltar. Solo dos podían: `budgetOverview` no trae `project_budget_eur` ni
>    `funding_rate_percent`. Que sigan ausentes **no es un fallo** — es la misma
>    distinción que se cerró con el TRL. El criterio correcto es dos de dos.
> 2. `"Proyectos de I+D"` coincidió con 7 convocatorias, así que `--max-claude 3`
>    dejó fuera la BDNS 919481. Se comprobó aparte (AGENTS.md 54.10).
> 3. **La regla determinista de consorcio no debe escribirse.** Se iba a añadir
>    una regla sobre `types_of_action` para tapar `consortium_requirement_missing`
>    (21 de 77 fichas). La medición la desmiente: 3 de 3 análisis lo resolvieron
>    bien leyendo el documento oficial. Codificar a mano lo que ya se lee de la
>    fuente sería el anti-patrón que el proyecto descartó el 31/08. **Encargo
>    cancelado por medición.**
>
> ### La modularización está TERMINADA (01/09/2026, AGENTS.md 57)
>
> La matriz de reglas se extrajo a `grant_radar/bdns_rules.py` en su sesión
> dedicada, con el embudo **idéntico dígito a dígito**. El script conserva
> **cuatro funciones** —`run_pipeline()`, `parse_args()`, `build_gap_reports()`
> y un ayudante de publicación— y **ninguna es lógica de dominio**: ya es
> configuración, punto de entrada y orquestación, que era el objetivo.
>
> No queda orden de extracción pendiente. Si una sesión futura busca «lo
> siguiente de la modularización», la respuesta es que no hay.
>
> **Arranque en frío: AGENTS.md secciones 54 a 60**, que cierran el 01-02/09/2026.
> La **60** es la última y la más reciente.
> Antes de ellas, la 53 resume las cinco del 31/08 (48 a 52). Backlog abierto
> en la sección 36.
>
> **OJO AL LANZAR CUALQUIER EJECUCIÓN LARGA:** dura más de quince minutos. **No
> redirijas su salida a un archivo propio.** El 01/09 se hizo con la primera
> prueba de pago y el usuario se quedó diecisiete minutos sin ver nada,
> creyendo que no había proceso (AGENTS.md 54.8).
>
> **Decisión cerrada sobre el TRL, para no volver a abrirla:** no hay que
> perseguirlo. En Horizon, donde se anuncia de forma visible, se recoge; en
> BDNS, donde no se anuncia, no se recoge. Es una ausencia real de la fuente, no
> un fallo de extracción, y **no tiene importancia para el uso de la
> herramienta**. `--gap-report` marca esos tres campos como «ausencia aceptada»
> justamente para que nadie lo reabra.

## Qué es esto

Grant-Radar-CC monitoriza subvenciones para Kalfrisa (PYME industrial de
Zaragoza). Backend Python (`Grant-Radar-prueba.py` + paquete `grant_radar/`)
recopila convocatorias de 7 fuentes oficiales, las filtra con reglas
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
  `estado_recopilacion.json`, un archivo aparte de nueve cifras que describe la
  recopilación —cuántas convocatorias esperan análisis, cuánto costaría y
  cuántas ha encontrado hoy que el producto no tiene— para que el panel pueda
  avisar. No toca el producto ni la caché de análisis.
  **Y desde el 02/09 (AGENTS.md 60.8): con `--source` NO lo publica.** Las
  cifras de una fuente no describen el día, y el panel las enseñaría como si lo
  hicieran.
- Después de cualquier cambio en `Grant-Radar-prueba.py` o `grant_radar/`,
  en este orden (el detalle en AGENTS.md 43.3; las cifras, en **54.7**):
  1. `poetry run python -m unittest tests.test_grant_radar_script_names`
     —un segundo, señala módulo y nombre exactos si falta un import. Desde el
     31/08 comprueba también cada módulo del paquete, no solo el script;
  2. `poetry run python -m py_compile "Grant-Radar-prueba.py"`;
  3. `poetry run python -m unittest discover -s tests` —**666 pruebas**. Una,
     `FrontendLayoutTests::test_consortium_role_is_visible...`, es intermitente
     bajo carga porque conduce Chromium de verdad: repetir antes de investigar
     (AGENTS.md 44.7, nota sobre pruebas intermitentes);
  4. `poetry run python "Grant-Radar-prueba.py" --no-claude` al cerrar la
     ronda, comparando contra los números de referencia de AGENTS.md 54.7:
     921 detectadas, **84 vigentes** (02/09/2026; subió de 82 al aplicar el
     plural, AGENTS.md 59.3). Si el cambio solo toca un
     conector, `--no-claude --source <alias>` recorre esa fuente sola: 13,7 s
     en vez de 937 s. La ronda se cierra igualmente con la completa. Ojo: ese recuento **ya no es un invariante fijo**, la
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

## Estructura actual (01/09/2026)

`Grant-Radar-prueba.py` sigue siendo el punto de entrada — se ejecuta
directamente, no se importa (su nombre con guiones no es válido para
`import`). Recuento verificado con `wc -l` el 01/09/2026: **1.595 líneas en el
script y 13.345 en los 41 módulos del paquete**. El script tenía 9.199 líneas
antes de las nueve rondas del 19/08/2026, 4.086 al empezar el 31/08, 2.362 tras
la mañana del 01/09, y hoy conserva **solo cuatro funciones**: `run_pipeline()`,
`parse_args()`, `build_gap_reports()` y `publish_collection_state()`. **Ninguna
es lógica de dominio.** (La cifra "8.835" de una nota anterior de este archivo
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
| `audit.py` | `DISCOVERY_AUDIT` y `audit_exclusion()` (usado por las 8 fuentes) **y el histórico en disco**: `save_discovery_audit()` / `load_audit_runs()`, que reciben la ruta como parámetro |
| `analysis.py` | **La capa de análisis con Haiku**: las dos etapas (extracción factual y evaluación de encaje), sus dos prompts de sistema como constantes de módulo, el presupuesto de evidencia y la llamada estructurada con reintentos. Recibe la clave de API como parámetro; no lee el entorno |
| `programme_annexes.py` | Las condiciones generales del programa, leídas del documento oficial que **la propia convocatoria enlaza**: un topic de Horizon no dice quién puede solicitar, y esto lo saca de sus Anexos Generales sin catálogo que mantener (AGENTS.md 50) |
| `product_watch.py` | **La identidad estable de una convocatoria** (`stable_identity()`, publicada como `stable_key`) y las dos comparaciones que la usan: producto contra producto (51.4) y **recopilación diaria contra producto** (60.5). Las dos son distintas a propósito y no se pueden intercambiar |
| `profile_scope.py` | Exclusiones de ámbito del perfil (`_hard_out_of_scope()`, `_explicit_profile_incompatibility()`). Viven aparte porque las usan **los dos lados**: la matriz de reglas antes de Claude y `_build_compatible_analysis()` después |
| `holds.py` | Segunda mitad del dominio de holds: resolución determinista, validación de citas, piloto, replay y reincorporación al pipeline. **Recibe la matriz de reglas inyectada** (`intrinsic_exclusion`, `prefilter`), que es lo que permitió extraerlo sin tocarla |
| `bdns_scope.py` | Filtro de candidatas BDNS: palabras clave + administración autonómica de Aragón |
| `runtime_state.py` | Estado compartido de la ejecución (metadatos por fuente, diagnósticos, landings, coverage watch) |
| `http_client.py` | `_http_get()` con reintentos y límite de bytes + `_is_safe_public_https_url()` |
| `source_health.py` | Salud de inventarios web: `assess_web_inventory_health()` mide el embudo entero (selección, carga, fecha, publicación) y `compare_funnels()` lo contrasta con la ejecución anterior |
| `call_text.py` | Texto de convocatoria compartido: mecanismo, identificador oficial, deadline, presupuesto, enlaces externos |
| `sources/horizon_europe.py` | Conector Horizon Europe (SEDIA Search API) |
| `sources/een.py` | Conector EEN: noticias de financiación y perfiles I+D con call verificable |
| `browser.py` | `PlaywrightBrowser`: sesión Chromium única de las fuentes sin API. `status()` devuelve el código HTTP, que `html()` no puede distinguir de un bloqueo. Y `VerifyingDocumentBrowser`, que **verifica** el TLS (`ignore_https_errors=False`, deliberado) y arranca solo si un documento falla por cadena de certificados incompleta (60.7) |
| `dedup.py` | Identidad de programa, rol documental y consolidación de duplicados |
| `sources/idae.py` | Conector IDAE: fichas de ayudas y catálogo por ámbito |
| `sources/boe_miteco.py` | Conector BOE/MITECO: extractos de convocatoria en ayudas.php. Quién entra lo decide `BOE_TRACKED_AUTHORITIES`, no la taxonomía: el listado son citas legales sin materia (sección 45.2) |
| `bdns_fields.py` | Lectura de campos de la API BDNS, compartida con la matriz de reglas |
| `sources/bdns.py` | Conector BDNS/SNPSAP: inventario transversal y detalle de convocatorias |
| `documents.py` | Documentos oficiales: descarga, extracción de texto y su caché. `_html_to_text()` es común a las dos rutas —`requests` y navegador— para que el mismo documento no dé textos distintos según por dónde entre |
| `sources/cdti.py` | Conector CDTI: calendario oficial con Chromium + catálogo curado, cuyas URLs se comprueban en cada ejecución (404/410 se apartan) |
| `sources/eccp.py` | Conector ECCP: calls y rastreo acotado de webs de proyectos |
| `public_output.py` | Registro público del dashboard, estadísticas, estado por fuente y URLs. `public_stable_key()` normaliza la url **antes** de calcular la identidad, que es lo que hace que la clave publicada y la que se compara después sean la misma cadena. `post_procesar_texto()` ya solo corrige acrónimos (antes corrompía palabras comunes: «cierre» → «CIRCE») |
| `publishing.py` | Subida a GitHub Pages (credenciales como parámetros, nunca leídas aquí) |
| `claude_selection.py` | Qué se manda a Claude, **en qué orden** (`prioritize_claude_candidates()`, 60.6) y la barrera de coste previa |
| `staleness.py` | Cuánto se está desfasando lo publicado, leyendo solo la auditoría (`--staleness-report`). Sin red y sin coste. Construye también `estado_recopilacion.json`, que **no repite el producto**: hay una prueba que lo vigila y ya paró un intento (60.5) |
| `bdns_rules.py` | **La matriz de reglas previa a Claude**: siete niveles de precedencia que deciden qué convocatorias llegan a Haiku y, con ello, el coste. Fue lo último en salir del script (AGENTS.md 57). Para tocar cualquier condición de aquí, ampliar antes `tests/fixtures/bdns_filter_cases.json` |
| `batch_analysis.py` | **El modo diferido**: dos lotes encadenados —todas las extracciones, luego todas las evaluaciones— al 50 % de coste. No arma prompts: los pide a los mismos constructores que el modo instantáneo, que es lo único que impide que los dos caminos diverjan (AGENTS.md 61) |
| `gap_report.py` | Qué campos faltan, por fuente, en lo ya analizado (`--gap-report`). Lee el JSON publicado **y la caché de análisis**: ese segundo origen es el que permite comprobar una prueba `--max-claude` sin volver a pagarla. Sin red y sin coste (AGENTS.md 54.3) |
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

**El orden de extracción está terminado** (AGENTS.md 57). `run_pipeline()` se
queda donde está: es el orquestador y su sitio es el punto de entrada.

`holds.py` y el conector ECCP siguen recibiendo lo que necesitan de la matriz
como **parámetro** (`intrinsic_exclusion`, `prefilter`, `is_relevant_enough`), no
importado. Conviene mantenerlo así: fue lo que permitió extraer holds sin tocar
la matriz, y después extraer la matriz sin tocar holds. **Los siete conectores
están en `grant_radar/sources/`.** Detalle completo de cada ronda en `AGENTS.md`,
secciones 21-57, y en `SUGERENCIAS.MD` (3.2/3.3 y secciones 6 y 11).

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
