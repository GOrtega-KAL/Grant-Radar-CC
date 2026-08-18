# Especificación de aceptación del filtro BDNS

Estado: matriz conectada al pipeline de producción y cubierta por pruebas
deterministas. `hold_manual` es un estado intermedio: el pipeline normal recupera
las bases, aplica reglas locales y convierte lo no resuelto en `ambiguous` para
el análisis general de Haiku. No requiere una decisión humana. Existe además un
piloto explícito y limitado que puede formular una sola pregunta factual por caso;
ese piloto sigue siendo diagnóstico y separado de producción.

## Objetivo

Reducir las convocatorias BDNS enviadas a Claude sin eliminar oportunidades en
las que Kalfrisa pueda financiar una inversión propia o participar formalmente
mediante un consorcio o un clúster. No se exige I+D: maquinaria, mejora de
procesos, ahorro energético, digitalización industrial y actuaciones ambientales
propias son positivas. Las ventas a beneficiarios ajenos quedan fuera aunque el
equipo de Kalfrisa sea gasto elegible.

## Salidas

- `retain`: entra en el análisis posterior.
- `hold_manual`: estado temporal mientras se recupera evidencia; nunca es una
  cola humana en producción.
- `reject`: exclusión determinista y auditable.

Toda oportunidad retenida tendrá un `opportunity_role`:

- `direct_beneficiary`: Kalfrisa puede solicitar la ayuda.
- `consortium_partner`: Kalfrisa es socio formal con actividad, costes o
  presupuesto propios.
- `cluster_route`: el clúster canaliza financiación, costes o un piloto ejecutado
  por Kalfrisa como empresa miembro.
- `unknown`: el papel no está demostrado.

No existe el papel `supplier`. Ser contratista, subcontratista o vendedor de un
beneficiario no constituye participación financiada directa.

## Precedencia de decisión

Las reglas se evaluarán en este orden. Una regla posterior no puede neutralizar
una incompatibilidad confirmada por una regla anterior. Las incompatibilidades
intrínsecas —beneficiario imposible, ayuda nominativa, sector excluido o alcance
residencial/formativo— se comprueban antes de la vigencia: seguirían siendo
incompatibles aunque la convocatoria estuviera abierta y no justifican descargar
bases ni consumir Haiku.

1. **Acceso y alcance intrínseco**
   - Rechazar beneficiarios incompatibles sin vía técnica o de clúster.
   - Rechazar concesiones nominativas, premios, formación, empleo, movilidad,
     vivienda y otros alcances inequívocamente ajenos.
   - Aplicar las exclusiones sectoriales explícitas antes de resolver plazos.
   - Si ya se descargaron bases para resolver otro dato, repetir el control antes
     de Haiku solo con expresiones documentales inequívocas. No aplicar términos
     amplios a todo el PDF porque pueden aparecer en excepciones o antecedentes.

2. **Alcance estructurado SNPSAP**
   - Rechazar finalidad primaria cuando Kalfrisa solo podría vender al beneficiario.
   - No aplicar ese rechazo a grupos operativos, consorcios o clústeres hasta
     comprobar si asignan actividad, costes y presupuesto propios a Kalfrisa.
   - Rechazar empleo solo con un objeto laboral explícito en el título; la mera
     finalidad administrativa `Fomento del Empleo` no basta porque se ha observado
     también en suelo industrial y transición energética.
   - Rechazar cooperación al desarrollo, ayudas destinadas expresamente a entes
     locales sin vía formal de participación y objetos autosuficientes de premios,
     ferias, artesanía, cultura o actividades primarias específicas.
   - Una anualidad histórica exige marcador inequívoco en el título, año de los
     dos ejercicios anteriores y ausencia de plazo confirmado. Fechas de leyes o
     proyectos no prueban que la convocatoria sea histórica.

3. **Integridad y vigencia**
   - Rechazar registros malformados y cierres confirmados.
   - Conservar fechas futuras y ventanillas expresamente indefinidas.
   - Si no existe fecha ni prueba de apertura, intentar extraerla de anuncios y
     documentos. Si sigue ausente, usar `hold_manual`; nunca asignar 90 días.
   - Un registro antiguo sin fecha ni evidencia documental vigente se rechaza
     como `no_active_evidence`, aunque el indicador API `abierto` sea verdadero.
   - La antigüedad se calcula con días con signo desde `fechaRecepcion`; las
     fechas pasadas no pueden truncarse a cero.
   - El indicador SNPSAP `abierto` se conserva como metadato, pero no demuestra
     por sí solo una ventanilla permanente: se han observado valores verdaderos
     en convocatorias cuyo plazo terminó años atrás.

