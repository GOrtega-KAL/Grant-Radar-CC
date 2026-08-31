# SUGERENCIAS.MD — Evaluación externa de Grant-Radar

Documento generado a partir de una revisión de solo lectura de `AGENTS.MD`,
`Grant-Radar-prueba.py`, `index.html`, `tests/` y la configuración de
dependencias (`pyproject.toml`/`poetry.lock`). No se ha modificado ningún
archivo del pipeline durante esta evaluación.

Fecha de la evaluación: 17/08/2026.

**Verificación posterior: 18/08/2026.** Se contrastó cada punto de este
documento contra el estado actual del código (`Grant-Radar-prueba.py` se
había modificado el 17/08 a las 15:41, después de escribir esta evaluación
a las 13:04; sin repositorio git no es posible diferenciar exactamente qué
cambió en esa ventana). Todos los puntos originales siguen vigentes salvo
dos correcciones factuales, marcadas explícitamente en 2.5 y 2.6, y se añade
un hallazgo nuevo (2.10 / 3.10) sobre ausencia de control de versiones. No
se modificó ningún archivo de `Grant-Radar-prueba.py`, `index.html` ni
`tests/` durante esta verificación.

**Seguimiento:** las secciones 4 y 5 recogen el estado a 19/08/2026 (sesión de
modularización), la 6 el de 20/08/2026 (ronda de calidad del dato y primera
ejecución completa publicada) y la 7 el de 21/08/2026 (URLs muertas en CDTI y
el embudo del IDAE), la 8 el indicador de embudo, la 9 la publicación y la 10 el falso negativo
del evaluador.
Para arrancar en frío, los documentos vigentes son `AGENTS.md` secciones 43 a
46; este de aquí es la evaluación externa y su seguimiento, no el estado vivo
del proyecto.

---

## 1. Evaluación general

Grant-Radar es un pipeline de vigilancia de subvenciones a medida para
Kalfrisa (PYME industrial de Zaragoza). Recopila convocatorias desde ocho
fuentes oficiales (BDNS, Horizon Europe, CDTI, IDAE, BOE/MITECO, BOA Aragón,
ECCP, EEN) combinando APIs oficiales y scraping con Playwright, aplica un
conjunto extenso de reglas deterministas de filtrado y salvaguarda, usa
Claude Haiku para extraer hechos estructurados y evaluar el encaje de los
casos ambiguos, y publica un JSON (`convocatorias.json`) que alimenta un
dashboard (`index.html`) con oportunidades relevantes, roles de
participación (beneficiario directo, socio de consorcio, vía clúster) y
estado de elegibilidad.

El diseño conceptual es notablemente maduro para un proyecto mantenido por
una sola persona:

- Caché basada en hash de contenido y versiones de perfil/extractor/
  evaluador/prompt/esquema, que evita reanálisis innecesarios y controla el
  coste de Claude.
- Barrera presupuestaria previa a cualquier llamada a Claude
  (`claude_safety_preflight()`), con límites nominales y de coste estimado.
- Salvaguardas deterministas posteriores al modelo que corrigen sesgos
  conocidos de Haiku (por ejemplo, confundir consorcio obligatorio con
  incompatibilidad de entidad, o descartar inversión propia por falta de
  I+D) sin necesidad de reanálisis.
- Matriz de reglas previa a Claude (`_bdns_pre_claude_gate()`) que reduce
  drásticamente el volumen que llega al modelo, con trazabilidad de motivo
  de descarte.
- Suite de 144 pruebas deterministas con fixtures reales (BDNS, ECCP,
  deduplicación, filtro común, contrato de frontend) que se ejecutan sin red
  ni gasto de tokens.
- Auditoría estructurada por ejecución (`grant_radar_audit.json`) con
  inventario de candidatas, motivo de inclusión/exclusión y consumo de
  Claude por intento.

Frente a esto, el proyecto arrastra una deuda estructural real, visible en
el propio historial de ajustes acumulados en `AGENTS.MD` (secciones 13 a
20): decenas de correcciones puntuales de vocabulario y reglas de negocio
introducidas por ensayo-error sobre casos concretos detectados en
producción. Esto indica un sistema de reglas que ha crecido de forma
reactiva y que es cada vez más costoso de razonar como conjunto coherente,
además de una base de código monolítica con una vulnerabilidad de gestión
de credenciales que depende enteramente de la disciplina manual del
usuario.

En síntesis: la lógica de negocio y el criterio de filtrado son de alta
calidad; la ingeniería de software que los sostiene (estructura del código,
gestión de secretos, modularidad) está por debajo de ese nivel y es el
principal freno a la mantenibilidad futura.

---

## 2. Problemas y debilidades detectadas

### 2.1. Gestión de credenciales insegura (crítico)

El archivo `API KEYs.txt` contiene credenciales reales (clave de API de
Anthropic y tokens de acceso personal de GitHub con permiso de escritura) y
reside en la raíz del repositorio. `.gitignore` **no excluye** ese archivo,
ni tampoco `convocatorias.json` ni `debug.log`; solo excluye las cachés de
`grant_radar_data/`. `AGENTS.MD` documenta que el usuario debe restaurar
manualmente `CLAUDE_API_KEY` y `GITHUB_TOKEN` a `"Placeholder"` antes de
guardar o compartir el código, pero esto es un proceso humano sin ningún
control automático que lo garantice. Un único olvido en un commit o en un
envío del código expondría credenciales reales con capacidad de escritura
en GitHub y de gasto en la cuenta de Anthropic.

### 2.2. Arquitectura monolítica

`Grant-Radar-prueba.py` concentra en un único archivo de casi 11.000 líneas
toda la lógica del sistema: scraping por fuente, reglas de negocio,
prompts, validación de esquemas, gestión de caché y publicación. No existen
paquetes ni módulos (`src/`, `sources/`, `rules/`, etc.). La propia suite de
tests necesita cargar el script completo con `runpy.run_path()` porque no es
un paquete importable de forma convencional. Esto implica:

- Cualquier cambio, por pequeño que sea, requiere entender potencialmente
  todo el archivo.
- El riesgo de romper una fuente o regla al tocar otra parte del código es
  alto, ya que todo comparte el mismo espacio de nombres.
- La incorporación de otro desarrollador al proyecto tiene una curva de
  entrada muy pronunciada.

### 2.3. Reglas de negocio hardcodeadas como código, no como datos

Funciones centrales como `_hard_out_of_scope()` y `_bdns_pre_claude_gate()`
implementan la lógica de exclusión sectorial y territorial como cascadas
largas de condicionales (`if`/`and`/`or`) sobre tuplas de términos
incrustadas directamente en el cuerpo de la función (por ejemplo
`transport_terms`, `building_terms`, `cybersecurity_terms`,
`nuclear_terms`, `marine_policy_terms`). El propio `AGENTS.MD` documenta
que casi cada ejecución de validación descubre una nueva variante léxica
que exige ampliar estos términos (secciones 13 a 20 documentan más de una
decena de ampliaciones puntuales entre el 07/08/2026 y el 17/08/2026).
Consecuencias:

- Cada ajuste de vocabulario obliga a modificar y desplegar código Python,
  cuando conceptualmente es un cambio de configuración.
- La complejidad ciclomática de estas funciones crece sin límite natural.
- No hay forma de que alguien sin conocimientos de Python (por ejemplo, la
  propia Kalfrisa) revise o proponga cambios en los criterios de filtrado.
- El riesgo de introducir una regresión al añadir un término nuevo es alto,
  porque no hay una estructura de datos que aísle "qué excluye" de "cómo se
  aplica".

### 2.4. Fragilidad estructural ante cambios en fuentes externas

Los conectores basados en scraping (CDTI, BOE/MITECO, IDAE, ECCP) dependen
de selectores HTML y estructuras de calendario que ya se han roto en el
pasado: `AGENTS.MD` documenta que el scraper de CDTI omitía convocatorias
por errores de orden en el pipeline (título demasiado corto tras retirar un
marcador, filtro de relevancia aplicado antes de abrir la ficha), y que el
parser de BOE/MITECO dejó de funcionar tras un cambio de marcado
(`p.linea-dem`) hasta ser detectado y corregido. Existe un control de salud
común (`assess_web_inventory_health()`) que detecta degradación, pero es
reactivo: informa después de que la cobertura ya se ha reducido, no la
previene. **[Corregido en la verificación del 18/08/2026]** `assess_web_inventory_health()`
sí emite un `log.warning()` inmediato en cuanto evalúa una fuente como
`degraded` o `unhealthy` (línea ~490), visible en consola durante la propia
ejecución en curso; no es necesario esperar ni revisar manualmente el JSON de
auditoría para verlo. Lo que sigue faltando es un resumen consolidado al
final de la ejecución (una fuente degradada puede pasar desapercibida entre
cientos de líneas de log de una recopilación larga) y, combinado con la
ausencia de tests contra las webs reales (los 144 tests son deterministas
sobre fixtures fijos), la detección de una rotura de estructura depende de
que alguien esté observando la consola o el log en el momento de la
ejecución, o revise `debug.log` después.

