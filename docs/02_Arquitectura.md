# 02 — Arquitectura

← [01 Resumen](01_Resumen.md) | [Índice](README.md) | Siguiente: [03 Árbol del Proyecto](03_ArbolProyecto.md) →

---

## 1. Estilo arquitectónico

PatitasBigotes es un **monolito modular en capas**, con separación estricta entre adaptadores HTTP y lógica de
dominio, pero **sin** arquitectura hexagonal formal: los servicios importan los modelos SQLAlchemy directamente, sin
puertos ni repositorios intermedios.

| Patrón | ¿Presente? | Evidencia |
|---|---|---|
| Layered architecture (Routes → Services → Models) | ✅ Sí, consistente | Ningún archivo en `routes/` contiene lógica de negocio |
| Service layer | ✅ Sí, pero **funcional** (funciones, no clases) | `source/services/*.py` — ninguna clase de servicio |
| Repository pattern | ❌ No | Los servicios llaman `db.query(Model)` directamente |
| Unit of Work | 🟡 Implícito | `get_db_transactional` (`db/session.py:29`) hace de UoW por request |
| Hexagonal / Ports & Adapters | ❌ No | `mercadopago_client` es la única frontera de infra aislada |
| DDD táctico | 🟡 Parcial | Hay lenguaje ubicuo y agregados conceptuales, sin entidades ricas |
| MVC | ❌ No aplica | Es una API, no hay vistas de servidor |
| Event-driven | 🟡 Simulado | `domain_events_s` es un dispatcher **síncrono in-process**, no un bus |
| Feature-sliced frontend | ✅ Sí | `frontend/src/features/<dominio>/{hooks,services,components,types,utils}` |

> ⚠️ La ausencia de repositorios significa que **no se puede testear un servicio sin base de datos**. Los tests
> resuelven esto con SQLite en memoria (ver [16_Testing.md](16_Testing.md)), lo que funciona pero acopla los tests
> al comportamiento de SQLite (por ejemplo, `with_for_update()` es un no-op ahí).

---

## 2. Vista de capas

```mermaid
flowchart TD
    subgraph CLIENT["Cliente"]
        BROWSER["Navegador<br/>SPA React 18 + Vite"]
    end

    subgraph EDGE["Borde HTTP — backend/main.py"]
        SH["SecurityHeadersMiddleware<br/>X-Frame-Options, CSP, HSTS"]
        CORS["CORSMiddleware<br/>allow_credentials=True"]
        CSRF["CSRFMiddleware<br/>Origin/Referer allowlist"]
    end

    subgraph ADAPTERS["Capa de adaptadores — source/routes/"]
        RT["12 routers<br/>auth · orders · payments · products ·<br/>storefront · discounts · turns · users ·<br/>notifications · stock_reservations ·<br/>mercadopago · maintenance"]
        DEPS["Dependencias<br/>get_current_user · require_admin ·<br/>get_db · get_db_transactional"]
        SCH["Schemas Pydantic<br/>extra=forbid"]
        ERR["errors.raise_http_error_from_exception<br/>excepción de dominio → status HTTP"]
    end

    subgraph DOMAIN["Capa de dominio — source/services/"]
        CAT["Catálogo<br/>products_s"]
        PRICE["Precios<br/>discount_s · money_s"]
        ORD["Órdenes<br/>orders_s"]
        STK["Inventario<br/>stock_reservations_s"]
        PAY["Pagos<br/>payment_s · refund_s"]
        AUTH["Identidad<br/>auth_*_s · users_s"]
        NOTIF["Eventos y avisos<br/>domain_events_s · notifications_s ·<br/>post_commit_actions_s"]
        ABUSE["Anti-abuso<br/>auth_rate_limit_s · anti_abuse_s"]
        IDEM["Idempotencia<br/>idempotency_s"]
        WH["Webhooks<br/>webhook_events_s"]
    end

    subgraph INFRA["Infraestructura"]
        MODELS["Modelos SQLAlchemy<br/>source/db/models.py — 17 tablas"]
        SESSION["Engine + SessionLocal<br/>source/db/session.py"]
        MPC["mercadopago_client<br/>SDK + retries"]
        MAIL["email_s<br/>smtplib"]
    end

    subgraph EXTERNAL["Servicios externos"]
        PG[("PostgreSQL<br/>Supabase")]
        MP["Mercado Pago<br/>Checkout Pro API"]
        SMTP["Servidor SMTP"]
    end

    BROWSER -->|"HTTPS · cookies HttpOnly"| SH
    SH --> CORS --> CSRF --> RT
    RT --> DEPS
    RT --> SCH
    RT --> ERR
    RT --> CAT & PRICE & ORD & STK & PAY & AUTH & NOTIF & ABUSE & IDEM & WH
    ORD --> STK
    ORD --> PAY
    ORD --> PRICE
    PAY --> STK
    PAY --> NOTIF
    PAY --> MPC
    STK --> NOTIF
    CAT --> PRICE
    CAT & PRICE & ORD & STK & PAY & AUTH & NOTIF & ABUSE & IDEM & WH --> MODELS
    MODELS --> SESSION --> PG
    MPC --> MP
    NOTIF --> MAIL --> SMTP
    MP -.->|"webhook HMAC SHA-256"| RT
```

