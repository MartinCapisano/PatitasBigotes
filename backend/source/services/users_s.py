from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth.security import ensure_password_policy, hash_password
from source.db.models import User, UserRefreshSession
from source.schemas import (
    CreateAdminUserRequest,
    CreateGuestUserRequest,
    CreateUserRequest,
    ResolveUserRequest,
)


def _serialize_user_created(user: User) -> dict:
    return {
        "id": int(user.id),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "dni": user.dni,
        "phone": user.phone,
        "has_account": bool(user.has_account),
        "is_admin": bool(user.is_admin),
        "status": "created",
    }


def serialize_user_basic(user: User) -> dict:
    return {
        "id": int(user.id),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "dni": user.dni,
        "phone": user.phone,
        "has_account": bool(user.has_account),
    }


def serialize_admin_user(user: User) -> dict:
    return {
        "id": int(user.id),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": user.phone,
        "has_account": bool(user.has_account),
        "is_admin": bool(user.is_admin),
        "email_verified": user.email_verified_at is not None,
        "created_at": user.created_at,
    }


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def create_auth_user(
    *,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
    db: Session,
) -> User:
    normalized_email = str(email).strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="email is required")

    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="email already exists")
    ensure_password_policy(password)

    user = User(
        first_name=_normalize_required_text(first_name, field_name="first_name"),
        last_name=_normalize_required_text(last_name, field_name="last_name"),
        email=normalized_email,
        phone=None,
        password_hash=hash_password(password),
        has_account=True,
        is_admin=False,
        email_verified_at=None,
        email_verification_sent_at=None,
    )
    db.add(user)
    db.flush()
    db.refresh(user)
    return user


def create_user(payload: CreateUserRequest, db: Session) -> dict:
    user_data = payload.model_dump()
    user = create_auth_user(
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
        email=user_data["email"],
        password=user_data["password"],
        db=db,
    )
    return _serialize_user_created(user)


def create_admin_user(payload: CreateAdminUserRequest, db: Session) -> dict:
    user_data = payload.model_dump()
    normalized_email = str(user_data["email"]).strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="email is required")

    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="email already exists")
    ensure_password_policy(user_data["password"])

    user = User(
        first_name=_normalize_required_text(
            user_data["first_name"],
            field_name="first_name",
        ),
        last_name=_normalize_required_text(
            user_data["last_name"],
            field_name="last_name",
        ),
        email=normalized_email,
        phone=_normalize_optional_text(user_data.get("phone")),
        password_hash=hash_password(user_data["password"]),
        has_account=True,
        is_admin=True,
        email_verified_at=datetime.now(UTC),
        email_verification_sent_at=None,
    )
    db.add(user)
    db.flush()
    db.refresh(user)
    return serialize_admin_user(user)


def revoke_admin_status(
    *,
    target_user_id: int,
    actor_user_id: int,
    db: Session,
) -> dict:
    if int(target_user_id) == int(actor_user_id):
        raise ValueError("cannot revoke own admin status")

    user = (
        db.query(User)
        .filter(User.id == int(target_user_id))
        .with_for_update()
        .first()
    )
    if user is None:
        raise LookupError("user not found")
    if not bool(user.is_admin):
        raise HTTPException(status_code=409, detail="user is not admin")

    user.is_admin = False
    user.token_version = int(user.token_version) + 1

    refresh_session = (
        db.query(UserRefreshSession)
        .filter(UserRefreshSession.user_id == int(user.id))
        .with_for_update()
        .first()
    )
    if refresh_session is not None:
        db.delete(refresh_session)

    db.flush()
    return {
        "id": int(user.id),
        "email": user.email,
        "is_admin": bool(user.is_admin),
        "token_version": int(user.token_version),
        "admin_revoked": True,
    }


def create_guest_user(payload: CreateGuestUserRequest, db: Session) -> dict:
    user_data = payload.model_dump()
    normalized_email = str(user_data["email"]).strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="email is required")

    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="email already exists")

    user = User(
        first_name=_normalize_required_text(
            user_data["first_name"],
            field_name="first_name",
        ),
        last_name=_normalize_required_text(
            user_data["last_name"],
            field_name="last_name",
        ),
        email=normalized_email,
        phone=_normalize_required_text(
            user_data["phone"],
            field_name="phone",
        ),
        # Sentinel invalid hash: prevents authentication until account activation flow.
        password_hash="!",
        has_account=False,
        is_admin=False,
    )
    db.add(user)
    db.flush()
    db.refresh(user)
    return _serialize_user_created(user)


