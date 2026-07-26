# ADR 0002 — Estrategia transaccional de los endpoints idempotentes

- **Estado:** Aceptada
- **Fecha:** 2026-07-25
- **Alcance:** `backend/source/routes/orders_r.py` — los dos endpoints con `Idempotency-Key`:
  `POST /checkout/guest` (`create_guest_checkout_order`) y `POST /admin/sales`
  (`create_admin_sale_endpoint`). Contexto: ticket **R01-8** del tablero
  [idempotencia_http](../18_Roadmap.md) (refactor **R-01**).

---

## Contexto

Los dos endpoints idempotentes manejan la transacción de forma distinta, y esa divergencia fue lo
que originalmente hizo peligroso el copy-paste de la idempotencia inline:

| | `create_guest_checkout_order` | `create_admin_sale_endpoint` |
|---|---|---|
| Dependencia de sesión | `get_db` (commit/rollback manual) | `get_db_transactional` (commit/rollback automático) |
| `FailurePolicy` | `PERSIST` | `DISCARD` |
| En fallo | persiste un record `failed` que sobrevive | descarta el `acquire` vía rollback |
| Camino de recuperación | sí (re-init de Mercado Pago) | no |
| Trabajo post-commit | sí (`dispatch_post_commit_actions`: emails) | no |

El refactor R-01 (tickets R01-1…R01-7) ya **eliminó la duplicación**: ambos endpoints corren sobre el
mismo context manager `idempotent()`, y la única diferencia visible es un parámetro (`failure=PERSIST`
vs `failure=DISCARD`). El árbol de 4 caminos, el `acquire`, el mapeo a 409 y la red de seguridad viven
en un solo lugar testeado.

Queda la pregunta que plantea R01-8: **¿hay que unificar además la dependencia de sesión**, para que
los dos endpoints usen un único patrón transaccional?

## La regla que ya existe

El repo ya tiene una estrategia transaccional documentada —
[`decision-sesion-transaccional.mmd`](../diagrams/decision-sesion-transaccional.mmd):

> ¿Escribe en DB? → ¿Necesita trabajo **después** del commit (emails, llamadas a MP)?
> - **No** → `Depends(get_db_transactional)` ← estrategia por defecto.
> - **Sí** → `Depends(get_db)` + `db.commit()` manual + `dispatch_post_commit_actions()`.

Y ese árbol **ya lista `POST /checkout/guest` como ejemplo del segundo caso**. Es decir: la elección de
`get_db` para el guest no es un accidente ni un smell — es la aplicación correcta de una regla vigente,
porque el guest hace trabajo post-commit (manda mails y llama a Mercado Pago después de commitear).
`POST /admin/sales` no hace trabajo post-commit, así que cae en el default (`get_db_transactional`).

## Decisión

**No** colapsar los dos endpoints a una única dependencia de sesión. Se conserva `get_db` + `PERSIST`
para el guest y `get_db_transactional` + `DISCARD` para el admin.

La unificación que importaba —y que R01-4…R01-7 ya hizo— es la de la **coordinación de idempotencia**:
un solo `idempotent()` como dueño de la relación record ↔ transacción, y un solo enum `FailurePolicy`
que nombra la diferencia. El mecanismo transaccional (qué dependencia) **debe** seguir a la regla del
árbol, no unificarse por su cuenta.

## Por qué no unificar el mecanismo

La divergencia no es un eje independiente: **`FailurePolicy` correlaciona con la estrategia de sesión**,
y las dos correlacionan con tres diferencias de dominio que apuntan todas en la misma dirección.

- **`get_db` + `PERSIST`** (guest): el commit manual es *load-bearing*. Se necesita para (a) persistir
  el estado fallido —orden + pago en `setup_failed` + record `failed`— de modo que un reintento pueda
  **recuperar** re-inicializando Mercado Pago en vez de rehacer todo; y (b) respetar el orden
  **commit → `dispatch_post_commit_actions`**: los mails solo deben salir una vez que la orden está
  durable.
- **`get_db_transactional` + `DISCARD`** (admin): sin trabajo post-commit y sin recuperación, un fallo
  significa "reintentá de cero". El rollback automático descarta el `acquire` y la misma clave queda
  libre. Es el default, y es correcto.

Analizando las dos opciones de unificación que plantea el ticket:

**Opción A — todo a `get_db_transactional`.** El commit del guest pasaría al final, dentro de la
dependencia, *después* de que el handler retorna. Pero `dispatch_post_commit_actions` se llama *dentro*
del handler: correría **antes** del commit y rompería el orden (mails de una orden todavía no durable).
Para evitarlo, el guest tendría que seguir commiteando a mano igual que hoy, y entonces el commit de la
dependencia sería un no-op: `get_db_transactional` prometería administrar una transacción que el guest
ignora. Peor que ser honesto con `get_db`.

**Opción B — todo a `get_db`.** El admin tendría que reintroducir `db.commit()` en el éxito y
`db.rollback()` en el fallo — exactamente el boilerplate que `get_db_transactional` le ahorra, sin
ninguna ganancia.

En ambas, el mecanismo se desalinearía de la necesidad real del endpoint. La elección de dependencia
**refleja** esa necesidad; unificarla la ocultaría.

## El caveat de SAVEPOINT en pysqlite

`acquire_record` inserta el record dentro de un `begin_nested()` (SAVEPOINT). Bajo `DISCARD`, el
rollback de la transacción entera debe descartar ese INSERT. En **PostgreSQL** (producción) funciona;
en **SQLite** (pysqlite, solo tests) el manejo roto de SAVEPOINT deja escapar el INSERT del rollback y
el record queda varado en `processing`.

Este caveat es propio de `DISCARD` y **no cambia con ninguna de las dos opciones** (es del driver, no
del patrón), así que no inclina la decisión. Queda documentado en el `except` de
`create_admin_sale_endpoint` y en el docstring de `FailurePolicy.DISCARD`. `PERSIST` no lo sufre porque
commitea explícitamente y no depende de la semántica de rollback del savepoint.

## Consecuencias

- **El invariante a codificar (R01-9):** `PERSIST` ⇔ `get_db` + commit manual + trabajo post-commit;
  `DISCARD` ⇔ `get_db_transactional`. R01-9 deja de ser "fusionar dependencias" y pasa a ser una tarea
  chica: dejar el invariante explícito (docstrings de `FailurePolicy` / `idempotent()` que remitan al
  árbol de decisión) y confirmar que no quedó coordinación transaccional ad-hoc que el CM debería
  poseer. El grueso del cambio de comportamiento ya ocurrió en R01-5 y R01-7.
- **Nada que migrar:** los dos endpoints ya están en el patrón correcto. La "unificación de la semántica
  transaccional" se cumple a nivel de la abstracción (un CM, un enum), no del mecanismo.
- **Handoff a R-11:** la unificación de los **3 patrones transaccionales** que conviven en
  `orders_r.py` (los endpoints de pago/retry, además de estos dos) excede R-01. Si esa unificación
  quisiera mover trabajo post-commit fuera de los handlers (p. ej. a un middleware o al cierre de la
  dependencia), recién ahí tendría sentido reconsiderar `get_db` vs `get_db_transactional` para el
  guest. Eso es R-11, y depende también de R-04 (emails post-commit).
