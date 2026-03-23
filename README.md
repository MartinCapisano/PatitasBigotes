# PatitasBigotes

## Backend env vars

1. Copy `backend/.env.example` to `backend/.env`.
2. Replace placeholder values with your local configuration.
3. Never commit `backend/.env` (it is ignored by git).
4. For Mercado Pago integration, set `MERCADOPAGO_ACCESS_TOKEN` and keep `MERCADOPAGO_ENV=sandbox` for test mode.
5. JWT defaults for auth are `ACCESS_TOKEN_EXPIRE_MINUTES=120` and `REFRESH_TOKEN_EXPIRE_DAYS=30`.
6. Set `JWT_ISSUER` consistently between token creation and validation.
7. For auth emails, configure SMTP (`SMTP_*`) and `MAIL_FROM`.
8. Set `APP_BASE_URL` so verification/reset links point to your frontend.
9. Cookie auth config:
   - `AUTH_COOKIE_ACCESS_NAME` (default `pb_at`)
   - `AUTH_COOKIE_REFRESH_NAME` (default `pb_rt`)
   - `AUTH_COOKIE_SAMESITE` (`lax|strict|none`)
   - `AUTH_COOKIE_SECURE` (`true` in prod HTTPS; `false` in local HTTP)
   - `AUTH_COOKIE_DOMAIN` (optional)
   - `AUTH_COOKIE_PATH_ACCESS` (default `/`)
   - `AUTH_COOKIE_PATH_REFRESH` (default `/auth`)
10. For CSRF origin checks, set `CORS_ALLOW_ORIGINS` to the exact frontend origin list.

## Database Migrations

Alembic is the source of truth for schema changes.

Run these commands from `backend/`.

Apply all pending migrations on a new or empty database:

```bash
alembic upgrade head
```

If an existing database is already aligned with the current schema baseline, mark it without reapplying DDL:

```bash
alembic stamp 20260321_01
```

Create a new migration after changing SQLAlchemy models:

```bash
alembic revision --autogenerate -m "describe change"
```

Notes:

1. `stamp` only records the revision in `alembic_version`; it does not change the schema.
2. Do not use `stamp` if the live schema diverges from the baseline.
3. Future schema changes must ship as Alembic revisions, not manual SQL in the README.

## Demo seed

Para cargar un admin demo, categorias, productos, variantes y descuentos de muestra:

```powershell
.\backend\scripts\seed-demo.ps1
```

Credenciales demo:

1. `admin@demo.com`
2. `AdminDemo!123`

## Auth cookie contract (backend phase 1)

Auth endpoints are cookie-based (cookie-only):

1. `POST /auth/login`: sets HttpOnly cookies `pb_at` + `pb_rt`, returns login status metadata (no tokens in body).
2. `POST /auth/refresh`: reads `pb_rt` cookie, rotates session, rewrites `pb_at` + `pb_rt` cookies.
3. `POST /auth/logout`: reads `pb_rt` cookie, invalidates refresh session, clears both cookies.
4. Protected endpoints read access token from `pb_at` cookie.

CSRF policy:

1. Unsafe methods (`POST|PUT|PATCH|DELETE`) require allowed `Origin` or `Referer`.
2. Allowed origins are derived from `CORS_ALLOW_ORIGINS`.
3. `POST /payments/webhook/mercadopago` is exempt.

## Frontend auth cookie (phase 2)

Frontend auth now uses backend cookies (`pb_at`, `pb_rt`) with `axios` credentials.

1. `frontend/src/services/http.ts` is configured with `withCredentials: true`.
2. Frontend no longer stores auth tokens or admin flags in `localStorage`.
3. Session bootstrap is done with `GET /auth/me` on app load.
4. Keep host consistency for API base URL:
   - Use only `localhost` or only `127.0.0.1`.
   - Do not alternate hosts, because cookies are host-scoped.

## Artefactos generados y carpetas temporales

La raiz del repo no debe guardar logs, bases temporales ni metadata de build.

Convencion oficial:

1. `backend/tmp/logs/`: logs locales del backend, tunnel y procesos auxiliares.
2. `backend/tmp/tests/`: SQLite temporales y artefactos persistentes de tests.
3. `backend/tmp/migrations/`: DBs/artefactos locales de validacion Alembic.
4. `frontend/tmp/logs/`: logs persistidos del frontend local.
5. `frontend/tmp/tsbuildinfo/`: metadata de TypeScript build mode.
6. `frontend/dist/`: build generado del frontend.

Reglas:

1. No dejar `*.db` ni `*.log` en la raiz del repo.
2. No versionar logs, DBs temporales ni `*.tsbuildinfo`.
3. Si persistes logs locales, deben ir solo a las carpetas listadas arriba.