4. **Acceso real a la ayuda**
   - Una concesión nominativa, convenio con beneficiario identificado o proyecto
     preseleccionado se rechaza como `not_open_call`.
   - La etiqueta BDNS `Concesión directa` no basta por sí sola: una ayuda directa
     con beneficiarios generales y plazo de solicitud abierto se conserva.
   - El valor oficial `Concesión directa - instrumental` sí se rechaza: describe
     una transferencia o instrumento sin solicitud competitiva abierta.

5. **Papel de Kalfrisa**
   - Beneficiaria empresarial admitida: `direct_beneficiary`.
   - Miembro formal de consorcio con trabajo, costes o presupuesto:
     `consortium_partner`.
   - Financiación, costes o pilotos canalizados a empresas miembro:
     `cluster_route`.
   - Solo funcionamiento, personal, estructura, representación o eventos del
     clúster: `reject_cluster_operations`.
   - Venta, suministro o subcontratación para un beneficiario ajeno:
     `indirect_commercial_role_only` y rechazo.
   - Papel no demostrable: `hold_manual`.

6. **Territorio**
   - Centro existente fuera de Aragón exigido al solicitar: rechazo.
   - Si las bases permiten abrirlo después de solicitar, solo se conserva cuando
     el periodo confirmado para implantación y ejecución es de al menos 730 días.
   - Un periodo de 729 días o menos es insuficiente.
   - Duración desconocida: `hold_manual`, no se presume viabilidad.
   - Localización del proyecto o inversión fuera de Aragón sin exigir centro
     previo no implica por sí sola rechazo.
   - Participación directa mediante clúster o consorcio sigue la rama de papel.

7. **Sector y conexión tecnológica**
   - C (manufactura), D (energía) y E (agua, residuos y descontaminación) son
     señales positivas.
   - B exclusivamente se rechaza; B junto con C, D o E no provoca rechazo.
   - F se conserva solo con conexión térmica o industrial explícita; edificación
     residencial o terciaria se rechaza.
   - A exclusivamente se rechaza como ayuda directa. Solo se conserva si existe
     una participación formal acreditada mediante consorcio o clúster.
   - Un NACE terciario no basta para excluir cuando hay evidencia fuerte de
     hidrógeno, energía, residuos, emisiones o demostración industrial.
   - No se exige I+D cuando Kalfrisa es beneficiaria: inversión productiva,
     maquinaria, mejora de procesos o ahorro energético propios son suficientes.
   - Sin conexión tecnológica ni papel empresarial acreditado se rechaza.

## Etiquetas visibles previstas

| Condición | Etiqueta |
|---|---|
| Participación formal en consorcio | `Socio de consorcio` |
| Participación mediante clúster | `Vía clúster` |
| Requiere abrir centro y cumple 730 días | `Requiere nuevo centro` |

Las etiquetas expresan el papel o dependencia principal. No sustituyen el motivo
completo almacenado en auditoría.

## Códigos mínimos de auditoría

- `deadline_closed`
- `no_active_evidence`
- `active_status_unverified`
- `not_open_call`
- `reject_cluster_operations`
- `cluster_role_unverified`
- `consortium_role_unverified`
- `consortium_participation_confirmed`
- `indirect_commercial_role_only`
- `existing_establishment_required_outside_aragon`
- `new_establishment_period_too_short`
- `new_establishment_duration_unknown`
- `primary_sector_only`
- `extractive_sector_only`
- `building_without_industrial_connection`
- `no_industrial_or_technology_connection`

## Restricciones de mantenimiento

- Conservar los campos BDNS como estructuras, no solo serializados dentro de
  `description`.
- Registrar valores originales y regla aplicada para cada exclusión.
- No cambiar el prompt o el evaluador general salvo que los papeles de consorcio
  o clúster se incorporen a la evaluación de encaje.
- No añadir los nuevos campos al hash factual si solo controlan el paso previo a
  Claude; evitar invalidar análisis válidos sin necesidad.
- Actualizar `AGENTS.md`, comentarios del código y pruebas cuando la matriz se
  conecte al filtro de producción.

## Piloto de resolución automática de `hold_manual`

El modo `--hold-pilot N`, con `1 <= N <= 20`, sirve para medir si la revisión
documental asistida puede sustituir el CSV manual sin degradar el recall. Solo
recopila BDNS y no puede combinarse con los demás modos de Claude.

