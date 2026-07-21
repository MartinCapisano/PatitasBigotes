# Despliegue en produccion — PatitasBigotes

Arquitectura de produccion sobre free tiers:

| Pieza | Servicio | Notas del free tier |
|---|---|---|
| Frontend (Vite build estatico) | Vercel o Cloudflare Pages | Sirve archivos estaticos; TLS y dominio incluidos. |
| Backend (FastAPI) | Render (web service) | Duerme tras ~15 min sin trafico; 30-60s de cold start. |
| Base de datos (Postgres) | Supabase | Se pausa tras 7 dias sin actividad; sin backups automaticos. |

Frontend y backend viven en **dominios distintos**, asi que la app corre en modo cross-origin real (cookies `SameSite=None; Secure`, allowlist de CORS exacta). La proteccion CSRF la da el middleware de Origin/Referer (`backend/source/dependencies/csrf_d.py`), no `SameSite`.

Plantillas de variables: [`backend/.env.production.example`](backend/.env.production.example) y [`frontend/.env.production.example`](frontend/.env.production.example).

---

## 1. Base de datos — Supabase

1. Crear un proyecto en Supabase (proyecto separado del backend).
2. Copiar la connection string: Project Settings -> Database -> Connection string (URI). Incluir `sslmode=require`.
3. Guardarla; sera el `DATABASE_URL` del backend y el `SUPABASE_DATABASE_URL` del workflow de backup.

## 2. Backend — Render

Render puede levantar el servicio desde [`render.yaml`](render.yaml) (Blueprint) o creando un web service manual con:

- Root directory: `backend`
- Build command: `pip install -r requirements.txt && alembic upgrade head`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`

Cargar en el dashboard de Render todas las variables de `backend/.env.production.example`. Las criticas:

- `APP_ENV=production`
- `DATABASE_URL` = la de Supabase (paso 1)
- `JWT_SECRET` = secreto largo aleatorio
- `AUTH_COOKIE_SAMESITE=none` y `AUTH_COOKIE_SECURE=true` (obligatorio para cross-origin; el backend aborta si `none` sin `Secure`)
- `APP_BASE_URL` y `CORS_ALLOW_ORIGINS` = URL del frontend (paso 3); se completan despues de tener esa URL
- `MERCADOPAGO_*` = credenciales y URLs reales de produccion
- `MAINTENANCE_RUN_TOKEN` = token largo aleatorio (paso 4)

> El `alembic upgrade head` del build corre contra Supabase; el proyecto debe estar activo (no pausado) durante el deploy.

## 3. Frontend — Vercel / Cloudflare Pages

1. Importar el repo. Root directory: `frontend`.
2. Build command `npm run build`, output `dist` (ya declarado en `frontend/vercel.json`; para Cloudflare el fallback SPA esta en `frontend/public/_redirects`).
3. Setear la variable de build `VITE_API_BASE_URL` = URL publica del backend en Render (paso 2). Vite la "hornea" en el build, no se lee en runtime.
4. Deploy. Anotar la URL publica resultante.

## 4. Cerrar el circulo (las dos URLs)

Con las URLs reales ya conocidas:

- En Render, setear `APP_BASE_URL` y `CORS_ALLOW_ORIGINS` con la URL del frontend, y las `MERCADOPAGO_SUCCESS_URL/FAILURE_URL/PENDING_URL` al frontend, `MERCADOPAGO_NOTIFICATION_URL` al backend (`.../payments/webhook/mercadopago`). Redeploy.
- En el panel de Mercado Pago, configurar el webhook apuntando a `MERCADOPAGO_NOTIFICATION_URL`.

## 5. Jobs de mantenimiento (ping externo)

En el free tier de Render no hay cron ni proceso siempre despierto, asi que los jobs (reconciliacion de pagos, reprocesamiento de webhooks, expiracion de reservas de stock, sweep de idempotencia, prunes) se disparan por un ping externo a `POST /internal/maintenance/run`, protegido por `MAINTENANCE_RUN_TOKEN`.

El workflow [`.github/workflows/maintenance.yml`](.github/workflows/maintenance.yml) lo pinga cada ~13 min (tambien mantiene despierto a Render y activo a Supabase). Configurar como **repository secrets** de GitHub:

- `PROD_API_BASE_URL` = URL del backend en Render
- `MAINTENANCE_RUN_TOKEN` = el mismo valor seteado en Render

## 6. Backups de la base

Supabase free no trae backups automaticos. El workflow [`.github/workflows/db-backup.yml`](.github/workflows/db-backup.yml) corre `pg_dump` diario y guarda el dump como artifact (retencion 30 dias). Configurar el secret:

- `SUPABASE_DATABASE_URL` = la misma connection string de Supabase

Para retencion offsite/largo plazo, empujar el dump a object storage (S3/R2) ademas del artifact.

---

## Tolerancia al cold start

El primer request tras el sleep de Render tarda 30-60s. Por eso:

- El cliente HTTP del frontend usa timeout de 60s (`VITE_API_TIMEOUT_MS`, ver `frontend/src/services/http.ts`).
- El webhook de Mercado Pago puede fallar si pega justo cuando el backend duerme; Mercado Pago reintenta, y el job de reconciliacion + el de reprocesamiento de webhooks son la red de seguridad para que el pago termine consolidando.
