"""Provider-agnostic webhook event bookkeeping (idempotent acquire, retry/dead-letter, replay).

Split out of payment_s.py, which had grown into a god file mixing this with MercadoPago
payload normalization and admin listing queries.
"""
from __future__ import annotations

from datetime import datetime, timedelta, UTC

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from source.db.models import WebhookEvent
from source.exceptions import WebhookReplayConflictError
from source.services.payment_s import _deserialize_provider_payload, _serialize_provider_payload

DEFAULT_WEBHOOK_MAX_ATTEMPTS = 4
DEFAULT_WEBHOOK_RETRY_DELAY_MINUTES = 60


def _normalize_webhook_key_part(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized


def _extract_webhook_data_id(payload: dict | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    raw = data.get("id")
    if raw is None:
        return None
    normalized = str(raw).strip()
    if not normalized:
        return None
    return normalized


def acquire_webhook_event(
    *,
    provider: str,
    event_key: str,
    payload: dict | None,
    db: Session,
) -> bool:
    normalized_provider = _normalize_webhook_key_part(provider)
    normalized_key = _normalize_webhook_key_part(event_key)
    if normalized_provider is None:
        raise ValueError("provider is required")
    if normalized_key is None:
        raise ValueError("event_key is required")

    now = datetime.now(UTC)
    event = WebhookEvent(
        provider=normalized_provider,
        event_key=normalized_key,
        status="processing",
        payload=_serialize_provider_payload(payload) if isinstance(payload, dict) else None,
        received_at=now,
        processed_at=None,
        last_error=None,
        next_retry_at=None,
        dead_letter_at=None,
    )
    try:
        with db.begin_nested():
            db.add(event)
            db.flush()
        return True
    except IntegrityError:
        existing = (
            db.query(WebhookEvent)
            .filter(
                WebhookEvent.provider == normalized_provider,
                WebhookEvent.event_key == normalized_key,
            )
            .with_for_update()
            .first()
        )
        if existing is None:
            return False
        if existing.status in {"failed", "dead_letter"}:
            existing.status = "processing"
            existing.received_at = now
            existing.processed_at = None
            existing.last_error = None
            existing.next_retry_at = None
            existing.dead_letter_at = None
            if isinstance(payload, dict):
                existing.payload = _serialize_provider_payload(payload)
            db.flush()
            return True
        return False


def mark_webhook_event_processed(
    *,
    provider: str,
    event_key: str,
    db: Session,
) -> None:
    event = (
        db.query(WebhookEvent)
        .filter(
            WebhookEvent.provider == provider,
            WebhookEvent.event_key == event_key,
        )
        .first()
    )
    if event is None:
        return
    event.status = "processed"
    event.processed_at = datetime.now(UTC)
    event.last_error = None
    event.next_retry_at = None
    event.dead_letter_at = None
    db.flush()


def mark_webhook_event_failed(
    *,
    provider: str,
    event_key: str,
    error_message: str,
    retry_delay_minutes: int = DEFAULT_WEBHOOK_RETRY_DELAY_MINUTES,
    max_attempts: int = DEFAULT_WEBHOOK_MAX_ATTEMPTS,
    db: Session,
) -> None:
    if retry_delay_minutes <= 0:
        raise ValueError("retry_delay_minutes must be greater than 0")
    if max_attempts <= 0:
        raise ValueError("max_attempts must be greater than 0")

    event = (
        db.query(WebhookEvent)
        .filter(
            WebhookEvent.provider == provider,
            WebhookEvent.event_key == event_key,
        )
        .first()
    )
    if event is None:
        return
    now = datetime.now(UTC)
    event.attempt_count = int(event.attempt_count or 0) + 1
    event.processed_at = now
    event.last_error = (error_message or "webhook processing failed")[:2000]
    if int(event.attempt_count) >= int(max_attempts):
        event.status = "dead_letter"
        event.dead_letter_at = now
        event.next_retry_at = None
    else:
        event.status = "failed"
        event.dead_letter_at = None
        event.next_retry_at = now + timedelta(minutes=int(retry_delay_minutes))
    db.flush()


def list_retryable_failed_webhook_events(
    *,
    provider: str,
    limit: int,
    now: datetime,
    db: Session,
) -> list[WebhookEvent]:
    normalized_provider = _normalize_webhook_key_part(provider)
    if normalized_provider is None:
        raise ValueError("provider is required")
    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    return (
        db.query(WebhookEvent)
        .filter(
            WebhookEvent.provider == normalized_provider,
            WebhookEvent.status == "failed",
            or_(WebhookEvent.next_retry_at.is_(None), WebhookEvent.next_retry_at <= now),
            WebhookEvent.dead_letter_at.is_(None),
        )
        .order_by(WebhookEvent.next_retry_at.asc(), WebhookEvent.processed_at.asc(), WebhookEvent.id.asc())
        .limit(int(limit))
        .all()
    )


def get_webhook_reprocess_metrics(
    *,
    provider: str,
    now: datetime,
    db: Session,
) -> dict[str, int]:
    normalized_provider = _normalize_webhook_key_part(provider)
    if normalized_provider is None:
        raise ValueError("provider is required")

    failed_due = (
        db.query(func.count(WebhookEvent.id))
        .filter(
            WebhookEvent.provider == normalized_provider,
            WebhookEvent.status == "failed",
            or_(WebhookEvent.next_retry_at.is_(None), WebhookEvent.next_retry_at <= now),
            WebhookEvent.dead_letter_at.is_(None),
        )
        .scalar()
    )
    failed_not_due = (
        db.query(func.count(WebhookEvent.id))
        .filter(
            WebhookEvent.provider == normalized_provider,
            WebhookEvent.status == "failed",
            WebhookEvent.next_retry_at.is_not(None),
            WebhookEvent.next_retry_at > now,
            WebhookEvent.dead_letter_at.is_(None),
        )
        .scalar()
    )
    dead_letter = (
        db.query(func.count(WebhookEvent.id))
        .filter(
            WebhookEvent.provider == normalized_provider,
            WebhookEvent.status == "dead_letter",
            WebhookEvent.dead_letter_at.is_not(None),
        )
        .scalar()
    )
    oldest_failed_received_at = (
        db.query(func.min(WebhookEvent.received_at))
        .filter(
            WebhookEvent.provider == normalized_provider,
            WebhookEvent.status == "failed",
            WebhookEvent.dead_letter_at.is_(None),
        )
        .scalar()
    )
    oldest_failed_age_seconds = 0
    if oldest_failed_received_at is not None:
        if oldest_failed_received_at.tzinfo is None:
            oldest_failed_received_at = oldest_failed_received_at.replace(tzinfo=UTC)
        oldest_failed_age_seconds = max(
            0,
            int((now - oldest_failed_received_at).total_seconds()),
        )

    return {
        "failed_due": int(failed_due or 0),
        "failed_not_due": int(failed_not_due or 0),
        "dead_letter": int(dead_letter or 0),
        "oldest_failed_age_seconds": int(oldest_failed_age_seconds),
    }


def replay_webhook_event_by_key(
    *,
    provider: str,
    event_key: str,
    db: Session,
    retry_delay_minutes: int = DEFAULT_WEBHOOK_RETRY_DELAY_MINUTES,
    max_attempts: int = DEFAULT_WEBHOOK_MAX_ATTEMPTS,
) -> dict:
    normalized_provider = _normalize_webhook_key_part(provider)
    normalized_key = _normalize_webhook_key_part(event_key)
    if normalized_provider is None:
        raise ValueError("provider is required")
    if normalized_key is None:
        raise ValueError("event_key is required")
    if normalized_provider != "mercadopago":
        raise ValueError("unsupported provider")

    event = (
        db.query(WebhookEvent)
        .filter(
            WebhookEvent.provider == normalized_provider,
            WebhookEvent.event_key == normalized_key,
        )
        .with_for_update()
        .first()
    )
    if event is None:
        raise LookupError("webhook event not found")

    previous_status = str(event.status)
    if previous_status not in {"failed", "dead_letter"}:
        raise WebhookReplayConflictError(
            "webhook event can only be replayed from failed/dead_letter status"
        )

    payload = _deserialize_provider_payload(event.payload)
    if payload is None:
        raise ValueError("invalid stored webhook payload")
    data_id = _extract_webhook_data_id(payload)
    if data_id is None:
        raise ValueError("stored webhook payload is missing data.id")

    event.status = "processing"
    event.processed_at = None
    event.last_error = None
    event.next_retry_at = None
    event.dead_letter_at = None
    db.flush()

    from source.services.mercadopago_client import WebhookNoOpError, process_mercadopago_event_payload

    try:
        updated_payment = process_mercadopago_event_payload(
            payload=payload,
            data_id=data_id,
            db=db,
        )
    except WebhookNoOpError as exc:
        if str(exc).strip().lower() == "payment not found":
            mark_webhook_event_failed(
                provider=normalized_provider,
                event_key=normalized_key,
                error_message=str(exc),
                retry_delay_minutes=retry_delay_minutes,
                max_attempts=max_attempts,
                db=db,
            )
        else:
            mark_webhook_event_processed(
                provider=normalized_provider,
                event_key=normalized_key,
                db=db,
            )
        refreshed = (
            db.query(WebhookEvent)
            .filter(
                WebhookEvent.provider == normalized_provider,
                WebhookEvent.event_key == normalized_key,
            )
            .first()
        )
        return {
            "event_key": normalized_key,
            "previous_status": previous_status,
            "new_status": str(refreshed.status if refreshed is not None else "unknown"),
            "processed": False,
            "reason": str(exc),
            "payment": None,
        }
    except Exception as exc:
        mark_webhook_event_failed(
            provider=normalized_provider,
            event_key=normalized_key,
            error_message=str(exc),
            retry_delay_minutes=retry_delay_minutes,
            max_attempts=max_attempts,
            db=db,
        )
        refreshed = (
            db.query(WebhookEvent)
            .filter(
                WebhookEvent.provider == normalized_provider,
                WebhookEvent.event_key == normalized_key,
            )
            .first()
        )
        return {
            "event_key": normalized_key,
            "previous_status": previous_status,
            "new_status": str(refreshed.status if refreshed is not None else "unknown"),
            "processed": False,
            "reason": str(exc),
            "payment": None,
        }

    mark_webhook_event_processed(
        provider=normalized_provider,
        event_key=normalized_key,
        db=db,
    )
    return {
        "event_key": normalized_key,
        "previous_status": previous_status,
        "new_status": "processed",
        "processed": True,
        "reason": None,
        "payment": updated_payment,
    }
