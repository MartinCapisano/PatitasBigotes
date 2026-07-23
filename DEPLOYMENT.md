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
- `BANK_TRANSFER_ALIAS` / `_CBU` / `_BANK_NAME` / `_HOLDER` / `_CUIT` y `WHATSAPP_NUMBER` = datos **reales** de la cuenta del comercio y su WhatsApp. **El backend no arranca sin ellos**: es el unico metodo de pago online y el cliente le transfiere plata a esa cuenta (ver [docs/banktransfer.md](docs/banktransfer.md))
- `MERCADOPAGO_ENABLED=false` = MercadoPago esta **en pausa** (ver [docs/mercadopago.md](docs/mercadopago.md)). Mientras siga en `false`, el resto de las `MERCADOPAGO_*` no hace falta completarlas
- `MERCADOPAGO_*` = credenciales y URLs reales de produccion (solo al reactivar MP)
- `MAINTENANCE_RUN_TOKEN` = token largo aleatorio (paso 4)
- `SMTP_HOST` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `MAIL_FROM` = credenciales de Gmail. **El backend no arranca sin las cuatro** (ver abajo)

> El `alembic upgrade head` del build corre contra Supabase; el proyecto debe estar activo (no pausado) durante el deploy.

### 2.1 SMTP con Gmail

`render.yaml` ya trae `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_TLS`, `SMTP_USERNAME` y `MAIL_FROM` con valor. La unica que hay que cargar a mano en el dashboard es **`SMTP_PASSWORD`** (`sync: false` — nunca va al repo).

**El backend no arranca si falta alguna.** Es deliberado: los emails se despachan despues del commit y se tragan sus errores, asi que en runtime una credencial revocada no da ningun sintoma — la tienda funciona perfecto y nadie recibe nada. El boot es el unico momento en que ese problema se ve, y ahi se ve en rojo. En local (`APP_ENV=local`) arranca igual y avisa con un `WARNING`.

Tres trampas de Gmail, en orden de cuanto tiempo hacen perder:

1. **`SMTP_PASSWORD` es un *app password*, no la contrasena de la cuenta.** Google solo ofrece la opcion si la cuenta tiene **verificacion en 2 pasos activada**. Sin 2FA no aparece por ningun lado, y no dice por que.
2. **`MAIL_FROM` tiene que ser la misma direccion que `SMTP_USERNAME`.** Si no coinciden, Gmail reescribe el header `From` y el cliente ve la casilla de Gmail igual — el remitente "lindo" no llega nunca.
3. **Un mail desde `@gmail.com` hablando de ordenes cae en spam mas seguido** que uno de dominio propio. Por eso el aviso de "revisa spam" en la app no es una formalidad. Si el volumen crece, la salida es un dominio propio con SPF/DKIM, no pelearle al filtro.

## 3. Frontend — Vercel / Cloudflare Pages

1. Importar el repo. Root directory: `frontend`.
2. Build command `npm run build`, output `dist` (ya declarado en `frontend/vercel.json`; para Cloudflare el fallback SPA esta en `frontend/public/_redirects`).
3. Setear la variable de build `VITE_API_BASE_URL` = URL publica del backend en Render (paso 2). Vite la "hornea" en el build, no se lee en runtime.
4. Setear `VITE_MERCADOPAGO_ENABLED=false` (MercadoPago en pausa): el checkout ofrece solo transferencia y efectivo. Tiene que coincidir con el `MERCADOPAGO_ENABLED` del backend.
5. Deploy. Anotar la URL publica resultante.

## 4. Cerrar el circulo (las dos URLs)

Con las URLs reales ya conocidas:

- En Render, setear `APP_BASE_URL` y `CORS_ALLOW_ORIGINS` con la URL del frontend. Redeploy.
- Con MercadoPago en pausa (`MERCADOPAGO_ENABLED=false`) no hay webhook que configurar ni URLs de MP que completar. Al reactivarlo: setear `MERCADOPAGO_SUCCESS_URL/FAILURE_URL/PENDING_URL` al frontend, `MERCADOPAGO_NOTIFICATION_URL` al backend (`.../payments/webhook/mercadopago`), y configurar el webhook en el panel de Mercado Pago apuntando ahi.

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
