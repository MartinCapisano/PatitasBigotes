from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from source.db.models import User
from source.services.notifications_s import create_admin_notification
from source.services.post_commit_actions_s import (
    enqueue_post_commit_order_paid_email,
    should_skip_order_paid_email,
)

logger = logging.getLogger(__name__)

EVENT_ORDER_SUBMITTED = "order_submitted"
EVENT_ORDER_PAID = "order_paid"
EVENT_POSSIBLE_REFUND_DETECTED = "possible_refund_detected"
EVENT_ORDER_CANCELLED = "order_cancelled"


def _require_int(payload: dict, field: str) -> int:
    if field not in payload or payload[field] is None:
        raise ValueError(f"{field} is required")
    return int(payload[field])


def handle_order_submitted_event(*, payload: dict, db: Session) -> None:
    order_id = _require_int(payload, "order_id")
    create_admin_notification(
        event_type=EVENT_ORDER_SUBMITTED,
        title="Nueva orden submitted",
        message=f"La orden #{order_id} fue enviada y espera pago.",
        order_id=order_id,
        dedupe_key=f"admin:order:{order_id}:submitted",
        db=db,
    )


def handle_order_paid_event(*, payload: dict, db: Session) -> None:
    order_id = _require_int(payload, "order_id")
    user_id = _require_int(payload, "user_id")
    payment_id = _require_int(payload, "payment_id")
    total_amount = _require_int(payload, "total_amount")
    currency = str(payload.get("currency") or "ARS").strip() or "ARS"
    order_status = str(payload.get("order_status") or EVENT_ORDER_PAID).strip() or EVENT_ORDER_PAID
    items = payload.get("items")
    normalized_items = items if isinstance(items, list) else []

    create_admin_notification(
        event_type=EVENT_ORDER_PAID,
        title="Orden pagada",
        message=f"La orden #{order_id} quedo en estado paid.",
        order_id=order_id,
        payment_id=payment_id,
        dedupe_key=f"admin:order:{order_id}:paid",
        db=db,
    )

    if should_skip_order_paid_email(db=db):
        logger.info(
            "event=domain_event_email_skipped event_type=%s order_id=%s user_id=%s reason=suppressed",
            EVENT_ORDER_PAID,
            order_id,
            user_id,
        )
        return

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        logger.warning(
            "event=domain_event_email_skipped event_type=%s order_id=%s user_id=%s reason=user_not_found",
            EVENT_ORDER_PAID,
            order_id,
            user_id,
        )
        return

    to_email = str(user.email or "").strip()
    if not to_email:
        logger.warning(
            "event=domain_event_email_skipped event_type=%s order_id=%s user_id=%s reason=missing_email",
            EVENT_ORDER_PAID,
            order_id,
            user_id,
        )
        return

    enqueue_post_commit_order_paid_email(
        payload={
            "to_email": to_email,
            "order_id": order_id,
            "order_status": order_status,
            "payment_id": payment_id,
            "total_amount": total_amount,
            "currency": currency,
            "items": normalized_items,
        },
        db=db,
    )


def handle_possible_refund_event(*, payload: dict, db: Session) -> None:
    order_id = _require_int(payload, "order_id")
    payment_id = _require_int(payload, "payment_id")
    incident_id = _require_int(payload, "incident_id")

    create_admin_notification(
        event_type="possible_refund",
        title="Posible refund detectado",
        message=f"Pago #{payment_id} en orden #{order_id} requiere revision para posible reembolso.",
        order_id=order_id,
        payment_id=payment_id,
        incident_id=incident_id,
        dedupe_key=f"admin:incident:{incident_id}:possible_refund",
        db=db,
    )


def handle_order_cancelled_event(*, payload: dict, db: Session) -> None:
    order_id = _require_int(payload, "order_id")
    reason = str(payload.get("reason") or "").strip()
    message = f"La orden #{order_id} fue cancelada."
    if reason:
        message = f"{message} Motivo: {reason}."

    create_admin_notification(
        event_type=EVENT_ORDER_CANCELLED,
        title="Orden cancelada",
        message=message,
        order_id=order_id,
        dedupe_key=f"admin:order:{order_id}:cancelled",
        db=db,
    )


def publish_domain_event(*, event_type: str, payload: dict, db: Session) -> None:
    normalized_type = str(event_type or "").strip().lower()
    if normalized_type == EVENT_ORDER_SUBMITTED:
        handle_order_submitted_event(payload=payload, db=db)
        return
    if normalized_type == EVENT_ORDER_PAID:
        handle_order_paid_event(payload=payload, db=db)
        return
    if normalized_type == EVENT_POSSIBLE_REFUND_DETECTED:
        handle_possible_refund_event(payload=payload, db=db)
        return
    if normalized_type == EVENT_ORDER_CANCELLED:
        handle_order_cancelled_event(payload=payload, db=db)
        return
    raise ValueError("unsupported domain event")