### 2.5. Código muerto y artefactos generados mezclados con el código fuente

**[Corregido en la verificación del 18/08/2026]** De las cuatro funciones
citadas originalmente como "legacy" sin eliminar, solo dos están realmente
muertas: `_legacy_bdns_cdti_session_scraper()` y
`_fetch_cdti_playwright_legacy()` se definen pero no tienen ninguna llamada
en el resto del archivo. `_legacy_tags_for()` y `LEGACY_TECH_TAG_MAP`, en
cambio, sí se usan activamente (líneas 10054 y 10334) para mantener
compatibilidad de taxonomía hacia atrás en el JSON publicado: el nombre
"legacy" es engañoso, pero no es código muerto y no debe eliminarse sin más.
Además, artefactos generados como `convocatorias.json` (845 KB) y
`debug.log` conviven en la raíz junto al código versionable, sin una
separación clara entre "fuente" y "salida".

### 2.6. Exportación XLSX reimplementada a mano, sin cobertura de regresión de columnas

**[Corregido en la verificación del 18/08/2026]** El frontend genera el
archivo XLSX construyendo manualmente el XML OOXML (`xlsxCellXml`,
`buildFilteredXLSX`) en lugar de usar una librería probada como SheetJS. A
diferencia de lo que afirmaba la versión anterior de este documento, sí
existe un test automatizado de integridad
(`test_xlsx_export_is_a_styled_filtered_workbook` en
`tests/test_grant_radar.py`): abre el XLSX generado con `zipfile.ZipFile`,
valida `testzip()`, confirma la presencia de `xl/worksheets/sheet1.xml` y
`xl/styles.xml`, y comprueba cabecera congelada, autofiltro, anchos de
columna, neutralización de fórmulas y exclusión de columnas de tokens
internos. El hueco real no es la integridad del formato en sí, sino la
regresión de contenido: ese test fija un conjunto concreto de columnas, así
que si se añade o quita una columna del export sin actualizar el test, nada
avisa automáticamente de la divergencia entre lo exportado y lo esperado.

### 2.7. Acoplamiento estricto al perfil de un único cliente

El perfil de Kalfrisa (sector, tamaño de empresa, ubicación en Aragón) está
embebido en la lógica de reglas (por ejemplo, el reconocimiento explícito
de "Zaragoza, Huesca y Teruel" como Aragón, o las salvaguardas de
territorio y tamaño empresarial). Esto es coherente con el objetivo actual
del proyecto (una herramienta interna para una empresa concreta), pero
significa que el sistema no es reutilizable para otra empresa sin reescribir
buena parte de las reglas deterministas, no solo cambiar un parámetro de
configuración.

### 2.8. Ausencia de tests de integración y de contrato explícito frontend-backend automatizado más allá de fixtures

Existe un test de "contrato del frontend" sobre fixtures sintéticos, lo cual
es positivo, pero no hay una validación automática que compare el esquema
JSON real generado por una ejecución completa contra lo que `index.html`
espera consumir, más allá de la revisión manual que `AGENTS.MD` pide hacer
antes de cada cambio de esquema.

**[Corregido en la verificación del 18/08/2026]** Ejecutar el pipeline completo
en un test no es viable sin red (recopila de ocho fuentes oficiales reales) y
rompería el diseño determinista de la suite, así que en vez de eso se extrajo
la construcción del registro público a una función aislada
(`_assemble_public_record()`, antes en línea dentro de `run_pipeline()`) y se
añadió un test que la llama con datos sintéticos y comprueba que cada campo
del registro real aparece en `index.html`. Ese test detectó de inmediato una
divergencia real ya existente: el backend publica `eoi_deadline_date`
(plazo de expresión de interés, distinto del cierre de la convocatoria) pero
`index.html` nunca lo leía; se corrigió mostrándolo en el bloque de
trazabilidad del detalle. Quedan cinco campos que el backend publica y el
frontend no consume, marcados como deliberadamente fuera del contrato en el
propio test: `catalog_scope`, `catalog_category`, `catalog_ref` (procedencia
de catálogos estáticos) y `related_documents_count`, `bdns_url`
(trazabilidad interna). No se ha decidido si deben mostrarse; queda como
mejora futura si se considera útil para el usuario final.

### 2.9. Requisito de versión de Python agresivo

`pyproject.toml` exige `python >= 3.14`, una versión muy reciente para un
proyecto en producción. Esto puede complicar la reproducibilidad del
entorno en otras máquinas o en el futuro, si el ecosistema de dependencias
(Playwright, pydantic, anthropic) tarda en dar soporte completo a versiones
tan nuevas de Python.

### 2.10. Ausencia de control de versiones **[Añadido en la verificación del 18/08/2026]**

No hay repositorio git en ningún punto del árbol de trabajo. El versionado
real del proyecto se hace mediante copias manuales de carpeta completa (esta
misma carpeta, `Grant-Radar - Claude Code`, es una copia de `Grant-Radar`) y
una carpeta `Obsoleto/` con snapshots sueltos nombrados por fecha (formato
`DDMMAA`: `260704`, `260724`, `260729`, `260804`, `260807`, `260810`,
`310426`) que contienen versiones anteriores de `Grant-Radar.py`,
`index.html` y `convocatorias.json`, incluyendo variantes paralelas
(`Grant-Radar CODEX.py`, `Vigtech I+D.py`). `Frontend alternativo/` añade más
variantes sueltas de `index.html`. Sin git no hay diff, blame, ramas ni forma
fiable de saber qué snapshot es el origen de cuál más allá de la fecha de
modificación del archivo; el propio historial narrativo acumulado en
`AGENTS.MD` (secciones 13-20) funciona en la práctica como sustituto parcial
de un changelog de commits, pero sin la trazabilidad línea a línea que
ofrecería git.

---

## 3. Soluciones propuestas

### 3.1. Frente a 2.1 — Gestión de credenciales insegura

1. **[Implementado el 18/08/2026]** `Grant-Radar-prueba.py` (Celda 2) ahora
   llama a `load_dotenv()` y lee `CLAUDE_API_KEY`/`GITHUB_TOKEN` con
   `os.environ.get(..., "Placeholder")`: si existe un `.env` con la variable,
   se usa esa; si no, cae al `"Placeholder"` de siempre. Se añadió
   `python-dotenv` a `pyproject.toml`/`poetry.lock`, un `.env.example`
   (versionado, sin claves reales) y un `.env` real vacío en esta copia
   (excluido de git). El flujo antiguo de pegar la clave directamente en el
   script sigue funcionando si alguien lo prefiere.
2. **[Implementado el 18/08/2026]** `.gitignore` excluye ahora `API KEYs.txt`,
   `.env`, `debug.log`, `convocatorias.json`, `.venv/` y `__pycache__/`.
   Verificado con `git check-ignore -v` sobre los seis antes del primer commit.
3. **[Implementado el 18/08/2026]** `scripts/Comprobar credenciales antes de
   commit.ps1` revisa los archivos "staged" en busca de los tres patrones de
   clave real y bloquea el commit si encuentra alguno; está enganchado como
   `.git/hooks/pre-commit`.
4. No se ha hecho: no había repositorio git antes de esta sesión (se inició
   hoy mismo, ver 2.10/3.10), así que `API KEYs.txt` no puede haber entrado
   en ningún historial de Git de esta copia. Sigue sin descartarse que haya
   estado en otras copias compartidas fuera de este control; solo el usuario
   puede confirmarlo y, si aplica, rotar las claves en Anthropic/GitHub.
5. **[Implementado el 18/08/2026]** Ver sección 7 de `AGENTS.md`, ampliada con
   esta configuración como invariante.

### 3.2. Frente a 2.2 — Arquitectura monolítica

1. Dividir `Grant-Radar-prueba.py` en paquetes por responsabilidad
   manteniendo el comportamiento actual, por ejemplo:
   `sources/` (un módulo por fuente: BDNS, Horizon, CDTI, IDAE, BOE, BOA,
   ECCP, EEN), `rules/` (matriz previa a Claude, filtro común, salvaguardas
   posteriores), `claude_pipeline/` (esquemas Pydantic, prompts, llamadas,
   validación), `cache/` (caché IA, caché documental, auditoría) y
   `pipeline.py` (orquestación de alto nivel).
