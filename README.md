# PatitasBigotes

Aplicacion full stack para tienda y turnos, con backend en FastAPI y frontend en React/Vite.

Este README esta pensado para dejar el proyecto listo para correr en Windows con PowerShell, usando PostgreSQL local. La idea es que una persona pueda clonar el repo, configurar variables, cargar demo data y levantar la app sin depender de conocimiento previo del autor.

## Stack

- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL
- Frontend: React, TypeScript, Vite
- Auth: cookies HttpOnly + CSRF por origen
- Pagos: Mercado Pago

## Requisitos previos

- Python 3 instalado y disponible como `py` o `python`
- Node.js 18+ y `npm`
- PostgreSQL corriendo en local
- PowerShell

## Setup rapido

### 1. Clonar el repo

```powershell
git clone <TU_REPO_URL>
cd PatitasBigotes
```

### 2. Configurar variables de entorno

Crea estos archivos a partir de los examples:

```powershell
Copy-Item .\backend\.env.example .\backend\.env
Copy-Item .\frontend\.env.example .\frontend\.env
```

Archivos a editar:

- `backend/.env`
- `frontend/.env`

### 3. Reemplazar variables obligatorias en `backend/.env`

Para correr en local, revisa y completa estas variables:

| Variable | Que poner |
| --- | --- |
| `DATABASE_URL` | Tu conexion real a PostgreSQL local |
| `JWT_SECRET` | Un secreto largo y aleatorio |
| `APP_BASE_URL` | Normalmente `http://localhost:5173` |
| `CORS_ALLOW_ORIGINS` | Normalmente `http://localhost:5173,http://127.0.0.1:5173` |

Tambien ten presente estas variables con placeholder:

- `MERCADOPAGO_ACCESS_TOKEN`: reemplazar si vas a probar Mercado Pago
- `MERCADOPAGO_PUBLIC_KEY`: reemplazar si vas a probar Mercado Pago
- `MERCADOPAGO_WEBHOOK_SECRET`: reemplazar si vas a probar webhooks de Mercado Pago
- `MERCADOPAGO_NOTIFICATION_URL`: reemplazar si vas a usar webhooks de Mercado Pago desde una URL publica
- `SMTP_HOST`, `MAIL_FROM` y demas `SMTP_*`: reemplazar si vas a usar mails reales

Si no vas a usar Mercado Pago real ni emails, puedes dejar esos valores para mas adelante y correr el proyecto igual.

### 4. Revisar `frontend/.env`

El archivo `frontend/.env.example` ya trae el valor local esperado:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Si vas a usar backend local en `http://localhost:8000`, normalmente solo necesitas copiar el example sin cambios.

### 5. Instalar dependencias del frontend

```powershell
cd .\frontend
npm install
cd ..
```

### 6. Ejecutar bootstrap del backend

El bootstrap crea `.venv` si hace falta, instala dependencias Python y aplica migraciones:

```powershell
.\backend\scripts\bootstrap.ps1
```

Si quieres que al final tambien abra backend y frontend:

```powershell
.\backend\scripts\bootstrap.ps1 -StartApp
```

Si quieres dejar explicito que NO se instalaran jobs en Windows Task Scheduler:

```powershell
.\backend\scripts\bootstrap.ps1 -NoJobs
```

Si quieres instalar los jobs de automatizacion:

```powershell
.\backend\scripts\bootstrap.ps1 -InstallJobs
```

Si ademas quieres cargar datos demo en la base:

```powershell
.\backend\scripts\bootstrap.ps1 -SeedDemo
```

Ese flag hace que el bootstrap ejecute las migraciones y luego cargue:

- admin demo
- categorias
- productos
- variantes
- descuentos

Tambien puedes correr la seed manualmente si prefieres:

```powershell
.\backend\scripts\seed-demo.ps1
```

## Modos de uso

### Uso local simple

Pensado para levantar frontend + backend rapido y probar la app sin dejar automatizaciones residentes en Windows.

Comando sugerido:

```powershell
.\backend\scripts\bootstrap.ps1 -SeedDemo -NoJobs
```

Si quieres dejarla andando al terminar el bootstrap:

```powershell
.\backend\scripts\bootstrap.ps1 -SeedDemo -NoJobs -StartApp
```

### Uso con automatizacion

Pensado para un uso mas sostenido, donde quieras que los procesos de mantenimiento sigan corriendo aunque no dejes una consola abierta.

Comando sugerido:

```powershell
.\backend\scripts\bootstrap.ps1 -InstallJobs
```

Si ademas quieres datos demo para una base de prueba:

```powershell
.\backend\scripts\bootstrap.ps1 -SeedDemo -InstallJobs
```

Si ademas quieres abrir backend y frontend al terminar:

```powershell
.\backend\scripts\bootstrap.ps1 -InstallJobs -StartApp
```

### Remover automatizacion

Si instalaste jobs en Windows Task Scheduler y luego quieres removerlos:

```powershell
.\backend\scripts\jobs.ps1 uninstall
```

Tambien puedes consultar el estado actual:

```powershell
.\backend\scripts\jobs.ps1 status
```

## Credenciales demo

Si corriste la demo seed, el admin de prueba queda con:

- Email: `admin@demo.com`
- Password: `AdminDemo!123`

## Como levantar la app

### Backend

En una terminal desde la raiz del repo:

