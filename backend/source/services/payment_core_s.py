"""Kernel de pago: el conjunto mínimo compartido por todos los caminos de pago.

Contiene el **punto de entrada del dinero** — `apply_order_paid_transition`, la
única definición de qué significa "la orden se pagó", invocada tanto por el
webhook del proveedor como por la confirmación manual de un administrador.

A diferencia de productos y órdenes, pagos no tenía ningún bloque
autocontenido: el serializador de pago se usa en 18 lugares y el de payload en
6. Existía un núcleo compartido por todo; este módulo lo hace explícito y le da
API pública, en vez de que otros servicios importen privados con guion bajo.

Señal de alarma: si este archivo supera las ~350 líneas, el corte falló y hay
que revisar el ADR 0001.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from source.db.config import get_mercadopago_enabled
from source.db.models import Order, Payment, variant_label
from source.exceptions import PaymentMethodDisabledError
from source.services.domain_events_s import publish_domain_event
from source.services.stock_reservations_s import consume_reservations_for_paid_order

PAYMENT_METHOD_DISABLED_MERCADOPAGO = "payment method is disabled: mercadopago"

ALLOWED_PAYMENT_TRANSITIONS = {
    "pending": {"pending", "paid", "cancelled", "expired"},
    "paid": {"paid"},
    "cancelled": {"cancelled"},
    "expired": {"expired"},
}


def payment_to_dict(payment: Payment) -> dict:
    parsed_provider_payload = deserialize_provider_payload(payment.provider_payload)
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


def serialize_provider_payload(payload: dict | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def deserialize_provider_payload(payload: str | None) -> dict | None:
    if payload is None:
        return None
    try:
        parsed = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def normalize_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def build_order_line_items(order: Order) -> list[dict]:
    """Lo que compro, en la forma que consumen los emails de la orden.

    Los dos mails que listan el pedido -- el de transferencia y el de pago
    confirmado -- salen de aca, para que no puedan describir la misma orden de
    dos maneras distintas.
    """
    items_payload: list[dict] = []
    for item in sorted(order.items, key=lambda row: row.id):
        product_name = None
        if getattr(item, "product", None) is not None:
            product_name = getattr(item.product, "name", None)
        items_payload.append(
            {
                "product_name": product_name,
                "variant_label": variant_label(getattr(item, "variant", None)),
                "quantity": int(item.quantity or 0),
                "line_total": int(item.line_total or 0),
            }
        )
    return items_payload


def build_order_paid_event_payload(*, order: Order, payment: Payment) -> dict:
    items_payload = build_order_line_items(order)

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


def apply_order_paid_transition(
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
        payload=build_order_paid_event_payload(order=order, payment=payment),
        db=db,
    )


def assert_payment_method_enabled(method: str) -> None:
    """Reject payment methods that configuration has switched off.

    Lives in the kernel so every path that can start a payment -- checkout,
    retry and provider checkout initialization -- goes through the same check.
    Hiding the option in the frontend is not a lock: the server has to refuse
    it too, before anything is persisted or sent to the provider.
    """
    if method == "mercadopago" and not get_mercadopago_enabled():
        raise PaymentMethodDisabledError(PAYMENT_METHOD_DISABLED_MERCADOPAGO)


def assert_valid_payment_transition(current_status: str, next_status: str) -> None:
    allowed = ALLOWED_PAYMENT_TRANSITIONS.get(current_status, {current_status})
    if next_status not in allowed:
        raise ValueError("invalid payment status transition")


def find_active_pending_payment(
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


def validate_active_pending_compatibility(
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


def resolve_payment_by_idempotency_key(
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