Secuencia por caso:

1. Recuperar metadatos SNPSAP, anuncios, bases y sede oficial mediante HTTPS.
2. Extraer de forma local HTML, texto o PDF, con un máximo de cuatro descargas,
   5 MB por documento, 12 MB por caso y 48.000 caracteres de evidencia.
3. Resolver plazos de solicitud inequívocos mediante reglas deterministas.
4. Si la causa sigue abierta, hacer una única llamada estructurada a Haiku sobre
   esa pregunta: vigencia, territorio/duración, consorcio o vía clúster.
5. Aceptar la clasificación solo si incluye una cita literal presente en la URL
   declarada, confianza mínima de 65 y la propia cita contiene las señales que
   prueban la conclusión; en otro caso queda `unresolved`.

Las respuestas negativas sobre consorcio o clúster nunca provocan un descarte
solo porque el modelo no encuentre evidencia. Un cierre requiere una fecha de
solicitud pasada citada. Un centro existente requiere que la cita incluya tanto
el establecimiento como la obligación de disponer de él. Una mera localización
del proyecto no satisface esa condición. Los días de ejecución se recalculan
desde la cita y no se acepta el número convertido por el modelo sin contraste.

La muestra de veinte reserva, cuando hay casos suficientes, 12 casos a vigencia,
5 a territorio, 2 a consorcio y 1 a clúster. Dentro de cada estrato prioriza
afinidad tecnológica para evaluar primero el riesgo de falsos negativos de mayor
impacto. El informe selecciona además hasta seis órdenes para control de calidad,
cubriendo primero `retain`, `reject` y `unresolved`.

Artefactos separados:

- `grant_radar_data/bdns_hold_ai_cache.json`: caché versionada por convocatoria,
  causa, hash factual, evidencia y modelo.
- `grant_radar_data/bdns_hold_pilot_report.json`: decisiones, citas, métricas,
  consumo y muestra de control.
- `grant_radar_data/bdns_hold_replay_report.json`: repetición con reglas actuales,
  sin nuevas llamadas a Claude ni escritura en las cachés.

El piloto no modifica `grant_radar_cache.json`, `convocatorias.json` ni la salida
pública. Tampoco aprende automáticamente de la muestra humana. Antes de integrar
sus decisiones en producción se exige medir precisión por causa, revisar todos
los falsos rechazos de la muestra y definir cómo reanudar la matriz desde la
regla resuelta; una decisión `retain` del piloto solo supera la causa concreta,
no acredita por sí sola compatibilidad global.

### Resultado del piloto v1 — 07/08/2026

- 20 casos seleccionados, 19 llamadas Haiku y una resolución local.
- 105.008 tokens; coste estimado de 0,127212 USD.
- Salida inicial: 6 `reject`, 2 `retain` y 12 `unresolved`.
- El control detectó un falso rechazo: BDNS 692325 se clasificó como centro
  existente aunque la cita solo exigía ejecutar la actuación en Baleares.
- También se observó una falsa prueba de cierre basada en un plazo de ejecución,
  referencias del modelo a 2024 en vez de la fecha actual y llamadas desperdiciadas
  en convocatorias históricas por el cálculo de antigüedad.

Por estos motivos ninguna decisión v1 se integra en producción. La versión v2
incorpora fecha actual explícita, metadatos etiquetados, normalización tipográfica
de citas, prueba semántica por causa y los ajustes de vigencia descritos. Los
artefactos v1 se archivan automáticamente antes de escribir una ejecución v2.

La medición determinista intermedia, sobre 736 registros BDNS, redujo los holds
de 373 a 117 sin llamadas de pago. El piloto v2 posterior hizo 20 llamadas,
105.264 tokens y 0,1297 USD: produjo un rechazo territorial con cita sólida y 19
`unresolved`. La seguridad fue superior a v1, pero una tasa de resolución del 5 %
no permite conectarlo a producción.

El análisis de v2 detectó que SNPSAP publica los PDF por
`/convocatorias/documentos?idDocumento=...`; el conector solo conservaba URLs ya
formadas e ignoraba esos identificadores. La versión v3 incorpora ese endpoint,
`datPublicacion`, plazos relativos en días naturales/hábiles o meses, fechas con
puntos y comparación compacta para palabras partidas por la maquetación PDF. Los
días hábiles se estiman sin festivos y se señalan como fecha sin confirmar.

