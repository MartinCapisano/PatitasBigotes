# 19 — Glosario

← [18 Roadmap](18_Roadmap.md) | [Índice](README.md) | Siguiente: [20 Diccionario de Objetos](20_DiccionarioObjetos.md) →

---

Términos propios del dominio y de la implementación de PatitasBigotes, en orden alfabético. Cada entrada indica
dónde vive el concepto en el código.

---

## A

### Access Token
JWT de vida corta (120 min por defecto) que autentica cada request. Viaja en la cookie **HttpOnly** `pb_at`.
Contiene los claims `sub` (id de usuario), `type="access"`, `is_admin`, **`tv`** (token version), `iss`, `iat` y
`exp`.
📍 `auth_security_s.create_access_token` · `auth_cookies_s.set_auth_cookies`

### Admin Sale (Venta admin / venta de mostrador)
Venta presencial creada por un administrador en un solo paso: crea (o busca) al cliente, crea la orden, reserva
stock, la marca `submitted` y opcionalmente confirma el cobro dejándola `paid`.
🔇 **No envía email al cliente**, porque está físicamente presente.
📍 `POST /admin/sales` · `orders_s.create_admin_sale`

### `AuthActionToken` (Token de acción)
Token de **un solo uso** para verificar el email o restablecer la contraseña. Solo se guarda su hash SHA-256; el
token crudo únicamente viaja por email. Crear uno nuevo invalida los activos del mismo `(usuario, acción)`.
📍 `auth_tokens_s` · tabla `auth_action_tokens`

### `AuthLoginThrottle` (Throttle)
Fila de control de tasa identificada por `(scope, key)`. Un mismo esquema sirve para 15 propósitos distintos
(login por email, login por IP, signup, checkout guest, reset de password, reenvío de verificación).
📍 `auth_rate_limit_s` · `anti_abuse_s` · tabla `auth_login_throttles`

---

## B

### Backoff exponencial
Estrategia de reintento donde el retraso se duplica en cada intento: `min(max_delay, base × 2^(n−1))`.
Con los defaults: 30 → 60 → 120 minutos, con techo de 720.
📍 `reprocess_failed_webhooks_job._retry_delay_minutes_for_attempt`

### `bank_transfer` (Transferencia bancaria)
Método de pago manual. Genera instrucciones estáticas (alias, banco, referencia `ORDER-{n}-PAY-{m}`) y queda
`pending` hasta que un administrador lo confirma con el comprobante.
📍 `payment_s._build_bank_transfer_payload`

### `blocking_reason` (Motivo de bloqueo)
Campo del snapshot público que explica por qué el cliente **no** puede continuar ni reintentar su pago. Seis
valores: `order_paid`, `order_cancelled`, `payment_pending`, `payment_not_retryable`,
`stock_reservation_expired`, `checkout_unavailable`.
📍 `orders_s.get_public_order_snapshot_by_payment_token`

---

## C

### Capability token
Token que otorga un permiso concreto por el mero hecho de poseerlo, sin identificar a quién lo usa. En este
sistema: **`public_status_token`**.
📍 Ver *Public Status Token*

### Carrito
- **Usuario autenticado:** es una **orden en estado `draft`** en la base. No hay tabla `carts`.
- **Invitado:** vive en `localStorage` del navegador (clave `pb_cart_items`).
📍 `orders_s.get_or_create_draft_order` · `frontend/src/lib/cart-storage.ts`

### `cash` (Efectivo)
Método de pago manual sin vencimiento (`expires_at = NULL`). Admite `change_amount` (vuelto): la regla de importe
es `paid_amount − change_amount == total_amount`.
📍 `payment_s.confirm_manual_payment_for_order`

### Categoría (`Category`)
Agrupación de productos. Su `name` es único. No se puede borrar si tiene productos (`ondelete=RESTRICT`).
Puede ser el destino de un descuento con `scope='category'`.
📍 tabla `categories`

### Checkout
Proceso de convertir un carrito en una orden `submitted` con un pago asociado. Dos variantes:
- **Guest:** un solo endpoint con idempotencia obligatoria.
- **Autenticado:** tres requests secuenciales (reemplazar ítems → submit → crear pago).
📍 `POST /checkout/guest` · `checkout-api.submitAuthenticatedCheckoutFromCart`

