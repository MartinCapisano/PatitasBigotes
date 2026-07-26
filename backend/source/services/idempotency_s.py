from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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


class FailurePolicy(enum.Enum):
    """Qué hacer con el record si el handler falla.

    El invariante (ADR 0002): la policy NO es un eje independiente — correlaciona
    con la dependencia de sesión que exige el árbol de decisión transaccional
    (`docs/diagrams/decision-sesion-transaccional.mmd`). Un endpoint que hace
    trabajo post-commit (mails, llamadas a MP) va por `get_db` + commit manual, y
    ese commit manual es lo que hace posible PERSIST; uno que no, cae en el default
    `get_db_transactional`, y su rollback automático es lo que hace correcto DISCARD.

    PERSIST ⇔ `get_db` + commit manual + trabajo post-commit (checkout de invitado):
        commitea un record 'failed' que sobrevive al rollback del trabajo de
        negocio, para que un retry pueda recuperar re-inicializando Mercado Pago en
        vez de rehacer todo.
    DISCARD ⇔ `get_db_transactional`, default (venta admin): no hace bookkeeping de
        fallo; deja que la transacción revierta el `acquire`. Un retry arranca de
        cero. Ver el caveat de SAVEPOINT en pysqlite/SQLite documentado en
        `create_admin_sale_endpoint` (orders_r.py): es propio del driver, no del
        patrón, y no lo sufre PERSIST porque commitea explícitamente.
    """

    PERSIST = "persist"
    DISCARD = "discard"


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


class IdempotencyContext:
    """Handle que el handler usa dentro de `with idempotent(...) as ctx:`.

    Es dueño del bookkeeping del record (complete/fail), NO de la transacción: el
    commit/rollback del trabajo de negocio queda en el handler o en la dependencia
    de DB. Así el mismo CM sirve tanto bajo `get_db` como bajo `get_db_transactional`.
    """

    def __init__(self, resolution: IdempotencyResolution, db: Session) -> None:
        self._resolution = resolution
        self._db = db
        self._settled = False

    @property
    def replay(self) -> dict | None:
        """Response guardado a devolver tal cual, o None si no es un REPLAY."""
        if self._resolution.outcome is Outcome.REPLAY:
            return self._resolution.stored_payload
        return None

    @property
    def recover_from(self) -> dict | None:
        """Payload del intento fallido a recuperar, o None si no es un RECOVER."""
        if self._resolution.outcome is Outcome.RECOVER:
            return self._resolution.stored_payload
        return None

    @property
    def settled(self) -> bool:
        """True si el handler ya marcó el record (complete/fail).

        Equivale al viejo chequeo `status == 'processing'` invertido: un handler que
        maneja su propio bookkeeping de fallo puede preguntar `if not ctx.settled`
        antes de marcarlo, sin tocar el estado del record.
        """
        return self._settled

    def complete(self, response_payload: dict) -> None:
        """Marca el record como completado. No commitea.

        No-op si la clave está desactivada (sin record).
        """
        if self._resolution.record is not None:
            mark_record_completed(
                record=self._resolution.record,
                response_payload=response_payload,
                db=self._db,
            )
        self._settled = True

    def fail(self, response_payload: dict) -> None:
        """Marca el record como fallido con un payload de dominio. No commitea.

        Al saldar el record (_settled), la red de seguridad de `idempotent()` no lo
        pisa con un payload genérico. No-op si la clave está desactivada.
        """
        if self._resolution.record is not None:
            mark_record_failed(
                record=self._resolution.record,
                response_payload=response_payload,
                db=self._db,
            )
        self._settled = True


@contextmanager
def idempotent(
    *,
    scope: str,
    key: str | None,
    payload: dict,
    db: Session,
    failure: FailurePolicy = FailurePolicy.DISCARD,
    ttl_hours: int = IDEMPOTENCY_TTL_HOURS,
) -> Iterator[IdempotencyContext]:
    """Envuelve un handler idempotente: resuelve la clave y garantiza que un fallo
    inesperado no deje el record atascado en 'processing'.

    El CM es dueño del bookkeeping del record (complete/fail + la red de seguridad),
    NO de la transacción de negocio: el commit/rollback lo maneja el handler o la
    dependencia de DB. Por eso sirve tanto bajo `get_db` como bajo
    `get_db_transactional` sin cambiar. `failure` no se elige libre: debe seguir a la
    dependencia de sesión según el árbol de decisión transaccional (ADR 0002 /
    `docs/diagrams/decision-sesion-transaccional.mmd`) — PERSIST con `get_db` +
    commit manual, DISCARD con `get_db_transactional`.

    El handler inspecciona `ctx.replay` / `ctx.recover_from`; en el camino de
    ejecución llama `ctx.complete(result)` (o `ctx.fail(payload)` ante un fallo de
    dominio) y maneja su propio commit. Los conflictos (clave reusada / en curso)
    se propagan como `IdempotencyError` y los mapea el borde HTTP (R01-3).
    """
    resolution = resolve_idempotency(
        scope=scope, key=key, payload=payload, db=db, ttl_hours=ttl_hours
    )
    ctx = IdempotencyContext(resolution, db)
    try:
        yield ctx
    except Exception as exc:
        # Red de seguridad: replica orders_r.py:301-317. Solo bajo PERSIST, y solo
        # si el handler no saldó el record, evita dejarlo en 'processing'
        # commiteando un fallo genérico que sobreviva al rollback del negocio.
        # Bajo DISCARD no hace nada: la dependencia transaccional revierte el acquire.
        # `not ctx._settled` se evalúa antes que `record.status` a propósito: si el
        # handler ya saldó el record y luego hizo rollback, el objeto puede estar
        # expirado y leer `.status` dispararía una query sobre una fila revertida.
        record = resolution.record
        if (
            failure is FailurePolicy.PERSIST
            and record is not None
            and not ctx._settled
            and record.status == "processing"
        ):
            try:
                mark_record_failed(
                    record=record, response_payload={"detail": str(exc)}, db=db
                )
                db.commit()
            except Exception:
                db.rollback()
        raise

