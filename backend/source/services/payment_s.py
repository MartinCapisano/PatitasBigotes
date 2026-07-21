"""Core payment lifecycle: creation, retries, manual/provider confirmation, and state transitions.

MercadoPago-specific payload shaping lives in mercadopago_normalization_s.py, generic
webhook event bookkeeping in webhook_events_s.py, and admin listing queries in
payment_admin_queries_s.py — all split out of what used to be a single ~1900-line file.
"""
from __future__ import annotations

from datetime import datetime, timedelta, UTC
import hashlib
import json

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from source.db.models import (
    Order,
    Payment,
    StockReservation,
    generate_public_status_token,
)
from source.exceptions import PaymentRetryConflictError
from source.services.refund_s import create_late_paid_incident_if_needed
from source.services.domain_events_s import publish_domain_event
from source.services.mercadopago_normalization_s import (
    _build_mercadopago_payload,
    _get_checkout_external_ref,
    _get_checkout_preference_id,
    _has_checkout_preference,
)
from source.services.stock_reservations_s import (
    consume_reservations_for_paid_order,
    expire_active_reservations_for_order,
    list_active_reservations_for_order,
)

ALLOWED_PAYMENT_METHODS = {"bank_transfer", "mercadopago", "cash"}
RETRYABLE_PAYMENT_STATUSES = {"cancelled", "expired"}
PAYMENT_PROVIDER_SETUP_FAILED = "setup_failed"
RETRY_NOT_ALLOWED_ORDER_CANCELLED = "retry not allowed: order cancelled"
RETRY_NOT_ALLOWED_ORDER_CANCELLED_STOCK_EXPIRED = "retry not allowed: order cancelled because stock reservation expired"
RETRY_NOT_ALLOWED_ORDER_NOT_SUBMITTED = "retry not allowed: order is no longer submitted"
RETRY_NOT_ALLOWED_ORDER_ALREADY_PAID = "retry not allowed: order already paid"
RETRY_NOT_ALLOWED_STOCK_RESERVATION_EXPIRED = "retry not allowed: stock reservation expired"
RETRY_NOT_ALLOWED_PAYMENT_STATE_CHANGED = "retry not allowed: payment state changed"
RETRY_FAILED_MERCADOPAGO_CHECKOUT_UNAVAILABLE = "retry failed: mercadopago checkout unavailable"
ALLOWED_PAYMENT_TRANSITIONS = {
    "pending": {"pending", "paid", "cancelled", "expired"},
    "paid": {"paid"},
    "cancelled": {"cancelled"},
    "expired": {"expired"},
}


def _payment_to_dict(payment: Payment) -> dict:
    parsed_provider_payload = _deserialize_provider_payload(payment.provider_payload)
    return {
        "id": payment.id,
        "order_id": payment.order_id,
        "method": payment.method,
        "status": payment.status,
        "amount": int(payment.amount),
        "change_amount": int(payment.change_amount) if payment.change_amount is not None else None,
        "currency": payment.currency,
        "idempotency_key": payment.idempotency_key,
        "external_ref": payment.external_ref,
        "preference_id": payment.preference_id,
        "public_status_token": payment.public_status_token,
        "provider_status": payment.provider_status,
        "provider_payload": payment.provider_payload,
        "provider_payload_data": parsed_provider_payload,
        "expires_at": payment.expires_at,
        "paid_at": payment.paid_at,
        "created_at": payment.created_at,
        "updated_at": payment.updated_at,
    }


