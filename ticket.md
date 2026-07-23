# ORD-1 — Bookkeeping de idempotencia en `orders_r`

**Rama:** `ord-1-refactor-orders-r` (base: `4418291` en `main`)
**Estado:** cerrado. El refactor grande se revirtió; queda un cambio chico.
**Tests:** 367 passed + 29 subtests (baseline) → **384 passed**

---

## 1. Qué se hizo finalmente

| Commit | Qué |
|---|---|
| `94c8725` | No marcar `failed` en el rollback del checkout de invitado |
| `e2ed537` | `sanitize_failure_payload()` movida a `idempotency_s` + 7 tests |
| `24f4abf` | **Revert** de la capa de bookkeeping con sesión separada |
| *(este)* | Vencimiento local en `acquire_record()`; fuera el prune del request path |

---

## 2. El plan original y por qué se abandonó

El plan era separar la sesión del bookkeeping de la de negocio, para que
`processing` fuera durable y `failed` sobreviviera al rollback. Se llegó a
escribir la capa entera (`IdempotencyClaim`, `claim()`, `attach_intent()`,
`complete()`, `fail()`, `release()`, 27 tests) antes de cablearla.

Al revisar qué compraba realmente, caso por caso contra lo que `orders_r` ya
hace en producción:

- **MercadoPago está apagado.** [render.yaml:61](render.yaml:61) lo fija en
  `"false"`, [config.py:31](backend/source/db/config.py:31) defaultea a
  deshabilitado y [payment_core_s.py:151](backend/source/services/payment_core_s.py:151)
  lo rechaza en el kernel. Sin handoff al proveedor no hay
  `PaymentCheckoutInitializationError`, así que **los casos 6, 7 y 7b son
  inalcanzables** — y ahí estaba toda la complejidad de la capa.
- **El caso 5 ya sale bien.** En una sola transacción el rollback descarta el
  INSERT del acquire y la clave queda libre: exactamente el destino que el plan
  le asignaba. Funciona por compartir transacción, no por diseño, pero funciona.
- **I3 / `attach_intent` resolvía un problema del propio refactor.** La ventana
  entre el commit de negocio y el del bookkeeping solo existe si se separan las
  sesiones. Con una sola hay un commit y no hay ventana.
- **El caso 8 es casi inalcanzable.** Requiere un `processing` varado, y en
  Postgres una caída de conexión hace rollback del lado del server.

Lo único que quedaba en pie era el **caso 4**: un duplicado concurrente espera
en el índice único en vez de recibir un 409 inmediato. Es latencia en un caso
raro, no una incorrección. No justifica la capa.

**Se revirtió `4ed8bef`, `b6e6eea` y `c8aa9a0`.** `sanitize_failure_payload()`
se conservó: no depende de la sesión separada y tiene su propia suite. Queda sin
llamadores en `source/` hasta que MercadoPago se reactive.

---

## 3. El cambio que sí se hizo: vencimiento local

El índice `uq_idempotency_records_scope_key` ([models.py:686](backend/source/db/models.py:686))
no sabe de `expires_at`, así que un record vencido igual colisiona y vuelve como
`record_created=False`:

- si estaba `completed` → replay de una respuesta rancia, pasado su TTL;
- si estaba `processing` → 409 eterno.

Algo tiene que volver usable una clave vencida. Hasta ahora era
`prune_expired_records()` llamado al inicio de cada request, y eso era un
problema propio:

- scan + delete de hasta 200 filas **ajenas al request**, dentro de la
  transacción del checkout; esos deletes toman locks de fila y se commitean con
  la orden → dos checkouts concurrentes se pelean por filas vencidas que ninguno
  pidió, con el sweeper como tercer escritor;
- en el camino de falla el rollback tira las bajas: trabajo hecho y descartado;
- la política de TTL quedaba implementada dos veces.

**Ahora el chequeo vive dentro de `acquire_record()`**, acotado a la clave que se
está adquiriendo: si la fila que colisiona está vencida, se borra *esa* fila y se
re-inserta. O(1), toca solo lo que el request ya iba a tocar.

Esto se dispara en **todos** los checkouts, con MercadoPago prendido o apagado —
por eso es el único pedazo del plan que valía la pena solo.

El GC masivo queda como único dueño del sweeper
([maintenance_s.py:107](backend/source/services/maintenance_s.py:107)). Si el
sweeper no corriera, las filas vencidas se acumulan pero **ninguna clave queda
trabada**: la corrección no depende de él, solo el espacio en disco.

Detalles fijados por los tests:

- el borde es inclusivo (`expires_at <= now`), igual que `prune_expired_records`;
- la fila de reemplazo toma el `request_hash` nuevo — una clave vencida está
  genuinamente libre y otro payload puede tomarla sin disparar el 409;
- si otro request se lleva la clave entre el delete y el insert, gana él y este
  reporta la colisión como siempre.

---

## 4. Qué queda abierto

- **Caso 4** — el duplicado concurrente bloquea en vez de 409 inmediato. Conocido
  y aceptado. La capa revertida está en `c8aa9a0` si alguna vez molesta.
- **El sweeper fabrica `failed` sin ids.**
  [idempotency_sweeper_job.py:38](backend/source/jobs/idempotency_sweeper_job.py:38)
  marca los `processing` varados como `failed` con `{"detail": "processing
  timeout"}`, sin `order_id` ni `payment_id`, y eso deja la clave respondiendo
  502 permanente 24 h en vez de ser reintentable. Bug real pero **sin entradas
  hoy** (§2: los `processing` varados casi no ocurren en Postgres). Limpieza
  barata, no prioridad.
- **`sanitize_failure_payload()` sin llamadores** en `source/`. Se reactiva junto
  con MercadoPago.

---

## 5. Fuera de alcance

El `idempotency_key` a nivel `Payment`
([payment_core_s.py:198](backend/source/services/payment_core_s.py:198)) es otro
mecanismo: resuelve pagos, no requests. No se toca.