La medición determinista final de v3 recuperó 679 registros todavía vigentes o
sin cierre demostrado: 576 `reject`, 98 `hold_manual`, cuatro `retain` y un
`ambiguous`. Los holds se reparten en 33 de vigencia, 64 territoriales y uno de
proveedor según la política antigua; trece tienen etiquetas tecnológicas directas. Los 679 registros ya
disponen de al menos una URL documental oficial y doce fechas calculadas están
marcadas como estimadas. Esta medición determinista precedió al piloto real v3;
ninguna de sus decisiones se conectó a producción.

### Reentrada automática activa

`resolve_bdns_holds_for_pipeline()` recupera documentos de todos los holds del
pipeline normal. Usa `apply_verified_bdns_hold_resolution()` para reintroducir
los hechos locales que hayan superado las salvaguardas deterministas.

- Un `reject` verificado se conserva con etapa de auditoría propia.
- Un `retain` no evita el resto de la matriz: incorpora exclusivamente el hecho
  acreditado (vigencia, condición territorial, participación en consorcio o apoyo
  directo a miembros del clúster) y vuelve a ejecutar `deterministic_prefilter()`.
- Un `unresolved` pasa a `ambiguous` y continúa al análisis general con las bases
  añadidas a `related_document_contents`. Nunca se transforma en rechazo ni exige
  una decisión humana durante la ejecución.

La ruta está activa desde el 10/08/2026 tras la repetición v3 y el control de
falsos rechazos. Sus decisiones y descargas se registran en
`RUN_DIAGNOSTICS["bdns_automatic_hold_resolution"]`.

### Cambio táctico v4 — participación directa

Desde el 10/08/2026 la política excluye cualquier papel comercial indirecto.
Que el beneficiario pueda comprar equipos o ingeniería de Kalfrisa no rescata la
convocatoria. Sí se conservan inversiones propias sin I+D, como PAIP o INNOVAE,
y la participación formal con actividad o costes propios en consorcios y
clústeres. El esquema focalizado sustituye la pregunta de gasto suministrable por
`consortium_participation`; por ello su versión es
`bdns-hold-2026-08-v4-direct-participation`.

El piloto v3 real del 10/08/2026 analizó 20 casos con 18 llamadas, 212.900 tokens
y 0,238344 USD: tres `reject`, dos `retain` y quince `unresolved`. Bajo la nueva
política, las dos ayudas riojanas que exigen establecimiento previo son rechazos
correctos aunque financien equipos. La ejecución también reveló llamadas evitables
a premios, empleo, formación, vivienda y concesiones nominativas; corregir esas
exclusiones es un trabajo separado de esta redefinición de papel.

La validación real de v4 sin Claude recuperó 656 candidatas de 2.071 registros:
565 `reject`, 87 `hold_manual`, tres `retain` y una `ambiguous`. El nuevo código
`indirect_commercial_role_only` excluyó 22 casos e INNOVAE permaneció como
`direct_beneficiary`. Las convocatorias FNEE 919209 y 919217 siguen en espera
territorial hasta incorporar la evidencia documental de centro previo. PAIP no
apareció como convocatoria activa en esa descarga y se protege mediante fixtures
sintéticos específicos.

### Repetición v3 con reglas actuales — 10/08/2026

`--replay-hold-report` volvió a recuperar metadatos y documentos de los veinte
casos v3 y reutilizó sus resoluciones verificadas sin llamar de nuevo a Claude.
El resultado fue 12 `reject`, siete `ambiguous` y un `retain`. Ocho llamadas
históricas, 75.828 tokens, se habrían evitado por exclusiones deterministas de
empleo, formación, vivienda, premios, economía social y acceso nominativo.

Un primer barrido completo de palabras sobre los PDF produjo dos falsos
rechazos: IVACE 914587 contenía una referencia incidental a ferias y la línea
financiera 889461 mencionaba economía social sin que fuera su objeto. La ayuda
905892 sí era residencial y permaneció correctamente rechazada. La regla final
separa metadatos breves de documentos largos: sobre estos últimos
solo acepta expresiones autosuficientes de vivienda/residencial, empleo,
formación, autónomos, premios o acceso nominativo. IVACE 914587 vuelve a `retain`.

La revisión acotada de los cuatro casos de consorcio identificó los BDNS 916134,
914145, 904630 y 924030 como `Concesión directa - instrumental`. Se resuelven con
el metadato estructurado como `not_open_call`; no se añadió una heurística por
título ni se relajó la exigencia de trabajo, costes o presupuesto propios para un
consorcio real. Los futuros casos sin prueba simple permanecen para Haiku.

### Validación integral de la reentrada — 10/08/2026