def _serialize_provider_payload(payload: dict | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def _deserialize_provider_payload(payload: str | None) -> dict | None:
    if payload is None:
        return None
    try:
        parsed = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _normalize_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def _build_order_paid_event_payload(*, order: Order, payment: Payment) -> dict:
    items_payload: list[dict] = []
    for item in sorted(order.items, key=lambda row: row.id):
        product_name = None
        if getattr(item, "product", None) is not None:
            product_name = getattr(item.product, "name", None)
        variant = getattr(item, "variant", None)
        variant_label = "-/-"
        if variant is not None:
            variant_label = f"{variant.size or '-'}/{variant.color or '-'}"
        items_payload.append(
            {
                "product_name": product_name,
                "variant_label": variant_label,
                "quantity": int(item.quantity or 0),
                "line_total": int(item.line_total or 0),
            }
        )

    return {
        "order_id": int(order.id),
        "user_id": int(order.user_id),
        "payment_id": int(payment.id),
        "payment_method": str(payment.method),
        "order_status": str(order.status),
        "total_amount": int(order.total_amount or 0),
        "currency": str(order.currency or payment.currency or "ARS").strip().upper(),
        "items": items_payload,
    }


def _apply_order_paid_transition(
    *,
    order: Order,
    payment: Payment,
    now: datetime,
    db: Session,
) -> None:
    """Single definition of what "the order got paid" means, shared by every payment method.

    Only valid from `submitted`: callers must have ruled out cancelled/already-paid orders
    (the provider path also decides on late-payment incidents before getting here).
    The flush is intentional -- manual confirmation can be creating the Payment row in the
    same call, so its id only exists after flushing and the event payload needs it.
    """
    consume_reservations_for_paid_order(order_id=order.id, db=db)
    order.status = "paid"
    if order.paid_at is None:
        order.paid_at = now
    db.flush()
    publish_domain_event(
        event_type="order_paid",
        payload=_build_order_paid_event_payload(order=order, payment=payment),
        db=db,
    )


def _assert_valid_payment_transition(current_status: str, next_status: str) -> None:
    allowed = ALLOWED_PAYMENT_TRANSITIONS.get(current_status, {current_status})
    if next_status not in allowed:
        raise ValueError("invalid payment status transition")


def _find_active_pending_payment(
    session: Session,
    *,
    order_id: int,
    method: str,
    now: datetime,
) -> Payment | None:
    return (
        session.query(Payment)
        .filter(
            Payment.order_id == order_id,
            Payment.method == method,
            Payment.status == "pending",
            or_(Payment.expires_at.is_(None), Payment.expires_at > now),
        )
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .first()
    )


def _validate_active_pending_compatibility(
    active_payment: Payment,
    *,
    requested_amount: int,
    requested_currency: str,
) -> None:
    active_amount = int(active_payment.amount)
    if active_amount != int(requested_amount):
        raise ValueError(
            "there is already an active pending payment with a different amount"
        )
    if active_payment.currency != requested_currency:
        raise ValueError(
            "there is already an active pending payment with a different currency"
        )


def _resolve_payment_by_idempotency_key(
    db: Session,
    key: str,
    *,
    expected_order_id: int,
    expected_method: str,
    expected_user_id: int | None,
) -> Payment | None:
    """Replay lookup for an idempotency key, validating it belongs to the same request.

    `expected_user_id=None` skips the ownership check for the flows that identify the
    caller by capability token instead of by session (guest retry by public_status_token).
    """
    payment = (
        db.query(Payment)
        .options(joinedload(Payment.order))
        .filter(Payment.idempotency_key == key)
        .first()
    )
    if payment is None:
        return None
    if payment.order_id != expected_order_id:
        raise ValueError("idempotency key already used for a different order")
    if payment.method != expected_method:
        raise ValueError("idempotency key already used for a different payment method")
    if expected_user_id is not None and int(payment.order.user_id) != int(expected_user_id):
        raise LookupError("order not found")
    return payment


def _build_bank_transfer_payload(
    order_id: int,
    payment_id: int,
    amount: int,
    currency: str,
) -> dict:
    return {
        "instructions": {
            "alias": "patitas.bigotes",
            "bank_name": "Banco Demo",
            "reference": f"ORDER-{order_id}-PAY-{payment_id}",
            "amount": amount,
            "currency": currency,
        }
    }


def _mark_payment_checkout_setup_failed(
    payment: Payment,
    *,
    error_detail: str,
    now: datetime | None = None,
) -> None:
    safe_now = now or datetime.now(UTC)
    payload = _deserialize_provider_payload(payment.provider_payload) or {}
    payload["checkout_setup_error"] = {
        "detail": error_detail,
        "failed_at": safe_now.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    payment.provider_status = PAYMENT_PROVIDER_SETUP_FAILED
    payment.provider_payload = _serialize_provider_payload(payload)


def initialize_mercadopago_checkout_for_payment(
    *,
    payment_id: int,
    db: Session,
) -> dict:
    payment = (
        db.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .options(joinedload(Payment.order))
        .filter(Payment.id == int(payment_id), Payment.method == "mercadopago")
        .with_for_update()
        .first()
    )
    if payment is None:
        raise LookupError("payment not found")
    if str(payment.status) != "pending":
        raise ValueError("payment checkout can only be initialized for pending payments")
    if payment.preference_id is not None:
        return _payment_to_dict(payment)

    order = payment.order
    if order is None:
        raise LookupError("order not found")
    payment_currency = str(payment.currency or "ARS").strip().upper()
    expires_at = payment.expires_at
    if expires_at is None:
        raise ValueError("payment expires_at is required")

    external_ref, provider_payload = _build_mercadopago_payload(
        order_id=int(order.id),
        payment_id=int(payment.id),
        amount=int(payment.amount),
        currency=payment_currency,
        expires_at=expires_at,
        payment_idempotency_key=str(payment.idempotency_key),
        public_status_token=str(payment.public_status_token),
    )
    payment.external_ref = external_ref
    payment.preference_id = _get_checkout_preference_id(provider_payload)
    payment.provider_status = "preference_created"
    payment.provider_payload = _serialize_provider_payload(provider_payload)
    db.flush()
    db.refresh(payment)
    return _payment_to_dict(payment)


def mark_payment_checkout_setup_failed(
    *,
    payment_id: int,
    error_detail: str,
    db: Session,
) -> dict:
    payment = (
        db.query(Payment)
        .filter(Payment.id == int(payment_id), Payment.method == "mercadopago")
        .with_for_update()
        .first()
    )
    if payment is None:
        raise LookupError("payment not found")
    _mark_payment_checkout_setup_failed(payment, error_detail=error_detail)
    db.flush()
    db.refresh(payment)
    return _payment_to_dict(payment)


def find_payment_for_mercadopago_event(
    *,
    preference_id: str | None,
    external_ref: str | None,
    db: Session,
) -> dict | None:
    normalized_preference_id = _normalize_optional_str(preference_id)
    normalized_external_ref = _normalize_optional_str(external_ref)
    if normalized_preference_id is None and normalized_external_ref is None:
        raise ValueError("preference_id or external_ref is required")

    if normalized_preference_id is not None:
        payment = (
            db.query(Payment)
            .filter(
                Payment.method == "mercadopago",
                Payment.preference_id == normalized_preference_id,
            )
            .order_by(Payment.created_at.desc(), Payment.id.desc())
            .first()
        )
        if payment is not None:
            return _payment_to_dict(payment)

    if normalized_external_ref is not None:
        payment = (
            db.query(Payment)
            .filter(
                Payment.method == "mercadopago",
                Payment.external_ref == normalized_external_ref,
            )
            .order_by(Payment.created_at.desc(), Payment.id.desc())
            .first()
        )
        if payment is not None:
            return _payment_to_dict(payment)

    return None


def apply_mercadopago_normalized_state(
    *,
    payment_id: int,
    normalized_state: dict,
    notification_payload: dict | None = None,
    db: Session,
) -> dict:
    if not isinstance(normalized_state, dict):
        raise ValueError("normalized_state is required")

    provider_status = _normalize_optional_str(normalized_state.get("provider_status"))
    if provider_status is None:
        raise ValueError("normalized_state.provider_status is required")
    internal_status = _normalize_optional_str(normalized_state.get("internal_status"))
    if internal_status is None:
        raise ValueError("normalized_state.internal_status is required")
    external_reference = _normalize_optional_str(normalized_state.get("external_reference"))
    if external_reference is None:
        raise ValueError("normalized_state.external_reference is required")

    normalized_amount = normalized_state.get("amount")
    if normalized_amount is not None:
        normalized_amount = int(normalized_amount)
    normalized_currency = _normalize_optional_str(normalized_state.get("currency"))
    if normalized_currency is not None:
        normalized_currency = normalized_currency.upper()

    now = datetime.now(UTC)
    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id, Payment.method == "mercadopago")
        .first()
    )
    if payment is None:
        raise LookupError("payment not found")
    order = payment.order
    if order is None:
        raise LookupError("order not found")
    expire_active_reservations_for_order(
        order_id=int(order.id),
        now=now,
        db=db,
    )

    payment_external_ref = _normalize_optional_str(payment.external_ref)
    if payment_external_ref != external_reference:
        raise ValueError("external_reference does not match payment")

    if normalized_amount is not None and int(payment.amount) != normalized_amount:
        raise ValueError("payment amount mismatch")
    if normalized_currency is not None and payment.currency.strip().upper() != normalized_currency:
        raise ValueError("payment currency mismatch")

    allow_paid_revival = internal_status == "paid" and str(payment.status) in {"cancelled", "expired"}
    if not allow_paid_revival:
        _assert_valid_payment_transition(payment.status, internal_status)
    payment.provider_status = provider_status

    existing_payload = _deserialize_provider_payload(payment.provider_payload) or {}
    merged_payload = dict(existing_payload)
    if notification_payload is not None:
        merged_payload["last_event"] = notification_payload
    merged_payload["payment_lookup"] = normalized_state.get("raw")
    merged_payload["reconciliation"] = {
        "provider_payment_id": normalized_state.get("provider_payment_id"),
        "external_reference": external_reference,
        "provider_status": provider_status,
        "provider_status_detail": normalized_state.get("provider_status_detail"),
        "internal_status": internal_status,
        "amount_consistent": normalized_amount is None or int(payment.amount) == normalized_amount,
        "currency_consistent": normalized_currency is None
        or payment.currency.strip().upper() == normalized_currency,
        "date_last_updated": normalized_state.get("date_last_updated"),
    }
    payment.provider_payload = _serialize_provider_payload(merged_payload)

    if payment.status != internal_status:
        payment.status = internal_status
        if internal_status == "paid" and payment.paid_at is None:
            payment.paid_at = now

    if internal_status == "paid":
        duplicate_paid_payment = (
            db.query(Payment.id)
            .filter(
                Payment.order_id == int(order.id),
                Payment.status == "paid",
                Payment.id != int(payment.id),
            )
            .first()
            is not None
        )

        if order.status == "cancelled":
            create_late_paid_incident_if_needed(
                order_id=int(order.id),
                payment_id=int(payment.id),
                reason="mercadopago approved after order cancellation",
                db=db,
            )
        elif order.status == "paid":
            if duplicate_paid_payment:
                create_late_paid_incident_if_needed(
                    order_id=int(order.id),
                    payment_id=int(payment.id),
                    reason="mercadopago approved but order already had another paid payment",
                    db=db,
                )
        elif order.status != "submitted":
            raise ValueError("order can only be paid from submitted status")

        if order.status == "submitted":
            _apply_order_paid_transition(order=order, payment=payment, now=now, db=db)
        elif order.status == "paid":
            if order.paid_at is None:
                order.paid_at = now
    elif internal_status == "cancelled":
        # A provider-level cancellation should only close this payment attempt.
        # The order stays in its current state so the customer can retry payment.
        pass

    db.flush()
    db.refresh(payment)
    return _payment_to_dict(payment)


