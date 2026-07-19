"""Read-only payment listing queries for the admin panel.

Split out of payment_s.py, which had grown into a god file mixing this with core
payment creation/transition logic, webhook bookkeeping, and MercadoPago normalization.
"""
from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from source.db.models import Order, Payment, PaymentIncident
from source.services.payment_s import _payment_to_dict
from source.services.refund_s import PAYMENT_INCIDENT_STATUS_PENDING_REVIEW


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
    result = [_payment_to_dict(payment) for payment in payments]
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
    safe_limit = max(1, min(int(limit), 500))
    rows = (
        db.query(Payment)
        .join(Order, Payment.order_id == Order.id)
        .options(joinedload(Payment.order))
        .filter(
            Payment.method == "bank_transfer",
            Payment.status == "pending",
            Order.status == "submitted",
        )
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .limit(safe_limit)
        .all()
    )
    result: list[dict] = []
    status_by_payment = _open_incident_status_by_payment_ids(
        payment_ids=[int(payment.id) for payment in rows],
        db=db,
    )
    for payment in rows:
        item = _payment_to_dict(payment)
        order = payment.order
        item["order_status"] = order.status if order is not None else None
        item["user_id"] = int(order.user_id) if order is not None else None
        incident_status = status_by_payment.get(int(payment.id))
        item["has_open_incident"] = incident_status is not None
        item["incident_status"] = incident_status
        result.append(item)
    return result


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
        item = _payment_to_dict(payment)
        order = payment.order
        item["order_status"] = order.status if order is not None else None
        item["user_id"] = int(order.user_id) if order is not None else None
        incident_status = status_by_payment.get(int(payment.id))
        item["has_open_incident"] = incident_status is not None
        item["incident_status"] = incident_status
        result.append(item)
    return result