2. **[Primer incremento aplicado el 18/08/2026]** Se creó el paquete
   `grant_radar/` (nombre válido para `import`, a diferencia de
   `Grant-Radar-prueba.py`, que conserva su nombre y sigue siendo el punto
   de entrada) y se extrajo `grant_radar/parsing_helpers.py`: doce
   funciones/constantes puras de fechas y texto
   (`_days_until`, `_parse_flexible_date`, `_extract_application_dates`,
   `_fold_text`, `_levenshtein`, etc.), sin dependencia de caché, reglas ni
   Claude. Cada eliminación del script principal se verificó con
   `py_compile` + los 146 tests existentes antes de continuar con la
   siguiente, tal como pide este punto; además se añadió
   `tests/test_grant_radar_parsing_helpers.py`, que importa el módulo de
   forma estándar (sin `runpy`) y prueba solo esas funciones. Fue posible
   extraerlas primero precisamente porque no dependen de nada más: intentar
   `cache/` primero (el candidato original) reveló que `filter_usable_cache()`
   llama a `apply_current_deterministic_rules()`, que a su vez depende de
   gran parte del dominio de reglas — cache y rules están acopladas y no se
   pueden separar de forma aislada sin extraer también ese dominio.
   El resto de la división (`sources/`, `rules/`, `claude_pipeline/`,
   `cache/`, `pipeline.py`) sigue pendiente; cada paquete requiere el mismo
   análisis de dependencias antes de mover código, y algunos (`rules/`,
   `cache/`) no son independientes entre sí.
   **[Segundo incremento, mismo día]** Se localizó un bloque grande y
   cohesionado que tampoco dependía de caché, reglas ni Claude: la
   taxonomía tecnológica y su comparación contra texto. Se extrajo
   `grant_radar/tech_taxonomy.py` (datos en `tech_taxonomy.json` + funciones
   `detect_tech_tags`, `is_relevant`, `keyword_match`, `_compat_tags_for`,
   etc.), y por separado — al ser puramente datos de cliente, relevantes
   para 2.7 — `grant_radar/kalfrisa_profile.py` (el texto de perfil de
   Kalfrisa que se envía a Claude, ahora en `kalfrisa_profile.txt`, editable
   sin tocar Python) y `grant_radar/partner_catalog.py` (los 16 socios
   técnicos y la función `preselect_partners()`). También se movió
   `select_evidence_excerpt()` a `parsing_helpers.py`, al ser igual de
   autónoma que el resto de ese módulo. Cada extracción se verificó por
   separado con `py_compile` y la suite completa antes de continuar con la
   siguiente; se añadieron tres archivos de test más
   (`test_grant_radar_tech_taxonomy.py`,
   `test_grant_radar_profile_and_partners.py`, y ampliaciones a
   `test_grant_radar_parsing_helpers.py`). El script principal bajó de
   10.976 a 10.037 líneas (-8,6 %) entre las dos rondas de extracción del
   18/08/2026; 180 tests `unittest` y `py_compile` en verde.
   **[Tercer incremento, mismo día — cache y rules juntos, a petición
   expresa]** Se extrajo el acoplamiento identificado en el primer
   incremento: `grant_radar/cache.py` (`cache_key`, `cache_save`,
   `cache_load`, `filter_usable_cache`, `analysis_is_usable`,
   `_reindex_cache_entries`, `source_hash`, `_stable_factual_hash_text`) y
   `grant_radar/deterministic_rules.py` (`apply_current_deterministic_rules`
   y las 18 funciones que llama: correcciones de inversión propia,
   valorización, consorcio, tamaño de empresa, región, consistencia
   temporal...). `cache.py` importa `apply_current_deterministic_rules` de
   `deterministic_rules.py`; es la única dependencia cruzada entre ambos, tal
   como se había detectado. También se creó `grant_radar/versions.py` (las
   versiones de perfil/extractor/evaluador/prompt/caché/modelo, que
   `cache_key`/`cache_save`/`cache_load` necesitaban) y se movió
   `_deterministic_call_status()` junto con `BDNS_DIRECT_OWN_INVESTMENT_TERMS`
   (compartida con el filtro previo a Claude, que sigue en el script
   principal y la reimporta). `cache_save`/`cache_load` pasaron a recibir la
   ruta del archivo como parámetro en vez de leer una constante propia, para
   no duplicar el cálculo de ruta basado en `__file__` en dos sitios.
   El script principal bajó de 10.037 a 9.006 líneas en este tercer paso
   (-10,3 % adicional; -17,9 % acumulado desde las 10.976 originales). Se
   añadieron `test_grant_radar_cache.py` y
   `test_grant_radar_deterministic_rules.py` con import estándar. Los tests
   de `test_grant_radar.py` que accedían a estas funciones vía
   `APP["nombre"]` (patrón `runpy`) se mantuvieron intactos: se añadió un
   bloque al principio del archivo que fusiona las funciones movidas de
   vuelta en `APP` en lugar de reescribir unos 12 puntos de acceso
   dispersos; los archivos de test nuevos sí importan directamente. 205
   tests `unittest` y `py_compile` en verde, más una ejecución real
   `--no-claude` completa (8:33 min, 47 candidatas, mismas cifras que la
   ejecución de esa misma mañana, las 4 fuentes con control de salud
   `healthy`): confirma que el cambio no alteró ningún resultado del
   pipeline real, no solo los tests.
   **[Cuarto incremento, mismo día — esquemas de Claude]** Se extrajo
   `grant_radar/claude_schemas.py`: los cinco modelos Pydantic
   (`CallFacts`, `CallEvaluation`, `FundingLineFacts`, `EvaluationScores`,
   `BdnsHoldFacts`), `ClaudeAnalysisError`, y las funciones que los validan
   contra los límites publicados de Anthropic
   (`structured_schema_complexity`, `validate_structured_output_schema`,
   `normalize_call_facts`). Fue el candidato más sencillo hasta ahora: no
   depende de ningún otro módulo del proyecto, solo de `pydantic` y la
   librería estándar. El script principal bajó de 9.006 a 8.835 líneas
   (-18,6 % acumulado). Nuevo `test_grant_radar_claude_schemas.py`,
   incluyendo un test que fija en código el invariante de `AGENTS.md`
   "cero opcionales, cero uniones" para los tres esquemas principales, para
   que un campo `Optional` añadido sin querer en el futuro rompa un test en
   vez de descubrirse al fallar una llamada real a Claude. 216 tests
   `unittest`, `py_compile` y una repetición de `--no-claude` en verde, con
   las mismas 47 candidatas de las ejecuciones anteriores.
   **Quinto incremento, sesión siguiente — primera prueba de `sources/`]**
   Se extrajo el primer conector de fuente, BOA Aragón (el más pequeño y
   autocontenido de los ocho), a `grant_radar/sources/boa_aragon.py`. Dos
   dependencias compartidas con otras fuentes se resolvieron antes de mover
   el conector: `_es_titulo_valido()` (pura, también usada por `fetch_boe()`)
   pasó a `parsing_helpers.py`; `audit_exclusion()` y la lista mutable
   `DISCOVERY_AUDIT` (compartidas por las 8 fuentes, 32 referencias en el
   script) pasaron juntas a un módulo nuevo, `grant_radar/audit.py` —
   el script principal las reimporta, así que las ~30 llamadas existentes no
   cambiaron. Ver AGENTS.md sección 25 para el detalle completo, incluida
   una discrepancia de recuento de líneas detectada al arrancar esta sesión
   (la cifra "8.835" del cuarto incremento no cuadraba con `wc -l` sobre el
   commit real: eran 9.426). Los otros siete conectores no son tan simples:
   CDTI fusiona con BDNS, BOE/IDAE/CDTI llaman a
   `assess_web_inventory_health()` (aún en el script principal), y ECCP/EEN
   tienen lógica propia de profundidad de rastreo — cada uno necesitará el
   mismo análisis de dependencias antes de moverse, no una repetición
   mecánica del mismo patrón.
   **[Sexto incremento, 19/08/2026 — la capa de infraestructura]** Antes de
   mover otro conector se analizaron con AST las dependencias reales de los
   siete que quedaban, y el resultado reordenó el trabajo: repetir el patrón
   BOA uno a uno no era posible porque seis de los siete dependen de piezas
   compartidas que seguían en el script (estado de ejecución, cliente HTTP,
   control de salud, navegador, helpers de texto, identidad documental). Se
   extrajo por eso la mitad de esa capa: `grant_radar/runtime_state.py`
   (`SOURCE_RUNTIME_METADATA`, `IDENTITY_LANDINGS`, `COVERAGE_WATCH_RESULTS`,
   `RUN_DIAGNOSTICS`, con el patrón de objetos mutables compartidos de
   `audit.py`), `grant_radar/http_client.py` (`_http_get`,
   `_is_safe_public_https_url`, `HTTP_USER_AGENT`),
   `grant_radar/source_health.py` (`assess_web_inventory_health`) y
   `grant_radar/call_text.py` (mecanismo de financiación, identificador oficial
   europeo, deadline y presupuesto en prosa, enlaces externos). Hallazgo
   colateral que abarata las etapas siguientes: los tests que sustituyen
   dependencias con `mock.patch.dict(APP["fn"].__globals__, ...)` siguen
   funcionando tras mover una función a un módulo, porque `__globals__` apunta
   al módulo donde la función queda definida. `Grant-Radar-prueba.py` bajó de
   9.199 a 8.963 líneas; 283 pruebas (238 + 45) y `py_compile` en verde tras
   cada extracción, más un `--no-claude` completo al cerrar la ronda. Detalle y
   plan por etapas del resto en AGENTS.md sección 28.
   **[Séptimo incremento, 19/08/2026 — primeros conectores sobre la capa
   nueva]** Con la infraestructura fuera, se extrajeron
   `grant_radar/sources/horizon_europe.py` y `grant_radar/sources/een.py`, los
   dos que ya no dependían de nada más. Confirmado en la práctica que los tests
   con `mock.patch.dict(APP["fn"].__globals__, ...)` no necesitan cambios; solo
   hubo que añadir el módulo EEN al bloque de fusión de `APP`, porque siete
   tests usan un helper privado que el script no reimporta. La ronda destapó
   además un `NameError` latente desde el tercer incremento: catorce funciones
   de `deterministic_rules` que `_build_compatible_analysis()` llamaba sin que
   el script las importara, invisible para `py_compile` y para `--no-claude`, y
   tapado sin querer por el propio bloque de fusión de `APP`. Corregido y
   cubierto con `tests/test_grant_radar_script_names.py`. 295 pruebas y un
   `--no-claude` con resultados idénticos (77 vigentes, mismo desglose).
   `Grant-Radar-prueba.py`: 8.963 → 8.403 líneas.
   **[Octavo incremento, 19/08/2026 — navegador e identidad documental]**
   Segunda mitad de la capa compartida: `grant_radar/browser.py`
   (`PlaywrightBrowser`, con lo que el script principal deja de importar
   `playwright.sync_api` y el conector BOA puede tipar su parámetro `browser`
   de verdad, en vez del `typing.Any` que arrastraba desde el quinto
   incremento) y `grant_radar/dedup.py` (identidad de programa, rol y rango
   documental, y deduplicación). Con esto queda extraída toda la
   infraestructura que bloqueaba a BOE, IDAE y CDTI. 317 pruebas (295 + 22,
   incluidas las de `browser.py` sin arrancar Chromium) y un `--no-claude` con
   las mismas 33 duplicadas fusionadas y las mismas 77 vigentes.
   `Grant-Radar-prueba.py`: 8.403 → 7.977 líneas.
   **[Noveno incremento, 19/08/2026 — conectores IDAE y BOE/MITECO]** Primeros
   conectores que usan la infraestructura completa (navegador, control de salud
   e identidad documental, ya todos en módulos): `grant_radar/sources/idae.py`
   y `grant_radar/sources/boe_miteco.py`, 1.090 líneas entre los dos. Tests
   nuevos complementarios a los existentes: los helpers de catálogo de IDAE y,
   para BOE, el modo de fallo real (inventario inalcanzable, marcado cambiado,
   convocatoria sin plazo). 331 pruebas y un `--no-claude` idéntico otra vez.
   `Grant-Radar-prueba.py`: 7.977 → 6.976 líneas, -24,2 % acumulado en el día.
   **[Décimo incremento, 19/08/2026 — conector BDNS]** El caso que exigía más
   cuidado: BDNS aporta 899 de las 953 convocatorias detectadas y comparte seis
   primitivas de lectura de campos con la matriz de reglas previa a Claude. Se
   resolvió extrayéndolas a `grant_radar/bdns_fields.py`, que el script
   reimporta, de modo que `grant_radar/sources/bdns.py` salió sin tocar una
   línea de esa matriz. Dos fallos los cazaron las pruebas durante la ronda (un
   import olvidado en el módulo nuevo y una llamada huérfana en el script), y a
   raíz del primero se amplió `tests/test_grant_radar_script_names.py` para
   comprobar también cada módulo del paquete. 349 pruebas y un `--no-claude`
   idéntico. `Grant-Radar-prueba.py`: 6.976 → 6.409 líneas, -30,3 % en el día.
   **[Undécimo incremento, 19/08/2026 — capa documental y CDTI]** CDTI era el
   único conector bloqueado por un dominio propio y no por infraestructura
   genérica: el enriquecimiento con documentos oficiales. Se extrajeron
   `grant_radar/documents.py` (descarga, extracción de texto HTML/PDF y caché
   documental de fuentes) y `grant_radar/sources/cdti.py`. Con ellos,
   `grant_radar/sources/` reúne siete de los ocho conectores; solo queda ECCP,
   que espera por `deterministic_prefilter()`. 361 pruebas y un `--no-claude`
   idéntico por sexta vez. `Grant-Radar-prueba.py`: 6.409 → 5.384 líneas,
   -41,5 % acumulado en el día.
   **[Duodécimo incremento, 19/08/2026 — conector ECCP; los ocho ya fuera]**
   ECCP se movió con el prefiltro inyectado como parámetro
   (`is_relevant_enough`), sin tocar la matriz de reglas: sus dos usos eran de
   predicado de relevancia, no de elegibilidad. La ronda destapó dos
   `NameError`: uno propio (`statistics` sin importar), que solo cazó la
   ejecución `--no-claude` porque ni `py_compile` ni los tests recorren esa
   ruta, y otro preexistente desde el commit inicial en `fetch_idae_catalog()`,
   que habría tumbado la fuente el día que el catálogo IDAE volviera a aportar
   una convocatoria. El detector de nombres se amplió a cualquier nombre leído
   —antes solo miraba llamadas directas— y a los parámetros de `lambda`.
   371 pruebas. `Grant-Radar-prueba.py`: 5.384 → 5.018 líneas, -45,5 % en el
   día. Queda `pipeline.py` y la sesión de reglas.
   **[Decimotercer incremento, 19/08/2026 — salida pública y decisiones de
   coste]** La etapa planeada era `pipeline.py`, pero al medirla resultó
   inviable: extraer `run_pipeline()` arrastraría 64 de las 68 funciones
   restantes, incluida la matriz de reglas. Se reformuló sobre los cuatro
   dominios con frontera limpia: `public_output.py` (registro público,
   estadísticas, estado por fuente, URLs), `publishing.py` (GitHub Pages, con
   las credenciales como parámetros en vez de leídas en el módulo),
   `claude_selection.py` (qué se manda a Haiku y la barrera de coste) y
   `coverage_watch.py`. 381 pruebas y un `--no-claude` con los números de
   referencia completos, BOE incluido. `Grant-Radar-prueba.py`: 5.018 → 4.286
   líneas, -53,4 % en el día; el paquete ya tiene casi el doble de código que
   el script.
   **[Decimocuarto incremento, 19/08/2026 — primera mitad del dominio de
   holds]** Las ~1.171 líneas del dominio de holds no se podían mover enteras:
   dependen de la matriz de reglas y de la capa de Haiku. Se midió por
   subgrupos y salió la mitad limpia: `hold_quotes.py` (validación de que una
   cita prueba la conclusión, cero dependencias), `claude_usage.py` (recuento
   de tokens y coste) y `hold_evidence.py` (documentos oficiales y caché
   documental de BDNS, con la regla intrínseca inyectada como parámetro). La
   resolución determinista y el piloto se quedan: su cometido es aplicar la
   matriz, así que se mueven con ella. 381 pruebas y un `--no-claude` idéntico,
   incluida la resolución automática de holds (`ambiguous=38, reject=35,
   revisión manual=0`). `Grant-Radar-prueba.py`: 4.286 → 3.842 líneas, -58,2 %
   en el día, y ya solo 33 funciones de las 68 iniciales.
