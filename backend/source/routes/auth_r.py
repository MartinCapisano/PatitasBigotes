import logging
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from source.services.auth_s import (
    authenticate_user,
    issue_token_pair,
    logout_with_refresh_token,
    refresh_with_token,
    set_user_password_and_invalidate_sessions,
)
from source.services.auth_security_s import ensure_password_policy, obtener_config_jwt, verify_password
from source.db.config import get_app_base_url
from source.db.models import User
from source.dependencies.auth_d import get_current_user, get_current_user_id
from source.db.session import get_db, get_db_transactional
from source.errors import raise_http_error_from_exception
from source.schemas import (
    EmailRequest,
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    RegisterRequest,
    TokenRequest,
    UpdateMyProfileRequest,
)
from source.services.anti_abuse_s import (
    enforce_email_verify_resend_limits,
    enforce_password_reset_request_limits,
    enforce_public_signup_limits,
)
from source.services.auth_rate_limit_s import (
    LoginRateLimitExceededError,
    clear_login_failures,
    enforce_login_rate_limit,
    register_login_failure,
)
from source.services.auth_tokens_s import (
    ACTION_EMAIL_VERIFY,
    ACTION_PASSWORD_RESET,
    consume_one_time_token,
    create_one_time_token,
)
from source.services.auth_cookies_s import (
    clear_auth_cookies,
    get_refresh_token_from_request,
    set_auth_cookies,
)
from source.services.email_s import send_email_verification, send_password_reset
from source.services.users_s import create_auth_user

router = APIRouter()
logger = logging.getLogger(__name__)
VERIFY_EMAIL_TTL_HOURS = 24
PASSWORD_RESET_TTL_MINUTES = 30


def _extract_client_ip(request: Request) -> str:
    # request.client.host is trustworthy as-is: Uvicorn's ProxyHeadersMiddleware
    # (proxy_headers=True by default) already rewrites it from X-Forwarded-For,
    # but only when the connection comes from an IP listed in FORWARDED_ALLOW_IPS
    # (env var read by Uvicorn at startup; defaults to 127.0.0.1). In production
    # behind a real reverse proxy, FORWARDED_ALLOW_IPS must be set to that proxy's
    # IP/CIDR, or this will silently fall back to the proxy's own IP for every request.
    if request.client is not None and request.client.host:
        return str(request.client.host).strip()
    return "unknown"


@router.post("/auth/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_transactional),
):
    client_ip = _extract_client_ip(request)
    normalized_email = str(payload.email).strip().lower()
    try:
        enforce_login_rate_limit(email=normalized_email, ip=client_ip, db=db)
        user = authenticate_user(
            email=payload.email,
            password=payload.password,
            db=db,
        )
        clear_login_failures(email=normalized_email, ip=client_ip, db=db)
        tokens = issue_token_pair(user=user, db=db)
    except LoginRateLimitExceededError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many attempts, try later",
        )
    except ValueError as exc:
        register_login_failure(email=normalized_email, ip=client_ip, db=db)
        db.commit()
        if str(exc) == "email not verified":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="email not verified",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    except LookupError:
        register_login_failure(email=normalized_email, ip=client_ip, db=db)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    settings = obtener_config_jwt()
    set_auth_cookies(
        response=response,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        access_max_age_seconds=int(tokens["access_expires_in_seconds"]),
        refresh_max_age_seconds=int(settings["refresh_token_expire_days"]) * 24 * 60 * 60,
    )
    logger.info("event=auth_login_success email=%s ip=%s", normalized_email, client_ip)
    return {
        "data": {
            "logged_in": True,
            "access_expires_in_seconds": int(tokens["access_expires_in_seconds"]),
            "access_expires_in_minutes": int(tokens["access_expires_in_minutes"]),
        }
    }