def create_payment_for_order(
    order_id: int,
    method: str,
    db: Session,
    *,
    user_id: int | None = None,
    idempotency_key: str,
    currency: str | None = None,
    expires_in_minutes: int = 60,
    initialize_provider: bool = True,
) -> dict:
    expire_active_reservations_for_order(
        order_id=order_id,
        now=datetime.now(UTC),
        db=db,
    )

    if method not in ALLOWED_PAYMENT_METHODS:
        raise ValueError("invalid payment method")
    if expires_in_minutes <= 0:
        raise ValueError("expires_in_minutes must be greater than 0")
    normalized_key = idempotency_key.strip()
    if not normalized_key:
        raise ValueError("idempotency_key is required")
    if currency is not None and str(currency).strip().upper() != "ARS":
        raise ValueError("only ARS currency is supported")

    existing_payment = _resolve_payment_by_idempotency_key(
        db,
        normalized_key,
        expected_order_id=order_id,
        expected_method=method,
        expected_user_id=user_id,
    )
    if existing_payment is not None:
        return _payment_to_dict(existing_payment)

    order = (
        db.query(Order)
        .options(selectinload(Order.items))
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )
    if order is None:
        raise LookupError("order not found")
    if user_id is not None and int(order.user_id) != int(user_id):
        raise LookupError("order not found")
    if order.status == "cancelled":
        raise ValueError("cannot create payment for a cancelled order")
    if order.status != "submitted":
        raise ValueError("payment can only be created for submitted orders")
    if not order.items:
        raise ValueError("cannot create payment for an empty order")
    if not list_active_reservations_for_order(order_id=order.id, db=db):
        raise ValueError("order has no active stock reservations")

    amount = int(order.total_amount or 0)
    if amount <= 0:
        raise ValueError("order total must be greater than 0")

    now = datetime.now(UTC)
    active_pending_payment = _find_active_pending_payment(
        db,
        order_id=order.id,
        method=method,
        now=now,
    )
    order_currency = str(order.currency or "ARS").strip().upper()
    if order_currency != "ARS":
        raise ValueError("only ARS currency is supported")
    payment_currency = "ARS"
    if active_pending_payment is not None:
        _validate_active_pending_compatibility(
            active_pending_payment,
            requested_amount=amount,
            requested_currency=payment_currency,
        )
        if (
            method == "mercadopago"
            and initialize_provider
            and active_pending_payment.preference_id is None
            and active_pending_payment.provider_status != PAYMENT_PROVIDER_SETUP_FAILED
        ):
            return initialize_mercadopago_checkout_for_payment(
                payment_id=int(active_pending_payment.id),
                db=db,
            )
        return _payment_to_dict(active_pending_payment)

    expires_at = None if method == "cash" else now + timedelta(minutes=expires_in_minutes)
    payment = Payment(
        order_id=order.id,
        method=method,
        status="pending",
        amount=amount,
        currency=payment_currency,
        idempotency_key=normalized_key,
        external_ref=None,
        public_status_token=generate_public_status_token(),
        provider_status=None,
        provider_payload=None,
        expires_at=expires_at,
        paid_at=None,
    )

    try:
        with db.begin_nested():
            db.add(payment)
            db.flush()
    except IntegrityError:
        payment_by_key = (
            db.query(Payment)
            .options(joinedload(Payment.order))
            .filter(Payment.idempotency_key == normalized_key)
            .first()
        )
        if payment_by_key is not None:
            if user_id is not None and int(payment_by_key.order.user_id) != int(user_id):
                raise LookupError("order not found")
            return _payment_to_dict(payment_by_key)

        existing_pending = _find_active_pending_payment(
            db,
            order_id=order.id,
            method=method,
            now=now,
        )
        if existing_pending is not None:
            _validate_active_pending_compatibility(
                existing_pending,
                requested_amount=amount,
                requested_currency=payment_currency,
            )
            return _payment_to_dict(existing_pending)
        raise

    if method == "bank_transfer":
        provider_payload = _build_bank_transfer_payload(
            order_id=order.id,
            payment_id=payment.id,
            amount=amount,
            currency=payment_currency,
        )
        payment.provider_payload = _serialize_provider_payload(provider_payload)
    elif method == "mercadopago" and initialize_provider:
        existing_provider_payload = _deserialize_provider_payload(
            payment.provider_payload
        )
        if _has_checkout_preference(existing_provider_payload):
            checkout_external_ref = _get_checkout_external_ref(
                existing_provider_payload
            )
            checkout_preference_id = _get_checkout_preference_id(existing_provider_payload)
            if checkout_external_ref is not None and payment.external_ref is None:
                payment.external_ref = checkout_external_ref
            if checkout_preference_id is not None and payment.preference_id is None:
                payment.preference_id = checkout_preference_id
            payment.provider_status = payment.provider_status or "preference_created"
        else:
            external_ref, provider_payload = _build_mercadopago_payload(
                order_id=order.id,
                payment_id=payment.id,
                amount=amount,
                currency=payment_currency,
                expires_at=expires_at,
                payment_idempotency_key=normalized_key,
                public_status_token=payment.public_status_token,
            )
            payment.external_ref = external_ref
            payment.preference_id = _get_checkout_preference_id(provider_payload)
            payment.provider_status = "preference_created"
            payment.provider_payload = _serialize_provider_payload(provider_payload)

    db.flush()
    db.refresh(payment)
    return _payment_to_dict(payment)