3. Hacerlo de forma incremental y verificada: extraer un módulo, ejecutar
   `py_compile` y la suite completa de `unittest`, confirmar comportamiento
   idéntico con `--no-claude`, y solo entonces continuar con el siguiente
   módulo. Evita una migración de alto riesgo en un único paso.
4. Conservar los encabezados `CELDA N` como comentarios de sección dentro de
   cada módulo mientras se considere útil para la navegación, o sustituirlos
   por la propia organización en archivos una vez completada la migración.
5. Actualizar los tests para importar los módulos de forma estándar en vez
   de depender de `runpy.run_path()` sobre un script monolítico
   (`tests/test_grant_radar_parsing_helpers.py` ya lo hace para el módulo
   extraído; `tests/test_grant_radar.py` sigue usando `runpy` para el resto
   del script, que continúa siendo un único archivo).

### 3.3. Frente a 2.3 — Reglas de negocio hardcodeadas

1. **[Primer incremento aplicado el 18/08/2026, solo datos]** Se externalizaron
   a `grant_radar/exclusion_terms.json` las diez listas de palabras que usa
   `_hard_out_of_scope()` (transporte, edificios, ciberseguridad, seguridad
   civil, gobernanza, generación renovable, nuclear, política marina,
   digital/cuántica genérica, educación/salud). `grant_radar/exclusion_terms.py`
   carga el JSON y expone cada lista como constante; `_hard_out_of_scope()`
   las referencia igual que antes. Deliberadamente **no** se movieron las
   condiciones (qué combinación de tags térmicos neutraliza cada lista, qué
   mensaje de descarte usa, si la comparación es por palabra completa o
   subcadena): eso es la parte de "cuándo se aplica cada regla", con lógica
   distinta por categoría y ajustada durante meses (AGENTS.md, secciones 4 y
   13-20); moverla habría sido el motor de reglas genérico del punto 2, con
   mucho más riesgo. Ampliar una categoría existente ya es hoy "añadir una
   palabra al JSON"; añadir una categoría nueva con una condición distinta
   sigue requiriendo Python. Verificado con `py_compile`, los 25 casos de
   `tests/fixtures/common_scope_filter_cases.json`, los 160 tests completos y
   un nuevo `tests/test_grant_radar_exclusion_terms.py` que comprueba que el
   JSON carga sin duplicados ni categorías vacías.