def get_or_create_user_by_contact(
    *,
    email: str,
    first_name: str,
    last_name: str,
    phone: str,
    dni: str | None = None,
    db: Session,
) -> tuple[User, bool]:
    normalized_email = str(email).strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="email is required")
    normalized_dni = _normalize_optional_text(dni)
    normalized_phone = _normalize_required_text(phone, field_name="phone")
    normalized_first_name = _normalize_required_text(first_name, field_name="first_name")
    normalized_last_name = _normalize_required_text(last_name, field_name="last_name")

    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user is not None:
        existing_first_name = str(existing_user.first_name or "").strip().lower()
        existing_last_name = str(existing_user.last_name or "").strip().lower()
        existing_phone = _normalize_optional_text(existing_user.phone)

        if existing_first_name and existing_first_name != normalized_first_name.lower():
            raise HTTPException(
                status_code=409,
                detail="contact data does not match existing user for this email",
            )
        if existing_last_name and existing_last_name != normalized_last_name.lower():
            raise HTTPException(
                status_code=409,
                detail="contact data does not match existing user for this email",
            )
        if existing_phone is not None and existing_phone != normalized_phone:
            raise HTTPException(
                status_code=409,
                detail="contact data does not match existing user for this email",
            )
        if (
            normalized_dni is not None
            and existing_user.dni is not None
            and str(existing_user.dni).strip() != normalized_dni
        ):
            raise ValueError("dni does not match existing user")
        if existing_user.dni is None and normalized_dni is not None:
            existing_user.dni = normalized_dni
        if existing_user.phone is None and normalized_phone is not None:
            existing_user.phone = normalized_phone
        db.flush()
        return existing_user, False

    user = User(
        first_name=normalized_first_name,
        last_name=normalized_last_name,
        email=normalized_email,
        dni=normalized_dni,
        phone=normalized_phone,
        # Sentinel invalid hash: prevents authentication until account activation flow.
        password_hash="!",
        has_account=False,
        is_admin=False,
    )
    db.add(user)
    db.flush()
    db.refresh(user)
    return user, True


def resolve_user(payload: ResolveUserRequest, db: Session) -> dict:
    data = payload.model_dump()
    user, created = get_or_create_user_by_contact(
        email=data["email"],
        first_name=data["first_name"],
        last_name=data["last_name"],
        phone=data["phone"],
        dni=data.get("dni"),
        db=db,
    )
    return {
        "user": serialize_user_basic(user),
        "created": created,
    }


def search_users(
    *,
    db: Session,
    email: str | None = None,
    dni: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    limit: int = 20,
) -> list[dict]:
    normalized_email = _normalize_optional_text(email)
    normalized_dni = _normalize_optional_text(dni)
    normalized_first_name = _normalize_optional_text(first_name)
    normalized_last_name = _normalize_optional_text(last_name)
    normalized_phone = _normalize_optional_text(phone)

    if not any(
        [
            normalized_email,
            normalized_dni,
            normalized_first_name,
            normalized_last_name,
            normalized_phone,
        ]
    ):
        raise ValueError("at least one search filter is required")

    safe_limit = max(1, min(int(limit), 100))
    query = db.query(User)

    if normalized_email is not None:
        query = query.filter(User.email == normalized_email.lower())
    if normalized_dni is not None:
        query = query.filter(User.dni == normalized_dni)
    if normalized_first_name is not None:
        query = query.filter(func.lower(User.first_name).like(f"%{normalized_first_name.lower()}%"))
    if normalized_last_name is not None:
        query = query.filter(func.lower(User.last_name).like(f"%{normalized_last_name.lower()}%"))
    if normalized_phone is not None:
        query = query.filter(User.phone.like(f"%{normalized_phone}%"))

    users = query.order_by(User.created_at.desc(), User.id.desc()).limit(safe_limit).all()
    return [serialize_user_basic(user) for user in users]