La ejecución `--no-claude` consolidó 732 convocatorias. La matriz inicial dejó 73
holds BDNS. La ruta automática recuperó 245 documentos y resolvió cinco como
`reject`; un hecho positivo reentró y descubrió un segundo hold, mientras 67
resoluciones locales `unresolved` produjeron en conjunto 68 resultados
`ambiguous`. El resultado
operativo es cero revisiones humanas y 148 candidatas generales.

Se descargaron 89.079.839 bytes y se registraron 44 errores documentales no
bloqueantes. Ante un fallo de documento la convocatoria continúa como ambigua;
nunca se descarta por ausencia de evidencia. PowerUp NetZero e INNOVAE permanecen
como positivos de regresión. La cantidad de ambiguos BDNS es todavía material,
por lo que una ejecución completa debe consultar primero la previsión de hashes y
coste generada por `--no-claude`.

Los registros cuya vigencia continúa desconocida conservan el valor `1` solo
como centinela interno hasta la reentrada. Su estado determinista es `unknown` y
la salida pública usa `deadline=null`, `deadline_date=""` y
`fecha_sin_confirmar=true`. El dashboard los muestra como `Sin fecha`, fuera del
ranking de cierres próximos y del contador de urgencias.

### Backtest de alcance estructurado — 11/08/2026

La capa se probó antes de conectarla a la matriz. Sobre 577 convocatorias ya
excluidas coincidió con 66 (11,44 %) sin recuperar ni modificar ninguna: 22 por
finalidad primaria, 17 por empleo o cooperación al desarrollo, 20 por objetos
específicos, seis por anualidad histórica inequívoca y una por beneficiarios
públicos explícitos. Esto demuestra repetición en una población amplia y no solo
en los casos usados para diseñar los términos; no demuestra por sí solo recall.

Sobre 76 holds detectó 22 exclusiones que ahora se aplican secuencialmente antes
de descargar bases. Las dos coincidencias entre cuatro registros ya retenidos
eran duplicados de una ayuda exclusiva a industrias agroalimentarias: Kalfrisa
solo podría vender equipos al beneficiario y, por tanto, son exclusiones correctas
bajo el alcance vigente. Las pruebas positivas conservan INNOVAE, PAIP, energía,
residuos, suelo industrial, economía circular y transición energética. Los grupos
operativos se difieren hasta probar participación formal.

La primera carga de la caché documental procesó 225 solicitudes y 91.999.444
bytes. Una repetición reutilizó 161 documentos y redujo la red a 68 solicitudes y
8.679.169 bytes (−90,6 %). La caché contiene texto público de documentos estables,
no decisiones IA ni landings mutables. El backtest retrospectivo fue puntual y no
se ejecuta en producción; el pipeline final conserva la eliminación secuencial.

La ejecución integral posterior consolidó 733 convocatorias: 601 descartes, 54
holds, 70 `retain` y ocho `ambiguous` en la primera pasada. La reentrada dejó 51
ambiguas y tres rechazadas, para un total final de 129 candidatas frente a las 148
anteriores. La caché documental produjo 107 aciertos, 49 descargas y 7.658.540
bytes de red. Quedan 53 candidatas con procedencia BDNS; antes de Claude deben
evaluarse nuevas expresiones autosuficientes para variantes observadas de bonos
de comercio, conciliación laboral, Pyme Global, cultura y beneficiarios locales.

### Segunda capa residual e inventario de auditoría — 11/08/2026

La segunda capa incorpora únicamente variantes observadas cuyo propio título o
beneficiario estructurado demuestra el alcance: bonos de comercio, convocatoria
Pyme Global, conciliación de la vida personal, familiar o laboral, fomento
cultural, arte y educación, movilidad de profesionales culturales y ayudas
destinadas expresamente a entidades locales. No busca términos amplios dentro de
bases largas y no modifica la espera de grupos operativos, consorcios o clústeres.

El prefiltro común añade una salvaguarda para fuentes europeas: educación,
resultados escolares o salud mental se rechazan solo cuando constituyen el objeto
explícito del título y no existe ninguna señal tecnológica. Una mención industrial
o térmica positiva neutraliza esta exclusión. La regla se aplica después de la
consolidación y, por tanto, decide una sola vez sobre una call descubierta por
Horizon y EEN sin perder su procedencia múltiple.

