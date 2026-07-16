from __future__ import annotations

from datetime import datetime, timedelta, timezone, UTC

from sqlalchemy.orm import Session

from source.db.models import AuthLoginThrottle
from source.services.anti_abuse_s import get_or_create_locked_row

MAX_FAILED_ATTEMPTS = 6
WINDOW_MINUTES = 15
BLOCK_MINUTES = 20


class LoginRateLimitExceededError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    return str(email).strip().lower()


def _normalize_ip(ip: str | None) -> str:
    normalized = str(ip or "").strip()
    return normalized if normalized else "unknown"


def _get_row(*, scope: str, key: str, db: Session) -> AuthLoginThrottle | None:
    return (
        db.query(AuthLoginThrottle)
        .filter(AuthLoginThrottle.scope == scope, AuthLoginThrottle.key == key)
        .first()
    )


def _iter_rows(*, email: str, ip: str, now: datetime, db: Session) -> tuple[AuthLoginThrottle, AuthLoginThrottle]:
    email_row, _ = get_or_create_locked_row(scope="email", key=_normalize_email(email), now=now, db=db)
    ip_row, _ = get_or_create_locked_row(scope="ip", key=_normalize_ip(ip), now=now, db=db)
    return email_row, ip_row


def enforce_login_rate_limit(email: str, ip: str, db: Session) -> None:
    now = _utc_now()
    email_row = _get_row(scope="email", key=_normalize_email(email), db=db)
    ip_row = _get_row(scope="ip", key=_normalize_ip(ip), db=db)
    for row in (email_row, ip_row):
        if row is None:
            continue
        blocked_until = row.blocked_until
        if blocked_until is not None and blocked_until.replace(tzinfo=timezone.utc) > now:
            raise LoginRateLimitExceededError("too many attempts, try later")


def _register_failure_for_row(*, row: AuthLoginThrottle, now: datetime) -> None:
    window_expires_at = row.window_started_at.replace(tzinfo=timezone.utc) + timedelta(
        minutes=WINDOW_MINUTES,
    )
    if now > window_expires_at:
        row.failed_count = 1
        row.window_started_at = now
        row.blocked_until = None
    else:
        row.failed_count = int(row.failed_count) + 1

    if row.failed_count >= MAX_FAILED_ATTEMPTS:
        row.blocked_until = now + timedelta(minutes=BLOCK_MINUTES)

    row.updated_at = now


def register_login_failure(email: str, ip: str, db: Session) -> None:
    now = _utc_now()
    for row in _iter_rows(email=email, ip=ip, now=now, db=db):
        _register_failure_for_row(row=row, now=now)


def _clear_row(*, row: AuthLoginThrottle, now: datetime) -> None:
    row.failed_count = 0
    row.window_started_at = now
    row.blocked_until = None
    row.updated_at = now


def clear_login_failures(email: str, ip: str, db: Session) -> None:
    now = _utc_now()
    email_row = _get_row(scope="email", key=_normalize_email(email), db=db)
    ip_row = _get_row(scope="ip", key=_normalize_ip(ip), db=db)
    for row in (email_row, ip_row):
        if row is not None:
            _clear_row(row=row, now=now)


def prune_auth_login_throttles(
    *,
    now: datetime,
    older_than_days: int,
    limit: int,
    db: Session,
) -> int:
    safe_older_than_days = max(1, int(older_than_days))
    safe_limit = max(1, int(limit))
    threshold = now - timedelta(days=safe_older_than_days)

    candidate_ids = [
        row.id
        for row in (
            db.query(AuthLoginThrottle.id)
            .filter(AuthLoginThrottle.updated_at <= threshold)
            .order_by(AuthLoginThrottle.updated_at.asc(), AuthLoginThrottle.id.asc())
            .limit(safe_limit)
            .all()
        )
    ]
    if not candidate_ids:
        return 0

    deleted = (
        db.query(AuthLoginThrottle)
        .filter(AuthLoginThrottle.id.in_(candidate_ids))
        .delete(synchronize_session=False)
    )
    db.flush()
    return int(deleted or 0)