### Compare-and-swap (CAS)
Técnica de actualización atómica sin bloqueo: se ejecuta el `UPDATE` con la condición en el `WHERE` y se verifica
el `rowcount`. Se usa para descontar stock al pagar.
```sql
UPDATE product_variants SET stock = stock - :qty WHERE id = :id AND stock >= :qty
```
📍 `stock_reservations_s.consume_reservations_for_paid_order`

### Cold start
Los 30–60 segundos que tarda Render (free tier) en responder la primera request tras 15 minutos de inactividad.
Condiciona el timeout del cliente (60 s) y la existencia del ping de mantenimiento cada 13 minutos.
📍 `http.ts:4-7` · `maintenance.yml`

### CSRF (Cross-Site Request Forgery)
Ataque en el que un sitio malicioso hace que el navegador de la víctima envíe una request autenticada. Se
defiende validando que `Origin` o `Referer` estén en la allowlist para todo método mutante.
📍 `dependencies/csrf_d.py`

---

## D

### Dead Letter
Estado final de un evento de webhook que agotó sus reintentos (4 por defecto). Requiere intervención manual vía
`POST /admin/webhooks/mercadopago/replay`.
📍 `webhook_events.dead_letter_at` · `webhook_events_s.mark_webhook_event_failed`

### `dedupe_key` (Clave de deduplicación)
Identificador único de una notificación que impide crear duplicados al reprocesar un evento.
Formato: `admin:order:{id}:paid`, `admin:incident:{id}:possible_refund`, etc.
📍 `notifications_s._find_by_dedupe_key`

### Descuento (`Discount`)
Regla de precio con cuatro alcances (`scope`) y dos tipos (`percent` de 1 a 100, o `fixed` en centavos).
📌 **Los descuentos no se acumulan:** de todos los aplicables, gana el que produce el mayor ahorro absoluto.
📍 `discount_s` · tabla `discounts`

### DiscountProduct
Tabla puente para descuentos con `scope='product_list'`. PK compuesta `(discount_id, product_id)`.
📍 tabla `discount_products`

### `draft` (Borrador)
Estado inicial de una orden. Es el carrito del usuario autenticado: se pueden editar ítems y los precios se
recalculan con los descuentos vigentes. Solo puede haber un draft por usuario.
📍 `orders_s`

### Domain Event (Evento de dominio)
Hecho de negocio relevante que dispara efectos secundarios. Hay cuatro: `order_submitted`, `order_paid`,
`possible_refund_detected`, `order_cancelled`.
⚠️ **No se persisten**: `publish_domain_event` es un despacho **síncrono in-process**, no un bus ni un event
store.
📍 `domain_events_s`

---

## E

### `event_key` (Clave de evento)
Identificador único de un webhook, usado para deduplicar. Se construye como `mp:event:{id}` si el payload trae
`id`, o `mp:{topic}:{data_id}:{action}` si no.
📍 `mercadopago_client._build_mp_event_key`

### `expired` (Expirado)
- **Pago:** superó su `expires_at` sin confirmarse.
- **Reserva:** superó su `expires_at`; puede reactivarse una vez o provocar la cancelación de la orden.

### `external_ref` (Referencia externa)
Identificador que comparten el sistema y Mercado Pago para correlacionar un pago.
Formato: `mp-order-{order_id}-pay-{payment_id}`. El webhook lo valida contra el pago local.
📍 `mercadopago_normalization_s._build_mercadopago_payload`

---

## F

### `FOR UPDATE`
Cláusula SQL que bloquea las filas seleccionadas hasta el fin de la transacción, evitando modificaciones
concurrentes.
⚠️ **En SQLite (los tests) es un no-op silencioso**, por lo que la corrección concurrente del sistema no está
verificada por ningún test.
📍 Usado en `orders`, `payments`, `product_variants`, `stock_reservations`, `users` y más

---

## G

### Guest (Invitado)
Cliente que compra sin cuenta. Se le crea una fila en `users` con `has_account=false` y el hash centinela `"!"`,
que impide autenticarse. Si más tarde se registra con el mismo email, **esa fila se asciende** y conserva su
historial de órdenes.
📍 `users_s.get_or_create_user_by_contact`

---

## H

### Hash centinela `"!"`
Valor del campo `password_hash` de los invitados. No es un hash válido de passlib, así que `verify_password`
siempre devuelve `False` (captura `UnknownHashError`). Es el mecanismo que impide que un invitado se loguee.
📍 `users_s.py:245-246` · `auth_security_s.py:27-29`

