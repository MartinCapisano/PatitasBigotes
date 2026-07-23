from __future__ import annotations

from datetime import datetime, timedelta, timezone, UTC

from fastapi import HTTPException
from sqlalchemy.orm import Session

from source.services.auth_security_s import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    ensure_password_policy,
    hash_password,
    hash_refresh_token,
    obtener_config_jwt,
    parsear_sub_a_user_id,
    verify_password,
)
from source.services.auth_tokens_s import ACTION_EMAIL_VERIFY, create_one_time_token
from source.services.post_commit_actions_s import enqueue_post_commit_email_verification
from source.db.config import get_app_base_url
from source.db.models import User, UserRefreshSession

VERIFY_EMAIL_TTL_HOURS = 24
PASSWORD_RESET_TTL_MINUTES = 30


def _ts_to_utc_datetime(raw_ts: object) -> datetime:
    try:
        return datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid token timestamp") from exc


def _upsert_refresh_session(
    *,
    user_id: int,
    refresh_token: str,
    refresh_claims: dict,
    db: Session,
) -> UserRefreshSession:
    now = datetime.now(timezone.utc)
    claim_iat = _ts_to_utc_datetime(refresh_claims.get("iat"))
    claim_exp = _ts_to_utc_datetime(refresh_claims.get("exp"))
    jti = str(refresh_claims.get("jti", "")).strip()
    if not jti:
        raise ValueError("Invalid refresh token id")

    current = (
        db.query(UserRefreshSession)
        .filter(UserRefreshSession.user_id == user_id)
        .first()
    )
    if current is None:
        current = UserRefreshSession(
            user_id=user_id,
            created_at=now,
        )
        db.add(current)

    current.token_hash = hash_refresh_token(refresh_token)
    current.token_jti = jti
    current.claim_sub = str(refresh_claims["sub"])
    current.claim_type = str(refresh_claims["type"])
    current.claim_iss = str(refresh_claims["iss"])
    current.claim_iat = claim_iat
    current.claim_exp = claim_exp
    current.expires_at = claim_exp
    current.updated_at = now
    return current


def authenticate_user(*, email: str, password: str, db: Session) -> User:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("email is required")
    if not password:
        raise ValueError("password is required")

    user = db.query(User).filter(User.email == normalized_email).first()
    if user is None:
        raise LookupError("user not found")
    if not bool(user.has_account):
        raise ValueError("user does not have an account yet")
    if user.email_verified_at is None:
        raise ValueError("email not verified")
    if not verify_password(password, user.password_hash):
        raise ValueError("invalid credentials")
    return user


def issue_token_pair(*, user: User, db: Session) -> dict:
    access_token = create_access_token(
        {
            "sub": str(user.id),
            "is_admin": bool(user.is_admin),
            "tv": int(user.token_version),
        }
    )
    refresh_token = create_refresh_token(usuario_id=int(user.id))
    refresh_claims = decode_refresh_token(refresh_token)
    _upsert_refresh_session(
        user_id=int(user.id),
        refresh_token=refresh_token,
        refresh_claims=refresh_claims,
        db=db,
    )

    settings = obtener_config_jwt()
    minutes = settings["access_token_expire_minutes"]
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "access_expires_in_seconds": minutes * 60,
        "access_expires_in_minutes": minutes,
    }


def bump_user_token_version(*, user_id: int, db: Session) -> User:
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .first()
    )
    if user is None:
        raise LookupError("user not found")
    user.token_version = int(user.token_version) + 1
    db.flush()
    return user


def refresh_with_token(*, refresh_token: str, db: Session) -> dict:
    refresh_claims = decode_refresh_token(refresh_token)
    user_id = parsear_sub_a_user_id(refresh_claims.get("sub"))
    token_jti = str(refresh_claims.get("jti", "")).strip()
    if not token_jti:
        raise ValueError("Invalid refresh token id")

    session_row = (
        db.query(UserRefreshSession)
        .filter(UserRefreshSession.user_id == user_id)
        .with_for_update()
        .first()
    )
    if session_row is None:
        raise LookupError("refresh session not found")
    if session_row.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise ValueError("refresh token expired")
    if session_row.token_hash != hash_refresh_token(refresh_token):
        raise ValueError("invalid refresh token")
    if session_row.token_jti != token_jti:
        raise ValueError("invalid refresh token")

    user = bump_user_token_version(user_id=user_id, db=db)

    return issue_token_pair(user=user, db=db)


