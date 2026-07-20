from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import logging

from sqlalchemy.orm import Session, joinedload

from source.db.models import Payment, PaymentIncident, PaymentRefund
from source.services.mercadopago_client import create_refund
from source.services.domain_events_s import publish_domain_event

logger = logging.getLogger(__name__)

PAYMENT_INCIDENT_TYPE_LATE_PAID_DUPLICATE = "late_paid_duplicate"
PAYMENT_INCIDENT_STATUS_PENDING_REVIEW = "pending_review"
PAYMENT_INCIDENT_STATUS_RESOLVED_REFUNDED = "resolved_refunded"
PAYMENT_INCIDENT_STATUS_RESOLVED_NO_REFUND = "resolved_no_refund"

PAYMENT_REFUND_STATUS_REQUESTED = "requested"
PAYMENT_REFUND_STATUS_APPROVED = "approved"
PAYMENT_REFUND_STATUS_FAILED = "failed"


def _serialize_payload(payload: dict | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def _deserialize_payload(payload: str | None) -> dict | None:
    if payload is None:
        return None
    try:
        parsed = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _incident_to_dict(incident: PaymentIncident) -> dict:
    return {
        "id": int(incident.id),
        "order_id": int(incident.order_id),
        "payment_id": int(incident.payment_id),
        "type": str(incident.type),
        "status": str(incident.status),
        "reason": incident.reason,
        "created_at": incident.created_at,
        "resolved_at": incident.resolved_at,
        "resolved_by_user_id": int(incident.resolved_by_user_id) if incident.resolved_by_user_id is not None else None,
    }


def _refund_to_dict(refund: PaymentRefund) -> dict:
    return {
        "id": int(refund.id),
        "order_id": int(refund.order_id),
        "payment_id": int(refund.payment_id),
        "incident_id": int(refund.incident_id),
        "amount": int(refund.amount),
        "currency": str(refund.currency),
        "provider": str(refund.provider),
        "provider_refund_id": refund.provider_refund_id,
        "status": str(refund.status),
        "idempotency_key": str(refund.idempotency_key),
        "requested_by_user_id": int(refund.requested_by_user_id),
        "requested_at": refund.requested_at,
        "updated_at": refund.updated_at,
        "provider_payload_data": _deserialize_payload(refund.provider_payload),
    }


def _extract_provider_payment_id(payment: Payment) -> str | None:
    payload = _deserialize_payload(payment.provider_payload)
    if not isinstance(payload, dict):
        return None
    reconciliation = payload.get("reconciliation")
    if isinstance(reconciliation, dict):
        candidate = reconciliation.get("provider_payment_id")
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    lookup = payload.get("payment_lookup")
    if isinstance(lookup, dict):
        candidate = lookup.get("id")
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    return None


def create_late_paid_incident_if_needed(
    *,
    order_id: int,
    payment_id: int,
    reason: str,
    db: Session,
) -> dict:
    existing = (
        db.query(PaymentIncident)
        .filter(
            PaymentIncident.order_id == int(order_id),
            PaymentIncident.payment_id == int(payment_id),
            PaymentIncident.type == PAYMENT_INCIDENT_TYPE_LATE_PAID_DUPLICATE,
            PaymentIncident.status == PAYMENT_INCIDENT_STATUS_PENDING_REVIEW,
        )
        .first()
    )
    if existing is not None:
        return _incident_to_dict(existing)

    incident = PaymentIncident(
        order_id=int(order_id),
        payment_id=int(payment_id),
        type=PAYMENT_INCIDENT_TYPE_LATE_PAID_DUPLICATE,
        status=PAYMENT_INCIDENT_STATUS_PENDING_REVIEW,
        reason=str(reason or "").strip() or None,
    )
    db.add(incident)
    db.flush()
    publish_domain_event(
        event_type="possible_refund_detected",
        payload={
            "order_id": int(order_id),
            "payment_id": int(payment_id),
            "incident_id": int(incident.id),
        },
        db=db,
    )
    logger.warning(
        "event=late_payment_incident_created order_id=%s payment_id=%s incident_id=%s reason=%s",
        int(order_id),
        int(payment_id),
        int(incident.id),
        str(reason),
    )
    return _incident_to_dict(incident)


def list_payment_incidents_for_admin(
    *,
    status: str | None,
    limit: int,
    db: Session,
) -> list[dict]:
    safe_limit = max(1, min(int(limit), 500))
    query = db.query(PaymentIncident).options(
        joinedload(PaymentIncident.payment),
        joinedload(PaymentIncident.order),
    )
    if status is not None:
        normalized = str(status).strip().lower()
        if normalized not in {
            PAYMENT_INCIDENT_STATUS_PENDING_REVIEW,
            PAYMENT_INCIDENT_STATUS_RESOLVED_REFUNDED,
            PAYMENT_INCIDENT_STATUS_RESOLVED_NO_REFUND,
        }:
            raise ValueError("invalid status")
        query = query.filter(PaymentIncident.status == normalized)
    rows = query.order_by(PaymentIncident.created_at.desc(), PaymentIncident.id.desc()).limit(safe_limit).all()
    result: list[dict] = []
    for row in rows:
        payload = _incident_to_dict(row)
        payment = row.payment
        order = row.order
        payload["payment"] = {
            "id": int(payment.id) if payment is not None else None,
            "method": str(payment.method) if payment is not None else None,
            "status": str(payment.status) if payment is not None else None,
            "amount": int(payment.amount) if payment is not None else None,
            "currency": str(payment.currency) if payment is not None else None,
            "external_ref": payment.external_ref if payment is not None else None,
        }
        payload["order"] = {
            "id": int(order.id) if order is not None else None,
            "status": str(order.status) if order is not None else None,
            "total_amount": int(order.total_amount) if order is not None else None,
            "user_id": int(order.user_id) if order is not None else None,
        }
        result.append(payload)
    return result


def _build_refund_idempotency_key(incident_id: int, payment_id: int, amount: int) -> str:
    digest = hashlib.sha256(f"{incident_id}:{payment_id}:{amount}".encode("utf-8")).hexdigest()[:24]
    return f"refund-{incident_id}-{digest}"


def resolve_payment_incident_no_refund(
    *,
    incident_id: int,
    admin_user_id: int,
    reason: str,
    db: Session,
) -> dict:
    normalized_reason = str(reason or "").strip()
    if not normalized_reason:
        raise ValueError("reason is required")

    incident = (
        db.query(PaymentIncident)
        .filter(PaymentIncident.id == int(incident_id))
        .with_for_update()
        .first()
    )
    if incident is None:
        raise LookupError("payment incident not found")
    if incident.status != PAYMENT_INCIDENT_STATUS_PENDING_REVIEW:
        raise ValueError("payment incident is already resolved")

    now = datetime.now(UTC)
    incident.status = PAYMENT_INCIDENT_STATUS_RESOLVED_NO_REFUND
    incident.reason = normalized_reason
    incident.resolved_at = now
    incident.resolved_by_user_id = int(admin_user_id)
    db.flush()
    return _incident_to_dict(incident)


def create_mercadopago_refund(
    *,
    incident_id: int,
    amount: int | None,
    admin_user_id: int,
    reason: str,
    db: Session,
) -> dict:
    normalized_reason = str(reason or "").strip()
    if not normalized_reason:
        raise ValueError("reason is required")

    incident = (
        db.query(PaymentIncident)
        .options(joinedload(PaymentIncident.payment), joinedload(PaymentIncident.order))
        .filter(PaymentIncident.id == int(incident_id))
        .with_for_update()
        .first()
    )
    if incident is None:
        raise LookupError("payment incident not found")
    if incident.status != PAYMENT_INCIDENT_STATUS_PENDING_REVIEW:
        if incident.status == PAYMENT_INCIDENT_STATUS_RESOLVED_REFUNDED:
            existing = (
                db.query(PaymentRefund)
                .filter(PaymentRefund.incident_id == int(incident.id))
                .order_by(PaymentRefund.requested_at.desc(), PaymentRefund.id.desc())
                .first()
            )
            if existing is not None:
                return {
                    "incident": _incident_to_dict(incident),
                    "refund": _refund_to_dict(existing),
                }
        raise ValueError("payment incident is already resolved")

    payment = incident.payment
    order = incident.order
    if payment is None or order is None:
        raise LookupError("incident references missing order or payment")
    if str(payment.method) != "mercadopago":
        raise ValueError("only mercadopago payments can be refunded")
    if str(payment.status) != "paid":
        raise ValueError("only paid payments can be refunded")

    refund_amount = int(payment.amount) if amount is None else int(amount)
    if refund_amount <= 0:
        raise ValueError("refund amount must be greater than 0")
    if refund_amount > int(payment.amount):
        raise ValueError("refund amount cannot exceed payment amount")

    existing_active = (
        db.query(PaymentRefund)
        .filter(
            PaymentRefund.payment_id == int(payment.id),
            PaymentRefund.status.in_([PAYMENT_REFUND_STATUS_REQUESTED, PAYMENT_REFUND_STATUS_APPROVED]),
        )
        .order_by(PaymentRefund.requested_at.desc(), PaymentRefund.id.desc())
        .first()
    )
    if existing_active is not None:
        if int(existing_active.incident_id) == int(incident.id):
            return {
                "incident": _incident_to_dict(incident),
                "refund": _refund_to_dict(existing_active),
            }
        raise ValueError("payment already has an active refund")

    idempotency_key = _build_refund_idempotency_key(int(incident.id), int(payment.id), refund_amount)
    now = datetime.now(UTC)
    refund = PaymentRefund(
        order_id=int(order.id),
        payment_id=int(payment.id),
        incident_id=int(incident.id),
        amount=refund_amount,
        currency=str(payment.currency or "ARS").strip().upper(),
        provider="mercadopago",
        provider_refund_id=None,
        status=PAYMENT_REFUND_STATUS_REQUESTED,
        idempotency_key=idempotency_key,
        requested_by_user_id=int(admin_user_id),
        requested_at=now,
        provider_payload=_serialize_payload(
            {
                "requested_reason": normalized_reason,
                "requested_at": now.isoformat().replace("+00:00", "Z"),
                "amount": refund_amount,
            }
        ),
    )
    db.add(refund)
    db.flush()
    logger.info(
        "event=refund_requested incident_id=%s payment_id=%s refund_id=%s amount=%s",
        int(incident.id),
        int(payment.id),
        int(refund.id),
        int(refund_amount),
    )

    try:
        provider_payment_id = _extract_provider_payment_id(payment)
        if provider_payment_id is None:
            raise ValueError("missing mercadopago provider payment id")
        provider_response = create_refund(
            payment_id=provider_payment_id,
            amount=refund_amount if refund_amount < int(payment.amount) else None,
            idempotency_key=idempotency_key,
        )
        provider_refund_id = provider_response.get("id")
        refund.provider_refund_id = str(provider_refund_id).strip() if provider_refund_id is not None else None
        refund.status = PAYMENT_REFUND_STATUS_APPROVED
        refund.provider_payload = _serialize_payload(provider_response)
        incident.status = PAYMENT_INCIDENT_STATUS_RESOLVED_REFUNDED
        incident.reason = normalized_reason
        incident.resolved_at = datetime.now(UTC)
        incident.resolved_by_user_id = int(admin_user_id)
        db.flush()
        logger.info(
            "event=refund_succeeded incident_id=%s payment_id=%s refund_id=%s provider_refund_id=%s",
            int(incident.id),
            int(payment.id),
            int(refund.id),
            str(refund.provider_refund_id or ""),
        )
        return {
            "incident": _incident_to_dict(incident),
            "refund": _refund_to_dict(refund),
        }
    except Exception as exc:
        # Commit the failed status now instead of leaving it to the caller's
        # transactional session wrapper, so that re-raising below doesn't trigger
        # a rollback that discards this refund request and its failed status.
        try:
            refund.status = PAYMENT_REFUND_STATUS_FAILED
            refund.provider_payload = _serialize_payload(
                {
                    "error": str(exc),
                    "requested_reason": normalized_reason,
                    "amount": refund_amount,
                }
            )
            db.commit()
        except Exception:
            # If marking failed errors, rollback to leave DB in a consistent
            # state and surface the original provider error.
            try:
                db.rollback()
            except Exception:
                pass
        logger.exception(
            "event=refund_failed incident_id=%s payment_id=%s refund_id=%s",
            int(incident.id),
            int(payment.id),
            int(refund.id),
        )
        raise
