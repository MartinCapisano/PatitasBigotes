# 10 — Flujos Completos

← [09 Reglas de Negocio](09_ReglasNegocio.md) | [Índice](README.md) | Siguiente: [11 Seguridad](11_Seguridad.md) →

---

Cada flujo se describe con el mismo esquema: **Usuario → Frontend → API → Service → DB → Respuesta**, con
diagrama de secuencia Mermaid y notas de las decisiones no obvias.

---

## 1. Registro

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant FE as RegisterPage / useRegisterPage
    participant API as POST /auth/register
    participant AB as anti_abuse_s
    participant US as users_s
    participant AT as auth_tokens_s
    participant EM as email_s
    participant DB as PostgreSQL

    U->>FE: nombre, apellido, email, password
    FE->>API: POST {first_name,last_name,email,password}
    Note over API: CSRF: valida Origin<br/>Pydantic: RegisterRequest (extra=forbid, password min 8)
    API->>AB: enforce_public_signup_limits(ip, email)
    AB->>DB: upsert auth_login_throttles ×3 (ip, email_window, email_interval)
    AB-->>API: 429 si supera algún límite
    API->>US: create_auth_user(...)
    US->>US: ensure_password_policy (≥8 y ≥1 especial)
    US->>DB: SELECT users WHERE email FOR UPDATE
    alt existe con has_account=true
        US-->>API: HTTPException 409 "email already exists"
    else existe con has_account=false (era invitado)
        US->>DB: UPDATE users SET nombre, password_hash, has_account=true,<br/>email_verified_at=NULL
        Note right of US: RN-AUTH-03: conserva su historial de órdenes
    else no existe
        US->>DB: INSERT users (has_account=true, is_admin=false, email_verified_at=NULL)
    end
    API->>AT: create_one_time_token(user, email_verify, TTL 24h, ip)
    AT->>DB: UPDATE auth_action_tokens SET used_at (invalida previos)
    AT->>DB: INSERT auth_action_tokens (solo el hash SHA-256)
    AT-->>API: token crudo
    API->>DB: UPDATE users SET email_verification_sent_at = now
    API->>EM: send_email_verification(email, APP_BASE_URL/verify-email?token=…)
    Note over EM: ⚠️ SMTP síncrono DENTRO de la transacción
    API->>DB: COMMIT (get_db_transactional)
    API-->>FE: 201 {data:{registered:true}}
    FE->>FE: savePendingVerificationEmail(email) en localStorage
    FE->>U: navigate("/login", state:{reason:"registration_completed"})
```

**Tablas escritas:** `users`, `auth_action_tokens`, `auth_login_throttles`

**Puntos a tener en cuenta:**
- ⚠️ El email se envía **dentro** de la transacción. Si el SMTP tarda o falla, la transacción se alarga o revierte
  el alta. Contrasta con el flujo de pago, que usa `post_commit_actions`. Ver
  [18_Roadmap.md](18_Roadmap.md#R-04).
- 🟢 El *upgrade de invitado* es transparente: el cliente que compró sin cuenta y luego se registra encuentra sus
  órdenes anteriores en `/profile`.
- El banner de "Verifica tu email" en `Layout` se alimenta del `localStorage` que escribe este flujo.

---

## 2. Verificación de email

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant ML as Cliente de correo
    participant FE as VerifyEmailPage
    participant API as POST /auth/email/verify/confirm
    participant AT as auth_tokens_s
    participant DB as PostgreSQL

    ML->>U: enlace APP_BASE_URL/verify-email?token=xxx
    U->>FE: abre el enlace
    FE->>FE: lee ?token= de la URL
    FE->>API: POST {token}
    API->>AT: consume_one_time_token(token, "email_verify")
    AT->>AT: hash_token = SHA-256(token)
    AT->>DB: SELECT auth_action_tokens WHERE token_hash AND action FOR UPDATE
    alt no existe
        AT-->>API: ValueError "invalid token" → 400
    else used_at IS NOT NULL
        AT-->>API: ValueError "token already used" → 400
    else expires_at <= now
        AT-->>API: ValueError "token expired" → 400
    end
    AT->>DB: SELECT users WHERE id FOR UPDATE
    AT->>DB: UPDATE auth_action_tokens SET used_at = now
    API->>DB: UPDATE users SET email_verified_at = now
    API->>DB: COMMIT
    API-->>FE: {data:{verified:true}}
    FE->>FE: clearPendingVerificationEmail()
    FE->>U: mensaje de éxito + link a /login
```

⚠️ Los tres mensajes de error son distintos, lo que revela si el token **existió alguna vez**. Es un filtrado de
información menor (el token tiene 256 bits de entropía), pero un mensaje único sería más prudente.

---

