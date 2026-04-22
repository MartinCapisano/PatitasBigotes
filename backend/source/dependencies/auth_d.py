from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from auth.security import decode_access_token, parsear_sub_a_user_id
from source.db.models import User
from source.db.session import get_db
from source.services.auth_cookies_s import get_access_token_from_request


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    access_token = get_access_token_from_request(request)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token cookie",
        )

    try:
        payload = decode_access_token(access_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing subject",
        )

    raw_tv = payload.get("tv")
    if raw_tv is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    try:
        token_version = int(raw_tv)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = get_current_user_id(payload)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or int(user.token_version) != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return payload


def get_current_user_id(current_user: dict) -> int:
    try:
        return parsear_sub_a_user_id(current_user.get("sub"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        ) from exc


def require_admin(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    user_id = get_current_user_id(current_user)
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if not bool(user.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permissions required",
        )

    current_user["is_admin"] = bool(user.is_admin)
    return current_user
