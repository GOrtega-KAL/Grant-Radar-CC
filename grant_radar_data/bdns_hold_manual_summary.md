# Revisión manual de casos BDNS en `hold_manual`

Generado a partir de la ejecución `--no-claude` iniciada el
`2026-08-06T12:08:19.838502+00:00` y del ajuste territorial posterior para la
convocatoria BDNS 922175. El informe no procede de Claude y no altera la caché
ni `convocatorias.json`.

## Inventario

| Prioridad orientativa | Casos |
|---|---:|
| Alta | 66 |
| Media | 254 |
| Baja | 136 |
| **Total** | **456** |

| Motivo automático | Alta | Media | Baja | Total |
|---|---:|---:|---:|---:|
| `territorial_eligibility_unverified` | 61 | 0 | 27 | 88 |
| `supplier_role_unverified` | 4 | 0 | 0 | 4 |
| `cluster_role_unverified` | 1 | 0 | 0 | 1 |
| `active_status_unverified` | 0 | 254 | 109 | 363 |
| **Total** | **66** | **254** | **136** | **456** |

La prioridad solo ordena la revisión. No equivale a encaje ni sustituye una
decisión. Se eleva cuando el título contiene señales industriales, energéticas,
ambientales o empresariales, o cuando debe verificarse una vía de proveedor o
clúster.

## Cómo revisar el CSV

Abrir `bdns_hold_manual_review.csv` con separador punto y coma y trabajar por
`orden_revision`. Las primeras columnas son editables:

- `estado_revision`: cambiar `pendiente` por `revisado` cuando exista decisión.
- `decision_manual`: usar únicamente `retain`, `reject` o `needs_data`.
- `notas_revisor`: anotar la evidencia concreta y, si existe, la página o
  documento donde se encontró.

Interpretación recomendada:

1. `active_status_unverified`: confirmar un cierre futuro o una ventanilla
   expresamente abierta. Sin evidencia vigente, usar `reject`.
2. `territorial_eligibility_unverified`: distinguir centro previo, mera
   localización del proyecto y apertura posterior. Si exige abrir centro, solo
   usar `retain` con al menos 730 días confirmados de ejecución.
3. `supplier_role_unverified`: usar `retain` únicamente si equipos,
   instalaciones o ingeniería compatibles con Kalfrisa son gasto elegible.
4. `cluster_role_unverified`: usar `retain` si el apoyo llega a empresas miembro,
   pilotos o costes empresariales; rechazar funcionamiento o estructura del
   clúster.

## Uso posterior

Las decisiones manuales deben convertirse, cuando sea posible, en reglas
generales basadas en datos o expresiones verificables. No crear excepciones por
título o BDNS. Antes de activar nuevas reglas hay que añadir casos a los fixtures,
medir falsos positivos y comprobar que INNOVAE, PowerUp y los positivos conocidos
siguen conservándose.
