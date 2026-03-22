from __future__ import annotations

from datetime import datetime, timedelta, UTC
import hashlib
import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from source.db.models import IdempotencyRecord

IDEMPOTENCY_TTL_HOURS = 24


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def normalize_idempotency_key(raw: str) -> str:
    normalized = str(raw or "").strip()
    if not normalized:
        raise ValueError("idempotency_key is required")
    return normalized


def build_guest_checkout_scope(email: str) -> str:
    normalized_email = str(email or "").strip().lower()
    if not normalized_email:
        raise ValueError("email is required")
    return f"checkout_guest:{normalized_email}"


def canonicalize_payload(payload: dict) -> str:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def hash_payload(canonical_json: str) -> str:
    normalized = str(canonical_json or "")
    if not normalized:
        raise ValueError("canonical payload is required")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_record(*, scope: str, idempotency_key: str, db: Session) -> IdempotencyRecord | None:
    return (
        db.query(IdempotencyRecord)
        .filter(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
        .first()
    )


def save_completed_record(
    *,
    scope: str,
    idempotency_key: str,
    request_hash: str,
    response_payload: dict,
    db: Session,
    expires_at: datetime | None = None,
) -> IdempotencyRecord:
    record = IdempotencyRecord(
        scope=scope,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_payload=json.dumps(
            response_payload,
            separators=(",", ":"),
            ensure_ascii=True,
            default=_json_default,
        ),
        status="completed",
        created_at=datetime.now(UTC),
        expires_at=expires_at or (datetime.now(UTC) + timedelta(hours=IDEMPOTENCY_TTL_HOURS)),
    )
    db.add(record)
    db.flush()
    return record


def acquire_record(
    *,
    scope: str,
    idempotency_key: str,
    request_hash: str,
    db: Session,
    expires_at: datetime | None = None,
) -> tuple[IdempotencyRecord, bool]:
    record = IdempotencyRecord(
        scope=scope,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_payload="{}",
        status="processing",
        created_at=datetime.now(UTC),
        expires_at=expires_at or (datetime.now(UTC) + timedelta(hours=IDEMPOTENCY_TTL_HOURS)),
    )
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
        return record, True
    except IntegrityError:
        existing = get_record(scope=scope, idempotency_key=idempotency_key, db=db)
        if existing is None:
            raise
        return existing, False


def mark_record_completed(
    *,
    record: IdempotencyRecord,
    response_payload: dict,
    db: Session,
) -> IdempotencyRecord:
    record.response_payload = json.dumps(
        response_payload,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    )
    record.status = "completed"
    db.flush()
    return record


def mark_record_failed(
    *,
    record: IdempotencyRecord,
    response_payload: dict,
    db: Session,
) -> IdempotencyRecord:
    record.response_payload = json.dumps(
        response_payload,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    )
    record.status = "failed"
    db.flush()
    return record


def load_replay_payload(record: IdempotencyRecord) -> dict:
    try:
        parsed = json.loads(record.response_payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid idempotency response payload") from exc
    if not isinstance(parsed, dict):
        raise ValueError("invalid idempotency response payload")
    return parsed


def prune_expired_records(
    *,
    now: datetime,
    db: Session,
    limit: int = 200,
) -> int:
    safe_limit = max(1, int(limit))
    expired_ids = [
        row.id
        for row in (
            db.query(IdempotencyRecord.id)
            .filter(IdempotencyRecord.expires_at <= now)
            .order_by(IdempotencyRecord.expires_at.asc(), IdempotencyRecord.id.asc())
            .limit(safe_limit)
            .all()
        )
    ]
    if not expired_ids:
        return 0
    deleted = (
        db.query(IdempotencyRecord)
        .filter(IdempotencyRecord.id.in_(expired_ids))
        .delete(synchronize_session=False)
    )
    db.flush()
    return int(deleted or 0)

