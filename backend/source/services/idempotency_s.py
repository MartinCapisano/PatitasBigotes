from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
import enum
import hashlib
import json

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from source.db.models import IdempotencyRecord

IDEMPOTENCY_TTL_HOURS = 24


class IdempotencyError(Exception):
    """Base para los conflictos de idempotencia.

    Es transport-agnostic: el borde HTTP la mapea a una respuesta (ver R01-3).
    Lleva scope + idempotency_key para logging y para el mapeo en la ruta.
    """

    def __init__(self, scope: str, idempotency_key: str, message: str) -> None:
        self.scope = scope
        self.idempotency_key = idempotency_key
        super().__init__(message)


class IdempotencyKeyReusedError(IdempotencyError):
    """Misma clave, payload distinto. El borde la mapea a 409."""

    def __init__(self, scope: str, idempotency_key: str) -> None:
        super().__init__(
            scope,
            idempotency_key,
            "idempotency key already used with a different payload",
        )


class IdempotencyInProgressError(IdempotencyError):
    """Un request gemelo ya tiene la clave tomada. El borde la mapea a 409."""

    def __init__(self, scope: str, idempotency_key: str) -> None:
        super().__init__(
            scope,
            idempotency_key,
            "idempotent request already in progress",
        )


class Outcome(enum.Enum):
    """Desenlace de resolver una clave de idempotencia.

    EXECUTE: correr la lógica de negocio (record nuevo, o clave desactivada).
    REPLAY:  devolver el response guardado tal cual, sin re-ejecutar.
    RECOVER: un intento previo falló; el handler decide cómo recuperar.
    """

    EXECUTE = "execute"
    REPLAY = "replay"
    RECOVER = "recover"


@dataclass(frozen=True)
class IdempotencyResolution:
    """Resultado de resolver una clave: colapsa los 4 caminos en un outcome.

    `record` es None cuando la clave está desactivada (sin Idempotency-Key).
    `stored_payload` está presente en REPLAY y RECOVER.
    """

    outcome: Outcome
    record: IdempotencyRecord | None = None
    stored_payload: dict | None = None


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


def resolve_idempotency(
    *,
    scope: str,
    key: str | None,
    payload: dict,
    db: Session,
    ttl_hours: int = IDEMPOTENCY_TTL_HOURS,
    prune: bool = True,
) -> IdempotencyResolution:
    """Toma (o encuentra) el record de idempotencia y colapsa los cuatro caminos
    en un unico Outcome.

    Transport-agnostic: no lanza HTTPException y nunca commitea. El borde HTTP
    mapea IdempotencyError (ver R01-3); la coordinacion transaccional queda en el
    llamador o en el context manager de R01-4.

    - clave vacia/None      -> EXECUTE sin record (idempotencia desactivada).
    - record recien creado  -> EXECUTE con el record tomado.
    - misma clave, hash !=  -> IdempotencyKeyReusedError (camino 1).
    - status 'completed'    -> REPLAY con el payload guardado (camino 2).
    - status 'failed'       -> RECOVER con el payload guardado (camino 3).
    - status 'processing'   -> IdempotencyInProgressError (camino 4).
    """
    if key is None or not str(key).strip():
        return IdempotencyResolution(Outcome.EXECUTE)

    now = datetime.now(UTC)
    if prune:
        prune_expired_records(now=now, db=db)

    normalized_key = normalize_idempotency_key(key)
    request_hash = hash_payload(canonicalize_payload(payload))
    record, created = acquire_record(
        scope=scope,
        idempotency_key=normalized_key,
        request_hash=request_hash,
        expires_at=now + timedelta(hours=ttl_hours),
        db=db,
    )
    if created:
        return IdempotencyResolution(Outcome.EXECUTE, record=record)
    if record.request_hash != request_hash:
        raise IdempotencyKeyReusedError(scope, normalized_key)
    if record.status == "completed":
        return IdempotencyResolution(
            Outcome.REPLAY, record=record, stored_payload=load_replay_payload(record)
        )
    if record.status == "failed":
        return IdempotencyResolution(
            Outcome.RECOVER, record=record, stored_payload=load_replay_payload(record)
        )
    raise IdempotencyInProgressError(scope, normalized_key)