def create_retry_payment_for_order(
    order_id: int,
    method: str,
    db: Session,
    *,
    user_id: int,
    idempotency_key: str,
    currency: str | None = None,
    expires_in_minutes: int = 60,
    initialize_provider: bool = True,
) -> dict:
    normalized_key = idempotency_key.strip()
    if not normalized_key:
        raise ValueError("idempotency_key is required")
    existing_payment = _resolve_payment_by_idempotency_key(
        db,
        normalized_key,
        expected_order_id=order_id,
        expected_method=method,
        expected_user_id=user_id,
    )
    if existing_payment is not None:
        return _payment_to_dict(existing_payment)

    expire_active_reservations_for_order(
        order_id=order_id,
        now=datetime.now(UTC),
        db=db,
    )

    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.user_id == user_id)
        .with_for_update()
        .first()
    )
    if order is None:
        raise LookupError("order not found")
    if str(order.status) == "cancelled":
        has_expired_reservation = (
            db.query(1)
            .filter(
                StockReservation.order_id == int(order.id),
                StockReservation.reason == "reservation_expired",
            )
            .first()
            is not None
        )
        if has_expired_reservation:
            raise PaymentRetryConflictError(RETRY_NOT_ALLOWED_ORDER_CANCELLED_STOCK_EXPIRED)
        raise PaymentRetryConflictError(RETRY_NOT_ALLOWED_ORDER_CANCELLED)
    if str(order.status) == "paid":
        raise PaymentRetryConflictError(RETRY_NOT_ALLOWED_ORDER_ALREADY_PAID)
    if str(order.status) != "submitted":
        raise PaymentRetryConflictError(RETRY_NOT_ALLOWED_ORDER_NOT_SUBMITTED)
    if not list_active_reservations_for_order(order_id=int(order.id), db=db):
        raise PaymentRetryConflictError(RETRY_NOT_ALLOWED_STOCK_RESERVATION_EXPIRED)

    latest_attempt = (
        db.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .filter(
            Payment.order_id == order_id,
            Payment.method == method,
            Order.user_id == user_id,
        )
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .first()
    )
    if latest_attempt is None:
        raise ValueError("no previous payment attempt found for this method")
    latest_status = str(latest_attempt.status)
    latest_provider_status = str(latest_attempt.provider_status or "").strip().lower() or None
    is_setup_failed_pending = (
        latest_status == "pending"
        and latest_provider_status == PAYMENT_PROVIDER_SETUP_FAILED
    )
    if latest_status not in RETRYABLE_PAYMENT_STATUSES and not is_setup_failed_pending:
        raise PaymentRetryConflictError(RETRY_NOT_ALLOWED_PAYMENT_STATE_CHANGED)
    if is_setup_failed_pending:
        latest_attempt.status = "cancelled"
        db.flush()

    return create_payment_for_order(
        order_id=order_id,
        method=method,
        db=db,
        user_id=user_id,
        idempotency_key=normalized_key,
        currency=currency,
        expires_in_minutes=expires_in_minutes,
        initialize_provider=initialize_provider,
    )


