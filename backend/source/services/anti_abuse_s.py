from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from source.db.models import AuthLoginThrottle

IP_WINDOW = timedelta(minutes=5)
IP_MAX_REQUESTS = 20
EMAIL_WINDOW = timedelta(minutes=10)
EMAIL_MAX_REQUESTS = 6
EMAIL_MIN_INTERVAL_SECONDS = 20

SIGNUP_SCOPE_IP = "public_signup_ip"
SIGNUP_SCOPE_EMAIL_WINDOW = "public_signup_email_window"
SIGNUP_SCOPE_EMAIL_INTERVAL = "public_signup_email_interval"

CHECKOUT_SCOPE_IP = "public_checkout_ip"
CHECKOUT_SCOPE_EMAIL_WINDOW = "public_checkout_email_window"
CHECKOUT_SCOPE_EMAIL_INTERVAL = "public_checkout_email_interval"

PASSWORD_RESET_SCOPE_IP = "password_reset_request_ip"
PASSWORD_RESET_SCOPE_EMAIL_WINDOW = "password_reset_request_email_window"
PASSWORD_RESET_SCOPE_EMAIL_INTERVAL = "password_reset_request_email_interval"

VERIFY_RESEND_SCOPE_IP = "email_verify_resend_ip"
VERIFY_RESEND_SCOPE_EMAIL_WINDOW = "email_verify_resend_email_window"
VERIFY_RESEND_SCOPE_EMAIL_INTERVAL = "email_verify_resend_email_interval"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_email(value: str) -> str:
    return str(value).strip().lower()


def _normalize_ip(value: str) -> str:
    normalized = str(value).strip()
    return normalized if normalized else "unknown"


def get_or_create_locked_row(
    *,
    scope: str,
    key: str,
    now: datetime,
    db: Session,
) -> tuple[AuthLoginThrottle, bool]:
    row = (
        db.query(AuthLoginThrottle)
        .filter(AuthLoginThrottle.scope == scope, AuthLoginThrottle.key == key)
        .with_for_update()
        .first()
    )
    if row is not None:
        return row, False

    row = AuthLoginThrottle(
        scope=scope,
        key=key,
        failed_count=0,
        window_started_at=now,
        blocked_until=None,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        row = (
            db.query(AuthLoginThrottle)
            .filter(AuthLoginThrottle.scope == scope, AuthLoginThrottle.key == key)
            .with_for_update()
            .first()
        )
        if row is None:
            raise
    return row, True


def _enforce_window_limit(
    *,
    row: AuthLoginThrottle,
    now: datetime,
    window: timedelta,
    max_requests: int,
    detail: str,
) -> None:
    window_started_at = _as_utc(row.window_started_at) or now
    if now > window_started_at + window:
        row.failed_count = 0
        row.window_started_at = now

    if int(row.failed_count) >= int(max_requests):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )

    row.failed_count = int(row.failed_count) + 1
    row.updated_at = now


def _enforce_min_interval(
    *,
    row: AuthLoginThrottle,
    now: datetime,
    min_interval_seconds: int,
    detail: str,
    skip_if_new: bool = False,
) -> None:
    if skip_if_new:
        row.updated_at = now
        return

    last_hit_at = _as_utc(row.updated_at)
    if last_hit_at is not None:
        elapsed = (now - last_hit_at).total_seconds()
        if elapsed < float(min_interval_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
            )

    row.updated_at = now


def enforce_public_guest_checkout_limits(
    *,
    client_ip: str,
    email: str,
    website: str | None = None,
    db: Session,
) -> None:
    if website is not None and str(website).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid request",
        )

    _enforce_public_email_ip_limits(
        client_ip=client_ip,
        email=email,
        ip_scope=CHECKOUT_SCOPE_IP,
        email_window_scope=CHECKOUT_SCOPE_EMAIL_WINDOW,
        email_interval_scope=CHECKOUT_SCOPE_EMAIL_INTERVAL,
        ip_detail="too many checkout attempts from this ip",
        email_detail="too many checkout attempts for this email",
        interval_detail="please wait before retrying checkout",
        db=db,
    )


def enforce_public_signup_limits(
    *,
    client_ip: str,
    email: str,
    db: Session,
) -> None:
    _enforce_public_email_ip_limits(
        client_ip=client_ip,
        email=email,
        ip_scope=SIGNUP_SCOPE_IP,
        email_window_scope=SIGNUP_SCOPE_EMAIL_WINDOW,
        email_interval_scope=SIGNUP_SCOPE_EMAIL_INTERVAL,
        ip_detail="too many signup attempts from this ip",
        email_detail="too many signup attempts for this email",
        interval_detail="please wait before retrying signup",
        db=db,
    )


def enforce_password_reset_request_limits(
    *,
    client_ip: str,
    email: str,
    db: Session,
) -> None:
    _enforce_public_email_ip_limits(
        client_ip=client_ip,
        email=email,
        ip_scope=PASSWORD_RESET_SCOPE_IP,
        email_window_scope=PASSWORD_RESET_SCOPE_EMAIL_WINDOW,
        email_interval_scope=PASSWORD_RESET_SCOPE_EMAIL_INTERVAL,
        ip_detail="too many password reset attempts from this ip",
        email_detail="too many password reset attempts for this email",
        interval_detail="please wait before retrying password reset",
        db=db,
    )


def enforce_email_verify_resend_limits(
    *,
    client_ip: str,
    email: str,
    db: Session,
) -> None:
    _enforce_public_email_ip_limits(
        client_ip=client_ip,
        email=email,
        ip_scope=VERIFY_RESEND_SCOPE_IP,
        email_window_scope=VERIFY_RESEND_SCOPE_EMAIL_WINDOW,
        email_interval_scope=VERIFY_RESEND_SCOPE_EMAIL_INTERVAL,
        ip_detail="too many verification attempts from this ip",
        email_detail="too many verification attempts for this email",
        interval_detail="please wait before retrying verification",
        db=db,
    )


def _enforce_public_email_ip_limits(
    *,
    client_ip: str,
    email: str,
    ip_scope: str,
    email_window_scope: str,
    email_interval_scope: str,
    ip_detail: str,
    email_detail: str,
    interval_detail: str,
    db: Session,
) -> None:
    normalized_ip = _normalize_ip(client_ip)
    normalized_email = _normalize_email(email)
    now = _utc_now()

    ip_row, _ = get_or_create_locked_row(
        scope=ip_scope,
        key=normalized_ip,
        now=now,
        db=db,
    )
    email_window_row, _ = get_or_create_locked_row(
        scope=email_window_scope,
        key=normalized_email,
        now=now,
        db=db,
    )
    email_interval_row, email_interval_created = get_or_create_locked_row(
        scope=email_interval_scope,
        key=normalized_email,
        now=now,
        db=db,
    )

    _enforce_window_limit(
        row=ip_row,
        now=now,
        window=IP_WINDOW,
        max_requests=IP_MAX_REQUESTS,
        detail=ip_detail,
    )
    _enforce_window_limit(
        row=email_window_row,
        now=now,
        window=EMAIL_WINDOW,
        max_requests=EMAIL_MAX_REQUESTS,
        detail=email_detail,
    )
    _enforce_min_interval(
        row=email_interval_row,
        now=now,
        min_interval_seconds=EMAIL_MIN_INTERVAL_SECONDS,
        detail=interval_detail,
        skip_if_new=email_interval_created,
    )
    db.flush()

