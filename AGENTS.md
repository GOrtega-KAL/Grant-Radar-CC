# Grant-Radar — contexto e instrucciones del repositorio

> **Arranque en frío: secciones 43 a 47.** La sesión del 21/08/2026 son las
> secciones 44 a 47. Cifras de referencia en 45.4 (recopilación) y 46.2 (última
> publicación). **La 47 deja la caché invalidada a propósito**: se subieron perfil,
> evaluador y prompt, así que la próxima ejecución completa reanaliza las 77 y
> cuesta ~1,8 USD, no ~0,2. El backlog abierto está en la sección 36. Las
> secciones 13-42 son historial narrativo fechado: se consultan, no se leen
> enteras.

## 1. Objetivo

Grant-Radar monitoriza convocatorias de subvenciones potencialmente relevantes
para Kalfrisa. Recopila información de fuentes oficiales, filtra convocatorias,
consolida documentos relacionados, utiliza Claude Haiku 4.5 para extraer hechos
y evaluar el encaje, y genera el JSON consumido por el dashboard.

El programa debe priorizar soluciones generales y mantenibles. No introducir
reglas específicas para una convocatoria cuando el problema pueda resolverse
mediante identidad de programas, clasificación documental, selección semántica
de evidencia, normalización o reglas deterministas reutilizables.

## 2. Archivo de trabajo y alcance

- Backend principal: `Grant-Radar-prueba.py`. Sigue siendo el punto de entrada
  (`poetry run python "Grant-Radar-prueba.py"`) y no se importa: su nombre con
  guiones no es válido para `import`. Lo que queda en él, a 20/08/2026: la
  matriz de reglas previa a Claude (sección 4.1), la capa de análisis con Haiku,
  la segunda mitad del dominio de holds, `save_discovery_audit()`, la
  configuración y credenciales, y la orquestación de `run_pipeline()`.
  **Los ocho conectores de fuentes ya están en `grant_radar/sources/`**,
  CDTI y ECCP incluidos (secciones 34 y 35).
- Paquete `grant_radar/`: la lógica ya extraída del backend principal (división
  en curso; historial por rondas en las secciones 21-33 y en `SUGERENCIAS.MD`
  3.2/3.3). `Grant-Radar-prueba.py` los importa con
  `from grant_radar.X import ...`, y `CLAUDE.md` mantiene la tabla de qué
  contiene cada módulo, además del recuento de líneas al día.
  Los recuentos concretos envejecen rápido mientras la división avanza: la
  cifra vigente está en `CLAUDE.md` y se comprueba siempre con `wc -l`, nunca
  de memoria (ver nota de discrepancia en la sección 24).
  Antes de mover más código aquí, comprobar sus dependencias reales con un
  análisis previo: no todo se puede extraer de forma aislada. El acoplamiento
  entre caché y reglas que bloqueó el primer intento se resolvió extrayendo
  ambos a la vez (sección 23), y seis de los siete conectores no se pudieron
  mover hasta extraer antes la infraestructura que compartían (secciones 28
  y 30).
- Frontend activo: `index.html`.
- JSON público/local del dashboard: `convocatorias.json`. Está en `.gitignore`
  pero rastreado en el remoto, porque lo publica el propio pipeline; ver 43.4
  antes de extrañarse al verlo en `git status`.
- No modificar archivos de backup, `Obsoleto/` ni `Frontend alternativo/` salvo
  petición expresa.
- Conservar los encabezados `CELDA 1`, `CELDA 2`, etc.; sirven para navegar por
  el script.
- El entorno objetivo es exclusivamente Windows local con Poetry, Playwright y
  Chromium. No reintroducir lógica específica de Google Colab.

## 3. Arquitectura del pipeline

Secuencia general:

1. Validar argumentos y, si corresponde, el formato de la clave de Claude.
2. Recopilar convocatorias mediante API oficial cuando exista.
3. Utilizar Playwright + Chromium solamente para fuentes sin API útil.
4. Aplicar catálogos estáticos únicamente como respaldo trazable.
5. Registrar descubrimientos, descartes y cobertura de programas recurrentes.
6. Deduplicar y fusionar páginas, extractos, bases y otros documentos de una
   misma convocatoria.
7. Filtrar convocatorias cerradas (`deadline_days <= 0`).
8. Validar localmente los esquemas y realizar dos llamadas por convocatoria:
   extracción factual compacta —incluidas las líneas— y evaluación del encaje.
9. Aplicar salvaguardas deterministas posteriores al modelo.
10. Verificar URLs, generar `convocatorias.json` y publicarlo en GitHub Pages.

Fuentes actuales:

- BDNS: API REST oficial SNPSAP (`/convocatorias/ultimas`,
  `/convocatorias/busqueda` y detalle `/convocatorias?numConv=...`). Se usa como
  inventario transversal y `bdns_id` prevalece como identidad fuerte.
- Horizon Europe: API oficial SEDIA; RSS como respaldo.
- CDTI: Playwright sobre calendario y fichas, con catálogo estático curado como
  respaldo; sus registros se fusionan con BDNS cuando comparten identidad. El
  calendario es un punto único de descubrimiento y su actualización o una rotura
  de su tabla puede reducir cobertura aunque las fichas sigan disponibles. Cada
  ejecución comprueba por ello su acceso, estructura, volumen, carga de fichas,
  cobertura de fechas y antigüedad declarada.
- IDAE: Playwright sobre ayudas y financiación, más el catálogo de ayudas para
  ámbito estatal, Aragón y Zaragoza.
- BOE/MITECO: Playwright y consolidación de documentos regulatorios.
- BOA Aragón: señal secundaria/backup (Playwright + catálogo estático); el
  descubrimiento automático principal de convocatorias autonómicas de Aragón
  es el filtro estructurado `nivel1`/`nivel2` dentro de BDNS (sección 26).
- ECCP: inventario de calls y rastreo limitado de landings oficiales y webs de
  proyectos, con profundidad elegida mediante experimento auditable de niveles
  0-3, `robots.txt`, HTTPS y límites de peticiones, bytes y tiempo. La prueba del
  04/08/2026 seleccionó profundidad 1: mediana de una petición externa por call;
  el nivel 2 elevó el total de 6 a 22 peticiones y activó la parada por coste.
- EEN: noticias de financiación y perfiles I+D con bloque `Call details`. Las
  búsquedas de socios sin convocatoria oficial verificable se excluyen.

## 4. Principios de extracción y análisis

- No truncar documentos largos tomando solo el comienzo. Usar
  `select_evidence_excerpt()` para conservar ventanas sobre beneficiarios,
  CNAE/NACE, importes, intensidades, fechas, consorcios, requisitos y líneas.
- Utilizar `_programme_identity()` y `_deduplicate_raw_convocations()` para
  consolidar familias documentales.
- Conservar `document_role` y la trazabilidad de documentos relacionados.
- Cuando existan líneas, lotes o subprogramas alternativos, representarlos en
  `funding_lines`; no acumular sus requisitos como si todos fueran obligatorios.
- Extraer en `eligible_actions` únicamente actuaciones, inversiones o categorías
  de gasto declaradas financiables. No sustituirlas por resultados esperados ni
  por ideas de proyecto. El frontend mantiene este dato dentro del resumen
  ejecutivo y distingue expresamente el respaldo basado solo en temas exigidos.
- Los esquemas Claude deben evitar campos anulables: usar `""`, `-1`, `0` y
  `"unknown"` como centinelas y convertirlos inmediatamente a `None` mediante
  `normalize_call_facts()` antes de evaluar o publicar.
- Validar `CallFacts` y `CallEvaluation` antes de recopilar y antes de cada
  petición. El límite publicado es 24 campos opcionales y 16 uniones; actualmente
  ambos esquemas deben mantener cero opcionales y cero uniones.
- No inferir restricciones de tamaño empresarial. Solo exigir condición PYME si
  la fuente la establece expresamente.
- Eliminar también de resumen y acción cualquier comprobación de PYME no fundada,
  conservando las verificaciones legítimas de tipo de entidad.
- Distinguir entre consorcio permitido y consorcio obligatorio. Si la fuente
  enumera solicitantes individuales y consorcios como alternativas, no marcar el
  consorcio como requisito pendiente.
- Un consorcio obligatorio es una forma de participación, no una incompatibilidad
  de entidad. La salvaguarda posterior al modelo revierte de forma general un
  `discard_ineligible` cuando la fuente admite expresamente empresas, el motivo
  se limita a que Kalfrisa no puede concurrir sola y el rol recomendado es de
  socio tecnológico, demostrador o socio de consorcio. No revierte exclusiones
  territoriales, sectoriales, jurídicas ni de tipo de entidad; las restricciones
  expresas de tamaño, como PYME, permanecen como comprobación pendiente.
- Una categoría obligatoria dentro de la composición del consorcio tampoco se
  interpreta como tipo exclusivo de beneficiario. Solo se corrige el análisis
  cuando la evidencia usa lenguaje compositivo inequívoco (`at least one`,
  `consortium must include` o `should be part of the consortium`) y el descarte
  se basa precisamente en exigir esa categoría a todos los socios. Las fórmulas
  `applicants must be` o equivalentes, sin evidencia compositiva, no se relajan.
- El perfil conocido indica que Kalfrisa es una empresa mediana situada en el
  polígono de Malpica, Zaragoza.
- Las fechas y el estado determinista prevalecen sobre recomendaciones temporales
  incoherentes generadas por el modelo.
- No inventar URLs, fechas, presupuestos, elegibilidad ni entidades colaboradoras.
  Marcar el dato como desconocido y pendiente de nueva evidencia cuando no sea
  suficiente; la falta de datos no crea por sí sola una revisión humana de
  compatibilidad.

### 4.1. Matriz BDNS previa a Claude

`_bdns_pre_claude_gate()` se ejecuta antes del filtro semántico común. Conserva
los campos estructurados originales de SNPSAP y devuelve `retain`, `hold_manual`
o `reject`. `hold_manual` es únicamente un estado intermedio de la matriz: en el
pipeline normal se descargan bases, se repiten las reglas locales y, si la causa
sigue sin resolverse, se convierte en `ambiguous` para el análisis general de
Haiku. Solo `reject` queda fuera de Claude y se registra como exclusión; no existe
una decisión humana bloqueante en tiempo de ejecución.

Precedencia y criterios vigentes:

0. Incompatibilidades intrínsecas: acceso nominativo, beneficiario imposible,
   sector excluido y alcance residencial, formativo, laboral o de premios se
   rechazan antes de comprobar vigencia. Seguirían siendo incompatibles aunque
   estuvieran abiertos y no justifican consumir Haiku. Tras descargar bases para
   resolver otro `hold`, repetir este control solo con expresiones documentales
   autosuficientes. No buscar términos amplios como `feria` o `economía social`
   en todo un PDF: pueden aparecer incidentalmente en exclusiones o referencias.
   En bases recuperadas también se rechaza un objeto inequívocamente laboral
   (`contratación` más `inserción laboral`) y una enumeración exhaustiva de
   solicitantes públicos, educativos o no lucrativos sin vía empresarial. La
   lista se acota hasta el siguiente epígrafe para que una mención posterior a
   `empresas` dentro de prohibiciones generales no produzca un falso positivo.
1. Alcance estructurado SNPSAP: antes de vigencia y territorio, rechazar una
   finalidad oficial exclusivamente primaria sin vía formal de grupo operativo,
   consorcio o clúster; empleo solo cuando el título confirma un objeto laboral;
   cooperación al desarrollo; títulos dirigidos expresamente a entes locales
   salvo vía formal de participación; y
   objetos autosuficientes como premios, ferias, artesanía, bienestar animal o
   buques pesqueros. Una anualidad pasada solo cuenta si el título contiene un
   marcador inequívoco reciente y no hay plazo confirmado. No usar categorías
   administrativas solas cuando contradigan el objeto: `Fomento del Empleo` no
   excluye suelo industrial ni economía circular/transición energética.
   La segunda ampliación reconoce variantes autosuficientes observadas:
   `bonos de comercio`, `Convocatoria Pyme Global`, conciliación personal,
   familiar o laboral, fomento cultural, arte y educación, y construcciones
   sintácticas alternativas que destinan la ayuda a entidades locales. Aplicar
   estas expresiones solo sobre metadatos breves, nunca como términos amplios en
   PDFs completos.
2. Sector antes de coste documental: C, D y E son positivos. B exclusivamente se
   rechaza salvo evidencia manufacturera; A directa se rechaza, pero un grupo
   operativo, consorcio o clúster se difiere para verificar participación propia;
   F exige conexión térmica o industrial. Agroindustria, cadena alimentaria y
   madera solo serían clientes comerciales indirectos y no oportunidades propias.
3. Vigencia: conservar cierres futuros y ventanillas expresamente abiertas. Un
   registro reciente sin prueba de apertura queda en `hold_manual`; uno antiguo
   sin prueba vigente se rechaza. La antigüedad usa días con signo desde la fecha
   de recepción; no reutilizar `_days_until()`, que recorta fechas pasadas a cero.
   El indicador SNPSAP `abierto` se conserva, pero no demuestra por sí solo una
   ventanilla permanente. No asignar 90 días como plazo ficticio.
4. Papel: distinguir `direct_beneficiary`, `consortium_partner`, `cluster_route`
   y `unknown`. No existe el papel `supplier`: vender o subcontratar para un
   beneficiario ajeno es una oportunidad comercial indirecta y se rechaza. Los
   consorcios requieren actividad, costes o presupuesto propios. Los clústeres
   solo se retienen cuando canalizan financiación, costes o pilotos ejecutados por
   empresas miembro; funcionamiento, personal y estructura se rechazan.
5. Territorio: una región distinta de Aragón no implica automáticamente rechazo.
   Centro previo obligatorio fuera de Aragón sí; localización del proyecto sin
   centro previo puede ser válida. Abrir un centro nuevo solo se considera viable
   con un periodo de ejecución confirmado de al menos 730 días; duración
   desconocida queda en `hold_manual`. Administraciones `OTROS` con NUTS
   específico no se tratan como estatales.
6. Inversión propia: energía, ahorro energético, residuos, valorización y
   depuración de gases son relevantes. No se exige I+D cuando Kalfrisa puede
   financiar una inversión propia: maquinaria, mejora de procesos, activos
   productivos, digitalización o eficiencia energética son positivas. Ferias,
   misiones comerciales, residencial, premios, formación y empleo se excluyen.

El filtro común de fuentes europeas aplica `_hard_out_of_scope()` antes de Claude
y no permite que una etiqueta digital o energética genérica neutralice por sí
sola una exclusión sectorial ya demostrada. Transporte, edificios como uso final,
generación eólica/fotovoltaica/mareomotriz y seguridad nuclear se rechazan salvo
integración térmica o de proceso industrial explícita. Medio marino, pesca,
gobernanza ambiental y familias digitales/cuánticas inequívocas requieren una
señal fuerte de calor residual, combustión de hidrógeno, proceso térmico o
valorización térmica de residuos. Educación y salud mental se rechazan solo como
objeto explícito y sin conexión tecnológica. No se excluye por `digital`, `IA`,
`piloto`, `innovación`, energía, residuos o economía circular de forma aislada.
Además, `_explicit_profile_incompatibility()` solo rechaza cuando concurren
requisitos formales incompatibles: sector restringido más producto propio
obligatorio, sin conexión con la taxonomía tecnológica de Kalfrisa ni vía
complementaria; o acceso exclusivo a entidades intermediarias incompatibles sin
financiación, costes o pilotos para empresas miembro. No usa títulos,
identificadores, URLs ni nombres de convocatorias como reglas.

Después de la evaluación se aplica también
`_correct_own_industrial_investment_scope()`. Esta salvaguarda evita que Haiku
descarte una ayuda únicamente porque carece de I+D cuando los hechos prueban una
inversión directa de Kalfrisa en activos, suelo, instalaciones, maquinaria,
procesos, digitalización o eficiencia. Exige elegibilidad empresarial positiva y
geografía compatible; no recupera inversiones de clientes, entidades públicas ni
otras comunidades autónomas. La corrección deja la oportunidad en `watch`: no
afirma que exista una necesidad de inversión, solo impide perder una línea que
podría financiar capacidad industrial propia. Se reaplica al cargar caché y no
forma parte del hash factual.

`_correct_direct_valorisation_scope()` cubre un segundo error postmodelo: una
convocatoria de valorización no es una simple oportunidad comercial cuando
admite expresamente a proveedores de soluciones o tecnología como participantes
financiados. La regla exige simultáneamente `thermal_waste`, objeto explícito de
valorización, presupuesto o ayuda positiva y lenguaje de solicitante tecnológico.
No recupera una ayuda reservada al cliente final ni una mera venta o
subcontratación. La decisión corregida es `watch`, con papel
`technology_partner`; las restricciones jurídicas de PYME u otra elegibilidad
expresa permanecen como `unknown` y no se relajan.

Los casos comunes positivos y negativos están en
`tests/fixtures/common_scope_filter_cases.json`; los requisitos ECCP en
`tests/fixtures/eccp_eligibility_filter_cases.json`; y las variantes residuales
BDNS en `tests/fixtures/bdns_residual_scope_cases.json`. Deben ampliarse antes de
cambiar estos dominios. `Pioneering Destination Earth` permanece para Haiku porque el
conjunto positivo conocido demostró que una exclusión general por esa familia
reduciría el recall. Las reglas no dependen de identificadores de convocatorias.

Etiquetas públicas del esquema 3: `Socio de consorcio`, `Vía clúster` y
`Requiere nuevo centro`. Se publican en `opportunity_labels`;
`opportunity_role` conserva el papel estructurado. El frontend debe mostrarlas
en la tarjeta, no solo en el detalle. Estos campos no forman parte del hash
factual y no invalidan la caché.

Los términos, el umbral y los casos límite están documentados en
`tests/BDNS_FILTER_SPEC.md` y `tests/fixtures/bdns_filter_cases.json`. Posibles
ajustes futuros deben ampliar primero esos fixtures: vocabulario de requisitos
territoriales, participación formal en consorcio, ayudas canalizadas por clúster y
clasificación de líneas CNAE múltiples. No relajar vigencia ni convertir
un dato ausente en rechazo. Los `hold_manual` no resueltos localmente deben llegar
como `ambiguous` a Haiku con las bases recuperadas, manteniendo métricas de recall
y coste.

El modo experimental `--hold-pilot N` permite medir esa automatización con un
máximo absoluto de 20 casos y una llamada factual a Haiku por caso que no pueda
resolverse localmente. Solo recopila BDNS; recupera bases, anuncios y sedes
oficiales, extrae HTML/texto/PDF y prioriza vigencia (60 % de la muestra), seguida
de territorio, consorcio y clúster. La salida exige una cita literal verificable,
confianza mínima de 65 y pasa por reglas deterministas: entre ellas, el umbral de
730 días para un centro nuevo. Una respuesta dudosa queda `unresolved`.

Este piloto es diagnóstico: `retain` significa que supera la causa concreta del
hold, no que sea globalmente compatible. No realimenta reglas, no incorpora la
decisión al pipeline normal y no modifica la caché principal ni el JSON. La
integración en producción requiere primero control de calidad estratificado,
métricas por causa y comprobación explícita de falsos rechazos.

La versión vigente del piloto es
`bdns-hold-2026-08-v4-direct-participation`. Además de comprobar que
la cita aparece en el documento, exige que la cita pruebe la conclusión: fecha
pasada de solicitud para cierre, obligación y establecimiento para centro previo,
señales de participación formal en consorcio y de apoyo directo a miembros para
clúster. La localización del proyecto no prueba centro existente. Las respuestas
negativas por ausencia de evidencia nunca generan rechazo y la duración se
recalcula desde la cita. El prompt recibe la fecha actual explícita. V3 añade
descarga de PDF por el endpoint oficial `convocatorias/documentos?idDocumento=`,
fechas de publicación, plazos relativos, fechas con puntos y comparación compacta
para palabras partidas por maquetación PDF. V4 elimina la pregunta sobre equipos
suministrables y la sustituye por participación formal en consorcio.

En producción, `resolve_bdns_holds_for_pipeline()` recupera la evidencia oficial
de todos los estados intermedios. Una exclusión intrínseca o un cierre demostrado
se rechaza localmente; un hecho positivo reentra por toda la matriz; y cualquier
incertidumbre restante pasa al extractor/evaluador general con las bases añadidas
a `related_document_contents`. El modo `--hold-pilot` permanece separado como
herramienta de evaluación focalizada y no interviene en esa ruta.

## 5. Caché, versiones y artefactos

Rutas:

- Caché IA: `grant_radar_data/grant_radar_cache.json`.
- Caché documental BDNS: `grant_radar_data/bdns_document_cache.json`. Conserva
  únicamente texto extraído de documentos/anuncios oficiales estables, con clave
  de URL, fecha de publicación, tipo y origen. No contiene decisiones IA ni
  cachea sedes electrónicas mutables. Puede escribirse en modos sin Claude para
  evitar descargas y extracción PDF repetidas. Está excluida de Git mediante
  `.gitignore` y no debe publicarse.
- Caché documental general: `grant_radar_data/source_document_cache.json`.
  Conserva texto de bases, convocatorias, extractos y modificaciones oficiales
  seleccionados desde fuentes web como CDTI. Es independiente de BDNS y de la
  caché IA, está excluida de Git y puede poblarse en `--no-claude`. Las respuestas
  sin texto extraíble se registran durante 30 días para no volver a descargar en
  cada ejecución un PDF escaneado o incompatible; después se reintentan.
- Auditoría: `grant_radar_data/grant_radar_audit.json`.
  Las ejecuciones `--no-claude` guardan en
  `diagnostics.candidate_inventory` un inventario compacto de todas las
  candidatas finales: identidad, título, fuente y descubrimiento, plazo,
  mecanismo, papel, resultado y señales del prefiltro, alcance BDNS, hash factual,
  clave y estado de caché (`hit`, `content_changed` o `new`). No guarda
  descripciones completas, bases, prompts ni secretos. El subesquema vigente del
  inventario es 1.
- Revisión manual BDNS: `grant_radar_data/bdns_hold_manual_review.csv` y su
  guía `grant_radar_data/bdns_hold_manual_summary.md`. El CSV es un artefacto de
  trabajo humano y no modifica por sí solo las decisiones del pipeline.
- Piloto automático BDNS: caché independiente
  `grant_radar_data/bdns_hold_ai_cache.json` e informe
  `grant_radar_data/bdns_hold_pilot_report.json`. Solo se crean al ejecutar el
  piloto autorizado; nunca sustituyen `grant_radar_cache.json`.
- Repetición determinista: `grant_radar_data/bdns_hold_replay_report.json`.
  Reprocesa un informe existente con metadatos y documentos actuales, reutiliza
  únicamente sus resoluciones ya verificadas y no hace nuevas llamadas a Claude.
  Es un informe desechable: el archivo no se conserva tras documentar sus
  conclusiones y puede recrearse con el comando explícito.
- Salida pública: `convocatorias.json`, junto a `index.html`.

La caché se identifica mediante hash del contenido y versiones del perfil,
extractor, evaluador, prompt, catálogo de socios, modelo y esquema. Si cambia la
semántica de extracción o evaluación, incrementar la versión correspondiente.
No borrar ni invalidar manualmente la caché sin avisar al usuario del coste y
obtener autorización.

La caché se guarda después de cada convocatoria completada —extracción y
evaluación—. Si Anthropic se queda sin saldo o falla una ejecución:

- Las convocatorias terminadas permanecen en caché y se omiten en la siguiente
  ejecución mientras no cambien el contenido o las versiones.
- La convocatoria que falla a mitad no se reanuda desde la segunda llamada: se
  repite completa la próxima vez.
- Las convocatorias todavía no iniciadas quedan pendientes.
- Si una extracción terminó pero falló la evaluación, su consumo parcial se
  registra en la auditoría, pero no se guarda como análisis utilizable.
- Cada respuesta HTTP de Claude se contabiliza antes de validar el JSON. Los
  intentos con salida truncada o inválida conservan tokens, coste, etapa, número
  de intento y estado de validación; un reintento exitoso acumula también el
  consumo de los intentos fallidos. Si la ejecución aborta, la auditoría suma los
  análisis completados anteriormente y las etapas facturables del caso fallido.
- Las ejecuciones completas y `--max-claude` guardan en su registro de auditoría
  el consumo de la ejecución, no solo en el JSON o en la salida del terminal.
- No se genera ni publica un JSON parcial cuando el pipeline aborta por Claude.

Al cargar una entrada válida, `apply_current_deterministic_rules()` reaplica en
memoria las salvaguardas vigentes de tamaño empresarial, consorcio y coherencia
temporal. Esto permite corregir redacción determinista sin volver a pagar un
análisis ni invalidar la caché. El archivo físico se actualiza cuando un análisis
nuevo o forzado llama posteriormente a `cache_save()`; el JSON generado en esa
misma ejecución ya consume la versión corregida en memoria.

La auditoría usa el esquema 2: cada exclusión se almacena una sola vez en un
catálogo normalizado y cada ejecución conserva referencias. Mantener la integridad
de esas referencias y un máximo de 365 ejecuciones.

El frontend y el backend comparten el esquema público. Antes de cambiar nombres,
tipos o estructuras de campos en el JSON, comprobar y adaptar `index.html`.
Mantener compatibilidad hacia atrás cuando sea razonable.

El esquema público vigente es 3. Añade `identifier`, `discovery_sources`,
`funding_mechanism`, `eoi_deadline_date`, `opportunity_role` y
`opportunity_labels` sin retirar campos de la versión 2. El frontend debe seguir
aceptando esquemas 2 y 3.

Desde entonces se han añadido tres campos más **sin subir el número de esquema**,
por ser puramente aditivos: `eligible_actions` y `eligible_actions_basis`
(sección 20) y `objeto_y_actuaciones` (sección 40). Un frontend antiguo los
ignora y sigue funcionando, que es el criterio para no subir versión; a cambio,
el número de esquema no basta para saber qué campos trae un JSON. Si alguna vez
se retira o se cambia el tipo de un campo, entonces sí hay que subirlo y adaptar
`index.html`.

## 6. Modos de ejecución

Desde PowerShell, en la raíz del proyecto:

```powershell
poetry run python "Grant-Radar-prueba.py" --no-claude
```

Recopila y diagnostica sin llamar a Claude, modificar la caché IA, generar el
JSON ni publicar. Puede poblar o reutilizar la caché documental pública BDNS y
guarda el inventario final de candidatas dentro de la auditoría.

Las pruebas deterministas locales se ejecutan con:

```powershell
poetry run python -m unittest discover -s tests -v
```

Incluyen fixtures sintéticos de BDNS, ECCP, EEN, deduplicación, filtro común y
contrato del frontend. PowerUp NetZero es una regresión de prueba, no una regla
especial de producción.

```powershell
poetry run python "Grant-Radar-prueba.py" --staleness-report
```

Informa de cuántas convocatorias esperan análisis y desde cuándo, leyendo solo
la auditoría. No recopila, no consulta ninguna fuente, no cuesta nada y es
instantáneo. Es un modo aislado: no se combina con ningún otro. Cada
`--no-claude` imprime además ese resumen en una línea al cerrar (sección 47.5).

```powershell
poetry run python "Grant-Radar-prueba.py" --hold-pilot 20
```

Recopila únicamente BDNS, selecciona una muestra estratificada de `hold_manual`,
recupera evidencia oficial y usa como máximo una llamada Haiku por caso todavía
no resuelto localmente. Consume tokens y escribe exclusivamente la caché y el
informe separados del piloto. Requiere autorización expresa; no genera JSON ni
publica. No puede combinarse con `--no-claude`, `--max-claude`, `--claude-match`
ni `--force-reanalysis`.

```powershell
poetry run python "Grant-Radar-prueba.py" --replay-hold-report
```

Reprocesa los casos del informe `hold_manual` existente con las reglas actuales.
Consulta BDNS y sus documentos, pero no llama a Claude, no modifica ninguna
caché principal, no genera `convocatorias.json` y no publica. Es incompatible
con todos los demás modos de ejecución.

```powershell
poetry run python "Grant-Radar-prueba.py" --max-claude 2
```

Analiza como máximo dos convocatorias y guarda sus análisis en caché. No genera
ni publica el JSON.

```powershell
poetry run python "Grant-Radar-prueba.py" --max-claude 2 --claude-match INNOVAE --claude-match HORIZON-CL5-2026-09-D4-08
```

Prueba dirigida a coincidencias concretas. Los filtros pueden repetirse.

```powershell
poetry run python "Grant-Radar-prueba.py" --max-claude 2 --force-reanalysis --claude-match INNOVAE --claude-match "Línea PID"
```

Reanaliza selectivamente coincidencias aunque ya estén en caché. Por seguridad,
`--force-reanalysis` exige simultáneamente `--max-claude` y al menos un
`--claude-match`. Nunca usarlo sin filtros ni convertirlo en un borrado global de
caché. Cada entrada anterior se sobrescribe solo después de terminar correctamente
su nuevo análisis; las demás entradas permanecen intactas.

```powershell
poetry run python "Grant-Radar-prueba.py"
```

Ejecución completa: recopila, analiza lo que no esté en caché, genera el JSON y,
si el token de GitHub es válido, intenta publicarlo. Antes de la primera llamada
aplica `claude_safety_preflight()`: detiene la ejecución si se han seleccionado
más de 200 análisis nuevos/cambiados o si el extremo superior estimado supera
5 USD. Con la calibración vigente de **0,047 USD** por convocatoria —el p95 de
los 76 análisis reales del 20/08, sección 42.3— el límite económico es el
efectivo y permite como máximo **106** análisis en una ejecución.

Para validar sintaxis sin red ni consumo de tokens:

```powershell
poetry run python -m py_compile "Grant-Radar-prueba.py"
```

## 7. Credenciales y confidencialidad

- Nunca incluir claves reales en documentación, respuestas, logs, diffs, pruebas
  o archivos destinados a GitHub.
- No leer, mostrar ni copiar el contenido de `API KEYs.txt` salvo petición expresa
  y justificada del usuario.
- Actualmente las variables `CLAUDE_API_KEY` y `GITHUB_TOKEN` están juntas en la
  Celda 2 para facilitar su sustitución manual.
- **Invariante desde el 18/08/2026:** la Celda 2 llama a `load_dotenv()` y lee
  ambas variables con `os.environ.get(..., "Placeholder")`. El sitio
  recomendado para credenciales reales es un archivo `.env` local (ver
  `.env.example`), que está en `.gitignore` y nunca debe subirse a git. Pegar
  la clave directamente en el script sigue funcionando como respaldo, pero ya
  no es la vía preferida. `API KEYs.txt`, `.env`, `debug.log` y
  `convocatorias.json` deben permanecer siempre en `.gitignore`; no quitarlos
  sin sustituir el control equivalente. El hook `.git/hooks/pre-commit`
  (que ejecuta `scripts/Comprobar credenciales antes de commit.ps1`) bloquea
  cualquier commit cuyos archivos "staged" contengan un patrón de clave real;
  no desactivarlo salvo autorización expresa del usuario.
- El valor `Placeholder` es deliberadamente inválido.
- La clave de Claude válida debe empezar por `sk-ant-`, no tener espacios externos
  y tener al menos 50 caracteres.
- El token de GitHub debe comenzar por `github_pat_` o `ghp_` y tener al menos
  40 caracteres.
- Tras una ejecución manual con secretos reales, el usuario suele restaurar ambos
  valores a `Placeholder` antes de guardar o compartir el código.
- No afirmar que una credencial es válida solo por su forma. La validación real
  ocurre al autenticar contra el servicio correspondiente.

## 8. Reglas para modificaciones

Antes de editar:

1. Inspeccionar el código y los artefactos relacionados.
2. Separar hechos observados, inferencias y recomendaciones.
3. Identificar efectos sobre caché, coste de Claude, esquema JSON, frontend y
   publicación.
4. Evitar soluciones ad hoc por título, URL o identificador, excepto catálogos de
   respaldo explícitamente curados y trazables.

Al editar:

- Trabajar sobre `Grant-Radar-prueba.py` salvo instrucción contraria.
- Preservar comentarios de celdas y el enfoque Windows local.
- Preferir API oficial; usar Playwright cuando la API no exista o no sea útil.
- Mantener comportamiento conservador ante errores: no publicar resultados
  incompletos cuando falle Claude.
- No hacer llamadas a Claude ni publicar en GitHub durante pruebas de código sin
  autorización expresa.
- No modificar backups o archivos ajenos a la tarea.

Después de editar:

1. Ejecutar `py_compile`.
2. Probar funciones deterministas con datos sintéticos.
3. Usar `--no-claude` para integración de fuentes cuando sea necesario.
4. Utilizar `--max-claude` solo con autorización, indicando que consume tokens y
   modifica la caché.
5. Verificar compatibilidad entre el JSON y `index.html` si cambia el esquema.
6. Informar con precisión qué archivos se modificaron y cuáles no.

## 9. Invariantes operativas

- `--no-claude` no debe llamar a Claude, modificar caché IA, generar JSON ni
  publicar. Sí puede actualizar las cachés documentales públicas BDNS y de otras
  fuentes oficiales.
- `--max-claude` puede modificar la caché, pero no debe generar ni publicar JSON.
- `--force-reanalysis` solo puede funcionar con `--max-claude` y uno o más
  `--claude-match`; debe ignorar la caché exclusivamente para esas coincidencias.
- `--replay-hold-report` no debe llamar a Claude ni modificar la caché principal,
  la auditoría, `convocatorias.json` o GitHub Pages.
- Una ejecución interrumpida debe conservar en caché todas las convocatorias
  completadas antes del fallo y registrar el consumo parcial disponible.
- Una clave Claude inválida debe detener la ejecución antes de recopilar o escribir.
- Ningún modo puede iniciar Claude si `claude_safety_preflight()` supera 200
  análisis seleccionados o 5 USD de coste superior estimado. El control cuenta
  también los reanálisis forzados porque generan el mismo consumo.
- Un token GitHub inválido debe omitir la publicación, no impedir guardar el JSON
  local tras una ejecución completa válida.
- Los contadores de convocatorias vigentes deben excluir `deadline_days <= 0`.
- Las fechas previstas o no confirmadas deben quedar señalizadas.
- Los catálogos estáticos deben indicar su procedencia y carácter de respaldo.
- La auditoría debe permitir explicar inclusiones, exclusiones y fallos de cobertura.

## 10. Riesgos conocidos

- Cambios de HTML pueden romper selectores Playwright.
- Fuentes SPA o protegidas pueden requerir navegación, espera de JavaScript o
  interceptación de respuestas de red.
- Los catálogos estáticos envejecen y deben tratarse como último respaldo.
- Cambiar versiones puede invalidar muchos análisis y elevar el coste de Claude.
- Si falla la publicación, GitHub Pages puede seguir mostrando un JSON antiguo.
- El dashboard puede quedar desalineado si el backend añade campos sin adaptar el
  frontend.
- La calidad del modelo no sustituye la comprobación determinista de fechas,
  elegibilidad expresa, URLs y coherencia interna.

## 11. Coste de Claude

**Calibración vigente: 20/08/2026, sobre una ejecución completa de 76
análisis.** Es la primera con el extractor v7 y la evidencia enriquecida
(sección 40), y sustituye a la del 03/08/2026, que se hizo con una muestra de
dos convocatorias.

Por convocatoria (dos llamadas, extracción y evaluación):

| Métrica | Valor |
|---|---|
| Entrada | 6.482-26.353 tokens (media 12.610) |
| Salida | 1.202-6.483 tokens (media 2.590) |
| Coste mediano | 0,0242 USD |
| Coste medio | 0,0256 USD |
| Percentil 95 | 0,0464 USD |
| Máximo observado | 0,0550 USD |

Ejecución completa de 76 convocatorias: **1,83 USD reales**, 1.095.295 tokens.

Qué cambió respecto a la calibración anterior: la media apenas se movió
(0,0265 → 0,0256), pero **la cola era mucho más larga de lo que sugería la
muestra de dos**. El máximo observado, 0,0550 USD, supera el 0,035 que la
barrera usaba como "extremo superior". Una barrera calibrada con la media no
protege de la cola, que es justo de lo que debe proteger.

Límite operativo vigente:

- Máximo nominal: 200 convocatorias nuevas, modificadas o forzadas por
  ejecución.
- Máximo de coste superior estimado: 5 USD.
- Coste superior unitario usado por la barrera: **0,047 USD**, el percentil 95
  redondeado hacia arriba (antes 0,035).
- Máximo efectivo actual: **106 convocatorias**, porque 107 estiman 5,029 USD
  (antes 142).
- La previsión que muestra el pipeline usa la media observada como valor
  central y el rango p05-p95 como horquilla.
- Sigue siendo una barrera presupuestaria previa basada en lo observado, no una
  garantía contractual sobre la factura de Anthropic.

Aviso metodológico, aprendido el 20/08/2026: una proyección hecha con tres
convocatorias elegidas por ser las más difíciles sobrestimó el coste total en
un 60 % (2,92 USD proyectados frente a 1,83 reales). Para calibrar hace falta
una muestra representativa, no una muestra de casos extremos.

## 12. Criterio de finalización

Una modificación se considera terminada cuando compila, se ha validado sin gastos
innecesarios, conserva los invariantes, mantiene trazabilidad, no expone secretos y
se han comunicado los efectos sobre caché, JSON, frontend, costes y publicación.

## 13. Estado operativo a 07/08/2026 tras ampliación de fuentes y filtro BDNS

Versiones activas:

- Perfil: `kalfrisa-2026-07-v4`.
- Extractor: `facts-2026-08-v6-eligible-actions`.
- Evaluador: `fit-2026-08-v5-size-consortium`.
- Prompt: `2026-08-v9-eligible-actions`.
- Esquema de caché: 3.
- Esquema de auditoría: 2.
- Esquema público del código: 3, compatible con JSON de entrada 2 y 3.

La caché contiene tres convocatorias válidas con esas mismas versiones:

1. `HORIZON-CL5-2026-09-D4-08` — Full-scale demonstration of heat upgrade
   solutions in industrial processes.
2. Programa INNOVAE, consolidado desde IDAE y dos documentos BOE.
3. CDTI Proyectos de I+D — Línea PID, ventanilla abierta.

La ejecución forzada de INNOVAE y Línea PID del 04/08/2026 funcionó:

- Reanálisis forzado desde caché: 1.
- Convocatoria nueva: 1.
- Cuatro peticiones HTTP 200.
- 29.233 tokens totales.
- Coste estimado: 0,0516 USD.
- No generó ni publicó `convocatorias.json`.

Resultados cualitativos actuales:

- INNOVAE: `pursue`, elegible, sin revisión obligatoria. La línea industrial
  reconoce CNAE división 28, ahorro mínimo 20 %, coste mínimo 100.000 EUR,
  ayuda máxima 2 MEUR y consorcio no obligatorio.
- Horizon térmico: `pursue`, elegibilidad aún desconocida por falta de condiciones
  generales de beneficiarios, presupuesto y consorcio en la evidencia recuperada.
  Las expresiones residuales `o tamaño` y `una vez publicado` se corrigen al cargar
  la caché mediante reglas deterministas, sin nueva llamada a Claude.
- CDTI PID: `manual_review`, confianza baja por insuficiencia de la ficha estática:
  faltan tipos de entidad, geografía, deadline, TRL, presupuesto máximo y temas.
  La evidencia sí indica modalidad individual, financiación hasta 85 % y coste
  mínimo de 175.000 EUR; el consorcio no debe tratarse como obligatorio.

Estado de artefactos:

- `grant_radar_cache.json`: 60 análisis presentes; no se ha invalidado ni
  modificado durante la ampliación.
- `grant_radar_audit.json`: normalizado, íntegro y con histórico de ejecuciones.
- `convocatorias.json`: generado el 04/08/2026, esquema 2 y 60 convocatorias. Se
  conserva deliberadamente sin regenerar hasta autorizar una ejecución completa.
- PowerUp NetZero y el identificador 14703 no aparecen en el JSON, la caché ni la
  auditoría anteriores a esta ampliación.
- La validación `--no-claude` posterior a la ampliación descubrió PowerUp desde
  ECCP antes de Claude, con cierre 15/09/2026 y mecanismo `cascade`. Detectó 864
  registros antes del filtro, rechazó 250 de forma determinista y conservó 614
  (149 `retain` y 465 `ambiguous`). Duración de recopilación: 622,89 segundos.
  Esa ejecución mostró dos noticias históricas EEN sin plazo; el parser final ya
  exige un deadline confirmado y una prueba local impide que vuelvan a publicarse.
- La validación integral del 06/08/2026 detectó 836 convocatorias consolidadas.
  Antes del último ajuste territorial produjo 81 candidatas a Claude:
  `retain=73`, `ambiguous=8`, `hold_manual=455` y `reject=300`. BDNS aportó 760
  registros a la matriz; solo cinco sobrevivieron, entre ellos INNOVAE, la
  compensación de CO2 y una oportunidad de descarbonización que entonces se
  consideraba comercialmente como proveedor; esa última ruta ya está excluida.
  El ajuste final clasifica también administraciones `OTROS` con región NUTS
  concreta como subnacionales: se espera que dos candidatos adicionales de
  Córdoba y Granada pasen a espera/rechazo, dejando tres BDNS antes de Claude.
  Este último efecto está cubierto por pruebas sintéticas, pero no justifica otra
  descarga integral por sí solo.
- PowerUp permaneció visible antes de Claude con cierre 15/09/2026. INNOVAE se
  conserva con cierre 18/11/2026; la evidencia manufacturera consolidada evita
  que un metadato NACE B incompleto provoque un falso descarte.
- La ejecución completa del 13/08/2026 generó 72 convocatorias: 37 relevantes y
  35 descartadas antes de la salvaguarda de consorcio. PowerUp había sido
  descartada por confundir la obligación de presentar un consorcio con una
  exclusión de Kalfrisa como entidad individual. La regla general anterior se
  aplicó al JSON local sin Claude: PowerUp pasó a `manual_review`, elegibilidad
  `unknown` por la verificación jurídica de PYME y rol `consortium_partner`. El
  JSON local queda con 38 relevantes y 34 descartadas; este ajuste no se ha
  publicado.
- La auditoría de los dos intentos del 13/08/2026 se reconstruyó desde las marcas
  temporales y el consumo conservado en caché. El intento abortado completó cinco
  análisis y efectuó 11 peticiones conocidas, con 67.245 tokens y 0,125613 USD;
  la reanudación completó 34 análisis y efectuó 70 peticiones conocidas, con
  555.313 tokens registrados y 0,889441 USD. En esta última hubo dos respuestas
  inválidas cuyo `usage` se perdió con la implementación anterior: los contadores
  de peticiones y reintentos están corregidos, pero tokens y coste permanecen
  marcados como límite inferior. Desde el cambio de código, esos reintentos sí
  quedan contabilizados antes de validar la salida.
- La salvaguarda de composición se aplicó sin Claude a
  `HORIZON-MISS-2027-07-CLIMA-CIT-CCRI-02`: la organización local de gestión del
  agua es un miembro obligatorio del consorcio, no el único tipo de beneficiario.
  La oportunidad pasó a `manual_review`, elegibilidad `unknown` y rol
  `consortium_partner`. El JSON local queda con 39 relevantes y 33 descartadas;
  no se ha publicado.
- La revisión documental de los tres descartes dudosos concluyó: GRAPPA admite
  directamente proveedores de tecnología y sobrevivió a todos los prefiltros;
  fue la evaluación de encaje de Haiku la que la descartó al interpretar la
  valorización agroalimentaria como un ámbito comercial marginal. El usuario ha
  confirmado que la línea de valorización sí es de interés para Kalfrisa, por lo
  que esa decisión queda pendiente de corregir con una regla general y no por el
  nombre de la convocatoria. Los Grupos Operativos AEI de Madrid distinguen miembros del
  sector primario y miembros cuya actividad principal es I+D/innovación, pero no
  consta que Kalfrisa cumpla ninguna de esas dos condiciones y no debe recuperarse
  automáticamente. El plan de suelo industrial de Zaragoza es jurídicamente
  compatible con una ampliación propia y se confirma como falso negativo.
- La salvaguarda general de inversión propia recupera ese plan sin Claude como
  `watch`, con encaje mínimo 55 y papel de líder, porque la ayuda financia suelo o
  capacidad industrial de la propia Kalfrisa. Exige una necesidad empresarial
  real antes de solicitarla, pero no exige que la inversión forme parte de un
  proyecto de I+D. No se ha cambiado la versión del perfil ni se ha invalidado la
  caché; la regla se aplica tanto a análisis futuros como a entradas ya cacheadas.
- La salvaguarda general de valorización recupera GRAPPA sin Claude como `watch`,
  encaje 60, accionabilidad 45, elegibilidad `unknown` y papel
  `technology_partner`. La incertidumbre de PYME permanece; la regla solo corrige
  la falsa equiparación entre participación tecnológica financiada y venta de
  equipos a un tercero.
- El filtro frontend de fuente usa una clave canónica para tolerar variantes como
  `BOE/MITECO` y `BOE / MITECO`; sus contadores representan convocatorias
  consolidadas, no documentos brutos. La opción activa conserva el contador en
  blanco. El menú de descarga separa visualmente formato y descripción.
- El panel `Fuentes monitorizadas` distingue volumen bruto y resultado público:
  muestra `registros recuperados → convocatorias consolidadas`. El desplegable
  `Fuente` sigue mostrando únicamente las consolidadas que puede filtrar. El
  backend publica `raw_count` y `consolidated_count`, manteniendo `count` como
  alias retrocompatible del volumen bruto; el frontend calcula el consolidado a
  partir de las tarjetas cuando carga un JSON anterior.
- Las salvaguardas vigentes se aplicaron al JSON local del 13/08/2026 sin Claude,
  red ni publicación. El resultado contiene 72 convocatorias: 41 relevantes y
  31 descartadas. Las fuentes muestran, entre otros, BDNS `650 → 34`, ECCP
  `6 → 4`, EEN `1 → 0` y BOE/MITECO `2 → 1`. `generated_at` no se alteró porque
  no hubo una nueva recopilación de datos.
- El dashboard admite `opportunity_role` y etiquetas visibles para
  `consortium_partner`, `cluster_route` y apertura de centro. El papel comercial
  indirecto se ha eliminado y no se conserva por compatibilidad. No se ha
  regenerado todavía el JSON.
- GitHub Pages: tampoco se ha actualizado durante las pruebas limitadas.

Siguiente ejecución completa esperada, si las fuentes y hashes no cambian:

- Reutilizar las entradas cuyo hash factual no cambie.
- Informar antes de ejecutar de las nuevas convocatorias y hashes que exigirían
  llamadas a Claude, junto con una estimación de coste.
- Guardar progreso después de cada convocatoria completa.
- Generar `convocatorias.json` solo al finalizar todos los análisis.
- Intentar publicar en GitHub únicamente si el token tiene formato válido.

Trabajo pendiente recomendado antes o después de la ejecución completa:

1. Enriquecer la evidencia CDTI PID desde la página oficial para reducir revisión
   manual por datos ausentes; evitar añadir hechos ad hoc sin fuente trazable.
2. Revisar si los textos narrativos sobre consorcios opcionales deben conservarse
   como recomendación estratégica o eliminarse cuando parezcan un requisito.
3. Evaluar la calidad del conjunto completo y recalibrar costes con una muestra
   mayor que las pruebas actuales.
4. Comparar el esquema JSON final con `index.html` antes de modificar el diseño.

Estado del piloto `hold_manual` a 10/08/2026:

- Piloto v1 completado: 20 casos, 19 llamadas Haiku, 105.008 tokens y coste
  estimado de 0,127212 USD. Resultado bruto: 6 `reject`, 2 `retain` y 12
  `unresolved`; una resolución fue determinista.
- La revisión detectó un falso rechazo territorial en BDNS 692325: la cita solo
  ubicaba la actuación en Baleares y no exigía un centro existente. También se
  aceptó indebidamente como prueba de cierre una cita sobre plazo de ejecución.
  Por tanto, ninguna decisión v1 puede entrar en producción.
- Se corrigió el cálculo de antigüedad, se dejó de tratar `abierto` como ventanilla
  permanente y se adelantaron incompatibilidades intrínsecas. La primera medición
  bajó los holds de 373 a 117 sobre 736 registros.
- Piloto v2 completado: 20 llamadas, 105.264 tokens y 0,1297 USD. Produjo un
  rechazo territorial respaldado y 19 `unresolved`. El 5 % de resolución es
  insuficiente para integración productiva.
- El análisis v2 descubrió que los PDF de `documentos` se recuperan por su ID y
  no traen URL en el detalle. V3 integra ese endpoint, fechas `datPublicacion`,
  plazos naturales/hábiles/meses y tolerancia a cortes de palabra en PDF.
- La medición final v3 recuperó 679 registros bajo la política anterior: 576 `reject`, 98 `hold_manual`,
  cuatro `retain` y un `ambiguous`. Los holds son 33 de vigencia, 64 territoriales
  y uno de proveedor; trece tienen etiquetas tecnológicas directas. Los 679
  registros conservan URL documental y doce deadlines calculados están marcados
  como estimados.
- V3 se ejecutó con Haiku el 10/08/2026: 20 casos, 18 llamadas, 212.900 tokens y
  0,238344 USD; produjo tres `reject`, dos `retain` y quince `unresolved`. Sus
  artefactos se archivarán automáticamente al iniciar v4.
- La reentrada productiva está activa mediante
  `resolve_bdns_holds_for_pipeline()`. Un `retain` incorpora solo el hecho
  verificado y vuelve a ejecutar toda la matriz; un `reject` conserva
  trazabilidad propia y un `unresolved` pasa a `ambiguous` para continuar al
  analizador general, nunca a descarte ni a revisión humana en tiempo de
  ejecución. Las bases recuperadas forman parte de la evidencia factual y de su
  hash, por lo que una convocatoria enriquecida puede requerir análisis nuevo.
- Cambio táctico del 10/08/2026: se excluye cualquier cliente comercial
  indirecto, incluso cuando sus equipos sean gasto elegible. Se conservan PAIP,
  INNOVAE y otras inversiones propias sin I+D cuando Kalfrisa es beneficiaria,
  así como consorcios o clústeres que le asignen actividad, costes, presupuesto o
  un piloto ejecutado directamente.
- La validación real BDNS de v4, sin Claude, recuperó 656 candidatas de 2.071
  inventariadas: 565 `reject`, 87 `hold_manual`, tres `retain` y una `ambiguous`.
  Veintidós se excluyeron como `indirect_commercial_role_only`; INNOVAE se
  conservó como `direct_beneficiary` por inversión propia. Las dos ayudas FNEE
  de La Rioja siguen en espera territorial en el metadato inicial y requieren la
  evidencia documental ya observada para confirmar el centro previo. No apareció
  una convocatoria PAIP activa; su salvaguarda se valida mediante fixtures.
- La repetición determinista del informe v3, sin nuevas llamadas a Claude,
  produjo 12 `reject`, siete `ambiguous` y un `retain`. Ocho de las 18 llamadas
  históricas, equivalentes a 75.828 tokens, se habrían evitado con las reglas
  actuales: empleo, formación, vivienda, premios, economía social y ayudas
  nominativas. El primer barrido documental detectó dos falsos rechazos por
  términos incidentales dentro de bases largas; por ello el segundo control usa
  una lista reducida de expresiones autosuficientes. IVACE 914587 y la línea
  financiera 889461 no se excluyen por esas menciones; la ayuda residencial
  905892 sí permanece rechazada por su objeto financiado.
- La única iteración sobre los cuatro `consortium_role_unverified` confirmó que
  916134, 914145, 904630 y 924030 eran concesiones directas instrumentales, no
  consorcios abiertos a socios. El parser reconoce ahora el calificativo oficial
  `instrumental` y los rechaza como `not_open_call` antes de evaluar el papel.
  No se amplió el vocabulario de consorcios; un caso realmente dudoso sigue a
  Haiku mediante la reentrada automática.
- La validación integral del 10/08/2026 tras activar la reentrada consolidó 732
  convocatorias. El prefiltro inicial produjo 72 `retain`, ocho `ambiguous`, 579
  `reject` y 73 holds BDNS intermedios. La recuperación de 245 documentos
  (89.079.839 bytes, 44 errores no bloqueantes) resolvió cinco holds como
  `reject`, uno como hecho positivo que reentró por la matriz y dejó 67 sin hecho
  local; el resultado final fue 68 `ambiguous`, cero revisiones humanas y 148
  candidatas totales al pipeline general. La ejecución duró 775 segundos, de los
  cuales 522 correspondieron a recopilación de fuentes.
- PowerUp NetZero se confirmó de nuevo desde ECCP con cierre 15/09/2026,
  mecanismo `cascade` y decisión local `retain`. INNOVAE se confirmó desde IDAE
  con cierre 18/11/2026 y decisión `retain`.
- Las 68 BDNS ambiguas no son una cantidad pequeña: antes de autorizar una
  ejecución completa con Claude debe revisarse la previsión exacta de caché y
  coste. `--no-claude` calcula ahora `cache_hits`, hashes nuevos/cambiados, número
  de llamadas y horquilla de coste en `RUN_DIAGNOSTICS["claude_forecast"]`.
- Los holds de vigencia usan internamente `deadline_days=1` solo para atravesar
  el filtro defensivo. `_deterministic_call_status()` los mantiene como
  `unknown` y `_public_deadline_values()` publica `deadline=null`; el frontend
  muestra `Sin fecha`, los ordena detrás de cierres conocidos y nunca los cuenta
  como urgentes. No reutilizar el centinela como fecha o plazo real.
- El informe puntual `bdns_hold_replay_report.json` se eliminó después de trasladar
  sus conclusiones a esta documentación y a los fixtures; el comando puede
  recrearlo si vuelve a ser necesario.
- Capa estructurada validada el 11/08/2026 sobre 657 candidatas BDNS, antes de
  activarla. La población de referencia contenía 577 exclusiones, 76 holds y
  cuatro casos que superaban la matriz. Sin alterar ni recuperar descartes, la
  capa coincidió con 66 exclusiones previas (11,44 %): 22 de primario, 17 de
  empleo/desarrollo, 20 de objetos específicos, seis anualidades históricas y un
  beneficiario público. Sobre los holds identificó 22 exclusiones adicionales:
  ocho primarias, seis laborales/desarrollo, siete específicas y una pública.
  Los dos casos previamente retenidos que marcó eran duplicados de una ayuda
  exclusiva a industrias agroalimentarias de Aragón; conforme al alcance vigente,
  Kalfrisa solo sería proveedor y se excluyen. INNOVAE, PAIP, energía, residuos,
  suelo industrial, economía circular y transición energética no activaron la
  capa. El backtest fue puntual y no forma parte del pipeline final, que aplica
  las reglas secuencialmente.
- La caché documental BDNS se probó con 157 entradas y 4.748.617 bytes. El primer
  llenado procesó 225 solicitudes documentales y 91.999.444 bytes de red; la
  repetición obtuvo 161 aciertos, 68 solicitudes y 8.679.169 bytes, una reducción
  de tráfico del 90,6 %. Los 47 errores documentales siguieron siendo no
  bloqueantes. La caché no incluye landings mutables y no altera el hash por sí
  sola: el hash factual cambia únicamente si el texto oficial incorporado cambia.
- La validación integral `--no-claude` del 11/08/2026 consolidó 733 convocatorias.
  El prefiltro inicial produjo 70 `retain`, ocho `ambiguous`, 601 `reject` y 54
  holds BDNS. La reentrada convirtió 51 holds en `ambiguous` y rechazó tres;
  quedaron 129 candidatas únicas, frente a 148 en la ejecución anterior (−19,
  −12,84 %), sin revisión humana. La diferencia se reconcilia así: 19 holds y dos
  retenidos agroindustriales pasaron a descarte inicial; dos de esos holds ya se
  rechazaban después de leer bases y apareció una candidata BDNS adicional en el
  inventario diario, por lo que la reducción final neta es 19.
- La misma ejecución reutilizó 107 documentos BDNS y realizó 49 descargas; el
  tráfico documental real fue 7.658.540 bytes frente a 89.079.839 en la ejecución
  anterior (−91,4 %). Los 72.424.376 `source_bytes` incluyen el tamaño lógico de
  documentos servidos desde caché y no representan tráfico de red.
- De las 129 candidatas, 58 coinciden con la caché IA y 71 son nuevas o tienen
  hash factual distinto: 142 llamadas previstas, coste central 1,8815 USD y
  horquilla 1,2780-2,4850 USD. Esto es solo una previsión; no se llamó a Claude.
- PowerUp NetZero permaneció visible desde ECCP con cierre 15/09/2026 y mecanismo
  `cascade`; INNOVAE permaneció con cierre 18/11/2026. ECCP volvió a seleccionar
  profundidad 1. La ejecución tardó 719,9 segundos, con 570,87 segundos de
  recopilación.
- Permanecen 53 candidatas con procedencia BDNS. La salida revela variantes
  todavía no cubiertas de forma determinista, entre ellas `bonos de comercio`,
  líneas de conciliación laboral, formulaciones de `Pyme Global`, ayudas
  culturales y títulos para entidades locales con orden sintáctico distinto.
  No ampliar vocabulario por simple coincidencia: revisar esas familias contra
  positivos y aplicar expresiones autosuficientes antes de una ejecución Claude.
- La caché principal y `convocatorias.json` permanecen intactos. La auditoría sí
  registra las ejecuciones v1, v2 y v3; GitHub Pages no se ha actualizado.
- La segunda capa residual se validó el 11/08/2026 en otra ejecución
  `--no-claude`. Consolidó las mismas 733 convocatorias y produjo inicialmente
  69 `retain`, ocho `ambiguous`, 610 `reject` y 46 holds BDNS. La reentrada dejó
  43 holds como `ambiguous` y rechazó tres; el inventario final contiene 120
  candidatas, nueve menos que la primera capa y 28 menos que la referencia de
  148 (−18,92 % acumulado). Los nueve descartes adicionales fueron ocho variantes
  BDNS autosuficientes —bonos de comercio, conciliación, Pyme Global, cultura y
  beneficiarios locales— y una call europea fusionada Horizon/EEN cuyo título
  era exclusivamente educativo y de salud mental, sin señal tecnológica.
- La procedencia visible de las 120 candidatas es Horizon 64, BDNS 45, ECCP seis,
  CDTI cinco e IDAE una; las cifras se solapan cuando una convocatoria tiene más
  de una fuente de descubrimiento. PowerUp NetZero e INNOVAE permanecieron
  visibles. El inventario de auditoría registró 58 `hit`, 62 `new` y cero
  `content_changed`; por razón de inclusión, 76 superaron el prefiltro común,
  una conservó inversión propia, una requirió análisis semántico BDNS y 42
  siguieron ambiguas tras recuperar evidencia oficial.
- La previsión posterior a la segunda capa es de 62 candidatas sin caché y 124
  llamadas, con coste central estimado de 1,6430 USD y horquilla de
  1,1160-2,1700 USD. Frente a la primera capa se evitan nueve análisis, 18
  llamadas y unos 0,2385 USD centrales. No se llamó a Claude, no se modificó la
  caché IA, no se regeneró `convocatorias.json` y no se publicó. Solo se actualizó
  la auditoría, que conserva el inventario completo de las 120 candidatas dentro
  de los diagnósticos de la ejecución.
- La revisión offline del inventario de 120 candidatas, sin red ni Claude,
  señaló 55 casos para una futura evaluación determinista, no para descarte
  inmediato: 36 Horizon —medio marino/política ambiental, transporte, edificios,
  digital/IA/cuántica genérica y generación no térmica—, 16 BDNS —empleo,
  emprendimiento local externo, anualidades municipales históricas, movilidad
  urbana y financiación sin inversión— y tres ECCP sectoriales o territoriales.
  El hallazgo principal es que una etiqueta genérica como `digital_thermal` o
  `energy_efficiency` podía neutralizar un alcance excluido que el propio
  `_hard_out_of_scope()` ya había identificado.
- La matriz común se implantó después de construir 18 fixtures positivos y
  negativos y mantener recall del 100 % sobre las oportunidades no descartadas
  del JSON vigente. La primera ejecución `--no-claude` eliminó 29 Horizon y dejó
  91 candidatas. Seis casos adicionales sobrevivieron por etiquetas incidentales;
  los seis ya constaban como `discard_out_of_scope` en la caché y el JSON. Tras
  incorporarlos a los fixtures, la ejecución final consolidó 733 registros,
  rechazó 645 en la primera pasada y dejó 85 candidatas: Horizon 29, BDNS 44,
  ECCP seis, CDTI cinco e IDAE una como fuentes principales.
- Frente al inventario de 120 se eliminaron 35 candidatas Horizon (−29,17 %).
  Veinticinco ya tenían caché y diez requerían análisis nuevo. La previsión final
  es de 52 análisis, 104 llamadas, coste central 1,378 USD y horquilla
  0,936-1,820 USD. La barrera de 5 USD permite la ejecución, pero Claude sigue
  sin autorización. PowerUp NetZero, INNOVAE, HORIZON-CL5-2026-09-D4-08 y
  Destination Earth permanecen. Las 16 familias BDNS y tres ECCP señaladas en el
  análisis offline no se modificaron en esta iteración.
- Se activó la barrera presupuestaria previa a Claude: máximo nominal de 200
  análisis y máximo superior estimado de 5 USD. Con 0,035 USD por análisis, el
  máximo efectivo era entonces 142 (**recalibrado a 106 el 20/08/2026**, sección
  42.3). La ejecución se audita y termina antes de la
  primera llamada si excede cualquiera de los dos límites.
- Capa residual ECCP/BDNS validada el 12/08/2026 sin Claude. La regla ECCP
  eliminó `Dual-Use Drones Innovative Programme` por sector restringido y
  producto propio obligatorio sin conexión tecnológica, e `IMPACT NETWORKS`
  por acceso exclusivo a intermediarios sin apoyo a empresas miembro. Conservó
  FutureProof Textiles por su vía expresa para proveedores tecnológicos y de
  maquinaria. Estas decisiones derivan de requisitos formales reutilizables, no
  de los nombres de las calls.
- Se añadieron seis fixtures ECCP y catorce BDNS, positivos y negativos. BDNS
  cubre objeto laboral, listas exhaustivas sin empresa, presencia local previa,
  nuevas implantaciones con duración desconocida, convocatorias multilínea y
  financiación de inversión productiva. Las reglas locales inspeccionan el texto
  completo ya descargado; el límite de extractos se aplica solo a la evidencia
  enviada a Claude, por lo que no puede ocultar el objeto jurídico al prefiltro.
- La medición integral final del 12/08/2026 consolidó 734 registros y dejó 72
  candidatas principales: Horizon 29, BDNS 33, ECCP cuatro, CDTI cinco e IDAE
  una. El resumen por conectores muestra 34 BDNS porque INNOVAE también se
  descubre allí y después se fusiona bajo IDAE. Frente a la referencia de 85 se
  eliminaron dos ECCP y once BDNS; cuatro anualidades de actividades ambientales
  escolares de Ondarroa y el objeto laboral de Investigo se rechazaron tras leer
  las bases completas.
- En esa medición había 33 `hit` y 39 candidatas nuevas/cambiadas: 78 llamadas
  previstas, coste central 1,0335 USD y horquilla 0,7020-1,3650 USD. PowerUp
  NetZero, INNOVAE, HORIZON-CL5-2026-09-D4-08, FutureProof Textiles, Rianxo, San
  Fernando y la financiación SGR permanecieron. No se llamó a Claude, no se
  modificó la caché IA, no se regeneró `convocatorias.json` y no se publicó.
- La comprobación final ejecutó `py_compile`, `poetry check` y 98 pruebas
  `unittest`; todas finalizaron correctamente. La integración tardó 514 segundos,
  con 452,72 segundos de recopilación.
- Frontend revisado el 13/08/2026. Entre 821 y 1.500 px la barra de filtros usa
  dos filas antes de comprimir contenido; todos los chips permanecen completos y
  `Cualquier temática` evita confundir el selector temático con `Fuente: Todas`.
  El selector `Fuente` incorpora dentro de su propio rectángulo un icono SVG de
  filtros de trazo fino y no introduce recursos raster.
- El resumen superior deja de usar alturas insuficientes: a 1.080 px las tres
  métricas ocupan una fila propia y mantienen visibles etiqueta, valor y nota.
  `Convocatorias abiertas`, `Descartadas` y `Marcadas` incluyen ayuda contextual
  accesible por hover, foco, clic y táctil. Los cuatro tooltips de ordenación
  comparten el mismo comportamiento y Escape los cierra incluso si el puntero
  permanece sobre el botón.
- Los gradientes ornamentales se retiraron del fondo, tarjetas, cabeceras y
  barras; `Oportunidades de alto encaje` y `Cierre más próximo` conservan colores
  corporativos planos. El único efecto decorativo complejo es el radar CSS del
  encabezado `Grant-Radar`, centrado detrás del logotipo circular y desactivado
  cuando se solicita movimiento reducido.
- Un único control `Descargar` ofrece XLSX y CSV y ambos exportan exclusivamente
  `getFiltered()`. Priorizan campos de negocio —plazo, elegibilidad, presupuesto,
  financiación, TRL, consorcio, resumen, acción y evidencias—, omiten contadores
  internos de tokens y neutralizan fórmulas. CSV usa UTF-8 y `sep=;`. El XLSX se
  genera localmente sin dependencias ni red, con cabecera corporativa, autofiltro,
  primera fila inmovilizada, texto ajustado, bandas alternas y anchos semánticos.
- La validación del frontend del 13/08/2026 comprobó los menús con teclado, el
  centrado del radar a 390 y 1.366 px, ausencia de desbordamiento horizontal y la
  integridad ZIP/OpenXML del XLSX. `py_compile` y las 101 pruebas `unittest`
  finalizaron correctamente, sin ejecutar fuentes ni llamar a Claude.
- Ajuste visual adicional del 13/08/2026: los fondos azul y rojo del resumen son
  aproximadamente un 12 % más claros; el raster del logotipo se recorta mediante
  máscara circular sin alterar el archivo incrustado; y el radar pasa de cuatro a
  seis anillos dentro de un diámetro de 220 px. El haz reduce su alfa de 0,24 a
  0,21 y los anillos también bajan ligeramente su contraste.
- El pie muestra `Última actualización de datos` a partir de `generated_at` o
  `last_updated` del JSON, con fecha y hora locales y un elemento `time` cuyo
  atributo `datetime` conserva el instante ISO. En modo demostración o ante una
  fecha inválida indica que la actualización no está disponible; nunca sustituye
  el dato por la hora de apertura del navegador.
- La validación posterior ejecutó `py_compile` y 103 pruebas `unittest`; todas
  finalizaron correctamente. Incluye comprobaciones de color, máscara circular,
  seis anillos, centrado responsive y fecha ISO del pie.
- Corrección visual final del radar del 13/08/2026: su centro se desplaza solo
  0,8 px a la izquierda respecto a la posición CSS anterior, el 20 % del ajuste
  inicial de 4 px. Al medir cajas DOM aparece una separación de 1,8 px porque el
  encabezado añade su borde de 1 px entre sistemas de referencia. El borde
  circular independiente permanece eliminado. Los seis anillos recuperan el paso original de 24 px y alcanzan un
  radio exterior de 144 px dentro de un diámetro de 288 px; por tanto, la
  diferencia entre radios consecutivos es constante sin comprimir la figura.

## 14. Estado operativo a 13/08/2026 tras revisar taxonomía y estados pendientes

- La taxonomía tecnológica mantiene categorías fijas, pero separa tres funciones:
  `TECH_TAG_STRONG_TERMS` asigna una categoría por evidencia autosuficiente;
  `TECH_TAG_CONTEXTUAL_TERMS` exige contexto industrial o térmico próximo; y
  `TECH_DISCOVERY_TERMS` solo amplía inventarios, sin puntuar, seleccionar socios
  ni neutralizar exclusiones. `TECH_TAGS` sigue siendo el contrato combinado que
  consumen el esquema, el frontend y Haiku.
- Se conservaron los términos históricos y solo se añadieron expresiones precisas:
  intercambiadores en procesos industriales o gases de combustión, procesos
  termoquímicos industriales, `waste-to-energy`, valorización energética o
  tratamiento térmico de residuos, gasificación de residuos o biomasa, IoT y
  analítica expresamente industriales o térmicos, y optimización energética
  industrial. `IoT`, `machine learning`, `data analysis`, `oxidación`,
  `gasification`, `WTE`, `heat exchange` y valorización genérica de biomasa no
  funcionan como señales aisladas.
- La regla de corrientes laterales no depende de una convocatoria: exige una
  formulación de valorización tecnológica de biomasa residual agroalimentaria.
  Conserva oportunidades como GRAPPA, donde el proveedor de tecnología es un
  participante financiado, pero no etiqueta estudios generales de flujos de
  biomasa. Vender equipos sin actividad, costes y resultados propios sigue fuera.
- `manual_review` ya no representa ausencia de presupuesto, elegibilidad o
  requisito de consorcio. Esos huecos pasan a `data_pending` y `data_gaps`; las
  alertas operativas quedan en `monitoring_flags`. `review_required` se reserva
  para una contradicción real entre modelo y salvaguarda determinista. El frontend,
  CSV y XLSX muestran por separado datos pendientes y contradicciones.
- La salvaguarda territorial posterior al modelo solo mantiene un descarte BDNS
  cuando los hechos contienen una región NUTS española distinta de Aragón y la
  razón prueba expresamente que la restricción hace inelegible a Kalfrisa. Una
  localización de proyecto o un territorio ambiguo no bastan.
- La segunda ejecución `--no-claude` del 13/08/2026, ya con la taxonomía final,
  consolidó 691 registros y dejó 62 candidatas: Horizon 19, BDNS 33, ECCP cuatro,
  CDTI cinco e IDAE una. Rechazó 619 casos inequívocos; 42 BDNS necesitaron
  evidencia adicional, de las que diez se resolvieron como rechazo local y 32
  continuaron como ambiguas para el análisis general. No existe cola humana.
- La comparación eliminó solamente `Understanding biomass flows in Europe`, que
  había recibido una etiqueta térmica injustificada. GRAPPA, PowerUp NetZero,
  INNOVAE y `Full-scale demonstration of heat upgrade solutions in industrial
  processes` permanecieron. El inventario final registra 59 `hit` y tres `new`;
  prevé seis llamadas y 0,0795 USD centrales, con horquilla 0,054-0,105 USD.
  No se llamó a Claude, no se modificó la caché IA y no se publicó.
- Las reglas vigentes se reaplicaron al `convocatorias.json` existente sin cambiar
  su fecha de datos: 72 tarjetas, 40 relevantes, 32 descartadas, 39 con datos
  pendientes y cero contradicciones. `review_queue` queda vacía y
  `data_gap_queue` contiene 39 entradas. No equivale a regenerar el JSON desde la
  recopilación de 62 candidatas ni a publicar ese inventario nuevo.
- El frontend se comprobó con Playwright en 912×368, 1.080×720, 820×900 y
  390×844: no hay desbordamiento horizontal y permanecen visibles la fuente, la
  búsqueda, la ayuda de ordenación, las métricas y los estados documentales.
- La validación final ejecutó `py_compile` y 125 pruebas `unittest`; todas
  finalizaron correctamente.

## 15. Estado operativo a 14/08/2026 tras cerrar la capa residual BDNS

- La segunda capa territorial reconoce requisitos documentales autosuficientes
  de presencia previa fuera de Aragón: establecimiento operativo, centro de
  trabajo o producción, domicilio social o fiscal y alta en el censo regional.
  No confunde la mera localización futura del proyecto con un centro preexistente
  y conserva las vías expresas de nueva implantación. La regla no contiene
  nombres de convocatorias, territorios, identificadores ni URLs.
- La capa común rechaza también objetos inequívocos de contratación indefinida o
  conversión de contratos temporales, cadenas de automoción, movilidad o
  vehículos y eficiencia energética cuyo uso final sean edificios terciarios.
  Estas expresiones no neutralizan oportunidades de proceso industrial, energía,
  residuos, valorización, depuración de gases o inversión productiva propia.
- Sobre las 32 candidatas BDNS ambiguas de referencia, la generalización resolvió
  13 rechazos deterministas: diez por presencia previa obligatoria fuera de
  Aragón, una ayuda laboral de localización y dos variantes de automoción o
  renovación de vehículos. Las 19 restantes siguen como `ambiguous` y llegarán a
  Haiku; la ausencia de evidencia nunca se convirtió en rechazo.
- La ejecución integral `--no-claude` consolidó 685 registros y dejó 49
  candidatas: Horizon 19, BDNS 20, ECCP cuatro, CDTI cinco e IDAE una como fuente
  principal. De 34 estados intermedios BDNS, 15 se resolvieron localmente como
  rechazo y 19 continuaron ambiguos; no existe cola humana. Permanecieron
  PowerUp NetZero, GRAPPA, INNOVAE, la demostración Horizon de recuperación de
  calor y la ayuda zaragozana para adquisición de suelo industrial.
- Se estabilizó el hash factual frente al reloj de fecha y hora que algunas sedes
  oficiales insertan en la landing de solicitud. Solo se normaliza ese reloj en
  documentos con papel `application_landing`; una fecha de cierre sigue
  invalidando la caché cuando cambia. Al cargar, las claves históricas se
  reindexan en memoria y una colisión conserva la entrada más reciente, sin
  escribir durante `--no-claude`.
- El análisis dirigido de tres candidatas realizó seis respuestas HTTP 200,
  consumió 45.750 tokens y estimó 0,0792 USD. Plan Radica quedó fuera por alcance
  laboral y territorial; Breña Baja resultó inelegible por implantación local y
  condición de nueva empresa; INNOVAE se conserva para vigilancia de inversión y
  ahorro energético. La caché se guardó y no se generó un JSON parcial.
- La ejecución completa posterior obtuvo 49 aciertos de caché y cero análisis
  nuevos, por lo que no consumió tokens adicionales. Generó un JSON de esquema 3
  con 49 tarjetas activas, 29 relevantes, 20 descartadas, cero contradicciones y
  28 entradas de datos pendientes. La procedencia bruta fue Horizon 30, BDNS
  644, ECCP seis, CDTI cinco e IDAE una; EEN, BOE/MITECO, BOA e IDAE Catálogo no
  aportaron una convocatoria consolidada en esta ejecución.
- Las URLs públicas aceptan ahora hosts inequívocos sin esquema añadiendo
  exclusivamente `https://`. No se reparan rutas, correos ni destinos dudosos.
  Tras normalizar dos dominios oficiales, las 49 URLs respondieron y el JSON se
  volvió a publicar en GitHub Pages. El JSON remoto se verificó contra el local y
  conserva PowerUp NetZero.
- El contrato del frontend ya no fija el contador histórico de BOE/MITECO: la
  prueba usa un fixture sintético y exige que el número del menú coincida con las
  tarjetas realmente filtrables, manteniendo la equivalencia `BOE/MITECO` y
  `BOE / MITECO`.
- La entrega final restauró `CLAUDE_API_KEY` y `GITHUB_TOKEN` a `Placeholder`.
  `py_compile` y las 127 pruebas `unittest` finalizaron correctamente después de
  esa restauración.

## 16. Estado operativo a 14/08/2026 tras la segunda iteración BDNS y EEN

- La ampliación residual BDNS sigue siendo generalista y exige evidencia
  autosuficiente. Rechaza beneficiarios limitados exclusivamente a grandes
  empresas; personas autónomas o microempresas que inician actividad; presencia
  empresarial previa obligatoria fuera de Aragón; y una alternativa de nueva
  implantación cuando el periodo confirmado es inferior a 730 días. No usa
  nombres de convocatorias, identificadores, URLs ni territorios concretos.
- La regla de presencia previa reconoce variantes de centro de actividad o
  producción, alta regional en IAE, actividad desarrollada en el territorio con
  establecimiento o domicilio fiscal y censo fiscal municipal. Zaragoza, Huesca
  y Teruel se reconocen explícitamente como Aragón para evitar falsos rechazos
  cuando SNPSAP devuelve provincia o municipio en lugar de la comunidad.
- El backtest integral sobre las 19 ambiguas de referencia resolvió siete
  rechazos: microempresa de nueva creación, gran empresa exclusiva,
  ciberseguridad industrial pura, dos requisitos de presencia previa fuera de
  Aragón, una presencia previa municipal y una nueva implantación con periodo
  insuficiente. Doce permanecen como candidatas para Haiku. Se conservaron suelo
  industrial en Zaragoza, áreas industriales de Aragón, eficiencia energética,
  energía y residuos, grupos operativos, empresas de base tecnológica,
  exploración tecnológica y química aplicada cuando la incompatibilidad no era
  demostrable. Una base energética balear se rechazó solo por cierre confirmado.
- La ejecución `--no-claude` consolidó 689 registros y dejó 54 candidatas. BDNS
  partió de 635 registros; 615 se excluyeron antes de evidencia adicional y, de
  32 estados intermedios, 20 se resolvieron como rechazo y 12 continuaron como
  ambiguos. La previsión fue de 13 análisis nuevos o cambiados, 26 llamadas y
  0,3445 USD centrales, dentro de la barrera. No se llamó a Claude, no se
  modificó la caché IA, no se generó JSON y no se publicó.
- EEN consulta ahora el filtro oficial `Research & Development Request`
  (`f[0]=p:4355`) en vez de recorrer perfiles comerciales generales. Solo crea
  una convocatoria si la ficha contiene `Call details`, cierre futuro y un
  enlace cuya URL identifica una call concreta; una homepage genérica del
  programa no basta. `Eurostars Call N` se normaliza como identidad fuerte para
  fusionar perfiles que apuntan a la misma convocatoria.
- El prefiltro común excluye seguridad civil o vial, desastres, gobernanza
  climática o ambiental, economía social y asesoramiento a agricultores o
  silvicultores cuando son el objeto principal y no existe evidencia de calor,
  combustión, emisiones, proceso térmico o valorización térmica. La regla es
  común a EEN y Horizon y conserva cualquier conexión térmica industrial
  explícita; no depende de una call individual.
- La comprobación EEN final recorrió 27 páginas y 233 fichas candidatas en
  unos 52 segundos. Publicó internamente diez calls verificables, consolidadas en
  nueve identidades: seis rechazos deterministas, dos `retain` (Eurostars Call 11
  y LIFE de economía circular/agua) y una `ambiguous` (POLNORIS). Estos son
  resultados del conector aislado; una ejecución completa puede fusionar las
  identidades Horizon con SEDIA y reducir de nuevo el número de análisis.
- Para evitar que un fallo transitorio de BOE degrade convocatorias consolidadas,
  `_hydrate_stable_cached_documents()` repone en memoria únicamente documentos
  HTTPS con papel `call_extract`, `regulatory_bases` o `amendment` y una identidad
  fuerte coincidente por BDNS o identificador oficial. No recupera landings,
  hechos de Claude ni evaluaciones. En la prueba real repuso el extracto y las
  bases BOE/MITECO de INNOVAE por BDNS 920153; su procedencia consolidada volvió
  a ser BDNS, IDAE y BOE/MITECO y conservó un acierto de caché.
- La validación ejecutó `py_compile`, 132 pruebas `unittest`, una consulta EEN
  completa y una integración `--no-claude`. Las credenciales permanecieron como
  `Placeholder`; `convocatorias.json` y la caché IA no cambiaron.

## 17. Auditoría Playwright de CDTI a 14/08/2026

- El calendario oficial contiene 14 filas enlazadas a fichas `/ayudas/`. El
  scraper anterior solo visitaba 12: `Neotec` desaparecía porque, una vez
  retirado `(*)`, su título no alcanzaba ocho caracteres; la ayuda de premios
  navales se excluía por relevancia antes de abrir su ficha. Ambas condiciones
  eran errores de orden del pipeline, aunque las dos convocatorias ya estaban
  cerradas en la fecha de la auditoría.
- `_parse_cdti_calendar_html()` inventaría ahora todas las fichas sin filtro
  temático previo y con un límite absoluto de 100. `_fetch_cdti_playwright()`
  intenta abrir cada URL, extrae su ficha y solo entonces aplica vigencia. El
  alcance sectorial se decide posteriormente mediante el prefiltro común; una
  convocatoria futura ajena no deja de inspeccionarse por su título.
- La prueba real intentó y cargó las 14 fichas. Trece tenían cierre vencido y
  una permanece próxima: `INNTERCONECTA - STEP 2026`, con apertura estimada el
  01/10/2026, cierre estimado el 30/11/2026 y presupuesto extraído de 138 MEUR.
  El resultado combinado continúa siendo cinco convocatorias porque el catálogo
  curado aporta tres ventanillas permanentes y Proyectos Bilaterales 2026.
- Cuatro fichas conservaban el texto `Abierta` pese a una fecha de cierre pasada:
  Misiones Ciencia e Innovación, SERA primera, Eurostars CoD10 y SERA segunda.
  La fecha determinista prevalece y la contradicción se registra como
  `status_conflict`; ninguna se publica como vigente por ese texto obsoleto.
- La extracción usa la estructura `.ficha-field-wrapper` y conserva beneficiarios,
  plazo de presentación, estado, tipo de ayuda, presupuesto, descripción y trazas
  de documentos oficiales. Reconoce rangos abreviados como `del 17 de junio al
  16 de julio de 2026` y `del 6 al 17 de julio de 2026`. La auditoría encontró
  71 enlaces documentales en las 14 fichas. Solo después de demostrar vigencia se
  seleccionan un máximo de tres bases, convocatorias, extractos o modificaciones;
  guías y adjuntos genéricos no se descargan.
- `diagnostics.cdti_scrape_audit` conserva un registro compacto por ficha con URL,
  carga, número de campos y documentos, fechas, estado, conflicto y resultado.
  `SOURCE_RUNTIME_METADATA["CDTI"]` expone los contadores agregados para distinguir
  cobertura del número de oportunidades vigentes.
- La dependencia del calendario sigue siendo una debilidad estructural: si CDTI
  deja de actualizarlo, retira filas o cambia su HTML, el conector puede omitir
  programas cuyas fichas individuales continúen publicadas. El control común
  `assess_web_inventory_health()` se ejecuta en cada recopilación y registra en
  `diagnostics.web_source_health.CDTI` un estado `healthy`, `degraded` o
  `unhealthy`. Comprueba acceso, columnas Apertura/Cierre, mínimo de diez fichas,
  carga de al menos el 90 %, cobertura esperada de fechas y versión no anterior a
  62 días. El catálogo reduce el impacto operativo, pero no demuestra que el
  inventario vivo esté completo ni sustituye el aviso de salud.
- `fetch_cdti()` ya no repite la antigua consulta BDNS basada en sesión. BDNS se
  recopila una sola vez mediante `fetch_bdns()` y se consolida después como fuente
  transversal. CDTI queda como Playwright más catálogo curado.
- Los fixtures `cdti_calendar_sample.html`, `cdti_detail_active_sample.html` y
  `cdti_detail_stale_open_sample.html` prueban el título corto, una convocatoria
  no relevante antes del filtro común, fechas abreviadas, presupuesto, documentos
  y un estado `Abierta` obsoleto. `py_compile` y las 139 pruebas `unittest`
  finalizaron correctamente. No se llamó a Claude, no se modificó la caché IA,
  no se regeneró `convocatorias.json` y no se publicó.

## 18. Auditoría ECCP a 14/08/2026

- El inventario `type=eccp_calls` expone veinte páginas con contenido y 228
  fichas únicas; una página terminal adicional queda vacía. El HTML recibido por
  HTTP contiene las mismas doce fichas de la primera página que el DOM renderizado
  por Playwright. ECCP se mantiene por HTTP porque Chromium no añade campos y sí
  aumenta el tiempo de ejecución; el control de salud detectará roturas futuras
  de estructura o cobertura.
- La auditoría cargó las 228 fichas, obtuvo un cierre en todas y encontró seis
  convocatorias vigentes: IMPACT NETWORKS, RIVCircular, Dual-Use Drones,
  FutureProof Textiles, PowerUp NetZero y GRAPPA CUT-OFF 2. El prefiltro común se
  aplica después y puede excluir las ajenas al perfil; la cifra de seis mide
  cobertura ECCP, no compatibilidad con Kalfrisa.
- Las fichas se descargan con cuatro trabajadores como máximo y sesiones HTTP
  aisladas. El rastreo de niveles 0-3 ya no se repite en producción: se aplica
  directamente la profundidad 1 seleccionada por el experimento del 04/08/2026.
  En la validación actual rastreó una landing oficial por cada una de las cuatro
  calls que superaron el prefiltro, con cuatro peticiones y mediana de una por
  call. Así se evita multiplicar peticiones sin reabrir una decisión ya medida.
- Los enlaces externos se limitan ahora al contenido principal de la ficha; las
  redes sociales, avisos legales y newsletter del pie ya no compiten por las dos
  plazas de rastreo. Se extrae también un presupuesto total solo cuando aparece
  con etiqueta explícita; no se suman importes por línea o beneficiario.
- `diagnostics.eccp_scrape_audit` registra páginas, inventario, fichas intentadas,
  cargadas y fallidas, cobertura de cierres y calls activas. El mismo
  `assess_web_inventory_health()` usado por CDTI publica el estado ECCP en
  `diagnostics.web_source_health`, lo que generaliza el control para futuras
  fuentes web sin mezclarlo con la relevancia temática.

## 19. Auditoría IDAE y documentos CDTI a 17/08/2026

- La portada IDAE contiene 97 rutas únicas bajo `/ayudas-y-financiacion/`: 26
  identificadas estructuralmente como históricas mediante
  `/convocatorias-cerradas` y 71 fichas restantes. La pasada exhaustiva abrió las
  71, cargó correctamente las 71 y confirmó una única convocatoria vigente,
  Programa INNOVAE, con cierre 18/11/2026. El resultado de cobertura coincide con
  el conector anterior, pero ahora se demuestra que no procede de filtrar títulos
  antes de visitar las fichas.
- Las páginas sin cierre no reciben ya el plazo ficticio de 30 días. Se conservan
  solo como landings de identidad para fusionarlas con BDNS/BOE y se excluyen si
  no aparece otra fuente que pruebe una call vigente. La extracción común de
  fechas reconoce también cierres separados de la apertura relativa por una frase
  distinta, como `El plazo para presentar solicitudes... Finalizará ... el 15 de
  julio de 2025`.
- `diagnostics.idae_scrape_audit` guarda inventario, rutas cerradas, fichas
  intentadas/cargadas, resultados, fechas y estado por URL. IDAE se incorporó al
  control común de salud. En la integración quedó `healthy`: inventario 97,
  71/71 fichas cargadas y una call activa. La pasada costó 126,15 segundos. Se
  mantiene por ahora la navegación exhaustiva porque el objetivo prioritario es
  cobertura; solo debe reducirse con una regla estructural validada contra esta
  referencia, no mediante términos o nombres de programas.
- CDTI descarga documentos únicamente para calls vigentes o próximas. El límite
  es tres documentos seleccionados, 12 MB por documento y 16 MB por call. Para
  INNTERCONECTA STEP 2026 seleccionó la orden de bases y su modificación de 2026.
  La modificación produjo 48.000 caracteres de texto reutilizable y quedó en la
  caché general. La orden de bases, de 11.438.106 bytes, es un PDF sin texto
  extraíble por `pypdf`; no se incorporó como evidencia y quedó registrada como
  fallo temporal durante 30 días. No se usa HTML de bloqueo ni texto vacío como
  contenido factual.
- La integración `--no-claude` terminó correctamente en 646 segundos, con
  589,70 segundos de recopilación. Consolidó 684 registros, dejó 47 candidatas y
  previó diez análisis: 37 aciertos de caché, cinco contenidos cambiados y cinco
  nuevos. La estimación fue 20 llamadas, 0,2650 USD central y 0,1800-0,3500 USD
  según la calibración vigente, dentro de la barrera.
- Los cambios de contenido fueron INNTERCONECTA STEP 2026 y tres calls ECCP
  enriquecidas, además de una BDNS. Las cinco nuevas proceden de dos BDNS y tres
  EEN. No se llamó a Claude, la caché IA conservó su fecha del 14/08/2026,
  `convocatorias.json` no cambió y no hubo publicación. La auditoría sí se
  actualizó, como exige `--no-claude`.
- `py_compile` y las 139 pruebas finalizaron correctamente. Los estados de salud
  guardados fueron `healthy` para CDTI (14/14 fichas, versión 31/07/2026), ECCP
  (227/227 fichas con cierre) e IDAE (71/71 fichas abiertas correctamente).

## 20. Auditoría BOE/MITECO y actuaciones elegibles a 17/08/2026

- `ayudas.php` expuso 178 bloques y no presentó paginación ni formulario en el
  DOM renderizado. Es una ventana cronológica de publicaciones, no un inventario
  completo de convocatorias abiertas; BDNS sigue siendo la fuente transversal y
  BOE/MITECO aporta extractos, bases e identidad documental para consolidación.
- El parser visitaba solo una entrada y devolvía cero. El marcado vigente usa
  `p.linea-dem` para organismo y el siguiente párrafo para el título; se ha
  adaptado el selector. La auditoría prefiltró ocho documentos y cargó los ocho
  en 60-80 segundos. La pasada diagnóstica amplia devolvió cuatro piezas, pero
  dos eran infraestructura verde urbana y refugios climáticos sin conexión
  industrial. La regla final no permite que la mera pertenencia a MITECO las
  convierta en relevantes: conserva el extracto INNOVAE, BDNS 920153, cierre
  18/11/2026, y sus bases; las ayudas MITECO futuras necesitan evidencia técnica
  general o ser una call activa de IDAE.
- BOE/MITECO usa ahora `assess_web_inventory_health()` y registra inventario,
  candidatos, detalles intentados/cargados, cobertura de plazos y aceptaciones.
  Se eliminó el respaldo que asignaba 45 días ficticios a enlaces sin fecha.
  Los saltos de línea del documento se normalizan antes de extraer el plazo.
- El contrato factual añade `eligible_actions` tanto en la convocatoria general
  como en cada `funding_line`. Solo admite actuaciones, inversiones o gastos que
  la fuente declare financiables. La versión del extractor y del prompt se eleva
  de forma intencionada; una ejecución normal deberá reanalizar las candidatas
  cacheadas, siempre bajo la barrera de entonces —142 análisis y 5 USD; hoy 106
y 5 USD—.
- Para JSON antiguos, `derive_eligible_actions()` no inventa contenido: prioriza
  el nuevo campo, luego las líneas, después `required_topics` y, solo si estos
  faltan, un epígrafe literal inequívoco de actuaciones o gastos elegibles. El frontend cambia
  el rótulo a `Actuaciones o temas que debe abordar el proyecto` en este último
  caso para no presentarlo como categoría de gasto. Si no existe evidencia lo
  indica expresamente y remite a las bases.
- El XLSX y el CSV incorporan una columna `Actuaciones elegibles`. No se llamó a
  Claude, no se modificó la caché IA, no se regeneró `convocatorias.json` y no se
  publicó durante esta modificación. `py_compile` y las 144 pruebas `unittest`
  finalizaron correctamente.

## 21. Mejoras de mantenibilidad e infraestructura a 18/08/2026

Esta sección resume la ejecución de las propuestas de `SUGERENCIAS.MD`
(evaluación externa del 17/08/2026, verificada y ampliada el 18/08/2026);
el detalle punto por punto, incluidas las correcciones a la evaluación
original, está en ese archivo.

- Credenciales: la Celda 2 ahora prioriza `.env` (vía `python-dotenv`) sobre
  el `"Placeholder"` embebido; ver invariante ampliada en la sección 7.
  `.gitignore` excluye `API KEYs.txt`, `.env`, `debug.log`,
  `convocatorias.json`, `.venv/` y `__pycache__/`. Nuevo hook
  `.git/hooks/pre-commit` bloquea commits con patrones de clave real.
- Control de versiones: se instaló Git for Windows (no estaba presente en el
  equipo) y se inicializó un repositorio en esta copia, con `origin` apuntando
  a `https://github.com/GOrtega-KAL/Grant-Radar-CC.git` (repositorio paralelo
  al original `Grant-Radar`, creado por el usuario). `GITHUB_REPO` se
  actualizó de `"Grant-Radar"` a `"Grant-Radar-CC"` en consecuencia. Sin
  `git push` todavía: pendiente de que el usuario complete `GITHUB_TOKEN` en
  `.env`.
- Código muerto real (`_legacy_bdns_cdti_session_scraper()`,
  `_fetch_cdti_playwright_legacy()`) eliminado, verificado sin llamadas
  previas. `LEGACY_TECH_TAG_MAP`/`_legacy_tags_for()` no eran código muerto
  (se usan en cada análisis para el campo público `tags`); se renombraron a
  `TECH_TAG_COMPAT_ALIASES`/`_compat_tags_for()` sin cambiar su
  comportamiento ni el esquema público.
- Salud de fuentes: `run_pipeline()` añade un resumen consolidado de fuentes
  `degraded`/`unhealthy` al final de la recopilación, además del aviso ya
  existente por consola en el momento en que `assess_web_inventory_health()`
  evalúa cada fuente.
- Contrato frontend-backend: se extrajo `_assemble_public_record()` desde
  dentro de `run_pipeline()` para poder probar de forma aislada, sin red ni
  Claude, que cada campo publicado tiene una contrapartida en `index.html`.
  Ese test encontró y permitió corregir una divergencia real:
  `eoi_deadline_date` se publicaba pero no se mostraba; ahora aparece en el
  bloque de trazabilidad del detalle. `catalog_scope`, `catalog_category`,
  `catalog_ref`, `related_documents_count` y `bdns_url` siguen sin
  consumirse en el frontend, marcados como deliberados en el test.
- Exportación XLSX/CSV: nuevo test de regresión fija la lista exacta de
  columnas de `buildExportTable()`.
- `pyproject.toml` relajado de `requires-python = ">=3.14"` a `">=3.11"` tras
  auditar el código en busca de sintaxis exclusiva de 3.12+ (no se encontró
  ninguna). No probado ejecutando realmente sobre un intérprete 3.11 —ver
  reserva en `SUGERENCIAS.MD` 3.9— porque este equipo solo tiene Python 3.14.
- División en módulos (`SUGERENCIAS.MD` 3.2): primer incremento aplicado.
  Nuevo paquete `grant_radar/` (nombre válido para `import`, a diferencia
  de `Grant-Radar-prueba.py`) con `parsing_helpers.py`: doce
  funciones/constantes puras de fechas y texto sin dependencia de caché,
  reglas ni Claude. El candidato original, `cache/`, resultó estar acoplado
  al dominio de reglas (`filter_usable_cache()` llama a
  `apply_current_deterministic_rules()`) y se descartó como primer paso.
  Resto de la división (`sources/`, `rules/`, `claude_pipeline/`, `cache/`,
  `pipeline.py`) pendiente.
- Reglas de exclusión (`SUGERENCIAS.MD` 3.3): primer incremento aplicado,
  solo datos. Las diez listas de términos de `_hard_out_of_scope()` viven
  ahora en `grant_radar/exclusion_terms.json`
  (`grant_radar/exclusion_terms.py` las carga); la lógica de cuándo se
  aplica cada una sigue en Python, sin cambios. Ampliar una lista existente
  ya no requiere tocar `Grant-Radar-prueba.py`. El motor de reglas genérico
  en sí y la externalización de `_bdns_pre_claude_gate()` (siete niveles de
  precedencia, sección 4.1) siguen sin implementarse: requieren formalizar
  antes todas las variantes de condición existentes, y el riesgo de
  regresión silenciosa es alto.
- Verificación: `py_compile` y las 160 pruebas `unittest` (144 originales +
  16 nuevas, incluyendo dos archivos de test que importan módulos de
  `grant_radar/` sin `runpy`) finalizaron correctamente tras cada cambio de
  código, incluidos los 25 casos de `tests/fixtures/common_scope_filter_cases.json`
  que cubren `_hard_out_of_scope()`. No se llamó a Claude, no se modificó la
  caché IA ni `convocatorias.json`, y no se publicó en GitHub Pages durante
  esta sesión.

## 22. Segunda ronda de modularización a 18/08/2026

Continuación de la sección 21, mismo día: se identificó un bloque grande y
autónomo (taxonomía tecnológica + su comparación contra texto) que tampoco
dependía de caché, reglas ni Claude, y se extrajo junto con los datos de
cliente que quedaban embebidos en el script.

- `grant_radar/tech_taxonomy.py` (+ `tech_taxonomy.json`): las categorías
  técnicas de Kalfrisa (`TECH_TAG_STRONG_TERMS`, `TECH_TAG_CONTEXTUAL_TERMS`,
  `TECH_DISCOVERY_TERMS`, `TECH_TAG_COMPAT_ALIASES`) y las funciones que
  comparan un texto contra ellas (`detect_tech_tags`, `is_relevant`,
  `keyword_match`, `_term_present`, `_contextual_term_present`,
  `has_technology_discovery_signal`, `_compat_tags_for`). `TECH_TAGS` y
  `KEYWORDS` siguen siendo valores derivados, calculados en el módulo igual
  que antes en el script.
- `grant_radar/kalfrisa_profile.py` (+ `kalfrisa_profile.txt`): el texto de
  perfil de Kalfrisa enviado en cada prompt de evaluación. Ahora es un
  archivo de texto plano editable sin tocar Python; `PROFILE_VERSION` sigue
  en `Grant-Radar-prueba.py` y sigue siendo manual (cambiar el texto no
  invalida la caché por sí solo).
- `grant_radar/partner_catalog.py` (+ `partner_catalog.json`): los 16 socios
  técnicos recomendables y `preselect_partners()`.
- `select_evidence_excerpt()` se movió a `parsing_helpers.py` (ya extraído
  el 18/08 por la mañana): dependía solo de `_fold_text`, igual que el resto
  de ese módulo.
- Tres archivos de test nuevos con import estándar (sin `runpy`):
  `test_grant_radar_tech_taxonomy.py`,
  `test_grant_radar_profile_and_partners.py`, y ampliación de
  `test_grant_radar_parsing_helpers.py` para `select_evidence_excerpt()`.
- `Grant-Radar-prueba.py` bajó de 10.976 a 10.037 líneas (-8,6 %) entre las
  dos rondas del 18/08/2026. `py_compile` y las 180 pruebas `unittest`
  (144 originales + 36 nuevas) finalizaron correctamente tras cada
  extracción. No se llamó a Claude, no se modificó la caché IA ni
  `convocatorias.json`, y no se publicó en GitHub Pages durante esta ronda.
- Sigue pendiente: `sources/`, `rules/`, `claude_pipeline/`, `cache/` y
  `pipeline.py` (ver sección 21). `cache/` y `rules/` continúan acoplados
  entre sí (`filter_usable_cache()` llama a
  `apply_current_deterministic_rules()`); extraer cualquiera de los dos
  exige abordar ese acoplamiento primero.

## 23. Tercera ronda de modularización a 18/08/2026: cache + rules juntos

Antes de esta ronda, el usuario corrigió a mano la línea 11 de `Grant-Radar-prueba.py`
(la ruta `cd` de la Celda 1), que seguía apuntando a la carpeta original
`Grant-Radar` en vez de a esta copia; y ejecutó dos veces
`poetry run python "Grant-Radar-prueba.py" --no-claude` como validación
real del trabajo de las secciones 21 y 22 (no solo `py_compile`/`unittest`).
Ambas ejecuciones terminaron con `status: completed_no_claude`, sin errores,
47 candidatas y las cuatro fuentes con control de salud (`ECCP`, `IDAE`,
`BOE / MITECO`, `CDTI`) en `healthy`. `grant_radar_cache.json` no se tocó,
como exige `--no-claude`.

A petición expresa, se extrajo a continuación el acoplamiento identificado
en la sección 21 (`filter_usable_cache()` → `apply_current_deterministic_rules()`):

- `grant_radar/versions.py`: `PROFILE_VERSION`, `EXTRACTOR_VERSION`,
  `EVALUATOR_VERSION`, `PARTNER_CATALOG_VERSION`, `ANALYSIS_PROMPT_VERSION`,
  `CACHE_SCHEMA_VERSION`, `CLAUDE_MODEL`. Sin estas constantes centralizadas,
  `cache_key()` (llamada en unos 6 puntos del script) habría necesitado
  parámetros adicionales en cada sitio; en cambio, tanto el script principal
  como `cache.py` las importan del mismo origen.
- `grant_radar/cache.py`: `cache_key()`, `cache_save()`, `cache_load()`,
  `filter_usable_cache()`, `analysis_is_usable()`, `_reindex_cache_entries()`,
  `source_hash()`, `_stable_factual_hash_text()`. `cache_save()`/`cache_load()`
  reciben ahora la ruta del archivo de caché como parámetro (antes leían
  `CACHE_FILE` directamente); la ruta se sigue calculando una sola vez en el
  script principal a partir de su propio `__file__`, para no arriesgar que la
  caché se lea o escriba en un sitio distinto tras mover código a un
  subdirectorio.
- `grant_radar/deterministic_rules.py`: `apply_current_deterministic_rules()`
  y las 18 funciones que orquesta (correcciones de inversión propia,
  valorización directa, participación en consorcio, tamaño de empresa,
  ineligibilidad regional, consistencia temporal, prioridad derivada...),
  más `_deterministic_call_status()` (usada también en otros dos puntos del
  script, que la reimportan) y la constante `BDNS_DIRECT_OWN_INVESTMENT_TERMS`
  (compartida con `deterministic_prefilter()`, que sigue en el script
  principal y también la reimporta).
- `cache.py` importa `apply_current_deterministic_rules` de
  `deterministic_rules.py`: es la única dependencia cruzada entre los dos
  módulos, la misma que motivó extraerlos juntos en vez de por separado.
- `tests/test_grant_radar.py` accedía a varias de estas funciones vía
  `APP["nombre"]` (patrón `runpy.run_path()`) en unos 12 puntos dispersos de
  la clase `DeterministicPostAnalysisTests` y otras. En vez de reescribir
  cada acceso, se añadió justo después de crear `APP` un bloque que fusiona
  en `APP` las funciones públicas y privadas de `grant_radar.cache` y
  `grant_radar.deterministic_rules`, documentando por qué. Los archivos de
  test nuevos (`test_grant_radar_cache.py`,
  `test_grant_radar_deterministic_rules.py`) sí importan directamente, sin
  pasar por `APP`.
- `Grant-Radar-prueba.py` bajó de 10.037 a 9.006 líneas en este paso
  (-17,9 % acumulado desde las 10.976 originales de hoy por la mañana).
  `py_compile` y 205 pruebas `unittest` (180 anteriores + 25 nuevas)
  finalizaron correctamente tras la extracción. Además, se repitió
  `poetry run python "Grant-Radar-prueba.py" --no-claude` después del
  cambio: terminó en 8 min 33 s con las mismas 47 candidatas y las mismas
  cuatro fuentes `healthy` que antes de extraer nada, confirmando que el
  resultado del pipeline real no cambió, no solo los tests.
- Sigue pendiente: `sources/`, `claude_pipeline/` y `pipeline.py` (ver
  sección 21). El acoplamiento cache/rules que bloqueaba avanzar ya está
  resuelto; el resto de dominios no tiene, de momento, ninguna dependencia
  cruzada conocida entre sí.

## 24. Cuarta ronda de modularización a 18/08/2026: esquemas de Claude

`grant_radar/claude_schemas.py`: los cinco modelos Pydantic (`CallFacts`,
`CallEvaluation`, `FundingLineFacts`, `EvaluationScores`, `BdnsHoldFacts`),
`ClaudeAnalysisError`, `STRUCTURED_SCHEMA_MAX_OPTIONAL_FIELDS`/
`STRUCTURED_SCHEMA_MAX_UNION_FIELDS`, y las funciones que validan los
esquemas contra los límites publicados de Anthropic
(`structured_schema_complexity`, `validate_structured_output_schema`,
`normalize_call_facts`). Sin dependencias cruzadas con otros módulos de
`grant_radar/` — solo `pydantic` y la librería estándar — fue el candidato
más simple de las cuatro rondas de hoy.

`Grant-Radar-prueba.py` bajó de 9.006 a 8.835 líneas (-19,5 % acumulado
desde las 10.976 originales de esta mañana). Nuevo
`tests/test_grant_radar_claude_schemas.py`, con un test que fija el
invariante "cero opcionales, cero uniones" de la sección 4 para los tres
esquemas principales como aserción de test, no solo como comentario. 216
pruebas `unittest`, `py_compile` y una repetición de
`poetry run python "Grant-Radar-prueba.py" --no-claude` en verde, con las
mismas 47 candidatas y las mismas cuatro fuentes `healthy` que en las rondas
anteriores.

Balance del día: cuatro rondas de modularización (secciones 21-24),
`Grant-Radar-prueba.py` pasó de 10.976 a 8.835 líneas. Paquete `grant_radar/`
con diez módulos: `parsing_helpers`, `exclusion_terms` (+ `.json`),
`tech_taxonomy` (+ `.json`), `kalfrisa_profile` (+ `.txt`),
`partner_catalog` (+ `.json`), `versions`, `cache`, `deterministic_rules`,
`claude_schemas`. Sigue pendiente `sources/` (los ocho conectores de
fuentes, el bloque más grande que queda) y `pipeline.py`
(`run_pipeline()` y su orquestación). La lógica más compleja del proyecto —
`_bdns_pre_claude_gate()` y `deterministic_prefilter()`, con los siete
niveles de precedencia de la sección 4.1 — sigue deliberadamente sin
tocar: se considera que merece su propia sesión dedicada por el riesgo de
regresión silenciosa, no encadenarla detrás de otra extracción.

**Nota de discrepancia detectada el 18/08/2026 (arranque en frío):** al
empezar la sesión siguiente, `git show <commit de esta sección>:"Grant-Radar-prueba.py" | wc -l`
daba 9.426 líneas, no 8.835. La cifra de esta sección quedó mal registrada
en su momento (o se contó con un método distinto); no se ha investigado más
a fondo por no ser bloqueante. A partir de la sección 25, las cifras de
línea citadas están verificadas con `wc -l` sobre el archivo real en el
momento de escribirlas.

## 25. Quinta ronda de modularización a 18/08/2026 (prueba): conector BOA Aragón

Primer intento de extraer un conector de fuente a un paquete `sources/`
propio (pendiente desde la sección 21), usando BOA Aragón como caso de
prueba por ser el más pequeño y autocontenido de los ocho (sin llamadas a
`assess_web_inventory_health()`, sin fusión con BDNS, solo tres funciones).

- `grant_radar/sources/boa_aragon.py` (paquete nuevo `grant_radar/sources/`):
  `_fetch_boa_static()`, `_fetch_boa_playwright()`, `fetch_boa()`, movidas
  sin cambios de lógica. `browser` se tipa como `typing.Any` en vez de
  `PlaywrightBrowser`: esa clase vive en `Grant-Radar-prueba.py`, cuyo
  nombre con guiones no es importable como módulo ni siquiera para un tipo;
  el módulo solo necesita `browser.html(url) -> str | None`.
- Dependencias resueltas antes de mover el conector:
  - `_es_titulo_valido()` (también usada por `fetch_boe()`, que sigue en el
    script principal) se movió a `grant_radar/parsing_helpers.py`: es una
    función pura de validación de texto, exactamente el criterio que ya
    agrupa ese módulo.
  - `audit_exclusion()` y la lista mutable `DISCOVERY_AUDIT` (usada por las
    ocho fuentes, no solo BOA — 32 referencias en todo el script) se
    movieron juntas a un módulo nuevo, `grant_radar/audit.py`. El script
    principal reimporta ambas (`from grant_radar.audit import
    DISCOVERY_AUDIT, audit_exclusion`), así que las llamadas existentes
    (`audit_exclusion(...)`, `DISCOVERY_AUDIT.clear()`, iterar sobre ella)
    siguen funcionando sin cambios: Python vincula el nombre importado al
    mismo objeto lista, no a una copia.
- `tests/test_grant_radar_sources_boa_aragon.py` (nuevo, import estándar):
  cubre `_fetch_boa_static()` fijando `_days_until()` con `mock.patch` en
  vez de depender de la fecha real del sistema (el catálogo estático tiene
  fechas fijas en el código y, a fecha de esta sesión, ambas ya están
  vencidas — ver nota de mantenimiento en el propio módulo), y
  `_fetch_boa_playwright()` con HTML sintético que ejercita en la misma
  pasada el resultado activo y relevante, el excluido por ámbito
  (regadío/agropecuario) y el excluido por estar fuera de plazo.
  `tests/test_grant_radar_audit.py` (nuevo) prueba `audit_exclusion()` de
  forma aislada, incluida la deduplicación por clave. Se añadieron también
  tres casos de `_es_titulo_valido()` a
  `tests/test_grant_radar_parsing_helpers.py`.
- `Grant-Radar-prueba.py` bajó de 9.426 a 9.202 líneas (-2,4 % en esta
  ronda; recuento verificado con `wc -l`, no con la cifra de la sección 24
  — ver nota de discrepancia arriba). 226 pruebas `unittest` (216 + 10
  nuevas) y `py_compile` en verde. Se repitió además
  `poetry run python "Grant-Radar-prueba.py" --no-claude` completo (534,78 s
  de recopilación, salida con código 0, sin `convocatorias.json` generado ni
  caché IA modificada): 46 convocatorias vigentes en total, BOA Aragón
  aportó 0 (cae al catálogo estático, que ya tiene sus dos únicas entradas
  vencidas a fecha de esta sesión — comportamiento idéntico al del código
  original, no una regresión de la extracción: ver nota de mantenimiento en
  `boa_aragon.py`, última revisión del catálogo 2026-04-09). El resto de
  fuentes no cambió de comportamiento respecto a ejecuciones anteriores más
  allá de la variación normal de datos reales (46 vs. 47 candidatas de la
  sección 23, esperable entre ejecuciones en días distintos).
- Sigue pendiente: los otros siete conectores (BDNS, Horizon, CDTI, IDAE,
  BOE/MITECO, ECCP, EEN) y `pipeline.py`. Ninguno es tan autocontenido como
  BOA: CDTI fusiona con BDNS, BOE llama a `assess_web_inventory_health()` y
  comparte `_es_titulo_valido()` (ya resuelto), ECCP y EEN tienen su propia
  lógica de profundidad de rastreo y parámetros de listado. El patrón que
  deja esta ronda para repetir con las demás: identificar qué helpers
  comparte el conector con otras fuentes antes de moverlo, y decidir por
  cada uno si es puro (→ `parsing_helpers.py`/`tech_taxonomy.py`), si es
  estado compartido genuino (→ módulo propio, como `audit.py`), o si debe
  quedarse en el script principal por depender de algo aún no extraído
  (como `PlaywrightBrowser` o `assess_web_inventory_health()`).

## 26. Cobertura automática de Aragón vía BDNS a 18/08/2026 (sesión siguiente)

El usuario pidió refrescar el catálogo estático de BOA (ambas entradas ya
vencidas, ver sección 25), pero con el objetivo real de dejar de depender de
un catálogo curado y lograr cobertura automática de verdad. Antes de tocar
código se investigaron dos fuentes de scraping directo aportadas por el
usuario y ambas se descartaron con evidencia real:

- **Registro BOA `CONV/AYUDAS`**
  (`boa.aragon.es/cgi-bin/CONV/BRSCGI?...&SEC=CONV_AYUDAS&TIPO-C=AYUDAS...`):
  estructurado, paginable por GET simple sin sesión (11.577 documentos
  históricos), pero su entrada más reciente está fechada 7/01/2026 — más de
  7 meses de desfase editorial respecto al 18/08/2026, confirmado revisando
  las primeras 100 entradas (ninguna posterior a enero 2026, densidad ~44
  filas/día hasta ahí) y el final del listado (documento 11570+, ya del
  Programa de Desarrollo Rural 2014-2020). No sirve como fuente de
  "vigentes ahora".
- **Buscador de trámites de aragon.es**
  (`aragon.es/tramites/.../ayudas-subvenciones?...p_auth=...`): acción de
  portlet Liferay con token de sesión — HTTP 403 ante un GET simple, no es
  una URL estable para scraping directo sin simular la interacción real del
  formulario.

La alternativa que sí funciona: **BDNS**, ya integrada vía `fetch_bdns()`
(línea ~4590), tiene datos casi en tiempo real (`fechaRecepcion` del mismo
día en pruebas reales) y cada fila de `convocatorias/ultimas` ya trae
`nivel1` ("AUTONOMICA"/"LOCAL"/"ESTADO"/"OTROS") y `nivel2` (nombre de la
administración, p. ej. "ARAGÓN") sin llamadas adicionales. Entradas del
propio índice BOA `CONV/AYUDAS` revisado arriba incluían literalmente
"Observaciones: BDNS (Identif.): ####", confirmando que las ayudas del
Gobierno de Aragón sí quedan registradas en BDNS, coherente con el principio
ya documentado en la sección 3 ("BDNS ... `bdns_id` prevalece como identidad
fuerte"). Se probó filtrar `convocatorias/busqueda` server-side por
`nivel1`, `nivel2`, `administraciones` o `regiones`: la API los ignora
silenciosamente (mismo resultado con o sin esos parámetros) — el filtro
debe hacerse en cliente, igual que ya hacía `_bdns_candidate_from_listing()`
con palabras clave.

**Cambio implementado:**

- `grant_radar/bdns_scope.py` (nuevo): `_bdns_candidate_from_listing()`
  (movida tal cual desde `Grant-Radar-prueba.py`, sin test dedicado hasta
  ahora), `_bdns_is_aragon_regional_administration()` (nueva: `nivel1`
  folded == "autonomica" y "aragon" en `nivel2` folded — administraciones
  LOCAL quedan fuera aunque mencionen Aragón, publican en el Boletín Oficial
  de la Provincia, no en BOA) y `_bdns_is_prefilter_candidate()` (OR de las
  dos). El script principal las reimporta; la línea de construcción de
  `candidates` en `fetch_bdns()` pasa a usar `_bdns_is_prefilter_candidate`.
- `BDNS_LATEST_MAX_PAGES` sube de 10 a 35 (línea ~4177), con comentario
  explicando la medición real de densidad (~44 filas/día nacional el
  17-18/08/2026) que la justifica: 35 páginas × 100 filas ≈ 79 días, colchón
  sobre el mínimo de negocio de 60 días pedido explícitamente por el
  usuario (se descartaron 30 páginas/~68 días y 40 páginas/~90 días como
  alternativas más ajustada/más holgada).
  Este ensanchado afecta a **todas** las administraciones, no solo a
  Aragón: la API no permite filtrar `convocatorias/ultimas` por región en
  servidor.
- `SOURCE_RUNTIME_METADATA["BDNS"]` gana un contador nuevo,
  `aragon_admin_candidates`, junto a `inventory_unique`/
  `prefilter_candidates` — visible en memoria durante la ejecución, aunque
  a fecha de esta sesión no queda persistido en
  `grant_radar_audit.json` (ese archivo no serializa
  `SOURCE_RUNTIME_METADATA` para fuentes que no llaman a
  `assess_web_inventory_health()`, que es el caso de BDNS); queda como
  posible mejora futura si se quiere ese número en el histórico de
  auditoría.
- `grant_radar/sources/boa_aragon.py`: solo nota de estado en el docstring
  de módulo, sin cambio de lógica — el conector queda como señal
  secundaria/backup, no como mecanismo principal.
- Nuevo `tests/test_grant_radar_bdns_scope.py` (import estándar) y dos
  tests añadidos a `tests/test_grant_radar.py` (`SourceParserTests`): uno de
  integración de `fetch_bdns()` con `_http_get` mockeado que verifica que
  una fila autonómica de Aragón sin ninguna palabra clave entra igualmente
  como candidata, y un test de regresión que ata `BDNS_LATEST_MAX_PAGES` ×
  `BDNS_PAGE_SIZE` al mínimo de negocio de 60 días usando la densidad
  medida, para que nadie reduzca la constante sin darse cuenta de que
  incumple el requisito. 238 pruebas `unittest` (226 + 12 nuevas) y
  `py_compile` en verde.

**Verificación real (`--no-claude`, 18/08/2026, 12:40-12:53 UTC), comparada
contra el baseline de la sección 25:**

| Métrica | Antes (sección 25) | Después |
|---|---|---|
| `BDNS_LATEST_MAX_PAGES` | 10 (~22-23 días) | 35 (~79 días) |
| BDNS inventariadas | 2.084 | 4.475 |
| BDNS candidatas (prefiltro) | 635 | 899 |
| BDNS vigentes (final) | 16 | 47 |
| Tiempo BDNS | 168,06 s | 243,15 s |
| Tiempo total recopilación | 534,78 s | 580,07 s |
| Total vigentes (todas las fuentes) | 46 | 77 |
| Previsión Claude (coste central) | $1,2190 (92 llamadas) | $2,0405 (154 llamadas) |

El incremento de 46→77 vigentes es enteramente atribuible a BDNS (16→47,
+31); el resto de fuentes no cambió (Horizon 19, ECCP 4, EEN 2, CDTI 5,
IDAE 1, BOE 1, BOA 0) — consistente con que el cambio solo toca `fetch_bdns()`.
Confirmado un caso real, concreto, que antes no aparecía y que no tiene
ninguna palabra clave industrial obvia en su título — prueba directa de que
el filtro de administración (no el de palabras clave) es lo que lo trajo:

> [2026-09-17] ORDEN ECE/ /2026, de 31 de julio, por la que se convocan
> para el ejercicio 2026 ayudas para la realización de inversiones en
> recintos feriales y para la promoción y organización de certámenes
> feriales en la Comunidad Autónoma de Aragón.

Invariantes de `--no-claude` confirmados en esta ejecución: código de salida
0, "No se llamó a Claude", caché IA no modificada, `convocatorias.json` no
generado ni publicado, barrera de Claude (`claude_safety_preflight()`)
dentro de límites pese al aumento de volumen (200 análisis / $5,00 máximo).

**No ejecutado en esta sesión:** ninguna llamada real a Claude/Haiku — el
usuario condicionó explícitamente su autorización a que no se hicieran
llamadas a la API sin pedir permiso primero. El aumento de coste central
estimado (+67 %, de $1,22 a $2,04) queda documentado aquí para que el
usuario lo revise antes de autorizar una ejecución completa.

## 27. Revisión del embudo determinista tras ampliar BDNS (mismo día, 18/08/2026)

Ante el aumento de candidatas BDNS (sección 26), el usuario pidió revisar si
merecía la pena endurecer los filtros deterministas antes de gastar en
Claude, y preguntó si tocar esos filtros ahora iría en contra del trabajo de
modularización. Se revisó el embudo completo con los datos reales de la
ejecución `--no-claude` de la sección 26 (948 convocatorias detectadas tras
deduplicar, dominadas por las 899 de BDNS) y se leyó el código real de
`_bdns_pre_claude_gate()` (líneas ~1056-1248) para entender el motivo exacto
de cada descarte, no solo los recuentos agregados.

**Respuesta a "¿tocar los filtros ahora contradice la modularización?":
no.** `AGENTS.md` (secciones 21-25) y `SUGERENCIAS.MD` (3.2/3.3) siempre
trataron "extraer código a módulos" y "cambiar reglas de negocio" como ejes
independientes, resueltos en sesiones separadas a propósito. La única razón
por la que `_bdns_pre_claude_gate()`/`deterministic_prefilter()` (sección
4.1) siguen sin extraer no es un conflicto estructural, sino que son la
lógica más compleja y ajustada del proyecto (siete niveles de precedencia) y
tocarla sin petición expresa del usuario se consideraba demasiado
arriesgado para colarla detrás de otra tarea — exactamente la situación para
la que se dejó esa nota. Modificarla ahora, con el script principal todavía
sin extraer esa lógica, no bloquea ni complica una extracción futura: se
extraerá lo que exista en ese momento, igual que con cualquier otro módulo.

**Veredicto sobre las 77 candidatas finales (32 retain + 8 ambiguous + 37
resueltas-ambiguas de BDNS):** el embudo determinista ya funciona
correctamente y no es el cuello de botella. De las 948 convocatorias
detectadas:

- `deterministic_prefilter()` (línea de log "Prefiltro común") rechaza
  **838 de 948 (88,4 %)** en el primer paso, solo con los datos del
  listado, sin llamar a Claude.
- De las 70 que quedan en `hold_manual` de BDNS por falta de datos en el
  listado, la resolución automática (`resolve_bdns_holds_for_pipeline`,
  que busca evidencia adicional y reaplica las reglas) rechaza **33 más
  sin Claude** y no necesita revisión manual humana en ningún caso
  (`revisión manual=0`). Solo entonces se declaran genuinamente ambiguas
  las **37 restantes**, que pasarían a Claude en una ejecución real.
- En total, **871 de 948 (91,9 %) se descartan de forma determinista**;
  solo 77 (8,1 %) llegarían a Claude — el coste estimado ($2,04 central)
  refleja esas 77, no las 899 candidatas iniciales de BDNS citadas en la
  sección 26. Confundir "candidatas tras el primer filtro de listado" con
  "candidatas que realmente cuestan Claude" habría llevado a una alarma de
  coste desproporcionada respecto a la realidad.
- De los 70 `hold_manual`, el motivo domina con claridad:
  `territorial_eligibility_unverified` = 57 (81 %),
  `active_status_unverified` = 12 (17 %), `consortium_role_unverified` = 1.
  Leyendo el código: el paso 1 (¿es de fuera de Aragón?, usa `bdns_regions`
  del detalle BDNS y `bdns_admin_type`/`nivel1`) funciona bien y clasifica
  correctamente administraciones como "Cámara de Comercio de Granada" o
  "Ayuntamiento de X" como subnacionales fuera de Aragón. El paso 2 (¿eso
  descarta a Kalfrisa?, `existing_centre_patterns`/`new_centre_patterns`/
  `project_location_patterns` sobre el texto de la descripción, línea
  ~4505) es el que se atasca: el requisito explícito de "centro ya
  existente en la comunidad convocante" casi nunca aparece en la
  descripción corta de BDNS, solo en las bases completas en PDF — de ahí
  que quede "unknown" y pase a `hold_manual`.
- Se consideró reutilizar `build_recurrent_coverage_watch()` (línea ~1385)
  para "recordar" que programas anuales repetidos de administraciones
  ajenas a Aragón (se detectaron ediciones 2023/2024/2025/2026 del mismo
  programa municipal, y tres convocatorias de la Cámara de Comercio de
  Granada) ya se descartaron en ediciones anteriores. Se descartó tras leer
  su código: esa función vigila que programas *relevantes* conocidos sigan
  apareciendo cada ejecución (alerta si dejan de encontrarse), no sirve
  para lo contrario (recordar descartes de programas irrelevantes). No hay
  hoy ningún mecanismo para eso; sería lógica nueva, no reutilización.

**Decisión del usuario:** no tocar el filtro territorial por ahora. Motivo
compartido con el usuario y aceptado: el crecimiento no viene de un filtro
laxo sino de que ensanchar la ventana temporal (sección 26) trae más
convocatorias subnacionales de fuera de Aragón en general, no solo las de
Aragón que se buscaban; el sistema ya resuelve automáticamente el 91,9 % sin
Claude y sin revisión manual; y el coste real ($2,04) sigue muy por debajo
de la barrera de seguridad ($5,00). Se documentan aquí, para si se retoma
más adelante, las dos vías concretas evaluadas y no descartadas por
inviables, solo aplazadas:

1. **Señal por tipo de administración**: usar `nivel2`/`nivel3` (ya
   disponibles sin coste adicional) para que Cámaras de Comercio/
   Ayuntamientos fuera de Aragón asuman por defecto "centro ya existente
   requerido" salvo que el texto sugiera lo contrario — invierte la
   presunción actual. Riesgo: falsos negativos si algún programa de estos
   emisores resulta ser de alcance nacional.
2. **Ampliar los patrones de texto**: revisar bases reales de varios de los
   37 casos ambiguos de esta ejecución para encontrar lenguaje de
   requisito de centro que `existing_centre_patterns`/`new_centre_patterns`
   no reconocen hoy. Más lento (requiere leer PDFs reales caso a caso) pero
   menor riesgo de falso negativo que la opción 1.

Cualquiera de las dos, si se retoma, debe seguir la disciplina ya vigente
en `SUGERENCIAS.MD` 3.3: ampliar primero los fixtures de test con los casos
reales encontrados, antes de tocar la lógica de `_bdns_pre_claude_gate()`.

## 28. Sexta ronda de modularización a 19/08/2026: capa de infraestructura

Punto de partida de la sesión: `Grant-Radar-prueba.py` con 9.199 líneas
(`wc -l`) y 238 pruebas en verde. Antes de mover ningún conector nuevo se
analizaron con AST las dependencias reales de los siete que quedaban, y el
resultado cambió el orden de trabajo previsto.

**Hallazgo 1 — repetir el patrón BOA conector a conector no funciona.** BOA se
pudo extraer (sección 25) porque no dependía de nada del script. Los demás sí:

| Conector | ~Líneas | Depende de (entonces en el script principal) |
|---|---|---|
| Horizon | 326 | `log`, `SOURCE_RUNTIME_METADATA`, 6 constantes propias |
| EEN | 182 | + `_http_get`, `_funding_mechanism`, `_official_call_identifier`, `_extract_deadline_from_text`, `_external_links`, `FUNDING_CONTEXT_TERMS` |
| BDNS | 459 | + `_bdns_descriptions/_codes/_company_eligible/_execution_days`, `_nace_section`, `_is_safe_public_https_url` |
| BOE | 246 | + `PlaywrightBrowser`, `assess_web_inventory_health`, `_document_role`, `_programme_identity` |
| IDAE (+catálogo) | 713 | + `IDENTITY_LANDINGS`, `RUN_DIAGNOSTICS`, `_extract_funding_budget` |
| CDTI | 742 | + `enrich_with_official_documents` (arrastra la caché documental) |
| ECCP | 377 | + `deterministic_prefilter` → la matriz de reglas, reservada |

Es decir: lo que queda no es "mover siete bloques" sino extraer primero una
capa fina de infraestructura compartida. Con ella fuera, seis de los siete
conectores caen casi solos; ECCP queda deliberadamente al final porque lo único
que le falta es la lógica que las secciones 24 y 27 reservan para su propia
sesión.

**Hallazgo 2 — el patrón de tests actual sobrevive a la extracción.**
`tests/test_grant_radar.py` sustituye dependencias con
`mock.patch.dict(APP["fn"].__globals__, {...})`. `__globals__` apunta al módulo
**donde la función está definida**, así que en cuanto un conector se mueva a
`grant_radar/sources/x.py` e importe `_http_get` a su propio espacio de nombres,
ese mismo test seguirá funcionando sin tocarlo. Y `APP["fetch_x"]` sigue
resolviendo mientras el script principal reimporte el nombre público. Esto
abarata mucho las etapas siguientes.

**Extraído en esta ronda (cuatro módulos, uno a uno y verificado entre medias):**

- `grant_radar/runtime_state.py`: `SOURCE_RUNTIME_METADATA`, `IDENTITY_LANDINGS`,
  `COVERAGE_WATCH_RESULTS` y `RUN_DIAGNOSTICS`. Mismo patrón que `audit.py`:
  objetos mutables compartidos, no copias. Se comprobó antes de mover que las
  cuatro se asignan una sola vez en todo el script y que el resto son
  mutaciones (`.clear()`, `.append()`, `d[k] = v`); reasignar cualquiera de
  ellas dentro de una función rompería el enlace sin fallar de forma visible,
  y así queda documentado en el módulo.
- `grant_radar/http_client.py`: `HTTP_USER_AGENT`, `_http_get()` y
  `_is_safe_public_https_url()`. `ipaddress` dejó de usarse en el script
  principal y se retiró de sus imports.
- `grant_radar/source_health.py`: `assess_web_inventory_health()`. Tras extraer
  `runtime_state` solo dependía de `RUN_DIAGNOSTICS` y `log`.
- `grant_radar/call_text.py`: helpers de texto de convocatoria compartidos entre
  fuentes — `FUNDING_CONTEXT_TERMS`, `CALL_LINK_TERMS`, `_funding_mechanism()`,
  `_official_call_identifier()`, `_extract_deadline_from_text()`,
  `_external_links()` y `_extract_funding_budget()`. Módulo propio y no
  `parsing_helpers.py` porque ese es deliberadamente texto/fechas puro y
  `_external_links()` necesita BeautifulSoup.

**Verificación:** `Grant-Radar-prueba.py` bajó de 9.199 a 8.963 líneas (-2,6 %;
recuento con `wc -l`). 283 pruebas `unittest` (238 + 45 nuevas en cuatro
archivos con import estándar) y `py_compile` en verde tras cada extracción.

La ejecución `--no-claude` de cierre (19/08/2026, 05:53-06:04 UTC, 617,97 s de
recopilación, código de salida 0) devolvió **exactamente el mismo resultado que
la referencia de la sección 26**, fuente por fuente:

| Fuente | Sección 26 (18/08) | Tras esta ronda (19/08) |
|---|---|---|
| BDNS | 47 | 47 |
| Horizon Europe | 19 | 19 |
| CDTI | 5 | 5 |
| ECCP | 4 | 4 |
| EEN | 2 | 2 |
| IDAE | 1 | 1 |
| BOE / MITECO | 1 | 1 |
| BOA Aragón | 0 | 0 |
| **Total vigentes** | **77** | **77** |

También coincide la previsión de coste ($2,0405 central, 154 llamadas) y las
cuatro fuentes con control de salud siguen `healthy`. Las diferencias están solo
en el volumen bruto —953 convocatorias detectadas frente a 948, y 904 candidatas
BDNS frente a 899—, variación normal de datos reales entre dos días distintos.
Invariantes confirmadas: no se llamó a Claude, no se modificó la caché IA
(`grant_radar_cache.json` sigue con fecha 14/08) y no se generó ni publicó
`convocatorias.json`.

Nota de comportamiento observada al escribir los tests: `_extract_funding_budget()`
no reconocía "2,5 millones **de** euros" aunque sí "2,5 millones EUR". Se dejó
fijado como test explícito sin corregir, por quedar fuera del alcance de una
extracción que debía preservar el comportamiento. **Corregido a continuación,
con dos fallos más del mismo patrón: ver sección 31.**

Sigue pendiente: `browser.py` (`PlaywrightBrowser`), `dedup.py` (identidad y
deduplicación documental), los siete conectores, `documents.py` (enriquecimiento
documental, necesario para CDTI) y `pipeline.py`.

## 29. Séptima ronda a 19/08/2026: conectores Horizon y EEN, y un NameError latente

Primera etapa de conectores apoyada en la capa de infraestructura de la sección
28. Ambos se movieron sin cambiar una línea de su lógica.

- `grant_radar/sources/horizon_europe.py`: `fetch_horizon_europe()`,
  `_fetch_horizon_rss_fallback()`, `_sedia_meta()`, `_sedia_values()` y las seis
  constantes `_SEDIA_*`/`_HORIZON_*`. Tras la sección 28 su única dependencia
  del script era `log`.
- `grant_radar/sources/een.py`: `fetch_een_funding()`, `_een_listing_params()`,
  `_een_profile_call_links()`, `_een_call_from_page()` y las constantes `EEN_*`.
  Usa cinco helpers de `call_text.py` y `_http_get()`, ya extraídos.
- `ENTIDADES_CANONICAS` se había arrastrado sin querer dentro de `een.py` al
  cortar por rango de texto: no es del conector (la usa `post_procesar_texto()`
  en la normalización de entidades) y se devolvió al script principal. Lección
  para las etapas siguientes: el análisis AST da las funciones del grupo, pero
  el corte por rango puede llevarse constantes vecinas; revisar siempre los
  nombres de nivel superior del módulo nuevo antes de dar por buena la
  extracción.
- `tests/test_grant_radar.py`: el bloque de fusión de `APP` incorpora ahora
  `grant_radar.sources.een`, porque siete tests usan `_een_call_from_page()`,
  un helper privado que el script no reimporta. Confirmado en la práctica el
  hallazgo 2 de la sección 28: los tests que sustituyen dependencias con
  `mock.patch.dict(APP["fn"].__globals__, ...)` no necesitaron ningún cambio.

**Fallo latente encontrado y corregido (anterior a esta sesión).**
`_build_compatible_analysis()` llamaba a catorce funciones de
`grant_radar/deterministic_rules.py` —`_correct_*`, `_enforce_*`,
`_hard_ineligibility`, `_derive_priority`, `_review_reasons`...— que el script
principal **nunca reimportó** al extraerlas en la sección 23. Una ejecución real
con Claude habría fallado con `NameError` justo después de pagar la primera
llamada a Haiku. Estaba enmascarado por dos motivos independientes:

1. `--no-claude` no ejecuta esa ruta, así que ninguna de las validaciones
   reales de las secciones 23-28 pudo detectarlo.
2. El bloque de fusión de `APP` de `tests/test_grant_radar.py` inyecta los
   nombres que faltan en los propios globals del script —`runpy.run_path()`
   devuelve ese diccionario, no una copia—, de modo que reparaba el fallo justo
   antes de probarlo.

Corregido añadiendo las catorce al import existente. Para que no vuelva a
ocurrir en las etapas siguientes, `tests/test_grant_radar_script_names.py`
(nuevo) carga el script con `runpy` en unos globals limpios, sin la fusión, y
comprueba que ningún nombre llamado falte, encadenando ámbitos para no
confundir parámetros de funciones anidadas, hermanas anidadas ni recursión.
Incluye seis casos sintéticos que demuestran que el detector sí falla cuando
debe: una prueba que no puede fallar no protege de nada.

**Verificación:** `Grant-Radar-prueba.py` bajó de 8.963 a 8.403 líneas (-6,2 %
en esta ronda; -8,7 % acumulado en el día desde 9.199). 295 pruebas `unittest`
(287 + 8) y `py_compile` en verde. La ejecución `--no-claude` de cierre
(547,30 s, código 0) volvió a dar exactamente los mismos números que la de la
sección 28 y que la referencia de la sección 26: 953 convocatorias detectadas,
39 tras el prefiltro inicial, 77 vigentes con idéntico desglose por fuente
(BDNS 47, Horizon 19, CDTI 5, ECCP 4, EEN 2, IDAE 1, BOE 1, BOA 0), mismo
prefiltro común (retain=32, ambiguous=7, hold_manual=73, reject=841) y misma
previsión de coste ($2,0405). Sin llamadas a Claude, sin tocar la caché IA, sin
generar ni publicar `convocatorias.json`.

Sigue pendiente: `browser.py` (`PlaywrightBrowser`), `dedup.py`, los conectores
BOE, IDAE, BDNS y CDTI (este último tras `documents.py`), ECCP —que solo espera
por `deterministic_prefilter()`— y `pipeline.py`.

## 30. Octava ronda a 19/08/2026: navegador e identidad documental

Segunda mitad de la capa de infraestructura (etapa 3 del plan de la sección
28). Es la que desbloquea los conectores que faltan: BOE, IDAE y CDTI dependen
de estas dos piezas.

- `grant_radar/browser.py`: la clase `PlaywrightBrowser`, sesión Chromium única
  compartida por las cuatro fuentes sin API. Su única dependencia del script
  era `log`. El script principal dejó de importar `playwright.sync_api`: ahora
  solo lo necesita este módulo.
- `grant_radar/sources/boa_aragon.py`: con la clase ya importable, el parámetro
  `browser` se tipa de verdad como `PlaywrightBrowser` en vez de `typing.Any`.
  Era una limitación explícita de la sección 25 y desaparece sola.
- `grant_radar/dedup.py`: `_programme_identity()`, `_document_role()`,
  `_document_rank()`, `_add_discovery_source()` y
  `_deduplicate_raw_convocations()`. Cero dependencias del script: solo
  `audit_exclusion`, `_official_call_identifier`, `_fold_text` y
  `select_evidence_excerpt`, todos ya extraídos. Es el bloque más central
  movido hasta ahora — decide qué convocatorias son la misma y cuál manda—,
  pero también uno de los más autónomos.

Aplicada la lección de la sección 29: se comprobaron los nombres de nivel
superior de cada módulo nuevo antes de dar la extracción por buena. `dedup.py`
contiene exactamente las cinco funciones previstas y nada más.

**Verificación:** `Grant-Radar-prueba.py` bajó de 8.403 a 7.977 líneas (-5,1 %
en esta ronda; -13,3 % acumulado en el día desde 9.199). 317 pruebas `unittest`
(295 + 22) y `py_compile` en verde. Dos archivos de test nuevos: `browser.py`
se prueba sin arrancar Chromium, sustituyendo `context` por un doble, y cubre
lo que es lógica propia de la clase (cuándo devuelve cadena vacía, cuándo marca
un ámbito bloqueado por WAF y cuándo deja de insistir, incluido el caso IDAE,
que bloquea solo las fichas de detalle y no el inventario); `dedup.py` prueba
por separado las tres piezas del criterio de identidad, que hasta ahora solo se
ejercitaban a través de la deduplicación completa.

La ejecución `--no-claude` de cierre (551,88 s, código 0) repite exactamente los
números de las secciones 26, 28 y 29: 953 convocatorias detectadas, **33
duplicadas fusionadas** —la cifra que probaría un fallo de la deduplicación si
hubiera cambiado—, 39 tras el prefiltro inicial, 77 vigentes con idéntico
desglose por fuente, mismo prefiltro común y misma previsión de coste. Chromium
arrancó desde el módulo nuevo y las cuatro fuentes con control de salud siguen
`healthy`. Sin llamadas a Claude, sin tocar la caché IA, sin generar ni publicar
`convocatorias.json`.

Sigue pendiente: los conectores BOE, IDAE, BDNS y CDTI (este último tras
`documents.py`), ECCP —que solo espera por `deterministic_prefilter()`— y
`pipeline.py`.

## 31. Notas de comportamiento verificadas a 19/08/2026

Comportamientos concretos comprobados con código en las rondas 28-30. No son
decisiones nuevas: son cómo se comporta realmente el sistema, escrito aquí
para no tener que volver a deducirlo leyendo expresiones regulares.

### 31.1. `_extract_funding_budget()` — tres fallos corregidos

El campo `budget` que devuelve esta función lo producen solo IDAE y ECCP, se
muestra en la tarjeta del dashboard, viaja en la evidencia enviada a Haiku y
**entra en `source_hash()`**: cambiarlo puede invalidar entradas de caché y
provocar reanálisis de pago. Por eso se midió antes de tocar nada.

| Texto real | Antes | Ahora |
|---|---|---|
| `Presupuesto: 2,5 millones de euros` | `Ver convocatoria` | `2,5 millones de euros total` |
| `Dotación: 3.000.000 de euros` | `Ver convocatoria` | `3.000.000 de euros total` |
| `Dotación de 2.500.000 euros` | `Ver convocatoria` | `2.500.000 euros total` |
| `Total budget: 2.5 million euros` | `2.5 million **eur** total` | `2.5 million euros total` |

Las causas eran tres y distintas: la preposición intermedia rompía el patrón;
la alternancia de moneda empezaba por `EUR` y, siendo insensible a mayúsculas,
se comía las tres primeras letras de "euros"; y el patrón solo tenía `dotacion`
sin tilde, porque esta función —a diferencia de `_extract_deadline_from_text()`—
no pliega el texto (devuelve el literal encontrado, así que no puede plegarlo
sin perder el original).

Impacto de caché medido, no supuesto: los cinco registros ECCP/IDAE de
`convocatorias.json` daban `Ver convocatoria` y ninguno contenía la expresión
afectada, así que ningún hash existente cambió.

Se conserva a propósito el respaldo cuando el importe **no** es la dotación:
"el presupuesto mínimo del proyecto es de 175.000 euros" describe un umbral por
proyecto y sigue devolviendo `Ver convocatoria`. Publicarlo como presupuesto
sería peor que no publicar nada.

### 31.2. `_programme_identity()` se queda en el acrónimo, sin ordinales

`_programme_identity("Convocatoria del Programa MOVES III")` devuelve
`("moves", "MOVES")`, no `"moves iii"`: el patrón de nombre directo corta en el
primer espacio. Es el comportamiento correcto para lo que hace falta —permite
fusionar "MOVES III" con "MOVES III 2026" o con una modificación posterior—,
pero conviene tenerlo presente si alguna vez dos programas comparten acrónimo y
se distinguen solo por el ordinal. No ha ocurrido con las fuentes actuales.

La función es deliberadamente conservadora en el otro sentido: exige la palabra
"programa" en el título y rechaza acrónimos administrativos genéricos (`FEDER`,
`PRTR`, `IDAE`, `MITECO`, `BOE`...) y años sueltos, porque fusionar por ellos
uniría convocatorias sin ninguna relación.

### 31.3. `PlaywrightBrowser` bloquea por ámbito, no siempre por host

Cuando una web responde con un bloqueo de WAF, `html()` recuerda el ámbito para
no insistir el resto de la ejecución. Para IDAE ese ámbito **no** es el host
entero sino `www.idae.es:grant-details`, y solo cuando la ruta empieza por
`/ayudas-y-financiacion/`: IDAE bloquea las fichas de detalle pero sirve el
inventario sin problema, y marcar el host completo perdería la fuente entera.
Cubierto en `tests/test_grant_radar_browser.py`.

### 31.4. El patrón de tests sobrevive a las extracciones

`mock.patch.dict(APP["fn"].__globals__, {...})` sigue funcionando después de
mover una función a un módulo, porque `__globals__` apunta al módulo donde la
función queda definida. Verificado en las rondas 29 y 30: ni un solo test de
`tests/test_grant_radar.py` necesitó reescribirse por una extracción. Lo único
que hay que añadir es el módulo nuevo al bloque de fusión de `APP` cuando los
tests usen alguno de sus helpers privados, que el script principal no reimporta.

El reverso de esa comodidad está en la sección 29: ese mismo bloque de fusión
puede tapar un `NameError` real. Por eso existe
`tests/test_grant_radar_script_names.py`, que carga el script con globals
limpios.

### 31.5. `_bdns_company_eligible()`: la vía de autónomos está partida

Detectado al escribir los tests de `grant_radar/bdns_fields.py` (sección 33).
La condición positiva busca `"persona fisica"` en **singular** y el guardián
que la anula busca `"no desarrollan"` en **plural verbal**. Ninguna cadena real
puede cumplir las dos a la vez, así que el guardián nunca llega a aplicarse.

**Impacto real medido: ninguno.** Estas son las únicas categorías de
beneficiario que SNPSAP entrega, con sus apariciones en los artefactos
locales, y la función acierta en las cuatro:

| Categoría real de SNPSAP | Veces | Resultado | ¿Correcto? |
|---|---|---|---|
| `PYME Y PERSONAS FÍSICAS QUE DESARROLLAN ACTIVIDAD ECONÓMICA` | 644 | `True` | sí, por "PYME" |
| `GRAN EMPRESA` | 264 | `True` | sí |
| `PERSONAS JURÍDICAS QUE NO DESARROLLAN ACTIVIDAD ECONÓMICA` | 134 | `False` | sí |
| `PERSONAS FÍSICAS QUE NO DESARROLLAN ACTIVIDAD ECONÓMICA` | 20 | `False` | sí |

La rama de personas físicas nunca llega a decidir: cuando aparece, viene
acompañada de "PYME", que resuelve antes. Los casos sintéticos en singular que
exponen la incoherencia no existen en la fuente.

**Nota sobre acentos:** no hacen falta variantes acentuadas. `_fold_text()` se
aplica antes de comparar y los elimina; por eso el código escribe `pequena`,
`fisica` y `economica`. Añadir `física` o `económica` sería código muerto.

**Qué haría falta si se retoma**, por orden de importancia:

1. **Decidir primero si esa rama debe existir para este perfil.** Kalfrisa es
   una empresa mediana, o sea una persona jurídica: una convocatoria dirigida
   solo a autónomos la excluye. Arreglar el plural haría que esas
   convocatorias pasaran a contar como elegibles para empresa, un falso
   positivo nuevo. Hoy el fallo actúa como red de seguridad accidental. Es una
   decisión de negocio, no técnica.
2. Si se conserva la rama, hacerla simétrica: `personas? fisicas?` en el
   positivo y `"no desarrolla"` en el guardián (que cubre singular y plural
   por ser prefijo), más `actividad(es) economica(s)` para el plural del
   complemento.
3. Documentar el contrato de entrada: la función espera **etiquetas cortas de
   categoría** de SNPSAP, no texto libre. `re.search(r"empresas?", ...)`
   es seguro sobre "GRAN EMPRESA", pero sobre el texto completo de unas bases
   acertaría con cualquier mención incidental a "empresas", incluidas las de
   las cláusulas de exclusión.

Cualquiera de los tres, con la disciplina de `SUGERENCIAS.MD` 3.3: ampliar
primero `tests/fixtures/bdns_filter_cases.json` con categorías reales, y solo
después tocar la condición. El comportamiento actual está fijado en
`tests/test_grant_radar_bdns_fields.py` para que un cambio no pase inadvertido.

**No se hace durante las etapas de modularización a propósito:** cambiar la
matriz altera qué convocatorias llegan a Haiku, y el recuento estable de 77
vigentes es justamente el invariante con el que se verifica que cada
extracción no rompió nada. Mezclarlo haría ambiguo ese control.

## 32. Novena ronda a 19/08/2026: conectores BOE/MITECO e IDAE

Etapa 4 del plan de la sección 28, y la primera que se apoya en la
infraestructura completa: ambos conectores usan navegador, control de salud e
identidad documental, ya todos en módulos. Tras la sección 30 su única
dependencia del script principal era `log`.

- `grant_radar/sources/idae.py` (802 líneas): los dos inventarios de la misma
  casa. `fetch_idae()` recorre fichas de ayudas y financiación con Chromium,
  recupera fechas de la propia ficha y recoge documentos oficiales enlazados,
  registrando en `IDENTITY_LANDINGS` las landings de programa que encuentra;
  `fetch_idae_catalog()` lee el catálogo por ámbito (estatal, Aragón y
  Zaragoza) e incorpora solo entradas con convocatoria abierta verificable.
- `grant_radar/sources/boe_miteco.py` (288 líneas): `fetch_boe()`, la vía por
  la que entran convocatorias estatales sin inventario web propio utilizable y
  los extractos oficiales de programas que también llegan por IDAE o BDNS.
- `tests/test_grant_radar.py`: el bloque de fusión de `APP` incorpora el módulo
  IDAE, por `_parse_idae_inventory_html()`. Es la tercera vez que hace falta y
  siempre por el mismo motivo: un test usa un helper privado que el script
  principal no reimporta.

Dos archivos de test nuevos, deliberadamente complementarios a lo que ya
cubría `tests/test_grant_radar.py`: para IDAE, los helpers del catálogo y de
documentos oficiales (ámbito, rango documental, filtrado de enlaces), que solo
se ejercitaban de forma indirecta; para BOE, el modo de fallo real —inventario
inalcanzable, marcado cambiado, convocatoria sin plazo confirmado—, porque el
caso positivo ya estaba probado y el parser de esta fuente ya se rompió una vez
por un cambio de marcado.

**Verificación:** `Grant-Radar-prueba.py` bajó de 7.977 a 6.976 líneas (-12,5 %
en esta ronda; -24,2 % acumulado en el día desde 9.199). 331 pruebas
`unittest` (317 + 14) y `py_compile` en verde. La ejecución `--no-claude` de
cierre (568,97 s, código 0) repite de nuevo los mismos números: 953
convocatorias detectadas, 33 duplicadas fusionadas, 39 tras el prefiltro
inicial, 77 vigentes con idéntico desglose, mismo prefiltro común y misma
previsión de coste. Las cuatro fuentes con control de salud siguen `healthy`,
con los inventarios esperados (ECCP 227, BOE 179, IDAE 97, CDTI 14).

Nota de comportamiento observada al escribir los tests, sin corregir por quedar
fuera del alcance de una extracción: en `_idae_catalog_document_rank()`, un
título como "Modificación de la convocatoria" suma por nombrar la convocatoria
(+4) y resta por ser modificación (-2), así que queda por encima de un
documento neutro. Es coherente —habla de la convocatoria— y en cualquier caso
pierde frente al extracto real, que es lo que decide. Fijado como test
explícito.

Sigue pendiente: los conectores BDNS y CDTI (este último tras `documents.py`),
ECCP —que solo espera por `deterministic_prefilter()`— y `pipeline.py`.

## 33. Décima ronda a 19/08/2026: conector BDNS

Etapa 5 del plan de la sección 28, y la que exigía más cuidado: BDNS aporta 899
de las 953 convocatorias detectadas, y su conector comparte primitivas con la
matriz de reglas previa a Claude, que no se debe tocar.

- `grant_radar/bdns_fields.py`: las seis piezas compartidas —
  `BDNS_NAMED_ACCESS_TERMS`, `_bdns_descriptions()`, `_bdns_codes()`,
  `_nace_section()`, `_bdns_company_eligible()` y `_bdns_execution_days()`.
  El análisis previo confirmó que tres las usa solo el conector y tres las
  comparte con la matriz (`_bdns_pre_claude_gate()`,
  `_bdns_intrinsic_exclusion()` y `_validated_hold_resolution()`). El script
  principal las reimporta, igual que ya hacía con
  `BDNS_DIRECT_OWN_INVESTMENT_TERMS`, de modo que el conector se movió **sin
  tocar una línea** de la matriz. `_bdns_applicant_section()` y
  `_bdns_gate_result()` se quedan en el script: son de la matriz, no del
  conector.
- `grant_radar/sources/bdns.py`: `fetch_bdns()`, `fetch_bdns_by_id()`,
  `_bdns_detail_to_raw()`, `_bdns_document_records()`,
  `_bdns_call_publication_date()`, `_bdns_relative_application_deadline()`,
  `_add_calendar_months()` y las constantes `BDNS_*` de listado.
  `resolve_hold_deterministically()` usa
  `_bdns_relative_application_deadline()` al recalcular un plazo desde la cita
  de las bases, así que el script la reimporta explícitamente.
- `tests/test_grant_radar.py`: el módulo BDNS entra en el bloque de fusión de
  `APP`, y `BDNS_LATEST_MAX_PAGES`/`BDNS_PAGE_SIZE` se añaden aparte, porque el
  bucle solo copia nombres privados y el script no reimporta esas constantes.

**Dos fallos detectados por las pruebas durante la propia ronda,** los dos
corregidos antes de cerrarla:

1. `bdns_fields.py` se quedó sin `from grant_radar.parsing_helpers import
   _fold_text`. El análisis AST previo solo listaba dependencias definidas en
   el script, no las importadas, y por eso no apareció. La suite lo detectó,
   pero como 27 errores en pruebas de otra cosa.
2. `resolve_hold_deterministically()` quedó llamando a una función ya movida.
   Lo detectó `tests/test_grant_radar_script_names.py`, creado en la sección 29
   exactamente para esto: señaló el nombre y la línea.

A raíz del primero, esa misma prueba se amplió con `PackageModuleNamesTests`,
que importa cada módulo de `grant_radar/` y comprueba que resuelve los nombres
que llama. Verificado que no pasa en vacío: quitando el import de `_fold_text`
de forma temporal, falla señalando `grant_radar.bdns_fields` y el nombre
exacto. Ahora un import olvidado se señala en el módulo culpable, no a través
de errores en pruebas ajenas.

**Verificación:** `Grant-Radar-prueba.py` bajó de 6.976 a 6.409 líneas (-8,1 %
en esta ronda; -30,3 % acumulado en el día desde 9.199). 349 pruebas
`unittest` (331 + 18) y `py_compile` en verde. La ejecución `--no-claude` de
cierre (810,73 s, código 0; el tiempo varía con la latencia de la API, no con
el código) repite todos los números, incluidos los propios de BDNS: 4.475
registros inventariados, 904 candidatas del prefiltro de listado, 47 vigentes,
953 convocatorias detectadas, 33 duplicadas fusionadas, mismo prefiltro común
y misma previsión de coste.

Nota de comportamiento nueva, sin corregir por ser matriz de reglas: ver 31.5
sobre `_bdns_company_eligible()`.

Sigue pendiente: CDTI (tras `documents.py`), ECCP —que solo espera por
`deterministic_prefilter()`— y `pipeline.py`.

## 34. Undécima ronda a 19/08/2026: capa documental y conector CDTI

Etapa 6 del plan de la sección 28. CDTI era el único conector bloqueado por una
dependencia que no era infraestructura genérica sino un dominio propio: el
enriquecimiento con documentos oficiales.

- `grant_radar/documents.py`: `enrich_with_official_documents()`,
  `_hold_document_text()` (extracción de texto de HTML, texto plano y PDF), la
  caché documental de fuentes (`_load/_save_source_document_cache()`,
  `_source_document_cache_key()`, `_SOURCE_DOCUMENT_CACHE_STATE`) y
  `_official_document_priority()`, más las constantes de política de tamaño y
  reintento.
  **Decisión de diseño:** la ruta `SOURCE_DOCUMENT_CACHE_FILE` se calcula ahora
  en el módulo, a partir de la posición del paquete, y el script la importa —al
  revés que con la caché de análisis (sección 23), donde la ruta se pasa como
  parámetro. El motivo es que CDTI llama a `enrich_with_official_documents()` y
  también es un módulo: pasar la ruta habría obligado a hacerla viajar por una
  firma más sin ganar nada. Hay un test que ata la ruta resultante a
  `grant_radar_data/source_document_cache.json` bajo la raíz del proyecto, para
  que módulo y script no puedan acabar escribiendo en ficheros distintos sin
  que salte nada. Verificado además contra la ruta real antes y después.
  `_hold_document_text()` la sigue usando `retrieve_bdns_hold_evidence()`, que
  permanece en el script y la reimporta.
- `grant_radar/sources/cdti.py`: las diez funciones del conector, incluido el
  calendario oficial con Chromium, el catálogo curado de ventanilla abierta y
  `_merge_cdti_results()`, que los combina con prioridad creciente.

Con esto, `grant_radar/sources/` reúne siete de los ocho conectores: BDNS,
BOA Aragón, BOE/MITECO, CDTI, EEN, Horizon Europe e IDAE. Solo queda ECCP, que
no espera por infraestructura sino por `deterministic_prefilter()`, es decir
por la sesión dedicada a las reglas.

**Verificación:** `Grant-Radar-prueba.py` bajó de 6.409 a 5.384 líneas (-16,0 %
en esta ronda; -41,5 % acumulado en el día desde 9.199). 361 pruebas
`unittest` (349 + 12) y `py_compile` en verde. La ejecución `--no-claude` de
cierre (702,12 s, código 0) repite todos los números por sexta vez: 953
convocatorias detectadas, 33 duplicadas fusionadas, 39 tras el prefiltro
inicial, 77 vigentes con idéntico desglose —CDTI en sus 5—, mismo prefiltro
común y misma previsión de coste. Las cuatro fuentes con control de salud
siguen `healthy` y la caché documental se leyó y escribió con normalidad desde
el módulo nuevo.

## 35. Duodécima ronda a 19/08/2026: conector ECCP y dos NameError latentes

Etapa 7 del plan de la sección 28, y con ella los ocho conectores están fuera
del script principal.

**Cambio de criterio respecto a la sección 28, con motivo.** Aquel plan
recomendaba esperar a la sesión de reglas antes de mover ECCP, y advertía de no
"forzar la inyección solo para cerrar la lista". Al leer el código real, los
dos usos de `deterministic_prefilter()` en ECCP resultaron ser un **predicado de
relevancia**, no la matriz de elegibilidad: filtrar páginas al rastrear la web
de un proyecto beneficiario, y elegir la muestra del experimento de
profundidad. Con eso, `is_relevant_enough` como parámetro no es un
contorsionismo sino la costura natural: el conector declara que necesita "algo
que diga si esto merece conservarse" y el script le pasa
`deterministic_prefilter()`, que no se ha tocado.

- `grant_radar/sources/eccp.py`: inventario de calls y rastreo acotado de webs
  de proyectos, con `robots.txt`, HTTPS y límites de peticiones, bytes y
  tiempo. `fetch_eccp(is_relevant_enough)` y
  `_crawl_project_domain(..., is_relevant_enough)`.
- `tests/test_grant_radar_sources_eccp.py`: prueba la costura nueva con
  predicados de mentira —uno que acepta todo y otro que rechaza todo—, de modo
  que el rastreo se ejercita sin depender de las reglas.

**Dos NameError, y lo que enseñan sobre las tres redes de seguridad:**

1. `statistics` faltaba en los imports del módulo nuevo. No lo vieron ni
   `py_compile` (no resuelve nombres) ni las 369 pruebas (el cuerpo de
   `fetch_eccp()` solo se ejecuta con red). **Lo cazó la ejecución
   `--no-claude`**, que abortó con código 1. Es exactamente el motivo por el
   que esa ejecución es obligatoria al cerrar cada ronda y no un trámite.
2. Al ampliar el detector de nombres para cubrir ese hueco apareció un segundo
   fallo, **preexistente desde el commit inicial**: `fetch_idae_catalog()`
   llamaba a `select_evidence_excerpt(description, title, ...)` con un `title`
   que nunca se define en ese ámbito. Nunca ha estallado porque el catálogo
   IDAE lleva tiempo sin aportar convocatorias incorporables (0 en todas las
   ejecuciones recientes), así que esa línea no se ejecuta; el día que el
   catálogo tenga una convocatoria abierta, la fuente entera caería. Corregido
   a `candidate["title"]`, que es el título que la propia función usa dos
   líneas más arriba.

`tests/test_grant_radar_script_names.py` tenía dos puntos ciegos, ambos
cerrados en esta ronda: solo miraba llamadas a nombres desnudos —por eso
`statistics.median(...)` pasó, ya que ahí el nombre ausente es el objeto del
atributo— y no reconocía los parámetros de una `lambda` como ámbito propio.
Ahora comprueba todo nombre leído. Los dos casos quedan fijados como pruebas
sintéticas: una comprobación que no falla cuando debe no protege de nada.

**Verificación:** `Grant-Radar-prueba.py` bajó de 5.384 a 5.018 líneas (-6,8 %
en esta ronda; -45,5 % acumulado en el día desde 9.199). 371 pruebas
`unittest` (361 + 10) y `py_compile` en verde. En la ejecución `--no-claude` de
cierre (630,15 s, código 0): 953 convocatorias detectadas, 39 tras el prefiltro
inicial, 77 vigentes, mismo prefiltro común y misma previsión de coste. ECCP,
que es lo que toca esta ronda, dio exactamente lo mismo que antes: 6 calls
vigentes, profundidad seleccionada 1 y 4 convocatorias tras consolidar.

**Salvedad honesta sobre esa ejecución:** BOE/MITECO devolvió 0 en vez de 1, y
las duplicadas fusionadas bajaron de 33 a 31, por una causa externa que el
propio sistema detectó y avisó: `HTTP 429` de `boe.es`, con estado de salud
`unhealthy` e `inventory_unreachable`. No es una regresión —esta ronda no toca
el conector BOE, extraído en la sección 32— y el total se mantuvo en 77 porque
INNOVAE también entra por IDAE. El control de salud hizo justo su trabajo:
avisar en vez de perder cobertura en silencio.

**Nota operativa que se deriva de ese 429:** las ejecuciones `--no-claude` no
consumen tokens, pero sí consumen paciencia de las fuentes públicas. Hoy se han
hecho ocho, y cada una carga unas 180 fichas del BOE. Conviene espaciarlas o
limitar la verificación a las fuentes que toca cada cambio cuando se encadenen
varias rondas en el mismo día.

Sigue pendiente: `pipeline.py` (`run_pipeline()` y el ensamblado del JSON), y
la sesión dedicada a la matriz de reglas.

## 36. Hallazgos abiertos y propuestas para iteraciones posteriores

Índice único de lo que se ha descubierto y **no** se ha hecho, con el motivo y
lo que costaría retomarlo. Las rondas anteriores lo documentan en su contexto;
esta sección existe para no tener que releerlas todas. Actualizar al cerrar o
al añadir cada punto.

### 36.1. Reglas de negocio (requieren decisión, no solo código)

| # | Hallazgo | Dónde | Por qué sigue abierto |
|---|---|---|---|
| 1 | `_bdns_company_eligible()`: la condición positiva está en singular y su guardián en plural, así que el guardián nunca se aplica | 31.5 | Impacto medido nulo sobre las cuatro categorías reales de SNPSAP. Antes del plural hay que decidir si esa rama debe conceder elegibilidad a un perfil que es persona jurídica: arreglarla crearía un falso positivo con convocatorias solo para autónomos |
| 2 | `_idae_catalog_document_rank()`: "Modificación de la convocatoria" queda por encima de un documento neutro | 32 | Es coherente (habla de la convocatoria) y siempre pierde frente al extracto real. Cambiarlo altera qué documento manda al consolidar |
| 3 | El contrato de entrada de `_bdns_company_eligible()` no está escrito: espera etiquetas cortas de categoría, no texto libre | 31.5 | Sobre texto completo de unas bases, `empresas?` acertaría con cualquier mención incidental, incluidas las de cláusulas de exclusión |

Los tres comparten condición: tocan la matriz previa a Claude, que decide qué
llega a Haiku y por tanto el coste. Disciplina obligatoria (`SUGERENCIAS.MD`
3.3): ampliar primero `tests/fixtures/bdns_filter_cases.json` con casos reales,
y solo después la condición. Además, mientras duren las rondas de
modularización conviene no mezclarlos: el recuento de vigentes es la referencia
con la que se verifica cada extracción —76 desde el 20/08, 77 antes— y cambiar
una regla lo haría ambiguo. Aviso: ese recuento ya no es un invariante fijo,
porque la ventana deslizante de BDNS lo mueve por causas externas (punto 26).
Con más razón conviene no introducir a la vez un cambio de reglas.

### 36.2. Fragilidad frente a las fuentes

| # | Propuesta | Origen |
|---|---|---|
| 4 | Reintento con espera ante `HTTP 429` en `PlaywrightBrowser`, en vez de tratarlo como fuente caída | 35 |
| 6 | Instantánea de la estructura esperada de cada fuente, comparada en cada ejecución, con historial | `SUGERENCIAS.MD` 3.4 punto 2 |
| 7 | Ejecución periódica automatizada en `--no-claude` solo para vigilar salud de fuentes | `SUGERENCIAS.MD` 3.4 punto 3 |
| 27 | Los catálogos curados se teclean a mano y caducan en silencio: el 21/08, seis de las diez URLs del de CDTI eran 404 (sección 44.1). **Medido el 01/09 (sección 55.2): el catálogo de CDTI aporta 4 de sus 5 vigentes, el 80 %**, porque la ventanilla permanente no tiene fecha y el calendario oficial solo publica lo fechado. No es deuda que retirar: derivarlo del calendario probablemente no es posible, y lo que necesita es revisión periódica | Vale la pena estudiar si las entradas de ventanilla permanente pueden **derivarse** del listado oficial en vez de mantenerse a mano. `_drop_catalog_entries_with_dead_urls()` ya evita publicarlas rotas, pero no las repara |
| 29 | El prefiltro de listado del BOE descarta 153 de 168 entradas **sin registrar exclusión**: solo deja rastro el filtro posterior, sobre el documento ya abierto | Sección 45.2. Auditar las 153 inflaría el catálogo (365 ejecuciones guardadas); lo razonable es un recuento por organismo, no una entrada por ficha |
| 30 | Los umbrales de salud son absolutos y calibrados a mano sobre un solo día | Sección 45.1. `compare_funnels()` ya cubre lo que un umbral absoluto no puede, pero la evolución natural es derivar los umbrales del historial de la auditoría en vez de fijarlos en el conector |
| 32 | Nueve hosts responden 200 a cualquier ruta, no solo `cdti.es`: sedes electrónicas y fundaciones públicas, 13 URLs publicadas afectadas | Sección 46.3. Hoy solo se avisa. Verificarlas de verdad exigiría navegador, que es caro para 13 URLs por ejecución; decidir si compensa o si basta con marcarlas en el dashboard |
| 34 | Programar la recopilación `--no-claude` diaria en el Programador de tareas de Windows | Sección 47.6 tiene el comando. **Es una acción del usuario en su equipo**, no del agente: queda anotada para no darla por hecha |
| 37 | **La ejecución completa**, ~2,02 USD sobre 79 convocatorias, **cuando el usuario lo decida** | Sección **54.9**. Los tres controles de 53.2 ya están ejercitados: presupuesto y elegibilidad de Horizon el 01/09 (54.4) y el territorial de Navarra el mismo día (54.10), por 0,1271 USD en total. No queda validación pendiente; lo que falta es publicar, y **la prioridad fijada por el usuario es depurar antes que publicar**: informar del desfase sí, convertirlo en urgencia no. **Requiere autorización expresa** |

El 429 del 19/08/2026 tuvo cooldown de minutos: una sonda de una sola petición,
7 minutos después, devolvió la página completa. No impone restricción horaria,
pero sí aconseja espaciar las ejecuciones completas cuando se encadenan varias
rondas el mismo día.

### 36.3. Modularización pendiente

| # | Qué falta | Notas |
|---|---|---|
| 9 | Motor de reglas genérico, declarativo | `SUGERENCIAS.MD` 3.3 punto 2. Requiere formalizar antes todas las variantes de condición existentes |
| 15 | Orden de extracción medido (secciones 37 y 38): `save_discovery_audit` → capa Haiku → segunda mitad de holds → reglas → `run_pipeline()`. **Los cuatro primeros están cerrados**: los tres primeros el 31/08 (sección 48) y la matriz de reglas el 01/09 (sección 57) | Queda solo `run_pipeline()`, que va el último por definición y hoy ya no arrastra lógica de dominio: el script conserva cuatro funciones y ninguna lo es |
| 21 | Ejecutar `tests/test_grant_radar_script_names.py` **antes** que la suite completa tras cada extracción | Señala el módulo y el nombre exactos en un segundo; la suite completa los presenta como errores en pruebas de otra cosa (pasó tres veces) |
| 16 | Usar `node.end_lineno`, nunca `max(lineno)`, al cortar bloques por AST | Un `return (` multilínea pierde el paréntesis de cierre; ocurrió en la sección 37 |

### 36.4. Huecos de cobertura de pruebas, medidos

Recuento sobre los 38 módulos del paquete a 31/08/2026. Desde el 01/09 hay dos
archivos de prueba más con import estándar, `tests/test_grant_radar_gap_report.py`
(26) y `tests/test_grant_radar_source_selection.py` (13), que no tapan ninguno
de los huecos de abajo pero sí marcan la forma preferida: import normal, sin
`runpy`.

| # | Qué | Detalle |
|---|---|---|
| 20 | **Los ocho conectores ya tienen archivo propio** desde el 01/09 (sección 55.3: BDNS con 20 pruebas y EEN con 17; CDTI y Horizon lo ganaron antes). Siguen sin archivo dedicado, cubiertos solo de forma indirecta vía `runpy`: `versions.py`, `publishing.py`, `claude_usage.py`, `hold_quotes.py`, `hold_evidence.py`, `holds.py` y `profile_scope.py` | No es urgente —el camino principal de cada uno se ejercita ahí—, pero un archivo propio con import estándar hace la regresión más legible y sobreviviría a retirar el patrón `runpy` (punto 10). `analysis.py` sí tiene ya uno para lo que más duele: `tests/test_grant_radar_prompts.py` |

### 36.5. Mapa de las tres redes de seguridad, y qué se escapa de cada una

Aprendido a base de que fallaran, en las secciones 29, 33 y 35:

| Red | Qué caza | Qué se le escapa |
|---|---|---|
| `py_compile` | Sintaxis rota (cazó el corte mal calculado con `max(lineno)`, sección 37) | No resuelve nombres: un import olvidado pasa entero |
| Suite `unittest` | Todo lo que el test toca de verdad, incluida la integridad de los módulos con `test_grant_radar_script_names.py` | Rutas que solo se ejecutan con red; y el bloque de fusión de `APP` puede **tapar** un `NameError` real del script inyectando el nombre que falta |
| Ejecución `--no-claude` | El comportamiento real de punta a punta (cazó `statistics`, sección 35) | Tarda diez minutos, consume paciencia de las fuentes públicas y no recorre la ruta de análisis con Claude, que solo se ejercita pagando |

De ahí que ninguna sustituya a las otras, y que las tres sean obligatorias al
cerrar una ronda. El punto 17 propone tapar el hueco más caro: lo único que hoy
solo detecta la ejecución real.

### 36.6. Otros, heredados de la evaluación externa

| # | Qué | Origen |
|---|---|---|
| 12 | `requires-python = ">=3.11"` no se ha probado sobre un intérprete 3.11 real | `SUGERENCIAS.MD` 3.9 |
| 13 | Limpieza de `Obsoleto/` y `Frontend alternativo/` ahora que hay historial de git | `SUGERENCIAS.MD` 3.10 punto 2 |
| 14 | Rotación de credenciales si `API KEYs.txt` estuvo en copias compartidas fuera de control | `SUGERENCIAS.MD` 3.1 punto 4; solo el usuario puede confirmarlo |
| 25 | `convocatorias.json` está en `.gitignore` pero **versionado en el remoto**: lo sube el propio pipeline por la API de Contents de GitHub, y `.gitignore` no afecta a lo ya rastreado. Consecuencia práctica: cada regeneración local aparece en `git status` y un `push` puede requerir `git rebase origin/main` primero | Sección 43.4. Es inherente a publicar desde la raíz para GitHub Pages; cambiarlo es decisión del usuario |
| 26 | Las «77 vigentes» dejaron de ser un invariante fijo: la ventana deslizante de BDNS mueve el recuento por causas externas (77 → 76 el 20/08). Conviene verificar con tolerancia y comprobación de causa, no con igualdad exacta | Secciones 40.3 y 40.4 |

### 36.6bis. Decisiones cerradas que no hay que reabrir

| Qué | Decisión |
|---|---|
| El TRL ausente en BDNS (42/50 análisis sin `trl_source`) | **No se persigue.** En Horizon, donde se anuncia de forma visible, se recoge; en BDNS, donde no se anuncia, no se recoge. Es una ausencia real de la fuente, no un fallo de extracción, y no tiene importancia para el uso de la herramienta (usuario, 31/08/2026; sección 53.3) |

### 36.7. Puntos ya cerrados

Se dejan anotados para que el hueco en la numeración no confunda al arrancar en
frío. No hay que buscarlos en las tablas de arriba: ya no están.

| # | Qué era | Cerrado en |
|---|---|---|
| 23 | Recalibrar `CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS` con datos de una ejecución completa, en vez de con la muestra de agosto | Sección 42.3: 76 análisis reales, barrera 0,035 → 0,047 USD |
| 18 | `coverage_watch.py` sin ninguna prueba: la alarma que avisa cuando un programa recurrente deja de aparecer era una red de seguridad sin red | Sección 46: 18 pruebas, incluidos los cinco estados de la sonda y la forma del catálogo real |
| 22 | La densidad del test de la ventana de BDNS (44 filas/día) era optimista y no habría detectado una caída por debajo del mínimo de 60 días | Sección 48.6: medición real de hoy (67 días, 52,2 filas/día) y el test fijado en la densidad más alta observada, 54 |
| 24 | Endurecer la instrucción contra presunciones en `objeto_y_actuaciones` | Sección 48.5: la frase prohíbe ahora la fórmula («se presume», «previsiblemente»…), no solo la invención. Agrupado con la caché ya invalidada, así que no costó nada |
| 31 | Una convocatoria publicaba como URL una frase entera con el esquema mal escrito | Sección 48.6: `_web_url_or_empty()` en el conector y en la publicación |
| 33 | `extraction_system` era una variable local que ninguna prueba podía mirar | Sección 48.3: constante de módulo `CLAUDE_EXTRACTION_SYSTEM_PROMPT` con siete pruebas de integridad |
| 35 | La elegibilidad de Horizon no estaba en el topic que leemos | Sección 50: el conector lee los Anexos Generales que el propio topic enlaza, una vez por edición, y envía tres extractos de 3.400 caracteres. Sin catálogo que mantener |
| 17 | Prueba de humo por conector | Sección 51.3: diez pruebas, 0,2 s, con la red y el navegador sustituidos. Una de ellas comprueba que el detector detecta, reproduciendo el `statistics` de la sección 35 |
| 36 | CDTI llegaba sin bases: 300 caracteres tecleados y cero documentos | Sección 51.2: las fichas del catálogo curado se leen con el navegador que ya las visitaba y traen sus documentos oficiales, con el mismo extractor que el calendario |
| 8 | La matriz de reglas previa a Claude, lo último del orden de extracción | Sección 57: extraída a `grant_radar/bdns_rules.py` en sesión dedicada, 774 líneas movidas y **el embudo idéntico dígito a dígito** (`ambiguous=7, hold_manual=75, reject=803, retain=34`). Resultó más limpia de lo temido —cero dependencias de globales del script, ningún módulo la importa— porque `holds.py` y ECCP la reciben inyectada, decisión tomada en su día justo para esto |
| 28 | ¿Mantener o retirar el catálogo estático de BOA? | Sección 56.1: **retirado el conector entero**, con la condición que puso el usuario comprobada antes: `paip_aragon` sale `active_captured` con 12 coincidencias y `sources=["BDNS"]`, y la caché documental trae el texto oficial del PAIP, 24 documentos de Transición Justa y 4 con Teruel. Verificado tras retirarlo: 82 vigentes, las mismas. El proyecto pasa de ocho fuentes a **siete** |
| 40 | El plural en `_term_present()` | Sección 59: aplicado **con guardia de siglas** (`PLURAL_MIN_LENGTH = 3`). La primera versión hizo casar `rto` con «RTOs» —que en Horizon son *Research and Technology Organisations*— y coló ocho convocatorias irrelevantes. Efecto final: 82 → 84 vigentes, ninguna sale. **Beneficio más modesto de lo estimado**: «calores residuales» no añade convocatorias, solo mejora la clasificación de las que ya entraban |
| 39 | La tasa de financiación de Horizon | Sección 59.5: leída de la sección G de los Anexos Generales. **La premisa de este punto era falsa**: no estaba en lo que ya descargábamos, sino en la página 32, más allá del corte de 48.000 caracteres. `max_chars` es ahora parámetro |
| 19 | `build_keywords()` sin ninguna prueba | Sección 59.4: nueve pruebas, y tenía un fallo —cuatro de sus siete colores estaban muertos—. El color se deriva ahora de la categoría técnica |
| 10 | Retirar el patrón `runpy` + fusión de `APP` | Sección 59.6: 81 de los 85 nombres ya eran importables; solo `run_pipeline` y `parse_args` obligan a mantener `runpy`. De 216 llamadas a `APP[...]` quedan 4 |
| 38 | `boletin.dpz.es` fallaba con `CERTIFICATE_VERIFY_FAILED`: era el único host que fallaba de toda la recopilación | Sección 60.7: **había una tercera vía que este punto no recogía**. El servidor envía un solo certificado, sin el intermedio; OpenSSL no lo verifica y Chromium sí, porque va a buscarlo. Medido con `ignore_https_errors` a **False** y a True: HTTP 200 en los dos casos, así que **no se relaja nada**. `VerifyingDocumentBrowser` arranca solo si algún documento falla y verifica el TLS a propósito |
| 11 | Cinco campos publicados que el frontend no consumía | Sección 60.9: entran `related_documents_count` y `bdns_url` en el detalle, porque ayudan a decidir y ya estaban en el JSON. Los otros tres son trazabilidad del pipeline y se quedan. De paso se retiró el «ID» posicional que el detalle enseñaba |
| 5 | Modo de verificación por fuente, para no recorrer las ocho cuando un cambio solo toca una | Sección 54.6: `--source`, con alias cortos. Medido contra los 937 s de una recopilación completa: `--source boa` 13,7 s (68×) y `--source een` 81,4 s (11×, sin arrancar Chromium). Exige `--no-claude` y apaga la vigilancia de recurrentes, que con fuentes sin consultar daría alarmas falsas seguras |

## 37. Decimotercera ronda a 19/08/2026: salida pública, publicación, selección y cobertura

Etapa 8 del plan de la sección 28, **reformulada tras medirla**. Ese plan la
definía como "extraer `pipeline.py`", pero antes de tocar nada se calculó el
cierre transitivo de `run_pipeline()`: arrastraría **64 de las 68 funciones**
que quedaban en el script, incluida toda la matriz de reglas. El orquestador es
por definición lo último que se mueve, cuando ya no queda nada que orquestar
dentro del propio archivo. Lo que sí tenía frontera limpia eran cuatro
dominios, y esos son los que se han extraído:

- `grant_radar/public_output.py` (461 líneas): el registro público que consume
  el dashboard (`_assemble_public_record()`), las estadísticas, el estado por
  fuente, las palabras clave, la verificación técnica de URLs, las acciones
  elegibles y `post_procesar_texto()` con su lista blanca de entidades. Es la
  frontera con `index.html`, y el test de contrato del frontend sigue
  ejerciéndola sin red ni Claude.
- `grant_radar/publishing.py` (82 líneas): `github_upload()` y
  `github_token_format_is_valid()`. **Las credenciales pasaron a ser
  parámetros**: el módulo ya no lee `GITHUB_TOKEN`, `GITHUB_USER`,
  `GITHUB_REPO` ni `GITHUB_BRANCH`, los recibe. El script principal sigue
  siendo el único que carga secretos desde `.env`, de modo que ningún módulo
  del paquete puede filtrarlos por error (sección 7).
- `grant_radar/claude_selection.py`: qué convocatorias necesitan análisis nuevo,
  la barrera presupuestaria previa (`claude_safety_preflight()`, con los
  límites autorizados de 200 análisis y 5 USD) y el inventario de candidatas
  que guarda `--no-claude`.
- `grant_radar/coverage_watch.py`: la vigilancia de programas recurrentes
  conocidos, con su catálogo.

**Un fallo propio, y la lección de método.** El primer intento de extraer
`public_output.py` rompió el script: se calculó el final de cada función con
`max(lineno)` de sus nodos, que en un `return (` multilínea se queda en la
última expresión y deja fuera el paréntesis de cierre. `py_compile` lo detectó
al instante y se restauró desde git sin más consecuencias. La forma correcta es
`node.end_lineno`, que es lo que se usa desde entonces. Anotado aquí porque el
mismo error volvería a aparecer en la extracción del dominio de reglas, que
está lleno de expresiones multilínea.

**Verificación:** `Grant-Radar-prueba.py` bajó de 5.018 a 4.286 líneas (-14,6 %
en esta ronda; **-53,4 % acumulado en el día** desde 9.199). El paquete son ya
31 módulos y 8.254 líneas: por primera vez hay casi el doble de código en
`grant_radar/` que en el script. 381 pruebas `unittest` (371 + 10) y
`py_compile` en verde. La ejecución `--no-claude` de cierre (544,66 s, código 0)
devolvió los números de referencia completos, **BOE incluido**: 953
convocatorias detectadas, 33 duplicadas fusionadas, 39 tras el prefiltro
inicial, 77 vigentes con el desglose habitual (BDNS 47, Horizon 19, CDTI 5,
ECCP 4, EEN 2, IDAE 1, BOE 1, BOA 0), mismo prefiltro común y misma previsión
de coste. Eso confirma además lo dicho en la sección 35: la desviación de BOE
de la ronda anterior fue el `HTTP 429` y nada más. Una sonda de una sola
petición, hecha antes de esta ronda, ya mostró la página accesible: el cooldown
fue de minutos.

**Lo que queda en el script, y en qué orden tiene sentido moverlo:**

| Dominio | ~Líneas | Bloqueo |
|---|---|---|
| Matriz de reglas previa a Claude | ~570 | Sesión dedicada (secciones 4.1, 24, 27) |
| Análisis con Haiku (`analyze_with_claude`, `_structured_claude_call`, `_build_compatible_analysis`) | ~545 | Depende de `_hard_out_of_scope()`, que es matriz de reglas; se podría inyectar como se hizo con ECCP |
| Dominio de holds BDNS (evidencia, resolución, piloto, replay) | ~1.000 | Independiente: es el siguiente candidato natural |
| Auditoría persistida (`save_discovery_audit`) | ~117 | Independiente, encaja en `grant_radar/audit.py` |
| `run_pipeline()` + `parse_args()` | ~840 | Último, por definición |

## 38. Decimocuarta ronda a 19/08/2026: primera mitad del dominio de holds

El dominio de holds de BDNS son ~1.171 líneas en 28 funciones, y el análisis
previo mostró que **no se puede mover entero**: depende de la matriz de reglas
(`_bdns_intrinsic_exclusion()`, `deterministic_prefilter()`) y de la capa de
análisis con Haiku (`_structured_claude_call()`). Se midió por subgrupos y se
extrajo la mitad que sí tiene frontera limpia.

- `grant_radar/hold_quotes.py` (~114 líneas, cero dependencias): la validación
  de que una cita **prueba** la conclusión y no solo aparece en el documento.
  Es la capa que distingue "el modelo dijo que sí" de "la fuente lo dice", y la
  que evita el falso rechazo que invalidó el piloto v1: aceptar una cita sobre
  el plazo de ejecución como prueba de cierre (sección 13).
- `grant_radar/claude_usage.py` (~96 líneas): el recuento de tokens y coste,
  incluidos los intentos fallidos, con las tarifas por millón de tokens. Cada
  respuesta HTTP se contabiliza antes de validar su JSON, porque un intento
  truncado ya se ha facturado.
- `grant_radar/hold_evidence.py` (~253 líneas): la descarga de documentos
  oficiales, su extracción de texto y la caché documental de BDNS.
  `retrieve_bdns_hold_evidence()` recibe ahora `intrinsic_exclusion` como
  parámetro, igual que ECCP recibe su prefiltro (sección 35): con los
  documentos completos delante conviene repetir el control de
  incompatibilidades intrínsecas, pero esa regla es de la matriz, así que el
  módulo la pide en vez de conocerla. Las tres llamadas del script la pasan
  explícitamente. La ruta de la caché se calcula en el módulo, como en
  `documents.py`, y se verificó que apunta al mismo archivo de siempre.

**Lo que se queda, y por qué:** la resolución determinista de holds
(`resolve_hold_deterministically()`, `_validated_hold_resolution()`,
`apply_verified_bdns_hold_resolution()`, ~305 líneas) necesita **dos** reglas de
la matriz, y su cometido es precisamente volver a ejecutarla cuando aparece un
hecho verificado. Inyectar la matriz entera en la función cuyo propósito es
aplicarla sería invertir la dependencia en la dirección equivocada: se mueve
con la sesión de reglas. Lo mismo el piloto y el replay, que llaman a
`_structured_claude_call()`.

**Verificación:** `Grant-Radar-prueba.py` bajó de 4.286 a 3.842 líneas (-10,4 %
en esta ronda; **-58,2 % acumulado en el día** desde 9.199) y ya solo tiene 33
funciones de las 68 con las que empezó la tarde. El paquete son 34 módulos y
8.847 líneas. 381 pruebas `unittest` y `py_compile` en verde. La ejecución
`--no-claude` de cierre (702,55 s, código 0) repitió todos los números de
referencia —953 detectadas, 33 duplicadas fusionadas, 77 vigentes con el
desglose habitual, BOE incluido— y, lo que importa en esta ronda, la
**resolución automática de holds dio exactamente lo mismo**: `ambiguous=38,
reject=35, revisión manual=0`. La regla inyectada se comporta igual que la
llamada directa.

Nota de método: por tercera vez, el análisis AST previo no vio dependencias que
eran nombres **importados** (`_fold_text`, `_parse_flexible_date`,
`select_evidence_excerpt`). Esa clase de fallo la detecta
`tests/test_grant_radar_script_names.py`, que conviene ejecutar **antes** que la
suite completa tras cada extracción: señala el módulo y el nombre exactos en un
segundo, mientras que la suite los presenta como errores en pruebas de otra
cosa.

## 39. Cierre de la sesión del 19/08/2026 y punto de partida para la siguiente

Resumen de una sola sesión con nueve rondas de extracción (secciones 28-38),
pensado para arrancar en frío sin releerlas.

> **Superada como punto de arranque por la sección 43** (cierre del 20/08/2026).
> Las cifras de referencia de 39.4 y 39.5 —77 vigentes, 381 pruebas, previsión de
> 2,04 USD— corresponden al estado de aquel día y **ya no valen para verificar**.
> El diagnóstico de 39.1-39.3 sí sigue vigente.

### 39.1. Qué cambió

| Métrica | Al empezar | Al cerrar |
|---|---|---|
| `Grant-Radar-prueba.py` | 9.199 líneas, 68 funciones | **3.842 líneas, 33 funciones** (-58,2 %) |
| Paquete `grant_radar/` | 12 módulos | **34 módulos, 8.847 líneas** |
| Pruebas `unittest` | 238 | **381**, todas en verde |
| Conectores fuera del script | 1 de 8 (BOA) | **8 de 8** |

El paquete tiene ya más del doble de código que el script. Lo que queda en
`Grant-Radar-prueba.py` es: credenciales y configuración, la matriz de reglas
previa a Claude, la capa de análisis con Haiku, la segunda mitad del dominio de
holds, `run_pipeline()` y `parse_args()`.

### 39.2. Tres fallos reales encontrados por el camino

Ninguno introducido por las extracciones; los tres estaban latentes y se
corrigieron:

1. **14 funciones de `deterministic_rules` sin reimportar** (sección 29). La
   siguiente ejecución con Claude habría fallado con `NameError` **después de
   pagar la primera llamada a Haiku**. Invisible para `py_compile` y para
   `--no-claude`, y tapado además por el bloque de fusión de `APP` de los tests.
2. **`title` inexistente en `fetch_idae_catalog()`** (sección 35), presente
   desde el commit inicial. No estalla porque el catálogo IDAE lleva tiempo sin
   aportar convocatorias; el día que aporte una, la fuente entera caería.
3. **Tres fallos en `_extract_funding_budget()`** (sección 31.1), que perdían
   el importe cuando la fuente escribía "2,5 millones **de** euros" o
   "Dotación" con tilde, y truncaban "euros" a "eur" en el dashboard.

De ahí nació `tests/test_grant_radar_script_names.py`, que ahora vigila que ni
el script ni ningún módulo llamen a nombres que no tienen.

### 39.3. Siguiente paso, ya medido

Por orden, con el motivo de cada posición (detalle en 36.3 y en la sección 38):

1. `save_discovery_audit()` (~117 líneas) → encaja en `grant_radar/audit.py`.
   Es el candidato más limpio que queda.
2. La capa de análisis con Haiku (~545 líneas: `_structured_claude_call()`,
   `analyze_with_claude()`, `_build_compatible_analysis()`). Depende de
   `_hard_out_of_scope()`, que es matriz de reglas; se puede inyectar como
   predicado, igual que se hizo con ECCP (sección 35) y con la evidencia de
   holds (sección 38).
3. La segunda mitad del dominio de holds: resolución determinista, piloto y
   replay. Necesitan reglas **y** Claude.
4. La matriz de reglas, en sesión dedicada. Es la lógica más ajustada del
   proyecto (siete niveles de precedencia, sección 4.1) y no debe encadenarse
   detrás de otra tarea.
5. `run_pipeline()` y `parse_args()`, al final por definición: hoy arrastrarían
   todo lo anterior.

### 39.4. Lo que está pendiente y no es refactor

**El producto lleva sin actualizarse desde el 14/08/2026.** `convocatorias.json`
es de esa fecha y la caché no contiene ninguna de las 77 convocatorias vigentes
actuales: la previsión es de **77 análisis nuevos, 154 llamadas y $2,04 de coste
central** ($1,39-$2,70), dentro de la barrera de $5. Una ejecución completa
refrescaría el dashboard.

Merece considerarse antes que seguir refactorizando, por dos razones: el valor
del refactor ya está asegurado y verificado nueve veces, y una ejecución
completa ejercitaría por primera vez la ruta de análisis con Claude, que es
justamente la única que ninguna de las tres redes de seguridad cubre (36.5) y
donde ya apareció uno de los tres fallos latentes.

**Requiere autorización expresa del usuario**, como cualquier llamada a la API.

### 39.5. Cómo verificar cualquier cambio, en orden

1. `poetry run python -m unittest tests.test_grant_radar_script_names` —un
   segundo, señala módulo y nombre exactos si falta un import.
2. `poetry run python -m py_compile "Grant-Radar-prueba.py"`.
3. `poetry run python -m unittest discover -s tests` —381 pruebas entonces,
   **405 desde el 20/08** (sección 43.3); el número solo puede subir.
4. `poetry run python "Grant-Radar-prueba.py" --no-claude` —diez minutos, sin
   coste. Los números de referencia estables, repetidos en nueve ejecuciones
   consecutivas:

   > 953 convocatorias detectadas · 33 duplicadas fusionadas · 39 tras el
   > prefiltro inicial · **77 vigentes** (BDNS 47, Horizon 19, CDTI 5, ECCP 4,
   > EEN 2, IDAE 1, BOE 1, BOA 0) · prefiltro común `retain=32, ambiguous=7,
   > hold_manual=73, reject=841` · resolución automática de holds
   > `ambiguous=38, reject=35, revisión manual=0` · previsión $2,0405.

   Si un número se desvía, comprobar primero el estado de salud de las fuentes:
   el 19/08 un `HTTP 429` de `boe.es` bajó BOE de 1 a 0 y las duplicadas de 33 a
   31, y no era una regresión (secciones 35 y 37).

## 40. Calidad del dato que entra y sale de Haiku, a 20/08/2026

Ronda previa a la primera ejecución completa de pago desde el 14/08. El objetivo
no era estructura sino **qué se le pasa al modelo y qué se le pide**, porque un
fallo de formato descubierto después obliga a subir versión y pagar dos veces
las 77 convocatorias.

### 40.1. Lo que mostraron los datos reales

Medido sobre las 49 convocatorias publicadas y las 102 entradas de caché:

- **Los 21 campos estructurados de BDNS no llegaban al modelo.** El pipeline
  extrae de SNPSAP tipos de beneficiario, CNAE, regiones, finalidad e
  instrumentos, los usa en la matriz de reglas y **no** los incluía en el
  prompt: se le preguntaba a Haiku quién puede solicitar cuando la respuesta
  oficial ya estaba en casa. `eligibility_unknown` aparecía en 27 de 49.
- **Las bases recuperadas perdían la mitad del texto.**
  `_attach_bdns_hold_evidence()` guarda 12.000 caracteres y el prompt los
  recortaba a 6.000.
- **Y además se ordenaban las últimas.** Esas bases llevaban `document_role`
  igual al `kind` de la API (`document`/`announcement`), valores que
  `related_role_rank` no reconoce: puntuaban 0 y competían por el corte de los
  cinco primeros contra documentos menos informativos.
- **`post_procesar_texto()` corrompía el resumen publicado.** Comparaba
  cualquier token de 4+ letras contra la lista blanca de entidades con
  distancia ≤ 2, así que reescribía prosa española corriente. En el JSON del
  14/08 estaban publicados `Plazo de CIRCE` (era *cierre*), `reference_IDAE`
  (era *date*), `fin de IDAE` (era *vida*) y, en INNOVAE, `verificación de que
  IDAE 2899 esté incluido en el anexo` (era *CNAE*). 18 menciones sospechosas
  en 49 registros.
- **El prompt no decía nada sobre `resumen`.** El campo existía en el esquema
  sin una sola instrucción sobre qué contener, de ahí que los resúmenes
  abrieran con fechas y puntuaciones en vez de con el objeto de la ayuda.
- **`eligible_actions` nunca se había producido.** Las 102 entradas de caché
  son del extractor `facts-2026-08-v5`; la v6 que introdujo el campo no llegó a
  ejecutarse nunca contra la API.

**Medido y descartado:** cachear el prompt no es viable. El perfil de Kalfrisa
(~690 tokens) más los prompts de sistema no alcanzan el mínimo cacheable.

**Corregido durante la ejecución del plan:** se había previsto bajar el límite
de 14.000 caracteres de la descripción por considerarlo inactivo, a partir de
la mediana (3.451). Al comprobar el máximo publicado —13.955— resultó que sí se
alcanza, y bajarlo habría recortado los topics largos de Horizon. Se mantuvo, y
el margen se dio solo a los documentos.

### 40.2. Cambios aplicados

| Área | Cambio |
|---|---|
| Corrupción | `post_procesar_texto()` solo corrige tokens escritos **en mayúsculas**, con umbral de distancia 1 para tokens cortos y 2 desde seis caracteres —sin eso `CNAE` seguía cayendo en `IDAE`— y una lista de acrónimos del dominio protegidos |
| Entrada | Bloque `<official_structured_data>` con 14 campos oficiales de SNPSAP, en extracción y evaluación, declarado en el prompt como evidencia de primer orden frente al `<source_document>` no confiable. Solo hechos de la fuente: las conclusiones del pipeline (`bdns_company_eligible`…) se excluyen para no difuminar la frontera entre evidencia y reglas |
| Entrada | Rol documental de las bases BDNS traducido al vocabulario que el ranking entiende (`regulatory_bases`/`call_extract`) |
| Entrada | Presupuesto de evidencia explícito: 10.000 caracteres por documento (antes 6.000) con tope total de 26.000 compartido, para que unas bases largas puedan usar más sin disparar el coste |
| Salida | Campo nuevo `objeto_y_actuaciones` en `CallEvaluation`, con instrucción de redactar qué financia la convocatoria, qué gastos cubre y qué excluye, desde la convocatoria y sin valoración de encaje. `resumen` recibe instrucción de no repetirlo |
| Salida | `max_tokens` de evaluación 2.200 → 3.000: el máximo observado (4.594 de 5.000 combinados) ya rozaba el techo y el campo nuevo alarga la respuesta |
| Frontend | Bloque destacado al inicio del resumen ejecutivo, más columna de exportación |
| Versiones | `facts-2026-08-v7-official-structured-data`, `fit-2026-08-v6-purpose-and-actions`, prompt `2026-08-v10`. Coste adicional cero: la caché ya era toda v5 |

### 40.3. Verificación: parcial, por una caída de red

400 pruebas `unittest` (381 + 19) y `py_compile` en verde. Entre las nuevas, las
que fijan los cinco daños reales de `post_procesar_texto()` con literales del
JSON publicado, y las que comprueban que los campos estructurados viajan al
prompt, que las conclusiones del pipeline no se cuelan como si fueran hechos de
la fuente, y que las bases conservan un rol que el ranking entiende.

**Primeros dos intentos, fallidos por una caída de red del equipo.**
Devolvieron 4 convocatorias en vez de 77, con todas las fuentes de red a cero y
solo el catálogo curado de CDTI sobreviviendo: `getaddrinfo failed` y
`ERR_NAME_NOT_RESOLVED` en todos los hosts. El sistema se comportó como debía —
marcó las cuatro fuentes con control de salud como `unhealthy` con
`inventory_unreachable`, no generó `convocatorias.json`, no tocó la caché de
análisis y terminó con código 0.

**Tercer intento, con red restablecida (20/08/2026, 724,51 s, código 0):**

| Métrica | Referencia 19/08 | Hoy 20/08 |
|---|---|---|
| Detectadas | 953 | 955 |
| Duplicadas fusionadas | 33 | 33 |
| Tras el prefiltro inicial | 39 | 39 |
| Prefiltro común | retain 32 · ambiguous 7 · hold 73 · reject 841 | retain 32 · ambiguous 7 · hold 72 · reject 844 |
| Resolución automática de holds | ambiguous 38 · reject 35 · revisión 0 | ambiguous 37 · reject 35 · revisión 0 |
| **Vigentes** | **77** | **76** |

**La única diferencia está explicada y no es una regresión.** Comparando los
inventarios de candidatas de ambas ejecuciones, la convocatoria que falta es
una sola: *Programa Pyme Cibersegura 2026* (BDNS 913401). No caducó —cierra el
31/10— ni fue excluida: no hay ningún registro de exclusión para ella. Es que
**no se detectó**, y la razón es la ventana deslizante de BDNS.

### 40.4. La ventana de BDNS se ha estrechado de 79 a 65 días

Medido contra la API el 20/08/2026, pidiendo la primera y la última página de
`convocatorias/ultimas`:

- Página 0: del 20/08 al 17/08. Página 34: del 17/06 al **16/06**.
- Ventana real: **65 días**, no los ~79 que documenta la sección 26.
- Densidad real: **54 filas/día**, no las 44 medidas el 17-18/08.
- Mínimo de negocio (60 días): **se cumple, con 5 días de margen**.

La convocatoria perdida tiene `fechaRecepcion` 2026-06-16, exactamente la fecha
más antigua que devuelve la última página: está en el borde y entra o sale
según el volumen publicado cada día.

Conviene saber que `tests/test_grant_radar.py::test_bdns_latest_window_covers_at_least_sixty_days`
ata la constante al mínimo de 60 días **usando la densidad de 44 filas/día**, de
modo que hoy es optimista: seguiría en verde aunque la ventana real bajara de
60. Queda anotado en la sección 36 como punto 22.

### 40.5. Estado

Los cambios de esta ronda están verificados: 400 pruebas, `py_compile` y una
ejecución real cuyo único desvío tiene causa externa identificada. Falta
todavía ver **lo que Haiku devuelve de verdad**, que es el objetivo de la
ronda y no puede comprobarse sin gastar: la prueba dirigida sobre tres
convocatorias (~$0,10) y, si convence, la ejecución completa (~$2,04). Ambas
requieren autorización expresa.

## 41. Prueba dirigida de pago a 20/08/2026: lo que la ronda de calidad produce

Tres convocatorias deliberadamente distintas, autorizadas expresamente:
**INNOVAE** (multilínea, con documentos BOE), **BDNS 918271 / PAIP Aragón**
(con bases recuperadas de un hold) y **HORIZON-CL5-2027-02-D3-07** (sin ningún
documento oficial).

### 41.1. Primer intento: abortó, y por eso valía la pena hacerlo

INNOVAE agotó los tres reintentos de extracción con
`Invalid JSON: EOF while parsing a string at line 1 column 9028`. Salida
truncada: la etapa de extracción tenía `max_tokens=2800` y la evidencia
enriquecida de esta ronda produce respuestas más largas —cuatro
`funding_lines` con sus importes, más `eligible_actions`—. Se subió el techo
de la evaluación (2.200 → 3.000) pero **no el de la extracción**, que es
justo la etapa que se había enriquecido.

Peor aún: con `temperature=0` los tres intentos fallaron **en la misma
columna**. Repetir una petición idéntica ante un JSON truncado no puede
funcionar, y costó $0,0896 para nada antes de abortar la ejecución.

Correcciones: extracción a `max_tokens=5000`, y cada reintento amplía el techo
un 60 % hasta un tope de 12.000. Ampliarlo no cuesta —Anthropic factura los
tokens generados, no el máximo autorizado— y convierte una truncación de fallo
fatal en recuperable. Cubierto por `StructuredCallRetryTests`, que simula
exactamente la respuesta truncada del caso real.

### 41.2. Segundo intento: los tres casos completos

`objeto_y_actuaciones` funciona, y con el nivel de detalle que se buscaba. Para
INNOVAE:

> INNOVAE financia subvenciones a proyectos singulares de mejora de eficiencia
> energética en industria, movilidad sostenible, edificios terciarios y
> sistemas de refrigeración. La línea industrial (presupuesto 30 M€, máximo
> 2 M€/proyecto) fomenta actuaciones de mejora tecnológica en procesos
> industriales que reduzcan consumo de energía final con ahorro mínimo del
> 20 %, coste elegible mínimo 100.000 €, plazo máximo 24 meses; excluye
> cogeneración y renovables sin ahorro de energía final.

Las cuatro líneas de INNOVAE se extraen por separado con sus importes, sin
mezclar sus requisitos.

**Los campos estructurados de BDNS llegan y se usan.** En PAIP Aragón,
`applicant_types` y `eligible_entity_types` recogen literalmente la categoría
oficial `PYME Y PERSONAS FÍSICAS QUE DESARROLLAN ACTIVIDAD ECONÓMICA` y
`eligible_geographies` queda como `ES24 - ARAGON`. Antes eran de los campos
más ausentes: `applicant_types` faltaba en 19 de 49 y `eligible_entity_types`
en 18.

**Los `data_gaps` bajan.** INNOVAE pasa de tres a uno (solo
`eligibility_unknown`); PAIP de tres a dos, resuelto el presupuesto. El
`eligibility_unknown` que queda es correcto y conservador: la categoría oficial
es «PYME», y Kalfrisa es mediana, así que la condición jurídica debe
verificarse en vez de presumirse.

**Una reserva sobre la redacción.** En los dos casos donde la fuente no
detalla los gastos, el modelo lo dice —«Gastos elegibles no detallados en
metadatos disponibles»—, pero en INNOVAE añade «se presume inversión en
equipos, instalación, ingeniería y validación». Es una presunción declarada,
no una invención encubierta, y el prompt pedía no inventar; aun así conviene
endurecer esa instrucción si vuelve a aparecer.

### 41.3. El coste real sube un 45 % sobre la calibración

| | Antes (extractor v5) | Ahora (v7) |
|---|---|---|
| Entrada media por convocatoria | 7.875 tokens | **15.278** |
| Salida media | 2.078 | 4.717 |
| Coste medio | $0,0265 | **$0,0389** |

La evidencia enriquecida casi duplica la entrada, que es exactamente lo que se
buscaba, pero encarece cada análisis. Para las 75 que faltan la proyección real
es **~$2,91**, no los $2,01 que muestra la previsión del pipeline, que sigue
usando la calibración de agosto.

La barrera de seguridad no bloquea —calcula 76 × $0,035 = $2,66 frente al
límite de $5,00— pero conviene saber que el margen es menor de lo que sugiere.
Recalibrar `CLAUDE_ESTIMATED_UPPER_USD_PER_ANALYSIS` con datos de la ejecución
completa queda anotado en la sección 36 como punto 23.

Gasto acumulado de las dos pruebas: **$0,0896 perdidos** en el primer intento y
**$0,1166** en análisis útiles (tres convocatorias completas).

## 42. Ejecución completa a 20/08/2026: resultado y recalibración

Primera ejecución completa desde el 14/08 y primera con la ronda de calidad del
dato (secciones 40 y 41). Autorizada expresamente; publicada en GitHub Pages.

### 42.1. Resultado

| | Valor |
|---|---|
| Convocatorias detectadas | 955 |
| Vigentes | 76 |
| Descartadas tras el análisis | 45 |
| Relevantes para Kalfrisa | 31 |
| Cierre urgente (<30 días) | 7 |
| Revisión manual requerida | 0 |
| Tokens | 1.095.295 |
| **Coste real** | **1,83 USD** |

### 42.2. El objetivo de la ronda, medido

Comparando el JSON publicado el 14/08 con el de hoy:

| | 14/08 (49 registros) | 20/08 (76 registros) |
|---|---|---|
| Con «datos pendientes» | 28 (57 %) | 29 (**38 %**) |
| `eligibility_unknown` | 27 (55 %) | 26 (34 %) |
| `budget_missing` | 17 (35 %) | 16 (21 %) |
| `consortium_requirement_missing` | 15 (31 %) | 20 (26 %) |
| Con `objeto_y_actuaciones` | 0 | **76 de 76** |
| Con `eligible_actions` | 0 | **71 de 76** |

Las tres causas de «datos pendientes» bajan en proporción, y los dos campos
que la ronda añadía se rellenan casi siempre. El `eligibility_unknown` que
queda es en su mayoría correcto: la categoría oficial de SNPSAP suele ser
«PYME», Kalfrisa es mediana, y la condición jurídica debe verificarse en vez de
presumirse.

### 42.3. Recalibración con datos reales

Los detalles están en la sección 11, que ya se ha reescrito. Lo esencial:

- La media apenas se movió: 0,0265 → **0,0256 USD** por convocatoria.
- La cola sí: el máximo observado es **0,0550 USD**, por encima del 0,035 que
  la barrera usaba como extremo superior.
- La barrera pasa a usar el percentil 95, **0,047 USD**, y su máximo efectivo
  baja de 142 a **106 convocatorias** por ejecución.
- La previsión del pipeline usa ahora la media observada y el rango p05-p95, en
  vez de tres constantes fijas de agosto.

**Corrección de un error propio.** Tras la prueba dirigida se avisó de que la
ejecución completa costaría ~2,91 USD y que la previsión de 2,01 se quedaba
corta un 45 %. Fue al revés: costó 1,83. La proyección se hizo con tres
convocatorias elegidas **por ser las más difíciles** —multilínea y con
documentos—, que no representan al conjunto. Queda anotado en la sección 11
como aviso metodológico: para calibrar hace falta una muestra representativa,
no una de casos extremos.

Con esto se cierra el punto 23 del backlog de la sección 36 (recalibrar la
barrera con datos reales). El punto 24 —endurecer la instrucción contra
presunciones en `objeto_y_actuaciones`— **sigue abierto**: la ejecución completa
no lo tocaba.

## 43. Cierre de la sesión del 20/08/2026 y punto de partida para la siguiente

**Esta es la sección de arranque en frío vigente.** Sustituye a la 39 como
punto de partida. El detalle de la sesión está en las secciones 40, 41 y 42;
esto es lo que hace falta para retomar sin releerlas.

### 43.1. Qué cambió

La sesión del 19/08 fue de estructura (nueve rondas de modularización). La del
20/08 fue de **calidad del dato y de producto**: qué se le pasa a Haiku, qué se
le pide, y una ejecución completa real.

| | Al empezar el 20/08 | Al cerrar |
|---|---|---|
| Producto publicado | JSON del 14/08, 49 convocatorias | **JSON del 20/08, 76 convocatorias** |
| Registros con «datos pendientes» | 57 % | **38 %** |
| `objeto_y_actuaciones` / `eligible_actions` | nunca producidos | **76/76** y **71/76** |
| Barrera de coste | 0,035 USD/análisis (muestra de 2) | **0,047 USD** (p95 de 76 reales) |
| Pruebas `unittest` | 381 | **405**, todas en verde |
| `Grant-Radar-prueba.py` | 3.842 líneas | 3.988 líneas |
| Paquete `grant_radar/` | 34 módulos, 8.847 líneas | 34 módulos, 8.901 líneas |

El script creció por primera vez en dos sesiones: la capa de análisis con Haiku
—que sigue dentro— es justo la que se enriqueció.

### 43.2. Estado del producto, ahora mismo

- El dashboard sirve datos del **20/08/2026**: 955 detectadas, 76 vigentes, 31
  relevantes para Kalfrisa, 7 con cierre urgente, 0 pendientes de revisión
  manual.
- La caché de análisis (`grant_radar_data/grant_radar_cache.json`) tiene
  **76 entradas, todas en `facts-2026-08-v7` / `fit-2026-08-v6`**, es decir en
  las versiones actuales de `grant_radar/versions.py`.
- **Consecuencia para el coste:** una ejecución completa hoy reutilizaría casi
  toda la caché y solo pagaría las convocatorias nuevas. Lo que hace cara una
  ejecución no es el tiempo transcurrido, sino **subir cualquiera de las
  versiones** de `versions.py`: eso invalida las 76 y vuelve a costar ~1,8 USD.
  Antes de tocarlas, decidirlo a conciencia.

### 43.3. Cómo verificar cualquier cambio, en orden

Sustituye a 39.5. **El orden sigue vigente; las cifras las actualiza 47.7**
(21/08/2026: 471 pruebas, 956 detectadas, 77 vigentes). Las cifras que aparecen
en los puntos de abajo son las del 20/08 y se conservan para no reescribir la
sección cada ronda: mandan siempre las de 47.7.

1. `poetry run python -m unittest tests.test_grant_radar_script_names` —un
   segundo, señala módulo y nombre exactos si falta un import. **Siempre el
   primero**: la suite completa presenta esos fallos como errores de pruebas de
   otra cosa (pasó tres veces).
2. `poetry run python -m py_compile "Grant-Radar-prueba.py"`.
3. `poetry run python -m unittest discover -s tests` —**405 pruebas**, el
   número solo puede subir.
4. `poetry run python "Grant-Radar-prueba.py" --no-claude` —unos 12 minutos,
   sin coste, sin autorización. Referencia del 20/08/2026:

   > 955 detectadas · 33 duplicadas fusionadas · 39 tras el prefiltro inicial ·
   > **76 vigentes** · prefiltro común `retain=32, ambiguous=7, hold_manual=72,
   > reject=844` · resolución automática de holds `ambiguous=37, reject=35,
   > revisión manual=0`.

**Cómo leer un desvío en el punto 4.** El recuento de vigentes ya no es un
invariante fijo: la ventana deslizante de BDNS lo mueve por causas externas
(77 → 76 entre el 19 y el 20/08, por una sola convocatoria en el borde de la
ventana; sección 40.3). Ante una diferencia, comprobar en este orden:
salud de las fuentes (un `HTTP 429` de `boe.es` ya bajó BOE de 1 a 0 sin ser
regresión), registros de exclusión de la convocatoria concreta, y solo después
sospechar del código. Anotado como punto 26 de la sección 36.

### 43.4. Lo que hay que saber del repositorio

`convocatorias.json` está listado en `.gitignore` **y a la vez versionado en el
remoto**: lo publica el propio pipeline por la API de Contents de GitHub, que es
como GitHub Pages lo sirve, y `.gitignore` no afecta a un archivo ya rastreado.

Dos consecuencias prácticas, ambas vistas el 20/08:

1. Tras una ejecución completa, `convocatorias.json` aparece modificado en
   `git status` aunque nadie lo haya tocado a mano.
2. El pipeline crea commits propios en `origin/main` («actualización
   automática»). Un `push` posterior puede ser rechazado; se resuelve con
   `git rebase origin/main` y volver a empujar, no con `--force`.

Anotado como punto 25 de la sección 36. Cambiar el mecanismo de publicación es
decisión del usuario, no una corrección pendiente.

### 43.5. Siguiente paso, por orden de valor

1. **Punto 24 del backlog** (el único que dejó abierto esta sesión): endurecer
   la instrucción del prompt contra presunciones en `objeto_y_actuaciones`.
   INNOVAE devolvió «se presume inversión en equipos…» donde la fuente no
   detalla gastos. Barato en código, pero **subir el prompt invalida la caché**:
   conviene agruparlo con cualquier otro cambio de prompt y pagar una sola vez.
2. **Punto 22**: la ventana de BDNS bajó de 79 a 65 días y el test de regresión
   la ata con una densidad optimista (44 filas/día frente a las 54 reales), así
   que hoy no detectaría una caída por debajo del mínimo de 60. Sin coste.
3. **Seguir modulando**, en el orden ya medido de 39.3, que sigue vigente:
   `save_discovery_audit()` → capa de análisis con Haiku → segunda mitad de
   holds → matriz de reglas (sesión dedicada) → `run_pipeline()`.
4. **Huecos de cobertura** de 36.4: `coverage_watch.py` sigue sin una sola
   prueba, y es la red que avisa cuando un programa recurrente deja de
   aparecer.

### 43.6. Medido y descartado: no volver a intentarlo

- **Cachear el prompt de Anthropic** no es viable: el perfil de Kalfrisa
  (~690 tokens) más los prompts de sistema no alcanzan el mínimo cacheable.
- **Reintentar sin cambiar nada ante un JSON truncado**: con `temperature=0`
  los tres intentos fallan en la misma columna. Costó 0,0896 USD comprobarlo
  (sección 41.1). Por eso cada reintento amplía ahora el techo de tokens.
- **Calibrar con una muestra de casos difíciles**: la proyección de ~2,91 USD
  para la ejecución completa salió de tres convocatorias elegidas por ser las
  más duras. El coste real fue 1,83. Para calibrar hace falta una muestra
  representativa (sección 42.3).

## 44. URLs muertas en CDTI y el embudo del IDAE, a 21/08/2026

Dos avisos del usuario sobre el producto publicado, no sobre el código: fichas
de CDTI que llevan a una página vacía, y un IDAE que apenas aporta una
convocatoria. Los dos resultaron ser fallos reales, y ninguno de los tres
mecanismos de verificación existentes podía haberlos visto.

### 44.1. CDTI: seis de diez URLs del catálogo curado eran 404

El usuario señaló tres. Al comprobar las diez del catálogo con el navegador
aparecieron **seis**:

| Ficha del catálogo | Ruta que tenía | Estado |
|---|---|---|
| Cervera (ventanilla abierta) | `/ayudas/proyectos-cervera` | 404 |
| Infraestructuras de Ensayo (LIEE) | `/ayudas/infraestructuras-ensayo-experimentacion` | 404 |
| Neotec 2026 | `/ayudas/neotec-2026` | 404 |
| Proyectos Bilaterales 13ª | `/ayudas/proyectos-bilaterales` | 404 |
| Sello de Excelencia + FEDER | `/ayudas/sello-de-excelencia` | 404 |
| CIIP Eurostars CoD10 | `/ayudas/eurostars` | 404 |
| Cervera Centros 2026 | `/ayudas/proyectos-cervera` | 404 (compartía ruta con la anterior) |

Las rutas correctas estaban **en el propio calendario oficial que el conector
ya recorre en cada ejecución**: `linea-de-ayudas-infraestructuras-de-ensayo-y-experimentacion`,
`proyectos-de-id-de-transferencia-tecnologica-cervera-0`, `ayudas-neotec-2026`,
`ayudas-pymes-sello-de-excelencia-2026`, `eurostars-3-2026-cod10` y
`ayudas-cervera-para-centros-tecnologicos-2026`. Las de Bilaterales no tienen
ficha propia bajo `/ayudas/`: su destino oficial es
`/programas-de-cooperacion-tecnologica-internacional-pcti`.

El catálogo declaraba «URLs facilitadas directamente desde la web del CDTI» y
«última revisión 2026-04-10». Se teclearon a mano hace cuatro meses y caducaron
en silencio.

### 44.2. Por qué `verificar_urls()` no podía detectarlo

`cdti.es` está tras un WAF (Incapsula) que **responde 200 a cualquier ruta**
cuando quien pregunta no parece un navegador. Comprobado con el cliente HTTP
del propio pipeline:

```
HEAD 200  https://www.cdti.es/ayudas/proyectos-bilaterales        (404 real)
HEAD 200  https://www.cdti.es/ayudas/eurostars                    (404 real)
HEAD 200  https://www.cdti.es/ayudas/proyectos-de-i-d             (válida)
HEAD 200  https://www.cdti.es/ayudas/esto-no-existe-jamas-12345   (inventada)
```

Una ruta inventada sobre la marcha respondía «correcta». `verificar_urls()`
comprueba `status_code < 400`, así que marcaba `url_rota=False` para las seis.
No era un fallo de la función: era que **el código HTTP no es informativo en
ese host**, y la función no tenía forma de saberlo.

Con Chromium sí se distingue: el WAF deja pasar al navegador y el origen
responde 404 de verdad. Esa es la asimetría que explica todo el episodio.

### 44.3. Qué se ha cambiado

1. **Las siete URLs, corregidas** contra el calendario y el listado oficiales,
   y las once del catálogo verificadas una a una con el navegador.
2. **`PlaywrightBrowser.status(url)`**: devuelve el código HTTP o `None`.
   Existe porque `html()` devuelve `""` tanto ante un 404 como ante un bloqueo
   o un fallo de red, y quien verifica un catálogo necesita distinguirlos.
3. **`_drop_catalog_entries_with_dead_urls()`** en el conector CDTI: en cada
   ejecución aparta las fichas del catálogo curado cuya URL dé **404 o 410**,
   con registro de exclusión. Cualquier otro resultado —bloqueo, 5xx, red
   caída— deja la entrada en su sitio: un catálogo curado no debe vaciarse
   porque el servidor tenga un mal día.
4. **Sonda de control por host en `verificar_urls()`**: antes de creerse ningún
   resultado, pide una ruta imposible
   (`/grant-radar-control-de-url-inexistente-9f3c2a7b`). Si el host la da por
   buena, sus códigos no distinguen rutas y la ejecución lo dice en el
   diagnóstico (`url_verification.opaque_hosts`) en vez de informar de que todo
   está correcto. Un fallo real sigue contando: un host permisivo puede tapar
   una URL rota, pero nunca inventa un error.

La verificabilidad **no se publica** en `convocatorias.json`: es metadato de la
comprobación, no del registro, y el esquema público solo debe crecer con lo que
el dashboard consume (sección 5).

De paso, `verificar_urls()` pasa a usar el mismo `HTTP_USER_AGENT` que el resto
del pipeline. Se identificaba aparte como «GrantRadar-Bot/1.0» sin motivo, y una
sola identidad frente a las webs públicas es más fácil de explicar si alguna
pregunta quién la está consultando.

### 44.4. IDAE: el inventario estaba sano; el prefiltro no

El IDAE publicaba una sola convocatoria. El embudo real, medido ejecutando el
conector:

| Etapa | Cuántas |
|---|---|
| Fichas en el inventario | 97 |
| En sección «convocatorias cerradas» | 26 |
| Fichas de detalle cargadas | 71 de 71 (**100 %**) |
| **Rechazadas por `is_relevant()`** | **68** |
| Con plazo ya vencido | 2 |
| **Publicadas** | **1** (Programa INNOVAE) |

No fallaba la navegación ni la extracción de fechas: fallaba el prefiltro
temático. Entre las 68 rechazadas estaban «**Para eficiencia energética en la
industria**», «**Ayudas para actuaciones de eficiencia energética en PYME y
gran empresa del sector industrial (2026)**» y su convocatoria autonómica
equivalente — es decir, exactamente el perfil de Kalfrisa.

**La causa.** `is_relevant()` acepta una mención genérica a eficiencia
energética solo si hay contexto industrial cerca, que es correcto. Pero el
vocabulario de contexto (`industrial_context_terms`) nombraba el **proceso**
—«procesos industriales», «horno», «fabricación», «siderurgia»— y no el
**sector**: no contenía «industria» ni «industrial» en ninguna forma suelta.
Una convocatoria dirigida literalmente a la industria no tenía cómo pasar.

### 44.5. La corrección, y por qué la conservadora

Se midieron dos vocabularios sobre las 68 fichas reales rechazadas:

| Variante | Términos añadidos | Recupera |
|---|---|---|
| Amplia | `industria`, `industrial`, `industriales`, `industry`… | 12 de 68 |
| **Conservadora (elegida)** | `sector industrial`, `la industria`, `empresa industrial`, `empresas industriales`, `industrial sector` | **9 de 68** |

La amplia solo añadía tres casos marginales (RENOVAL 2, Hy2Move, una línea
FEDER de renovables) y a cambio metía la palabra suelta «industrial» en
`INDUSTRIAL_CONTEXT_TERMS`, que **también alimenta la matriz de reglas previa a
Claude** (`Grant-Radar-prueba.py`, señal `industrial`) y por tanto el coste. La
conservadora recupera las tres convocatorias de eficiencia energética
industrial, más H2 Pioneros e IPCEI Hy2/Hy2Use, tocando mucho menos.

Medido aparte, sobre Horizon Europe en vivo: de sus 30 convocatorias vigentes
de hoy, **ninguna depende de los términos nuevos**. El cambio es tan estrecho
como se pretendía.

Disciplina seguida (`SUGERENCIAS.MD` 3.3): primero los casos de prueba con los
títulos textuales del IDAE —que fallaron—, después el vocabulario. Se añadió
también la prueba en negativo: eficiencia energética en viviendas, en
rehabilitación de edificios del sector terciario y en explotaciones
agropecuarias sigue rechazándose.

### 44.6. Lo que la corrección del IDAE consigue, y lo que no

Medido en una ejecución `--no-claude` completa del 21/08/2026:

| Desenlace de las 97 fichas | Antes | Después |
|---|---|---|
| Rechazadas por `is_relevant()` | 68 | **59** |
| Landings de programa sin plazo | 0 | 6 |
| Con plazo ya vencido | 2 | 4 |
| Página informativa | 0 | 1 |
| **Publicadas como convocatoria** | **1** | **1** |

**El recuento publicado no sube, y es correcto que no suba.** Las nueve
recuperadas no son convocatorias abiertas:

- «Para eficiencia energética en la industria» es una **página de sección**.
- «Ayudas para actuaciones de eficiencia energética en PYME y gran empresa del
  sector industrial» es un programa de **concesión directa a las CCAA**: el
  IDAE reparte el dinero entre comunidades autónomas y son ellas las que
  convocan. La página no tiene plazo de solicitud porque no se solicita ahí.
- «…Convocatorias en las Comunidades Autónomas» es el **registro histórico** de
  esas convocatorias. Comprobado: las de Aragón son la Orden ICD/119/2021 y sus
  modificaciones de 2022 y 2024. Ninguna abierta hoy, así que **no se está
  escapando dinero por ahí**.
- Cuatro más (MOVES Corredores, IPCEI Hy2Use, renovables térmicas, concesión
  directa CCAA) tienen plazos vencidos en 2020, 2024 y febrero de 2026.

El conector se niega deliberadamente a inventar un plazo para una landing de
programa y la conserva como identidad para consolidar con BDNS/BOE. Esa
decisión estaba bien tomada; lo que estaba mal era no llegar siquiera a
plantearla, porque el prefiltro temático descartaba la ficha antes.

**Lo que sí se gana**, aunque no se vea en el recuento:

1. Las landings de identidad pasan de 29 a **30**, y son las que permiten
   fusionar un registro del IDAE con su convocatoria real en BDNS.
2. Cualquier convocatoria futura del IDAE que **sí** tenga plazo y hable de
   «sector industrial» ya no caerá en silencio.

**Por qué el IDAE aporta poco, en una frase:** porque en eficiencia energética
industrial el IDAE casi no convoca, reparte. Las convocatorias reales las
publican las comunidades autónomas y llegan por BDNS, que es donde el pipeline
sí las ve —de las 77 candidatas de hoy, la de Aragón es la BDNS 918271—.

### 44.7. Estado y cifras de referencia a 21/08/2026

Ejecución `--no-claude` completa, 774 s, código 0:

> 956 detectadas · 34 duplicadas fusionadas · 39 tras el prefiltro inicial ·
> **77 vigentes** (BDNS 47, Horizon 19, CDTI 5, ECCP 4, EEN 2, IDAE 1, BOE 1,
> BOA 0) · prefiltro común `retain=32, ambiguous=7, hold_manual=75, reject=842`
> · resolución automática de holds `ambiguous=38, reject=37, revisión manual=0`
> · previsión 8 análisis nuevos, 0,2048 USD.

La previsión es baja porque la caché conserva las 76 entradas de la ejecución
del 20/08 en las versiones vigentes: solo 8 convocatorias son nuevas o han
cambiado.

Las cuatro fuentes con control de salud siguen `healthy`. Dos avisos externos,
ninguno regresión: `boletin.dpz.es` presenta un certificado TLS que no valida
(dos documentos no descargados) y el catálogo agregado del IDAE no aporta nada
(6 cerradas, 3 antiguas sin plazo).

Pruebas: **420**, todas en verde (405 + 15 nuevas: 7 del control de URLs del
catálogo CDTI, 6 de la sonda por host y 2 de la taxonomía).

**Una prueba intermitente, no introducida por esta ronda.**
`FrontendLayoutTests::test_consortium_role_is_visible_on_the_card_without_opening_it`
falló una vez de tres pasadas y pasó sola y en las otras dos. Conduce un Chromium
real contra `index.html` servido en local y espera con `networkidle`, así que es
sensible a la carga de la máquina; falló justo con una recopilación recién
terminada y varios Chromium en marcha. Nada de esta ronda toca `index.html` ni esa
ruta. **Si vuelve a fallar, repetir la suite antes de investigar**; si falla dos
veces seguidas con la máquina en reposo, entonces sí es real y conviene sustituir
`is_visible()` por una espera explícita.

## 45. El indicador de embudo y el hueco industrial del BOE, a 21/08/2026

Continuación directa de la sección 44. Allí se arreglaron dos fallos concretos;
aquí se ataca **por qué ninguno se detectó solo**, que es lo que se repetiría.

### 45.1. Un indicador que hubo que apagar para que no molestara

El control de salud por fuente tenía los datos delante. De la ejecución del
21/08:

| Fuente | Inventario | Detalle | `date_coverage` | Veredicto |
|---|---|---|---|---|
| ECCP | 227 | 227/227 | 100 % | healthy |
| CDTI | 14 | 14/14 | 100 % | healthy |
| **IDAE** | 97 | 71/71 | **6,2 %** | **healthy** |
| **BOE / MITECO** | 168 | **8/168** | **1,8 %** | **healthy** |

Las dos fuentes con el embudo hundido eran justo las dos con el umbral apagado:
CDTI y ECCP declaraban `expected_date_coverage=0.8`, el IDAE **no lo pasaba**
—se quedaba en el 0.0 por defecto— y el BOE lo fijaba en `0.0` con este
comentario:

> *«La cobertura de fecha se mide sobre el inventario completo en el helper
> común; por ello no se fija umbral: solo algunas entradas del BOE son
> convocatorias con plazo y se visitan tras el prefiltro.»*

Es decir: **la métrica tenía el denominador equivocado**. Contaba fechas
encontradas contra el inventario entero, incluidas las fichas que nadie llega a
abrir, así que daba cifras absurdas y la única salida fue silenciarla. Un
indicador que hay que apagar para que no moleste no es un indicador.

Ahora cada tasa se mide contra su propio denominador:

| Tasa | Fórmula | Pregunta que responde |
|---|---|---|
| `selection_rate` | `detail_attempted / discovered_count` | ¿cuánto del inventario merece abrirse? |
| `detail_load_rate` | `detail_loaded / detail_attempted` | ¿carga lo que se abre? |
| `date_coverage` | `dated_count / detail_loaded` | ¿tienen plazo las que se abren? |
| `publication_rate` | `published_count / detail_loaded` | ¿cuánto acaba publicándose? |

Con el denominador correcto, el BOE pasa del 1,8 % al **37,5 %** de cobertura
de fecha, que sí describe a esa fuente, y su umbral puede encenderse en 0,20.

**Y una limitación que conviene decir en voz alta:** ningún umbral absoluto
habría cazado el caso del IDAE. Convertir 71 fichas en 1 convocatoria era a la
vez el síntoma del fallo **y su estado normal** —es una fuente de landings de
programa—, así que cualquier umbral o bien no salta nunca o salta siempre. Lo
único que delata ese tipo de avería es el **cambio**. Por eso se añade
`compare_funnels()`, que compara cada etapa con la ejecución anterior guardada
en la auditoría —que conserva 365— y avisa de caídas superiores al 40 % sobre
etapas de al menos 8 elementos, para no confundir ruido con señal.

### 45.2. El BOE: la taxonomía técnica no admitía a nadie

Auditando el embudo del BOE con el mismo método que el del IDAE apareció algo
que no esperaba. Replicando su puerta de listado regla a regla sobre las 168
entradas reales:

| Regla que admite | Entradas |
|---|---|
| Taxonomía técnica (`is_relevant`) | **0** |
| Señal de descubrimiento | **0** |
| Autoridad vigilada (IDAE, MITECO, Fundación Biodiversidad) | **8** |

**Las ocho que se abren entran por autoridad; la taxonomía no aporta ni una.**
Y tiene su lógica: el listado del BOE son citas legales —«Extracto de la Orden
… por la que se convocan las subvenciones dispuestas en el Real Decreto
309/2022»— sin una sola palabra sobre la materia. Un vocabulario técnico no
puede funcionar ahí, y el conector ya lo sabía: por eso tenía la excepción por
organismo.

El problema es que esa lista **no incluía la parte industrial**. Contando sobre
el listado real, con palabra de ayuda presente:

| Organismo | Entradas | Decisión |
|---|---|---|
| Ministerio de Industria y Turismo | 5 | **añadido** |
| Sociedad Estatal de Promoción Industrial (SEPIDES) | 2 | **añadido** |
| Ciencia, Innovación y Universidades | 17 | **fuera** |

Entre las que se perdían: las ayudas a **Agrupaciones Empresariales
Innovadoras**, dos convocatorias de SEPIDES y la Orden ITU/498/2026 que modifica
las bases de varios programas. Ciencia e Innovación queda deliberadamente fuera:
sus 17 entradas de ese día eran institutos de salud, universidades y FECYT, y la
parte que sí interesa de ese ministerio es el CDTI, que tiene conector propio.

Son 7 fichas más que abrir, no 7 convocatorias más que publicar: la relevancia
de verdad la sigue decidiendo después el texto completo del documento.

### 45.3. Qué se ha cambiado

1. **`assess_web_inventory_health()` mide el embudo entero**, cada tasa contra
   su denominador (tabla de 45.1), y acepta `published_count`. Umbrales nuevos
   opcionales: `expected_selection_rate` y `expected_publication_rate`. Un
   umbral en 0 sigue significando «no lo compruebes».
2. **Umbrales encendidos donde estaban apagados**: el IDAE declara
   `expected_selection_rate=0.40` (medido: 0,73) y el BOE recupera su
   `expected_date_coverage`, ahora en 0,20 (medido: 0,27). CDTI y ECCP reportan
   además `published_count`.
3. **`compare_funnels()` y `previous_source_health()`**: comparación de cada
   etapa contra la ejecución anterior, con el resultado impreso en el resumen de
   recopilación y guardado en `RUN_DIAGNOSTICS["source_funnel_regressions"]`. Es
   la única forma de cazar una avería cuyo síntoma coincide con el estado normal.
4. **`BOE_TRACKED_AUTHORITIES`**: la lista de organismos pasa a ser una
   constante con nombre —antes estaba incrustada en la condición— y suma
   Industria y Turismo y SEPIDES. `is_miteco_aid` se renombra a
   `is_tracked_authority_aid`, que es lo que de verdad comprueba.

### 45.4. Resultado medido

Ejecución `--no-claude` completa del 21/08/2026, código 0:

| | Antes | Después |
|---|---|---|
| BOE: fichas abiertas | 8 de 168 | **15 de 168** |
| BOE: aceptadas por el conector | 2 | **3** |
| BOE: `date_coverage` | 1,8 % (denominador malo) | **26,7 %** |
| Total vigentes | 77 | 77 |
| Previsión de coste | 0,2048 USD | 0,2048 USD |

**Ninguna convocatoria publicada nueva, y conviene decirlo así.** La tercera que
acepta el BOE es la Orden ITU/498/2026, que modifica bases reguladoras: no tiene
plazo propio, así que entra como documento regulatorio para consolidar, no como
convocatoria. Las de SEPIDES y las Agrupaciones Empresariales Innovadoras **sí
se abren ahora**, se juzgan por el texto completo del documento y se rechazan
ahí, dejando registro en la auditoría (`boe_detail_filter`). Antes desaparecían
en el listado sin dejar rastro de ninguna clase.

Es decir: lo que se gana no es cobertura hoy, es que la decisión pasa de «nunca
se miró» a «se miró y se decidió, y consta». Si mañana el Ministerio de
Industria convoca algo que encaje, ya no se pierde.

Salud tras el cambio, con las tasas nuevas:

| Fuente | selección | carga | fecha | publicación |
|---|---|---|---|---|
| ECCP | 1,00 | 1,00 | 1,00 | 6/227 |
| CDTI | 1,00 | 1,00 | 1,00 | 1/14 |
| IDAE | 0,73 | 1,00 | 0,08 | 1/71 |
| BOE / MITECO | 0,09 | 1,00 | 0,27 | 3/15 |

Las cuatro `healthy`, sin regresiones de embudo frente a la ejecución anterior
—que es lo esperable cuando nada se ha roto—. La primera vez que una de estas
columnas se hunda, ahora se dirá.

Pruebas: **430**, todas en verde (420 + 10: 5 de las tasas nuevas y 5 de la
lista de organismos del BOE).

## 46. Publicación del 21/08/2026 y la alarma de recurrencia, ya con pruebas

Cierre de la sesión: las dos rondas anteriores llegan al producto, y se tapa el
hueco de cobertura más incoherente que quedaba.

### 46.1. Por qué hacía falta publicar

Al valorar el estado apareció algo incómodo: **las secciones 44 y 45 no habían
cambiado nada de lo que el usuario ve**. El dashboard seguía sirviendo el JSON
del 20/08 a las 11:40 UTC, **con las tres URLs rotas que él mismo había
reportado**. Las correcciones existían solo en git.

Es el patrón a vigilar: el pipeline no publica solo, así que cada mejora se
queda en el repositorio hasta que alguien autoriza una ejecución de pago. Con la
caché al día ese paso era casi gratis y no se había dado.

### 46.2. La ejecución

Autorizada expresamente. 956 detectadas, **77 vigentes**, 46 descartadas tras el
análisis, 31 relevantes, 7 con cierre urgente, 0 de revisión manual.

| | Previsión | Real |
|---|---|---|
| Análisis nuevos o cambiados | 8 | 8 |
| Coste | 0,2048 USD | **0,2000 USD** |

**La recalibración de la sección 42 se valida sola**: 0,2 % de desviación, frente
al 45 % con que falló la proyección hecha con la muestra de casos difíciles. 120.223
tokens.

Las tres URLs de CDTI que motivaron todo salen ya correctas en
`convocatorias.json`: `proyectos-de-id-de-transferencia-tecnologica-cervera-0`,
`linea-de-ayudas-infraestructuras-de-ensayo-y-experimentacion` y
`programas-de-cooperacion-tecnologica-internacional-pcti`.

### 46.3. La sonda de hosts opacos: no era solo CDTI

Primera ejecución completa con el control de la sección 44.3, y resulta que el
problema era más común de lo que sugería el caso que lo destapó. **Nueve hosts
responden 200 a una ruta inexistente**, afectando a 13 URLs publicadas:

> `convocatoria.fecyt.es`, `convocatoriamariadeguzman.fecyt.es`,
> `gestion.convocatoriaip.fecyt.es`, `gestion.estanciasip.fecyt.es`,
> `sede.carm.es`, `sede.institutofomentomurcia.es`, `www.cdti.es`,
> `www.gov.pl`, `www.manresa.cat`

Sedes electrónicas y portales de fundaciones públicas, sobre todo. En esas 13,
`url_rota=False` **no prueba que la ficha exista**; antes se afirmaba que
estaban bien sin base ninguna.

Y apareció un fallo de extracción que nadie había visto: una convocatoria
publica como URL una **frase entera con el esquema mal escrito** —
`hhtp://www.aragon.es/tramites), incluyendo en el buscador de trámites el
procedimiento número 11810 “Ayudas para actuaciones en materia de certámenes
feriales en Aragón”`. Queda como punto 31 del backlog.

### 46.4. `coverage_watch.py`, con 18 pruebas

Era el punto 18 del backlog y el hueco más incoherente del proyecto: el
mecanismo que avisa cuando un programa recurrente conocido deja de aparecer
—la red que vigila que no se pierda nada— no tenía **ni una** prueba.

Lo que ahora queda cubierto, con la distinción que de verdad importa:

| Estado | Qué significa |
|---|---|
| `active_captured` | una fuente produjo la convocatoria |
| `landing_only` | solo se vio su página de programa |
| `closed_observed` | la landing dice que está cerrada: **no es regresión** |
| `seasonal_pending` | programa anual, aún no toca: **no es regresión** |
| `republication_not_observed` | anual, ya pasó su mes y no ha salido |
| **`active_not_captured`** | **está abierta en su landing y no la hemos encontrado** |

El último es el único que significa «hay una avería», y ahora tiene prueba
propia. También se cubre que la sonda **no** se lance para programas ya
capturados —es un recurso de última hora, no una comprobación rutinaria— y que
una landing inalcanzable deje la alarma intacta en vez de concluir nada.

Una prueba propia se escribió mal al principio: daba por hecho que una tilde
separaba un alias de su título. `_fold_text` normaliza los dos lados, así que no
lo hace —y menos mal, porque los alias reales mezclan «Aragón» y «Aragon»—. La
aserción estaba equivocada, no el código; se corrigió en el sentido contrario.

Pruebas: **448**, todas en verde (430 + 18).


## 47. Un falso negativo del evaluador y el informe de desfase, a 21/08/2026

Dos encargos del usuario. El primero, un caso concreto de mala puntuación; el
segundo, una idea suya para vigilar cuánto envejece la información sin pagar por
ello.

### 47.1. PowerUp NetZero: 35 % de encaje en una convocatoria a la que la empresa se presenta

El usuario avisó de que **PowerUp NetZero Open Call for Innovation Projects**
recibía un `fit_score` de 35 y salía como descartada, siendo una convocatoria a
la que Kalfrisa va a concurrir, y apuntó a sus líneas de I+D en consorcio sobre
validación de simulaciones y gemelos digitales.

**Causa principal: el evaluador ignoró un dato que su propia extracción había
recuperado.** La etapa factual leyó el documento oficial de Piemonte Innova y
capturó los ocho temas admisibles:

> Waste management of solar panels and batteries · Materials and critical raw
> materials · Storage alternatives to batteries · **Digital solutions for
> PowerUp NetZero NZT** · **Value chain efficiency** · **CO2 and hydrogen
> coupling** · **Carbon capture technologies** · City of Turin Challenges

Y la evaluación escribió que «las capacidades de Kalfrisa […] no figuran en los
temas obligatorios listados». Es falso, y lo desmiente un campo que viajaba en
su propio payload: `evaluation_payload["facts"]` incluye `required_topics`.
Comprobado. Razonó solo sobre los **cinco titulares** del programa —Solar,
Baterías, Hidrógeno, Biogás, CCS— que aparecen en la descripción de portada.

Causas concurrentes, todas verificadas:

| # | Causa | Evidencia |
|---|---|---|
| 1 | El prompt tenía regla para `funding_lines` («basta la mejor línea») pero **ninguna para `required_topics`** | El modelo trató la lista como conjunción que satisfacer entera |
| 2 | La cláusula «FUERA DE FOCO» del perfil excluye «hidrógeno genérico sin uso térmico industrial», y el paraguas del programa es exactamente eso | El modelo cruzó portada con exclusión y paró antes de bajar al tema concreto |
| 3 | El perfil mencionaba gemelos digitales **dentro** de la frase «vinculados a equipos y procesos térmicos» | Se leía como capacidad subordinada, no como línea propia. EHAT no aparecía |
| 4 | Se cargó a la convocatoria lo que es limitación nuestra: «no se proporcionan candidatos de socio» | Es una propiedad del catálogo de socios, no de la oportunidad |
| 5 | Presupuesto pequeño y plazo corto entraron en el motivo de descarte | Para eso existe `actionability_score`, que ya valía 25 por separado |

### 47.2. Y una frase que yo mismo partí por la mitad

Revisando el prompt de sistema apareció una regresión introducida el 20/08 al
insertar la instrucción de `objeto_y_actuaciones`: partió en dos la frase de
`consortium_required`, que quedó así durante cuatro días —

> «…`consortium_required=false` significa que la evidencia admite solicitantes
> individuales además de **objeto_y_actuaciones debe abrir el análisis**: una
> sola frase densa…»

— con el resto de la frase (`consorcios; no lo presentes como requisito
pendiente`) huérfano cien palabras más abajo. El evaluador leyó cuatro días una
instrucción rota sobre consorcios, y PowerUp NetZero penalizó precisamente el
consorcio (`consortium_readiness: 30`).

**Ninguna prueba podía verlo** porque `evaluation_system` era una variable local
dentro de `analyze_with_claude()`. Ahora es la constante de módulo
`CLAUDE_EVALUATION_SYSTEM_PROMPT`, y hay pruebas que comprueban que la frase
sigue entera y que ningún nombre de campo del esquema aparece detrás de una
preposición, que es la huella que deja este tipo de empalme.

### 47.3. Lo que se ha cambiado

1. **Prompt de evaluación**: `required_topics` se trata como las líneas —basta
   encajar en uno— con obligación de **declarar en cuál** si concluye que hay
   encaje, y de recorrer esa lista si concluye que no. `fit_score` no puede
   bajar por presupuesto, plazo ni ausencia de socios en nuestro catálogo.
2. **Prompt de sistema**: frase de consorcio reparada, más la nota de que
   Kalfrisa tiene experiencia acreditada en consorcios y de que un
   `deterministic_tech_tags` vacío significa «la taxonomía térmica no reconoció
   el vocabulario», no «no hay encaje».
3. **Perfil**: simulación y gemelos digitales pasan a **línea propia** (CFD/HPC,
   modelización, validación experimental, EHAT y DT4RAF), declarada capacidad
   autónoma aplicable aunque el paraguas de la convocatoria no sea térmico. Y la
   lista «FUERA DE FOCO» aclara que describe el objeto de un proyecto, no la
   portada de un programa.
4. **Versiones subidas**: perfil a `kalfrisa-2026-08-v5-simulation-line`,
   evaluador a `fit-2026-08-v7-topic-and-scope`, prompt a
   `2026-08-v11-topic-and-scope`.

**Lo que NO se ha cambiado, y por qué.** La propuesta inicial incluía ampliar la
taxonomía con «captura de carbono», «almacenamiento» e «hidrógeno» suelto, para
que la convocatoria dejara de llegar con `tech_tags: []`. Al medirlo, no
funcionaba: los términos contextuales exigen contexto industrial cerca y **el
texto de PowerUp no tiene ninguno** —una sola aparición de «industrial», dentro
de la fórmula «industrially relevant environment» del TRL—. Forzar la etiqueta
habría sido la regla ad-hoc para una convocatoria concreta que prohíbe la
sección 1. `tech_tags: []` es honesto ahí; lo que estaba mal era usarlo como
prueba de desalineación, y eso se corrige en el prompt.

### 47.4. ¿Hay más casos así?

Se revisaron las 46 descartadas buscando solape real entre sus temas o
actuaciones y el vocabulario de capacidades del perfil, con límites de palabra.
Salen 8, y examinadas una a una **PowerUp NetZero es el único falso negativo
claro**:

| Convocatoria | fit | Veredicto |
|---|---|---|
| PowerUp NetZero | 35 | **falso negativo** |
| De-risking renewable fuel technologies | 15 | correcto: es compra pública precomercial, solo autoridades contratantes |
| PYME Sostenible / PYME Digital (Granada) | 35 / 15 | correcto: territorial |
| Cabildo de Lanzarote | 15 | correcto: territorial |

No hay sesgo sistemático. Hay un modo de fallo concreto, que se dispara cuando
el paraguas temático es amplio y el encaje está en un subtema.

**Nota metodológica:** el primer barrido usó una expresión sin límites de
palabra y «voc» casaba dentro de «conVOCatoria», devolviendo 38 falsos
positivos de 46. Es exactamente el error que `_term_present()` existe para
evitar (sección 31) y conviene recordarlo antes del próximo barrido manual.

### 47.5. El informe de desfase

Idea del usuario, con su encuadre: *las subvenciones se mueven despacio, así que
la frecuencia útil no baja de 3 días o una semana*. Decisión: **no** se
periodifica la llamada a Claude; se programa una recopilación `--no-claude`
diaria y se mira cuántas convocatorias esperan análisis, para decidir a mano
cuándo pagar.

No hizo falta recopilar nada nuevo: el dato ya estaba. Cada `--no-claude` guarda
su `claude_forecast` en la auditoría, y cada ejecución completa queda marcada
como publicación. `grant_radar/staleness.py` solo lee ese histórico, así que es
instantáneo, gratuito y no toca la red.

- `--staleness-report`: modo aislado que imprime la última publicación, cuántas
  convocatorias esperan análisis, lo que costaría ponerse al día y las catorce
  últimas mediciones.
- Cada `--no-claude` cierra ya con una línea de desfase.

**Un error propio, corregido antes de commitear:** la primera versión contaba
como pendientes una previsión **anterior** a la última publicación, de modo que
declaraba ocho convocatorias esperando análisis justo después de haberlas
analizado y publicado. Ahora solo cuenta lo medido después de publicar, y si no
hay medición posterior lo dice en vez de inventar un número. Hay prueba propia.

### 47.6. Cómo programar la recopilación diaria

En Windows, con el Programador de tareas. El pipeline no necesita cambios: basta
llamarlo con `--no-claude`, que ya no toca la caché de análisis ni publica.

```powershell
$accion = New-ScheduledTaskAction -Execute "poetry" `
  -Argument 'run python "Grant-Radar-prueba.py" --no-claude' `
  -WorkingDirectory "C:\Users\guillermo.ortega\Desktop\Guillermo\Grant-Radar - Claude Code"
$disparador = New-ScheduledTaskTrigger -Daily -At 7:00am
Register-ScheduledTask -TaskName "Grant-Radar diario" -Action $accion -Trigger $disparador
```

Dos avisos antes de activarlo:

1. Cada recopilación tarda unos 13 minutos y consulta ocho fuentes públicas. Una
   al día está muy por debajo de lo que provocó el `HTTP 429` de `boe.es` el
   19/08 (ocho en un día), pero conviene no encadenar ejecuciones manuales el
   mismo día que corra la programada.
2. Con `VIRTUAL_ENV` heredada en este equipo, la tarea debe limpiarla antes de
   llamar a `poetry` (ver `CLAUDE.md`), o ejecutará contra el entorno de la
   carpeta original.

Consultar el desfase acumulado no requiere esperar a nada:
`poetry run python "Grant-Radar-prueba.py" --staleness-report`.

### 47.7. Verificación y estado

**471 pruebas** en verde (448 + 23: 11 del prompt y el perfil, 12 del informe de
desfase). Ejecución `--no-claude` completa, código 0, sin desviaciones:

> 956 detectadas · 35 duplicadas fusionadas · 39 tras el prefiltro inicial ·
> **77 vigentes** (BDNS 47, Horizon 19, CDTI 5, ECCP 4, EEN 2, IDAE 1, BOE 1,
> BOA 0) · prefiltro común `retain=32, ambiguous=7, hold_manual=75, reject=842`
> · resolución automática de holds `ambiguous=38, reject=37, revisión manual=0`.

Las cuatro fuentes con control de salud siguen `healthy` y no hay regresiones de
embudo. Era lo esperable: esta ronda toca prompt y perfil, no recopilación.

**La previsión pasa de 0,2048 a 1,9712 USD**, y esa es la prueba de que los
cambios están activos: subir perfil, evaluador y prompt invalidó las 77 entradas
de caché. La línea de desfase lo dice con todas las letras:

```
Desfase: 77 convocatorias pendientes de analizar · 1.9712 USD ·
0 días desde la última publicación.
```

Cero días desde la publicación y aun así 77 pendientes: no es una contradicción,
es exactamente lo que significa invalidar la caché. El informe lo describe bien.

**Decisión del usuario, vigente:** aplicar los cambios y **no reanalizar
todavía**. Lo publicado el 21/08 sigue siendo válido y visible; incorpora los
arreglos de las secciones 44 a 46, pero **no** los de esta. PowerUp NetZero
seguirá mostrando su 35 % hasta que se autorice una ejecución completa.

Antes de esa ejecución conviene agrupar también el punto 24 del backlog
—endurecer la instrucción contra presunciones en `objeto_y_actuaciones`—, que
lleva abierto desde el 20/08 esperando exactamente esta oportunidad: es otro
cambio de prompt, y pagar dos veces la misma invalidación no tiene sentido.

## 48. Terminar la modularización y agrupar los cambios de prompt, a 31/08/2026

> Nota al arrancar en frío: **la sección de partida vigente es la 53**, que
> resume las cinco de hoy y deja escrito el próximo paso. Esta cuenta la
> primera de ellas.

Diez días sin tocar el proyecto. La sesión arranca con una decisión del usuario
que ordena todo lo demás: **no reanalizar dos veces**. Primero se termina la
estructura y se revisa la capa de análisis; todo lo que invalide caché se
agrupa ahí; y la ejecución de pago va al final, una sola vez.

### 48.1. De qué se partía

Línea base medida hoy antes de tocar nada (`--no-claude` completa, 684 s,
código 0):

> 915 detectadas · 34 duplicadas fusionadas · 40 tras el prefiltro inicial ·
> **80 vigentes** (BDNS 49, Horizon 19, CDTI 5, ECCP 4, EEN 3, IDAE 1, BOE 1,
> BOA 0) · prefiltro común `retain=33, ambiguous=7, hold_manual=75, reject=800`
> · previsión 80 análisis, **2,0480 USD**.

Comparado con el 21/08: 956 → 915 detectadas y 77 → 80 vigentes. Es movimiento
externo, no regresión: la ventana deslizante de BDNS entra y saca convocatorias
por su cuenta (43.3). Las cuatro fuentes con control de salud siguen `healthy` y
`compare_funnels()` no señala ninguna caída de etapa.

Y lo que el usuario ve, que es lo que importa: `convocatorias.json` seguía
siendo el del 21/08 a las 12:12 UTC, con las versiones **anteriores**
(`fit-…v6`, prompt `v10`, perfil `v4`). Es decir, el arreglo de PowerUp NetZero
de la sección 47 no está publicado, y tres de sus 77 convocatorias ya tenían el
plazo vencido.

### 48.2. Ronda 1: el histórico de auditoría se va con la auditoría

`save_discovery_audit()` (117 líneas) y `_load_audit_runs()` se mueven a
`grant_radar/audit.py`, que ya tenía la otra mitad del concepto: `DISCOVERY_AUDIT`
y `audit_exclusion()` son la memoria de la ejecución en curso; estas dos la
persisten. Con ellas viajan `AUDIT_SCHEMA_VERSION` y `AUDIT_MAX_RUNS`.

Medido antes de moverlo: **no arrastraba ni una función del script**. Solo tres
constantes y `log`.

La ruta se pasa como parámetro —`save_discovery_audit(..., audit_file=AUDIT_FILE)`,
`load_audit_runs(AUDIT_FILE)`— siguiendo lo que ya hacían `cache_load(CACHE_FILE)`
y `previous_source_health(AUDIT_FILE)`. Ocho llamadas actualizadas, todas dentro
de `run_pipeline()`.

Efecto lateral que conviene anotar: la prueba de persistencia del inventario de
candidatas inyectaba `AUDIT_FILE` en `__globals__` para redirigir la escritura.
Con la ruta como parámetro eso sobra, así que la prueba se mudó a
`tests/test_grant_radar_audit.py` con import estándar y allí se le añadieron
siete más: rotación a `AUDIT_MAX_RUNS`, migración del esquema v1, exclusiones
huérfanas que se podan, y un histórico ilegible que se recrea sin detener la
ejecución.

### 48.3. Ronda 2: la capa de análisis con Haiku sale del script

Unas 740 líneas a `grant_radar/analysis.py`: `analyze_with_claude()`,
`_structured_claude_call()`, `_build_compatible_analysis()`, el presupuesto de
evidencia, el techo de salida y los dos prompts de sistema.

Otra vez la medición previa dio una sorpresa buena: **tampoco arrastraba ninguna
función del script**. Todo lo que invoca —`deterministic_rules`,
`claude_schemas`, `tech_taxonomy`, `partner_catalog`, `claude_usage`— ya estaba
en el paquete desde rondas anteriores.

Tres decisiones dentro de esta ronda:

1. **La clave de API se recibe, no se lee.** `analyze_with_claude(conv, api_key)`
   y `claude_key_format_is_valid(api_key)`, igual que `github_upload(token=…)` en
   `publishing.py`. Ningún módulo del paquete toca el entorno.
2. **Nace `grant_radar/profile_scope.py`** (205 líneas) con `_hard_out_of_scope()`
   y `_explicit_profile_incompatibility()`. No podían ir en `analysis.py`: las
   llama también la matriz de reglas, que se queda en el script, y eso habría
   obligado a las reglas a importar de la capa de Claude para *no* llamarla.
   Tampoco en `deterministic_rules.py`, cuyo contrato declara actuar solo sobre
   hechos ya extraídos. Son exclusiones de ámbito del perfil, con dos
   consumidores —antes y después del modelo—, y ahora eso está escrito.
3. **Punto 33 del backlog, cerrado.** `extraction_system` deja de ser variable
   local y pasa a `CLAUDE_EXTRACTION_SYSTEM_PROMPT`, con siete pruebas de
   integridad en el archivo que antes solo cubría el del evaluador (renombrado a
   `tests/test_grant_radar_prompts.py`, que es lo que de verdad prueba). Fijan
   las instrucciones que costó dinero descubrir: los centinelas de dato ausente,
   la defensa contra instrucciones incrustadas en un documento público, la
   prioridad del bloque oficial sobre el texto libre y el `eligible_actions` que
   no confunde objetivos con gastos.

La guarda genérica de empalmes —ningún nombre de campo detrás de una
preposición— se parametrizó para usarla en los dos prompts, y saltó a la primera
con un falso positivo instructivo: «0 para TRL y `'unknown'` **para
consortium_required**» es una frase legítima. Ese campo queda fuera de la guarda
en el prompt de extracción, con la razón escrita al lado, porque su instrucción
ya la fija otra prueba literal.

De paso desaparece una indirección que quedó del arreglo del 21/08:
`evaluation_system = CLAUDE_EVALUATION_SYSTEM_PROMPT`, una variable local que
solo copiaba la constante.

### 48.4. Ronda 3: la segunda mitad del dominio de holds

872 líneas a `grant_radar/holds.py`: resolución determinista, validación de
citas, piloto, replay y la reincorporación al pipeline. La primera mitad —qué
documentos tiene un hold— ya había salido a `hold_evidence.py` (sección 38).

Esta sí tenía acoplamiento, y era el previsto: tres llamadas directas a la
matriz de reglas, que **no se toca** (AGENTS.md 4.1). Se resuelve con el patrón
que ya usaba el propio dominio —`retrieve_bdns_hold_evidence()` recibía
`intrinsic_exclusion` desde antes— y que estrenó el conector ECCP con
`is_relevant_enough`: se inyectan como parámetro.

| Función | Recibe ahora |
|---|---|
| `resolve_hold_deterministically()` | `intrinsic_exclusion` |
| `apply_verified_bdns_hold_resolution()` | `prefilter` |
| `replay_bdns_hold_item()` | `prefilter`, `intrinsic_exclusion` |
| `replay_bdns_hold_report()` | `prefilter`, `intrinsic_exclusion` |
| `run_bdns_hold_pilot()` | `api_key`, `intrinsic_exclusion` |
| `resolve_bdns_holds_for_pipeline()` | `intrinsic_exclusion`, `prefilter` |

El script solo llama a tres de ellas y les pasa las funciones reales. Las otras
trece son internas del módulo.

Dos constantes se quedaban a medio camino, usadas por la matriz de reglas *y*
por los holds: `BDNS_NEW_ESTABLISHMENT_MIN_DAYS` y `BDNS_TECHNOLOGY_TERMS`. Van
a `grant_radar/bdns_fields.py`, que existe exactamente para eso y cuya cabecera
ya nombraba a la resolución de holds como su segundo consumidor.

Las rutas de los artefactos (`bdns_hold_ai_cache.json`, el informe del piloto y
el del replay) sí se calculan dentro del módulo, al contrario que en la ronda 1.
No es incoherencia: `hold_evidence.py` y `documents.py` hacen lo mismo porque
son los dueños de su archivo, mientras que la auditoría y la caché comparten el
suyo con el script. Como efecto práctico, las pruebas que redirigen esas rutas
por `__globals__` siguen funcionando sin cambios.

### 48.5. El punto 24, que llevaba once días esperando esta ocasión

Con los dos prompts ya legibles de una vez, se leyeron enteros, frase por frase,
buscando el empalme de la sección 47.2. No hay ninguno: las 12 frases del
extractor y las 19 del evaluador cierran donde deben.

Lo que sí seguía abierto era el **punto 24**. La instrucción decía «si la fuente
no detalla los gastos, descríbelo con lo que sí conste y no lo inventes», y el
Programa INNOVAE devolvió «se presume inversión en equipos…» (sección 41.2). No
la incumplía: una presunción declarada no es una invención. Ahora la frase
prohíbe la fórmula, no solo la mentira:

> «Si la fuente no detalla los gastos, dilo y describe solo lo que conste. No
> los completes por deducción ni con fórmulas del tipo «se presume»,
> «previsiblemente», «cabe esperar» o «se entiende que»: declarar una suposición
> no la convierte en un hecho, y este campo describe lo que dice la
> convocatoria, no lo que parece razonable suponer.»

Versiones subidas: evaluador a `fit-2026-08-v8-no-presumption` y prompt a
`2026-08-v12-no-presumption`. **El perfil y el extractor no cambian, así que sus
versiones tampoco**: subir una versión sin motivo cuesta dinero real. Y como la
caché ya estaba invalidada desde el 21/08, agrupar aquí este cambio no ha
costado nada.

### 48.6. Dos arreglos que sí se verán en el producto

**Punto 31 — la URL que era una frase.** Confirmado sobre el JSON publicado: el
registro `id=20` (BDNS 922117, certámenes feriales de Aragón) publicaba como
`url` el texto `hhtp://www.aragon.es/tramites), incluyendo en el buscador de
trámites el procedimiento número 11810…`. Viene del campo `sedeElectronica` de
la API, que es texto libre, y `_normalize_public_url()` lo dejaba pasar porque
`hhtp://` parece un esquema.

Arreglado en dos capas, con un solo helper —`_web_url_or_empty()` en
`parsing_helpers.py`— que corta en el primer espacio y solo acepta `http`/`https`:

1. En el conector, la sede electrónica solo se usa si es navegable; si no, se
   publica la ficha oficial de BDNS, que siempre lo es.
2. En la publicación, para que ninguna otra fuente pueda colar prosa en un campo
   que el dashboard trata como destino.

No repara el esquema a propósito: `hhtp` podría ser un `http` mal tecleado, pero
adivinarlo es inventarse un destino. La prueba usa la cadena literal publicada.

Comprobado de paso sobre las 77 publicadas: 74 `https`, 2 `http` y esa. No hay
`mailto:` ni ningún otro esquema que la regla nueva fuera a descartar.

**Punto 22 — el test que no habría avisado.** La prueba de regresión de la
ventana de BDNS fijaba 44 filas/día, medidos el 17-18/08. Con esa cifra
declaraba 79 días de cobertura y no habría detectado una caída por debajo del
mínimo de negocio de 60. Medición real de hoy contra la API, dos peticiones:
**3.500 filas cubriendo 67 días, 52,2 filas/día**.

La prueba pasa a fijar **54 filas/día**, que es la densidad más alta observada
(20/08), no la última ni la media: lo que estrecha la ventana es que se publique
más, así que el caso a resistir es el de más volumen. Con 54, las 35 páginas
cubren 64,8 días y el margen real queda a la vista. El comentario del conector
recoge las tres mediciones, para que la próxima no vuelva a partir de una sola.

`BDNS_LATEST_MAX_PAGES` no se mueve: sigue cumpliendo el mínimo.

### 48.7. Un efecto lateral que merecía limpiarse

Sacar casi 2.000 líneas dejó al script importando **61 nombres que ya no usaba**:
`anthropic`, los cuatro precios por millón de tokens, las quince salvaguardas
deterministas, los diez vocabularios de exclusión, los siete validadores de
cita… Un bloque de imports que describe dependencias inexistentes es
exactamente lo que hace difícil leer un archivo, y este archivo ahora se lee
para saber qué queda.

Se retiran los 61 —y solo esos: había otros 68 sin usar de rondas anteriores,
que no son de esta sesión y pueden estar sosteniendo el arnés de pruebas—. Dos
de los 61 resultaron estar sosteniéndolo justamente: `TECH_TAGS` y
`retrieve_bdns_hold_evidence` llegaban a `APP` de rebote por el `runpy`. La
corrección no es devolverlos al script, que no los usa, sino registrarlos en el
bloque de fusión desde su módulo real. Los imports del script vuelven a
describir el script.

### 48.8. Verificación

Las tres redes, en el orden de 43.3, después de cada una de las cinco rondas:

1. `tests.test_grant_radar_script_names` — la que más trabajó hoy. Señaló en un
   segundo el único acoplamiento que la medición previa no había anticipado
   (`analyze_bdns_hold_with_claude` llamando a `_structured_claude_call`
   después de que este se fuera a `analysis.py`) y confirmó cada módulo nuevo.
2. `py_compile`.
3. La suite completa: **471 → 493 pruebas**, todas en verde. Las 22 nuevas: 8
   del histórico de auditoría, 7 del prompt de extracción, 5 de la URL que era
   una frase y 2 del punto 24.
4. Cuatro ejecuciones `--no-claude` completas: la línea base, una tras la ronda
   2, otra al terminar las cinco rondas y la de cierre contra el código
   definitivo, ya con los imports limpios. Las cuatro con código 0 y las mismas
   cifras.

Cifras finales, `--no-claude` completa del 31/08/2026, código 0:

> 915 detectadas · 34 duplicadas fusionadas · 40 tras el prefiltro inicial ·
> **80 vigentes** (BDNS 49, Horizon 19, CDTI 5, ECCP 4, EEN 3, IDAE 1, BOE 1,
> BOA 0) · prefiltro común `retain=33, ambiguous=7, hold_manual=75, reject=800`
> · resolución automática de holds `ambiguous=40, reject=35, revisión manual=0`
> · previsión 80 análisis, **2,0480 USD** · 633 s.

Idénticas a la línea base de 48.1 en todo lo que debe serlo. Era lo esperable:
**esta sesión no toca la recopilación**. Mueve código de sitio, cambia una
instrucción del evaluador —que `--no-claude` no ejecuta— y arregla una URL de
BDNS que no altera el recuento. Que las cifras se muevan habría sido la señal de
alarma, no al revés.

Recuentos verificados con `wc -l`:

| | Al empezar el 31/08 | Al cerrar |
|---|---|---|
| `Grant-Radar-prueba.py` | 4.086 líneas | **2.140** |
| Paquete `grant_radar/` | 35 módulos | **38 módulos**, 11.660 líneas |
| Funciones de nivel superior en el script | 36 | **8** |
| Pruebas | 471 | **493** |
| Puntos abiertos del backlog | 32 | **28** |

### 48.9. Qué queda, y por qué queda

**En el script, dos cosas y las dos por decisión:**

1. La **matriz de reglas** (punto 8 del backlog): 526 líneas, siete niveles de
   precedencia, y la que decide qué llega a Claude y por tanto el coste. Sesión
   propia, y no encadenada detrás de nada sin que el usuario lo pida. `holds.py`
   y ECCP ya la reciben inyectada, así que moverla no obliga a tocarlos.
2. **`run_pipeline()`** con su `parse_args()`: el orquestador va el último por
   definición.

**En el producto, una decisión pendiente que es del usuario:** lo publicado
sigue siendo del 21/08. La ejecución completa que lo pondría al día cuesta
**~2,05 USD** (80 convocatorias, caché invalidada a propósito desde el 21/08 y
otra vez hoy al subir el evaluador) y publicaría de golpe el arreglo de PowerUp
NetZero, el punto 24, la URL rota y las convocatorias de estos diez días.
Requiere autorización expresa, como siempre.

Y sigue anotado el **punto 34**: programar la recopilación diaria `--no-claude`
en el Programador de tareas es una acción del usuario en su equipo, no del
agente. El comando está en 47.6.

## 49. Por qué casi nada llegaba a «elegible», y el aviso de la recopilación diaria, a 31/08/2026

Tres encargos del usuario mirando el producto, no el código: que la
recopilación diaria se vea en el panel, que la elegibilidad no aparezca dos
veces en una ficha, y que se estudie por qué casi ninguna convocatoria
consigue confirmarla.

### 49.1. El dato que estaba a la vista y no se veía

De las 31 convocatorias no descartadas del JSON publicado, **25 salían con
elegibilidad «por confirmar»**. Leídas una a una, no eran un solo problema
sino tres, y solo el primero era un fallo nuestro.

| Familia | Cuántas | Qué pasa |
|---|---|---|
| Convocatorias territoriales de otra comunidad | 8 | El propio texto dice «la convocatoria limita a ES22 (Navarra)» y aun así se publicaba como pendiente de confirmar |
| Horizon Europe y CDTI sin datos de elegibilidad | 14 | La fuente no publica quién puede solicitar: no está en el topic, está en los Anexos Generales del programa |
| Dudas legítimas | 3 | CNAE no listado en el IDAE, alcance de una ayuda nacional, y una convocatoria de Aragón con condiciones abiertas |

### 49.2. La primera familia: una regla que decidía leyendo prosa

`_enforce_explicit_regional_ineligibility()` existe justamente para cerrar
estos casos. Su intención estaba escrita —«mantiene el descarte cuando modelo y
hechos prueban otra región española»— pero su implementación exigía que el
**razonamiento redactado por el modelo** contuviera una de seis expresiones
tecleadas a mano (`restriccion geografica`, `esta en zaragoza`, `ubicacion:`…)
*y* una de otras siete (`limita a`, `no cumple`, `determinante`…).

Medido sobre las doce convocatorias reales del corpus a las que debía
aplicarse: **disparaba en una**. En las once restantes el modelo había escrito
lo mismo con otras palabras —«Kalfrisa está ubicada en Zaragoza (ES24), no en
Navarra (ES22)»— y la regla no lo reconocía.

Es el mismo error que el proyecto ya se ha encontrado dos veces: una regla
determinista que depende del vocabulario que el modelo elija esta vez. Ahora
decide sobre datos:

1. **El campo `regiones` de la API de BDNS**, que es oficial y llega en el
   `official_structured_data` desde la sección 40; si faltara, las geografías
   que extrajo el modelo.
2. Dos guardas medidas sobre el corpus: `ES - ESPAÑA` (ámbito nacional) no
   lleva código de región y no dispara, y si Aragón aparece entre las regiones
   admitidas —en cualquier forma: `ES24`, `ES243`, «Zaragoza»— tampoco.

Y de paso se corrige un segundo fallo del mismo sitio: el patrón `\bes\d{2}\b`
solo casaba con códigos de dos dígitos, así que **ES212 (Gipuzkoa), ES614
(Granada), ES120 (Asturias) o ES3 (Madrid) nunca entraban**. Media España se
escapaba de una regla escrita para toda ella.

**Efecto medido** con la función real sobre los 50 análisis BDNS en caché: 16
pasan a «no elegible», de los cuales 8 ya estaban descartados por otra regla.
Los **8 restantes desaparecen de las fichas «por confirmar»**: Navarra (2),
Granada, Asturias, Murcia, Comunidad Valenciana, Castilla-La Mancha y Cataluña.
Todas territoriales de otra comunidad, que es exactamente lo que la revisión de
la sección 47.4 ya había dado por correcto descartar.

**No cuesta un céntimo:** `apply_current_deterministic_rules()` se reaplica al
cargar la caché, así que la corrección entra sin reanalizar.

### 49.3. La segunda familia: la elegibilidad de Horizon no está en el topic

Catorce de las diecisiete «por confirmar» que quedan son de Horizon Europe y
CDTI, y no son un fallo del pipeline ni del modelo. El texto de un topic de
Horizon son 3.000 caracteres de *Expected Outcome* y *Scope*: **no dice quién
puede solicitar**, porque eso vive en los Anexos Generales del programa de
trabajo, comunes a todos los topics. El prompt prohíbe explícitamente completar
huecos, así que el modelo hace lo correcto: declara `applicant_types` ausente y
deja la elegibilidad en «unknown».

Queda como decisión abierta, no como pendiente técnico. La vía natural sería
inyectar **hechos de programa** —igual que BDNS inyecta su bloque oficial—: un
JSON versionado con las reglas generales de Horizon Europe y de CDTI, revisable
y con fecha de última revisión. Se anota como punto 35 del backlog con su
advertencia: los catálogos escritos a mano de este proyecto (puntos 27 y 28)
han caducado en silencio dos veces.

### 49.4. La elegibilidad salía dos veces en la misma ficha

Literal: `ov-eligibility-note` (la nota de la tarjeta ELEGIBILIDAD) y el aviso
amarillo de arriba imprimían **la misma cadena**, `c.eligibility_reason`. Como
ese texto son varias frases, la tarjeta se estiraba y descuadraba la fila de
indicadores.

La tarjeta pasa a decir **qué falta para decidir**, que es corto y no está en
ninguna otra parte de la ficha: «La fuente no publica: tipos de solicitante,
entidades admitidas, evidencia de elegibilidad», leído de `missing_fields`. El
razonamiento completo se queda donde tiene sitio, en el aviso.

### 49.5. La recopilación diaria, por fin visible

El flujo acordado el 21/08 (47.5) tenía un cabo suelto: la recopilación
`--no-claude` diaria mide cuántas convocatorias esperan análisis, pero ese
número solo salía por consola, así que **quien mira el panel no podía saber si
lo publicado seguía al día**.

Ahora cada recopilación escribe y publica `estado_recopilacion.json`: ocho
cifras que describen la recopilación, no el producto. El panel lo lee aparte y
muestra un aviso —«80 convocatorias esperan análisis · coste estimado 2,05 USD
· recopilado el 31/08 · lo publicado tiene 10 días»— que desaparece solo cuando
no hay nada pendiente.

**Matiz del invariante de `--no-claude`, que conviene leer entero:** sigue sin
llamar a Claude, sin tocar la caché de análisis y sin generar ni publicar
`convocatorias.json`. Lo que publica es un archivo distinto, pequeño y de solo
lectura para el panel. Publicar no es lo mismo que analizar, y era la parte del
circuito que faltaba para que la ejecución diaria sirviera para algo sin
intervención de nadie.

`github_upload()` acepta ahora un mensaje de commit propio, para que en el
historial se distinga una publicación completa de un estado diario.

### 49.6. Verificación

**507 pruebas** en verde (493 antes). Las 14 nuevas: 8 de la regla territorial
—incluidos los códigos de provincia, la convocatoria nacional y el caso en que
Aragón aparece junto a otra comunidad—, 4 del estado de recopilación, 1 del
aviso en el panel conducido con Chromium de verdad y 1 de que el motivo de
elegibilidad ya no se imprime dos veces.

### 49.7. Viabilidad de leer los Anexos Generales de Horizon, medida

El usuario descartó la propuesta inicial —escribir a mano las reglas del
programa— y planteó otra mejor: **que el código busque y acceda al anexo
general**, de forma que cuando el programa cambie no haya que tocar nada
porque leerá el documento nuevo. Se estudió con sondas públicas, sin coste, y
sale viable en las tres etapas.

**1. Descubrir el documento.** No hace falta buscarlo: viene en la respuesta
que el conector ya recibe. La SEDIA API entrega por cada topic dos campos de
metadatos que hoy **no se leen**:

| Campo | Qué trae |
|---|---|
| `topicConditions` | 10.349 caracteres de HTML con el bloque «General conditions» y 32 enlaces, entre ellos el de los Anexos Generales |
| `typesOfAction` | «HORIZON Innovation Actions», que es lo que determina qué regla de consorcio aplica |

Y el enlace apunta a la edición correcta por sí solo:
`…/horizon/wp-call/2026-2027/wp-15-general-annexes_horizon-2026-2027_en.pdf`.
Un topic de 2028 traerá el suyo. Es exactamente lo que el usuario pedía: sin
catálogo que mantener y sin caducidad silenciosa.

**2. Acceder y leer.** Medido: **557 KB, 46 páginas, 0,7 s de descarga y 1,4 s
de extracción** con el `pypdf` que ya es dependencia; 130.633 caracteres de
texto. `grant_radar/documents.py` ya tiene descarga, extracción y caché
documental, así que sería **una descarga por edición**, compartida por los 19
topics de Horizon de una ejecución, no una por convocatoria.

**3. Encontrar las condiciones.** Las tres secciones que importan existen con
título propio y texto literal:

- *Entities eligible to participate* — «Any legal entity, regardless of its
  place of establishment […] is eligible to participate».
- *Entities eligible for funding* — la lista de países (Estados miembros,
  regiones ultraperiféricas, países asociados…).
- *Consortium composition* — «only legal entities forming a consortium are
  eligible to participate […] three legal entities independent from each other
  and each established in a different country», con el matiz de que las
  entidades afiliadas no cuentan para el mínimo.

Es decir: la respuesta a «¿puede Kalfrisa presentarse?» está en el documento,
en prosa localizable por encabezado, no dispersa.

**Coste de inyectarlo.** Pasar el anexo entero sería absurdo: 130.000
caracteres son unos 33.000 tokens por llamada. Pasar **solo las tres secciones
localizadas** son unos 4.000-6.000 caracteres, ~1.500 tokens por convocatoria
de Horizon: con 19 topics, unos 0,03 USD por ejecución completa. Despreciable
frente a los 2 USD que ya cuesta.

**Lo que falta antes de implementarlo**, y por eso queda como punto 35 y no
como hecho: decidir si el evaluador debe tratar esas condiciones como hechos de
la convocatoria —hoy el prompt le prohíbe completar huecos, y con razón— y
subir las versiones correspondientes, lo que obliga a que entre en la misma
reanalisis que el resto. También conviene decidir qué se hace cuando el enlace
falle: lo coherente con el resto del proyecto es dejar el dato ausente y
declararlo, nunca suponerlo.

## 50. Horizon deja de llegar sin elegibilidad: se leen sus Anexos Generales, a 31/08/2026

Implementación de lo que la sección 49.7 midió. La decisión de fondo es del
usuario y conviene dejarla escrita porque cambia el criterio del proyecto: ante
un dato que la fuente no publica, **no se teclea el dato, se busca el documento
que lo contiene**.

### 50.1. Lo que había y lo que hacía falta

De las 17 convocatorias que seguían «por confirmar» tras el arreglo territorial,
14 eran de Horizon Europe y CDTI. La causa no era nuestra: el texto de un topic
son 3.000 caracteres de objetivos y alcance, y quién puede solicitar está en los
Anexos Generales del programa de trabajo, comunes a todos los topics de esa
edición.

La propuesta inicial —un JSON con las reglas del programa escritas a mano— la
descartó el usuario con un argumento mejor: que el código busque el anexo, para
que un cambio de programa no obligue a tocar código. Y el proyecto le da la
razón dos veces: los dos catálogos tecleados que existen han caducado en
silencio (seis URLs de CDTI en 404 durante cuatro meses, sección 44.1; el
catálogo de BOA con «última revisión 2026-04-09», punto 28).

### 50.2. Cómo se resuelve, en tres pasos que ya no envejecen

**1. El enlace lo da la propia convocatoria.** La SEDIA API entrega por cada
topic dos campos que el conector **no leía**: `topicConditions` (10 KB de HTML
con el bloque «General conditions» y 32 enlaces) y `typesOfAction`. Entre esos
enlaces está el de los Anexos Generales de la edición del topic:
`…/wp-call/2026-2027/wp-15-general-annexes_horizon-2026-2027_en.pdf`. Un topic
de 2028 traerá el suyo, y esto leerá el documento nuevo sin que nadie lo toque.

**2. El documento se lee una vez por edición.** 557 KB, 46 páginas: 0,7 s de
descarga y 1,4 s de extracción con el `pypdf` que ya era dependencia. El módulo
nuevo `grant_radar/programme_annexes.py` recibe el cliente HTTP y el extractor
documental como parámetros —así se prueba sin red y sin PDF— y guarda un memo
por ejecución. **Medido en vivo: 30 convocatorias, 30 con condiciones, una sola
descarga.**

**3. Se envían tres extractos, no el documento.** El anexo entero son 128.000
caracteres, unos 33.000 tokens por llamada: mandarlo sería tirar el dinero. Se
localizan por su encabezado literal las tres secciones que deciden y se acotan:

| Sección | Qué aporta | Límite |
|---|---|---|
| `Entities eligible to participate` | Cualquier entidad jurídica puede participar | 700 |
| `Entities eligible for funding` | La lista de países financiables, España incluida | 1.500 |
| `Consortium composition` | Tres entidades independientes de tres países distintos | 1.200 |

Total: **3.400 caracteres, unos 850 tokens por convocatoria**. Con 30 topics,
unos 0,03 USD por ejecución completa frente a los ~2 USD que ya cuesta.

Si algo falla —no hay enlace, el PDF no responde, el texto no trae las
secciones— se devuelve vacío y el dato queda ausente. Nunca se supone: es la
misma disciplina que el resto del pipeline, y hay prueba de cada caso.

### 50.3. Cómo llega a Haiku

Las condiciones viajan dentro del bloque `<official_structured_data>`, que el
prompt ya trata como evidencia de primer orden, pero **etiquetadas como lo que
son**: `condiciones_generales_del_programa`, con el documento del que se
leyeron, más `tipo_de_accion`. La instrucción nueva dice que aplican salvo que
el texto de la convocatoria diga otra cosa —que es literalmente lo que el propio
anexo establece— y que con ellas hay que rellenar `eligible_entity_types`,
`eligible_geographies` y `consortium_required` en vez de declararlos ausentes.

`tipo_de_accion` no es un adorno: de las 30 convocatorias de hoy, 19 son
Innovation Actions, 5 RIA, 3 JU RIA, 2 CSA y 1 compra precomercial, y **el
mínimo de socios depende de esa modalidad**. Una CSA no exige consorcio de tres,
y hasta hoy el modelo no tenía forma de saber cuál era cuál.

Versiones subidas: extractor a `facts-2026-08-v8-programme-annexes` y prompt a
`2026-08-v13-programme-annexes`. La caché ya estaba invalidada, así que este
cambio entra en la misma reanalisis pendiente sin coste adicional.

### 50.4. Un límite conocido, escrito para no descubrirlo dos veces

`source_hash()` no incluía el bloque oficial —ni el de BDNS ni este—, así que
si la Comisión corrigiera los anexos **dentro de la misma edición**, una
convocatoria ya analizada no se reanalizaría por sí sola.

**Resuelto el mismo día, y la solución merece leerse** (sección 51.1): la huella
del anexo entra en `source_hash()` **solo cuando la convocatoria lleva
condiciones de programa**. Así se consigue lo que hacía falta —reanalizar cuando
el documento cambia— sin lo que se temía: añadir una clave a todos los registros
habría invalidado de golpe la caché de las ocho fuentes por un dato que siete no
usan.

### 50.5. Verificación

**523 pruebas** en verde (507 antes). Las 16 nuevas: 14 del módulo —incluido
que el enlace sale del topic, que el mínimo de consorcio sobrevive entero, que
un documento inalcanzable deja el dato ausente y que no se descarga dos veces— y
2 de que las condiciones llegan al payload con su documento y no se cuela un
bloque vacío cuando no las hay.

Ejecución del conector en vivo: 30 de 30 con condiciones, un solo documento
leído, 94 s. Ejecución `--no-claude` completa: código 0 y las cifras de
referencia intactas.

## 51. Reutilizar lo leído, y las tres medidas propuestas, a 31/08/2026

Cierre de la sesión. El usuario aprobó las tres medidas propuestas y añadió una
pregunta que resultó ser la más importante de las cuatro.

### 51.1. La pregunta: ¿y esto se reanaliza cada vez?

Sobre los Anexos Generales recién implementados: *«¿se ha previsto guardar lo
que se extraiga para que Haiku no lo analice si no ha cambiado?»*. La respuesta
honesta era **a medias**, y el hueco estaba anotado en la sección 50.4 como
límite conocido:

- La caché de análisis ya evitaba reanalizar una convocatoria sin cambios, así
  que el anexo viajaba solo cuando esa convocatoria se analizaba de todas
  formas. Eso ya funcionaba.
- Pero el texto del anexo **no entraba en `source_hash()`**, así que una
  corrección de la Comisión no habría provocado reanálisis: se habría seguido
  publicando con las reglas viejas hasta que alguien subiera una versión a mano.
- Y el documento se descargaba en cada ejecución, sin memoria entre ellas.

Las tres cosas quedan resueltas:

1. **Huella en la clave de caché.** `sections_fingerprint()` resume el texto que
   se le envía al modelo y `source_hash()` lo incorpora **solo cuando la
   convocatoria lleva condiciones de programa**. El matiz importa: añadir una
   clave vacía a todos los registros habría invalidado de golpe la caché de las
   ocho fuentes por un dato que siete de ellas no usan.
2. **Caché en disco** (`programme_annexes_cache.json`), con relectura cada 7
   días. Un anexo publicado no cambia a diario, pero la Comisión publica
   correcciones dentro de una misma edición.
3. **Respaldo ante fallo.** Si el portal no responde, se conservan las
   condiciones leídas la última vez en lugar de perderlas — que es lo que antes
   habría dejado treinta convocatorias «por confirmar» y, peor, habría
   provocado un reanálisis con peor información.

El comportamiento resultante es el que pedía el usuario: **se paga por leer el
anexo una vez, y solo se vuelve a pagar cuando el anexo cambia de verdad**. Y
cuando cambie, el aviso queda en el registro de la ejecución.

### 51.2. Medida (a): CDTI también trae sus bases

Las tres convocatorias de CDTI que seguían «por confirmar» eran las de
ventanilla abierta del catálogo curado, y la causa estaba medida: llegaban con
**~300 caracteres tecleados a mano y cero documentos**, mientras las del
calendario oficial llegaban con sus bases adjuntas. Nadie le estaba enseñando al
modelo quién puede solicitarlas.

`_attach_catalog_official_documents()` aprovecha que la ficha ya se visita con
el navegador para comprobar que existe —lo que se añadió en la sección 44— y la
lee con el mismo extractor que el calendario. Solo las fichas concretas, que en
cdti.es viven bajo `/ayudas/`: una página de programa lista PDF de varias
convocatorias y adjuntárselos a una sola sería peor que no adjuntar nada.

**Dos cosas se midieron mal a la primera y conviene dejarlas escritas**, porque
las dos parecían funcionar:

1. La decisión de visitar o no se tomaba con el campo `url_generica` del
   catálogo, y las tres fichas corregidas el 21/08 **seguían marcadas como
   genéricas**: la mejora no hacía nada justo en las convocatorias que la
   necesitaban. Ahora decide la ruta, que es un hecho comprobable, y de paso se
   corrigen las tres marcas —el panel les mostraba un aviso de «página general
   del programa» que ya no era cierto—.
2. Con los documentos adjuntos, el rastro se llenaba y **no llegaba una sola
   línea de texto al modelo**: `enrich_with_official_documents()` solo descarga
   roles de bases o convocatoria, y el PDF de la ficha se clasificaba como
   registro genérico. Cada página enlaza además dos documentos que salen en
   todas (FAQ de empresas en crisis, exención de garantías), así que tampoco
   valía con aceptarlos todos. `_catalog_programme_document()` reconoce el que
   repite el nombre del programa y lo reclasifica como bases reguladoras.

Resultado medido con Chromium real: **3 de las 4 fichas del catálogo llegan con
su documento y 20.015 caracteres de texto**, incluidas sus secciones «Entidades
beneficiarias», «Actividades excluidas» y «Gastos financiables». La cuarta
—Proyectos Bilaterales— apunta a una página de programa y se queda como estaba.
Un fallo del navegador nunca pierde la entrada.

### 51.3. Medida (b): prueba de humo por conector

Punto 17 del backlog, abierto desde el 19/08. Cada `fetch_*()` se ejecuta de
principio a fin con la red y el navegador sustituidos por dobles que responden
bien y vacío. **Diez pruebas, 0,2 segundos**, frente a los once minutos de una
recopilación —o a una ejecución de pago, que es donde apareció el `statistics`
del conector ECCP (sección 35)—.

Una de las diez comprueba que el detector detecta: fuerza el error real de
entonces y exige que salga a la superficie. Y el encabezado dice el límite en
voz alta: con respuestas vacías no se recorren las ramas que solo existen
cuando la fuente trae datos. Reduce el hueco, no lo cierra; la ejecución
`--no-claude` sigue siendo obligatoria al cerrar una ronda.

### 51.4. Medida (c): vigilar el producto, no solo el embudo

`compare_funnels()` vigila la recopilación. El otro extremo —el JSON que ve el
usuario— no lo vigilaba nadie, y esta misma sesión lo demostró: corregir la
regla territorial movió dieciséis análisis a «no elegible» de golpe. Era lo
correcto, pero **nada lo habría dicho** si no llega a mirarse a mano.

`grant_radar/product_watch.py` compara la versión que se va a publicar con la
que sustituye, justo antes de escribirla, que es la única oportunidad de tener
las dos a mano. Cuatro señales, elegidas porque un cambio brusco en ellas suele
significar un cambio de código y no del mundo:

| Señal | Por qué |
|---|---|
| Convocatorias que desaparecen **sin vencer su plazo** | Si caducó, es normal; si no, alguien dejó de encontrarla |
| Convocatorias nuevas | No son un problema, pero explican el resto |
| Movimientos de elegibilidad en bloque | El caso de esta sesión |
| Campos publicados que se vacían | Una regresión que los recuentos no ven: siguen siendo 77 fichas |

Umbral de tres registros: en un producto de ochenta convocatorias, dos
movimientos sueltos son funcionamiento normal. El resumen sale por consola y
queda en `RUN_DIAGNOSTICS["product_changes"]`, es decir, en la auditoría.

Probado contra el producto real: con el JSON actual contra sí mismo dice
«Producto: 77 publicadas.» y calla; con una regresión simulada dice «⚠ 17
desaparecen sin vencer su plazo · ⚠ 40 se quedan sin objeto_y_actuaciones».

Un detalle que se corrigió sobre la marcha: el resumen contaba la **muestra**
recortada a diez en vez del total, de modo que con diecisiete desaparecidas
decía diez. Tiene prueba propia.

### 51.5. Verificación

**566 pruebas** en verde (523 antes). Las 43 nuevas: 8 de la reutilización de
los anexos entre ejecuciones, 11 del catálogo de CDTI —incluidas las que fijan
cómo se reconoce el documento del programa entre los genéricos de la página—,
10 de humo por conector y 14 de la vigilancia del producto.

Ejecución `--no-claude` completa, código 0: 916 detectadas, **81 vigentes**
(Horizon 20 y EEN 4, uno más cada una que por la mañana; movimiento externo, no
del código). Y una comprobación aparte con Chromium real sobre el catálogo de
CDTI, porque es la única forma de ver que el texto llega de verdad.

## 52. El dinero de Horizon, que estaba en la respuesta y se tiraba, a 31/08/2026

El usuario pidió mover el aviso de recopilación al final del panel y preguntó si
quedaba alguna prueba o mejora de extracción antes de pagar. Contestar esa
pregunta con datos, y no de memoria, destapó el mayor hueco de extracción que
tenía el proyecto.

### 52.1. Dónde se estaba trabajando menos: el dinero

Recuento de campos ausentes por fuente sobre los análisis en caché:

| Fuente | Campos que más faltan |
|---|---|
| **Horizon Europe** | **19/19 sin `budget_total_eur`, `project_budget_eur`, `grant_max_eur` ni `funding_rate_percent`** |
| BDNS | 42/50 `trl_source`, 34/50 `project_budget_eur`, 30/50 `eligible_actions` |
| CDTI | 8/8 TRL, 7/8 presupuesto (mejorado hoy, sección 51.2) |

Lo de BDNS es esperable: unas bases españolas rara vez hablan de TRL. Lo de
Horizon no: **las diecinueve llegaban sin una sola cifra económica**, y la razón
resultó ser nuestra.

`budgetOverview` es un campo que la SEDIA API entrega en la misma respuesta que
ya descargamos, y trae por topic:

| Campo | Qué es |
|---|---|
| `minContribution` / `maxContribution` | Cuánto se financia **por proyecto** |
| `budgetYearMap` | El presupuesto de la convocatoria, por año |
| `expectedGrants` | Cuántos proyectos se esperan financiar |
| `deadlineModel` | Una fase o dos |

El conector lo reducía todo a la cadena **«Presupuesto 2026»**. Es exactamente
el mismo patrón que los Anexos Generales de la sección 50: el dato estaba en
casa y nadie lo miraba.

### 52.2. Qué se ha cambiado

`_horizon_budget_facts()` lee el bloque y `_horizon_budget_summary()` lo escribe
para el panel. Un detalle que importa y tiene prueba propia: el mapa lista
**varias acciones**, porque un mismo bloque presupuestario cubre topics
hermanos, y hay que quedarse con la que empieza por el identificador del topic.
Coger la primera habría publicado el presupuesto del vecino, que es peor que no
publicar ninguno; si el topic no aparece, se devuelve vacío.

Las cifras viajan además al bloque oficial como `cifras_oficiales_del_topic`,
donde el prompt ya las trata como evidencia de primer orden.

Medido en vivo sobre las 30 convocatorias de Horizon de hoy: **30 de 30 con
cifras**. Lo que el panel publicaba y lo que publicará:

> antes: `Presupuesto 2026`
> ahora: `9.000.000 € por proyecto · 18.000.000 € en total · 2 proyectos previstos`

Versiones subidas a `facts-2026-08-v9-programme-annexes-and-budget` y
`2026-08-v14-programme-annexes-and-budget`.

### 52.3. El aviso de recopilación, al final

Movido del encabezado al pie, con tono de nota en vez de aviso. El motivo lo dio
el usuario y conviene recordarlo al tocar el panel: **la herramienta la usa
personal que no la mantiene**, y el estado de la monitorización no es lo que ha
venido a ver. Sigue apareciendo solo cuando hay convocatorias esperando análisis.

### 52.4. Lo que queda antes de pagar, dicho en orden

1. **Una prueba dirigida de pago**, no la completa. El proyecto ya lo hizo el
   20/08 (sección 41) por 0,09 USD: `--max-claude 3` con convocatorias elegidas
   —una de Horizon, una de CDTI y una territorial— comprueba que los cambios de
   hoy producen lo que se espera antes de gastar dos euros en ochenta y una. Es
   la única prueba que falta, porque la ruta de análisis solo se recorre
   pagando.
2. Después, la ejecución completa.

Lo que **no** conviene seguir persiguiendo antes de pagar: el TRL de BDNS
(42/50 ausentes) no es un fallo de extracción sino una ausencia real en las
bases españolas, y `eligible_actions` en BDNS (30/50) depende de que el hold
haya descargado las bases, que ya tiene su propio mecanismo. Ahí no hay un dato
en la mano sin usar, que es lo que sí había en Horizon.

## 53. Cierre de la sesión del 31/08/2026 y punto de partida para la siguiente

**Esta es la sección de arranque en frío vigente.** Sustituye a la 48 como punto
de partida. El detalle está en las secciones 48 a 52; esto es lo que hace falta
para retomar sin releerlas.

### 53.1. Qué cambió hoy

| | Al empezar el 31/08 | Al cerrar |
|---|---|---|
| `Grant-Radar-prueba.py` | 4.086 líneas | **2.203** |
| Paquete `grant_radar/` | 35 módulos | **40 módulos** |
| Pruebas | 471 | **575** |
| Puntos abiertos del backlog | 32 | **28** |
| Producto publicado | JSON del 21/08 | el mismo: **no se ha pagado nada** |

Cinco rondas de estructura (48), tres encargos de producto (49), los Anexos
Generales de Horizon (50), la reutilización de lo leído y tres medidas nuevas
(51) y el presupuesto de Horizon (52).

### 53.2. El próximo paso, decidido con el usuario

**1. Prueba dirigida de pago, antes de la completa.** Requiere autorización
expresa:

```
poetry run python "Grant-Radar-prueba.py" --max-claude 3 --claude-match HORIZON-CL5-2026-09-D4-08 --claude-match "Proyectos de I+D" --claude-match 919481
```

Tres convocatorias, una por cada cosa que hay que comprobar: el topic de Horizon
para las cifras y las condiciones del programa, la ficha de CDTI de ventanilla
abierta para su documento oficial recién adjuntado, y la BDNS 919481 (Navarra)
para que salga «no elegible» por territorio sin pedir confirmación.
`--max-claude` no publica ni genera `convocatorias.json`. Coste de una prueba
equivalente el 20/08: 0,09 USD (sección 41).

**2. En esa misma prueba, revisar la extracción de presupuestos.** Es lo último
que se tocó y lo menos rodado. Qué mirar, en concreto:

- que `budget_total_eur`, `grant_max_eur`, `project_budget_eur` y
  `funding_rate_percent` **dejen de aparecer en `missing_fields`** para la
  convocatoria de Horizon, que es donde faltaban en 19 de 19;
- que las cifras del análisis **coincidan** con las del `budgetOverview`
  oficial: para `HORIZON-CL5-2026-09-D4-08`, 9.000.000 € por proyecto,
  18.000.000 € en total y 2 proyectos previstos;
- que no se haya colado el presupuesto de un topic hermano, que es el error que
  `_horizon_budget_facts()` evita a propósito y el único que produciría
  desinformación en vez de ausencia (sección 52.2).

**3. Solo después, la ejecución completa** (~2,07 USD sobre 81 convocatorias),
que publica de golpe todo lo acumulado el 31/08.

### 53.3. Decisión cerrada: el TRL no se persigue

Confirmado por el usuario al cerrar la sesión, y se anota para que ninguna
sesión futura lo reabra como si fuera un pendiente:

> En Horizon, donde el TRL se anuncia de forma visible, se recoge. En BDNS,
> donde no se anuncia, no se recoge. **Es una ausencia real de la fuente, no un
> fallo de extracción, y no tiene importancia para el uso de la herramienta.**

Los 42 de 50 análisis de BDNS sin `trl_source` no son un hueco que tapar. Si
alguna vez vuelve a aparecer en un recuento de campos ausentes, es ruido
esperable: pasar de largo sin darle más importancia.

### 53.4. Cómo verificar cualquier cambio, en orden

Sigue vigente el orden de 43.3, con las cifras de hoy:

1. `poetry run python -m unittest tests.test_grant_radar_script_names` —siempre
   el primero; desde el 31/08 comprueba también cada módulo del paquete.
2. `poetry run python -m py_compile "Grant-Radar-prueba.py"`.
3. `poetry run python -m unittest discover -s tests` —**575 pruebas**.
4. `poetry run python "Grant-Radar-prueba.py" --no-claude`, contra la referencia
   del 31/08/2026:

   > 916 detectadas · 34 duplicadas fusionadas · **81 vigentes** (BDNS 49,
   > Horizon 20, CDTI 5, ECCP 4, EEN 4, IDAE 1, BOE 1, BOA 0) · prefiltro común
   > `retain=34, ambiguous=7, hold_manual=75, reject=800` · previsión 81
   > análisis, 2,0736 USD.

   Ese recuento **no es un invariante fijo**: la ventana deslizante de BDNS lo
   mueve por causas externas. Ante un desvío, mirar salud de fuentes y registros
   de exclusión antes que el código (43.3).

### 53.5. Lo que queda en el script, y por qué

Solo dos cosas, las dos por decisión: la **matriz de reglas** previa a Claude
(526 líneas, punto 8 del backlog, sesión propia y no encadenada a otra tarea sin
que el usuario lo pida) y **`run_pipeline()`**, que va el último por definición.

## 54. Medir antes de arreglar, y la prueba de pago que corrigió su propio criterio, a 01/09/2026

**Esta es la sección de arranque en frío vigente.** Sustituye a la 53.

La sesión ejecuta el orden que fijó el usuario: `--gap-report`, prueba dirigida
de pago, consorcio, `--source`. Dos de los cuatro puntos terminaron en un sitio
distinto del previsto, y en los dos casos porque una medición contradijo lo que
se daba por supuesto.

### 54.1. Qué cambió hoy

| | Al empezar el 01/09 | Al cerrar |
|---|---|---|
| `Grant-Radar-prueba.py` | 2.203 líneas | **2.368** |
| Paquete `grant_radar/` | 40 módulos | **41 módulos** (12.708 líneas) |
| Pruebas | 575 | **614** |
| Puntos abiertos del backlog | 28 | **29** (cierra el 5, abre dos) |
| Producto publicado | JSON del 21/08 | el mismo: **sigue sin publicarse** |
| Gastado en API | — | **0,1271 USD** (dos pruebas dirigidas) |

### 54.2. El desfase ya no es teórico: tiene fecha

Lo primero que se midió, y cambia la urgencia de todo lo demás. El producto
publicado es del 21/08. A 01/09:

- **cuatro fichas** ya tienen el plazo vencido (el 31/08 eran tres);
- **doce** vencen en los siguientes catorce días;
- y entre ellas están **las tres de mayor encaje del catálogo** —fit 78, 75 y
  75, las tres `eligible`—, tres topics de Horizon que cierran el **15/09** y
  se publicaron con `budget_missing`.

Es decir: quien mira el panel ve las tres mejores oportunidades del año sin una
sola cifra de dinero, a dos semanas del cierre, cuando el arreglo que las
completa está hecho desde el 31/08 y sin publicar. **La ejecución completa deja
de ser «cuando convenga» y pasa a tener una fecha límite real**, en torno al
08-10/09, porque una propuesta de Horizon necesita margen.

### 54.3. `--gap-report`: convertir un método en un comando

`SUGERENCIAS.MD` 14 había dejado escrito que el recuento de campos ausentes por
fuente «cuesta cinco minutos y ha valido más que cualquier refactorización de
hoy». Seguía siendo un cálculo a mano. Ahora es `--gap-report`
(`grant_radar/gap_report.py`), sin red y sin coste.

Lee **dos orígenes**, y el segundo es el que hacía falta: el producto publicado
y **la caché de análisis**. Una prueba `--max-claude` guarda en caché y termina
sin publicar, así que sin leer la caché no había forma de comprobar una prueba
de pago sin volver a pagarla. Eso es exactamente lo que se hizo hoy.

Dos correcciones que el informe tuvo que aprender, ambas reales:

1. **Los huecos de producto se cuentan solo sobre las convocatorias vivas.**
   `_data_gap_reasons()` devuelve lista vacía en cuanto la decisión empieza por
   `discard_`, así que usar el total como denominador hacía parecer sana a BDNS,
   donde 33 de sus 46 fichas están descartadas.
2. **Se cuentan convocatorias, no menciones.** La primera ejecución publicó
   `funding_rate_percent 20/19` en Horizon —imposible—, porque el modelo repite
   a veces un campo dentro del mismo `missing_fields`. Hay una prueba que exige
   que ningún recuento supere jamás su denominador.

Los tres campos de TRL salen marcados como **ausencia aceptada**, para que
ningún recuento futuro reabra la decisión cerrada en 53.3.

### 54.4. La prueba dirigida de pago: 0,0916 USD

Autorizada expresamente por el usuario, con el comando de 53.2. Coste real
0,0916 USD frente a los 0,09 previstos. La convocatoria de Horizon salió como
debía, y es justamente una de las que cierran el 15/09:

| `HORIZON-CL5-2026-09-D4-08` | Publicado (21/08) | Tras la prueba |
|---|---|---|
| `budget_total_eur` | ausente | **18.000.000 €** |
| `grant_max_eur` | ausente | **9.000.000 €** |
| Elegibilidad | `unknown` | **`eligible`** |
| `consortium_required` | ausente | **`True`**, con cita literal |
| `data_gaps` | 3 | **0** |
| Encaje | 75 | **85** |

Los tres controles del 53.2 sobre el presupuesto pasan: las cifras **coinciden
con el `budgetOverview` oficial** (9 M€/proyecto, 18 M€ totales, 2 proyectos) y
**no se coló el presupuesto de un topic hermano**. La elegibilidad viene del
documento oficial, no de un catálogo tecleado; la cita que trajo el anexo fue
«at least three independent legal entities from different countries».

### 54.5. Lo que la prueba corrige de lo que dejamos escrito el 31/08

Tres cosas, y conviene que consten porque las tres eran suposiciones nuestras:

**1. El criterio de aceptación de 53.2 estaba mal formulado.** Pedía que los
**cuatro** campos económicos dejaran de faltar. Solo dos podían: `budgetOverview`
trae el importe por proyecto y el total, pero **no** trae `project_budget_eur`
—que es el coste del proyecto, no la ayuda— ni `funding_rate_percent`. Que sigan
ausentes **no es un fallo de extracción**: es la misma distinción que se cerró
con el TRL. El criterio correcto es **dos de dos**, no cuatro de cuatro.

**2. Falta un control por hacer.** El plan asumía tres patrones → tres
convocatorias. Pero `"Proyectos de I+D"` es poco específico y **coincidió con
7**; `--max-claude 3` tomó las tres primeras (1 Horizon + 2 CDTI) y dejó
**919481 sin analizar**. Se comprobó aparte, en la misma sesión y con
autorización expresa: **pasa** (sección **54.10**, 0,0355 USD). La lección que
queda es sobre el diseño de la prueba, no sobre el código: un `--claude-match`
poco específico gasta el presupuesto de `--max-claude` en convocatorias que no
son las que se querían mirar.

**3. La regla determinista de consorcio que se iba a escribir no debe
escribirse.** Era el tercer encargo de la sesión: `consortium_requirement_missing`
afectaba a 21 de las 77 fichas publicadas y la idea era resolverlo con una regla
sobre `types_of_action`. La medición lo desmiente: **3 de 3 análisis resolvieron
`consortium_required` correctamente**, leyendo el documento oficial. Codificar a
mano lo que ya se lee de la fuente sería el anti-patrón que este proyecto
descartó el 31/08. **Encargo cancelado por medición, no por falta de tiempo.**
Volver a medirlo con `--gap-report` tras la ejecución completa.

### 54.6. `--source`: recopilar una fuente en vez de ocho

Punto 5 del backlog, abierto desde la sección 35. Medido contra los 937 s de la
recopilación completa de hoy:

| | Tiempo | Ganancia |
|---|---|---|
| Recopilación completa | 937 s | — |
| `--source een` | 81,4 s | 11× |
| `--source boa` | 13,7 s | **68×** |

Las cuatro fuentes de HTTP puro (Horizon, BDNS, ECCP, EEN) se piden fuera del
bloque del navegador, así que verificar un cambio en ellas ya **no paga el
arranque de Chromium**: la salida lo dice explícitamente.

Dos salvaguardas, porque una selección parcial puede hacer daño callando:
**exige `--no-claude`** (un catálogo incompleto que llegara al análisis
publicaría un producto sin fuentes enteras) y **apaga la vigilancia de
programas recurrentes**, que con fuentes sin consultar daría por desaparecido
todo lo que vive en ellas. Además avisa en consola de que los recuentos no son
comparables con las cifras de referencia.

Las pruebas leen el propio script y comparan el mapa de alias con las fuentes
que el pipeline consulta: el riesgo real no es que la selección falle, sino que
un conector nuevo no aparezca en ella y nadie se entere.

### 54.7. Cifras de referencia a 01/09/2026

Sustituyen a las de 53.4. Verificación `--no-claude` completa, posterior a todos
los cambios de hoy:

> 920 detectadas · 34 duplicadas fusionadas · **82 vigentes** (BDNS 50,
> Horizon 20, CDTI 5, ECCP 4, EEN 4, IDAE 1, BOE 1, BOA 0) · prefiltro común
> `retain=34, ambiguous=7, hold_manual=75, reject=804` · previsión **79**
> análisis, **2,0224 USD**.

La previsión baja de 82 a 79 porque las tres de la prueba de pago ya están en
caché: no se volverían a pagar. Recordatorio de 53.4, que sigue vigente: **este
recuento no es un invariante fijo**; la ventana deslizante de BDNS lo mueve por
causas externas.

Orden de verificación, sin cambios respecto a 43.3:

1. `poetry run python -m unittest tests.test_grant_radar_script_names`
2. `poetry run python -m py_compile "Grant-Radar-prueba.py"`
3. `poetry run python -m unittest discover -s tests` — **614 pruebas**
4. `poetry run python "Grant-Radar-prueba.py" --no-claude`

### 54.8. Una lección de método sobre las ejecuciones en segundo plano

Al lanzar la prueba de pago se redirigió toda la salida a un archivo propio
(`> prueba_pago.log 2>&1`), con lo que la consola del usuario se quedó **sin
ver nada durante diecisiete minutos** y pareció que el proceso no existía. El
proceso estaba vivo y terminó bien, pero el usuario no tenía forma de saberlo.
**Al lanzar una ejecución larga en segundo plano, no redirigir la salida fuera
de donde el usuario la ve.** Vale doble para la ejecución completa, que dura más
y además cuesta dinero.

### 54.9. La prioridad, fijada por el usuario al cerrar el día

**Corrige lo que esta misma sección decía antes**, y conviene que quede escrito
con el error incluido, porque es el tipo de deriva que una sesión repite:

> «Ten en cuenta que la herramienta sigue en desarrollo, es importante recordar
> cuánto lleva sin actualizarse las convocatorias **pero el foco actual es
> depurar la herramienta y minimizar los fallos antes que hacer continuamente
> análisis de pago**.» (usuario, 01/09/2026)

La sesión había medido el desfase —cuatro fichas vencidas, tres topics de
máximo encaje cerrando el 15/09 sin cifras— y **convirtió esa medición en una
fecha límite**, empujando a publicar «antes del 08-10/09». La medición era
correcta; la conclusión, no. En una herramienta en desarrollo, publicar un
análisis de pago no es el objetivo: **es la recompensa de haberla depurado**.

Regla práctica para las próximas sesiones: **informar del desfase sí, convertirlo
en urgencia no.** `--staleness-report` lo da gratis y el panel ya lo enseña; con
eso basta. La decisión de pagar es del usuario y no necesita que se la empuje.

El próximo paso, en consecuencia:

1. **Trabajo gratis que reduzca fallos**, que es casi todo lo que queda: los 29
   puntos de la sección 36 —el 8 (extraer la matriz de reglas, sesión propia),
   los huecos de cobertura de 36.4, los catálogos curados que caducan en
   silencio (27 y 28), los umbrales de salud calibrados a ojo (30)— más
   `--gap-report` y `--source`, que ahora abaratan justamente eso.
2. **La ejecución completa (~2,02 USD sobre 79 convocatorias), cuando el usuario
   lo decida.** Requiere autorización expresa. Publica de golpe todo lo
   acumulado el 31/08 y validado el 01/09.
3. **Después de publicar, `--gap-report` otra vez**: es la comprobación de
   regresión de todo lo de hoy, y cuesta cero.

### 54.10. El control territorial que faltaba, ya hecho: 0,0355 USD

Autorizado expresamente por el usuario después de 54.5. `--max-claude 1
--claude-match 919481` — esta vez el patrón coincidió con **una sola**
convocatoria, que era el problema de la prueba anterior.

**Pasa, y limpiamente.** BDNS 919481, «Convocatoria de 2026 de ayudas para la
realización de proyectos de I+D+i», Comunidad Foral de Navarra:

| | |
|---|---|
| `eligibility` | **`ineligible`** |
| `decision` | `discard_ineligible` |
| **`review_required`** | **`False`** — no pide confirmación |
| `eligible_geographies` | `['ES22 - Comunidad Foral de Navarra']` |

Con esto, **los tres controles de 53.2 quedan ejercitados**, por 0,1271 USD en
total entre las dos pruebas dirigidas del día.

**Lo interesante está en el razonamiento, y confirma por qué la sección 49
importaba.** El modelo concluyó `ineligible` por su cuenta, pero su prosa titubea
de lo lindo:

> «…la línea *Proyectos competitivos - Modalidad individual* no especifica
> restricción geográfica explícita en los hechos extraídos, solo en metadatos
> generales. **Debe verificarse** si la restricción a Navarra aplica a todas las
> líneas o solo a algunas. […] Si la modalidad individual admite solicitantes de
> otras regiones, Kalfrisa **sería elegible** bajo esa línea específica.»

Ese «debe verificarse» es exactamente lo que la regla rota de antes del 31/08
leía para pedir confirmación manual, y es la causa de que 25 de 31 convocatorias
salieran «por confirmar» (sección 49). Ahora la regla decide sobre
`eligible_geographies` —el campo oficial, `ES22`— y el titubeo del modelo ya no
cambia nada: `review_required` sale `False`.

Dicho de otro modo: **el modelo no ha dejado de dudar; lo que ha cambiado es que
su duda ya no manda.** Conviene recordarlo antes de intentar «arreglar» el
prompt para que deje de hedgear: no hace falta, porque la decisión no depende de
cómo redacte.

Nota menor: la ficha sale con `fit_score` 72 pese a estar descartada. No es un
defecto — el encaje temático es real (proyectos de I+D+i industrial) y lo que
falla es el territorio. `descartada: True` y `discard_ineligible` impiden que
aparezca como oportunidad.

## 55. Un filtro que buscaba la palabra equivocada, y qué aportan los catálogos, a 01/09/2026 (tarde)

Ronda de depuración, en la línea de la prioridad fijada en 54.9. Sin coste: no
se llamó a la API.

### 55.1. El chip «Hornos», retirado

Estaba desierto. La cadena, medida de punta a punta:

1. `horn` lo produce **una sola** categoría técnica, `thermal_processes`, por un
   mapa determinista (`_compat_tags_for`), no por el modelo;
2. `thermal_processes` se disparó **0 veces** en las 77 fichas publicadas;
3. su vocabulario son 13 frases compuestas exactas (`horno industrial`, `kiln`,
   `calcinación`…) y **cero términos contextuales**.

Hay además un fallo real: `_term_present` exige la frase exacta, así que
**«hornos industriales» no casa con `horno industrial`**. Comprobado:
«modernización de horno industrial» → `horn`; «mejora de hornos industriales» →
nada. El español administrativo escribe en plural casi siempre.

**Pero ese no era el motivo, y aquí está la lección.** En los 288 documentos
oficiales de `bdns_document_cache.json`, «horno» aparece **tres veces**:

| Dónde | Qué es |
|---|---|
| Ayudas a talleres artesanos | electricidad de «maquinaria, herramientas, **hornos**» |
| La misma convocatoria | combustible para «**hornos**, maquinaria, herramientas» |
| Listado de municipios de Segovia | **ALDEHORNO** |

Ensanchar el vocabulario habría llenado el filtro de subvenciones a alfarería y
de un pueblo. La exigencia de compuestos no era un descuido: era lo que impedía
esa basura.

**El motivo de fondo es de diseño**: el chip filtraba por **equipo** mientras las
convocatorias se describen por **objetivo**. Las que sí financiarían un proyecto
de hornos no dicen «horno», dicen «descarbonización de procesos industriales», y
**ya están en el producto** bajo `ee` y `desc`. Por eso no podía funcionar por
muchos sinónimos que se le añadieran, y por eso se retira en vez de ampliarse.

`thermal_processes` pasa a mapear a `["ee", "desc"]`, como su hermana
`waste_heat`, para que si algún día se dispara la ficha caiga en un chip
existente en vez de quedarse sin ninguno. **`compat_aliases` solo alimenta el
campo público `tags`, no la detección**: verificado con `--no-claude`, el embudo
sale idéntico (`retain=34, ambiguous=7, hold_manual=75, reject=804`).

No se tocaron `BDNS_TECHNOLOGY_TERMS` (vocabulario de búsqueda de la matriz de
reglas) ni el mapa de colores de `build_keywords()`: comparten la palabra pero
no son el filtro.

**Queda abierto el fallo del plural**, que es real y afecta a vocabulario que sí
existe en las convocatorias: `recuperadores`, `intercambiadores de calor
industriales`, `tratamientos térmicos`. Es punto 40 del backlog. Ojo: tocarlo sí
ensancha `detect_tech_tags` y por tanto el embudo y el coste, así que hay que
medirlo antes.

### 55.2. Qué aportan los catálogos curados, medido

Pregunta del usuario. La respuesta reordena el backlog, y empieza por una
corrección: **el BOE no tiene catálogo curado**. `BOE_TRACKED_AUTHORITIES` es una
lista de cinco organismos a vigilar, no de convocatorias; el BOE se lee siempre
en vivo. Los dos catálogos curados son CDTI y BOA, y rinden al revés.

**CDTI: el catálogo aporta 4 de 5, el 80 %.**

> CDTI Playwright: 14 fichas comprobadas, 13 cerradas y **1** vigente
> → **4** convocatorias CDTI vigentes en catálogo curado
> CDTI combinado: **5** convocatorias únicas vigentes

Y son las que importan: las tres de ventanilla permanente (PID, Cervera,
Infraestructuras de Ensayo) más los Bilaterales, tres de ellas ya con sus
documentos oficiales desde 51.2. La razón es estructural: **el calendario
oficial publica convocatorias con fecha, y la ventanilla permanente no tiene
fecha**, así que no aparece ahí.

**Esto corrige el punto 27 del backlog**, que proponía estudiar si esas entradas
podían derivarse del listado oficial. La medición dice que probablemente no,
porque el calendario no las lista. El catálogo de CDTI no es deuda técnica que
retirar: es la única vía a cuatro de las cinco convocatorias de CDTI. **Lo que
necesita es revisión periódica, no sustitución.**

**BOA: el catálogo aporta 0, y la fuente entera también.**

> BOA Playwright: 0 convocatorias relevantes
> BOA: navegación en vivo sin resultados; activando catálogo estático
> → **0** convocatorias BOA cargadas desde el respaldo

Sus dos entradas están vencidas —Fondo de Transición Justa (05/05/2026) y PAIP
TDI-Feder (15/01/2026, marcada `✗ CERRADA` en el propio código)—, así que el
filtro las excluye a las dos. La fuente cuesta 8 s por ejecución y 198 líneas
para no aportar nada.

No es pérdida de cobertura: **Aragón se cubre desde la sección 26 por el filtro
`nivel1`/`nivel2` de `fetch_bdns()`**. BOA quedó como señal secundaria y hoy no
da señal. La recomendación registrada es **retirar el conector** (punto 28), pero
es decisión del usuario porque implica renunciar a una fuente.

### 55.3. Archivo propio para los dos conectores que faltaban

Punto 20 del backlog, que estaba desactualizado: decía cuatro conectores sin
archivo y solo faltaban **dos**, porque CDTI y Horizon lo ganaron en rondas
anteriores.

- **`tests/test_grant_radar_sources_bdns.py`, 20 pruebas.** BDNS aporta 50 de las
  82 vigentes —más que las otras siete fuentes juntas— y era el mayor sin
  archivo. Se prueba la **aritmética de fechas**, que es donde un fallo no se
  nota: un plazo mal calculado no rompe nada, solo publica como abierta una
  convocatoria cerrada. Días hábiles frente a naturales, números escritos con
  letra («quince días»), meses de calendario (31 de enero + 1 mes = 28 de
  febrero, y 29 en bisiesto) y la ventana de 45 días que evita fechar la
  convocatoria con una reedición posterior.
- **`tests/test_grant_radar_sources_een.py`, 17 pruebas.** Su fallo
  característico no es de red sino de ambigüedad: en una página de perfil
  conviven el enlace a la convocatoria y la web del socio que la busca, y
  publicar el segundo produce una ficha con URL que carga y no lleva a ninguna
  ayuda. Incluye que `callback` y `recall` no se confundan con `call`, y que un
  topic de Horizon descubierto vía EEN se atribuya a Horizon y no a EEN.

Nota de método: al escribir las de EEN, la primera versión daba por válido un
perfil con solo «Call details» y el conector lo rechazaba **con razón** —exige
además plazo futuro y enlace externo—. Se corrigió la prueba, no el código, y se
añadieron las tres ramas de descarte. Conviene dejarlo escrito: cuando una
prueba nueva falla contra código rodado, la hipótesis por defecto es que la
prueba está mal.

### 55.4. Estado y cifras

**651 pruebas** en verde (614 al empezar la tarde). Verificación `--no-claude`
completa idéntica a la referencia de 54.7: 920 detectadas, **82 vigentes**,
prefiltro `retain=34, ambiguous=7, hold_manual=75, reject=804`. Pendientes de
analizar **78** (~2,00 USD): baja de 79 porque la BDNS 919481 quedó en caché.

### 55.5. Lo siguiente: la matriz de reglas, en sesión propia

Decidido con el usuario. Es el punto 8 del backlog y lo único que queda del
orden de extracción junto a `run_pipeline()`: 526 líneas y siete niveles de
precedencia que deciden qué llega a Claude y, con ello, el coste. `AGENTS.md`
4.1 y 36.3 piden sesión dedicada y no encadenarla a otra tarea; el usuario lo ha
confirmado explícitamente.

## 56. BOA retirado con pruebas, y el plural medido, a 01/09/2026 (cierre)

Dos encargos, los dos con la misma forma: **comprobar antes de tocar**. El
primero condicionaba una retirada a que la comprobación saliera bien; el
segundo era solo medir. Sin coste: no se llamó a la API.

### 56.1. El conector BOA, retirado

El usuario puso la condición: retirar solo si el filtro `nivel1`/`nivel2` de
`fetch_bdns()` encuentra por su cuenta las convocatorias que el catálogo de BOA
mantiene a mano —el PAIP entre ellas—, porque eso probaría que no hace falta
teclearlas. Se comprobó y se cumple, por dos vías independientes:

**1. La vigilancia de programas recurrentes ya lo decía.** En el registro de la
auditoría, para la ejecución del 01/09:

```
key: paip_aragon · status: active_captured · matches: 12 · sources: ["BDNS"]
```

Doce coincidencias, todas de BDNS, ninguna de BOA. La sonda que existe para
avisar cuando un programa recurrente **desaparece** estaba diciendo lo
contrario: que este se captura de sobra sin el catálogo.

**2. La caché documental lo confirma con el texto oficial.** Sobre los 291
documentos de `bdns_document_cache.json`:

| Búsqueda | Documentos |
|---|---|
| `PAIP` | 1, con el texto oficial del «Programa de Ayudas a la Industria y la pyme en Aragón» |
| `Transición Justa` | **24** |
| `Teruel` | 4, incluida la tabla de intensidades de ayuda por provincia (Teruel 70/60/50 %) |

Las dos entradas del catálogo de BOA —Fondo de Transición Justa de Teruel y PAIP
TDI-Feder— son por tanto materia que BDNS ya trae, con su documentación.

Sumado a lo medido en 55.2 —BOA aporta **0 por sus dos vías**: el scraper en vivo
no encuentra nada y sus dos entradas estáticas vencieron el 05/05/2026 y el
15/01/2026—, la condición se cumple y el conector se retira.

**Verificado después de retirarlo:** 919 detectadas, **82 vigentes**, las mismas
que antes. Prefiltro `retain=34, ambiguous=7, hold_manual=75, reject=803`.
**Cobertura perdida: cero.** (Las 919 frente a 920 y el 803 frente a 804 son la
ventana deslizante de BDNS, no el cambio.)

Piezas retiradas: el módulo (198 líneas), su archivo de pruebas, el import, el
alias `--source boa`, el bloque de recolección, la etiqueta de fuente de
`public_output.py`, el comentario de `browser.py` («cuatro conectores» → tres) y
la entrada de los datos de demostración del frontend. Cuatro pruebas que lo
citaban como ejemplo pasan a citar fuentes vivas.

**El proyecto pasa de ocho fuentes a siete.** Conviene decirlo así en cualquier
descripción del sistema, porque «8 fuentes oficiales» aparece en varios sitios.

Nota de método: `test_grant_radar_script_names` falló al instante señalando
`fetch_boa`, antes de que la suite completa tuviera ocasión de presentarlo como
un error en pruebas de otra cosa. Es la tercera vez que esa prueba paga su
coste (secciones 29, 35 y esta).

### 56.2. El plural en `_term_present()`, medido

Punto 40 del backlog, abierto en 55.1. La pregunta era si arreglarlo ensancha el
embudo lo bastante como para que importe. **No lo hace.**

Simulación sobre 368 textos reales —291 documentos oficiales de BDNS más las 77
fichas publicadas— parcheando `_term_present()` en memoria para que cada palabra
del término admita sufijo de plural (`-s` / `-es`):

| | Antes | Después |
|---|---|---|
| Textos que pasan `is_relevant()` | 35 | **36** |
| Textos que **pierden** relevancia | — | **0** |

| Categoría técnica | Antes | Después |
|---|---|---|
| `waste_heat` | 9 | **10** |
| `thermal_processes` | 0 | **1** |
| Las otras seis | — | sin cambio |

**Impacto en el embudo: +1 de 368.** Extrapolado a la recopilación completa,
entre uno y tres análisis más: del orden de 0,03-0,08 USD por ejecución completa.

**Y las dos ganancias son aciertos, no ruido.** Es lo que decide el asunto:

1. «Recuperación de **calores residuales**» — plural de `calor residual`. Es
   literalmente el negocio central de Kalfrisa, y hoy se pierde por una «s».
2. «**High-temperature processes**, by innovative technologies for electrified
   and hybrid high-temperature…» — un topic de Horizon sobre procesos de alta
   temperatura.

Ni un falso positivo en los 368 textos, y ninguna pérdida. El riesgo que se
temía en 55.1 —que ensanchar la detección disparara el coste— **no se
materializa**, porque el vocabulario es específico: admitir el plural de
«intercambiador de calor industrial» no abre la puerta a nada genérico.

**Queda medido y sin implementar**, porque el encargo era medir. La
recomendación registrada es aplicarlo: coste marginal despreciable, dos aciertos
recuperados y uno de ellos en la tecnología central del cliente.

Un matiz para quien lo implemente: el sufijo `(?:e?s)?` cubre el plural pero no
el género («térmico» → «térmicas»). Ampliarlo a género exigiría medir otra vez,
porque ahí sí empieza a haber riesgo de sobrecoincidencia.

### 56.3. Estado

**646 pruebas** en verde (651 antes; las cinco que faltan son las de BOA).
Verificación `--no-claude` completa: 919 detectadas, **82 vigentes**, siete
fuentes. Pendientes de analizar 78 (~2,00 USD). Coste de la ronda: **0 USD**.

Lo siguiente, confirmado por el usuario: **la matriz de reglas, en sesión
propia** (punto 8 del backlog; ver 55.5).

## 57. La matriz de reglas, extraída: se acaba la modularización, a 01/09/2026 (noche)

Sesión dedicada, como pedían `AGENTS.md` 4.1 y 36.3 y como confirmó el usuario.
Punto 8 del backlog, y con él **el orden de extracción medido en las secciones
37 y 38 queda cerrado**. Sin coste: no se llamó a la API.

### 57.1. El criterio de aceptación, cumplido

Una extracción no puede cambiar comportamiento. El criterio era que el embudo
saliera idéntico, y sale **dígito a dígito**:

| | Antes | Después |
|---|---|---|
| Prefiltro común | `ambiguous=7, hold_manual=75, reject=803, retain=34` | **igual** |
| Detectadas | 919 (34 fusionadas) | **igual** |
| Vigentes | 82 | **igual** |
| Por fuente | BDNS 50, Horizon 20, CDTI 5, ECCP 4, EEN 4, IDAE 1, BOE 1 | **igual** |

### 57.2. El bloque era más limpio de lo que temíamos

Se analizó con AST antes de mover una línea, y conviene que conste porque la
documentación llevaba meses describiéndolo como la pieza más delicada:

- **774 líneas**: 27 constantes de vocabulario y 6 funciones;
- **cero dependencias de globales del script**. Todo lo que usa ya venía de
  módulos de `grant_radar/` (`bdns_fields`, `call_text`, `deterministic_rules`,
  `parsing_helpers`, `profile_scope`, `tech_taxonomy`) o de la stdlib;
- **solo `run_pipeline()` la usa**, y solo dos de los seis nombres:
  `_bdns_intrinsic_exclusion` y `deterministic_prefilter`;
- **ningún módulo del paquete la importa.** Un `grep` daba ocho módulos, pero
  todas eran menciones en comentarios salvo dos claves de diccionario;
- **sin ciclos de import**: el grafo es un DAG con raíz en `parsing_helpers`.

La razón de que fuera tan limpio no es suerte: **`holds.py` y el conector ECCP
la reciben inyectada como parámetro**, y esa decisión se tomó en su día
precisamente para poder hacer esto. La apuesta se cobra hoy — extraer la matriz
no obligó a tocar ni el dominio de holds ni el conector.

Lo delicado de la matriz, entonces, nunca fue su acoplamiento: era **lo que
decide**. Sigue siéndolo, y por eso el módulo nuevo abre con los siete niveles
de precedencia y con la disciplina obligatoria para tocar cualquier condición
(ampliar antes `tests/fixtures/bdns_filter_cases.json`).

### 57.3. Dos avisos del backlog, y uno se ganó el sueldo

- **Punto 16: cortar por `node.end_lineno`, nunca por `max(lineno)`.** Respetado,
  y además con tres aserciones de frontera antes de escribir nada. **Una falló**
  —la expectativa sobre la última línea del bloque era errónea— y abortó sin
  tocar los archivos. Ese es exactamente el fallo que el punto 16 describe, y
  esta vez no llegó a producirse.
- **Punto 21: `test_grant_radar_script_names` antes que la suite completa.**
  Respetado.

### 57.4. Qué queda en el script

**Cuatro funciones**, y ninguna es lógica de dominio:

| Función | Qué es |
|---|---|
| `run_pipeline()` | el orquestador |
| `parse_args()` | las banderas de línea de comandos |
| `build_gap_reports()` | reúne los dos orígenes de `--gap-report` |
| `publish_collection_state()` | ayudante de publicación del estado |

El script pasa de **2.362 a 1.595 líneas**; el paquete, a **41 módulos** y 13.345
líneas. Recordatorio del punto de partida: el script tenía **9.199 líneas** antes
de las nueve rondas del 19/08/2026.

**El script ya es lo que el proyecto perseguía: configuración, punto de entrada y
orquestación.** Con eso se cumple la condición que el punto 10 del backlog ponía
para revisar el patrón `runpy` + fusión de `APP` en `tests/test_grant_radar.py`:
ya tiene sentido plantearlo. No se hace aquí porque sería mezclar dos cosas en
una sesión, que es justo lo que esta sección ha evitado.

### 57.5. Estado

**646 pruebas** en verde. Se añadió `bdns_rules` al bloque de fusión de `APP`
para las 46 pruebas que alcanzan estos nombres, y se corrigieron seis
comentarios de otros módulos que decían «sigue en `Grant-Radar-prueba.py`» y
habían dejado de ser ciertos.

Cifras de referencia sin cambios respecto a 56.3: 919 detectadas, 82 vigentes,
78 pendientes de analizar (~2,00 USD).

## 59. Medir donde hay luz, y otras tres cosas, a 02/09/2026

Cuatro encargos del usuario. El primero produjo el error de método más caro de
la sesión y conviene que abra la sección, porque la lección no es sobre el
plural sino sobre cómo se mide.

### 59.1. La lección: medí donde había luz, no donde estaba el riesgo

Se propuso aplicar el plural en `_term_present()` con esta estimación, dada dos
veces y con confianza: **«+1 texto de 368, 0 falsos positivos, ~0,03 USD»**.

La realidad al aplicarlo: **+8 convocatorias y +0,23 USD**, y casi todas basura
—infraestructura cuántica, mundos virtuales, plataformas de software de
automoción—.

**Falló el método, no el código.** La medición se hizo sobre el corpus que había
en disco: 291 documentos de BDNS y las 77 fichas publicadas. **Horizon no estaba
ahí**, porque sus descripciones se descargan en vivo y no se guardan. Y los
topics de Horizon están en inglés y llenos de plurales, que es exactamente lo
que el cambio tocaba.

> **Regla para la próxima vez: un cambio que toca la clasificación debe medirse
> sobre el corpus que el pipeline procesa de verdad, no sobre el que resulta
> cómodo tener a mano.** Si una fuente no está en la muestra, la medición no
> dice nada sobre ella. Cuesta cinco minutos más llamar al conector.

### 59.2. La causa concreta: una sigla que significa dos cosas

`rto` pasó a casar con **«RTOs»**. En el vocabulario de Kalfrisa `RTO` es un
*Regenerative Thermal Oxidizer* —tratamiento de emisiones—; en la letra pequeña
de Horizon, «RTOs» son las *Research and Technology Organisations*, y aparecen
en casi todos los topics («Universities, RTOs and SMEs are encouraged to…»).
Cinco coincidencias arrastrando ocho convocatorias.

**El propio código lo había advertido.** El docstring original de
`_term_present()` decía, literalmente: «evita falsos positivos de siglas: RTO no
debe casar con demonstration». El guardián de límites lo impedía; pluralizar sin
más lo reabrió por otra puerta. Que un aviso esté escrito no basta si quien
cambia el código lo lee como una anécdota y no como una restricción.

**Arreglo:** `PLURAL_MIN_LENGTH = 3`. Las palabras de tres letras o menos no se
pluralizan, porque en este vocabulario **son todas siglas** (`rto`, `voc`,
`cov`, `cfd`) **o partículas** (`de`, `of`, `en`, `del`). Comprobado sobre el
vocabulario real, no supuesto.

Al nivel del conector Horizon: **30 exacto → 37 con el plural sin guardia → 32
ahora**, y las únicas coincidencias que el plural añade ya son legítimas:
`digital twins` y `high-temperature processes`.

### 59.3. El balance honesto del plural

| | Exacto | Plural sin guardia | Plural corregido |
|---|---|---|---|
| Vigentes | 82 | 90 | **84** |
| Horizon | 20 | 28 | **22** |
| `retain` | 34 | 43 | **38** |
| Coste | 2,00 USD | 2,23 | **2,07** |

Entran dos convocatorias de Horizon y **no sale ninguna**: «Advanced
manufacturing for key products (Made in Europe)», plausible para una PYME
industrial, y «Next-generation battery concepts», marginal.

**El beneficio es más modesto de lo que se dijo al proponerlo.** El caso que se
usó para justificarlo —«recuperación de calores residuales», el negocio central
del cliente— **no añade ninguna convocatoria**: BDNS sigue en 50. Su efecto está
en la clasificación de convocatorias que ya entraban, que es real —mejores
`tech_tags`, mejor preselección de socios— pero mucho menos vistoso que como se
vendió. Conviene dejarlo escrito para que nadie herede una expectativa inflada.

### 59.4. Los colores del panel, derivados en vez de tecleados

`build_keywords()` tenía siete colores escritos a mano contra palabras
concretas, y **cuatro estaban muertos**: «hidrógeno», «hydrogen», «hornos
industriales» y «combustión limpia» no existen en `KEYWORDS`, que las escribe de
otra forma. Nunca podían coincidir, así que las palabras que de verdad se
publican —`decarbonisation`, `waste heat`, `heat recovery`— caían todas al color
por defecto y el panel se veía plano.

Ahora el color se deriva de la **categoría técnica**, así que no puede volver a
caducar: vocabulario nuevo en el JSON hereda el color de su categoría.

Cierra el punto 19 del backlog, que señalaba esta función como **la única sin
ninguna prueba**. Tenía un fallo. No es coincidencia y merece anotarse: donde no
hay pruebas, no es que no haya fallos, es que no se ven.

### 59.5. La tasa de financiación de Horizon, y otra imprecisión corregida

Se había escrito que el dato «ya está en los Anexos Generales que descargamos»
(punto 39). **Era falso, y solo se supo al ir a buscarlo.** Está en el mismo PDF,
pero en la página 32, y el extractor cortaba en 48.000 caracteres de los 124.411
del documento: descargábamos el 37 %.

Hecho: `max_chars` pasa a ser parámetro de `_hold_document_text()` —con el mismo
valor por defecto, así que nadie hereda un documento mayor sin pedirlo— y solo
los Anexos Generales suben a 130.000. Nueva sección `funding_rates`.

Verificado contra el documento oficial: **cuatro secciones**, con la lista de
tasas entera —«Research and innovation action: 100%», «Innovation action: 70%
(except for non-profit legal entities)»—. En un proyecto de 3 M€ esa diferencia
son **900.000 € que pone la empresa**, y hasta hoy el panel no lo decía.

Detalle que casi se escapa: hubo que **subir `ANNEXES_CACHE_VERSION`**. Sin eso,
las entradas escritas el 31/08 se habrían reutilizado durante los siete días de
`ANNEXES_REFRESH_DAYS` sin la sección nueva, y el cambio no habría hecho nada
sin que nada lo dijera.

### 59.6. Retirado el patrón `runpy` + fusión de `APP` (punto 10)

Resultó mucho más limpio de lo previsto: de los 85 nombres que las pruebas
pedían a `APP`, **81 ya vivían en módulos importables**. Solo `run_pipeline` y
`parse_args` obligan a mantener `runpy`, porque `Grant-Radar-prueba.py` no se
puede importar. Las **216 llamadas a `APP[...]` bajan a 4**.

El motivo no era estético: **esa fusión podía tapar un `NameError` real** del
script, inyectando justo el nombre que faltaba antes de probarlo (36.5). Pasó
tres veces. El hueco lo sigue cubriendo `test_grant_radar_script_names.py`, que
hace su propio `run_path()` con globals limpios y sin fusión: es la razón de que
se pueda quitar sin perder red.

### 59.7. La recopilación diaria, preparada

`scripts/Recopilacion diaria.ps1`, lista para registrar en el Programador de
tareas. **No llama a `poetry`**, y eso es deliberado: en una tarea programada el
`PATH` no es el de la sesión interactiva, y este equipo tiene una `VIRTUAL_ENV`
heredada que apunta al `.venv` de la carpeta original. Llamar directamente a
`.venv\Scripts\python.exe` esquiva las dos cosas. Escribe a un log rotado de 30
días y el comando de registro va comentado al final del propio archivo.

**Sobre automatizarlo en GitHub Actions**, que preguntó el usuario: técnicamente
cabe —15 min/día, y el repositorio es público, así que los minutos son
ilimitados—, pero **el riesgo no es la capacidad de cálculo sino la IP**. Los
runners salen por rangos de Azure compartidos, y estas fuentes ya han enseñado
que vigilan: `boe.es` devolvió 429 tras ocho ejecuciones en un día desde la IP
local. Lo probable es un bloqueo intermitente, que es la peor variante porque
parece un fallo del código. Recomendación registrada: **empezar en local**, y si
se quiere, montar Actions en paralelo una semana y comparar recuentos antes de
migrar.

### 59.9. La solución intermedia acordada: un `.bat` de doble clic

Decidido con el usuario el 02/09/2026. **Hasta alojar la herramienta en un
servidor —previsto para dentro de unos meses—**, la recopilación diaria se
lanza a mano con `scripts/Grant-Radar diario.bat`: abre VS Code con el proyecto
y ejecuta `--no-claude` en la misma ventana. El análisis con Claude **sigue
siendo manual y discrecional**, y ningún script lo lanza.

Tres decisiones del archivo que no son evidentes y conviene no deshacer:

1. **No llama a `poetry`, llama a `.venv\Scripts\python.exe`.** En una tarea
   programada el `PATH` no es el de la sesión interactiva, y este equipo tiene
   una `VIRTUAL_ENV` heredada que apunta al `.venv` de la carpeta original.
2. **`chcp 65001` al principio.** La salida del pipeline lleva acentos y `✓`;
   sin eso `cmd` los destroza.
3. **VS Code se abre con `start`, no llamando a `code`.** `code` es un shim
   `.cmd`: invocarlo directo desde un `.bat` se lleva por delante el proceso
   padre y la recopilación no llegaría a ejecutarse.

Y un fallo clásico de `.bat` que apareció al escribirlo: la marca de tiempo del
log se calculaba **dentro** de un bloque `if`, donde `cmd` expande las variables
al parsear el bloque entero y por tanto salía vacía. Se sacó fuera.

Probado de verdad antes de darlo por bueno, con una copia que sustituía
`--no-claude` por `--staleness-report` —el mismo script, cinco segundos— para
ejercitar todo el flujo sin esperar quince minutos: argumentos, rutas, acentos,
el *tee* de `/log` y los dos caminos de salida.

`grant_radar_data/logs/` queda en `.gitignore`: son para diagnosticar una
ejecución concreta, y el historial que importa vive en la auditoría.

### 59.8. Estado

**666 pruebas** en verde (646 al empezar). Verificación `--no-claude`: 921
detectadas, **84 vigentes**, prefiltro `retain=38, ambiguous=5, hold_manual=75,
reject=803`. Pendientes de analizar **81** (~2,07 USD). Coste de la sesión en
API: **0 USD**.

## 60. Una identidad que aguante, y lo que se pudo construir encima, a 02/09/2026 (tarde)

Dos encargos del usuario —mejorar el backend y poner favoritos en el panel—
que resultaron ser el mismo encargo, porque los dos tropezaban con una pieza
que no existía. Sin coste: **no se llamó a la API**.

### 60.1. Qué cambió hoy

| | Al empezar | Al cerrar |
|---|---|---|
| Pruebas | 666 | **711** |
| Paquete `grant_radar/` | 41 módulos | 41 (ninguno nuevo; crecen seis) |
| Puntos abiertos del backlog | 29 | **27** (cierran el 11 y el 38) |
| Producto publicado | JSON del 21/08 | el mismo: **no se ha pagado nada** |
| Archivos nuevos | — | `scripts/favoritos-worker/` (3) |

### 60.2. El `id` publicado era un contador posicional, y eso bloqueaba todo

`_assemble_public_record()` recibía `len(enriched) + 1`, asignado **después** de
ordenar por encaje. El id 42 de hoy y el 42 de la próxima publicación son
convocatorias distintas. Consecuencias, y la primera es la que importa:

- **unos favoritos guardados contra `id` habrían señalado, tras publicar, a la
  convocatoria equivocada — y en silencio**, que es el tipo de fallo que este
  proyecto persigue (36.5);
- nada externo al JSON podía referirse a una convocatoria: ni un enlace
  profundo, ni una nota, ni un «esto ya lo miramos».

La identidad estable **ya estaba escrita** desde el 31/08: `_identity()`, en
`product_watch.py`, que usaba la comparación de productos. Medida antes de
usarla, sobre el `convocatorias.json` publicado: **77 de 77 únicas, cero
colisiones** (67 resuelven por `identifier`, 10 caen a `url`). No había que
inventar nada, había que exponerlo. Es ahora `stable_identity()`, pública, y
cada ficha publica `stable_key` (esquema público **4**).

**Una sola implementación en Python, a propósito.** Publicar la clave por un
lado y compararla por otro invita a que las dos se separen sin que nadie lo
note, que es justo el fallo que la función existe para evitar.

### 60.3. Cuatro afirmaciones del plan que el código desmintió

El plan se escribió leyendo la documentación. Verificarlo contra el código
cambió cuatro cosas, y **las cuatro habrían fallado en silencio**.

**1. `stable_identity(conv)` no da la clave publicada.** `conv["url"]` no es la
url del JSON: `_normalize_public_url()` la reescribe —añade el esquema a un
dominio que no lo trae— y puede vaciarla. Para las **diez** fichas que resuelven
su identidad por url, calcular la clave sobre el `conv` crudo produciría una
cadena que no coincide con la que `compare_published_products()` calcula después
leyendo el archivo. De ahí `public_stable_key()`, en `public_output.py`: aplica
la normalización y delega. Vive ahí y no en `product_watch` porque ese módulo es
una hoja del grafo de imports, y meterle esta dependencia crearía un ciclo.

**2. Los favoritos habrían nacido muertos.** `--no-claude` **no regenera**
`convocatorias.json`, así que `stable_key` no llegaría al producto hasta la
próxima ejecución de pago — y la prioridad fijada por el usuario es no pagar. El
panel deriva la clave él mismo cuando falta (`deriveStableKey()`), con la misma
regla. Así los favoritos funcionan **hoy**, contra el JSON del 21/08, y las
claves coinciden exactamente cuando el backend empiece a publicarlas: el `url`
del JSON ya viene normalizado, que es lo que hace `public_stable_key()`.

Que haya dos implementaciones de una identidad es exactamente lo que 60.2 dice
que hay que evitar. La red es una prueba de Playwright que ejecuta
`deriveStableKey()` sobre el `convocatorias.json` real y compara los 77
resultados con los de `stable_identity()`. **Es lo único que impide que se
separen**, y por eso conviene no borrarla por lenta.

**3. La fase del aviso diario no podía reutilizar `compare_published_products()`.**
Calcula bien la diferencia de conjuntos, pero compara producto contra producto.
Sobre la recopilación cruda —que no ha pasado por Haiku y no tiene `summary`, ni
`objeto_y_actuaciones`, ni `eligible_actions`— habría marcado esos tres campos
como «vaciados» en las **77** fichas, y el aviso diario abriría con una regresión
inventada. Hay una prueba que lo demuestra en las dos direcciones: que la función
nueva no lo hace y que la vieja sí lo haría.

**4. La priorización ordenaba por un campo que todavía no existe.** `tech_tags`
sale del análisis: antes de llamar a Claude no está. El equivalente disponible es
`keywords_found`, que ponen los siete conectores.

### 60.4. Los favoritos compartidos

Estrella en cada tarjeta y en el detalle, chip `★ Favoritos (N)` junto a los de
temática, nota por favorito y quién lo marcó. Endpoint propio en
`scripts/favoritos-worker/` (Cloudflare Worker + KV), decidido con el usuario.

**La decisión de diseño que importa: una clave de KV por favorito**, no un JSON
único. Con un blob compartido, dos personas que marcan a la vez leen la misma
lista, cada una añade lo suyo y la segunda escritura pisa a la primera: un
favorito desaparece y nadie se entera. Con una clave por favorito, alta y baja
son escrituras independientes y el conflicto no llega a existir.

**La clave viaja en la query string, no en la ruta.** Las claves de las diez
fichas que se identifican por url llevan `https://…` con barras dentro; un `%2F`
en un path es terreno de normalización de proxies, y una query string no se
normaliza nunca.

**Sobre la seguridad, y conviene que quede escrito antes de que alguien la dé por
segura:** la URL del Worker viaja en el código de una página pública, en un
repositorio público. La comprobación de origen y los topes son **badenes contra
el paso casual, no seguridad** — quien quiera saltárselos solo necesita `curl`.
Para una lista interna de convocatorias sin datos personales es una compensación
razonable. Si algún día hay que cerrarla de verdad, el sitio es el servidor
propio previsto para dentro de unos meses (59.9), no este Worker.

**Tres detalles que no son evidentes y conviene no deshacer:**

1. `FAVORITES_ENDPOINT` vacío significa **modo local** (`localStorage`). No es
   una alternativa descartada: es el respaldo al que el panel cae solo si el
   Worker no responde, y el chip lo dice —«Favoritos (sin conexión)»— en vez de
   aparentar normalidad. Un endpoint caído nunca rompe el panel.
2. **Un favorito con el plazo vencido sigue viéndose** bajo el filtro de
   favoritos, atenuado y con la etiqueta «Plazo vencido». `getFiltered()`
   descarta todo lo vencido en cualquier otro caso; aquí la excepción es
   deliberada, porque que una convocatoria marcada a mano desaparezca sin avisar
   es peor que verla caducada.
3. El chip **no pasa por `setFilter()`**, que es excluyente dentro de su grupo:
   lleva su propio conmutador para poder combinarse con fuente, temática y
   búsqueda a la vez.

Gratis por arrastre: las descargas XLSX/CSV exportan `getFiltered()`, así que
«filtrar por favoritos y descargar» funcionó sin tocar el exportador.

**Cómo se comprobó que las pruebas no son decorativas.** Dos mutaciones
deliberadas, revertidas después: cambiar `favorites.has(c.stable_key)` por
`c.id` hace fallar la prueba del ciclo de marcado, y mover la clave de la query
string a la ruta hace fallar la del camino compartido. Una prueba que no falla
al romper lo que vigila no vigila nada.

**Hueco declarado:** `worker.js` es JavaScript desplegado fuera del repositorio y
**la suite de Python no lo ejecuta**. Se cubre con tres `curl` documentados en su
`README.md`, más la prueba a dos navegadores. No se finge que haya regresión
automática donde no la hay.

### 60.5. El aviso diario ya dice qué ha cambiado, no solo cuánto costaría

`compare_collection_against_product()`, en `product_watch.py`, y **una** cifra
más en `estado_recopilacion.json` (esquema **2**): `new_since_publication`.

Solo una, y esa restricción la puso una prueba. La primera versión metía además
`expiring_soon`, `expired` y una muestra con el título y la fecha de tres
convocatorias publicadas. `test_it_does_not_repeat_the_published_product` falló,
y **tenía razón**: eso es el producto, y ese archivo existe justamente para no
repetirlo. El panel ya tiene `convocatorias.json` cargado y deriva esas dos
cifras por su cuenta. Subir el tope del guardián de 9 a 14 y seguir habría
convertido la prueba en un trámite; subió a 10, por un solo campo, y ganó de paso
una comprobación que no tenía —que ningún valor del estado sea una lista—.

Las nuevas van etiquetadas **«detectadas, sin analizar»**, en consola y en el
panel. Han pasado el filtro determinista, no el de Haiku, y confundir las dos
cosas sería vender como oportunidad lo que aún no se ha evaluado.

Medido en la ejecución de hoy: *13 sin publicar · 13 publicadas cierran en 14
días o menos · 4 publicadas ya vencidas · la primera en 2 días.*

### 60.6. `--max-claude` ya prioriza por urgencia, no por orden de llegada

`prioritize_claude_candidates()`, en `claude_selection.py`. Antes, truncar se
quedaba con las N primeras **en el orden en que respondieron las fuentes**. El
efecto se vio el 01/09: `--max-claude 3` con un patrón poco específico gastó el
presupuesto en tres convocatorias que no eran las que se querían mirar (54.5).
Aquello se anotó como lección sobre el diseño de la prueba; como comportamiento
del producto es otra cosa, porque convierte una ejecución parcial barata en un
sorteo.

Cuatro criterios previos al análisis y un desempate: veredicto del prefiltro
(`retain` antes que `ambiguous`), cierre más próximo, más palabras clave, mayor
puntuación, y **identidad estable** para que el orden sea reproducible. Sin ese
último, dos candidatas iguales en lo demás cambiarían de sitio según cómo las
devolviera la fuente, y una prueba `--max-claude N` dejaría fuera una distinta
cada vez.

Dos decisiones concretas: **sin fecha de cierre se va al final, no al principio**
—no se puede decir que urja lo que no se sabe cuándo cierra—, y la ordenación
vive en `build_claude_analysis_selection()`, no en quien trunca, para que
`--no-claude` enseñe **el mismo orden** que usará la ejecución de pago. En sitios
distintos, revisarlo gratis dejaría de significar nada.

`--no-claude` imprime ahora las quince primeras con su veredicto, sus días y sus
palabras clave. Es la revisión gratuita que exige 59.1: **medir sobre lo que el
pipeline procesa de verdad**. Salida real de hoy, con las tres primeras:

```
   1. [retain   ] [   8 d] [ 0 kw] EEN            Eurostars Call 11 …
   2. [retain   ] [  13 d] [ 4 kw] HORIZON EUROPE Full-scale demonstration of heat upgrade …
   3. [retain   ] [  13 d] [ 2 kw] HORIZON EUROPE R&I in Support of the Clean Industrial Deal …
```

**Una observación honesta al verlo funcionar:** muchas candidatas salen con
`0 kw`, así que en la práctica el tercer criterio desempata poco y **manda el
plazo**. No es un fallo —el orden resultante es el que se quería—, pero conviene
no vender `keywords_found` como si estuviera decidiendo.

Lo que abre: análisis parciales con sentido. «Las 20 más urgentes» ≈ 0,51 USD
frente a 2,12 USD por las 83.

### 60.7. Punto 38: la tercera vía existía, y por poco se defiende mal

`boletin.dpz.es` —el Boletín Oficial de la provincia de Zaragoza, la de la propia
empresa— fallaba con `CERTIFICATE_VERIFY_FAILED` en dos edictos, y era **el único
host que fallaba** de toda la recopilación. El backlog lo planteaba como una
elección entre añadir un paquete de CA que hay que mantener y relajar la
verificación TLS, que contradice `_is_safe_public_https_url()`.

**Lo medido, en dos pasos, y el segundo casi no se da.**

Primero: el servidor envía **un solo certificado**, el suyo, sin el intermedio
que completa la cadena. OpenSSL —`requests`— no puede verificarlo. Chromium abre
las dos URLs con **HTTP 200** y devuelve el texto oficial del edicto, con su
identificador BDNS incluido.

Y aquí estaba la trampa: `PlaywrightBrowser` arranca su contexto con
`ignore_https_errors=True`. Con esa medición **no se puede distinguir «Chromium
completa la cadena» de «Chromium ignora el error»**, y la diferencia lo es todo:
si fuera lo segundo, el «tercer camino» sería la misma relajación de TLS que el
backlog descarta, con otro nombre. Se volvió a medir forzando las dos
configuraciones:

```
ignore_https_errors=False  ->  HTTP 200
ignore_https_errors=True   ->  HTTP 200
```

**Que la primera línea diga 200 es todo el argumento**: Chromium verifica de
verdad, porque va a buscar por su cuenta el certificado intermedio que el
servidor omite —algo que OpenSSL no hace—. No se relaja nada; se usa un cliente
que verifica mejor.

Por eso `VerifyingDocumentBrowser` (en `browser.py`) **no reutiliza
`PlaywrightBrowser`**: crea su propio contexto con `ignore_https_errors=False`.
Reutilizar el otro habría dejado el código relajando la verificación aunque no le
hiciera falta, y la frase anterior habría dejado de ser cierta.

Cuatro decisiones más, todas por algo:

- **Arranca perezosamente.** Si ningún documento falla —lo normal—, Chromium no
  se inicia y no se paga nada. BDNS se recopila fuera del bloque del navegador y
  el de las fuentes ya está cerrado cuando se descargan estos documentos.
- **`status()` antes que `html()`.** `html()` devuelve algo tanto ante un 404
  como ante un bloqueo de WAF; sin comprobar el código, la página de error de un
  portal entraría en la evidencia oficial como si fuera el documento.
- **Solo HTML.** Un PDF servido tras una cadena rota sigue perdiéndose. Hoy los
  dos afectados son HTML; si mañana son PDF, esto no los salva, y hay que saberlo.
- **Se inyecta**, como `intrinsic_exclusion` y `prefilter`, y el ciclo de vida se
  queda en el orquestador. El piloto y el replay no lo reciben a propósito: son
  herramientas de diagnóstico y no compensa que arranquen Chromium.

`_html_to_text()` se separó de `_hold_document_text()` para que las dos rutas
extraigan igual: un mismo documento no puede dar textos distintos según entre por
`requests` o por el navegador, o la caché documental guardaría una cosa u otra
según el día. Hay una prueba que compara las dos salidas.

**Verificado de punta a punta** con `--no-claude --source bdns` contra el
servidor real, no solo con dobles:

```
[WARNING] HTTP agotado para https://boletin.dpz.es/…idEdicto=894917…
          [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate
[INFO]    Chromium arrancado para un segundo intento de descarga
          (cadena de certificados incompleta en el origen)
  Documentos recuperados con el navegador: 2
```

Chromium arrancó **en el momento del fallo**, no antes, que era el diseño. Los
dos edictos están ahora en `bdns_document_cache.json` con `format:
"html_browser"` (4.581 y 3.403 bytes) y traen el texto oficial completo, con su
identificador BDNS —914771 y 908965— y su entidad publicadora. Cero caracteres
perdidos y los acentos intactos, comprobado explícitamente: el navegador no pasa
por el `errors="replace"` de la ruta de `requests`.

### 60.8. Un fallo que no estaba en el plan: una recopilación parcial publicaba el estado del día

Apareció al ir a verificar el punto 38 con `--source bdns`. El camino
`--no-claude` llamaba a `publish_collection_state()` **incondicionalmente**, así
que una selección de una sola fuente habría subido a GitHub Pages unas cifras que
describen esa fuente y el panel las habría enseñado como el estado **del día**:
«13 sin publicar» pasaría a «2» sin que nada lo dijera.

Es el mismo daño callado que ya evitaban las otras dos salvaguardas de `--source`
(54.6), y ahora son **tres**: exige `--no-claude`, apaga la vigilancia de
recurrentes y **no publica el estado diario**. La tercera tiene su prueba junto a
las otras dos.

Conviene anotar cómo apareció: no lo encontró una prueba ni una revisión, sino
**ir a ejecutar el comando de verificación y preguntarse qué escribía**.

Y la misma ejecución enseña por qué importaba. Sus cifras parciales fueron *51
pendientes · 1,3056 USD · 10 sin publicar* frente a las del día completo, *83 ·
2,1248 · 13*. Publicarlas habría dejado el panel diciendo que falta la mitad de
lo que falta, sin que nada lo indicara. La salida ahora dice:

```
  Estado de recopilación NO publicado: la selección es parcial (BDNS)
  y sus cifras no describen el día.
```

### 60.9. Punto 11: dos campos que se publicaban y nadie leía

`related_documents_count` (cuánta evidencia oficial respalda la ficha) y
`bdns_url` (enlace al registro oficial) entran en el detalle: ayudan a decidir y
ya estaban en el JSON, así que exponerlos no costó nada. Los otros tres
(`catalog_scope`, `catalog_category`, `catalog_ref`) son trazabilidad del
pipeline y se quedan donde están.

De paso salió el «ID» que el detalle enseñaba: era el contador posicional, así
que anotarlo no servía para volver a encontrar nada. Ahora enseña la identidad
estable, que es la que sí aguanta entre publicaciones.

### 60.10. Cifras de referencia a 02/09/2026 (tarde)

Sustituyen a las de 59.8. Verificación `--no-claude` completa, posterior a todos
los cambios:

> **922 detectadas** · 33 duplicadas fusionadas · **86 vigentes** (BDNS 52,
> Horizon 22, CDTI 5, ECCP 4, EEN 4, IDAE 1, BOE 1) · prefiltro común
> `retain=38, ambiguous=5, hold_manual=77, reject=802` · pendientes de analizar
> **83** (**2,1248 USD**).

Sube de 84 a 86 respecto a 59.8 por BDNS (50 → 52): es la ventana deslizante
moviéndose por causas externas, no una regresión (36.6, punto 26). Horizon se
mantiene en 22, que es la cifra que dejó el plural con guardia de siglas.

Orden de verificación, sin cambios respecto a 43.3:

1. `poetry run python -m unittest tests.test_grant_radar_script_names`
2. `poetry run python -m py_compile "Grant-Radar-prueba.py"`
3. `poetry run python -m unittest discover -s tests` — **711 pruebas**
4. `poetry run python "Grant-Radar-prueba.py" --no-claude`

### 60.11. Estado

**711 pruebas** en verde (666 al empezar). 41 módulos. Coste de la sesión en
API: **0 USD**. El producto publicado sigue siendo el del 21/08: **la decisión de
pagar es del usuario y esta sesión no la ha empujado**.

Queda una acción del usuario para que los favoritos sean de verdad compartidos:
desplegar el Worker (`wrangler deploy`) y pegar su URL en `FAVORITES_ENDPOINT`.
Hasta entonces funcionan en local, por navegador.