def create_retry_payment_for_payment_token(
    *,
    public_status_token: str | None,
    db: Session,
    idempotency_key: str,
    expires_in_minutes: int = 60,
    initialize_provider: bool = True,
) -> dict:
    normalized_key = idempotency_key.strip()
    if not normalized_key:
        raise ValueError("idempotency_key is required")
    normalized_public_status_token = _normalize_optional_str(public_status_token)
    if normalized_public_status_token is None:
        raise ValueError("public_status_token is required")
    if len(normalized_public_status_token) > 255:
        raise ValueError("public_status_token is too long")

    token_payment = (
        db.query(Payment)
        .filter(
            Payment.method == "mercadopago",
            Payment.public_status_token == normalized_public_status_token,
        )
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .first()
    )
    if token_payment is None:
        raise LookupError("payment not found")
    existing_payment = _resolve_payment_by_idempotency_key(
        db,
        normalized_key,
        expected_order_id=int(token_payment.order_id),
        expected_method="mercadopago",
        # The public status token is the capability here; there is no session user to match.
        expected_user_id=None,
    )
    if existing_payment is not None:
        return _payment_to_dict(existing_payment)

    order_id = int(token_payment.order_id)
    expire_active_reservations_for_order(
        order_id=order_id,
        now=datetime.now(UTC),
        db=db,
    )

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )
    if order is None:
        raise LookupError("order not found")
    if str(order.status) == "cancelled":
        has_expired_reservation = (
            db.query(1)
            .filter(
                StockReservation.order_id == int(order.id),
                StockReservation.reason == "reservation_expired",
            )
            .first()
            is not None
        )
        if has_expired_reservation:
            raise PaymentRetryConflictError(RETRY_NOT_ALLOWED_ORDER_CANCELLED_STOCK_EXPIRED)
        raise PaymentRetryConflictError(RETRY_NOT_ALLOWED_ORDER_CANCELLED)
    if str(order.status) == "paid":
        raise PaymentRetryConflictError(RETRY_NOT_ALLOWED_ORDER_ALREADY_PAID)
    if str(order.status) != "submitted":
        raise PaymentRetryConflictError(RETRY_NOT_ALLOWED_ORDER_NOT_SUBMITTED)
    if not list_active_reservations_for_order(order_id=int(order.id), db=db):
        raise PaymentRetryConflictError(RETRY_NOT_ALLOWED_STOCK_RESERVATION_EXPIRED)

    latest_attempt = (
        db.query(Payment)
        .filter(
            Payment.order_id == int(order.id),
            Payment.method == "mercadopago",
        )
        .with_for_update()
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .first()
    )
    if latest_attempt is None:
        raise ValueError("no previous payment attempt found for this method")

    latest_status = str(latest_attempt.status)
    latest_provider_status = str(latest_attempt.provider_status or "").strip().lower() or None
    is_setup_failed_pending = (
        latest_status == "pending"
        and latest_provider_status == PAYMENT_PROVIDER_SETUP_FAILED
    )
    if latest_status not in RETRYABLE_PAYMENT_STATUSES and not is_setup_failed_pending:
        raise PaymentRetryConflictError(RETRY_NOT_ALLOWED_PAYMENT_STATE_CHANGED)
    if is_setup_failed_pending:
        latest_attempt.status = "cancelled"
        db.flush()

    return create_payment_for_order(
        order_id=int(order.id),
        method="mercadopago",
        db=db,
        user_id=None,
        idempotency_key=normalized_key,
        currency="ARS",
        expires_in_minutes=expires_in_minutes,
        initialize_provider=initialize_provider,
    )


