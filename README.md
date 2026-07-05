# PatitasBigotes

PatitasBigotes es una aplicacion full stack orientada a mostrar un flujo completo de tienda online y gestion operativa: catalogo, autenticacion, carrito, checkout, pagos, panel administrativo y procesos de soporte en backend. El proyecto esta pensado como demo tecnica para evaluacion y tambien como base funcional para pruebas reales en entorno local.

## Stack

- Backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL
- Frontend: React, TypeScript, Vite
- Auth: JWT en cookies HttpOnly + CSRF
- Pagos: Mercado Pago
- Scripts y entorno local: PowerShell sobre Windows

## Requisitos

Antes de levantar la aplicacion en local, es necesario contar con lo siguiente:

- Python 3
- Node.js
- npm
- PostgreSQL
- PowerShell sobre Windows

`bootstrap.ps1` prepara el entorno del backend, pero no instala dependencias globales del sistema como Node.js, npm o PostgreSQL.

## Puesta En Marcha Local

Para levantar la aplicacion en local, asumimos la convencion de desarrollo del proyecto con frontend en `http://localhost:5173` y backend en `http://localhost:8000`. El repositorio ya incluye un `backend/.env.example` con las variables compartidas del proyecto precargadas, como URLs locales, expiraciones, cookies y parametros operativos. Tambien incluye `frontend/.env.example`, que ya apunta al backend local mediante `VITE_API_BASE_URL=http://localhost:8000`.

Como primer paso, hay que crear `backend/.env` copiando `backend/.env.example`, y crear `frontend/.env` copiando `frontend/.env.example`. En principio no hace falta modificar las variables compartidas si se mantiene la convencion local del proyecto. La persona que levante la app debe completar las variables sensibles o dependientes de su entorno, principalmente `DATABASE_URL` y `JWT_SECRET`, y opcionalmente las credenciales de `SMTP` si quiere probar envio de mails (Hoy no implementado al 100%).

Antes de correr las migraciones, es necesario verificar que la base de datos configurada en `DATABASE_URL` exista y que PostgreSQL este disponible en ese entorno. Despues, desde PowerShell, puede ejecutarse `backend/scripts/bootstrap.ps1`, que prepara la virtualenv del backend, instala dependencias de Python y aplica las migraciones. Si ademas se quiere cargar informacion de prueba, puede usarse la opcion `-SeedDemo`.

El proyecto tambien incluye jobs programados para tareas de mantenimiento y sincronizacion. Si se quieren instalar desde el inicio, `bootstrap.ps1` permite usar la opcion `-EnableJobs`. Si la app ya fue levantada y los jobs no estan activos, pueden instalarse manualmente con `backend/scripts/jobs.ps1 enable`. Como esos jobs quedan registrados como tareas programadas de Windows, en entornos locales suele ser conveniente y casi necesario desinstalarlos cuando se deja de usar la app o cuando se quiere evitar ejecuciones en segundo plano; para eso puede usarse `backend/scripts/jobs.ps1 uninstall`. Si solo se quieren pausar temporalmente, puede usarse `backend/scripts/jobs.ps1 disable`. Entre esos procesos se encuentra el job de reconciliacion de pagos pendientes, utilizado para volver a consultar estados en Mercado Pago cuando hace falta.

Con el entorno preparado, el backend puede iniciarse con `backend/scripts/start-backend.ps1` en el puerto `8000`, y el frontend con `backend/scripts/start-frontend.ps1` en el puerto `5173`. Si se prefiere abrir ambos juntos, puede usarse `backend/scripts/start-app.ps1`, que lanza backend y frontend en ventanas separadas.

## Variables A Completar

Quien levante la app debe revisar y completar en `backend/.env` las variables que dependen de su entorno o de credenciales propias:

- `DATABASE_URL`
- `JWT_SECRET`
- `SMTP_HOST`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `MAIL_FROM`

## Mercado Pago

Para probar la integracion con Mercado Pago, hay que completar en `backend/.env` las variables de esa seccion a partir de `backend/.env.example`. En particular, deben revisarse `MERCADOPAGO_ACCESS_TOKEN`, `MERCADOPAGO_WEBHOOK_SECRET` (no es estrictamente necesario si no se va a configurar el webhook), `MERCADOPAGO_ENV`, `MERCADOPAGO_SUCCESS_URL`, `MERCADOPAGO_FAILURE_URL`, `MERCADOPAGO_PENDING_URL` y `MERCADOPAGO_NOTIFICATION_URL`.

Las URLs y el modo de ejecucion ya se encuentran definidos en `backend/.env.example` de acuerdo con la configuracion local asumida por el proyecto, por lo que no es necesario modificarlos si se mantiene ese entorno. En cambio, las credenciales sensibles deben completarse manualmente con datos obtenidos desde la cuenta de Mercado Pago utilizada para la prueba. `MERCADOPAGO_ACCESS_TOKEN` debe cargarse con el access token de la aplicacion configurada en Mercado Pago, mientras que `MERCADOPAGO_WEBHOOK_SECRET` debe cargarse con el secreto asociado al webhook definido en esa misma aplicacion dentro del panel de desarrolladores.

Las URLs de retorno ya estan pensadas para el flujo local del proyecto: el frontend corre en `http://localhost:5173` y recibe al usuario cuando Mercado Pago redirige a las pantallas de `success`, `failure` o `pending`. A su vez, la URL `MERCADOPAGO_NOTIFICATION_URL` define el endpoint del backend que recibiria las notificaciones automaticas del proveedor. En este proyecto, ese endpoint es `http://localhost:8000/payments/webhook/mercadopago`, y tambien viene declarado en el `.env.example` como referencia base.

Si el webhook no se configura o no esta accesible desde Internet, no hay problema para una prueba local: el checkout igual puede abrirse y el pago puede realizarse. La diferencia es que la actualizacion del estado no sera inmediata por webhook, sino diferida a traves del job de reconciliacion de pagos pendientes, siempre que esa automatizacion este instalada y activa.
