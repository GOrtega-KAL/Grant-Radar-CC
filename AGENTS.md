# Grant-Radar — contexto e instrucciones del repositorio

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
  guiones no es válido para `import`. Lo que queda en él es la matriz de reglas
  previa a Claude (sección 4.1), los conectores CDTI y ECCP, el análisis con
  Haiku y la orquestación de `run_pipeline()`.
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
- JSON público/local del dashboard: `convocatorias.json`.
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
5 USD. Con la calibración vigente de 0,035 USD por convocatoria, el límite
económico es el efectivo y permite como máximo 142 análisis en una ejecución.

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

Calibración real del 03/08/2026 con Horizon e INNOVAE, muestra de dos casos:

- Coste observado por convocatoria: 0,0180-0,0350 USD.
- Coste central medio: 0,0265 USD.
- JSON inicial de unas 60 convocatorias: centro 1,59 USD y horquilla observada
  1,08-2,10 USD.
- Actualización de 1-5 convocatorias: centro 0,0265-0,1325 USD y horquilla
  observada 0,018-0,175 USD.

La muestra es pequeña. Recalibrar tras una ejecución completa. Incrementar
`max_tokens` no consume automáticamente el máximo: Anthropic factura los tokens
realmente procesados y generados.

Límite operativo autorizado el 11/08/2026:

- Máximo nominal: 200 convocatorias nuevas, modificadas o forzadas por ejecución.
- Máximo de coste superior estimado: 5 USD.
- Coste superior unitario usado por la barrera: 0,035 USD.
- Máximo efectivo actual: 142 convocatorias, porque 143 estiman 5,005 USD.
- Es una barrera presupuestaria previa basada en la calibración observada; no es
  una garantía contractual sobre la factura final de Anthropic.

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
  máximo efectivo vigente es 142. La ejecución se audita y termina antes de la
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
  cacheadas, siempre bajo la barrera de 142 análisis y 5 USD.
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
modularización conviene no mezclarlos: el recuento estable de 77 vigentes es el
invariante con el que se verifica cada extracción, y cambiar una regla lo haría
ambiguo.

### 36.2. Fragilidad frente a las fuentes

| # | Propuesta | Origen |
|---|---|---|
| 4 | Reintento con espera ante `HTTP 429` en `PlaywrightBrowser`, en vez de tratarlo como fuente caída | 35 |
| 5 | Modo de verificación por fuente (algo como `--no-claude --source BOE`) para no recorrer las ocho cuando un cambio solo toca una | 35 |
| 6 | Instantánea de la estructura esperada de cada fuente, comparada en cada ejecución, con historial | `SUGERENCIAS.MD` 3.4 punto 2 |
| 7 | Ejecución periódica automatizada en `--no-claude` solo para vigilar salud de fuentes | `SUGERENCIAS.MD` 3.4 punto 3 |
| 17 | Prueba de humo por conector: llamar a cada `fetch_*()` con el HTTP simulado y comprobar que recorre su camino sin `NameError` | 35. Habría cazado el `statistics` ausente en segundos en vez de en una recopilación de diez minutos |

El 429 del 19/08/2026 tuvo cooldown de minutos: una sonda de una sola petición,
7 minutos después, devolvió la página completa. No impone restricción horaria,
pero sí aconseja espaciar las ejecuciones completas cuando se encadenan varias
rondas el mismo día.

### 36.3. Modularización pendiente

| # | Qué falta | Notas |
|---|---|---|
| 8 | La matriz de reglas (`_bdns_pre_claude_gate()`, `deterministic_prefilter()`) | Sesión dedicada; es la lógica más ajustada del proyecto (siete niveles de precedencia, sección 4.1) |
| 9 | Motor de reglas genérico, declarativo | `SUGERENCIAS.MD` 3.3 punto 2. Requiere formalizar antes todas las variantes de condición existentes |
| 10 | Retirar el patrón `runpy` + fusión de `APP` en `tests/test_grant_radar.py` | Tiene sentido revisarlo cuando el script principal quede reducido a configuración y punto de entrada |
| 15 | Orden de extracción medido (secciones 37 y 38): `save_discovery_audit` → capa Haiku → segunda mitad de holds → reglas → `run_pipeline()` | La primera mitad de holds ya salió (sección 38). `run_pipeline()` arrastra el resto: va el último, no el siguiente |
| 21 | Ejecutar `tests/test_grant_radar_script_names.py` **antes** que la suite completa tras cada extracción | Señala el módulo y el nombre exactos en un segundo; la suite completa los presenta como errores en pruebas de otra cosa (pasó tres veces) |
| 16 | Usar `node.end_lineno`, nunca `max(lineno)`, al cortar bloques por AST | Un `return (` multilínea pierde el paréntesis de cierre; ocurrió en la sección 37 |

### 36.4. Huecos de cobertura de pruebas, medidos

Recuento sobre los 31 módulos del paquete a 19/08/2026:

| # | Qué | Detalle |
|---|---|---|
| 18 | `grant_radar/coverage_watch.py` no tiene **ninguna** prueba | Ni un solo test menciona `build_recurrent_coverage_watch()` ni `probe_missing_recurrent_coverage()`. Es el mecanismo que avisa cuando un programa conocido deja de aparecer: una red de seguridad que no tiene red |
| 19 | `build_keywords()` y `verificar_urls()` tampoco aparecen en ninguna prueba | Ambas afectan a lo que se publica: la primera al panel de palabras clave, la segunda a marcar URLs rotas |
| 20 | Sin archivo de test dedicado, aunque sí cubiertos de forma indirecta vía `runpy`: `sources/bdns.py`, `sources/cdti.py`, `sources/een.py`, `sources/horizon_europe.py`, `public_output.py`, `versions.py` | No es urgente —el camino principal de cada uno se ejercita en `tests/test_grant_radar.py`—, pero un archivo propio con import estándar hace la regresión más legible y sobreviviría a retirar el patrón `runpy` (punto 10) |

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
| 11 | Cinco campos que el backend publica y el frontend no consume (`catalog_scope`, `catalog_category`, `catalog_ref`, `related_documents_count`, `bdns_url`) | `SUGERENCIAS.MD` 2.8 |
| 12 | `requires-python = ">=3.11"` no se ha probado sobre un intérprete 3.11 real | `SUGERENCIAS.MD` 3.9 |
| 13 | Limpieza de `Obsoleto/` y `Frontend alternativo/` ahora que hay historial de git | `SUGERENCIAS.MD` 3.10 punto 2 |
| 14 | Rotación de credenciales si `API KEYs.txt` estuvo en copias compartidas fuera de control | `SUGERENCIAS.MD` 3.1 punto 4; solo el usuario puede confirmarlo |

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
3. `poetry run python -m unittest discover -s tests` —381 pruebas, el número
   solo puede subir.
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