def list_reconcilable_pending_mercadopago_payments(
    *,
    db: Session,
    now: datetime,
    limit: int,
    max_age_hours: int,
    min_age_minutes: int,
) -> list[Payment]:
    safe_limit = max(1, int(limit))
    safe_max_age_hours = max(1, int(max_age_hours))
    safe_min_age_minutes = max(0, int(min_age_minutes))
    oldest_created_at = now - timedelta(hours=safe_max_age_hours)
    newest_created_at = now - timedelta(minutes=safe_min_age_minutes)
    return (
        db.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .filter(
            Payment.method == "mercadopago",
            Payment.status == "pending",
            Payment.external_ref.is_not(None),
            Payment.created_at >= oldest_created_at,
            Payment.created_at <= newest_created_at,
            Order.status.in_(["submitted", "paid"]),
        )
        .order_by(Payment.created_at.asc(), Payment.id.asc())
        .limit(safe_limit)
        .all()
    )


def _build_manual_payment_idempotency_key(order_id: int, payment_ref: str, method: str) -> str:
    digest = hashlib.sha256(f"{method}:{payment_ref}".encode("utf-8")).hexdigest()[:16]
    return f"manual-order-{order_id}-{method}-{digest}"


def confirm_manual_payment_for_order(
    *,
    order_id: int,
    user_id: int,
    payment_ref: str,
    paid_amount: int,
    method: str = "bank_transfer",
    change_amount: int | None = None,
    allow_create_if_missing: bool = False,
    db: Session,
) -> dict:
    expire_active_reservations_for_order(
        order_id=order_id,
        now=datetime.now(UTC),
        db=db,
    )

    normalized_ref = str(payment_ref or "").strip()
    normalized_method = str(method or "").strip().lower()
    if normalized_method not in {"bank_transfer", "cash"}:
        raise ValueError("manual payment method must be bank_transfer or cash")
    if normalized_method == "bank_transfer" and not normalized_ref:
        raise ValueError("payment_ref is required for bank_transfer")
    if normalized_method == "cash" and not normalized_ref:
        normalized_ref = f"cash-order-{int(order_id)}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    if int(paid_amount) <= 0:
        raise ValueError("paid_amount must be greater than 0")
    normalized_change_amount = (
        int(change_amount) if change_amount is not None else None
    )
    if normalized_method == "cash":
        if normalized_change_amount is None:
            raise ValueError("change_amount is required for cash payments")
        if normalized_change_amount < 0:
            raise ValueError("change_amount cannot be negative")
    else:
        if normalized_change_amount is not None:
            raise ValueError("change_amount is only allowed for cash payments")

    order = (
        db.query(Order)
        .options(
            selectinload(Order.items),
            selectinload(Order.payments),
        )
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )
    if order is None or int(order.user_id) != int(user_id):
        raise LookupError("order not found")

    if order.status == "cancelled":
        raise ValueError("cannot pay a cancelled order")
    if order.status not in {"submitted", "paid"}:
        raise ValueError("order can only be paid from submitted status")
    if not order.items:
        raise ValueError("cannot pay an empty order")

    expected_total = int(order.total_amount or 0)
    received_total = int(paid_amount)
    if normalized_method == "cash":
        if received_total - int(normalized_change_amount or 0) != expected_total:
            raise ValueError("amount_paid minus change_amount must match order total")
    else:
        if expected_total != received_total:
            raise ValueError("paid_amount does not match order total")

    existing_paid_by_ref = (
        db.query(Payment)
        .filter(
            Payment.order_id == order.id,
            Payment.status == "paid",
            Payment.external_ref == normalized_ref,
        )
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .first()
    )
    pending_payment = (
        db.query(Payment)
        .filter(
            Payment.order_id == order.id,
            Payment.status == "pending",
            Payment.method == normalized_method,
        )
        .with_for_update()
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .first()
    )
    if order.status == "paid":
        if (
            existing_paid_by_ref is not None
            and int(existing_paid_by_ref.amount) == received_total
        ):
            return _payment_to_dict(existing_paid_by_ref)
        raise ValueError("order already paid with a different payment_ref")

    if pending_payment is None and not allow_create_if_missing:
        raise ValueError("pending payment not found for order and method")

    now = datetime.now(UTC)
    payment = pending_payment or existing_paid_by_ref
    if payment is None:
        payment = Payment(
            order_id=order.id,
            method=normalized_method,
            status="paid",
            amount=received_total,
            change_amount=normalized_change_amount,
            currency=order.currency or "ARS",
            idempotency_key=_build_manual_payment_idempotency_key(order.id, normalized_ref, normalized_method),
            external_ref=normalized_ref,
            provider_status="manual_confirmed",
            provider_payload=None,
            expires_at=None,
            paid_at=now,
        )
        db.add(payment)
    else:
        payment.method = normalized_method
        payment.status = "paid"
        payment.amount = received_total
        payment.change_amount = normalized_change_amount
        payment.currency = order.currency or payment.currency or "ARS"
        payment.external_ref = normalized_ref
        payment.provider_status = "manual_confirmed"
        payment.expires_at = None
        payment.paid_at = now

    payment.provider_payload = _serialize_provider_payload(
        {
            "manual_confirmation": {
                "payment_ref": normalized_ref,
                "method": normalized_method,
                "amount_paid": received_total,
                "change_amount": normalized_change_amount,
                "confirmed_at": now.isoformat() + "Z",
            }
        }
    )

    _apply_order_paid_transition(order=order, payment=payment, now=now, db=db)
    db.refresh(payment)
    return _payment_to_dict(payment)


