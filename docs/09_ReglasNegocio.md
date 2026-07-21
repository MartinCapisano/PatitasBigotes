# 09 — Reglas de Negocio

← [08 Base de Datos](08_BaseDatos.md) | [Índice](README.md) | Siguiente: [10 Flujos Completos](10_Flujos.md) →

---

Este documento extrae **todas** las reglas de negocio del código y explica **por qué existen**, no solo qué hacen.
Cada regla lleva su referencia al archivo y línea donde está implementada.

---

## 1. Catálogo e inventario

### RN-CAT-01 — Un producto no tiene precio ni stock propios
**Regla:** el precio de un producto es el **mínimo** de sus variantes activas; su stock es la **suma** de ellas.
**Dónde:** `products_s::_product_inventory` y `products_s::_compute_min_var_price`
**Por qué:** el cliente compra un SKU concreto (talle M, color azul), no "el producto". Mostrar "desde $X"
es la convención de e-commerce, y evita inventar un precio de producto que ninguna variante tiene.
**Consecuencia:** un producto sin variantes activas **no aparece** en el storefront
(`products_storefront_s::list_storefront_products` filtra `active_variant_count > 0`) y su detalle devuelve 404.

### RN-CAT-02 — Desactivar un producto desactiva todas sus variantes
**Dónde:** `products_s::update_product`
**Por qué:** `products` no tiene columna `active`; el estado se deriva de las variantes. Para que "desactivar
producto" signifique algo, hay que propagarlo.
⚠️ **Efecto no deseado:** reactivar el producto reactiva **todas** las variantes, incluidas las que estaban
desactivadas individualmente. Se pierde información sin aviso.

### RN-CAT-03 — El SKU es único en todo el sistema
**Dónde:** `product_variants.sku UNIQUE` (`models.py:72`) + validación en `products_s::create_variant` y `products_s::update_variant`
**Por qué:** el SKU es el identificador comercial; duplicarlo rompería la trazabilidad de inventario.

### RN-CAT-04 — No se puede borrar una categoría con productos
**Dónde:** `products.category_id` con `ondelete="RESTRICT"` (`models.py:48`)
**Por qué:** evitar productos huérfanos.
**En la UI:** el panel calcula `deletableCategories` y solo ofrece borrar las vacías.

### RN-CAT-05 — No se puede borrar un producto que se vendió
**Dónde:** `order_items.product_id` con `ondelete="RESTRICT"` (`models.py:253`)
**Por qué:** las órdenes históricas deben seguir siendo legibles.
⚠️ El error que llega al usuario es el genérico `database constraint violation` (409), no un mensaje explicativo.

### RN-CAT-06 — El precio nunca puede ser negativo
**Dónde:** `CHECK price >= 0` en `product_variants` + `Field(gt=0)` en los DTOs de admin
**Nota:** el modelo permite `0`, los DTOs exigen `>0`. Es una inconsistencia menor: se puede crear una variante
gratis por migración o seed, pero no por API.

---

## 2. Precios y descuentos {#descuentos}

### RN-DESC-01 — Los descuentos NO se acumulan: gana el que más ahorra
**Regla:** de todos los descuentos aplicables a un producto, se aplica **exactamente uno**: el que produce el
mayor descuento absoluto sobre el precio unitario.
**Dónde:** `discount_s.select_best_discount` (`discount_s.py:306-316`)
**Por qué:** evita que promociones superpuestas (por ejemplo, "20% en toda la tienda" + "$5.000 en alimento")
lleven un producto a precio cero o negativo, y hace el precio final predecible.
> 📌 **Esta regla no está documentada en ningún comentario del código.** Se deduce de la implementación. Es una
> de las reglas más importantes del negocio y merece estar escrita.

### RN-DESC-02 — Ante empate, gana el descuento de menor `id`
**Dónde:** `select_best_discount` usa `>` estricto, así que el primero de la iteración gana; `list_discounts`
ordena por `Discount.id.asc()` (`discount_s.py:85`).
**Por qué:** determinismo. No hay una razón de negocio detrás; es un efecto del orden de iteración.

### RN-DESC-03 — Un descuento nunca deja el precio en negativo
**Dónde:** `money_s.py:74-75` → `if discount_amount > unit_price: discount_amount = unit_price`
**Por qué:** un descuento fijo de $10.000 sobre un producto de $3.000 debe dejarlo en $0, no en −$7.000.
**Verificado en:** `tests/test_money_amounts.py`

### RN-DESC-04 — Cuatro alcances mutuamente excluyentes
| Scope | Requiere | Prohíbe |
|---|---|---|
| `all` | — | `category_id`, `product_id` |
| `category` | `category_id` existente | `product_id` |
| `product` | `product_id` existente | `category_id` |
| `product_list` | `product_ids` no vacío | `category_id`, `product_id` |

