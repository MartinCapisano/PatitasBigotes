# 03 — Árbol del Proyecto

← [02 Arquitectura](02_Arquitectura.md) | [Índice](README.md) | Siguiente: [04 Backend](04_Backend.md) →

---

## 1. Árbol completo

Generado desde `git ls-files` (284 archivos versionados). Se excluyen `node_modules/`, `dist/`, `.git/`, `.venv/`,
`.pytest_cache/` y `.ruff_cache/`, todos ignorados por `.gitignore` o no versionados.

```text
PatitasBigotes/
|-- .claude/
|   `-- launch.json                          # Config de dev servers para el agente (frontend 5173, backend 8000)
|-- .github/
|   `-- workflows/
|       |-- ci.yml                           # 3 jobs: backend-tests, contract-schema, frontend-tests
|       |-- db-backup.yml                    # pg_dump diario 04:00 UTC -> artifact 30 días
|       `-- maintenance.yml                  # Ping cada 13 min a /internal/maintenance/run
|-- backend/
|   |-- alembic/
|   |   |-- versions/
|   |   |   |-- 20260321_01_baseline_current_schema.py     # Baseline: crea todo desde schema_snapshot
|   |   |   |-- 20260322_01_add_payment_public_status_token.py
|   |   |   `-- 20260718_01_add_fk_indexes.py              # 6 índices sobre FKs
|   |   |-- env.py                           # Config Alembic; toma la URL de db/config.py
|   |   `-- schema_snapshot.py               # Copia congelada del schema para el baseline
|   |-- scripts/
|   |   |-- bootstrap.ps1                    # venv + deps + migraciones (+ -SeedDemo, -EnableJobs)
|   |   |-- export_openapi.py                # app.openapi() -> backend/openapi.json
|   |   |-- install-jobs.ps1                 # Registra tareas en Windows Task Scheduler
|   |   |-- jobs.ps1                         # status | enable | disable | reinstall | uninstall
|   |   |-- run-job.ps1                      # Ejecuta un job puntual
|   |   |-- seed-demo.ps1                    # Carga datos de demo
|   |   |-- start-app.ps1                    # Levanta backend + frontend en ventanas separadas
|   |   |-- start-backend.ps1                # uvicorn :8000
|   |   |-- start-frontend.ps1               # vite :5173
|   |   `-- start-webhook-reprocess-job.ps1
|   |-- source/
|   |   |-- db/
|   |   |   |-- config.py                    # 25 getters de env con validación fail-fast
|   |   |   |-- models.py                    # 17 modelos SQLAlchemy — única fuente del schema
|   |   |   `-- session.py                   # engine, SessionLocal, get_db, get_db_transactional
|   |   |-- dependencies/
|   |   |   |-- auth_d.py                    # get_current_user, get_current_user_id, require_admin
|   |   |   |-- csrf_d.py                    # CSRFMiddleware por Origin/Referer
|   |   |   |-- mercadopago_d.py             # Validación HMAC de la firma del webhook
|   |   |   `-- security_headers_d.py        # CSP, HSTS, X-Frame-Options, nosniff
|   |   |-- jobs/
|   |   |   |-- expire_stock_reservations_job.py
|   |   |   |-- idempotency_sweeper_job.py
|   |   |   |-- prune_auth_action_tokens_job.py
|   |   |   |-- prune_auth_login_throttles_job.py
|   |   |   |-- reconcile_pending_payments_job.py
|   |   |   `-- reprocess_failed_webhooks_job.py
|   |   |-- routes/
|   |   |   |-- auth_r.py                    # 11 endpoints de identidad
|   |   |   |-- discounts_r.py               # CRUD de descuentos (admin)
|   |   |   |-- maintenance_r.py             # POST /internal/maintenance/run
|   |   |   |-- mercadopago_r.py             # Webhook + replay admin
|   |   |   |-- notifications_r.py           # Bandeja in-app
|   |   |   |-- orders_r.py                  # Checkout, carrito, pagos, ventas admin (el más grande)
|   |   |   |-- payments_r.py                # Consulta de pagos e incidencias
|   |   |   |-- products_r.py                # CRUD admin de catálogo
|   |   |   |-- stock_reservations_r.py      # Expiración manual (admin)
|   |   |   |-- storefront_r.py              # Catálogo público (sin auth)
|   |   |   |-- turns_r.py                   # Turnos de peluquería
|   |   |   `-- users_r.py                   # Búsqueda, alta y revocación de admins
|   |   |-- schemas/
|   |   |   |-- __init__.py                  # Barrel: reexporta los 32 DTOs
|   |   |   |-- auth_s.py · discounts_s.py · orders_s.py · payments_s.py
|   |   |   |-- products_s.py · stock_reservations_s.py · turns_s.py · users_s.py
|   |   |-- services/                        # 27 archivos — ver tabla en la sección 3
|   |   |-- errors.py                        # Traductor único excepción -> HTTPException
|   |   |-- exceptions.py                    # 4 excepciones de dominio
|   |   `-- seed_demo.py                     # Catálogo demo + admin@demo.com (bloqueado en prod)
|   |-- tests/
|   |   |-- factories/                       # Builders de datos y helpers HTTP
|   |   |   |-- http_auth.py · http_catalog.py · http_checkout.py
|   |   |   |-- http_payments.py · http_webhooks.py · orders.py · users.py
|   |   |-- http/                            # 13 suites de integración sobre TestClient
|   |   |   |-- _base.py                     # HttpFundamentalsBase: SQLite en memoria + overrides
|   |   |   `-- test_*_fundamentals.py
|   |   `-- test_*.py                        # 26 suites unitarias / de servicio
|   |-- tmp/                                 # Convención de temporales (logs, tests, migrations) — solo .gitkeep
|   |-- .env.example                         # Plantilla local con valores compartidos precargados
|   |-- .env.production.example              # Plantilla de producción
|   |-- Dockerfile.sweeper                   # Imagen mínima solo para el sweeper (referencia)
|   |-- IDEMPOTENCY_SWEEPER_RUNBOOK.md
|   |-- alembic.ini
|   |-- k8s_idempotency_sweeper_{cronjob,externalsecret,sa,secret}.yaml   # Referencia, NO usados
|   |-- main.py                              # Punto de entrada FastAPI: middlewares + routers + /health
|   |-- requirements.txt                     # 10 deps de runtime
|   |-- requirements-dev.txt                 # + alembic, pytest, ruff
|   |-- requirements-sweeper.txt             # Solo 3 deps para el contenedor del sweeper
|   `-- ruff.toml
|-- frontend/
|   |-- public/
|   |   |-- patterns/                        # 2 SVG de fondo (patas y bigotes)
|   |   `-- _redirects                       # SPA fallback para Cloudflare Pages
|   |-- src/
|   |   |-- auth/AuthContext.tsx             # Re-export puente hacia features/auth
|   |   |-- components/Layout.tsx            # Shell: topbar, carrito, notificaciones, Outlet
|   |   |-- features/
|   |   |   |-- admin/                       # 13 componentes + 7 hooks + tipos + formato
|   |   |   |-- auth/                        # AuthProvider + 5 hooks de página + verification-storage
|   |   |   |-- checkout/                    # useCheckoutPage, usePaymentReturnStatus
|   |   |   |-- contact/                     # Datos estáticos
|   |   |   |-- profile/                     # useProfilePage
|   |   |   |-- storefront/                  # 3 hooks de catálogo
|   |   |   `-- turns/                       # useGroomingPage
|   |   |-- guards/                          # ProtectedRoute, AdminRoute
|   |   |-- lib/                             # cart-storage, useAsyncResource, useClickOutside, useModalA11y
|   |   |-- pages/                           # 14 páginas, todas lazy-loaded desde App.tsx
|   |   |-- services/                        # 12 clientes API + http.ts + http-errors.ts + idempotency.ts
|   |   |-- test/setup.ts                    # Setup de Vitest (@testing-library/jest-dom)
|   |   |-- types/api.generated.ts           # 3.992 líneas autogeneradas — COMMITEADO a propósito
|   |   |-- App.tsx                          # Router + AuthProvider + Suspense
|   |   |-- main.tsx                         # createRoot + BrowserRouter
|   |   |-- styles.css                       # Hoja de estilos única (no CSS modules, no Tailwind)
|   |   |-- types.ts                         # Tipos de dominio escritos a mano (paralelos a api.generated)
|   |   `-- vite-env.d.ts
|   |-- tmp/                                 # logs y tsbuildinfo — solo .gitkeep
|   |-- .env.example · .env.production.example · .nvmrc
|   |-- eslint.config.js · tsconfig*.json · vite.config.ts · vitest.config.ts
|   |-- index.html · package.json · package-lock.json
|   `-- vercel.json                          # buildCommand, outputDirectory, SPA rewrites
|-- .gitignore
|-- DEPLOYMENT.md                            # Guía de despliegue Render + Vercel + Supabase
|-- DEPLOYMENT_WALKTHROUGH.md                # Paso a paso contextual (ES)
|-- README.md                                # Puesta en marcha local
`-- render.yaml                              # Blueprint del web service en Render
```

---

## 2. Propósito y relaciones de cada carpeta

### Raíz

| Carpeta / archivo | Propósito | Relación con el resto |
|---|---|---|
| `.claude/` | Configuración del entorno agéntico: define cómo levantar frontend y backend | Aislado; no afecta al runtime |
| `.github/workflows/` | CI y los dos cron de producción | `ci.yml` valida `backend/` y `frontend/`; `maintenance.yml` invoca `maintenance_r.py`; `db-backup.yml` toca Supabase directamente |
| `render.yaml` | Blueprint de infra del backend | Declara las env vars que consume `backend/source/db/config.py` |
| `README.md`, `DEPLOYMENT*.md` | Documentación operativa preexistente | Complementan, no reemplazan, `docs/` |

### `backend/`

| Carpeta | Propósito | Responsabilidad | Depende de | Es usada por |
|---|---|---|---|---|
| `source/db/` | Fuente de verdad del schema y del acceso a datos | Definir modelos, leer env, abrir sesiones | `python-dotenv`, SQLAlchemy | **Todo** el backend |
| `source/routes/` | Adaptadores HTTP | Validar, delegar, traducir errores | `schemas/`, `services/`, `dependencies/`, `errors.py` | `main.py` |
| `source/services/` | Lógica de negocio | Invariantes, transiciones, orquestación | `db/models.py`, entre sí | `routes/`, `jobs/`, `seed_demo.py` |
| `source/schemas/` | Contratos de entrada | Validar forma y rangos con Pydantic | `pydantic` | `routes/` |
| `source/dependencies/` | Cross-cutting HTTP | Auth, CSRF, headers, firma de webhook | `db/`, `services/auth_*` | `main.py`, `routes/` |
| `source/jobs/` | Batch idempotente | Un `run_once()` autocontenido cada uno | `db/session.py`, `services/` | `maintenance_s.py`, Task Scheduler, K8s CronJob |
| `alembic/` | Versionado del schema | Migrar la DB hacia `models.py` | `source/db/` | `render.yaml` (`buildCommand`), `bootstrap.ps1` |
| `scripts/` | Tooling de desarrollo local (Windows) | Bootstrap, arranque, jobs, export de OpenAPI | El resto de `backend/` | Persona desarrolladora, CI (`export_openapi.py`) |
| `tests/` | Verificación | Unitarios + integración HTTP | Todo `source/` | CI |
| `tmp/` | Convención de artefactos temporales | Ninguna en runtime | — | — |

> 📌 **Convención de nombres del backend:** el sufijo indica la capa.
> `*_r.py` = router, `*_s.py` = service **o** schema (según la carpeta), `*_d.py` = dependency, `*_job.py` = job.
> ⚠️ El sufijo `_s` es ambiguo: `source/schemas/orders_s.py` y `source/services/orders_s.py` son archivos
> distintos con el mismo nombre. Se resuelve por la ruta del import, pero confunde al leer stack traces.

### `frontend/src/`

| Carpeta | Propósito | Responsabilidad | Depende de | Es usada por |
|---|---|---|---|---|
| `features/<dominio>/` | Slice vertical de un dominio | Hooks de página, componentes propios, tipos y utilidades del dominio | `services/`, `lib/` | `pages/` |
| `features/*/hooks/` | **Toda** la lógica de UI | Estado, fetching, validación, mensajes | `services/`, `lib/` | Componentes de página |
| `features/*/services/index.ts` | Barrel de reexport | Dar a la feature un punto de entrada estable hacia `src/services/` | `src/services/` | Hooks de la feature |
| `services/` | Clientes HTTP tipados | Una función por endpoint; desenvuelven `{data}` | `http.ts` | `features/`, `components/` |
| `lib/` | Utilidades transversales sin dominio | Carrito en localStorage, hooks genéricos | Ninguna del proyecto | `features/`, `components/` |
| `guards/` | Control de acceso por ruta | Redirigir según sesión y rol | `auth/AuthContext` | `App.tsx` |
| `pages/` | Composición de la vista | Renderizar; casi sin lógica | `features/*/hooks`, `components/` | `App.tsx` (lazy) |
| `components/` | Componentes globales | Solo `Layout` | `lib/`, `services/`, `auth/` | `App.tsx` |
| `types/` | Contrato autogenerado | Tipos derivados de OpenAPI | Generado por CI | Actualmente **poco usado** ⚠️ |
| `test/` | Setup de Vitest | Registrar matchers de jest-dom | — | `vitest.config.ts` |

> 📌 **Convención de nombres del frontend:** `use<Pantalla>Page.ts` = hook que concentra la lógica de una página;
> `<recurso>-api.ts` = cliente HTTP; `<Nombre>Section.tsx` = sección del panel admin.

---

## 3. Mapa de los 27 servicios de dominio

| Archivo | LOC | Contexto | Exporta (principales) |
|---|---:|---|---|
| `payment_s.py` | 1135 | Pagos | `create_payment_for_order`, `create_retry_payment_for_order`, `create_retry_payment_for_payment_token`, `apply_mercadopago_normalized_state`, `confirm_manual_payment_for_order`, `initialize_mercadopago_checkout_for_payment` |
| `orders_s.py` | 950 | Órdenes | `change_order_status`, `replace_draft_order_items`, `create_admin_sale`, `create_manual_submitted_order`, `get_public_order_snapshot_by_payment_token` |
| `products_s.py` | 946 | Catálogo | `list_storefront_products`, `get_storefront_product_by_id`, `list_admin_catalog`, CRUD de producto/variante/categoría |
| `discount_s.py` | 446 | Precios | `reprice_order_items`, `select_best_discount`, `calculate_line_pricing`, CRUD de descuentos |
| `mercadopago_client.py` | 439 | Proveedor | `create_checkout_preference`, `get_payment_by_id`, `create_refund`, `resolver_evento_webhook_mercadopago` |
| `stock_reservations_s.py` | 393 | Inventario | `reserve_stock_for_submitted_order`, `consume_reservations_for_paid_order`, `expire_active_reservations` |
| `webhook_events_s.py` | 386 | Webhooks | `acquire_webhook_event`, `mark_webhook_event_failed`, `replay_webhook_event_by_key` |
| `refund_s.py` | 378 | Reembolsos | `create_late_paid_incident_if_needed`, `create_mercadopago_refund`, `resolve_payment_incident_no_refund` |
| `auth_s.py` | 330 | Identidad | `authenticate_user`, `issue_token_pair`, `refresh_with_token`, `update_user_profile` |
| `users_s.py` | 314 | Identidad | `create_auth_user`, `create_admin_user`, `get_or_create_user_by_contact`, `search_users` |
| `mercadopago_normalization_s.py` | 301 | Proveedor | `normalize_mp_payment_state`, `_build_mercadopago_payload` |
| `anti_abuse_s.py` | 282 | Anti-abuso | `enforce_public_guest_checkout_limits`, `enforce_public_signup_limits`, … |
| `auth_security_s.py` | 195 | Identidad | `hash_password`, `create_access_token`, `decode_access_token`, `ensure_password_policy` |
| `idempotency_s.py` | 186 | Idempotencia | `acquire_record`, `mark_record_completed`, `load_replay_payload`, `prune_expired_records` |
| `auth_tokens_s.py` | 181 | Identidad | `create_one_time_token`, `consume_one_time_token`, `prune_auth_action_tokens` |
| `notifications_s.py` | 177 | Notificaciones | `create_admin_notification`, `list_notifications_for_user`, `mark_all_notifications_read` |
| `domain_events_s.py` | 151 | Eventos | `publish_domain_event` + 4 handlers |
| `turns_s.py` | 140 | Turnos | `create_turn_for_user`, `list_turns_for_admin`, `update_turn_status_for_admin` |
| `maintenance_s.py` | 139 | Operación | `run_all_maintenance`, `JOBS` |
| `payment_admin_queries_s.py` | 135 | Pagos (lectura) | `list_payments_for_admin`, `list_pending_bank_transfer_payments_for_admin` |
| `auth_rate_limit_s.py` | 128 | Anti-abuso | `enforce_login_rate_limit`, `register_login_failure`, `clear_login_failures` |
| `email_s.py` | 127 | Notificaciones | `send_email_verification`, `send_password_reset`, `send_order_paid_email` |
| `money_s.py` | 86 | Precios | `calcular_amount`, `parse_amount_to_cents`, `round_half_up_decimal` |
| `auth_cookies_s.py` | 78 | Identidad | `set_auth_cookies`, `clear_auth_cookies`, getters de token desde `Request` |
| `post_commit_actions_s.py` | 61 | Notificaciones | `enqueue_post_commit_order_paid_email`, `dispatch_post_commit_actions` |
| `payment_errors.py` | 25 | Pagos | 6 clases de excepción del proveedor |

Ficha detallada de cada uno en [04_Backend.md](04_Backend.md).

---

## 4. Dónde tocar según lo que quieras hacer

| Quiero… | Empezá por | Después tocá |
|---|---|---|
| Agregar un campo a producto | `db/models.py` → nueva migración Alembic | `schemas/products_s.py`, `services/products_s.py`, `services/admin-catalog-api.ts` |
| Cambiar cómo se calcula un descuento | `services/discount_s.py` | `tests/test_discounts_category_scope.py`, `tests/test_products_min_var_price.py` |
| Agregar un método de pago | `services/payment_s.py:38` (`ALLOWED_PAYMENT_METHODS`) | `schemas/payments_s.py`, `schemas/orders_s.py`, frontend `checkout-api.ts` |
| Cambiar el TTL de las reservas | `services/stock_reservations_s.py:11-13` | `tests/test_stock_reservations_expiration.py` |
| Agregar un job de mantenimiento | `jobs/nuevo_job.py` con `run_once()` | `services/maintenance_s.py:103` (lista `JOBS`), `scripts/jobs.ps1:15` |
| Agregar una pantalla del panel admin | `features/admin/types.ts` (nueva `AdminSection`) | nuevo hook + componente + `AdminPage.tsx` |
| Cambiar mensajes de error del usuario | `frontend/src/services/http-errors.ts` | — |
| Agregar una variable de entorno | `db/config.py` (getter con validación) | `.env.example`, `.env.production.example`, `render.yaml` |

---

← [02 Arquitectura](02_Arquitectura.md) | [Índice](README.md) | Siguiente: [04 Backend](04_Backend.md) →