def list_payments_for_order(
    order_id: int,
    user_id: int,
    db: Session,
) -> list[dict]:
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.user_id == user_id)
        .first()
    )
    if order is None:
        raise LookupError("order not found")

    payments = (
        db.query(Payment)
        .filter(Payment.order_id == order_id)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .all()
    )
    return [_payment_to_dict(payment) for payment in payments]


def list_payments_for_orders(order_ids: list[int], db: Session) -> dict[int, list[dict]]:
    unique_ids = list(dict.fromkeys(order_ids))
    payments_by_order_id: dict[int, list[dict]] = {order_id: [] for order_id in unique_ids}
    if not unique_ids:
        return payments_by_order_id

    payments = (
        db.query(Payment)
        .filter(Payment.order_id.in_(unique_ids))
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .all()
    )
    for payment in payments:
        payments_by_order_id[payment.order_id].append(_payment_to_dict(payment))
    return payments_by_order_id


def get_payment_for_user(
    payment_id: int,
    user_id: int,
    db: Session,
) -> dict:
    payment = (
        db.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .filter(Payment.id == payment_id, Order.user_id == user_id)
        .first()
    )
    if payment is None:
        raise LookupError("payment not found")

    return _payment_to_dict(payment)


def get_payment_public_status(
    *,
    public_status_token: str | None = None,
    db: Session,
) -> dict:
    normalized_public_status_token = _normalize_optional_str(public_status_token)
    if normalized_public_status_token is None:
        raise ValueError("public_status_token is required")
    if len(normalized_public_status_token) > 255:
        raise ValueError("public_status_token is too long")

    payment = (
        db.query(Payment)
        .options(joinedload(Payment.order))
        .filter(
            Payment.method == "mercadopago",
            Payment.public_status_token == normalized_public_status_token,
        )
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .first()
    )
    if payment is None:
        raise LookupError("payment not found")

    order = payment.order
    return {
        "order_status": str(order.status) if order is not None else None,
        "status": str(payment.status),
        "updated_at": payment.updated_at,
        "paid_at": payment.paid_at,
    }