@router.post("/auth/refresh")
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_transactional),
):
    refresh_token = get_refresh_token_from_request(request)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token cookie",
        )
    try:
        tokens = refresh_with_token(refresh_token=refresh_token, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    settings = obtener_config_jwt()
    set_auth_cookies(
        response=response,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        access_max_age_seconds=int(tokens["access_expires_in_seconds"]),
        refresh_max_age_seconds=int(settings["refresh_token_expire_days"]) * 24 * 60 * 60,
    )
    return {
        "data": {
            "refreshed": True,
            "access_expires_in_seconds": int(tokens["access_expires_in_seconds"]),
            "access_expires_in_minutes": int(tokens["access_expires_in_minutes"]),
        }
    }


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db_transactional),
):
    refresh_token = get_refresh_token_from_request(request)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token cookie",
        )
    try:
        logout_with_refresh_token(refresh_token=refresh_token, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    clear_auth_cookies(response=response)
    logger.info("event=auth_logout_success")
    return {"data": {"logged_out": True}}


def _find_user_by_email(*, email: str, db: Session) -> User | None:
    normalized = str(email).strip().lower()
    if not normalized:
        return None
    return db.query(User).filter(User.email == normalized).first()


def _serialize_my_profile(user: User) -> dict:
    return {
        "id": int(user.id),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": user.phone,
        "has_account": bool(user.has_account),
        "is_admin": bool(user.is_admin),
        "email_verified": user.email_verified_at is not None,
        "email_verified_at": user.email_verified_at,
        "created_at": user.created_at,
    }


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db_transactional),
):
    client_ip = _extract_client_ip(request)
    try:
        enforce_public_signup_limits(
            client_ip=client_ip,
            email=str(payload.email),
            db=db,
        )
        user = create_auth_user(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=str(payload.email),
            password=payload.password,
            db=db,
        )
        raw_token = create_one_time_token(
            user_id=int(user.id),
            action=ACTION_EMAIL_VERIFY,
            ttl=timedelta(hours=VERIFY_EMAIL_TTL_HOURS),
            requested_ip=client_ip,
            db=db,
        )
        user.email_verification_sent_at = datetime.now(UTC)
        verify_link = f"{get_app_base_url()}/verify-email?token={raw_token}"
        send_email_verification(to_email=user.email, verify_link=verify_link)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    logger.info("event=auth_register email=%s ip=%s", str(payload.email).strip().lower(), client_ip)
    return {"data": {"registered": True}}


@router.post("/auth/email/verify/request")
def email_verify_request(
    payload: EmailRequest,
    request: Request,
    db: Session = Depends(get_db_transactional),
):
    client_ip = _extract_client_ip(request)
    try:
        enforce_email_verify_resend_limits(
            client_ip=client_ip,
            email=str(payload.email),
            db=db,
        )
        user = _find_user_by_email(email=str(payload.email), db=db)
        if user is not None and bool(user.has_account) and user.email_verified_at is None:
            raw_token = create_one_time_token(
                user_id=int(user.id),
                action=ACTION_EMAIL_VERIFY,
                ttl=timedelta(hours=VERIFY_EMAIL_TTL_HOURS),
                requested_ip=client_ip,
                db=db,
            )
            user.email_verification_sent_at = datetime.now(UTC)
            verify_link = f"{get_app_base_url()}/verify-email?token={raw_token}"
            send_email_verification(to_email=user.email, verify_link=verify_link)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    logger.info("event=auth_verify_requested email=%s ip=%s", str(payload.email).strip().lower(), client_ip)
    return {"data": {"requested": True}}


@router.post("/auth/email/verify/confirm")
def email_verify_confirm(
    payload: TokenRequest,
    db: Session = Depends(get_db_transactional),
):
    try:
        user = consume_one_time_token(
            raw_token=payload.token,
            action=ACTION_EMAIL_VERIFY,
            db=db,
        )
        user.email_verified_at = datetime.now(UTC)
        db.flush()
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    logger.info("event=auth_verify_confirmed")
    return {"data": {"verified": True}}


