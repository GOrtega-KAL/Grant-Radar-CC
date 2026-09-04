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
> **El usuario autorizó el análisis el 03/09 y la fase 2 el 04/09; las dos están
> pagadas y en marcha** (92 convocatorias, ~1,18 USD). Eso NO deroga la prioridad
> de arriba: fueron decisiones suyas después de que el paso 2 cerrara, no una
> urgencia que empujara una sesión. **La publicación sigue siendo suya**; ver
> «PRIMERO DE TODO» más abajo.
>
> El desfase, para informar sin empujar: producto del **21/08**. Detalle en
> AGENTS.md 54.2. **Cualquier análisis de pago posterior a este lote vuelve a
> requerir autorización expresa** — que se haya dado una vez no abre la puerta a
> la siguiente.
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
> **Estado del código al cerrar el 03/09/2026 (noche):** 42 módulos, **760
> pruebas en verde**. Verificación `--no-claude` completa: **921 detectadas, 92
> vigentes**, prefiltro `retain=35, ambiguous=5, hold_manual=84, reject=797`.
>
> Suben de 87 a 92 **por el relevo territorial de la sección 63**, no por deriva:
> las cinco nuevas son convocatorias de ferias y misiones que antes se
> descartaban por el tema y ahora se juzgan por el territorio. **No desapareció
> ninguna.**
>
> Pendientes de analizar **92** —eran 84 por la mañana— porque el cambio de
> prompt **invalidó la caché a propósito** y la regla nueva admite cinco más:
> **2,36 USD instantáneo o ~1,18 USD por lotes**. Cifras de referencia en
> **AGENTS.md 63.4**.
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
> ## PRIMERO DE TODO, si arrancas en frío el 04/09/2026 o después
>
> **HAY UN LOTE DE PAGO EN VUELO: la FASE 2, enviada el 04/09/2026 a las 06:29
> UTC.** Antes de tocar nada, mira dónde está de verdad — es gratis:
>
> ```
> poetry run python "Grant-Radar-prueba.py" --batch-poll
> ```
>
> Usa **`--batch-poll`, no `--batch-status`**: el segundo lee solo el archivo
> local, que dice lo que se sabía al enviar y **no sabe si el lote ha
> terminado** (AGENTS.md 64.2).
>
> No hace falta prisa: las 24 h de la API son de **procesamiento**, no de
> recogida, y lo ya procesado queda disponible **29 días** (AGENTS.md 61.12).
>
> ### RESUELTO el 04/09/2026: fase 1 recogida y fase 2 en vuelo
>
> El usuario autorizó la fase 2 esa mañana. `--batch-collect` recogió la fase 1
> —**92 hechos, 0 fallos**— y envió la evaluación:
>
> ```
> fase 1  msgbatch_01WtMtqABULPghYFyj2F591D  ended · succeeded=92
> fase 2  msgbatch_01EYuyTWgccwamSBM8P1VaLz  in_progress · 92 peticiones
> ```
>
> **Lo que toca ahora:** sondear con `--batch-poll` —gratis— y, cuando la fase 2
> haya terminado, `--batch-collect` otra vez: ensambla, guarda en caché y retira
> el estado. **Eso ya no cuesta nada**, porque la fase 2 está pagada desde que se
> envió. Después, una ejecución normal publica sin llamar a Claude.
>
> Las tres cosas que hay que mirar al leer los resultados siguen siendo las de
> más abajo, y el criterio de 61.1 sigue mandando: nada de ajustar para alcanzar
> una cifra.
>
> ### El sondeo diario, desde el 04/09/2026
>
> ```
> poetry run python "Grant-Radar-prueba.py" --batch-poll
> ```
>
> **No cuesta nada** y hace dos preguntas: cómo está el lote que conocemos, y
> **qué lotes tiene Anthropic que nosotros no sepamos** —porque
> `batch_state.json` es local y está en `.gitignore`, así que perderlo dejaría
> trabajo pagado invisible—. Está en `scripts\Grant-Radar diario.bat`, antes de
> la recopilación; `/solo-lotes` sondea sin recopilar. Detalle en AGENTS.md 64.4.
>
> `--batch-status` sigue existiendo y sigue sin tocar la red, pero **no sabe si
> un lote terminó**: para eso está el sondeo.
>
> ### Cómo se llegó aquí: el sondeo del 04/09 a las 05:50 UTC
>
> `--batch-status` dice `phase1_running`, pero eso es solo el marcador local —
> significa «nadie ha sondeado desde el envío», **no** «sigue corriendo». Un
> `messages.batches.retrieve` de solo lectura, que cuesta **0 USD**, dice la
> verdad:
>
> ```
> processing_status: ended
> succeeded: 92 · errored: 0 · expired: 0 · processing: 0
> created_at  2026-09-03 13:23:35 UTC
> ended_at    2026-09-03 13:26:04 UTC   ← 2 min 29 s
> ```
>
> **La caída de los servidores de Anthropic del 03/09 no tocó el lote:** terminó
> dos minutos y medio después de enviarse, mucho antes. Las 92 extracciones están
> pagadas, completas y disponibles **29 días** (hasta el 02/10). El `expires_at`
> del 04/09 a las 13:23 UTC **no aplica** — es el plazo de procesamiento, y el
> procesamiento ya acabó.
>
> Lo que la caída sí rompió fue local: la sesión murió antes de commitear, y
> este archivo con su aviso no llegó al remoto hasta el 04/09.
>
> **Hueco cerrado el mismo día, punto 45 del backlog:** ese sondeo ya existe,
> es `--batch-poll`, y está en el `.bat` diario. Ver AGENTS.md 64.4.
>
> **Qué hacer, según lo que diga el sondeo:**
>
> | Dice | Qué hacer |
> |---|---|
> | `phase2_running` · `in_progress` | Esperar. Sondear cuando quieras: no cuesta |
> | `phase2_running` · **`ended`** | `--batch-collect`: ensambla, guarda en caché y retira el estado. **Ya está pagado, esto no cuesta** |
> | No hay lote | Ya está recogido: una ejecución normal publica **sin llamar a Claude** |
> | Un lote que el archivo local no conoce | Se perdió `batch_state.json` con trabajo pagado dentro. Ver 64.4 |
>
> **La recogida final NO publica, a propósito** (61.3). Deja los análisis en la
> caché; el producto lo publica la siguiente ejecución normal, que los encuentra
> ahí y no paga nada.
>
> **Lo que NO se puede hacer mientras el lote vuela:** tocar el prompt, el
> perfil o el catálogo de socios. `cache_key()` incluye sus versiones y la
> recogida **se negaría**, diciendo cuál cambió (61.4). Es la salvaguarda
> haciendo su trabajo, pero dejaría el lote bloqueado y ya pagado.
>
> ### Qué mirar al recoger, y por qué esas tres cosas
>
> El lote es la primera medición de los tres cambios de prompt del 03/09
> (AGENTS.md 62.7). Ninguno se puede verificar sin pagar, así que este es el
> momento:
>
> 1. **Si el montón del 45 se reparte.** Hoy 16 de las 77 fichas publicadas
>    valen exactamente 45. Es una comprobación **de distribución**, no de
>    ninguna nota concreta — y es la única que no deforma los criterios, que es
>    la condición que el usuario puso el 02/09.
> 2. **Si sube algo de las líneas que Kalfrisa QUIERE DESARROLLAR.** Hay 5-6
>    casos entre las 92: «MODERNIZACIÓN DE LA ESTRUCTURA PRODUCTIVA Y DIGITAL DE
>    LA ACTIVIDAD INDUSTRIAL», Apply AI, automatización de fábrica,
>    electrificación del calor. Mirar **`recommended_role`**, no solo la nota:
>    si sube pero el papel dice «fabricante» de algo que solo integra, es el
>    error de EHEAT (61.13) por la otra puerta.
> 3. **Que las municipales sigan bajas.** Breña Baja, Manresa, Cardona, el
>    comercio de Lleida, la beca INAP-Fulbright. Si la instrucción de coherencia
>    las empujara hacia arriba, está haciendo daño y **hay que revertirla**. La
>    distancia entre ellas y las de I+D industrial vale más que cualquier cifra
>    absoluta.
>
> **Lo que NO se va a poder comprobar, y está verificado sobre los 92 títulos:**
> la mitad «lo que Kalfrisa **INTEGRA**» de la tercera instrucción. No hay
> ninguna convocatoria de rotoconcentradores, COV ni filtros de mangas. No es un
> fallo: este mes no las hay (AGENTS.md 62.5).
>
> **Y el criterio que manda al leer los resultados** (61.1, del usuario): nada
> de ajustar para alcanzar una cifra. Las referencias —PowerUp 75-85, INNOVAE
> 65-75— son **termómetro, no objetivo**.
>
> ## POR DÓNDE SEGUIR, al cerrar el 03/09/2026 (noche)
>
> El usuario fijó tres pasos. **Los tres están hechos o en marcha.**
>
> **PASO 2 — HECHO, y el diagnóstico canceló la mitad de lo que proponía.**
> Todo el detalle en **AGENTS.md 62**; lo esencial, para no volver a intentarlo:
>
> - **La taxonomía NO se amplió, y es una decisión medida, no un olvido.**
>   `scrubber`, `rotoconcentrador`, `oxidador catalítico`, `SCR` y `filtro de
>   mangas` tienen **cero apariciones** en 313 documentos oficiales de BDNS,
>   5.006 títulos excluidos y 163.952 caracteres de topics de Horizon en vivo.
>   Es la lección del chip «Hornos» (55.1): las convocatorias se describen por
>   **objetivo**, no por equipo. **COV, VOC, RTO y «oxidación térmica» ya
>   estaban** en la taxonomía, bajo `emissions` — la nota anterior de este
>   archivo era imprecisa.
> - **Y aunque se ampliara, no movería la nota:** 52 de los 80 análisis no
>   llevan ninguna etiqueta técnica, y **las cuatro fichas mejor puntuadas
>   (72, 72, 65, 65) no tienen ninguna**. La taxonomía sirve para descubrir y
>   excluir, no para puntuar.
> - **Sí se cambió el prompt, con tres instrucciones** (versiones a
>   `fit-2026-09-v11-coherent-score-and-three-fits` y
>   `2026-09-v17-coherent-score-and-three-fits`): el dato ausente no rebaja el
>   encaje sino `confidence`; `fit_score` debe ser coherente con las cinco
>   sub-puntuaciones que el propio modelo da; y **los tres encajes del perfil
>   —fabrica, integra, quiere desarrollar— son encaje**, cada uno con su papel.
>
> **El hallazgo que manda sobre el paso 3:** medidos los 439 riesgos de los 80
> análisis en disco, **el 65,9 % de los riesgos de la banda estancada en 45 son
> huecos de información** —«no consta», «falta», «desconocido»—, y **la banda
> alta tiene el mismo 63,7 %**. O sea que el hueco **no distinguía un 45 de un
> 75**. Y `fit_score` va **por encima** de la media de sus dimensiones en las
> cuatro bandas: no está arrastrado hacia abajo, está **aplanado** —16 de 77
> fichas valen exactamente 45—. **45 es un atractor, no una valoración.**
>
> **PASO 3 — EN MARCHA. Autorizado por el usuario el 03/09 y enviado esa
> noche**, por lotes: 92 convocatorias, **~1,18 USD** en vez de 2,36. La fase 2
> queda para el 04/09, y es lo primero de este archivo.
>
>
> ## Lo que hay que saber para no repetir errores ya pagados
>
> **CRITERIO DE DISEÑO, fijado por el usuario el 03/09 y manda sobre lo demás:**
> nada de reglas deterministas en la puntuación, ni ajuste artificial para
> alcanzar una cifra. El camino es entender qué motiva una nota baja y ajustar
> los criterios **generales**. Eso descartó derivar `fit_score` con pesos y
> descartó rellenar el prompt para desbloquear la caché.
>
> **`fit_score` no se deriva de las cinco sub-puntuaciones**: son campos
> independientes del esquema `CallEvaluation`. Medido el 02/09: la alineación
> tecnológica de PowerUp se dobló (25 → 50) y el `fit_score` **se quedó en 45**.
> Conviene tenerlo presente al medir el paso 2 — mirar las cinco dimensiones y
> no solo el número global.
>
> **Las cifras de referencia del usuario son termómetro, NO objetivo.** PowerUp
> 75-85 en consorcio, INNOVAE 65-75, PYME INNOVA baja por territorio. La señal
> buena no es ninguna de las tres, sino que **las tres estaban en 45**: una
> convocatoria a la que la empresa se presenta y otra excluida por territorio
> puntuaban igual. Esa distancia sí es un criterio que no se puede falsear, y ya
> mejoró: PYME INNOVA cae a 35 y `discard_ineligible`.
>
> **Lo más contraintuitivo del perfil nuevo** (AGENTS.md 61.15): la simulación
> CFD **NO es capacidad de Kalfrisa** —la aportan NABLADOT, BIFI y AIMEN—. Lo
> suyo es el caso de uso, los equipos y la **validación a escala piloto o
> industrial**. Una prueba llevaba dos semanas afirmando lo contrario sin que
> nadie lo hubiera comprobado con el cliente.
>
> **El error más caro de esta ronda, para no repetirlo:** describir un proyecto
> **en consorcio** por lo que hace el proyecto y no por lo que aporta Kalfrisa.
> Produjo que se le atribuyera el calentamiento por microondas de EHEAT. No es
> un falso negativo, es un **falso positivo cualificado**: el análisis parece
> sólido y el error solo se ve al leer las bases. El perfil lleva ahora una
> regla que lo prohíbe.
>
> **El modo por lotes está IMPLEMENTADO Y VERIFICADO** (AGENTS.md 61):
> `--batch`, `--batch-collect`, `--batch-status` y `--batch-abandon`. El lote de
> humo pasó el 03/09 (61.9): la API acepta salidas estructuradas en lote, 2 de 2
> extracciones válidas, y **el descuento del 50 % es exacto** —0,00481 frente a
> 0,00961 USD—. Lo que no se ha ejercitado todavía es un lote **grande** de
> verdad: la ejecución completa de las 84 pendientes costaría ~1,08 USD por
> lotes en vez de ~2,15, y **requiere tu autorización**.
>
> **Para migrar a un servidor 24/7, lee AGENTS.md 61.14**: la máquina de estados
> entera, qué archivos necesitan almacenamiento persistente (`grant_radar_data/`
> y solo ese), la forma del cron y lo único que falta — **no hay bloqueo entre
> procesos**, así que dos `--batch-collect` solapados pagarían la fase 2 dos
> veces. Punto 41 del backlog. Con ejecución manual el riesgo es bajo; antes de
> dejarlo desatendido hay que cerrarlo.
>
> **El perfil se reescribió el 03/09 con las respuestas del usuario** (AGENTS.md
> 61.15) y la partición ES la corrección: **lo que Kalfrisa FABRICA**, **lo que
> INTEGRA pero no fabrica** y **las líneas que QUIERE DESARROLLAR** son tres
> encajes distintos, y tenerlos en una sola lista fue lo que produjo el error de
> las microondas. Lo más contraintuitivo: **la simulación CFD NO es capacidad
> suya** —la aportan NABLADOT, BIFI y AIMEN— y lo que sí es suyo es el caso de
> uso, los equipos y la **validación a escala piloto o industrial**.
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
> **La internacionalización ya NO se descarta por el tema** (AGENTS.md 63). Los
> seis términos de ferias y misiones comerciales —`programa pyme global`,
> `mision comercial`, `visita a la feria`…— se **retiraron** de
> `BDNS_ALWAYS_OUT_OF_SCOPE_TERMS`, y su trabajo lo hace
> `_bdns_beneficiary_territory_outside_aragon()`, que descarta por **dónde tiene
> que estar la empresa**, no por de qué va la ayuda. Se apoya en la lista cerrada
> de provincias españolas, no en un catálogo de ferias que caduque.
> **No vuelvas a añadir esos términos**: hay una prueba que lo prohíbe.
>
> La regla exige el **sujeto beneficiario** delante del topónimo a propósito.
> Sin él, «Misión Comercial a México» descartaría por el destino del viaje y
> «con socios de Cataluña» por la procedencia de un socio, que no es donde tiene
> que estar Kalfrisa.
>
> **Arranque en frío: AGENTS.md secciones 54 a 63**, que cierran el 01-03/09/2026.
> La **63** es la última: el relevo territorial, que **invierte la recomendación
> de 62.6** —ese apartado se conserva porque explica por qué cambió el número, no
> porque siga valiendo—. La **62** es la que más ahorra trabajo: el diagnóstico que
> canceló medio paso 2 con cifras —por qué motivo se rebaja el encaje (62.2), que
> `fit_score` está aplanado y no arrastrado (62.3), y que ampliar la taxonomía no
> puede funcionar (62.4 y 62.5)—. Antes, la **61**: modo por lotes, notas para el
> servidor (61.14) y el perfil reescrito con las respuestas del cliente (61.15).
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
- **Con un lote en vuelo, NO se tocan `versions.py`, el perfil ni el catálogo
  de socios.** `cache_key()` incluye esas versiones y la recogida se **negaría**,
  dejando bloqueado un análisis ya pagado (AGENTS.md 61.4). Comprobar antes con
  `--batch-status`, que es gratis y no toca la red. Es la salvaguarda haciendo
  su trabajo, no un fallo, pero conviene no provocarla.
- **Llamar a Claude/Haiku por API requiere SIEMPRE autorización expresa del
  usuario**, sin excepción, porque cuesta dinero real. Que se haya autorizado
  una vez —el lote del 03/09— no cubre la siguiente. En cambio, el usuario
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