2. No implementado: el motor de reglas genérico en sí (que interpretaría
   condiciones de precedencia y contexto de forma declarativa, no solo
   listas de términos) sigue pendiente. Diseñarlo bien requeriría formalizar
   primero, en un documento aparte, todas las variantes de condición que hoy
   existen en `_hard_out_of_scope()` y, sobre todo, en `_bdns_pre_claude_gate()`
   (mucho más compleja: siete niveles de precedencia documentados en la
   sección 4.1 de `AGENTS.md`) — no se ha intentado en esta sesión por el
   riesgo de introducir una regresión silenciosa en la lógica de negocio más
   ajustada de todo el proyecto.
3. Mantener la exigencia ya vigente en `AGENTS.MD` de ampliar primero los
   fixtures (`tests/fixtures/*.json`) antes de cualquier cambio de reglas,
   aplicándola también a las nuevas entradas de configuración.
4. Documentar en la propia configuración el motivo y la fecha de cada regla
   añadida, sustituyendo el actual registro narrativo en `AGENTS.MD` por
   metadatos estructurados y trazables junto a cada regla.
5. **[Auditado el 18/08/2026, sesión siguiente, sin cambios de código]** Tras
   ampliar la ventana de BDNS (ver 3.2, quinto/sexto incremento), se auditó
   con datos reales si `_bdns_pre_claude_gate()` necesitaba endurecerse para
   contener el volumen nuevo. Conclusión, con cifras reales (detalle en
   AGENTS.md sección 27): de 948 candidatas detectadas, el 91,9 % (871) se
   descarta de forma determinista sin llamar a Claude y sin ninguna
   revisión manual; solo el 8,1 % (77) llega genuinamente ambiguo. El
   cuello de botella dominante (81 % de los casos en espera de evidencia,
   `territorial_eligibility_unverified`) no es un filtro laxo: es que el
   requisito de "centro ya existente en la comunidad convocante" casi nunca
   aparece en la descripción corta de BDNS, solo en las bases completas en
   PDF — una limitación de datos disponibles, no de la regla en sí. Se
   decidió explícitamente no tocar el filtro por ahora (coste real dentro
   de la barrera de seguridad); quedan documentadas en AGENTS.md sección 27
   dos vías concretas para si se retoma en el futuro (señal por tipo de
   administración vía `nivel2`/`nivel3`, o ampliar los patrones de texto de
   requisito de centro), ambas sujetas a la misma exigencia de fixtures
   primero del punto 3.

### 3.4. Frente a 2.4 — Fragilidad ante cambios en fuentes externas

1. **[Implementado el 18/08/2026]** `assess_web_inventory_health()` ya avisa
   en el momento (log en consola) por cada fuente degradada; se añadió
   además un resumen consolidado al final de `run_pipeline()` que lista
   todas las fuentes `degraded`/`unhealthy` de la ejecución en un único
   bloque, para que no dependa de detectar una línea suelta en medio del
   log de una recopilación larga.
2. Guardar una instantánea periódica (snapshot) de la estructura esperada
   de cada fuente (número mínimo de fichas, columnas esperadas, selectores
   clave) y comparar automáticamente contra ella en cada ejecución
   `--no-claude`, generando una alerta temprana ante desviaciones, tal como
   ya se hace parcialmente pero de forma más sistemática y con historial.
3. Considerar una ejecución periódica automatizada en modo `--no-claude`
   (por ejemplo diaria) exclusivamente para vigilar la salud de las
   fuentes, independiente de la ejecución completa que consume Claude.

### 3.5. Frente a 2.5 — Código muerto y artefactos mezclados

1. **[Implementado el 18/08/2026]** Se eliminaron `_legacy_bdns_cdti_session_scraper()`
   y `_fetch_cdti_playwright_legacy()` (confirmado sin llamadas antes de
   borrar) y se ejecutaron `py_compile` + las 144 pruebas `unittest`
   existentes para verificar que no había regresión (siguieron en verde).
   `LEGACY_TECH_TAG_MAP`/`_legacy_tags_for()`, al no ser código muerto (ver
   corrección de 2.5), no se eliminaron: se renombraron a
   `TECH_TAG_COMPAT_ALIASES`/`_compat_tags_for()` para que el nombre refleje
   su función real (compatibilidad hacia atrás del campo público `tags`, que
   no cambió de nombre ni de valores).
2. No implementado: mover `convocatorias.json` de la raíz rompería la
   publicación actual en GitHub Pages (`index.html` lo carga por ruta
   relativa desde la raíz del sitio) y `AGENTS.MD` lo documenta
   explícitamente como "Salida pública, junto a index.html". Cambiar esa
   ruta es una decisión de publicación, no solo de organización de carpetas;
   se dejó fuera de esta pasada para no arriesgar la publicación. `debug.log`
   y `convocatorias.json` sí quedaron excluidos de git (ver 3.1).

### 3.6. Frente a 2.6 — Exportación XLSX manual sin tests

1. **[Implementado el 18/08/2026]** Ya existía `test_xlsx_export_is_a_styled_filtered_workbook`
   para la integridad estructural (ver corrección de 2.6). Se añadió
   `test_xlsx_and_csv_export_columns_match_the_expected_contract`, que fija la
   lista exacta de columnas de `buildExportTable()` (compartida por XLSX y
   CSV): si alguien añade, quita o reordena una columna sin actualizar el
   test, la suite falla en vez de dejarlo pasar en silencio.
2. Evaluar, solo si el mantenimiento manual empieza a ser costoso, sustituir
   la generación manual de OOXML por una librería ligera y sin dependencias
   de red, priorizando en cualquier caso mantener la exportación 100 %
   local tal como exige el proyecto actualmente.

### 3.7. Frente a 2.7 — Acoplamiento a un único cliente

1. Si en algún momento se plantea reutilizar Grant-Radar para otra empresa,
   extraer el perfil de la empresa objetivo (sector, ubicación, tamaño,
   taxonomía tecnológica) a un fichero de configuración de perfil,
   análogo a la propuesta de 3.3, en vez de tenerlo embebido en las
   funciones de reglas.
2. Mantener esto como mejora condicionada a una necesidad de negocio real
   (nuevo cliente), no como refactor especulativo si el alcance del
   proyecto sigue siendo exclusivamente Kalfrisa.

