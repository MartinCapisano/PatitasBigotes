# Paso a paso del deploy (guía contextual)

Guía práctica y explicada para desplegar PatitasBigotes en producción sobre free tiers
(Supabase + Render + Vercel). Para la referencia técnica más escueta, ver [DEPLOYMENT.md](DEPLOYMENT.md).

Seguí el orden: hay dependencias entre pasos (uno necesita el resultado del anterior).

---

## Antes de empezar: preparativos

**Cuentas a crear** (todas gratis, todas dejan "iniciar sesión con GitHub"):

- Supabase (la base de datos)
- Render (el backend)
- Vercel (el frontend)

Tu repo ya está en GitHub, así que eso está.

**Generá dos secretos ahora** y guardalos en un bloc de notas — los vas a pegar más adelante.
En la terminal del proyecto, corré esto **dos veces**:

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

- El **primer** resultado → `JWT_SECRET` (firma las sesiones).
- El **segundo** resultado → `MAINTENANCE_RUN_TOKEN` (protege el endpoint de jobs).

**MercadoPago:** para cobrar de verdad necesitás las credenciales de producción (access token +
webhook secret) de tu panel de MercadoPago. Atajo para simplificar: podés desplegar primero con
`MERCADOPAGO_ENV=sandbox` (modo prueba) para verificar que el armado funciona, y cambiar a
producción después.

---

## Paso 1 — Base de datos en Supabase

**Por qué primero:** el backend necesita la dirección de la base para arrancar.

1. Entrá a supabase.com, iniciá sesión con GitHub, creá un **New project**. Ponele nombre y una
   **contraseña de base de datos** (guardala).
2. Esperá ~2 min a que se cree.
3. Andá a **Project Settings → Database → Connection string → URI**. Vas a ver algo así:
   `postgresql://postgres:[TU-PASSWORD]@db.xxxxx.supabase.co:5432/postgres`
4. Copiá esa cadena (reemplazando `[TU-PASSWORD]` por tu contraseña) y agregale `?sslmode=require`
   al final. **Guardala** — es tu `DATABASE_URL`.

> Si más adelante Render falla al conectar, volvé acá y probá la opción "Session pooler" que
> Supabase también ofrece. Pero probá primero con esta.

---

## Paso 2 — Backend en Render

**Por qué ahora:** ya tenés la base (paso 1). Al final de este paso vas a tener la **URL del
backend**, que necesita el frontend.

1. Entrá a render.com, iniciá sesión con GitHub.
2. **New → Blueprint** (Blueprint = "usá el `render.yaml` de mi repo"). Elegí `PatitasBigotes`.
   Render detecta el `render.yaml` solo.
3. Render te pide completar las variables marcadas como `sync: false`. Pegá, usando
   `backend/.env.production.example` como guía:
   - `DATABASE_URL` → la de Supabase (paso 1)
   - `JWT_SECRET` → el primer secreto generado
   - `AUTH_COOKIE_SAMESITE` → `none`
   - `AUTH_COOKIE_SECURE` → `true`
   - `MAINTENANCE_RUN_TOKEN` → el segundo secreto generado
   - `APP_BASE_URL` y `CORS_ALLOW_ORIGINS` → poné algo **temporal** (ej.
     `https://temporal.vercel.app`); los corregís en el Paso 4
   - `MERCADOPAGO_*` → si vas por sandbox, `MERCADOPAGO_ENV=sandbox` + tus credenciales de prueba;
     las URLs pueden quedar temporales por ahora
4. **Apply / Deploy.** Render instala dependencias, corre las migraciones (`alembic upgrade head`)
   contra Supabase y levanta la API.

   > `AUTH_COOKIE_SECURE=true` es obligatorio junto con `SameSite=none`. Si te olvidás uno, el
   > backend aborta a propósito (es un guard, no un bug).

5. Cuando termine (verde), Render muestra la **URL del backend**, tipo
   `https://patitasbigotes-api.onrender.com`. **Guardala.**
6. Verificá: abrí `https://tu-backend.onrender.com/health` → debe responder `{"status":"ok"}`.

---

## Paso 3 — Frontend en Vercel

**Por qué ahora:** ya tenés la URL del backend (paso 2), que el frontend necesita.

1. Entrá a vercel.com, iniciá sesión con GitHub, **Add New → Project**, elegí tu repo.
2. **Root Directory** → `frontend` (el frontend vive en esa subcarpeta).
3. En **Environment Variables**:
   - `VITE_API_BASE_URL` → la URL del backend de Render (paso 2)
4. **Deploy.** Vercel lee tu `vercel.json`, buildea y publica.
5. Te da la **URL del frontend**, tipo `https://patitasbigotes.vercel.app`. **Guardala.**

---

## Paso 4 — Cerrar el círculo (conectar las dos URLs)

**Por qué:** en el paso 2 pusiste una URL temporal para el frontend porque todavía no existía.
Ahora que la tenés, hay que corregirla, si no el backend rechaza al frontend (CORS) y las cookies
no funcionan.

1. Volvé a **Render → tu servicio → Environment** y corregí:
   - `APP_BASE_URL` → la URL real del frontend (paso 3)
   - `CORS_ALLOW_ORIGINS` → la misma URL del frontend
   - `MERCADOPAGO_SUCCESS_URL` / `FAILURE_URL` / `PENDING_URL` →
     `https://tu-frontend.vercel.app/payments/success` (y failure, pending)
   - `MERCADOPAGO_NOTIFICATION_URL` → `https://tu-backend.onrender.com/payments/webhook/mercadopago`
2. Guardá → Render re-despliega solo.
3. (Solo si vas a cobrar de verdad) en el panel de MercadoPago, configurá el webhook apuntando a
   esa `MERCADOPAGO_NOTIFICATION_URL`.

En este punto la app **ya funciona**: entrá a la URL del frontend, registrate y logueate. Si el
login persiste al recargar, las cookies cross-origin están andando.

---

## Paso 5 — Jobs de mantenimiento y backup (GitHub)

**Por qué:** Render gratis se duerme y no tiene cron. Estos secretos hacen que GitHub despierte al
backend cada 13 min, corra los jobs, y haga backups de la base.

1. En GitHub: repo → **Settings → Secrets and variables → Actions → New repository secret**.
   Creá tres:
   - `PROD_API_BASE_URL` → la URL del backend de Render
   - `MAINTENANCE_RUN_TOKEN` → **el mismo** segundo secreto que pusiste en Render (deben coincidir)
   - `SUPABASE_DATABASE_URL` → la misma `DATABASE_URL` de Supabase
2. Listo. Los workflows ya están en el repo; GitHub los corre solos.
3. Para probar el de mantenimiento sin esperar: repo → pestaña **Actions → "Maintenance ping" →
   Run workflow**. Verde = funciona.

---

## Paso 6 — Verificar

- **Frontend:** abrí la URL de Vercel, navegá el catálogo, registrate/logueate.
- **Backend:** `/health` responde ok.
- **Cross-origin:** que el login no te expulse al recargar = cookies OK.
- **Jobs:** pestaña Actions de GitHub, "Maintenance ping" en verde.
- **Cold start:** la primera visita tras un rato de inactividad tarda 30-60s (el backend se
  despertó). Es esperado; el frontend lo tolera con el timeout de 60s.

---

**Resumen del orden y sus dependencias:** Supabase da la base → Render da la URL del backend →
Vercel usa esa URL → volvés a Render a poner la URL del frontend → GitHub para los jobs.
