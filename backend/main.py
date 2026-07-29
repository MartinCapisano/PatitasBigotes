import logging

from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from source.db.config import get_cors_allow_origins, validate_bank_transfer_config
from source.db.session import get_db
from source.observability.sentry_s import init_sentry
from source.services.idempotency_s import IdempotencyError
from source.dependencies.csrf_d import CSRFMiddleware
from source.dependencies.security_headers_d import SecurityHeadersMiddleware
from source.routes.auth_r import router as auth_router
from source.routes.discounts_r import router as discounts_router
from source.routes.maintenance_r import router as maintenance_router
from source.routes.mercadopago_r import router as mercadopago_router
from source.routes.notifications_r import router as notifications_router
from source.routes.orders_r import router as orders_router
from source.routes.payments_r import router as payments_router
from source.routes.products_r import router as products_router
from source.routes.stock_reservations_r import router as stock_reservations_router
from source.routes.storefront_r import router as storefront_router
from source.routes.turns_r import router as turns_router
from source.routes.users_r import router as users_router

# Sentry antes de crear la app para que instrumente FastAPI desde el arranque.
# No-op si no hay SENTRY_DSN (local/tests). Ver source/observability/sentry_s.py.
init_sentry()

app = FastAPI(
    title="Sales API",
    version="0.1.0",

)
logger = logging.getLogger(__name__)

# Bank transfer is the only online payment method: booting without its data
# means booting a shop that cannot be paid. Better to break the deploy here
# than to show a customer empty bank details.
validate_bank_transfer_config()

allowed_origins = get_cors_allow_origins()
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CSRFMiddleware)

app.include_router(products_router)
app.include_router(mercadopago_router)
app.include_router(orders_router)
app.include_router(users_router)
app.include_router(auth_router)
app.include_router(turns_router)
app.include_router(discounts_router)
app.include_router(payments_router)
app.include_router(notifications_router)
app.include_router(stock_reservations_router)
app.include_router(storefront_router)
app.include_router(maintenance_router)


@app.exception_handler(IdempotencyError)
async def handle_idempotency_error(request: Request, exc: IdempotencyError) -> JSONResponse:
    """Mapea los conflictos de idempotencia (transport-agnostic) a 409.

    El `detail` se conserva identico al HTTPException.detail que hoy se lanza
    inline en orders_r.py, para que el front lo siga leyendo sin cambios hasta
    que R-05 introduzca codigos de error estables.
    """
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


@app.get("/health")
def health_check():
    """Liveness: solo confirma que el proceso responde. No toca la base, asi que
    un pico de latencia de Supabase no marca el servicio como caido."""
    return {"status": "ok"}


@app.get("/health/ready")
def readiness_check(db: Session = Depends(get_db)):
    """Readiness: verifica que la base sea alcanzable. Devuelve 503 si no lo es,
    para que un monitor externo (o el healthCheckPath de Render) distinga
    "el proceso vive" de "el proceso puede atender pedidos"."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("event=readiness_check_failed component=database")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "db": "unreachable"},
        )
    return {"status": "ok", "db": "ok"}


