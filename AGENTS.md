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

- Backend principal en desarrollo: `Grant-Radar-prueba.py`. Sigue siendo el
  punto de entrada (`poetry run python "Grant-Radar-prueba.py"`) y el archivo
  donde vive la mayoría del código.
- Paquete `grant_radar/`: módulos extraídos del backend principal como parte
  de la división en curso (ver sección 21 y `SUGERENCIAS.MD` 3.2/3.3).
  `Grant-Radar-prueba.py` los importa con `from grant_radar.X import ...`.
  Antes de mover más código aquí, comprobar sus dependencias reales — no
  todo se puede extraer de forma aislada (ver nota sobre `cache/` y `rules/`
  en la sección 21).
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
- BOA Aragón: Playwright; catálogo estático como respaldo.
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
