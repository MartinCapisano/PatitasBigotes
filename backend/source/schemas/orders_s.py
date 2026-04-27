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
