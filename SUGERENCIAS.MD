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

## Nota de alcance

Este documento es una evaluación externa de solo lectura, ampliada con una
verificación puntual de código el 18/08/2026 (grep dirigido sobre puntos
específicos, no una auditoría línea a línea completa del archivo de casi
11.000 líneas). No se ha modificado ningún archivo de `Grant-Radar-prueba.py`,
`index.html`, `tests/` ni la configuración del proyecto durante su
elaboración ni durante su verificación, ni se ha leído ni copiado el
contenido de `API KEYs.txt`, únicamente se ha constatado su existencia y su
ausencia en `.gitignore` como hallazgo de seguridad.