## 3. Login

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant FE as LoginPage / useLoginPage
    participant CTX as AuthContext.login
    participant API as POST /auth/login
    participant RL as auth_rate_limit_s
    participant AS as auth_s
    participant SEC as auth_security_s
    participant CK as auth_cookies_s
    participant DB as PostgreSQL

    U->>FE: email + password
    FE->>CTX: login(email, password)
    CTX->>API: POST /auth/login {email,password}
    API->>RL: enforce_login_rate_limit(email, ip)
    RL->>DB: SELECT auth_login_throttles (scope=email), (scope=ip)
    alt blocked_until > now
        RL-->>API: LoginRateLimitExceededError → 429
    end
    API->>AS: authenticate_user(email, password)
    AS->>DB: SELECT users WHERE email
    alt no existe
        AS-->>API: LookupError
        API->>RL: register_login_failure() + db.commit()
        API-->>CTX: 401 "invalid credentials"
    else has_account = false
        AS-->>API: ValueError → 401 "invalid credentials"
    else email_verified_at IS NULL
        AS-->>API: ValueError "email not verified" → 403
    else password incorrecta
        AS->>SEC: verify_password → False
        AS-->>API: ValueError → 401
    end
    API->>RL: clear_login_failures(email, ip)
    API->>AS: issue_token_pair(user)
    AS->>SEC: create_access_token({sub, is_admin, tv})
    AS->>SEC: create_refresh_token(user_id) → incluye jti UUID4
    AS->>DB: UPSERT user_refresh_sessions<br/>(token_hash SHA-256, jti, claims, expires_at)
    Note right of AS: RN-AUTH-05: una sola sesión por usuario<br/>pisa la anterior
    API->>CK: set_auth_cookies(response, access, refresh)
    Note over CK: pb_at path=/ · pb_rt path=/auth<br/>HttpOnly + Secure + SameSite según config
    API->>DB: COMMIT
    API-->>CTX: 200 {data:{logged_in,access_expires_in_*}} + Set-Cookie ×2
    CTX->>API: GET /auth/me
    API-->>CTX: perfil con is_admin
    CTX->>CTX: setIsAuthenticated(true), setIsAdmin(...)
    CTX-->>FE: devuelve isAdmin
    FE->>U: navigate(isAdmin ? "/admin" : "/profile")<br/>o "/checkout" si venía de ahí
```

**Tablas escritas:** `user_refresh_sessions`, `auth_login_throttles`, `users` (en fallo, solo throttles)

**Puntos a tener en cuenta:**
- 🔒 Mensaje idéntico para usuario inexistente y password incorrecta.
- ⚠️ Pero el 403 `email not verified` **solo puede ocurrir si el email existe** → enumeración indirecta.
- 🟢 El `db.commit()` explícito en el `except` (`auth_r.py:100`) hace que el contador de fallos sobreviva al 401.
- ⚠️ El login son **dos** requests: `/auth/login` y `/auth/me`. Si el backend devolviera `is_admin` en el login,
  sería una sola.

---

## 4. Renovación de sesión (refresh automático)

```mermaid
sequenceDiagram
    autonumber
    participant C as Componente
    participant AX as axios interceptor
    participant API as Backend
    participant AS as auth_s
    participant DB as PostgreSQL
    participant CTX as AuthContext

    C->>AX: GET /orders (cookie pb_at expirada)
    AX->>API: request
    API-->>AX: 401 (token_version o exp inválidos)
    AX->>AX: ¿url ∈ rutas de auth? ¿ya se reintentó?  → no
    AX->>AX: marca _retry=true; si ya hay refreshPromise, lo espera
    AX->>API: POST /auth/refresh (cookie pb_rt)
    API->>AS: refresh_with_token(refresh_token)
    AS->>AS: decode_refresh_token → sub, jti
    AS->>DB: SELECT user_refresh_sessions WHERE user_id FOR UPDATE
    alt no existe
        AS-->>API: LookupError → 404
    else expires_at <= now
        AS-->>API: ValueError "refresh token expired" → 400
    else token_hash ≠ SHA-256(token) o jti ≠ token_jti
        AS-->>API: ValueError "invalid refresh token" → 400
    end
    AS->>DB: UPDATE users SET token_version = token_version + 1
    Note right of AS: RN-AUTH-06: invalida TODOS los access tokens previos
    AS->>AS: issue_token_pair(user)
    AS->>DB: UPSERT user_refresh_sessions (nuevo hash y jti)
    API-->>AX: 200 + Set-Cookie pb_at, pb_rt nuevas
    AX->>API: reintenta GET /orders con las cookies nuevas
    API-->>C: 200 {data}

    Note over AX,CTX: Si el refresh falla:
    AX->>CTX: window.dispatchEvent("pb-auth-unauthorized")
    CTX->>CTX: isAuthenticated=false, sessionExpired=true
    CTX->>C: ProtectedRoute redirige a /login<br/>con state.reason="session_expired"
```

🟢 **`refreshPromise` como singleton** (`http.ts:28`) evita que N requests simultáneas disparen N refresh. Sin
esa deduplicación, la rotación de `token_version` haría que cada refresh invalidara al anterior y todos fallaran
menos uno.

---

## 5. Navegación del catálogo

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant FE as StorefrontPage / useStorefrontPage
    participant API as GET /storefront/products
    participant PS as products_s
    participant DS as discount_s
    participant DB as PostgreSQL

    U->>FE: entra a /home (o filtra / busca / ordena / pagina)
    FE->>API: ?q=&category_id=&sort_by=name&sort_order=desc&limit=12&offset=0
    Note over API: Sin auth. Valida min_price ≤ max_price
    API->>PS: list_storefront_products(...)
    PS->>DB: subquery: MIN(price), SUM(stock), COUNT(id)<br/>GROUP BY product_id WHERE is_active
    PS->>DB: JOIN products + filtros (category_id, name ILIKE)
    alt sort_by=name y sin filtros de precio
        PS->>DB: COUNT(*) + OFFSET/LIMIT   ⚡ pagina en SQL
    else hay min_price/max_price o sort_by=price
        PS->>DB: trae TODAS las filas       ⚠️ pagina en Python
    end
    PS->>DS: list_discounts(db)
    loop por cada producto
        PS->>DS: get_applicable_discounts_for_product
        loop por cada variante activa
            PS->>DS: select_best_discount + calculate_line_pricing
        end
        PS->>PS: min_var_price_original / min_var_price_final / has_discount
    end
    PS-->>API: (data, total)
    API-->>FE: {data:[...], meta:{total,limit,offset,has_more,filters_applied}}
    FE->>U: grilla con precio tachado si has_discount
```

