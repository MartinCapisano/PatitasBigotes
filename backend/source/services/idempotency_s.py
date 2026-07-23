from __future__ import annotations

from datetime import datetime, timedelta, UTC
import hashlib
import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from source.db.models import IdempotencyRecord

IDEMPOTENCY_TTL_HOURS = 24

# Substrings that mark a key as carrying a secret. Matched case-insensitively
# against the key name, not its value, so the check stays cheap and predictable.
_SECRET_KEY_MARKERS = (
    "token",
    "secret",
    "access",
    "password",
    "card",
    "cvv",
    "number",
)


def sanitize_failure_payload(payload: object) -> object:
    """Recursively redact obvious secrets from a payload before persisting it.

    Only failure payloads go through this. A 'completed' record's payload is
    replayed verbatim to the client, so redacting it would corrupt the replay;
    a 'failed' record's payload is built from exception text that can carry
    provider tokens, and nothing reads it back except our own recovery path.
    """
    if isinstance(payload, dict):
        out = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SECRET_KEY_MARKERS):
                out[key] = "<redacted>"
            else:
                out[key] = sanitize_failure_payload(value)
        return out
    if isinstance(payload, list):
        return [sanitize_failure_payload(item) for item in payload]
    return payload


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


def _is_expired(record: IdempotencyRecord, *, now: datetime) -> bool:
    # SQLite hands back naive datetimes even for DateTime(timezone=True), so
    # comparing against an aware `now` would raise. Everything written here is
    # UTC, so reading a naive value as UTC is the truthful interpretation.
    expires_at = record.expires_at
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


def acquire_record(
    *,
    scope: str,
    idempotency_key: str,
    request_hash: str,
    db: Session,
    expires_at: datetime | None = None,
    now: datetime | None = None,
) -> tuple[IdempotencyRecord, bool]:
    """Take (scope, idempotency_key), replacing a collision that has expired.

    The unique index does not know about expires_at, so a record past its TTL
    still collides and would come back as an unusable claim: a 'completed' one
    replays a stale response forever, a 'processing' one answers 409 forever.
    Something has to make an expired key claimable again.

    That expiry check lives here, scoped to the one key being acquired, rather
    than in a prune pass over the whole table at the start of each request. Same
    effect for the caller, but O(1) and touching only rows this request owns --
    a bulk prune took locks on up to 200 unrelated rows inside the caller's
    transaction, so two concurrent checkouts contended over expired records
    neither of them had asked about. Bulk cleanup belongs to the sweeper job.
    """
    moment = now or datetime.now(UTC)
    deadline = expires_at or (moment + timedelta(hours=IDEMPOTENCY_TTL_HOURS))

    def _insert() -> IdempotencyRecord:
        record = IdempotencyRecord(
            scope=scope,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_payload="{}",
            status="processing",
            created_at=moment,
            expires_at=deadline,
        )
        with db.begin_nested():
            db.add(record)
            db.flush()
        return record

    try:
        return _insert(), True
    except IntegrityError:
        existing = get_record(scope=scope, idempotency_key=idempotency_key, db=db)
        if existing is None:
            raise
        if not _is_expired(existing, now=moment):
            return existing, False
        db.delete(existing)
        db.flush()
        try:
            return _insert(), True
        except IntegrityError:
            # Another request claimed the key between our delete and our
            # insert. Theirs is live by definition, so it wins and this one
            # reports the collision as usual.
            retaken = get_record(scope=scope, idempotency_key=idempotency_key, db=db)
            if retaken is None:
                raise
            return retaken, False


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