**Dónde:** `discount_s._validate_discount_payload` (`discount_s.py:226-257`) **y** el `CHECK`
`ck_discounts_scope_target_consistency` en la base (`models.py:597-608`).
**Por qué:** doble defensa. La validación en Python da mensajes útiles; el `CHECK` impide estados imposibles
aunque alguien escriba en la base a mano.

### RN-DESC-05 — Un descuento porcentual va de 1 a 100
**Dónde:** `discount_s._normalize_discount_value` (`discount_s.py:57-58`)
**Por qué:** 0% no es un descuento; >100% daría precio negativo (aunque RN-DESC-03 lo atajaría).

### RN-DESC-06 — Vigencia por ventana temporal opcional
**Regla:** un descuento aplica si `is_active` **y** (`starts_at` es nulo o ya pasó) **y** (`ends_at` es nulo o
no pasó).
**Dónde:** `discount_s.is_discount_currently_valid` (`discount_s.py:260-277`)
**Por qué:** permite programar promociones con antelación y que caduquen solas.

### RN-DESC-07 — El redondeo monetario es half-up a 2 decimales
**Dónde:** `money_s.round_half_up_decimal` con `ROUND_HALF_UP`
**Por qué:** es la convención comercial en Argentina. El default de Python (`ROUND_HALF_EVEN`, "banker's
rounding") redondearía 0,125 a 0,12 en vez de 0,13, lo que en un catálogo produce diferencias sistemáticas.

### RN-DESC-08 — Borrar un descuento no altera las órdenes pasadas
**Dónde:** `order_items.discount_id` con `ondelete="SET NULL"` (`models.py:268`)
**Por qué:** `order_items` guarda `discount_amount` y `final_unit_price` como snapshot; perder la referencia al
descuento no cambia lo que se cobró.

---

## 3. Carrito y órdenes

### RN-ORD-01 — El carrito de un usuario autenticado ES una orden en estado `draft`
**Dónde:** `orders_s::get_or_create_draft_order`
**Por qué:** evita una tabla `carts` paralela y permite reutilizar toda la maquinaria de precios e ítems.
**Consecuencia:** solo puede haber **un** draft por usuario; si hubiera varios, se toma el más reciente
(`ORDER BY created_at DESC, id DESC`).

### RN-ORD-02 — El carrito del invitado vive en `localStorage`, no en el servidor
**Dónde:** `frontend/src/lib/cart-storage.ts`
**Por qué:** sin sesión no hay a quién asociar la orden, y crear usuarios anónimos por cada visita llenaría la
tabla `users` de basura.
**Consecuencia:** el carrito del invitado no sobrevive a cambiar de dispositivo ni de navegador.

### RN-ORD-03 — Máquina de estados de la orden
```
draft ──→ submitted ──→ paid        (paid solo vía endpoint de pago)
  │            │
  └──→ draft   └──→ cancelled
```
**Dónde:** `orders_s::ORDER_ALLOWED_TRANSITIONS`
**Reglas asociadas:**
- `paid` y `cancelled` son **terminales**: no se sale de ellos.
- Una transición al mismo estado es válida (idempotente).
- **`paid` no se puede setear desde `PATCH /orders/{id}/status`**: `_assert_transition_preconditions` lo rechaza
  con `"paid status must be set through a payment endpoint"` (`orders_s::_assert_transition_preconditions`).
  **Por qué:** el estado `paid` implica dinero cobrado. Solo puede llegar de un pago confirmado (manual) o del
  proveedor (webhook/reconciliación). Si se pudiera setear por API, un cliente marcaría su orden como pagada.

### RN-ORD-04 — No se puede salir de `draft` con la orden vacía
**Dónde:** `orders_s::_assert_transition_preconditions`
**Por qué:** una orden sin ítems no tiene sentido ni total.

### RN-ORD-05 — Al pasar a `submitted` se congelan los precios
**Regla:** `submitted` fija `pricing_frozen = True` y `pricing_frozen_at`; a partir de ahí `_recalculate_order_total`
lanza `"cannot recalculate a frozen order"` salvo con `force=True`.
**Dónde:** `orders_s::_recalculate_order_total` y `orders_s::change_order_status`
**Por qué:** el cliente vio un precio al confirmar. Si el admin cambia el precio o expira un descuento mientras
el pago está en curso, el importe **no debe** moverse. Sin esto, un cliente podría pagar un importe distinto del
que aceptó.

### RN-ORD-06 — Los ítems solo se editan en `draft`
**Dónde:** `orders_s::replace_draft_order_items`
**Por qué:** después de `submitted` hay stock reservado y precio congelado; cambiar ítems invalidaría ambos.

### RN-ORD-07 — Las cantidades del mismo `variant_id` se agregan
**Dónde:** `orders_s::_normalize_requested_items`
**Por qué:** si el frontend envía dos líneas del mismo SKU, la orden debe tener una sola con la suma. Evita
duplicados y hace la reserva de stock coherente (una reserva activa por `order_item`).

### RN-ORD-08 — Máximo 10 unidades por variante y 20 líneas en el checkout de invitado
**Dónde:** `schemas/orders_s.py:40` (`quantity gt=0 le=10`) y `:46` (`items min_length=1 max_length=20`)
**Por qué:** anti-abuso. Un invitado sin cuenta no debería poder reservar 500 unidades y bloquear el inventario.
**Nota:** estos límites **no aplican** al checkout autenticado (`ManualOrderItemRequest` solo exige `gt=0`).

### RN-ORD-09 — Cancelar una orden libera su stock
**Dónde:** `orders_s::change_order_status` → `release_reservations_for_cancelled_order(reason="order_cancelled")`
**Por qué:** el inventario debe volver a estar disponible de inmediato, sin esperar a la expiración.

---

## 4. Stock y reservas {#stock}

Es el subsistema con más reglas implícitas y el que más impacta en la operación.

### RN-STK-01 — Stock disponible ≠ stock físico
```
disponible(variante) = variante.stock − Σ(reservas activas con expires_at > now)
```
**Dónde:** `stock_reservations_s._available_stock_for_variant` (`stock_reservations_s.py:85-95`)
**Por qué:** entre que un cliente confirma la compra y paga pueden pasar horas. Ese stock no está vendido, pero
tampoco disponible. Descontarlo del stock físico haría imposible distinguir "vendido" de "reservado".

### RN-STK-02 — La reserva ocurre al pasar a `submitted`, no al agregar al carrito
**Dónde:** `orders_s::change_order_status` → `reserve_stock_for_submitted_order`
**Por qué:** reservar al agregar al carrito permitiría a cualquiera agotar el inventario sin comprometerse.
Reservar al confirmar es el equilibrio estándar del e-commerce.

### RN-STK-03 — Si falta stock para **un** ítem, no se reserva **nada**
**Dónde:** `stock_reservations_s.py:245-257` — primera pasada valida todo, segunda inserta
**Por qué:** una orden parcialmente reservada es peor que ninguna: el cliente pagaría por algo que no se le
puede entregar completo.

### RN-STK-04 — TTL de reserva: 42 horas
**Dónde:** `RESERVATION_TTL_HOURS = 42` (`stock_reservations_s.py:11`)
**Por qué (hipótesis razonada):** 42 h ≈ un día y tres cuartos. Cubre el escenario "compro el viernes a la
noche, pago el domingo a la tarde" incluyendo fin de semana.
**Hipótesis:** el valor exacto no está justificado en ningún comentario.

### RN-STK-05 — Una reserva vencida puede reactivarse **una sola vez**, por 12 horas
**Dónde:** `RESERVATION_REACTIVATION_TTL_HOURS = 12`, `MAX_RESERVATION_REACTIVATIONS = 1`
(`stock_reservations_s.py:12-13`), lógica en `_expire_active_reservations_internal`
**Por qué:** dar una segunda oportunidad al cliente que se demoró, sin permitir que retenga stock
indefinidamente. La ventana corta (12 h vs 42 h) comunica urgencia.
**Condición:** solo se reactiva si **hay stock disponible para todos los ítems** en ese momento. Si otro cliente
se llevó el inventario mientras tanto, no se reactiva.

### RN-STK-06 — Si la reserva no se puede reactivar, la orden se CANCELA
**Dónde:** `stock_reservations_s.py:165-181` y `:205-219`
**Por qué:** una orden `submitted` sin stock reservado no se puede cumplir. Dejarla abierta generaría una
promesa que no se puede honrar.
**Efectos en cascada:**
1. `orders.status = 'cancelled'`, `cancelled_at = now`.
2. Se publica `order_cancelled` con `reason = "expiracion de reserva"` → notificación al admin.
3. **Todos los pagos `pending` de la orden pasan a `cancelled`** con
   `provider_status = 'order_cancelled_reservation_expired'` (`stock_reservations_s.py:98-109`).
> ⚠️ Esta cancelación **no pasa por `orders_s.change_order_status`**, así que salta la validación de
> transiciones y el logging asociado. Es un camino paralelo de mutación de estado.

### RN-STK-07 — Las reservas se expiran de forma perezosa, no solo por job
**Dónde:** `expire_active_reservations_for_order` se invoca en 9 puntos distintos: al crear un pago, al
reintentar, al confirmar manualmente, al aplicar estado del proveedor, al cambiar el estado de la orden, al
listar reservas, al consumir, al liberar y al armar el snapshot público.
**Por qué:** el job corre cada 13 minutos (o cada 15 en local). Sin la expiración perezosa, un cliente podría
pagar en una ventana en la que su reserva ya venció pero nadie la barrió.

### RN-STK-08 — El stock físico se descuenta al PAGAR, con compare-and-swap
**Dónde:** `stock_reservations_s.py:319-332`
```sql
UPDATE product_variants SET stock = stock - :qty
WHERE id = :variant_id AND stock >= :qty      -- ← la condición hace la operación atómica
```
Si `rowcount != 1` → `ValueError("insufficient stock for variant N")`.
**Por qué:** es el único momento en que el inventario real baja, y debe ser seguro ante concurrencia sin
depender del orden de bloqueos.

### RN-STK-09 — Consumir reservas es idempotente
**Dónde:** `stock_reservations_s.py:305-317` — si no hay activas pero sí `consumed` y la orden está `paid`,
devuelve las consumidas en lugar de fallar.
**Por qué:** un webhook de Mercado Pago puede llegar dos veces. Sin esta salvaguarda, el segundo intento
descontaría el stock una segunda vez.

### RN-STK-10 — Como máximo una reserva activa por línea de orden
**Dónde:** índice parcial `uq_stock_reservation_active_per_item` (`models.py:544-550`)
**Por qué:** convierte la regla en garantía del motor, no en un chequeo en Python que podría perder una carrera.

---

## 5. Pagos

### RN-PAY-01 — Solo se puede pagar una orden en estado `submitted`
**Dónde:** `payment_s::create_payment_for_order`
**Por qué:** un `draft` no está confirmado; un `cancelled` no debe cobrarse; un `paid` ya se cobró.

### RN-PAY-02 — Sin reservas activas no se puede crear un pago
**Dónde:** `payment_s::create_payment_for_order` → `if not list_active_reservations_for_order(...): raise ValueError(...)`
**Por qué:** cobrar sin stock reservado es prometer algo que puede no existir. Es la regla que conecta
inventario y cobro.

### RN-PAY-03 — Solo se acepta ARS
**Dónde:** `payment_s::create_payment_for_order`
**Por qué:** el negocio opera en Argentina. Los campos `currency` existen para una futura expansión pero hoy
cualquier otro valor se rechaza.

### RN-PAY-04 — Como máximo un pago `pending` por (orden, método)
**Dónde:** índice parcial `uq_payments_one_pending_per_order_method` (`models.py:290-297`)
**Por qué:** evita que el cliente genere N links de Mercado Pago simultáneos para la misma orden y pague dos
veces. El sistema devuelve el pendiente existente en vez de crear otro (`payment_s::create_payment_for_order`, vía `payment_core_s::find_active_pending_payment`).

### RN-PAY-05 — Los pagos en efectivo no vencen
**Dónde:** `payment_s::create_payment_for_order` → `expires_at = None if method == "cash" else now + timedelta(...)`
**Por qué:** un pago en efectivo se concreta en el mostrador; no tiene sentido que expire por tiempo.

### RN-PAY-06 — Regla de importe según método
| Método | Regla |
|---|---|
| `bank_transfer` | `paid_amount == total_amount` exacto; `change_amount` prohibido; `payment_ref` obligatorio |
| `cash` | `paid_amount − change_amount == total_amount`; `change_amount` obligatorio (≥0); `payment_ref` autogenerado si falta |
| `mercadopago` | El importe lo fija el sistema; se **valida** contra lo que informa el proveedor |

**Dónde:** `payment_s::confirm_manual_payment_for_order`
**Por qué:** en efectivo el cliente entrega de más y recibe vuelto — eso es normal y debe registrarse. En
transferencia el importe es exacto por naturaleza.

### RN-PAY-07 — Transiciones de estado del pago
```
pending → {paid, cancelled, expired}     paid → paid     cancelled → cancelled     expired → expired
```
**Dónde:** `payment_core_s::ALLOWED_PAYMENT_TRANSITIONS`

### RN-PAY-08 — Excepción "paid revival": un pago cancelado o expirado PUEDE pasar a `paid`
**Dónde:** `payment_provider_s::apply_mercadopago_normalized_state`
```python
allow_paid_revival = internal_status == "paid" and str(payment.status) in {"cancelled", "expired"}
if not allow_paid_revival:
    assert_valid_payment_transition(payment.status, internal_status)
```
**Por qué:** la realidad manda sobre el estado local. Si Mercado Pago dice que el pago se aprobó, **el dinero
existe**, aunque nosotros hubiéramos dado el intento por perdido. Rechazar la actualización dejaría el sistema
mintiendo sobre un cobro real.
**Consecuencia:** se genera una `PaymentIncident` para revisión humana (RN-PAY-13).
> 📌 Esta es la regla **menos obvia** del sistema. Quien lea `ALLOWED_PAYMENT_TRANSITIONS` sin ver esta excepción
> sacará conclusiones erróneas.

### RN-PAY-09 — Un pago cancelado NO cancela la orden
**Dónde:** `payment_provider_s::apply_mercadopago_normalized_state`, con comentario explícito
**Por qué:** que falle una tarjeta no significa que el cliente desista. La orden sigue `submitted` y puede
reintentar con otro método o la misma tarjeta.

### RN-PAY-10 — El webhook valida importe, moneda y referencia externa
**Dónde:** `payment_provider_s::apply_mercadopago_normalized_state`
```python
if payment_external_ref != external_reference: raise ValueError("external_reference does not match payment")
if normalized_amount is not None and int(payment.amount) != normalized_amount: raise ValueError("payment amount mismatch")
if normalized_currency is not None and payment.currency.upper() != normalized_currency: raise ValueError("payment currency mismatch")
```
**Por qué:** 🔒 aunque la firma HMAC ya autentica el origen, esto impide que un evento legítimo del proveedor
—referido a otro pago, o con un importe alterado— marque como pagada una orden por un monto incorrecto.
Defensa en profundidad.

### RN-PAY-11 — Reintentar un pago tiene 6 condiciones
| # | Condición | Mensaje |
|---|---|---|
| 1 | La orden no está cancelada | `retry not allowed: order cancelled` (o `...because stock reservation expired`) |
| 2 | La orden no está pagada | `retry not allowed: order already paid` |
| 3 | La orden sigue `submitted` | `retry not allowed: order is no longer submitted` |
| 4 | Hay reservas de stock activas | `retry not allowed: stock reservation expired` |
| 5 | El último intento está `cancelled`/`expired`, **o** es un `pending` con `setup_failed` | `retry not allowed: payment state changed` |
| 6 | El checkout del proveedor responde | **502** `retry failed: mercadopago checkout unavailable` |

**Dónde:** `payment_s::_guard_order_retryable`, `payment_s::create_retry_payment_for_order` y `payment_s::create_retry_payment_for_payment_token`
**Por qué:** cada condición corresponde a un escenario real de soporte. Los mensajes son específicos para que el
frontend explique al cliente **qué** pasó, no un genérico "error".

### RN-PAY-12 — Un pago con `setup_failed` se cancela antes de reintentar
**Dónde:** `payment_s::create_retry_payment_for_order`
**Por qué:** ese pago quedó `pending` pero sin `preference_id` (falló la creación de la preferencia). Si no se
cancelara, el índice único de pago pendiente por método bloquearía el nuevo intento.

### RN-PAY-13 — Un pago aprobado sobre orden cancelada o duplicada genera una incidencia
**Dónde:** `payment_provider_s::apply_mercadopago_normalized_state` → `refund_s.create_late_paid_incident_if_needed`
**Casos:**
| Situación | Motivo registrado |
|---|---|
| La orden ya estaba `cancelled` | `mercadopago approved after order cancellation` |
| La orden ya estaba `paid` con **otro** pago aprobado | `mercadopago approved but order already had another paid payment` |

**Por qué:** hay dinero cobrado que probablemente hay que devolver, pero **la decisión es de una persona**: quizá
el cliente acepta que se le entregue igual, quizá hay que reembolsar. El sistema no lo decide solo.

### RN-PAY-14 — El `public_status_token` es una capability, no una identidad
**Dónde:** `models.py:323-329` (`secrets.token_urlsafe(32)`, único), usado en `orders_s`, `payment_s`,
`mercadopago_normalization_s.py:256-264`
**Regla:** quien posea el token puede **consultar** el estado de ese pago y **reintentarlo**, sin sesión.
**Por qué:** un invitado que compró sin cuenta y volvió de Mercado Pago no tiene forma de identificarse. El token
viaja en la `back_url` y le permite continuar.
🔒 32 bytes = 256 bits de entropía; no es adivinable. No permite ver datos de otras órdenes ni modificar nada
más que reintentar ese pago.

---

## 6. Reembolsos

### RN-REF-01 — Solo se reembolsan pagos de Mercado Pago en estado `paid`
**Dónde:** `refund_s.py:262-265`
**Por qué:** los cobros en efectivo y transferencia se devuelven fuera del sistema; no hay API que ejecutar.

### RN-REF-02 — El reembolso no puede superar el importe del pago
**Dónde:** `refund_s.py:267-271`

### RN-REF-03 — Un solo reembolso activo por pago
**Dónde:** índice parcial `uq_payment_refunds_active_per_payment` (`models.py:408-414`)
**Por qué:** evita reembolsar dos veces el mismo cobro por una carrera entre dos administradores.

### RN-REF-04 — El motivo del reembolso es obligatorio
**Dónde:** `refund_s.py:230-232` + `Field(min_length=1, max_length=500)` en el DTO + validación en el cliente
**Por qué:** trazabilidad. Junto con `resolved_by_user_id` y `resolved_at`, deja registro de quién devolvió qué
y por qué.

### RN-REF-05 — Un reembolso fallido queda registrado
**Dónde:** `refund_s.py:351-378` — commit explícito del estado `failed` dentro del `except`
**Por qué:** sin ese commit, el rollback del wrapper transaccional borraría el intento. Un reembolso que se
intentó y falló **debe** quedar visible para reintentarlo o escalarlo.

### RN-REF-06 — Resolver una incidencia con reembolso ya hecho es idempotente
**Dónde:** `refund_s.py:243-256` — si la incidencia ya está `resolved_refunded`, devuelve el refund existente.

---

## 7. Idempotencia {#idempotencia}

### RN-IDEM-01 — Dos niveles de defensa
| Nivel | Mecanismo | Alcance |
|---|---|---|
| **HTTP** | `IdempotencyRecord` con `(scope, idempotency_key)` UNIQUE | `POST /checkout/guest`, `POST /admin/sales` |
| **Entidad** | `payments.idempotency_key` UNIQUE | Todos los endpoints de creación de pago |

**Por qué dos:** el nivel HTTP protege una *operación compuesta* (crear usuario + orden + reserva + pago). El
nivel entidad protege el recurso concreto aunque la operación llegue por otro camino (job, admin).

### RN-IDEM-02 — La misma clave con otro payload es un error, no un replay
**Dónde:** `orders_r.py:175-179` → **409** `idempotency key already used with a different payload`
**Por qué:** si el cliente reusa la clave con datos distintos, es un bug del cliente, no un reintento. Devolver
la respuesta anterior sería peor: el usuario creería que su nuevo pedido se procesó.
**Cómo se detecta:** SHA-256 del payload canonicalizado (`json.dumps(sort_keys=True, separators=(",",":"))`),
que es determinista independientemente del orden de las claves.

### RN-IDEM-03 — Un registro `failed` de checkout guest permite RECUPERACIÓN, no solo replay
**Dónde:** `orders_r.py:182-225`
**Regla:** si el registro está `failed` y guardó `order_id` y `payment_id`, un reintento con la misma clave
**vuelve a intentar inicializar el checkout de Mercado Pago** sobre el pago ya creado.
**Por qué:** el caso real es "la orden y el pago se crearon bien, pero Mercado Pago estaba caído". Volver a
crear todo generaría una orden duplicada; reintentar solo el paso que falló es lo correcto.
> 🟢 Esta es una de las decisiones de diseño más sofisticadas del sistema.

### RN-IDEM-04 — Un registro atascado en `processing` se libera a los 30 minutos
**Dónde:** `idempotency_sweeper_job.py:27-44`
**Por qué:** si el proceso murió a mitad del checkout, el registro quedaría `processing` para siempre y el
cliente recibiría 409 eternamente.

### RN-IDEM-05 — TTL de 24 horas
**Dónde:** `IDEMPOTENCY_TTL_HOURS = 24` (`idempotency_s.py:12`)
**Por qué:** equilibrio entre proteger reintentos razonables y no acumular registros con datos personales.

### RN-IDEM-06 — El scope del checkout guest incluye el email
**Dónde:** `idempotency_s.build_guest_checkout_scope` → `checkout_guest:{email}`
**Por qué:** dos clientes distintos podrían generar la misma clave por casualidad (o maliciosamente). Aislar por
email impide que uno vea la respuesta del otro. 🔒

---

## 8. Webhooks

### RN-WH-01 — Todo webhook debe traer firma HMAC válida y reciente
**Dónde:** `mercadopago_d.is_mercadopago_signature_valid`
**Reglas:** manifiesto `id:{data_id};request-id:{request_id};ts:{ts};`, HMAC-SHA256 con el secreto,
comparación en tiempo constante, y `ts` dentro de `[now − 300s, now + 60s]`.
**Por qué:** sin esto cualquiera podría marcar órdenes como pagadas. La ventana temporal previene replay de un
webhook legítimo capturado.

### RN-WH-02 — Cada evento se procesa una sola vez
**Dónde:** `webhook_events.event_key UNIQUE` + `acquire_webhook_event`
**Clave:** `mp:event:{id}` si el payload trae `id`; si no, `mp:{topic}:{data_id}:{action}`.
**Por qué:** Mercado Pago reintenta los webhooks. Sin deduplicación, un pago se procesaría N veces.

### RN-WH-03 — "Pago no encontrado" es reintentable; el resto de no-ops no
**Dónde:** `mercadopago_client._is_retryable_noop_error` (`mercadopago_client.py:53-56`) y `:410-423`
**Por qué:** `payment not found` suele ser una carrera — el webhook llegó antes de que se commiteara el pago
local. Reintentar lo resuelve. En cambio, "topic no soportado" o "evento duplicado" nunca cambiarán, y
reintentarlos sería un bucle infinito.

### RN-WH-04 — Backoff exponencial con dead letter al cuarto intento
**Dónde:** `reprocess_failed_webhooks_job.py:77-87`
```
delay = min(max_delay, base_delay × 2^(intento−1))     # 30 → 60 → 120 min, tope 720
```
**Por qué:** un fallo transitorio se resuelve rápido; uno persistente no debe consumir recursos indefinidamente.
El dead letter lo hace visible para intervención humana.

### RN-WH-05 — Un evento fallido o en dead letter puede revivir
**Dónde:** `webhook_events_s.py:89-99` (si llega otra notificación equivalente) y
`replay_webhook_event_by_key` (si un admin lo dispara)
**Por qué:** dar una vía de recuperación manual sin tocar la base.

---

## 9. Autenticación e identidad

### RN-AUTH-01 — Un usuario no verificado NO puede iniciar sesión
**Dónde:** `auth_s.py:85-86`
**Por qué:** confirmar que el email es real antes de permitir comprar con cuenta.
⚠️ **Efecto lateral:** cambiar el email desde el perfil pone `email_verified_at = NULL`, así que el usuario
queda bloqueado hasta reverificar (su sesión actual sigue viva hasta expirar).

### RN-AUTH-02 — El invitado no puede loguearse: hash centinela `"!"`
**Dónde:** `users_s.py:245-246` con comentario
**Por qué:** un invitado tiene fila en `users` (para asociarle órdenes) pero no cuenta. El hash `"!"` no es un
hash válido de passlib, así que `verify_password` siempre devuelve `False`
(captura `UnknownHashError` en `auth_security_s.py:27-29`).

### RN-AUTH-03 — Registrarse con el email de un invitado ASCIENDE esa cuenta
**Dónde:** `users_s.py:76-88`
**Por qué:** el cliente que compró como invitado y luego se registra debe conservar su historial de órdenes.
Crear un segundo usuario duplicaría su identidad.

### RN-AUTH-04 — Política de password: ≥8 caracteres y ≥1 especial
**Dónde:** `auth_security_s.ensure_password_policy` (`auth_security_s.py:32-38`)
⚠️ No exige mayúsculas ni dígitos, y no hay verificación contra listas de passwords comunes.

### RN-AUTH-05 — Una sola sesión activa por usuario
**Dónde:** `user_refresh_sessions.user_id UNIQUE` + upsert en `_upsert_refresh_session`
**Por qué:** simplifica la revocación (basta borrar una fila) a costa de no soportar multi-dispositivo.
**Consecuencia:** loguearse en el teléfono cierra la sesión de la computadora.

### RN-AUTH-06 — El refresh es rotativo e invalida el access token anterior
**Dónde:** `auth_s.py:156` → `bump_user_token_version` dentro de `refresh_with_token`
**Por qué:** si alguien robó el access token, deja de servir en cuanto el usuario legítimo refresca.
**Cómo funciona:** el access token lleva el claim `tv`; `auth_d.py:51` lo compara con `users.token_version`.

### RN-AUTH-07 — Cambiar o resetear la password cierra TODAS las sesiones
**Dónde:** `auth_s.set_user_password_and_invalidate_sessions` (`auth_s.py:189-217`)
**Por qué:** es el comportamiento esperado tras una sospecha de compromiso.

### RN-AUTH-08 — Los endpoints públicos de email no revelan si la cuenta existe
**Dónde:** `auth_r.py:227-255` y `:277-304` — siempre responden `{requested: true}`
**Por qué:** 🔒 evitar enumeración de usuarios.
⚠️ **Pero el login sí filtra información**: devuelve `403 email not verified` en vez de `401 invalid credentials`
cuando el email existe pero no está verificado.

### RN-AUTH-09 — Un token de acción invalida a los anteriores del mismo tipo
**Dónde:** `auth_tokens_s.create_one_time_token` → `invalidate_active_tokens` (`auth_tokens_s.py:85`)
**Por qué:** si el usuario pide "recuperar password" tres veces, solo el último enlace debe funcionar.

### RN-AUTH-10 — TTL de tokens: 24 h para verificación, 30 min para reset
**Dónde:** `auth_s.py:24-25`
**Por qué:** el reset de password es más sensible; una ventana corta reduce la exposición si el email se
compromete.

### RN-AUTH-11 — Revocar admin: no a uno mismo, y con efecto inmediato
**Dónde:** `users_s.revoke_admin_status` (`users_s.py:146-185`)
**Por qué:** impedir autorevocarse evita quedarse sin ningún administrador. Incrementar `token_version` y borrar
la sesión corta el acceso al instante, sin esperar a que expire el JWT.

---

## 10. Anti-abuso y rate limiting

### RN-ABU-01 — Login: 6 fallos en 15 min → bloqueo de 20 min, por email Y por IP
**Dónde:** `auth_rate_limit_s.py:10-12`
**Por qué:** dos dimensiones porque un atacante puede rotar IPs (el límite por email lo frena) o probar muchos
emails desde una IP (el límite por IP lo frena).
**Detalle:** un login exitoso limpia ambos contadores (`clear_login_failures`).

### RN-ABU-02 — Operaciones públicas: triple límite
| Dimensión | Límite | Constante |
|---|---|---|
| Por IP | 20 requests / 5 min | `IP_MAX_REQUESTS`, `IP_WINDOW` |
| Por email (ventana) | 6 requests / 10 min | `EMAIL_MAX_REQUESTS`, `EMAIL_WINDOW` |
| Por email (intervalo) | 1 cada 20 s | `EMAIL_MIN_INTERVAL_SECONDS` |

**Dónde:** `anti_abuse_s.py:11-15`
**Aplica a:** signup, checkout guest, solicitud de reset de password, reenvío de verificación.
**Por qué el intervalo mínimo:** frena el "usuario nervioso" que hace clic 10 veces, sin castigarlo con un
bloqueo largo.

### RN-ABU-03 — Honeypot en el checkout de invitado
**Dónde:** campo `website` con `max_length=0` (`schemas/orders_s.py:47`) + verificación en
`anti_abuse_s.py:149-153`
**Por qué:** los bots rellenan todos los campos del formulario. Un campo invisible que llega con contenido
delata al bot sin molestar al humano. Doble validación (Pydantic + servicio).

### RN-ABU-04 — El contador de fallos persiste aunque el login devuelva error
**Dónde:** `auth_r.py:99-100` y `:111-112` — `db.commit()` explícito dentro del `except`
**Por qué:** si no se commiteara, el rollback del wrapper borraría el registro del fallo y el rate limiting
nunca se activaría.

---

## 11. Turnos de peluquería

### RN-TUR-01 — Solo de lunes a viernes
**Dónde:** `turns_s.py:58-59` → `if int(local_dt.weekday()) > 4: raise ValueError(...)`

### RN-TUR-02 — Solo entre 13:00 y 20:00, hora de Buenos Aires
**Dónde:** `turns_s.py:60-64`, zona `America/Argentina/Buenos_Aires` (`turns_s.py:10`)
**Detalle:** un `scheduled_at` sin zona se **interpreta** en horario de Buenos Aires; uno con zona se
**convierte** antes de validar. 🟢 Correcto.

### RN-TUR-03 — Un turno solo transiciona desde `pending`
**Dónde:** `turns_s.py:133-135`
**Por qué:** confirmar o cancelar un turno ya resuelto no tiene sentido.

### RN-TUR-04 — No hay control de capacidad ni de solapamiento
**Dónde:** ausencia de validación en `create_turn_for_user`
⚠️ Se pueden crear N turnos para el mismo minuto. **Hipótesis:** aceptable si la confirmación es manual y la
peluquería coordina por teléfono, pero es una limitación real si el volumen crece.

---

## 12. Notificaciones y eventos

### RN-NOT-01 — Cuatro eventos de dominio
| Evento | Cuándo | Efecto |
|---|---|---|
| `order_submitted` | Orden pasa a `submitted` | Notificación al admin |
| `order_paid` | Orden pasa a `paid` | Notificación al admin **+ email al cliente** (post-commit) |
| `order_cancelled` | Orden pasa a `cancelled` (manual o por expiración) | Notificación al admin, con motivo |
| `possible_refund_detected` | Se crea una `PaymentIncident` | Notificación al admin |

**Dónde:** `domain_events_s.py`

### RN-NOT-02 — Las notificaciones se deduplican por `dedupe_key`
**Dónde:** `notifications_s._find_by_dedupe_key` + `notifications.dedupe_key UNIQUE`
**Claves usadas:** `admin:order:{id}:submitted`, `admin:order:{id}:paid`, `admin:order:{id}:cancelled`,
`admin:incident:{id}:possible_refund`
**Por qué:** reprocesar un webhook no debe generar cinco notificaciones idénticas.

### RN-NOT-03 — Los emails se envían DESPUÉS del commit
**Dónde:** `post_commit_actions_s.py`
**Por qué:** un fallo de SMTP no debe revertir un pago, y no debe enviarse un email de una transacción que se
revirtió. Los routers llaman `clear_post_commit_actions` en el `except` y `dispatch_post_commit_actions` tras el
commit.
**Consecuencia:** es *best-effort*. Si el proceso muere entre commit y dispatch, el email se pierde sin registro.

### RN-NOT-04 — Las ventas presenciales NO envían email de orden pagada
**Dónde:** `orders_s::create_admin_sale` → `set_skip_order_paid_email(db, True)` con restauración en `finally`
**Por qué:** el cliente está físicamente en el mostrador con su comprobante. Mandarle un email sería ruido.

---

## 13. Resumen: dónde vive cada regla

| Mecanismo | Cuántas reglas | Ejemplos |
|---|---|---|
| Constraints de base (`CHECK`, `UNIQUE`, índices parciales) | ~15 | Precios ≥0, un pago pendiente por método, una reserva activa por ítem |
| Validación Pydantic (DTOs) | ~40 | Rangos, longitudes, `Literal`, `extra="forbid"` |
| Código de servicio | ~60 | Transiciones, reprecio, reservas, idempotencia |
| Constantes de módulo | ~20 | TTLs, límites de rate, mapeos de estado |
| Validación en el frontend | ~10 | Máximo 10 por variante, host de MP, `reason` obligatorio |

> 📌 **Lo más valioso de esta arquitectura:** las invariantes concurrentes (no dos pagos pendientes, no dos
> reservas activas, no dos reembolsos activos) están expresadas como **índices parciales únicos** en PostgreSQL,
> no como chequeos en Python. Eso las hace correctas bajo concurrencia por construcción, no por suerte.

---

← [08 Base de Datos](08_BaseDatos.md) | [Índice](README.md) | Siguiente: [10 Flujos Completos](10_Flujos.md) →