### Responsabilidad de cada capa

| Capa | Debe | No debe |
|---|---|---|
| **Middlewares** | Cabeceras de seguridad, CORS, defensa CSRF | Conocer entidades de negocio |
| **Routers** | Validar entrada (Pydantic), resolver dependencias, delegar, traducir excepciones, gestionar el commit en los casos "manuales" | Contener reglas de negocio, hacer queries |
| **Servicios** | Todas las reglas de negocio, invariantes, transiciones de estado, orquestación | Conocer FastAPI, `Request`, `Response` o códigos HTTP¹ |
| **Modelos** | Estructura, constraints, índices, relaciones | Lógica de negocio (son modelos anémicos por diseño) |
| **Jobs** | Un `run_once()` idempotente + un `run_forever()` opcional | Depender de una request HTTP |

> ¹ ⚠️ **Violación conocida:** `users_s.py` y `auth_s.py` lanzan `HTTPException` directamente
> (`users_s.py:46`, `users_s.py:78`, `auth_s.py:306`). Es la única fuga de la capa HTTP hacia el dominio.
> Detallada en [13_CalidadCodigo.md](13_CalidadCodigo.md#acoplamiento).

---

## 3. Gestión de transacciones

Es el punto más sutil de la arquitectura y hay que entenderlo antes de escribir un endpoint nuevo.

Existen **dos dependencias de sesión** (`backend/source/db/session.py`):

```python
def get_db():                      # lectura: nunca commitea
    db = SessionLocal()
    try: yield db
    finally: db.close()

def get_db_transactional():        # escritura: commit al salir, rollback ante excepción
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback(); raise
    finally:
        db.close()
```

Y **tres estrategias** conviviendo en los routers:

```mermaid
flowchart TD
    A["Endpoint nuevo"] --> B{"¿Escribe en DB?"}
    B -->|No| C["Depends(get_db)<br/>lectura pura"]
    B -->|Sí| D{"¿Necesita hacer trabajo<br/>DESPUÉS del commit?<br/>(emails, llamadas a MP)"}
    D -->|No| E["Depends(get_db_transactional)<br/>← estrategia por defecto"]
    D -->|Sí| F["Depends(get_db) + db.commit() manual<br/>+ dispatch_post_commit_actions()"]

    C -.->|ejemplo| C1["GET /orders<br/>GET /storefront/products"]
    E -.->|ejemplo| E1["POST /auth/login<br/>PATCH /orders/{id}/status<br/>POST /discounts"]
    F -.->|ejemplo| F1["POST /orders/{id}/payments<br/>POST /checkout/guest<br/>POST /payments/webhook/mercadopago"]
```

**Casos especiales que rompen la regla (documentados en el propio código):**

| Endpoint | Sesión | Por qué |
|---|---|---|
| `GET /public/orders/by-payment-token` | `get_db_transactional` | Un GET que **escribe**: expira reservas vencidas antes de armar el snapshot (`orders_r.py:499-501`) |
| `GET /orders/{id}/reservations` | `get_db_transactional` | Idem: expira reservas antes de listarlas (`orders_r.py:730-732`) |
| `refund_s.create_mercadopago_refund` | commit propio en el `except` | Persiste el estado `failed` antes de re-lanzar, para que el rollback del caller no lo pierda (`refund_s.py:352-355`) |

> ⚠️ **Trampa para quien agregue endpoints:** si usás `get_db_transactional` y necesitás enviar un email,
> el email se dispararía **dentro** de la transacción. Usá siempre el patrón `post_commit_actions_s`
> (ver [20_DiccionarioObjetos.md](20_DiccionarioObjetos.md#postcommitaction)).

---

## 4. Flujo completo de una request

Ejemplo: cliente autenticado crea el pago de una orden.

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant FE as React (useCheckoutPage)
    participant AX as axios http.ts
    participant MW as Middlewares
    participant R as orders_r.create_order_payment
    participant AD as auth_d.get_current_user
    participant PS as payment_s
    participant SR as stock_reservations_s
    participant MPN as mercadopago_normalization_s
    participant MP as Mercado Pago
    participant DB as PostgreSQL

    U->>FE: Clic "Finalizar compra"
    FE->>AX: POST /orders/{id}/payments<br/>Idempotency-Key: checkout_payment_…
    AX->>MW: withCredentials → cookies pb_at/pb_rt
    MW->>MW: SecurityHeaders → CORS → CSRF (Origin allowlist)
    MW->>R: request validada
    R->>AD: Depends(get_current_user)
    AD->>DB: SELECT users WHERE id=sub
    AD-->>R: 401 si token_version ≠ tv del JWT
    R->>PS: create_payment_for_order(initialize_provider=False)
    PS->>SR: expire_active_reservations_for_order()
    PS->>DB: SELECT orders … FOR UPDATE
    PS->>PS: valida status=submitted, items, reservas activas, total>0
    PS->>DB: INSERT payments (idempotency_key UNIQUE)
    PS-->>R: dict del pago (sin preference_id)
    R->>R: db.flush()
    R->>PS: _initialize_mercadopago_payment_or_raise()
    PS->>MPN: _build_mercadopago_payload()
    MPN->>MP: POST /checkout/preferences (x-idempotency-key)
    MP-->>MPN: {id, init_point, sandbox_init_point}
    MPN->>MPN: valida host HTTPS ∈ allowlist
    MPN-->>PS: (external_ref, provider_payload)
    PS->>DB: UPDATE payments SET preference_id, external_ref, provider_payload
    R->>DB: db.commit()
    R-->>AX: 201 {data: {…, provider_payload_data.checkout.checkout_url}}
    AX-->>FE: payment
    FE->>FE: validateMercadoPagoCheckoutUrl() (2ª validación en cliente)
    FE->>U: window.location.assign(checkout_url)
```

Los flujos de login, registro, checkout guest, webhook, reembolso y turnos están en
[10_Flujos.md](10_Flujos.md).

---

## 5. Arquitectura de despliegue

```mermaid
flowchart TB
    subgraph GH["GitHub"]
        REPO["Repositorio main"]
        CI["Actions: CI<br/>backend-tests · contract-schema · frontend-tests"]
        CRON1["Actions: Maintenance ping<br/>cron */13 * * * *"]
        CRON2["Actions: DB backup<br/>cron 0 4 * * * · pg_dump → artifact 30d"]
    end

    subgraph VERCEL["Vercel"]
        SPA["Build estático Vite<br/>rewrites /* → /index.html"]
    end

    subgraph RENDER["Render — plan free"]
        API["uvicorn main:app<br/>build: pip install && alembic upgrade head<br/>healthCheckPath /health<br/>💤 duerme a los 15 min"]
    end

    subgraph SUPA["Supabase — plan free"]
        PG[("PostgreSQL<br/>⏸ se pausa a los 7 días")]
    end

    MP["Mercado Pago"]
    SMTP["SMTP externo"]

    REPO --> CI
    REPO -->|deploy| SPA
    REPO -->|deploy| API
    SPA -->|"VITE_API_BASE_URL<br/>timeout 60s por cold start"| API
    API --> PG
    API <-->|"preferencias · refunds · lookups"| MP
    MP -->|"webhook firmado"| API
    API --> SMTP
    CRON1 -->|"POST /internal/maintenance/run<br/>Bearer MAINTENANCE_RUN_TOKEN"| API
    CRON2 --> PG
```

### Por qué el diseño está condicionado por el free tier

Esta es la razón de varias decisiones que de otro modo parecerían raras:

| Restricción del free tier | Consecuencia en el diseño | Evidencia |
|---|---|---|
| Render duerme tras ~15 min sin tráfico | Timeout de axios en 60 s, no 10 s | `http.ts:4-7` |
| Render duerme → no hay scheduler in-process fiable | Los jobs se disparan por ping externo cada 13 min | `maintenance_s.py:1-20` |
| Render free = **una sola instancia** | El lock de mantenimiento es un `threading.Lock` de proceso, no distribuido | `maintenance_s.py:39` ⚠️ |
| Supabase se pausa tras 7 días de inactividad | El mismo ping de 13 min mantiene viva la base | `maintenance.yml:16-18` |
| Supabase free no tiene backups | `pg_dump` diario a artifact de GitHub (retención 30 días) | `db-backup.yml` |
| Vercel/Cloudflare no tienen Python | `api.generated.ts` se commitea; CI valida que no derive | `.gitignore:24-27`, `ci.yml:51-54` |
| Frontend y backend en dominios distintos | Cookies `SameSite=None; Secure` obligatorias en prod | `db/config.py:116-126` |

---

## 6. Dependencias entre módulos (resumen)

Mapa completo, incluida la detección de ciclos, en [21_MapaDependencias.md](21_MapaDependencias.md).

```mermaid
flowchart LR
    orders_s --> discount_s
    orders_s --> payment_s
    orders_s --> products_s
    orders_s --> stock_reservations_s
    orders_s --> domain_events_s
    orders_s --> post_commit_actions_s
    orders_s --> users_s

    payment_s --> refund_s
    payment_s --> domain_events_s
    payment_s --> mercadopago_normalization_s
    payment_s --> stock_reservations_s

    refund_s --> mercadopago_client
    refund_s --> domain_events_s

    mercadopago_normalization_s --> mercadopago_client
    mercadopago_normalization_s --> money_s

    mercadopago_client -.->|"import diferido<br/>dentro de la función"| payment_s
    mercadopago_client -.->|"import diferido"| webhook_events_s
    mercadopago_client -.->|"import diferido"| mercadopago_normalization_s

    webhook_events_s --> payment_s
    webhook_events_s -.->|"import diferido"| mercadopago_client

    payment_admin_queries_s --> payment_s
    payment_admin_queries_s --> refund_s

    discount_s --> money_s
    products_s --> discount_s
    stock_reservations_s --> domain_events_s
    domain_events_s --> notifications_s
    domain_events_s --> post_commit_actions_s
    post_commit_actions_s --> email_s
    auth_s --> auth_security_s
    auth_s --> auth_tokens_s
    auth_s --> email_s
    auth_rate_limit_s --> anti_abuse_s
    users_s --> auth_security_s

    classDef cycle stroke-dasharray: 5 5
```

**Ciclos detectados (todos resueltos con imports diferidos y comentados en el código):**

| Ciclo | Cómo se rompe | Evidencia |
|---|---|---|
| `payment_s` ↔ `mercadopago_normalization_s` ↔ `mercadopago_client` | `mercadopago_client` importa `payment_s` **dentro** de `process_mercadopago_event_payload` | `mercadopago_client.py:334-340` |
| `webhook_events_s` ↔ `mercadopago_client` | Ambos sentidos usan import local dentro de la función | `webhook_events_s.py:308`, `mercadopago_client.py:389` |
| `payment_s` ↔ `refund_s` | `refund_s` no importa `payment_s`; `payment_admin_queries_s` importa a ambos | Sin ciclo real |
| Helper `_normalize_optional_str` duplicado | Duplicación deliberada para no crear ciclo, con comentario explicativo | `mercadopago_normalization_s.py:44-46` |

---

## 7. Arquitectura del frontend

```mermaid
flowchart TD
    MAIN["main.tsx<br/>React.StrictMode + BrowserRouter"] --> APP["App.tsx<br/>AuthProvider + Suspense + Routes"]
    APP --> LAYOUT["components/Layout.tsx<br/>topbar · carrito · campana de notificaciones · Outlet"]
    LAYOUT --> PUB["Rutas públicas<br/>/home /categorias /peluqueria /contacto<br/>/checkout /products/:id /login /register<br/>/forgot-password /reset-password /verify-email<br/>/payments/{success,failure,pending}"]
    LAYOUT --> PROT["ProtectedRoute<br/>→ /profile"]
    LAYOUT --> ADM["AdminRoute<br/>→ /admin"]

    PUB --> PAGES["pages/*.tsx<br/>14 páginas, todas lazy-loaded"]
    PAGES --> HOOKS["features/*/hooks/use*Page.ts<br/>toda la lógica de UI"]
    HOOKS --> SVC["services/*-api.ts<br/>12 clientes tipados"]
    SVC --> HTTP["services/http.ts<br/>axios + interceptor 401 → refresh"]
    HTTP --> API["Backend FastAPI"]

    HOOKS --> LIB["lib/<br/>cart-storage (localStorage)<br/>useAsyncResource<br/>useClickOutside · useModalA11y"]
    APP --> CTX["AuthContext<br/>isAuthenticated · isAdmin · sessionExpired"]
    HTTP -.->|"CustomEvent pb-auth-unauthorized"| CTX
    LIB -.->|"CustomEvent pb-cart-updated"| LAYOUT
```

**Patrón dominante: *hook de página*.** Cada página es un componente de presentación casi puro; toda la lógica
(estado, fetching, validación, mensajes de error) vive en un hook `useXxxPage`. Esto hace los tests de frontend
posibles sin renderizar árboles completos — los 51 tests testean hooks, no componentes.

**Comunicación desacoplada por `CustomEvent` del navegador:**

| Evento | Emisor | Consumidor | Propósito |
|---|---|---|---|
| `pb-auth-unauthorized` | `services/http.ts:36` | `AuthContextProvider.tsx:54` | Un 401 irrecuperable limpia la sesión en toda la app |
| `pb-cart-updated` | `lib/cart-storage.ts:15` | `Layout.tsx:33` | El contador del carrito se actualiza sin prop drilling |

---

## 8. Contrato Frontend ↔ Backend

```mermaid
flowchart LR
    A["backend/source/schemas/*.py<br/>+ routers"] -->|"app.openapi()"| B["scripts/export_openapi.py"]
    B --> C["backend/openapi.json<br/>(gitignored)"]
    C -->|"npm run gen:api-types<br/>openapi-typescript"| D["frontend/src/types/api.generated.ts<br/>(COMMITEADO)"]
    D --> E["Tipos disponibles en el frontend"]
    C -.->|"CI: git diff --exit-code"| F["❌ CI falla si hay drift"]
```

> ⚠️ **Punto débil del contrato:** casi todos los endpoints devuelven `{"data": ...}` sin `response_model`
> declarado, por lo que en OpenAPI aparecen como objetos genéricos. La única excepción es
> `GET /public/orders/by-payment-token`, que sí declara
> `response_model=dict[str, PublicOrderSnapshotResponse]` (`orders_r.py:496`).
> Como consecuencia, `api.generated.ts` aporta poca seguridad de tipos sobre las respuestas y el frontend
> mantiene sus **propios** tipos duplicados en `frontend/src/types.ts`.
> Ver [18_Roadmap.md](18_Roadmap.md#R-06).

---

← [01 Resumen](01_Resumen.md) | [Índice](README.md) | Siguiente: [03 Árbol del Proyecto](03_ArbolProyecto.md) →
