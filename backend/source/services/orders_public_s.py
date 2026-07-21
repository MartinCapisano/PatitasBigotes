"""Snapshot público de orden: la proyección anónima accesible por token de pago.

Toda la superficie anónima de órdenes vive acá, aislada de los caminos
autenticados, para que auditarla sea leer un archivo y no recorrer `orders_s`.

Órdenes se parte por **público anónimo vs autenticado**, no por usuario vs
admin: las dos vías de creación de venta llaman al mismo camino interno, así
que separarlas habría producido un módulo importando media docena de privados
del otro — un archivo partido al medio, no una frontera.

El import hacia `orders_s` es de una sola vía (público -> core, nunca al revés).
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

from sqlalchemy.orm import Session, joinedload

from source.db.models import Order, OrderItem, Payment, StockReservation
from source.services.mercadopago_normalization_s import MERCADOPAGO_ALLOWED_CHECKOUT_HOSTS
from source.services.orders_s import _utc_now, _variant_label
from source.services.stock_reservations_s import expire_active_reservations_for_order


def _deserialize_public_checkout_payload(payload: str | None) -> dict | None:
    if payload is None:
        return None
    try:
        parsed = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _extract_public_checkout_url(payment: Payment) -> str | None:
    if str(payment.method) != "mercadopago" or str(payment.status) != "pending":
        return None
    payload = _deserialize_public_checkout_payload(payment.provider_payload)
    if not isinstance(payload, dict):
        return None
    checkout = payload.get("checkout")
    if not isinstance(checkout, dict):
        return None
    raw_checkout_url = checkout.get("checkout_url")
    if raw_checkout_url is None:
        return None
    checkout_url = str(raw_checkout_url).strip()
    if not checkout_url:
        return None
    parsed = urlparse(checkout_url)
    hostname = str(parsed.hostname or "").strip().lower().rstrip(".")
    if parsed.scheme.lower() != "https":
        return None
    if hostname not in MERCADOPAGO_ALLOWED_CHECKOUT_HOSTS:
        return None
    return checkout_url


def get_public_order_snapshot_by_payment_token(
    *,
    public_status_token: str | None,
    db: Session,
) -> dict:
    normalized_public_status_token = str(public_status_token or "").strip()
    if not normalized_public_status_token:
        raise ValueError("public_status_token is required")
    if len(normalized_public_status_token) > 255:
        raise ValueError("public_status_token is too long")

    token_payment = (
        db.query(Payment)
        .options(
            joinedload(Payment.order)
            .joinedload(Order.items)
            .joinedload(OrderItem.product),
            joinedload(Payment.order)
            .joinedload(Order.items)
            .joinedload(OrderItem.variant),
        )
        .filter(
            Payment.method == "mercadopago",
            Payment.public_status_token == normalized_public_status_token,
        )
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .first()
    )
    if token_payment is None:
        raise LookupError("payment not found")

    order = token_payment.order
    if order is None:
        raise LookupError("order not found")

    expire_active_reservations_for_order(order_id=int(order.id), now=_utc_now(), db=db)
    db.refresh(order)

    mercadopago_payments = (
        db.query(Payment)
        .filter(
            Payment.order_id == int(order.id),
            Payment.method == "mercadopago",
        )
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .all()
    )
    if not mercadopago_payments:
        raise LookupError("payment not found")

    relevant_payment = next(
        (payment for payment in mercadopago_payments if str(payment.status) == "pending"),
        None,
    )
    if relevant_payment is None:
        relevant_payment = next(
            (payment for payment in mercadopago_payments if int(payment.id) == int(token_payment.id)),
            None,
        )
    if relevant_payment is None:
        relevant_payment = mercadopago_payments[0]

    checkout_url = _extract_public_checkout_url(relevant_payment)
    order_status = str(order.status)
    token_payment_status = str(token_payment.status)
    relevant_payment_status = str(relevant_payment.status)
    has_pending_continuable_payment = any(
        str(payment.status) == "pending" and _extract_public_checkout_url(payment) is not None
        for payment in mercadopago_payments
    )
    is_order_open = order_status == "submitted"
    can_continue_payment = (
        is_order_open
        and relevant_payment_status == "pending"
        and str(relevant_payment.method) == "mercadopago"
        and checkout_url is not None
    )
    can_retry_payment = (
        token_payment_status in {"cancelled", "expired"}
        and is_order_open
        and not has_pending_continuable_payment
    )
    is_payment_terminal = relevant_payment_status in {"paid", "cancelled", "expired"}
    has_stock_reservation_expired = (
        db.query(1)
        .filter(
            StockReservation.order_id == int(order.id),
            StockReservation.reason == "reservation_expired",
        )
        .first()
        is not None
    )

    blocking_reason = None
    if not can_continue_payment and not can_retry_payment:
        if order_status == "paid":
            blocking_reason = "order_paid"
        elif order_status == "cancelled":
            blocking_reason = (
                "stock_reservation_expired"
                if has_stock_reservation_expired
                else "order_cancelled"
            )
        elif relevant_payment_status == "pending":
            blocking_reason = (
                "checkout_unavailable" if checkout_url is None else "payment_pending"
            )
        else:
            blocking_reason = "payment_not_retryable"

    return {
        "order": {
            "status": order_status,
            "total_amount": int(order.total_amount or 0),
            "currency": str(order.currency or "ARS"),
            "items": [
                {
                    "product_name": item.product.name if item.product is not None else None,
                    "variant_label": _variant_label(item.variant),
                    "quantity": int(item.quantity),
                    "line_total": int(item.line_total or 0),
                }
                for item in sorted(order.items, key=lambda row: row.id)
            ],
        },
        "payment": {
            "method": str(relevant_payment.method),
            "status": relevant_payment_status,
            "amount": int(relevant_payment.amount or 0),
            "currency": str(relevant_payment.currency or "ARS"),
            "checkout_url": checkout_url,
        },
        "flags": {
            "can_continue_payment": bool(can_continue_payment),
            "can_retry_payment": bool(can_retry_payment),
            "is_order_open": bool(is_order_open),
            "is_payment_terminal": bool(is_payment_terminal),
        },
        "blocking_reason": blocking_reason,
    }
