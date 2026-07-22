"""Read-only payment listing queries for the admin panel.

Split out of payment_s.py, which had grown into a god file mixing this with core
payment creation/transition logic, webhook bookkeeping, and MercadoPago normalization.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from source.db.models import Order, Payment, PaymentIncident, StockReservation
from source.services.bank_transfer_s import build_payment_reference
from source.services.payment_core_s import deserialize_provider_payload, payment_to_dict
from source.services.refund_s import PAYMENT_INCIDENT_STATUS_PENDING_REVIEW
from source.services.stock_reservations_s import RESERVATION_ACTIVE
from source.services.users_s import serialize_user_basic


def _open_incident_status_by_payment_ids(*, payment_ids: list[int], db: Session) -> dict[int, str]:
    if not payment_ids:
        return {}
    rows = (
        db.query(PaymentIncident.payment_id, PaymentIncident.status)
        .filter(
            PaymentIncident.payment_id.in_(payment_ids),
            PaymentIncident.status == PAYMENT_INCIDENT_STATUS_PENDING_REVIEW,
        )
        .all()
    )
    result: dict[int, str] = {}
    for payment_id, status in rows:
        result[int(payment_id)] = str(status)
    return result


def _reservation_deadline_by_order_ids(*, order_ids: list[int], db: Session) -> dict[int, object]:
    """When each order's stock reservation lapses.

    The reservation is the clock that actually cancels the order (the payment's
    own `expires_at` governs nothing for a transfer), so this is what tells the
    admin which pending transfers are about to fall off the queue. The earliest
    active reservation wins: the first one to lapse takes the whole order with it.
    """
    if not order_ids:
        return {}
    rows = (
        db.query(StockReservation.order_id, func.min(StockReservation.expires_at))
        .filter(
            StockReservation.order_id.in_(order_ids),
            StockReservation.status == RESERVATION_ACTIVE,
        )
        .group_by(StockReservation.order_id)
        .all()
    )
    return {int(order_id): expires_at for order_id, expires_at in rows}


def list_payments_for_order_admin(
    *,
    order_id: int,
    db: Session,
) -> list[dict]:
    order_exists = db.query(Order.id).filter(Order.id == order_id).first()
    if order_exists is None:
        raise LookupError("order not found")
    payments = (
        db.query(Payment)
        .filter(Payment.order_id == order_id)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .all()
    )
    result = [payment_to_dict(payment) for payment in payments]
    status_by_payment = _open_incident_status_by_payment_ids(
        payment_ids=[int(payment.id) for payment in payments],
        db=db,
    )
    for item in result:
        incident_status = status_by_payment.get(int(item["id"]))
        item["has_open_incident"] = incident_status is not None
        item["incident_status"] = incident_status
    return result


def list_pending_bank_transfer_payments_for_admin(
    *,
    db: Session,
    limit: int = 100,
) -> list[dict]:
    """The admin's queue of transfers waiting to be verified.

    Oldest first: with no webhook, a human is the whole verification, and the
    transfer that has been waiting longest is the one closest to being cancelled
    out from under the customer.

    Each row carries what it takes to cross a bank statement line with an order
    without opening anything else: the reference the customer was told to write,
    who bought, how much exactly, and when the reservation lapses.
    """
    safe_limit = max(1, min(int(limit), 500))
    rows = (
        db.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .options(joinedload(Payment.order).joinedload(Order.user))
        .filter(
            Payment.method == "bank_transfer",
            Payment.status == "pending",
            Order.status == "submitted",
        )
        .order_by(Payment.created_at.asc(), Payment.id.asc())
        .limit(safe_limit)
        .all()
    )
    result: list[dict] = []
    status_by_payment = _open_incident_status_by_payment_ids(
        payment_ids=[int(payment.id) for payment in rows],
        db=db,
    )
    deadline_by_order = _reservation_deadline_by_order_ids(
        order_ids=[int(payment.order_id) for payment in rows],
        db=db,
    )
    for payment in rows:
        item = payment_to_dict(payment)
        order = payment.order
        item["order_status"] = order.status if order is not None else None
        item["user_id"] = int(order.user_id) if order is not None else None
        item["order_total"] = int(order.total_amount or 0) if order is not None else None
        item["customer"] = (
            serialize_user_basic(order.user)
            if order is not None and order.user is not None
            else None
        )
        item["reference"] = _stored_reference(payment)
        item["reservation_expires_at"] = deadline_by_order.get(int(payment.order_id))
        incident_status = status_by_payment.get(int(payment.id))
        item["has_open_incident"] = incident_status is not None
        item["incident_status"] = incident_status
        result.append(item)
    return result


def _stored_reference(payment: Payment) -> str:
    """The reference the customer was actually shown, not a fresh guess.

    It is read back from the payload stored on the payment so the queue repeats
    the exact string that travelled to the checkout screen, the email and the
    WhatsApp message. Rebuilding it is only the fallback for rows created before
    the payload existed.
    """
    stored_payload = deserialize_provider_payload(payment.provider_payload) or {}
    instructions = stored_payload.get("instructions")
    if isinstance(instructions, dict):
        reference = instructions.get("reference")
        if reference:
            return str(reference)
    return build_payment_reference(int(payment.order_id), int(payment.id))


def list_payments_for_admin(
    *,
    status: str | None,
    limit: int,
    sort_by: str,
    sort_dir: str,
    db: Session,
) -> list[dict]:
    safe_limit = max(1, min(int(limit), 500))
    query = db.query(Payment).join(Order, Payment.order_id == Order.id).options(joinedload(Payment.order))
    if status is not None:
        normalized_status = status.strip().lower()
        if normalized_status not in {"pending", "paid", "cancelled", "expired"}:
            raise ValueError("invalid status")
        query = query.filter(Payment.status == normalized_status)

    if sort_by not in {"created_at", "id"}:
        raise ValueError("invalid sort_by")
    if sort_dir not in {"asc", "desc"}:
        raise ValueError("invalid sort_dir")
    sort_column = Payment.created_at if sort_by == "created_at" else Payment.id
    if sort_dir == "asc":
        query = query.order_by(sort_column.asc(), Payment.id.asc())
    else:
        query = query.order_by(sort_column.desc(), Payment.id.desc())

    rows = query.limit(safe_limit).all()
    result: list[dict] = []
    status_by_payment = _open_incident_status_by_payment_ids(
        payment_ids=[int(payment.id) for payment in rows],
        db=db,
    )
    for payment in rows:
        item = payment_to_dict(payment)
        order = payment.order
        item["order_status"] = order.status if order is not None else None
        item["user_id"] = int(order.user_id) if order is not None else None
        incident_status = status_by_payment.get(int(payment.id))
        item["has_open_incident"] = incident_status is not None
        item["incident_status"] = incident_status
        result.append(item)
    return result