@router.post("/auth/password/reset/request")
def password_reset_request(
    payload: EmailRequest,
    request: Request,
    db: Session = Depends(get_db_transactional),
):
    client_ip = _extract_client_ip(request)
    try:
        enforce_password_reset_request_limits(
            client_ip=client_ip,
            email=str(payload.email),
            db=db,
        )
        user = _find_user_by_email(email=str(payload.email), db=db)
        if user is not None and bool(user.has_account) and user.email_verified_at is not None:
            raw_token = create_one_time_token(
                user_id=int(user.id),
                action=ACTION_PASSWORD_RESET,
                ttl=timedelta(minutes=PASSWORD_RESET_TTL_MINUTES),
                requested_ip=client_ip,
                db=db,
            )
            reset_link = f"{get_app_base_url()}/reset-password?token={raw_token}"
            send_password_reset(to_email=user.email, reset_link=reset_link)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    logger.info("event=auth_reset_requested email=%s ip=%s", str(payload.email).strip().lower(), client_ip)
    return {"data": {"requested": True}}


@router.post("/auth/password/reset/confirm")
def password_reset_confirm(
    payload: PasswordResetConfirmRequest,
    db: Session = Depends(get_db_transactional),
):
    try:
        ensure_password_policy(payload.new_password)
        user = consume_one_time_token(
            raw_token=payload.token,
            action=ACTION_PASSWORD_RESET,
            db=db,
        )
        set_user_password_and_invalidate_sessions(
            user_id=int(user.id),
            new_password=payload.new_password,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    logger.info("event=auth_reset_confirmed")
    return {"data": {"password_reset": True}}


@router.post("/auth/password/change")
def password_change(
    payload: PasswordChangeRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_transactional),
):
    user_id = get_current_user_id(current_user)
    try:
        user = (
            db.query(User)
            .filter(User.id == int(user_id))
            .with_for_update()
            .first()
        )
        if user is None:
            raise LookupError("user not found")
        if not verify_password(payload.current_password, user.password_hash):
            raise ValueError("current password is invalid")
        ensure_password_policy(payload.new_password)
        set_user_password_and_invalidate_sessions(
            user_id=int(user_id),
            new_password=payload.new_password,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    logger.info("event=auth_password_changed user_id=%s", int(user_id))
    return {"data": {"password_changed": True}}


@router.get("/auth/me")
def get_my_profile(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(current_user)
    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if user is None:
            raise LookupError("user not found")
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": _serialize_my_profile(user)}


@router.patch("/auth/me")
def update_my_profile(
    payload: UpdateMyProfileRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_transactional),
):
    user_id = get_current_user_id(current_user)
    client_ip = _extract_client_ip(request)
    try:
        user = (
            db.query(User)
            .filter(User.id == int(user_id))
            .with_for_update()
            .first()
        )
        if user is None:
            raise LookupError("user not found")

        normalized_email = str(payload.email).strip().lower()
        if not normalized_email:
            raise ValueError("email is required")

        verification_email_sent = False
        if normalized_email != str(user.email or "").strip().lower():
            existing = db.query(User).filter(User.email == normalized_email, User.id != int(user_id)).first()
            if existing is not None:
                raise HTTPException(status_code=409, detail="email already exists")

            user.email = normalized_email
            user.email_verified_at = None
            user.email_verification_sent_at = datetime.now(UTC)
            raw_token = create_one_time_token(
                user_id=int(user.id),
                action=ACTION_EMAIL_VERIFY,
                ttl=timedelta(hours=VERIFY_EMAIL_TTL_HOURS),
                requested_ip=client_ip,
                db=db,
            )
            verify_link = f"{get_app_base_url()}/verify-email?token={raw_token}"
            send_email_verification(to_email=user.email, verify_link=verify_link)
            verification_email_sent = True

        user.first_name = str(payload.first_name).strip()
        user.last_name = str(payload.last_name).strip()
        user.phone = str(payload.phone).strip()
        db.flush()
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    logger.info("event=auth_profile_updated user_id=%s email_changed=%s", int(user_id), bool(verification_email_sent))
    return {
        "data": _serialize_my_profile(user),
        "meta": {
            "verification_email_sent": verification_email_sent,
        },
    }

