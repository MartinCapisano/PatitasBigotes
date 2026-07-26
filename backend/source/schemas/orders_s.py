from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

class ReplaceDraftItemsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list["ManualOrderItemRequest"] = Field(default_factory=list)


class UpdateOrderStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["draft", "submitted", "cancelled"]


class AdminRegisterPaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["cash", "bank_transfer"]
    paid_amount: int = Field(gt=0)
    change_amount: int | None = Field(default=None, ge=0)
    payment_ref: str | None = Field(default=None, min_length=1, max_length=255)


class ManualOrderCustomerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=6, max_length=30)


class ManualOrderItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant_id: int
    quantity: int = Field(gt=0)


class PublicGuestCheckoutItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant_id: int
    quantity: int = Field(gt=0, le=10)


class PublicGuestCheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer: ManualOrderCustomerRequest
    items: list[PublicGuestCheckoutItemRequest] = Field(min_length=1, max_length=20)
    website: str | None = Field(default=None, max_length=0)
    payment_method: Literal["bank_transfer", "mercadopago", "cash"] | None = None


class AuthenticatedCheckoutRequest(BaseModel):
    """Entrada del checkout autenticado unificado (R-03).

    Espejo de `PublicGuestCheckoutRequest` sin el bloque `customer` ni el honeypot
    `website`: el usuario viene del token, no del body. Reutiliza
    `PublicGuestCheckoutItemRequest` para no duplicar la validación de items.
    """

    model_config = ConfigDict(extra="forbid")
    items: list[PublicGuestCheckoutItemRequest] = Field(min_length=1, max_length=20)
    payment_method: Literal["bank_transfer", "mercadopago", "cash"] | None = None
    currency: str = "ARS"
    expires_in_minutes: int = Field(default=60, gt=0)


class AdminSalesCustomerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["existing", "new"]
    user_id: int | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=6, max_length=30)
    dni: str | None = Field(default=None, max_length=30)


class AdminSalesPaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["cash", "bank_transfer"]
    amount_paid: int = Field(gt=0)
    change_amount: int | None = Field(default=None, ge=0)
    payment_ref: str | None = Field(default=None, min_length=1, max_length=255)


class CreateAdminSaleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer: AdminSalesCustomerRequest
    items: list[ManualOrderItemRequest] = Field(min_length=1)
    register_payment: bool = False
    payment: AdminSalesPaymentRequest | None = None


class PublicOrderSnapshotItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_name: str | None
    variant_label: str
    quantity: int
    line_total: int


class PublicOrderSnapshotOrderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["draft", "submitted", "paid", "cancelled"]
    total_amount: int
    currency: str
    items: list[PublicOrderSnapshotItemResponse]


class PublicOrderSnapshotPaymentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["bank_transfer", "mercadopago", "cash"]
    status: Literal["pending", "paid", "cancelled", "expired"]
    amount: int
    currency: str
    checkout_url: str | None = None


class PublicOrderSnapshotFlagsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    can_continue_payment: bool
    can_retry_payment: bool
    is_order_open: bool
    is_payment_terminal: bool


class PublicOrderSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: PublicOrderSnapshotOrderResponse
    payment: PublicOrderSnapshotPaymentResponse
    flags: PublicOrderSnapshotFlagsResponse
    blocking_reason: Literal[
        "order_paid",
        "order_cancelled",
        "payment_pending",
        "payment_not_retryable",
        "stock_reservation_expired",
        "checkout_unavailable",
    ] | None = None


# --- Convención de DTOs de salida (`*Response`) -------------------------------
#
# R-06 / RM-1: espejo de salida de los `*Request`. Cada `*Response` describe la
# forma EXACTA del dict que un serializer del service devuelve, de modo que al
# declararlo como `response_model` el OpenAPI (y `api.generated.ts`) tipen la
# respuesta con su forma real en vez de `unknown`.
#
# Reglas de la convención:
#   - `extra="forbid"`: el DTO es un espejo fiel. Bajo `response_model` FastAPI
#     construye el modelo desde el dict devuelto; si sobra o falta una clave,
#     falla en serialización. Eso obliga a que schema y serializer no driftéen.
#   - Los DTO de orden/pago/cliente de abajo son COMPARTIDOS: los reutilizan los
#     tickets siguientes (RM-2 checkout guest, RM-3 mutaciones de pago) en lugar
#     de que cada endpoint invente el suyo. Antes de reusarlos, verificar que el
#     serializer del endpoint produce exactamente estas claves.
#   - Envoltura `{"data": ...}`: se declara como `dict[str, <DTO>]` en el
#     endpoint (mismo patrón que `GET /public/orders/by-payment-token`).


class UserBasicResponse(BaseModel):
    """Espejo de `serialize_user_basic` (services/users_s.py)."""

    model_config = ConfigDict(extra="forbid")
    id: int
    first_name: str
    last_name: str
    email: str
    dni: str | None
    phone: str | None
    has_account: bool


class OrderItemResponse(BaseModel):
    """Un renglón de orden tal como lo emite `_order_to_dict` (services/orders_s.py)."""

    model_config = ConfigDict(extra="forbid")
    id: int
    product_id: int
    variant_id: int
    product_name: str | None
    variant_label: str
    quantity: int
    unit_price: int
    discount_id: int | None
    discount_amount: int
    final_unit_price: int
    line_total: int


class OrderResponse(BaseModel):
    """Espejo de `_order_to_dict` (services/orders_s.py). DTO de orden compartido."""

    model_config = ConfigDict(extra="forbid")
    id: int
    user_id: int
    customer: UserBasicResponse | None
    status: Literal["draft", "submitted", "paid", "cancelled"]
    currency: str
    items: list[OrderItemResponse]
    subtotal: int
    discount_total: int
    total_amount: int
    pricing_frozen: bool
    pricing_frozen_at: datetime | None
    submitted_at: datetime | None
    paid_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PaymentResponse(BaseModel):
    """Espejo de `payment_to_dict` (services/payment_core_s.py) con
    `include_provider_payload=False` (el crudo del webhook nunca llega al cliente).
    DTO de pago compartido."""

    model_config = ConfigDict(extra="forbid")
    id: int
    order_id: int
    method: Literal["bank_transfer", "mercadopago", "cash"]
    status: Literal["pending", "paid", "cancelled", "expired"]
    amount: int
    change_amount: int | None
    currency: str
    idempotency_key: str | None
    external_ref: str | None
    preference_id: str | None
    public_status_token: str | None
    provider_status: str | None
    provider_payload_data: dict | None
    expires_at: datetime | None
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminSaleMetaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_created: bool
    payment_registered: bool
    order_paid_email_suppressed: bool


class CreateAdminSaleResponse(BaseModel):
    """Salida de `POST /admin/sales` (create_admin_sale). Compone los DTO
    compartidos de cliente/orden/pago."""

    model_config = ConfigDict(extra="forbid")
    customer: UserBasicResponse
    order: OrderResponse
    payment: PaymentResponse | None
    meta: AdminSaleMetaResponse