### Honeypot
Campo de formulario invisible para el usuario (`website`, con `max_length=0`) que los bots tienden a rellenar.
Si llega con contenido, la request se rechaza.
📍 `schemas/orders_s.py:47` · `anti_abuse_s.py:149-153`

---

## I

### Idempotencia
Propiedad por la cual repetir una operación produce el mismo resultado que ejecutarla una vez. En este sistema
opera en **dos niveles**:
1. **HTTP:** `IdempotencyRecord` con `(scope, idempotency_key)` único + hash del payload.
2. **Entidad:** `payments.idempotency_key` único.
📍 `idempotency_s` · [09_ReglasNegocio.md](09_ReglasNegocio.md#idempotencia)

### `IdempotencyRecord`
Fila que registra una operación idempotente en curso o completada. Estados: `processing`, `completed`, `failed`.
TTL de 24 horas.
📌 Un registro `failed` de checkout guest habilita **recuperación**, no solo replay: el reintento con la misma
clave vuelve a intentar únicamente el paso que falló.
📍 tabla `idempotency_records`

### `Idempotency-Key`
Header HTTP que el cliente genera (`{prefijo}_{uuid}`) para identificar de forma única una operación.
Obligatorio en `POST /checkout/guest` y en los tres endpoints de creación de pago.
📍 `frontend/src/services/idempotency.ts`

---

## J

### `jti` (JWT ID)
UUID4 único de cada refresh token. Se guarda en `user_refresh_sessions.token_jti` y se valida junto con el hash
del token, dando una segunda dimensión de verificación.
📍 `auth_security_s.construir_claims_refresh`

---

## L

### `late_paid_duplicate` (Cobro tardío o duplicado)
Único tipo de `PaymentIncident`. Se genera cuando Mercado Pago aprueba un pago pero:
- la orden ya estaba `cancelled`, o
- la orden ya estaba `paid` con **otro** pago aprobado.
📍 `refund_s.create_late_paid_incident_if_needed`

---

## M

### Mercado Pago
Pasarela de pago (Argentina). El sistema usa **Checkout Pro**: crea una *preferencia*, redirige al cliente, y
recibe la confirmación por webhook firmado con HMAC.
📍 `mercadopago_client` · `mercadopago_normalization_s`

### `min_var_price` (Precio mínimo de variante)
Precio de un producto en el catálogo: el **mínimo** entre sus variantes activas. El storefront devuelve además
`min_var_price_original` (sin descuento) y `min_var_price_final` (con el mejor descuento aplicado).
📍 `products_s._compute_min_var_price` · `_build_storefront_product_pricing`

---

## N

### `Notification` (Notificación)
Aviso in-app. Puede dirigirse a un usuario concreto (`user_id`) o a un rol (`role_target='admin'`).
⚠️ Hoy **solo se crean notificaciones de admin**; el soporte para clientes existe en el modelo pero no tiene
emisor.
📍 `notifications_s` · tabla `notifications`

---

## O

### `option_axis` (Eje de opciones)
Campo del detalle de producto que indica cómo etiquetar el selector de variante en el frontend.
Valores: `"size"` (si alguna variante tiene talle), `"color"`, o `"variant"` (genérico).
📍 `products_s._storefront_option_axis`

### Orden (`Order`)
Entidad central de la compra. Cuatro estados: `draft` → `submitted` → `paid` | `cancelled`.
📌 `paid` **no es alcanzable** desde el endpoint de cambio de estado: solo lo setean los caminos de pago.
📍 `orders_s` · tabla `orders`

### `OrderItem` (Línea de orden)
Snapshot inmutable de un producto comprado: guarda `unit_price`, `discount_id`, `discount_amount`,
`final_unit_price` y `line_total` **al momento del submit**.
⚠️ `discount_amount` es **por unidad**, no por línea.
📍 tabla `order_items`

---

## P

### `paid revival` (Resurrección a pagado)
Excepción a las transiciones de pago: si Mercado Pago informa `approved` sobre un pago local `cancelled` o
`expired`, la validación de transición **se omite** y el pago pasa a `paid`, generando una `PaymentIncident`.
**Razón:** el dinero se cobró de verdad; rechazar la actualización dejaría el sistema mintiendo.
📍 `payment_s.py:373-375`

### `Payment` (Pago)
Intento de cobro. Tres métodos (`bank_transfer`, `mercadopago`, `cash`) y cuatro estados (`pending`, `paid`,
`cancelled`, `expired`). Una orden puede acumular varios.
📌 Como máximo **un** pago `pending` por `(orden, método)`, garantizado por índice único parcial.
📍 `payment_s` · tabla `payments`

### `PaymentIncident` (Incidencia de pago)
Registro de un cobro que llegó cuando no debía y requiere decisión humana: reembolsar o justificar por qué no.
📍 `refund_s` · tabla `payment_incidents`

### `PaymentRefund` (Reembolso)
Solicitud de devolución de dinero a través del proveedor. Estados: `requested`, `approved`, `failed`.
Tiene su propia clave de idempotencia derivada de `(incident_id, payment_id, amount)`.
📍 `refund_s.create_mercadopago_refund` · tabla `payment_refunds`

### Post-commit action
Acción encolada en `db.info` que solo se ejecuta **después** del commit de la transacción. Hoy se usa para el
email de "orden pagada", de modo que un fallo de SMTP no revierta un pago.
📍 `post_commit_actions_s`

### Preferencia (Preference)
Objeto de Mercado Pago que representa una intención de cobro: ítems, importe, URLs de retorno, URL de
notificación y vencimiento. Su `id` se guarda en `payments.preference_id`.
📍 `mercadopago_client.create_checkout_preference`

### `pricing_frozen` (Precio congelado)
Flag que se activa al pasar una orden a `submitted`. A partir de ahí `_recalculate_order_total` se niega a
recalcular los totales, para que un cambio de precio o el fin de un descuento no altere el importe que el
cliente ya aceptó.
📍 `orders_s.py:314-316`

### `public_status_token` (Token público de estado)
Cadena de 32 bytes urlsafe (256 bits) generada por pago. Es un **capability token**: quien lo posee puede
consultar el estado y **reintentar** ese pago sin autenticarse. Se inyecta en las `back_urls` de Mercado Pago
para que el invitado pueda volver y continuar.
📍 `models.generate_public_status_token` · `orders_s.get_public_order_snapshot_by_payment_token`

---

## R

### Reactivación de reserva
Segunda (y última) oportunidad para una reserva vencida: si hay stock disponible para **todos** los ítems de la
orden, las reservas vuelven a `active` con un TTL de 12 horas y `reactivation_count += 1`.
Si ya se reactivó una vez, o si no hay stock, **la orden se cancela**.
📍 `stock_reservations_s._expire_active_reservations_internal`

### Reconciliación
Proceso que consulta a Mercado Pago el estado real de los pagos que llevan entre 15 minutos y 24 horas en
`pending`, para cerrar el círculo cuando el webhook no llegó.
📍 `reconcile_pending_payments_job`

### Refresh Token
JWT de vida larga (30 días) que permite obtener un nuevo access token. Viaja en la cookie `pb_rt` con path
acotado a `/auth`. Se guarda **hasheado** en `user_refresh_sessions`.
📌 **Es rotativo:** cada refresh emite un par nuevo e incrementa `token_version`, invalidando los access tokens
anteriores.
📍 `auth_s.refresh_with_token`

### Replay (de webhook)
Reprocesamiento manual de un evento en estado `failed` o `dead_letter`, disparado por un administrador.
📍 `POST /admin/webhooks/mercadopago/replay` · `webhook_events_s.replay_webhook_event_by_key`

### Reserva de stock (`StockReservation`)
Bloqueo temporal de unidades de una variante para una línea de orden concreta. TTL de 42 horas.
Estados: `active`, `consumed`, `released`, `expired`.
📌 Como máximo **una** reserva `active` por `order_item_id`, garantizado por índice único parcial.
📍 `stock_reservations_s` · tabla `stock_reservations`

---

## S

### `scope` (Alcance)
Tiene **dos** significados según el contexto:
1. **Descuento:** a qué alcanza — `all`, `category`, `product`, `product_list`.
2. **Idempotencia / throttle:** espacio de nombres de la clave — `checkout_guest:{email}`,
   `admin_sales:{admin_id}`, `email`, `ip`, `public_signup_ip`, …

### SKU (Stock Keeping Unit)
Identificador comercial único de una variante. Es lo que realmente se vende y se inventaría.
📍 `product_variants.sku UNIQUE`

### Snapshot público
Vista sin autenticación del estado de una orden y su pago, obtenida con el `public_status_token`. Incluye
`order`, `payment`, cuatro `flags` y un `blocking_reason`.
📍 `GET /public/orders/by-payment-token`

### Stock disponible vs stock físico
- **Stock físico** (`product_variants.stock`): unidades que existen.
- **Stock disponible**: `stock − Σ(reservas activas no vencidas)`.
El stock físico solo baja **al pagar**.
📍 `stock_reservations_s._available_stock_for_variant`

### `submitted` (Enviada)
Estado de una orden confirmada por el cliente: precios congelados, stock reservado, esperando pago.

### Sweeper (Barredor)
Job que libera los `IdempotencyRecord` atascados en `processing` más de 30 minutos y poda los expirados.
📍 `idempotency_sweeper_job`

---

## T

### `token_version` (`tv`)
Entero en `users` que se incrementa en cada refresh, logout, cambio/reset de password y revocación de admin.
Cada access token lleva su valor como claim `tv`; el backend compara en **cada** request y rechaza si difieren.
📌 **Es el mecanismo de invalidación global de sesiones del sistema.**
📍 `auth_s.bump_user_token_version` · `auth_d.get_current_user`

### Turno (`Turn`)
Cita de peluquería canina. Estados: `pending`, `confirmed`, `cancelled`. Solo lunes a viernes de 13:00 a 20:00,
hora de Buenos Aires.
⚠️ Sin control de solapamiento ni de capacidad.
📍 `turns_s` · tabla `turns`

---

## U

### `UserRefreshSession` (Sesión de refresh)
Fila que representa la sesión activa de un usuario. `user_id` es **único** → una sola sesión por usuario.
Guarda el hash del refresh token, su `jti` y todos los claims.
📍 tabla `user_refresh_sessions`

---

## V

### Variante (`ProductVariant`)
Unidad realmente vendible de un producto: combinación de talle, color, precio y stock, identificada por su SKU.
📌 Un producto **no tiene precio ni stock propios**: ambos se derivan de sus variantes activas.
📍 tabla `product_variants`

---

## W

### `WebhookEvent`
Registro de un evento recibido del proveedor, con su `event_key` único para deduplicar, contador de intentos,
próxima fecha de reintento y marca de dead letter.
📍 `webhook_events_s` · tabla `webhook_events`

### Webhook
Notificación HTTP que Mercado Pago envía al backend cuando cambia el estado de un pago. Autenticada por firma
HMAC-SHA256 con ventana anti-replay de 300 segundos.
📍 `POST /payments/webhook/mercadopago` · `mercadopago_d.is_mercadopago_signature_valid`

---

## Abreviaturas y siglas

| Sigla | Significado | Contexto |
|---|---|---|
| **ARS** | Peso argentino | Única moneda soportada |
| **ASGI** | Asynchronous Server Gateway Interface | Interfaz de Uvicorn/FastAPI |
| **CAS** | Compare-and-swap | Descuento atómico de stock |
| **CDN** | Content Delivery Network | Vercel/Cloudflare |
| **CI** | Continuous Integration | GitHub Actions |
| **CSP** | Content Security Policy | Cabecera de seguridad |
| **CSRF** | Cross-Site Request Forgery | Middleware propio |
| **DTO** | Data Transfer Object | Schemas de Pydantic |
| **HMAC** | Hash-based Message Authentication Code | Firma del webhook |
| **HSTS** | HTTP Strict Transport Security | Cabecera de seguridad |
| **IDOR** | Insecure Direct Object Reference | Clase de vulnerabilidad |
| **JWT** | JSON Web Token | Access y refresh tokens |
| **MP** | Mercado Pago | Pasarela de pago |
| **ORM** | Object-Relational Mapping | SQLAlchemy |
| **PII** | Personally Identifiable Information | Datos personales |
| **PITR** | Point-In-Time Recovery | Recuperación de base |
| **RPO** | Recovery Point Objective | Máxima pérdida de datos tolerable |
| **RTO** | Recovery Time Objective | Máximo tiempo de recuperación tolerable |
| **SKU** | Stock Keeping Unit | Identificador de variante |
| **SPA** | Single Page Application | Frontend React |
| **SPOF** | Single Point Of Failure | Punto único de fallo |
| **TTL** | Time To Live | Vida útil de reservas, tokens y registros |
| **UoW** | Unit of Work | `get_db_transactional` |
| **XSS** | Cross-Site Scripting | Clase de vulnerabilidad |

---

← [18 Roadmap](18_Roadmap.md) | [Índice](README.md) | Siguiente: [20 Diccionario de Objetos](20_DiccionarioObjetos.md) →
