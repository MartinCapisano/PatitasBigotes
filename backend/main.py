import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from source.db.config import get_cors_allow_origins
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

app = FastAPI(
    title="Sales API",
    version="0.1.0",

)
logger = logging.getLogger(__name__)

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


@app.get("/health")
def health_check():
    return {"status": "ok"}


