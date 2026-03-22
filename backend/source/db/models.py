from datetime import UTC, datetime
import secrets

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def utc_now() -> datetime:
    return datetime.now(UTC)


def generate_public_status_token() -> str:
    return secrets.token_urlsafe(32)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    img_url = Column(String, nullable=True)

    category_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )

    category = relationship("Category", back_populates="products")
    discount_links = relationship("DiscountProduct", back_populates="product")
    variants = relationship("ProductVariant", back_populates="product")


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_product_variants_price_non_negative"),
    )

    id = Column(Integer, primary_key=True, index=True)

    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )

    sku = Column(String, nullable=False, unique=True, index=True)
    size = Column(String, nullable=True)
    color = Column(String, nullable=True)
    img_url = Column(String, nullable=True)
    price = Column(Integer, nullable=False)
    stock = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    product = relationship("Product", back_populates="variants")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)

    email = Column(String, nullable=False, unique=True, index=True)
    dni = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    has_account = Column(Boolean, default=False, nullable=False)
    token_version = Column(Integer, nullable=False, default=1)

    is_admin = Column(Boolean, default=False, nullable=False)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    email_verification_sent_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    orders = relationship("Order", back_populates="user")
    turns = relationship("Turn", back_populates="user")
    refresh_session = relationship(
        "UserRefreshSession",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    auth_action_tokens = relationship(
        "AuthActionToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class AuthLoginThrottle(Base):
    __tablename__ = "auth_login_throttles"
    __table_args__ = (
        Index("uq_auth_login_throttles_scope_key", "scope", "key", unique=True),
        CheckConstraint(
            "failed_count >= 0",
            name="ck_auth_login_throttles_failed_count_non_negative",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    scope = Column(String, nullable=False, index=True)
    key = Column(String, nullable=False, index=True)
    failed_count = Column(Integer, nullable=False, default=0)
    window_started_at = Column(DateTime(timezone=True), nullable=False)
    blocked_until = Column(DateTime(timezone=True), nullable=True, index=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class Turn(Base):
    __tablename__ = "turns"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status = Column(String, nullable=False, default="pending")
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user = relationship("User", back_populates="turns")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="ck_orders_subtotal_non_negative"),
        CheckConstraint("discount_total >= 0", name="ck_orders_discount_total_non_negative"),
        CheckConstraint("total_amount >= 0", name="ck_orders_total_amount_non_negative"),
    )

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status = Column(String, nullable=False, default="draft")
    currency = Column(String, nullable=False, default="ARS")
    subtotal = Column(Integer, nullable=False, default=0)
    discount_total = Column(Integer, nullable=False, default=0)
    total_amount = Column(Integer, nullable=False, default=0)
    pricing_frozen = Column(Boolean, nullable=False, default=False)
    pricing_frozen_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user = relationship("User", back_populates="orders")
    items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )
    payments = relationship(
        "Payment",
        back_populates="order",
        cascade="all, delete-orphan",
    )
    payment_incidents = relationship(
        "PaymentIncident",
        back_populates="order",
        cascade="all, delete-orphan",
    )
    payment_refunds = relationship(
        "PaymentRefund",
        back_populates="order",
        cascade="all, delete-orphan",
    )
    stock_reservations = relationship(
        "StockReservation",
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_non_negative"),
        CheckConstraint("discount_amount >= 0", name="ck_order_items_discount_amount_non_negative"),
        CheckConstraint("final_unit_price >= 0", name="ck_order_items_final_unit_price_non_negative"),
        CheckConstraint("line_total >= 0", name="ck_order_items_line_total_non_negative"),
    )

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    variant_id = Column(
        Integer,
        ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=False,
    )

    quantity = Column(Integer, nullable=False)
    unit_price = Column(Integer, nullable=False)
    discount_id = Column(
        Integer,
        ForeignKey("discounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    discount_amount = Column(Integer, nullable=False, default=0)
    final_unit_price = Column(Integer, nullable=False, default=0)
    line_total = Column(Integer, nullable=False, default=0)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")
    variant = relationship("ProductVariant")
    discount = relationship("Discount")
    stock_reservations = relationship(
        "StockReservation",
        back_populates="order_item",
        cascade="all, delete-orphan",
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index(
            "uq_payments_one_pending_per_order_method",
            "order_id",
            "method",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        CheckConstraint("amount >= 0", name="ck_payments_amount_non_negative"),
        CheckConstraint(
            "change_amount IS NULL OR change_amount >= 0",
            name="ck_payments_change_amount_non_negative",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    method = Column(String, nullable=False)  # bank_transfer | mercadopago | cash
    status = Column(String, nullable=False, default="pending")
    amount = Column(Integer, nullable=False)
    change_amount = Column(Integer, nullable=True)
    currency = Column(String, nullable=False, default="ARS")

    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    external_ref = Column(String, nullable=True, index=True)
    preference_id = Column(String, nullable=True, index=True)
    public_status_token = Column(
        String,
        nullable=False,
        unique=True,
        index=True,
        default=generate_public_status_token,
    )
    provider_status = Column(String, nullable=True)
    provider_payload = Column(String, nullable=True)
    receipt_url = Column(String, nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    order = relationship("Order", back_populates="payments")
    incidents = relationship(
        "PaymentIncident",
        back_populates="payment",
        cascade="all, delete-orphan",
    )
    refunds = relationship(
        "PaymentRefund",
        back_populates="payment",
        cascade="all, delete-orphan",
    )


class PaymentIncident(Base):
    __tablename__ = "payment_incidents"
    __table_args__ = (
        Index(
            "uq_payment_incidents_open_per_payment_type",
            "payment_id",
            "type",
            unique=True,
            postgresql_where=text("status = 'pending_review'"),
            sqlite_where=text("status = 'pending_review'"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_id = Column(
        Integer,
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="pending_review", index=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    order = relationship("Order", back_populates="payment_incidents")
    payment = relationship("Payment", back_populates="incidents")
    resolved_by = relationship("User")
    refunds = relationship(
        "PaymentRefund",
        back_populates="incident",
        cascade="all, delete-orphan",
    )


class PaymentRefund(Base):
    __tablename__ = "payment_refunds"
    __table_args__ = (
        Index(
            "uq_payment_refunds_active_per_payment",
            "payment_id",
            unique=True,
            postgresql_where=text("status IN ('requested','approved')"),
            sqlite_where=text("status IN ('requested','approved')"),
        ),
        CheckConstraint("amount > 0", name="ck_payment_refunds_amount_positive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_id = Column(
        Integer,
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    incident_id = Column(
        Integer,
        ForeignKey("payment_incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount = Column(Integer, nullable=False)
    currency = Column(String, nullable=False, default="ARS")
    provider = Column(String, nullable=False, default="mercadopago")
    provider_refund_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="requested", index=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    requested_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    requested_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    provider_payload = Column(Text, nullable=True)

    order = relationship("Order", back_populates="payment_refunds")
    payment = relationship("Payment", back_populates="refunds")
    incident = relationship("PaymentIncident", back_populates="refunds")
    requested_by = relationship("User")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_read_created", "user_id", "is_read", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    role_target = Column(String, nullable=True, index=True)  # admin | null
    event_type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payment_id = Column(
        Integer,
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    incident_id = Column(
        Integer,
        ForeignKey("payment_incidents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dedupe_key = Column(String, nullable=True, unique=True, index=True)
    is_read = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="notifications")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="ck_webhook_events_attempt_count_non_negative"),
        Index(
            "ix_webhook_events_provider_status_retry",
            "provider",
            "status",
            "next_retry_at",
        ),
        Index("ix_webhook_events_dead_letter_at", "dead_letter_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False, index=True)
    event_key = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="processing")
    payload = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    dead_letter_at = Column(DateTime(timezone=True), nullable=True)


class StockReservation(Base):
    __tablename__ = "stock_reservations"
    __table_args__ = (
        Index(
            "ix_stock_reservations_variant_status_expires",
            "variant_id",
            "status",
            "expires_at",
        ),
        Index("ix_stock_reservations_order_status", "order_id", "status"),
        Index("ix_stock_reservations_status_expires", "status", "expires_at"),
        Index(
            "uq_stock_reservation_active_per_item",
            "order_item_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        CheckConstraint("quantity > 0", name="ck_stock_reservations_quantity_positive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_item_id = Column(
        Integer,
        ForeignKey("order_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    variant_id = Column(
        Integer,
        ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="active")
    reactivation_count = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    order = relationship("Order", back_populates="stock_reservations")
    order_item = relationship("OrderItem", back_populates="stock_reservations")
    variant = relationship("ProductVariant")


class Discount(Base):
    __tablename__ = "discounts"
    __table_args__ = (
        CheckConstraint("value > 0", name="ck_discounts_value_positive"),
        CheckConstraint(
            "("
            "(scope = 'all' AND category_id IS NULL AND product_id IS NULL)"
            " OR "
            "(scope = 'category' AND category_id IS NOT NULL AND product_id IS NULL)"
            " OR "
            "(scope = 'product' AND category_id IS NULL AND product_id IS NOT NULL)"
            " OR "
            "(scope = 'product_list' AND category_id IS NULL AND product_id IS NULL)"
            ")",
            name="ck_discounts_scope_target_consistency",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # percent | fixed
    value = Column(Integer, nullable=False)

    scope = Column(String, nullable=False)  # all | category | product | product_list
    category_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    is_active = Column(Boolean, default=True, nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    product_links = relationship("DiscountProduct", back_populates="discount")


class DiscountProduct(Base):
    __tablename__ = "discount_products"

    discount_id = Column(
        Integer,
        ForeignKey("discounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )

    discount = relationship("Discount", back_populates="product_links")
    product = relationship("Product", back_populates="discount_links")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        Index(
            "uq_idempotency_records_scope_key",
            "scope",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_idempotency_records_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    scope = Column(String, nullable=False, index=True)
    idempotency_key = Column(String, nullable=False, index=True)
    request_hash = Column(String, nullable=False)
    response_payload = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="completed")
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class UserRefreshSession(Base):
    __tablename__ = "user_refresh_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    token_hash = Column(String, nullable=False)
    token_jti = Column(String, nullable=False, index=True)
    claim_sub = Column(String, nullable=False)
    claim_type = Column(String, nullable=False)
    claim_iss = Column(String, nullable=False)
    claim_iat = Column(DateTime(timezone=True), nullable=False)
    claim_exp = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    user = relationship("User", back_populates="refresh_session")


class AuthActionToken(Base):
    __tablename__ = "auth_action_tokens"
    __table_args__ = (
        Index("uq_auth_action_tokens_token_hash", "token_hash", unique=True),
        Index("ix_auth_action_tokens_user_action_expires", "user_id", "action", "expires_at"),
        Index("ix_auth_action_tokens_action_expires", "action", "expires_at"),
        Index("ix_auth_action_tokens_used_at", "used_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = Column(String, nullable=False, index=True)
    token_hash = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    requested_ip = Column(String, nullable=True)
    meta = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="auth_action_tokens")