⚡ **El punto crítico de performance del sistema.** El precio final con descuento **no es computable en SQL**
porque la selección del mejor descuento vive en Python. El código lo documenta explícitamente
(`products_s.py:600-604`) y mitiga permitiendo paginación en SQL para el caso común (orden por nombre sin filtro
de precio). Ver [12_Performance.md](12_Performance.md#storefront).

---

## 6. Agregar al carrito

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant PD as ProductDetailPage / useProductDetailPage
    participant API as GET /storefront/products/{id}
    participant CS as lib/cart-storage
    participant LS as localStorage
    participant LAY as Layout

    U->>PD: entra a /products/42
    PD->>API: GET /storefront/products/42
    API-->>PD: producto + option_axis + options[] (precio con descuento)
    PD->>U: selector de variante (talle o color según option_axis)
    U->>PD: elige variante y cantidad → "Agregar al carrito"
    PD->>CS: addToCart({product_id, product_name, variant_id,<br/>option_label, unit_price, quantity, img_url})
    CS->>LS: lee pb_cart_items, suma si ya existe (product_id + variant_id)
    CS->>LS: escribe pb_cart_items
    CS->>LAY: window.dispatchEvent("pb-cart-updated")
    LAY->>LAY: setCurrentCartCount(cartCount())
    LAY->>U: "Carrito (3)" en la topbar
```

**Nada toca el servidor.** El carrito es puramente cliente hasta el checkout.

⚠️ `unit_price` se congela en `localStorage` al agregar. Si el precio cambia después, el total que ve el usuario
en `/checkout` puede no coincidir con el que calcula el backend. El backend **siempre repreicia**, así que el
importe cobrado es el correcto — pero la discrepancia visual es real.

---

## 7. Checkout de invitado (guest) con Mercado Pago

El flujo más complejo del sistema.

```mermaid
sequenceDiagram
    autonumber
    actor U as Invitado
    participant FE as CheckoutPage / useCheckoutPage
    participant API as POST /checkout/guest
    participant ID as idempotency_s
    participant AB as anti_abuse_s
    participant OS as orders_s
    participant US as users_s
    participant SR as stock_reservations_s
    participant PS as payment_s
    participant MPN as mercadopago_normalization_s
    participant MP as Mercado Pago
    participant DE as domain_events_s
    participant DB as PostgreSQL

    U->>FE: datos de contacto + método = mercadopago
    FE->>FE: buildIdempotencyKey("guest_checkout")
    FE->>API: POST {customer, items, website:"", payment_method}<br/>Idempotency-Key: guest_checkout_uuid
    Note over API: CSRF por Origin · Pydantic (honeypot website max_length=0)

    API->>ID: prune_expired_records(now)
    API->>ID: acquire_record(scope="checkout_guest:email", key, hash(payload))
    ID->>DB: INSERT idempotency_records (status=processing) en SAVEPOINT
    alt IntegrityError y hash distinto
        API-->>FE: 409 "idempotency key already used with a different payload"
    else IntegrityError y status=completed
        API-->>FE: 200 replay del payload guardado
    else IntegrityError y status=processing
        API-->>FE: 409 "idempotent request already in progress"
    else IntegrityError y status=failed
        Note over API: RN-IDEM-03: RECUPERACIÓN — reintenta<br/>solo la inicialización del checkout
    end

    API->>AB: enforce_public_guest_checkout_limits(ip, email, website)
    AB-->>API: 400 si honeypot · 429 si supera límites

    API->>OS: create_manual_submitted_order(customer, items)
    OS->>DB: SELECT users WHERE email AND has_account=true
    alt existe cuenta registrada
        OS-->>API: RegisteredAccountCheckoutConflictError → 409
        FE->>U: navigate("/login", state:{from:"/checkout", checkoutEmail, reason})
    end
    OS->>US: get_or_create_user_by_contact(...)
    US->>DB: INSERT users (has_account=false, password_hash="!")
    Note right of US: RN-AUTH-02: hash centinela, no puede loguearse
    OS->>DB: INSERT orders (status=draft)
    OS->>DB: INSERT order_items (precio de lista)
    OS->>OS: _recalculate_order_total(force=True) → aplica mejor descuento
    OS->>SR: reserve_stock_for_submitted_order(order_id)
    SR->>DB: SELECT product_variants FOR UPDATE + SUM(reservas activas)
    alt falta stock para algún ítem
        SR-->>API: ValueError "insufficient stock for variant N" → 400 + ROLLBACK
    end
    SR->>DB: INSERT stock_reservations (TTL 42 h)
    OS->>DB: UPDATE orders SET pricing_frozen=true, submitted_at, status=submitted
    OS->>DE: publish_domain_event("order_submitted")
    DE->>DB: INSERT notifications (role_target=admin, dedupe_key)

    API->>PS: create_payment_for_order(method=mercadopago, initialize_provider=False)
    PS->>DB: INSERT payments (status=pending, public_status_token, idempotency_key)
    API->>DB: db.flush()
    API->>PS: _initialize_mercadopago_payment_or_raise()
    PS->>MPN: _build_mercadopago_payload(...)
    MPN->>MP: POST /checkout/preferences<br/>(items, back_urls con public_status_token,<br/>notification_url, expires, metadata)
    alt MP falla (timeout / 5xx / credenciales)
        MPN-->>PS: PaymentProviderError
        PS->>DB: UPDATE payments SET provider_status='setup_failed' + COMMIT
        API->>ID: mark_record_failed({detail, order_id, payment_id})
        API->>DB: COMMIT
        API-->>FE: 502 "no se pudo inicializar el checkout de Mercado Pago"
        Note over FE: Reintentar con la MISMA clave activa la recuperación
    end
    MP-->>MPN: {id, init_point, sandbox_init_point}
    MPN->>MPN: valida HTTPS + host ∈ allowlist
    MPN-->>PS: (external_ref, provider_payload con checkout_url)
    PS->>DB: UPDATE payments SET preference_id, external_ref, provider_payload
    API->>ID: mark_record_completed(response_payload)
    API->>DB: COMMIT
    API-->>FE: 201 {data:{customer, order, payment}}

    FE->>FE: getMercadoPagoCheckoutUrl(payment)
    FE->>FE: validateMercadoPagoCheckoutUrl (HTTPS + host) 🔒 2ª validación
    FE->>FE: clearCart()
    FE->>U: window.location.assign(checkout_url)
```

**Tablas escritas:** `idempotency_records`, `auth_login_throttles`, `users`, `orders`, `order_items`,
`stock_reservations`, `payments`, `notifications`

---

## 8. Checkout de usuario autenticado

Más simple, pero **3 requests secuenciales** desde el cliente:

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario autenticado
    participant FE as useCheckoutPage
    participant A1 as PUT /orders/draft/items
    participant A2 as PATCH /orders/{id}/status
    participant A3 as POST /orders/{id}/payments
    participant DB as PostgreSQL

    U->>FE: "Finalizar compra"
    FE->>A1: {items: [{variant_id, quantity}]}
    A1->>DB: get_or_create draft FOR UPDATE
    A1->>DB: DELETE order_items del draft
    A1->>DB: INSERT order_items nuevos (precio de lista)
    A1->>DB: reprice (mejor descuento) + totales
    A1->>DB: COMMIT
    A1-->>FE: {data: order}

    FE->>A2: {status: "submitted"}
    A2->>DB: reprice forzado + validación
    A2->>DB: reserve_stock_for_submitted_order
    alt sin stock
        A2-->>FE: 400 "insufficient stock for variant N"
        Note over FE: ⚠️ el carrito ya se modificó en el paso 1
    end
    A2->>DB: pricing_frozen, submitted_at, status=submitted
    A2->>DB: publish order_submitted → notifications
    A2->>DB: COMMIT
    A2-->>FE: {data: order}

    FE->>A3: {method, currency:"ARS", expires_in_minutes:60}<br/>Idempotency-Key: checkout_payment_{orderId}_{method}
    A3->>DB: INSERT payments + preferencia en MP
    alt MP falla
        A3-->>FE: 502
        Note over FE: ⚠️ orden queda submitted SIN pago.<br/>Recuperable desde /profile, pero el usuario no lo sabe
    end
    A3->>DB: COMMIT
    A3-->>FE: {data: payment}
    FE->>U: redirect a MP · o mensaje de éxito para transferencia/efectivo
```

⚠️ **No hay idempotencia entre los tres pasos.** Cualquier fallo intermedio deja un estado parcial. Los tres
pasos deberían fusionarse en un `POST /checkout` autenticado análogo al de invitado. Ver
[18_Roadmap.md](18_Roadmap.md#R-03).

---

## 9. Confirmación del pago por webhook

```mermaid
sequenceDiagram
    autonumber
    participant MP as Mercado Pago
    participant API as POST /payments/webhook/mercadopago
    participant MPD as mercadopago_d
    participant MC as mercadopago_client
    participant WE as webhook_events_s
    participant MPN as mercadopago_normalization_s
    participant PS as payment_s
    participant SR as stock_reservations_s
    participant RF as refund_s
    participant DE as domain_events_s
    participant PC as post_commit_actions_s
    participant DB as PostgreSQL

    MP->>API: POST {type:"payment", data:{id}, action}<br/>x-signature: ts=…,v1=… · x-request-id
    Note over API: 🔓 EXENTO de CSRF (server-to-server)
    API->>MC: resolver_evento_webhook_mercadopago(payload, x_signature, x_request_id)
    MC->>MC: topic ∈ {payment}? si no → WebhookNoOpError
    MC->>MC: _extract_mercadopago_data_id(payload)
    MC->>MPD: is_mercadopago_signature_valid(data_id, request_id, signature)
    MPD->>MPD: manifest = "id:{data_id};request-id:{rid};ts:{ts};"
    MPD->>MPD: HMAC-SHA256 + compare_digest + ventana [now-300s, now+60s]
    alt firma inválida
        MPD-->>API: False → WebhookInvalidSignatureError
        API->>DB: ROLLBACK + clear_post_commit_actions
        API-->>MP: 401 "invalid signature"
    end
    MC->>MC: event_key = mp:event:{id} | mp:{topic}:{data_id}:{action}
    MC->>WE: acquire_webhook_event(provider, event_key, payload)
    WE->>DB: INSERT webhook_events en SAVEPOINT
    alt duplicado en processing/processed
        WE-->>MC: False → WebhookNoOpError("duplicate webhook event")
        API-->>MP: 200 {processed:false, reason}
    else estaba failed/dead_letter
        WE->>DB: revive a processing
    end

    MC->>MP: GET /v1/payments/{data_id}   (3 reintentos, timeout configurable)
    MP-->>MC: payload del pago
    MC->>MPN: normalize_mp_payment_state(mp_payment)
    MPN->>MPN: mapea provider_status → internal_status
    alt estado desconocido
        MPN-->>MC: ValueError → webhook marcado failed (reintentable) 🔒
    end
    MC->>PS: find_payment_for_mercadopago_event(external_ref)
    alt no encontrado
        MC->>WE: mark_webhook_event_failed (reintentable — puede ser una carrera)
        API-->>MP: 200 {processed:false, reason:"payment not found"}
    end

    MC->>PS: apply_mercadopago_normalized_state(payment_id, normalized_state, payload)
    PS->>SR: expire_active_reservations_for_order
    PS->>PS: 🔒 valida external_ref == payment.external_ref
    PS->>PS: 🔒 valida amount y currency
    PS->>PS: transición (con paid revival si el pago estaba cancelled/expired)
    PS->>DB: UPDATE payments SET status, paid_at, provider_payload

    alt internal_status = paid
        alt orden cancelled
            PS->>RF: create_late_paid_incident_if_needed("approved after cancellation")
            RF->>DB: INSERT payment_incidents (pending_review)
            RF->>DE: publish possible_refund_detected → notifications
        else orden paid con otro pago paid
            PS->>RF: create_late_paid_incident_if_needed("already had another paid payment")
        else orden submitted
            PS->>SR: consume_reservations_for_paid_order
            SR->>DB: UPDATE product_variants SET stock = stock - qty<br/>WHERE stock >= qty   ⚡ compare-and-swap
            alt rowcount ≠ 1
                SR-->>PS: ValueError "insufficient stock" → webhook failed, reintenta
            end
            SR->>DB: UPDATE stock_reservations SET status=consumed
            PS->>DB: UPDATE orders SET status=paid, paid_at
            PS->>DE: publish_domain_event("order_paid")
            DE->>DB: INSERT notifications (admin)
            DE->>PC: enqueue_post_commit_order_paid_email(payload)
        end
    end

    MC->>WE: mark_webhook_event_processed
    API->>DB: COMMIT
    API->>PC: dispatch_post_commit_actions(source="mercadopago_webhook")
    PC->>PC: send_order_paid_email  (fallo → solo logger.exception)
    API-->>MP: 200 {data:{processed:true, payment}}
```

**Tablas escritas:** `webhook_events`, `payments`, `orders`, `stock_reservations`, `product_variants`,
`notifications`, y opcionalmente `payment_incidents`

---

## 10. Retorno del usuario desde Mercado Pago

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant MP as Mercado Pago
    participant FE as PaymentReturnPage / usePaymentReturnStatus
    participant API as GET /public/orders/by-payment-token
    participant OS as orders_s
    participant SR as stock_reservations_s
    participant RT as POST /payments/{token}/retry
    participant DB as PostgreSQL

    MP->>U: redirect a /payments/success?public_status_token=xxx
    U->>FE: carga la página
    FE->>API: GET ?public_status_token=xxx
    Note over API: 🎫 Sin auth. Usa get_db_transactional<br/>porque escribe (expira reservas)
    API->>OS: get_public_order_snapshot_by_payment_token
    OS->>DB: SELECT payments WHERE public_status_token AND method=mercadopago
    OS->>SR: expire_active_reservations_for_order   ⚠️ un GET que muta
    OS->>DB: SELECT todos los pagos mercadopago de la orden
    OS->>OS: elige el "pago relevante": pending > el del token > el más reciente
    OS->>OS: _extract_public_checkout_url  🔒 revalida HTTPS + host
    OS->>OS: calcula flags y blocking_reason
    API->>DB: COMMIT
    API-->>FE: {data:{order, payment, flags, blocking_reason}}

    alt flags.can_continue_payment
        FE->>U: botón "Continuar pago"
        U->>FE: clic
        FE->>FE: validateMercadoPagoCheckoutUrl 🔒
        FE->>MP: window.location.assign(checkout_url)
    else flags.can_retry_payment
        FE->>U: botón "Reintentar pago"
        U->>FE: clic
        FE->>FE: reutiliza idempotencyKey de activeRetryAttemptRef si existe
        FE->>RT: POST /payments/{token}/retry<br/>Idempotency-Key
        RT->>DB: valida 6 condiciones de RN-PAY-11
        RT->>MP: crea preferencia nueva
        RT-->>FE: 201 {data: payment con checkout_url}
        FE->>MP: redirect
    else blocking_reason
        FE->>U: mensaje explicativo según el motivo:<br/>order_paid · order_cancelled · payment_pending ·<br/>payment_not_retryable · stock_reservation_expired · checkout_unavailable
    end
```

🟢 **`activeRetryAttemptRef`** guarda `{idempotencyKey, payment}` en un `useRef`. Si el usuario pulsa
"Reintentar" dos veces, la segunda reutiliza la misma clave y el backend devuelve el pago ya creado en lugar de
crear otro. Coordinación cliente-servidor bien resuelta.

---

## 11. Reconciliación de pagos pendientes (sin webhook)

Cuando el webhook no llega —típico en desarrollo local sin URL pública, o si Mercado Pago tuvo un problema— este
job cierra el círculo.

```mermaid
sequenceDiagram
    autonumber
    participant CRON as GitHub Actions */13 min
    participant API as POST /internal/maintenance/run
    participant MS as maintenance_s
    participant JOB as reconcile_pending_payments_job
    participant MC as mercadopago_client
    participant MP as Mercado Pago
    participant PS as payment_s
    participant PC as post_commit_actions_s
    participant DB as PostgreSQL

    CRON->>API: POST con Bearer MAINTENANCE_RUN_TOKEN
    API->>API: secrets.compare_digest 🔒
    API->>MS: run_all_maintenance()
    MS->>MS: threading.Lock (no reentrante)
    MS->>JOB: run_once(batch_size=50, max_age_hours=24, min_age_minutes=15)
    JOB->>DB: SELECT payments WHERE method=mercadopago AND status=pending<br/>AND external_ref IS NOT NULL<br/>AND created_at ∈ [now-24h, now-15min]<br/>AND orders.status ∈ (submitted, paid)  LIMIT 50
    Note over JOB: min_age_minutes evita pisar pagos recién creados<br/>que aún están en el flujo del usuario
    loop por cada pago candidato
        JOB->>MC: find_latest_payment_by_external_reference(external_ref)
        MC->>MP: POST /v1/payments/search
        alt no encontrado
            JOB->>JOB: metrics.provider_not_found += 1
        else encontrado
            JOB->>PS: apply_mercadopago_normalized_state(source="batch_reconcile")
            Note over PS: mismo camino que el webhook:<br/>consume stock, orden → paid, evento order_paid
            JOB->>DB: COMMIT (por ítem)
            JOB->>PC: dispatch_post_commit_actions → email al cliente
            JOB->>JOB: metrics.reconciled += 1
        end
    end
    JOB-->>MS: {selected, reconciled, provider_not_found, failed}
    MS->>MS: ...los otros 5 jobs
    MS-->>API: {status: ok|partial, jobs:{...}}
    API-->>CRON: 200
```

🟢 **Commit por ítem**: un fallo en el pago 7 no revierte los 6 anteriores.
⚠️ **Llamadas HTTP secuenciales**: un lote de 50 son 50 requests en serie. Con timeout de 10 s y 3 reintentos,
el peor caso teórico supera el `--max-time 150` del cron.

---

## 12. Expiración de reserva y cancelación automática

```mermaid
sequenceDiagram
    autonumber
    participant TRIG as Disparador<br/>(job o lectura perezosa)
    participant SR as stock_reservations_s
    participant DE as domain_events_s
    participant DB as PostgreSQL

    TRIG->>SR: expire_active_reservations(now, limit)
    SR->>DB: SELECT stock_reservations WHERE status=active<br/>AND expires_at <= now FOR UPDATE
    alt ninguna
        SR-->>TRIG: 0   (camino rápido)
    end
    SR->>SR: agrupa por order_id
    loop por cada orden afectada
        SR->>DB: SELECT orders + order_items FOR UPDATE
        SR->>DB: UPDATE reservations SET status=expired,<br/>released_at=now, reason='reservation_expired'
        alt orden no está submitted
            SR->>SR: cuenta y continúa (nada que rescatar)
        else alguna reserva ya tiene reactivation_count >= 1
            SR->>DB: UPDATE orders SET status=cancelled, cancelled_at
            SR->>DE: publish order_cancelled (reason="expiracion de reserva")
            DE->>DB: INSERT notifications (admin)
            SR->>DB: UPDATE payments SET status=cancelled,<br/>provider_status='order_cancelled_reservation_expired'<br/>WHERE status=pending
        else todas reactivables
            SR->>DB: para cada ítem: calcula stock disponible
            alt alcanza para todos
                SR->>DB: UPDATE reservations SET status=active,<br/>reactivation_count+=1, expires_at=now+12h
                Note right of SR: RN-STK-05: segunda y última oportunidad
            else no alcanza
                SR->>DB: cancela la orden (igual que arriba)
            end
        end
    end
    SR->>DB: flush
    SR-->>TRIG: cantidad de reservas expiradas
```

⚠️ Las **reactivadas no se cuentan** en el retorno, así que `expire_stock_reservations_job` puede ver `0` y cortar
el bucle de lotes aunque haya hecho trabajo.

---

## 13. Venta presencial (admin)

```mermaid
sequenceDiagram
    autonumber
    actor A as Administrador
    actor C as Cliente en el mostrador
    participant FE as SalesSection / useAdminSales
    participant API as POST /admin/sales
    participant OS as orders_s
    participant US as users_s
    participant SR as stock_reservations_s
    participant PS as payment_s
    participant PC as post_commit_actions_s
    participant DB as PostgreSQL

    C->>A: quiere llevar 2 productos
    A->>FE: buscar cliente (GET /users/search) o cargar datos nuevos
    A->>FE: elegir productos y variantes, cantidades
    A->>FE: método = efectivo, monto recibido, vuelto
    FE->>API: POST {customer{mode}, items, register_payment:true, payment}
    Note over API: 👑 require_admin (relee is_admin de la DB)<br/>⚠️ el cliente NO envía Idempotency-Key
    API->>OS: create_admin_sale(...)
    alt mode = existing
        OS->>DB: SELECT users WHERE id
        OS->>OS: 🔒 prohíbe enviar otros campos del cliente
    else mode = new
        OS->>US: get_or_create_user_by_contact(...)
        US->>US: 🔒 valida coincidencia de contacto si el email ya existe
    end
    OS->>DB: INSERT orders (draft) + order_items
    OS->>OS: reprice con descuentos vigentes
    OS->>SR: reserve_stock_for_submitted_order
    OS->>DB: UPDATE orders SET pricing_frozen, submitted_at, status=submitted
    OS->>DB: publish order_submitted → notifications

    OS->>PC: set_skip_order_paid_email(db, True)   🔇
    OS->>PS: confirm_manual_payment_for_order(allow_create_if_missing=True)
    PS->>PS: valida paid_amount − change_amount == total  (efectivo)
    PS->>SR: consume_reservations_for_paid_order
    SR->>DB: UPDATE product_variants SET stock = stock - qty
    PS->>DB: INSERT payments (status=paid, provider_status='manual_confirmed')
    PS->>DB: UPDATE orders SET status=paid, paid_at
    PS->>DB: publish order_paid → notifications (email suprimido)
    OS->>PC: set_skip_order_paid_email(db, valor previo)   restaura en finally
    API->>DB: COMMIT (get_db_transactional)
    API-->>FE: {data:{customer, order, payment, meta{customer_created,<br/>payment_registered, order_paid_email_suppressed}}}
    FE->>A: comprobante en pantalla
    A->>C: entrega productos y vuelto
```

🟢 **Supresión del email** con restauración en `finally`. Detalle de producto bien pensado.
⚠️ **Sin `Idempotency-Key` desde el cliente**, pese a que el endpoint la soporta.

---

## 14. Registro de un pago por transferencia (admin)

```mermaid
sequenceDiagram
    autonumber
    actor A as Administrador
    participant FE as RegisterPaymentSection
    participant S1 as GET /users/search
    participant S2 as GET /admin/payments?status=pending
    participant API as POST /admin/orders/{id}/payments/manual
    participant PS as payment_s
    participant SR as stock_reservations_s
    participant PC as post_commit_actions_s
    participant DB as PostgreSQL

    A->>FE: ve la transferencia acreditada en el banco
    FE->>S1: busca al cliente
    FE->>S2: lista pagos pendientes
    FE->>FE: filtra en el cliente por usuario ⚠️
    A->>FE: selecciona el pago, carga monto y referencia
    FE->>FE: normalizePaymentAmountsForOrder<br/>⚠️ heurística: prueba centavos y pesos
    A->>FE: confirma en el modal
    FE->>API: POST {method:"bank_transfer", paid_amount, payment_ref}
    API->>PS: confirm_manual_payment_for_order(allow_create_if_missing=False)
    PS->>DB: SELECT orders FOR UPDATE
    PS->>PS: valida paid_amount == total_amount exacto
    PS->>DB: SELECT payments WHERE status=pending AND method=bank_transfer FOR UPDATE
    alt no hay pago pendiente de ese método
        PS-->>API: ValueError "pending payment not found for order and method" → 400
        Note over API: ⚠️ si el cliente eligió Mercado Pago,<br/>este endpoint NO sirve
    end
    PS->>SR: consume_reservations_for_paid_order
    SR->>DB: UPDATE product_variants SET stock = stock - qty
    PS->>DB: UPDATE payments SET status=paid, external_ref, provider_status='manual_confirmed'
    PS->>DB: UPDATE orders SET status=paid, paid_at
    PS->>DB: publish order_paid → notifications + encola email
    API->>DB: db.commit()   (patrón manual, no get_db_transactional)
    API->>PC: dispatch_post_commit_actions("admin_register_manual_payment")
    PC->>PC: send_order_paid_email → 📧 al cliente
    API-->>FE: {data:{order, payment}}
```

Aquí el email **sí** se envía: el cliente no está presente y necesita el aviso.

---

## 15. Reembolso de un cobro tardío o duplicado

```mermaid
sequenceDiagram
    autonumber
    participant SYS as Webhook / reconciliación
    participant RF as refund_s
    participant DE as domain_events_s
    actor A as Administrador
    participant FE as PaymentIncidentsSection
    participant API as POST /admin/payment-incidents/{id}/resolve-refund
    participant MC as mercadopago_client
    participant MP as Mercado Pago
    participant DB as PostgreSQL

    SYS->>RF: create_late_paid_incident_if_needed(order, payment, reason)
    RF->>DB: SELECT incidencia pending_review existente
    alt ya existe
        RF-->>SYS: la devuelve (idempotente)
    end
    RF->>DB: INSERT payment_incidents (type=late_paid_duplicate, status=pending_review)
    RF->>DE: publish possible_refund_detected
    DE->>DB: INSERT notifications (dedupe_key=admin:incident:{id}:possible_refund)

    A->>FE: ve la campana con el aviso → sección "Incidencias de pago"
    FE->>FE: GET /admin/payment-incidents?status=pending_review&limit=200
    A->>FE: decide reembolsar; escribe el motivo (obligatorio)
    FE->>API: POST {amount?, reason}
    API->>RF: create_mercadopago_refund(...)
    RF->>DB: SELECT payment_incidents FOR UPDATE
    alt ya resuelta con reembolso
        RF-->>API: devuelve el refund existente (idempotente)
    end
    RF->>RF: valida método=mercadopago, estado=paid, amount ≤ payment.amount
    RF->>DB: SELECT refund activo del pago
    alt ya hay uno activo
        RF-->>API: ValueError "payment already has an active refund" → 400
    end
    RF->>DB: INSERT payment_refunds (status=requested,<br/>idempotency_key=sha256(incident:payment:amount))
    RF->>RF: _extract_provider_payment_id(payment.provider_payload)
    alt no encontrado
        RF-->>API: ValueError "missing mercadopago provider payment id" → 400
    end
    RF->>MC: create_refund(payment_id, amount?, idempotency_key)
    MC->>MP: POST /v1/payments/{id}/refunds<br/>x-idempotency-key · amount en decimal
    alt error del proveedor
        MP-->>MC: 4xx/5xx/timeout
        RF->>DB: UPDATE payment_refunds SET status=failed + payload
        RF->>DB: COMMIT   ⚠️ dentro del except, deliberado
        RF-->>API: re-lanza → 502/503/504
        Note over FE: la incidencia sigue pending_review, se puede reintentar
    end
    MP-->>MC: {id, status, ...}
    RF->>DB: UPDATE payment_refunds SET status=approved, provider_refund_id
    RF->>DB: UPDATE payment_incidents SET status=resolved_refunded,<br/>reason, resolved_at, resolved_by_user_id
    API->>DB: COMMIT
    API-->>FE: 201 {data:{incident, refund}}
    FE->>A: confirmación
```

---

## 16. Administración de catálogo

```mermaid
sequenceDiagram
    autonumber
    actor A as Administrador
    participant FE as CatalogSection / useAdminCatalog
    participant AD as require_admin
    participant API as products_r
    participant PS as products_s
    participant DB as PostgreSQL

    A->>FE: entra a /admin, sección "catalogo"
    FE->>API: GET /admin/catalog?limit=200
    API->>AD: valida cookie + relee users.is_admin  🔒
    API->>PS: list_admin_catalog(limit)
    PS->>DB: subquery MIN(price) + JOIN products + joinedload(category, variants)
    PS->>DB: SELECT categories
    PS-->>API: {categories, products, variants_by_product}
    API-->>FE: {data:{...}}
    FE->>FE: normalizeVariantsByProduct (claves string → number, ordena por id)

    Note over A,DB: --- Crear producto ---
    A->>FE: nombre, categoría, descripción, imagen
    FE->>API: POST /products {name, description, img_url, category, active}
    API->>PS: create_product(payload)
    PS->>DB: SELECT categories WHERE name
    alt categoría inexistente
        PS-->>API: ValueError "category not found" → 400
    end
    PS->>DB: INSERT products
    Note over PS: ⚠️ el campo 'active' del DTO se IGNORA
    API-->>FE: {data: product}
    FE->>FE: reload() del catálogo completo

    Note over A,DB: --- Editar variante (con precio) ---
    A->>FE: expande el producto, edita la variante
    A->>FE: activa "editar precio" → escribe el precio → CONFIRMA en modal 🔒
    FE->>API: PATCH /variants/{id} {sku, size, color, img_url, price, stock, active}
    API->>PS: update_variant(id, updates)
    PS->>DB: SELECT product_variants WHERE id
    PS->>PS: valida sku único, price ≥ 0, stock ≥ 0
    PS->>DB: UPDATE product_variants
    API-->>FE: {data: variant}
    FE->>FE: deriveProductFromVariants → actualiza stock, active y min_var_price<br/>del producto SIN volver a llamar al servidor ⚡

    Note over A,DB: --- Desactivar producto ---
    A->>FE: toggle "activo" = false
    FE->>API: PATCH /products/{id} {active:false}
    API->>PS: update_product
    PS->>DB: UPDATE product_variants SET is_active=false  (TODAS)
    Note over PS: ⚠️ RN-CAT-02: al reactivar se reactivan todas,<br/>incluidas las que estaban desactivadas a mano
```

---

## 17. Resumen: qué toca cada flujo

| Flujo | Endpoints | Servicios | Tablas escritas | Externos |
|---|---|---|---|---|
| Registro | 1 | `users_s`, `auth_tokens_s`, `email_s`, `anti_abuse_s` | `users`, `auth_action_tokens`, `auth_login_throttles` | SMTP |
| Verificación | 1 | `auth_tokens_s` | `auth_action_tokens`, `users` | — |
| Login | 2 | `auth_rate_limit_s`, `auth_s`, `auth_security_s`, `auth_cookies_s` | `user_refresh_sessions`, `auth_login_throttles`, `users` | — |
| Refresh | 1 | `auth_s` | `user_refresh_sessions`, `users` | — |
| Catálogo | 2 | `products_s`, `discount_s` | — | — |
| Carrito | 0 | — | — | — |
| Checkout guest | 1 | `idempotency_s`, `anti_abuse_s`, `orders_s`, `users_s`, `stock_reservations_s`, `payment_s`, `mercadopago_*`, `domain_events_s` | 7 tablas | Mercado Pago |
| Checkout auth | 3 | `orders_s`, `stock_reservations_s`, `payment_s`, `discount_s` | 5 tablas | Mercado Pago |
| Webhook | 1 | `mercadopago_client`, `webhook_events_s`, `payment_s`, `stock_reservations_s`, `refund_s`, `domain_events_s`, `post_commit_actions_s` | 7 tablas | Mercado Pago, SMTP |
| Retorno de pago | 1–2 | `orders_s`, `payment_s`, `stock_reservations_s` | `stock_reservations`, `orders`, `payments` | Mercado Pago |
| Reconciliación | 1 | `reconcile_pending_payments_job` + los del webhook | ídem webhook | Mercado Pago, SMTP |
| Expiración | 0 (job) | `stock_reservations_s`, `domain_events_s` | `stock_reservations`, `orders`, `payments`, `notifications` | — |
| Venta admin | 2 | `orders_s`, `users_s`, `stock_reservations_s`, `payment_s`, `post_commit_actions_s` | 7 tablas | — |
| Registro de pago | 3 | `payment_s`, `stock_reservations_s`, `post_commit_actions_s` | 5 tablas | SMTP |
| Reembolso | 2 | `refund_s`, `mercadopago_client`, `domain_events_s` | `payment_incidents`, `payment_refunds`, `notifications` | Mercado Pago |
| Catálogo admin | 5+ | `products_s` | `products`, `product_variants`, `categories` | — |

---

← [09 Reglas de Negocio](09_ReglasNegocio.md) | [Índice](README.md) | Siguiente: [11 Seguridad](11_Seguridad.md) →