## -JOBS-

Automatizacion de jobs de backend via Programador de tareas de Windows.

Comando unico:

```powershell
.\backend\scripts\jobs.ps1 <status|enable|disable|reinstall>
```

Comandos principales:

1. Ver estado:

```powershell
.\backend\scripts\jobs.ps1 status
```

2. Activar automatizacion:

```powershell
.\backend\scripts\jobs.ps1 enable
```

3. Desactivar automatizacion:

```powershell
.\backend\scripts\jobs.ps1 disable
```

Estado global:

1. `AUTOMATIZACION: ACTIVADA`: todas las tareas `PatitasBigotes_*` existen y no estan en `Disabled`.
2. `AUTOMATIZACION: DESACTIVADA`: falta alguna tarea o alguna esta en `Disabled`.

Jobs administrados:

1. `PatitasBigotes_WebhookReprocess` (cada 10 minutos)
2. `PatitasBigotes_PaymentsReconcile` (cada 4 horas)
3. `PatitasBigotes_ExpireStockReservations` (cada 15 minutos)
4. `PatitasBigotes_PruneAuthActionTokens` (diario)
5. `PatitasBigotes_PruneAuthLoginThrottles` (diario)

Notas de bootstrap:

1. `backend/scripts/bootstrap.ps1` ya no activa jobs automaticamente por default.
2. `bootstrap.ps1` aplica `alembic upgrade head` por default. Usa `-SkipMigrations` si queres omitir ese paso.
3. Para bootstrap + jobs en un paso:

```powershell
.\backend\scripts\bootstrap.ps1 -EnableJobs
```

## Guest checkout idempotency

`POST /checkout/guest` now requires header `Idempotency-Key`.

Behavior:

1. New key in scope `checkout_guest:<normalized_email>`: creates order (`201`).
2. Same key + same payload in same scope: replays original response (`201`), no new order.
3. Same key + different payload in same scope: returns `409 Conflict`.
4. Same key while the first request is still being processed: returns `409 Conflict`.

Idempotency records are stored in `idempotency_records` and expire after 24 hours.

## Admin sales flow (registrar venta)

Nuevo endpoint recomendado para ventas manuales en admin:

1. `POST /admin/sales`
   - Crea orden `submitted` para un usuario existente o nuevo.
   - Opcionalmente registra pago vinculado (`cash` o `bank_transfer`) y deja la orden en `paid`.
   - Soporta `Idempotency-Key` opcional para evitar duplicados por doble click.

### Legacy

1. `POST /orders/manual/submitted` sigue activo por compatibilidad, pero esta deprecado.
2. `POST /admin/orders/{order_id}/pay/manual` sigue activo para pagar ordenes existentes.

## Stock reservations expiration job

For production-like latency, reservation expiration should run outside request paths.

Run once:

```bash
python -m source.jobs.expire_stock_reservations_job --once
```

Run periodically (default every 60 minutes):

```bash
python -m source.jobs.expire_stock_reservations_job
```

Override interval:

```bash
python -m source.jobs.expire_stock_reservations_job --interval-minutes 240
```

Override batching behavior:

```bash
python -m source.jobs.expire_stock_reservations_job --batch-limit 200 --max-batches 20
```

Or via env var:

```bash
STOCK_RESERVATIONS_JOB_INTERVAL_MINUTES=240
STOCK_RESERVATIONS_JOB_BATCH_LIMIT=200
STOCK_RESERVATIONS_JOB_MAX_BATCHES=20
```

## Failed webhook reprocess job

If webhook processing fails (`webhook_events.status='failed'`), you can reprocess
those events in background without waiting for provider retries.

Run once:

```bash
python -m source.jobs.reprocess_failed_webhooks_job --once
```

Run periodically (default every 30 minutes, batch 25):

```bash
python -m source.jobs.reprocess_failed_webhooks_job
```

Dead-letter + retry policy defaults (small store profile):

1. `WEBHOOK_REPROCESS_INTERVAL_MINUTES=30`
2. `WEBHOOK_REPROCESS_BATCH_SIZE=25`
3. `WEBHOOK_REPROCESS_MAX_ATTEMPTS=4`
4. `WEBHOOK_REPROCESS_BASE_DELAY_MINUTES=30`
5. `WEBHOOK_REPROCESS_MAX_DELAY_MINUTES=720` (12h cap)

Override runtime values:

```bash
python -m source.jobs.reprocess_failed_webhooks_job --interval-minutes 30 --batch-size 100 --max-attempts 5 --base-delay-minutes 20 --max-delay-minutes 360
```

Or via env vars:

```bash
WEBHOOK_REPROCESS_INTERVAL_MINUTES=30
WEBHOOK_REPROCESS_BATCH_SIZE=100
WEBHOOK_REPROCESS_MAX_ATTEMPTS=5
WEBHOOK_REPROCESS_BASE_DELAY_MINUTES=20
WEBHOOK_REPROCESS_MAX_DELAY_MINUTES=360
```

## Pending payments reconciliation job

Reconciles pending Mercadopago payments in batch using `external_ref`.
Useful when webhooks are delayed/lost and internal state is still `pending`.

Run once:

```bash
python -m source.jobs.reconcile_pending_payments_job --once
```

Run periodically (default every 180 minutes, batch 50, max age 24h, min age 15m):

```bash
python -m source.jobs.reconcile_pending_payments_job
```

Override runtime values:

```bash
python -m source.jobs.reconcile_pending_payments_job --interval-minutes 180 --batch-size 100 --max-age-hours 24 --min-age-minutes 15
```

Or via env vars:

```bash
PAYMENTS_RECONCILE_INTERVAL_MINUTES=180
PAYMENTS_RECONCILE_BATCH_SIZE=100
PAYMENTS_RECONCILE_MAX_AGE_HOURS=24
PAYMENTS_RECONCILE_MIN_AGE_MINUTES=15
```

## Auth action tokens prune job

Run once:

```bash
python -m source.jobs.prune_auth_action_tokens_job --once
```

Run periodically (default daily):

```bash
python -m source.jobs.prune_auth_action_tokens_job
```

## Pagos MP en local (Uvicorn + ngrok fijo)

### Requisitos

1. Python y dependencias del backend instaladas.
2. `uvicorn` disponible en PATH (`pip install uvicorn`).
3. `ngrok` disponible en PATH (Windows: `winget install --id Ngrok.Ngrok -e`).
4. Cuenta de Mercado Pago Developers con una integracion de prueba.
5. Credenciales sandbox (`MERCADOPAGO_ACCESS_TOKEN`) y `MERCADOPAGO_WEBHOOK_SECRET`.
6. Cuentas de prueba de Mercado Pago (comprador/vendedor) para pruebas reales.
7. `ngrok` vinculado a tu cuenta (`ngrok config add-authtoken <tu_token>`).

### Configuracion inicial de `.env`

1. Copia `backend/.env.example` a `backend/.env`.
2. Completa:
   - `MERCADOPAGO_ACCESS_TOKEN=...` (de prueba/sandbox).
   - `MERCADOPAGO_WEBHOOK_SECRET=...` (de prueba/sandbox).
   - `MERCADOPAGO_ENV=sandbox`.
3. Configura tu propia URL publica para webhooks:
   - `MERCADOPAGO_NOTIFICATION_URL=https://tu-dominio-ngrok.ngrok-free.app/payments/webhook/mercadopago`
4. El retorno del checkout consulta el estado con `public_status_token` opaco agregado por backend. `external_ref` queda solo para proveedor y reconciliacion interna.

### Arranque local (2 terminales)

Terminal 1 (backend):

```powershell
.\backend\scripts\start-backend.ps1
```

Si quieres persistir la salida local del backend:

```powershell
.\backend\scripts\start-backend.ps1 -PersistLogs
```

Logs: `backend/tmp/logs/uvicorn.log`

Terminal 2 (tunnel ngrok fijo):

```powershell
.\backend\scripts\start-tunnel.ps1
```

Si quieres persistir la salida del tunnel:

```powershell
.\backend\scripts\start-tunnel.ps1 -PersistLogs
```

Logs: `backend/tmp/logs/ngrok.log`

El dominio esperado es algo como:
`https://tu-dominio-ngrok.ngrok-free.app`

### Paso manual obligatorio en Mercado Pago (panel web)

Debes pegar esta URL en:

`Mercado Pago Developers > Tus integraciones > App de prueba > Webhooks/Notificaciones > URL de notificacion`

`https://tu-dominio-ngrok.ngrok-free.app/payments/webhook/mercadopago`

Despues de guardar la URL, verifica si Mercado Pago muestra un `webhook secret` nuevo para esa configuracion. Si cambio, actualiza tambien `MERCADOPAGO_WEBHOOK_SECRET` en `backend/.env`.

### Nota sobre dominio fijo

- Con este dominio ngrok fijo no necesitas actualizar la URL por sesion.
- Solo vuelve a cambiarla si cambias de dominio en ngrok.

### Flujo de verificacion

1. Crear pago sandbox desde la app.
2. Pagar con comprador de prueba.
3. Confirmar que el webhook llega a `POST /payments/webhook/mercadopago`.
4. Confirmar que el estado interno se actualiza (`pending` -> `paid` u otro estado esperado).