```powershell
.\backend\scripts\start-backend.ps1
```

Backend local:

- `http://localhost:8000`
- health check: `http://localhost:8000/health`

### Frontend

En otra terminal:

```powershell
cd .\frontend
npm run dev
```

Si prefieres abrir ambos desde un solo comando:

```powershell
.\backend\scripts\start-app.ps1
```

Frontend local:

- `http://localhost:5173`

## Flujo recomendado para alguien que clona por primera vez

1. Crear `backend/.env` y `frontend/.env` desde los examples.
2. Editar `backend/.env` con tu `DATABASE_URL` y tu `JWT_SECRET`.
3. Correr `npm install` en `frontend/`.
4. Correr `.\backend\scripts\bootstrap.ps1 -SeedDemo -NoJobs -StartApp`.
5. Si no usaste `-StartApp`, levantar backend con `.\backend\scripts\start-backend.ps1`.
6. Si no usaste `-StartApp`, levantar frontend con `npm run dev` dentro de `frontend/`.
7. Entrar al frontend y usar el admin demo si quieres probar datos iniciales.

## Variables de entorno

### Backend obligatorias para correr local

- `DATABASE_URL`
- `JWT_SECRET`
- `JWT_ALGORITHM`
- `JWT_ISSUER`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REFRESH_TOKEN_EXPIRE_DAYS`
- `APP_BASE_URL`
- `CORS_ALLOW_ORIGINS`
- `AUTH_COOKIE_ACCESS_NAME`
- `AUTH_COOKIE_REFRESH_NAME`
- `AUTH_COOKIE_SAMESITE`
- `AUTH_COOKIE_SECURE`
- `AUTH_COOKIE_DOMAIN`
- `AUTH_COOKIE_PATH_ACCESS`
- `AUTH_COOKIE_PATH_REFRESH`

### Backend opcionales para mails

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS`
- `MAIL_FROM`

Solo hacen falta si quieres probar verificacion por mail o reset de password por email.

### Backend opcionales para Mercado Pago

- `MERCADOPAGO_ACCESS_TOKEN`
- `MERCADOPAGO_TIMEOUT_SECONDS`
- `MERCADOPAGO_SUCCESS_URL`
- `MERCADOPAGO_FAILURE_URL`
- `MERCADOPAGO_PENDING_URL`
- `MERCADOPAGO_NOTIFICATION_URL`
- `MERCADOPAGO_WEBHOOK_SECRET`
- `MERCADOPAGO_WEBHOOK_MAX_AGE_SECONDS`
- `MERCADOPAGO_PUBLIC_KEY`
- `MERCADOPAGO_ENV`

Para pruebas reales de Mercado Pago en local, completa esas variables con credenciales sandbox y una URL publica para webhooks.

### Backend opcionales para jobs

- `WEBHOOK_REPROCESS_INTERVAL_MINUTES`
- `WEBHOOK_REPROCESS_BATCH_SIZE`
- `WEBHOOK_REPROCESS_MAX_ATTEMPTS`
- `WEBHOOK_REPROCESS_BASE_DELAY_MINUTES`
- `WEBHOOK_REPROCESS_MAX_DELAY_MINUTES`
- `PAYMENTS_RECONCILE_INTERVAL_MINUTES`
- `PAYMENTS_RECONCILE_BATCH_SIZE`
- `PAYMENTS_RECONCILE_MAX_AGE_HOURS`
- `PAYMENTS_RECONCILE_MIN_AGE_MINUTES`
- `AUTH_ACTION_TOKENS_PRUNE_INTERVAL_MINUTES`
- `AUTH_ACTION_TOKENS_PRUNE_OLDER_THAN_DAYS`
- `AUTH_ACTION_TOKENS_PRUNE_BATCH_SIZE`
- `AUTH_LOGIN_THROTTLES_PRUNE_INTERVAL_MINUTES`
- `AUTH_LOGIN_THROTTLES_PRUNE_OLDER_THAN_DAYS`
- `AUTH_LOGIN_THROTTLES_PRUNE_BATCH_SIZE`
- `STOCK_RESERVATIONS_JOB_INTERVAL_MINUTES`
- `STOCK_RESERVATIONS_JOB_BATCH_LIMIT`
- `STOCK_RESERVATIONS_JOB_MAX_BATCHES`

## Notas importantes de auth local

- El frontend usa cookies del backend con `withCredentials: true`.
- Usa siempre el mismo host para frontend y backend durante la sesion.
- No mezcles `localhost` y `127.0.0.1`, porque las cookies son host-scoped.

## Sintesis funcional

El proyecto cubre una tienda con catalogo, carrito, checkout y gestion de ordenes, junto con un flujo de turnos y un panel administrativo para operar productos, descuentos, ventas, pagos y reservas.

Tambien incluye autenticacion por cookies HttpOnly con CSRF, integracion con Mercado Pago, procesamiento de webhooks, manejo de reservas de stock, datos demo para prueba rapida y scripts de bootstrap/arranque para uso local en Windows.

## Agregados operativos

- Bootstrap de entorno con creacion de `.venv`, instalacion de dependencias y migraciones.
- Seed demo opcional con credenciales de administrador de prueba.
- Arranque separado o combinado de backend y frontend con `-StartApp`.
- Jobs opcionales para automatizacion local y comando para desinstalarlos cuando ya no se usen.