La ejecución de validación consolidó 733 convocatorias: 610 descartes, 46 holds,
69 `retain` y ocho `ambiguous` en la primera pasada. Tras recuperar evidencia,
43 holds quedaron ambiguos y tres se rechazaron. El resultado final fue de 120
candidatas, nueve menos que en la ejecución de la primera capa y 28 menos que la
referencia de 148. Los descartes nuevos fueron ocho BDNS y una call fusionada
Horizon/EEN de alcance exclusivamente educativo y de salud mental. PowerUp
NetZero, INNOVAE y los positivos de energía, residuos e inversión industrial
permanecieron.

`--no-claude` guarda además `diagnostics.candidate_inventory` con un registro por
candidata final. Incluye identidad, fuentes, plazo, mecanismo, papel, decisión y
razón de inclusión, señales, resumen de alcance BDNS, hash factual y estado de
caché; excluye descripciones, bases y prompts completos. En esta ejecución hubo
58 `hit`, 62 `new` y cero `content_changed`. Las razones fueron 76 superaciones
del prefiltro común, una inversión propia confirmada, un análisis semántico BDNS
necesario y 42 holds no resueltos localmente. Este inventario sirve para explicar
el coste previsto, localizar cambios de contenido y comparar ejecuciones; no
introduce una revisión humana en el pipeline.

### Variantes residuales basadas en bases — 12/08/2026

La ampliación no reconoce programas, números BDNS ni municipios. Aplica dos
construcciones documentales reutilizables: un objeto explícito de contratación e
inserción laboral, y una enumeración exhaustiva de beneficiarios no empresariales.
En el segundo caso la sección termina en el siguiente epígrafe jurídico; una
mención a empresas en prohibiciones o requisitos generales posteriores no abre
una vía de acceso. Si la convocatoria contiene una línea empresarial, una nueva
implantación o una inversión productiva propia, se conserva.

Los catorce casos de `bdns_residual_scope_cases.json` cubren ambas decisiones y
sus contrapruebas: nueva empresa fuera de Aragón con duración desconocida,
programas con líneas nuevas y existentes, agrupación con empresas y financiación
de activos productivos. La ausencia de un epígrafe o de una lista concluyente
nunca causa rechazo. Las reglas locales inspeccionan el documento completo ya
descargado; `select_evidence_excerpt()` limita únicamente la evidencia que podría
recibir Claude. Así el objeto no compite con presupuesto o beneficiarios por un
cupo de caracteres y no es necesario reconocer el nombre de un programa.

### Presencia territorial previa y objetos residuales — 14/08/2026

La regla territorial solo rechaza cuando las bases obligan al beneficiario a
tener antes de solicitar un establecimiento operativo, centro de trabajo o de
producción, domicilio social o fiscal, o alta en el censo regional fuera de
Aragón. La ubicación del proyecto no demuestra presencia previa. Una nueva
implantación se conserva y, si exige abrir centro, se aplica por separado el
umbral de 730 días de ejecución confirmada.

La capa residual común reconoce objetos completos de contratación indefinida o
conversión contractual, automoción, movilidad o renovación de vehículos y
eficiencia energética de edificios terciarios. No usa `energía`, `residuos`,
`digital`, `edificio` o `vehículo` de forma aislada. La conexión explícita a un
proceso térmico o industrial prevalece y la incertidumbre continúa hacia Haiku.

El backtest sobre 32 ambiguas resolvió 13 exclusiones con estas construcciones y
conservó 19 casos para el modelo. Los fixtures incluyen contrapruebas de
localización futura del proyecto y mantienen suelo industrial, inversión propia,
energía, valorización de residuos y depuración de gases como dominios positivos.

### Segunda iteración sobre las 19 ambiguas — 14/08/2026

Se añadieron cinco hechos excluyentes reutilizables: gran empresa como único
beneficiario; personas autónomas o microempresas que inician actividad como
único perfil; nuevas variantes documentales de presencia previa regional o
municipal; nueva implantación con menos de 730 días confirmados; y
ciberseguridad industrial como objeto exclusivo sin conexión térmica. Cada
regla tiene contrapruebas que conservan PYME, nuevas implantaciones de al menos
730 días y tecnología térmica industrial.

El backtest integral resolvió siete de las 19: seis por incompatibilidad de
perfil, territorio o sector, y una por cierre confirmado. Las doce restantes no
aportaban evidencia bastante para un rechazo seguro y continúan a Haiku. Esta
es la condición de parada de la iteración: extraer más ahorro exigiría interpretar
semánticamente elegibilidad territorial, participación financiada o alcance de
inversión, por lo que una expresión local adicional elevaría el riesgo de falso
negativo.
