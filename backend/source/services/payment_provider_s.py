"""Módulo de proveedor de pago: todo lo que habla con MercadoPago.

Inicialización de checkout, marcado de fallo de setup, resolución de pago
desde un evento del proveedor, aplicación de estado normalizado y listado de
pagos reconciliables. Al concentrar acá la integración, evaluar el impacto de
un cambio del proveedor es leer un módulo en vez de rastrear seis funciones
dispersas.

Depende del kernel (`payment_core_s`) pero no de `payment_s`: la dependencia
entre ambos es de una sola vía (payment_s -> payment_provider_s).
"""
from __future__ import annotations

from datetime import datetime, timedelta, UTC

from sqlalchemy.orm import Session, joinedload

from source.db.models import Order, Payment
from source.services.mercadopago_normalization_s import (
    _build_mercadopago_payload,
    _get_checkout_preference_id,
)
from source.services.payment_core_s import (
    apply_order_paid_transition,
    assert_valid_payment_transition,
    deserialize_provider_payload,
    normalize_optional_str,
    payment_to_dict,
    serialize_provider_payload,
)
from source.services.refund_s import create_late_paid_incident_if_needed
from source.services.stock_reservations_s import expire_active_reservations_for_order

PAYMENT_PROVIDER_SETUP_FAILED = "setup_failed"


def _mark_payment_checkout_setup_failed(
    payment: Payment,
    *,
    error_detail: str,
    now: datetime | None = None,
) -> None:
    safe_now = now or datetime.now(UTC)
    payload = deserialize_provider_payload(payment.provider_payload) or {}
    payload["checkout_setup_error"] = {
        "detail": error_detail,
        "failed_at": safe_now.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    payment.provider_status = PAYMENT_PROVIDER_SETUP_FAILED
    payment.provider_payload = serialize_provider_payload(payload)


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
        return payment_to_dict(payment)

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
    payment.provider_payload = serialize_provider_payload(provider_payload)
    db.flush()
    db.refresh(payment)
    return payment_to_dict(payment)


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
    return payment_to_dict(payment)


def find_payment_for_mercadopago_event(
    *,
    preference_id: str | None,
    external_ref: str | None,
    db: Session,
) -> dict | None:
    normalized_preference_id = normalize_optional_str(preference_id)
    normalized_external_ref = normalize_optional_str(external_ref)
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
            return payment_to_dict(payment)

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
            return payment_to_dict(payment)

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

    provider_status = normalize_optional_str(normalized_state.get("provider_status"))
    if provider_status is None:
        raise ValueError("normalized_state.provider_status is required")
    internal_status = normalize_optional_str(normalized_state.get("internal_status"))
    if internal_status is None:
        raise ValueError("normalized_state.internal_status is required")
    external_reference = normalize_optional_str(normalized_state.get("external_reference"))
    if external_reference is None:
        raise ValueError("normalized_state.external_reference is required")

    normalized_amount = normalized_state.get("amount")
    if normalized_amount is not None:
        normalized_amount = int(normalized_amount)
    normalized_currency = normalize_optional_str(normalized_state.get("currency"))
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

    payment_external_ref = normalize_optional_str(payment.external_ref)
    if payment_external_ref != external_reference:
        raise ValueError("external_reference does not match payment")

    if normalized_amount is not None and int(payment.amount) != normalized_amount:
        raise ValueError("payment amount mismatch")
    if normalized_currency is not None and payment.currency.strip().upper() != normalized_currency:
        raise ValueError("payment currency mismatch")

    allow_paid_revival = internal_status == "paid" and str(payment.status) in {"cancelled", "expired"}
    if not allow_paid_revival:
        assert_valid_payment_transition(payment.status, internal_status)
    payment.provider_status = provider_status

    existing_payload = deserialize_provider_payload(payment.provider_payload) or {}
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
    payment.provider_payload = serialize_provider_payload(merged_payload)

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
            apply_order_paid_transition(order=order, payment=payment, now=now, db=db)
        elif order.status == "paid":
            if order.paid_at is None:
                order.paid_at = now
    elif internal_status == "cancelled":
        # A provider-level cancellation should only close this payment attempt.
        # The order stays in its current state so the customer can retry payment.
        pass

    db.flush()
    db.refresh(payment)
    return payment_to_dict(payment)


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