def logout_with_refresh_token(*, refresh_token: str, db: Session) -> None:
    refresh_claims = decode_refresh_token(refresh_token)
    user_id = parsear_sub_a_user_id(refresh_claims.get("sub"))
    token_jti = str(refresh_claims.get("jti", "")).strip()
    if not token_jti:
        raise ValueError("Invalid refresh token id")

    session_row = (
        db.query(UserRefreshSession)
        .filter(UserRefreshSession.user_id == user_id)
        .with_for_update()
        .first()
    )
    if session_row is None:
        raise ValueError("invalid refresh token")

    now = datetime.now(timezone.utc)
    if session_row.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise ValueError("expired refresh token")
    if session_row.token_hash != hash_refresh_token(refresh_token):
        raise ValueError("invalid refresh token")
    if session_row.token_jti != token_jti:
        raise ValueError("invalid refresh token")

    bump_user_token_version(user_id=user_id, db=db)
    db.delete(session_row)


def set_user_password_and_invalidate_sessions(
    *,
    user_id: int,
    new_password: str,
    db: Session,
) -> User:
    user = (
        db.query(User)
        .filter(User.id == int(user_id))
        .with_for_update()
        .first()
    )
    if user is None:
        raise LookupError("user not found")

    user.password_hash = hash_password(new_password)
    user.has_account = True
    user.token_version = int(user.token_version) + 1

    refresh_session = (
        db.query(UserRefreshSession)
        .filter(UserRefreshSession.user_id == int(user_id))
        .with_for_update()
        .first()
    )
    if refresh_session is not None:
        db.delete(refresh_session)
    db.flush()
    return user


def find_user_by_email(*, email: str, db: Session) -> User | None:
    normalized = str(email).strip().lower()
    if not normalized:
        return None
    return db.query(User).filter(User.email == normalized).first()


def serialize_my_profile(user: User) -> dict:
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


def get_user_profile(*, user_id: int, db: Session) -> dict:
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise LookupError("user not found")
    return serialize_my_profile(user)


def change_user_password(
    *,
    user_id: int,
    current_password: str,
    new_password: str,
    db: Session,
) -> None:
    user = (
        db.query(User)
        .filter(User.id == int(user_id))
        .with_for_update()
        .first()
    )
    if user is None:
        raise LookupError("user not found")
    if not verify_password(current_password, user.password_hash):
        raise ValueError("current password is invalid")
    ensure_password_policy(new_password)

    set_user_password_and_invalidate_sessions(
        user_id=int(user_id),
        new_password=new_password,
        db=db,
    )


def update_user_profile(
    *,
    user_id: int,
    first_name: str,
    last_name: str,
    phone: str,
    email: str,
    client_ip: str,
    db: Session,
) -> dict:
    user = (
        db.query(User)
        .filter(User.id == int(user_id))
        .with_for_update()
        .first()
    )
    if user is None:
        raise LookupError("user not found")

    normalized_email = str(email).strip().lower()
    if not normalized_email:
        raise ValueError("email is required")

    verification_email_sent = False
    if normalized_email != str(user.email or "").strip().lower():
        existing = (
            db.query(User)
            .filter(User.email == normalized_email, User.id != int(user_id))
            .first()
        )
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
        enqueue_post_commit_email_verification(
            to_email=user.email,
            verify_link=verify_link,
            db=db,
        )
        verification_email_sent = True

    user.first_name = str(first_name).strip()
    user.last_name = str(last_name).strip()
    user.phone = str(phone).strip()
    db.flush()

    return {
        "profile": serialize_my_profile(user),
        "verification_email_sent": verification_email_sent,
    }