**[Decisión del 18/08/2026, actualizada]** El texto de perfil de Kalfrisa que
se envía a Claude (`KALFRISA_PROFILE`) ya salió del script, como
consecuencia natural de extraer `grant_radar/tech_taxonomy.py` y
`grant_radar/partner_catalog.py` (ver 3.2): ahora vive en
`grant_radar/kalfrisa_profile.txt`, un archivo de texto plano editable sin
tocar Python. Eso cubre la parte de "datos de cliente" (identidad,
capacidades, programas de interés). Lo que **no** se ha tocado, siguiendo la
recomendación original, son las reglas de negocio que usan ese perfil de
forma implícita (por ejemplo, el reconocimiento de "Zaragoza, Huesca y
Teruel" como Aragón dentro de `_bdns_pre_claude_gate()`): moverlas sería
refactor especulativo sobre código de reglas ya frágil (ver 2.3) sin que
exista todavía un segundo cliente real que lo justifique.

### 3.8. Frente a 2.8 — Validación de contrato frontend-backend

1. **[Implementado el 18/08/2026]** Ver corrección de 2.8: test
   `test_backend_record_fields_are_understood_by_frontend` sobre
   `_assemble_public_record()`, sin red ni Claude. Ya encontró y permitió
   corregir una divergencia real (`eoi_deadline_date`).

### 3.9. Frente a 2.9 — Requisito de Python agresivo

1. **[Implementado el 18/08/2026, con reserva]** Se auditó `Grant-Radar-prueba.py`
   buscando sintaxis exclusiva de Python 3.12+ (`type X = ...`, `except*`,
   genéricos PEP 695) y no se encontró ninguna; el código usa uniones `X | None`
   y genéricos `list[str]`/`dict[...]` disponibles desde Python 3.10. En base a
   eso se relajó `pyproject.toml` a `requires-python = ">=3.11"`. **Esto no se
   ha probado ejecutando realmente sobre un intérprete 3.11**, porque este
   equipo solo tiene instalado Python 3.14 y añadir otra versión completa del
   intérprete para validarlo es un cambio de sistema más invasivo de lo que
   corresponde a este ajuste; antes de depender de esta versión mínima en otra
   máquina, instalar Python 3.11 y ejecutar `poetry install` + la suite
   `unittest` completa ahí para confirmarlo.

### 3.10. Frente a 2.10 — Ausencia de control de versiones

1. **[Implementado el 18/08/2026]** Git no estaba instalado en el equipo (ni
   en PATH ni en las rutas habituales); se instaló Git for Windows 2.55 con
   `winget` (autorizado explícitamente por el usuario) y se ejecutó
   `git init` en esta carpeta, con `.gitignore` ya corregido (3.1) antes del
   primer `git add`. Se creó la rama `main`, se configuró la identidad local
   del repositorio (`user.name`/`user.email`, solo para este repositorio, no
   globalmente) y se añadió `origin` apuntando a
   `https://github.com/GOrtega-KAL/Grant-Radar-CC.git`. **No se ha hecho
   `git push`** todavía: falta el token de GitHub, que el usuario añadirá a
   `.env` (ver 3.1). `GITHUB_REPO` en `Grant-Radar-prueba.py` se actualizó de
   `"Grant-Radar"` a `"Grant-Radar-CC"` para que la publicación desde esta
   copia apunte al repositorio nuevo y no al original.
   Hallazgo colateral: la terminal de este equipo tenía la variable de
   entorno `VIRTUAL_ENV` apuntando al `.venv` de la carpeta `Grant-Radar`
   original, lo que hacía que `poetry run`/`poetry install` ejecutados desde
   esta copia usaran silenciosamente el entorno de la OTRA carpeta. Es un
   riesgo real para el flujo de copiar-y-renombrar que usa este proyecto: dos
   copias del mismo `pyproject.toml` pueden compartir intérprete sin que se
   note. Cada comando de esta sesión limpió esa variable antes de invocar
   `poetry`; queda pendiente revisar por qué la terminal la fija así por
   defecto (perfil de PowerShell o similar) si se quiere evitar en el futuro.
2. No implementado todavía: limpiar `Obsoleto/` y `Frontend alternativo/`
   ahora que hay historial de git es una operación algo más delicada (decidir
   qué snapshot es realmente recuperable vs. descartable) y no es solo un
   cambio de nombre; se deja para una revisión explícita del usuario en vez
   de borrarlo unilateralmente en esta pasada.
3. Pendiente del usuario: mantener esta carpeta como la única copia de
   trabajo activa a partir de ahora.

---

## 4. Estado a 19/08/2026 tras la sesión de modularización

El punto 3.2 de este documento —"dividir el monolito en paquetes por
responsabilidad"— pasó de un primer incremento a estar sustancialmente
completo en una sola sesión de nueve rondas: `Grant-Radar-prueba.py` bajó de
9.199 a 3.842 líneas (-58,2 %), el paquete `grant_radar/` tiene 34 módulos y
8.847 líneas, los ocho conectores de fuentes están extraídos y las pruebas
pasaron de 238 a 381. El balance completo y el orden ya medido de lo que
queda están en `AGENTS.md` sección 39.

Lo que sigue pendiente de 3.2 no es "más de lo mismo": la matriz de reglas
(punto 3.3) merece su propia sesión, y `run_pipeline()` va el último por
definición, porque hoy arrastraría todo lo demás.

## 5. Estado del backlog a 19/08/2026

Los hallazgos abiertos y las propuestas que han ido apareciendo durante las
ocho rondas de modularización de hoy están reunidos, con su motivo y lo que
costaría retomarlos, en **`AGENTS.md` sección 36**: reglas de negocio que
requieren una decisión de negocio antes que código, fragilidad frente a las
fuentes, modularización pendiente con su orden ya medido, huecos de cobertura
de pruebas contados uno a uno, y un mapa de qué caza y qué se le escapa a cada
una de las tres redes de seguridad del proyecto.

Se mantiene ahí y no aquí para que exista un solo índice: este documento es la
evaluación externa del 17/08/2026 y su seguimiento; aquel es el estado vivo.

## 6. Estado a 20/08/2026 tras la ronda de calidad del dato

La sesión del 20/08 no fue de estructura sino de **contenido**: qué datos
recibe el modelo, qué se le pide y qué acaba publicándose. Toca tres puntos de
este documento.

**Frente a 2.6 (regresión de columnas del export XLSX): el hueco descrito se
materializó, y el test hizo su trabajo.** Al añadir la columna «Objeto y
actuaciones» al export, el test que fija el conjunto de columnas falló de
inmediato y obligó a actualizarlo de forma consciente. Es exactamente el
comportamiento que este documento pedía: la divergencia entre lo exportado y lo
esperado no puede pasar en silencio.

**Frente a 2.8 (contrato frontend-backend):** el campo nuevo
`objeto_y_actuaciones` se añadió a la vez en el backend, en `index.html` y en el
export, con el test de contrato verificándolo. Los cinco campos publicados y no
consumidos que señalaba este punto siguen igual (`catalog_scope`,
`catalog_category`, `catalog_ref`, `related_documents_count`, `bdns_url`):
siguen como punto 11 del backlog de `AGENTS.md` sección 36.

**Frente a 2.5 (artefactos generados mezclados con el código):** el caso de
`convocatorias.json` resultó ser más enredado de lo que este documento
suponía. No es solo que conviva con el código en la raíz: está en `.gitignore`
**y a la vez rastreado en el remoto**, porque lo publica el propio pipeline por
la API de Contents de GitHub, que es como GitHub Pages lo sirve, y `.gitignore`
no afecta a un archivo ya rastreado. Separar «fuente» de «salida» aquí no es una
limpieza cosmética: chocaría con el mecanismo de publicación. Anotado como
punto 25 del backlog.

**Recuentos verificados hoy con `wc -l`**, para no arrastrar cifras viejas:
`Grant-Radar-prueba.py` tiene 3.988 líneas (creció desde las 3.842 del 19/08,
porque la capa de análisis con Haiku —que sigue dentro del script— es
justamente la que se enriqueció), el paquete `grant_radar/` tiene 34 módulos y
8.901 líneas, y la suite pasó de 381 a **405 pruebas**, todas en verde.

**Estado del producto:** el pipeline se ejecutó completo y se publicó (76
convocatorias vigentes, 1,83 USD reales), y la barrera de coste se recalibró
con esos 76 análisis en vez de con la muestra de dos de agosto. Balance
completo en `AGENTS.md` secciones 40 a 43; **la 43 es el punto de arranque en
frío vigente**.

---

## 7. Estado a 21/08/2026: dos fallos que ningúna red de seguridad veía

Los detectó el usuario mirando el producto publicado, no una prueba. Merece la
pena anotarlo aquí porque toca dos puntos de esta evaluación.

**Frente a 2.4 (fragilidad ante cambios en fuentes externas).** El catálogo
curado de CDTI tenía **seis de diez URLs en 404**: se teclearon a mano en abril
y caducaron en silencio. Lo grave no es que caducaran —esta evaluación ya
advertía de que los catálogos estáticos envejecen— sino que la comprobación
automática de URLs **daba las seis por buenas**: `cdti.es` está tras un WAF que
responde 200 a cualquier ruta, incluida una inventada, cuando quien pregunta no
parece un navegador. Una verificación que no puede fallar no verifica nada.
Corregido con una sonda de control por host y con una comprobación del catálogo
hecha con el navegador, que sí obtiene el 404 real. Detalle en `AGENTS.md` 44.1
a 44.3.

**Frente a 2.3 (reglas de negocio como código, no como datos).** El prefiltro
temático rechazaba 68 de las 71 fichas del IDAE, incluidas tres cuyo título es
literalmente eficiencia energética en el sector industrial. La causa estaba en
el vocabulario: `industrial_context_terms` nombraba el proceso («procesos
industriales», «horno», «siderurgia») pero no el sector, así que no contenía
«industria» ni «industrial» en ninguna forma. Es exactamente el tipo de fallo
que este documento anticipaba al pedir que las reglas fueran datos revisables:
el vocabulario **sí** está en un JSON, y por eso arreglarlo fueron cuatro líneas
—pero nadie lo había revisado contra casos reales.

Se siguió la disciplina del punto 3.3: primero los casos de prueba con los
títulos textuales del IDAE, que fallaron, y después el vocabulario. Se eligió
la variante conservadora (cinco expresiones concretas) sobre la amplia (la
palabra «industrial» suelta) porque `INDUSTRIAL_CONTEXT_TERMS` alimenta también
la matriz de reglas previa a Claude, y por tanto el coste: medido, la amplia
solo añadía tres casos marginales.

**Una lección sobre las tres redes de seguridad** (`AGENTS.md` 36.5): ninguna de
las tres podía ver estos dos fallos. `py_compile` y la suite no miran hacia
fuera; la ejecución `--no-claude` sí, pero informaba de «1 convocatoria IDAE» y
de «todas las URLs correctas» sin que ninguna de las dos cosas fuera falsa a sus
ojos. Hace falta una cuarta comprobación, más barata que elegante: **mirar de vez
en cuando el producto publicado**.

Estado tras la ronda: **420 pruebas** en verde y una ejecución `--no-claude`
completa con 956 detectadas y 77 vigentes (`AGENTS.md` 44.7).

---

## 8. Estado a 21/08/2026 (tarde): el indicador que había que apagar

Continuación de la sección 7. Allí se arreglaron dos fallos; aquí, la razón de
que ninguno se detectara solo. Toca de lleno el punto 2.4 de esta evaluación.

**El control de salud por fuente tenía los datos y no los miraba.** Medía la
cobertura de fecha contra el **inventario completo**, incluidas las fichas que
nadie llega a abrir. Para el BOE eso daba 1,8 %, una cifra sin sentido, y la
única salida fue fijar su umbral en `0.0` con un comentario que explicaba por
qué. El IDAE ni siquiera lo pasaba. Resultado: las dos fuentes cuyo embudo se
había hundido eran exactamente las dos declaradas `healthy` sin comprobación.
Un indicador que hay que apagar para que no moleste no es un indicador; es
ruido con permiso.

Ahora cada tasa se mide contra su propio denominador —selección sobre el
inventario, carga sobre lo abierto, fecha y publicación sobre lo cargado— y con
eso el BOE pasa de 1,8 % a 26,7 %, que sí lo describe, y su umbral puede
encenderse.

**Una limitación que conviene no maquillar.** Ningún umbral absoluto habría
cazado el caso del IDAE: convertir 71 fichas en 1 convocatoria era el síntoma
del fallo **y** su estado normal. Lo único que delata esa clase de avería es el
cambio, así que se añadió una comparación de cada etapa contra la ejecución
anterior, aprovechando que la auditoría ya guarda 365. Es la primera vez que el
historial de auditoría se usa para algo más que consultarlo a mano.

**Y un hallazgo sobre el BOE que cambia cómo hay que pensar esa fuente.**
Replicando su puerta de listado regla a regla sobre las 168 entradas reales, la
taxonomía técnica admite **cero**: las 8 que se abrían entraban todas por la
excepción de organismo. Es coherente —el listado del BOE son citas legales, sin
una palabra sobre la materia— pero significa que la cobertura de esa fuente la
decide una lista de organismos, no el vocabulario, y esa lista no incluía la
parte industrial. Añadidos Industria y Turismo y SEPIDES: se abren 15 en vez de
8, y las de SEPIDES y Agrupaciones Empresariales Innovadoras ahora se juzgan por
el texto del documento y dejan rastro en la auditoría, en lugar de desaparecer
sin registro.

Estado tras la ronda: **430 pruebas** en verde y una ejecución `--no-claude`
completa con 956 detectadas y 77 vigentes (`AGENTS.md` 45.4).

---

## 9. Estado a 21/08/2026 (cierre): la brecha entre el código y el producto

Al valorar el estado del programa apareció un problema que no está en ninguno de
los diez puntos de esta evaluación, y que conviene añadir: **las mejoras se
acumulaban en el repositorio sin llegar al usuario**. Las dos rondas de ese día
habían corregido seis URLs rotas de CDTI y un prefiltro que descartaba fichas
industriales, y el dashboard seguía sirviendo el JSON del día anterior **con las
URLs rotas dentro**. El pipeline no publica solo.

Se publicó (0,20 USD reales frente a 0,2048 previstos: la calibración de la
sección 6 se valida con un 0,2 % de desviación) y las tres URLs que motivaron
todo salen ya correctas. Pero el patrón queda anotado: mientras la publicación
dependa de una autorización manual, el producto envejece por defecto.

**Frente a 2.4, un hallazgo que amplía el de la sección 8.** La sonda de hosts
opacos se estrenó en una ejecución completa y el problema no era de `cdti.es`:
**nueve hosts** responden 200 a una ruta inexistente —cuatro subdominios de
FECYT, dos sedes electrónicas, `gov.pl`, `manresa.cat`— afectando a 13 URLs
publicadas. Sedes electrónicas y fundaciones públicas, sobre todo. En esas 13,
decir que la URL no está rota no significa nada, y hasta ese día se decía.

**Frente a 2.8**, también se cerró el hueco de cobertura más incómodo:
`coverage_watch.py` —la alarma que avisa cuando un programa recurrente conocido
deja de aparecer— pasa de **cero** pruebas a 18, cubriendo sobre todo la
distinción que importa: `closed_observed` y `seasonal_pending` no son
regresiones, y `active_not_captured` —abierta en su landing y no encontrada— sí.

Estado tras la sesión: **448 pruebas** en verde, producto publicado al día, y un
backlog que crece más rápido de lo que se cierra (32 puntos; esa sesión cerró 2
y abrió 6). No es alarmante todavía, pero la tendencia sí conviene mirarla.

---

## 10. Estado a 21/08/2026: un falso negativo, y un prompt que nadie podía leer

El usuario detectó que **PowerUp NetZero** recibía un 35 % de encaje y salía
descartada, siendo una convocatoria a la que su empresa se presenta. La causa
principal no estaba en ninguno de los diez puntos de esta evaluación, y merece
añadirse porque es un modo de fallo propio de los sistemas con LLM: **el
evaluador contradijo un dato que su propia etapa de extracción había
recuperado**. Los ocho temas admisibles de la convocatoria —uno de ellos de
soluciones digitales, donde la empresa sí encaja— viajaban en su payload, y
razonó solo sobre los cinco titulares de la portada del programa.

**Frente a 2.3 (reglas como código y no como datos), un matiz nuevo.** Aquí las
«reglas» son un prompt y un perfil en texto, que es la forma más blanda posible
de regla. Y precisamente por blanda se degradó sin que nadie lo notara: al
insertar una instrucción el 20/08 se partió por la mitad la frase que explicaba
`consortium_required`, y el evaluador leyó cuatro días una instrucción rota
sobre consorcios. Ninguna de las tres redes de seguridad podía verlo, porque el
prompt de sistema era una **variable local** dentro de la función de análisis.
Ahora es una constante de módulo con pruebas que comprueban que las frases
siguen enteras.

La lección generaliza más allá de este proyecto: **un prompt es código, y si no
se puede leer entero ni probar, se pudre igual que el código**.

**Frente a 2.4 y al punto 3.4, la idea del usuario.** En lugar de automatizar la
llamada de pago, se programa una recopilación `--no-claude` diaria y se mide
cuántas convocatorias esperan análisis, para decidir a mano cuándo pagar. Su
encuadre —«las subvenciones se mueven despacio, la frecuencia útil no baja de 3
días o una semana»— es correcto y evita el error de automatizar el gasto antes
de entender su ritmo. El módulo `staleness.py` no recopila nada: el dato ya
estaba en la auditoría, así que el informe es instantáneo y gratuito.

Estado tras la ronda: **471 pruebas** en verde. La caché queda **invalidada a
propósito** —se subieron perfil, evaluador y prompt—, así que lo publicado sigue
mostrando las puntuaciones antiguas hasta que se autorice una reanálisis
(~1,8 USD). Decisión explícita del usuario: dejarlo listo y no pagar todavía.

---

---

---

## 11. Estado a 31/08/2026: el punto 3.2 llega al final que tenía sentido

La sesión del 31/08 fue de estructura, por decisión expresa del usuario: **no
reanalizar dos veces**, así que primero se termina la modularización y se revisa
la capa de análisis, y solo después se paga una ejecución que publique todo
junto. Toca cuatro puntos de esta evaluación.

**Frente a 2.2 (arquitectura monolítica), el punto 3.2 se puede dar por
cerrado.** `Grant-Radar-prueba.py` pasa de 4.086 a **2.140 líneas** y el paquete
de 35 a **38 módulos** (11.660 líneas). Lo que queda en el script no es residuo:
son la matriz de reglas previa a Claude —526 líneas que el usuario decidió no
tocar fuera de una sesión dedicada— y `run_pipeline()`, el orquestador, que por
definición va el último. Del monolito de 9.199 líneas de agosto queda menos de
una cuarta parte, y ya no hay ninguna pieza que esté ahí por no haberla mirado.

Lo interesante de esta ronda no fue el tamaño, sino que **las dos extracciones
grandes no arrastraban nada**: medido con AST antes de tocar, ni la auditoría ni
la capa de análisis con Haiku llamaban a una sola función del script. Todo lo que
usaban ya estaba en el paquete desde rondas anteriores. Es el retorno diferido de
haber respetado el orden de dependencias en vez de empezar por lo más vistoso.

La única que sí estaba acoplada —la resolución de holds, que llamaba tres veces a
la matriz de reglas— salió con el patrón que este documento pedía en 3.3 y que el
proyecto ya usaba en dos sitios: **inyectar la regla como parámetro** en vez de
importarla. `holds.py` recibe `intrinsic_exclusion` y `prefilter`, así que el día
que la matriz se extraiga no habrá que tocarlo.

**Frente a 2.3 (reglas de negocio como código y no como datos), el matiz de la
sección 10 se lleva a la práctica.** Allí se anotó que un prompt es la forma más
blanda posible de regla y que por blanda se degrada sin que nadie lo note. Hoy
los **dos** prompts de sistema son constantes de módulo con pruebas de
integridad: el del evaluador lo era desde el 21/08, y el de la extracción factual
—que seguía siendo una variable local dentro de la función, el mismo riesgo
exacto— pasa a serlo ahora, con siete pruebas que fijan las instrucciones cuyo
descubrimiento costó dinero.

Con los dos ya legibles de una vez se leyeron enteros, frase por frase. No había
ningún empalme. Sí seguía abierta la instrucción del punto 24 del backlog: decía
«no lo inventes» y el modelo respondía «se presume inversión en equipos…», que no
es una invención sino una presunción declarada. La frase ahora prohíbe la
fórmula, no solo la mentira. Como la caché ya estaba invalidada desde el 21/08,
agrupar ese cambio aquí no ha costado nada — que era justo el motivo de
esperarlo.

**Frente a 2.4 (fragilidad ante las fuentes), dos casos con la misma moraleja.**
Una convocatoria publicaba como URL una frase entera con el esquema mal escrito,
porque el campo `sedeElectronica` de la API de BDNS es texto libre y nadie lo
estaba tratando como tal. Y la prueba que vigila la ventana deslizante de BDNS
fijaba una densidad medida una sola vez, en agosto, que ya no era cierta: con
ella declaraba 79 días de cobertura cuando la medición real de hoy da 67. En los
dos casos el dato de la fuente había cambiado y la comprobación seguía anclada al
día en que se escribió. La corrección, en los dos, es la misma: **medir otra vez
y dejar escrito cuándo se midió** — el comentario del conector lleva ahora las
tres mediciones con su fecha, no una.

**Frente a 2.8 (cobertura), la suite pasa de 471 a 493 pruebas**, todas en verde.
Las 22 nuevas no son relleno: ocho cubren el histórico de auditoría que hasta hoy
solo se ejercitaba de refilón (rotación, migración de esquema v1, exclusiones
huérfanas, archivo ilegible), siete el prompt de extracción, cinco la URL que era
una frase y dos el punto 24.

**Balance del backlog:** se cierran cuatro puntos (22, 24, 31 y 33) y no se abre
ninguno. Es la primera sesión desde el 19/08 en que el backlog baja: quedan
**28 puntos abiertos** de los 34 numerados, frente a los 32 del 21/08.

**Lo que sigue sin hacerse, y conviene no perder de vista:** el producto que ve
el usuario sigue siendo el del 21/08. Todo lo de esta sesión —y el falso negativo
de PowerUp NetZero, corregido hace diez días— está en el repositorio y no en el
dashboard. La sección 9 de este documento ya avisaba del patrón: *mientras la
publicación dependa de una autorización manual, el producto envejece por
defecto*. Diez días después, sigue siendo cierto.

---

---

## 12. Estado a 31/08/2026 (cierre): una regla determinista que dependía de cómo redactara el modelo

Tres encargos del usuario sobre el producto publicado. Los tres tocan puntos de
esta evaluación, y el segundo aporta el ejemplo más claro que ha dado el
proyecto de lo que advierte el punto 2.3.

**Frente a 2.3 (reglas de negocio como código y no como datos).** De las 31
convocatorias no descartadas, 25 se publicaban con la elegibilidad «por
confirmar». Ocho de ellas eran convocatorias territoriales de otras comunidades
—Navarra, Cataluña, Murcia, Asturias…— y el propio texto publicado lo decía:
«la convocatoria limita a ES22 (Navarra)». Existía una regla determinista para
cerrar justo esos casos, pero **decidía leyendo la prosa del modelo**: exigía
que el razonamiento contuviera una de seis expresiones tecleadas a mano. Medido
sobre el corpus real, disparaba en 1 de cada 12 casos.

Es la misma lección de la sección 10 llevada un paso más allá. Allí el problema
era un prompt que se degradaba sin que nadie lo viera; aquí es una regla
**determinista** cuyo dato de entrada era, en la práctica, el estilo de
redacción de un modelo generativo. La corrección es la que este documento pide
en 3.3: decidir sobre datos —el campo `regiones` de la API oficial, que ya
llegaba— y dejar la prosa para explicar, no para decidir. Ocho convocatorias
dejan de pedir confirmación, y no cuesta nada: las salvaguardas deterministas
se reaplican al cargar la caché.

De paso apareció un segundo fallo en la misma regla: el patrón `\bes\d{2}\b`
solo casaba códigos de dos dígitos, así que ES212 (Gipuzkoa), ES614 (Granada) o
ES3 (Madrid) nunca entraban. Media España se escapaba de una regla escrita para
toda ella. Ninguna prueba lo cubría porque el único caso probado usaba ES53.

**Frente a 2.8 (contrato frontend-backend).** La ficha de una convocatoria
imprimía **el mismo texto dos veces**: el motivo de elegibilidad salía entero en
el aviso superior y otra vez como nota de la tarjeta, que se estiraba y
descuadraba la fila de indicadores. La tarjeta pasa a decir qué dato falta para
decidir, leído de `missing_fields`; el razonamiento se queda en un solo sitio.
Es una duplicación que ninguna prueba podía ver porque las dos mitades eran
correctas por separado.

En sentido contrario, se añade un contrato nuevo y deliberado:
`estado_recopilacion.json`, ocho cifras que publica la recopilación diaria sin
llamar a Claude para que el panel avise de cuántas convocatorias esperan
análisis. Es la pieza que faltaba del flujo de la sección 10 —recopilar gratis a
diario, pagar a mano cuando compense—, y responde también a lo que la sección 9
dejó anotado: **mientras la publicación dependa de una autorización manual, el
producto envejece por defecto**; al menos ahora el panel lo dice.

**Frente a 2.4 (fragilidad ante las fuentes), un límite que no es un fallo.**
Las 14 convocatorias que siguen «por confirmar» son de Horizon Europe y CDTI, y
lo están porque **la fuente no publica el dato**: un topic de Horizon son 3.000
caracteres de objetivos y alcance, y quién puede solicitar vive en los Anexos
Generales del programa de trabajo. El modelo declara el dato ausente, que es lo
correcto según su prompt. Resolverlo exige inyectar hechos de programa
versionados, como ya se hace con el bloque oficial de BDNS, y eso crea otro
catálogo mantenido a mano —los dos que existen han caducado en silencio—. Queda
como punto 35 del backlog. **El usuario descartó esa vía y propuso otra mejor**:
que el código busque y lea el propio anexo, para que un cambio de programa no
exija tocar código. Medido el mismo día (AGENTS.md 49.7): la API que ya
consultamos entrega el enlace al anexo de la edición correcta, el PDF son 46
páginas que se leen en dos segundos, y las tres secciones de elegibilidad
existen con título propio. La lección para este documento es del punto 2.4: la
alternativa a un catálogo que envejece no es mantenerlo mejor, es no tenerlo.

Estado tras la ronda: **507 pruebas** en verde (493 antes) y un backlog de **29
puntos abiertos**, uno más que hace un rato: no se cierra ninguno y se abre el
35. A cambio se corrige un fallo que no estaba anotado en ninguna parte, porque
nadie lo había visto hasta que el usuario preguntó por qué su panel decía «por
confirmar» tantas veces.

---

## Nota de alcance

Este documento es una evaluación externa de solo lectura, ampliada con una
verificación puntual de código el 18/08/2026 (grep dirigido sobre puntos
específicos, no una auditoría línea a línea completa del archivo de casi
11.000 líneas). No se ha modificado ningún archivo de `Grant-Radar-prueba.py`,
`index.html`, `tests/` ni la configuración del proyecto durante su
elaboración ni durante su verificación, ni se ha leído ni copiado el
contenido de `API KEYs.txt`, únicamente se ha constatado su existencia y su
ausencia en `.gitignore` como hallazgo de seguridad.
