from datetime import datetime, timedelta, timezone
import hashlib
import os
import uuid
from typing import Optional

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

DEFAULT_ALGORITHM = "HS256"
DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS = 30
DEFAULT_JWT_ISSUER = "patitasbigotes-api"

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (UnknownHashError, ValueError, TypeError):
        return False


def ensure_password_policy(password: str) -> None:
    normalized = str(password or "")
    if len(normalized) < 8:
        raise ValueError("password must be at least 8 characters long")
    has_special = any(not ch.isalnum() and not ch.isspace() for ch in normalized)
    if not has_special:
        raise ValueError("password must include at least one special character")


def obtener_config_jwt() -> dict:
    secret_key = os.getenv("JWT_SECRET", "").strip()
    algorithm = os.getenv("JWT_ALGORITHM", DEFAULT_ALGORITHM).strip()
    issuer = os.getenv("JWT_ISSUER", DEFAULT_JWT_ISSUER).strip()
    raw_access_minutes = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "").strip()
    raw_refresh_days = os.getenv(
        "REFRESH_TOKEN_EXPIRE_DAYS",
        str(DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS),
    ).strip()

    if not secret_key:
        raise RuntimeError("JWT_SECRET is required")
    if not algorithm:
        raise RuntimeError("JWT_ALGORITHM is required")
    if not issuer:
        raise RuntimeError("JWT_ISSUER is required")
    if not raw_access_minutes:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES is required")

    access_minutes = int(raw_access_minutes)
    if access_minutes <= 0:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be greater than 0")

    refresh_days = int(raw_refresh_days)
    if refresh_days <= 0:
        raise RuntimeError("REFRESH_TOKEN_EXPIRE_DAYS must be greater than 0")

    return {
        "secret_key": secret_key,
        "algorithm": algorithm,
        "issuer": issuer,
        "access_token_expire_minutes": access_minutes,
        "refresh_token_expire_days": refresh_days,
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def construir_claims_access(
    usuario_id: int,
    is_admin: bool,
    now: datetime | None = None,
) -> dict:
    settings = obtener_config_jwt()
    issued_at = now or _utc_now()
    expire_at = issued_at + timedelta(minutes=settings["access_token_expire_minutes"])
    return {
        "sub": str(usuario_id),
        "type": "access",
        "is_admin": bool(is_admin),
        "iss": settings["issuer"],
        "iat": int(issued_at.timestamp()),
        "exp": int(expire_at.timestamp()),
    }


def construir_claims_refresh(usuario_id: int, now: datetime | None = None) -> dict:
    settings = obtener_config_jwt()
    issued_at = now or _utc_now()
    expire_at = issued_at + timedelta(days=settings["refresh_token_expire_days"])
    return {
        "sub": str(usuario_id),
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iss": settings["issuer"],
        "iat": int(issued_at.timestamp()),
        "exp": int(expire_at.timestamp()),
    }


def firmar_jwt(claims: dict) -> str:
    settings = obtener_config_jwt()
    required = {"sub", "type", "iss", "iat", "exp"}
    missing = [field for field in required if field not in claims]
    if missing:
        raise ValueError(f"missing token claims: {', '.join(missing)}")
    return jwt.encode(
        claims,
        settings["secret_key"],
        algorithm=settings["algorithm"],
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    settings = obtener_config_jwt()
    now = _utc_now()
    expire_at = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings["access_token_expire_minutes"])
    )

    to_encode = dict(data)
    if "sub" not in to_encode:
        raise ValueError("Token payload is missing subject")
    to_encode.setdefault("type", "access")
    to_encode.setdefault("iss", settings["issuer"])
    to_encode.setdefault("iat", int(now.timestamp()))
    to_encode["exp"] = int(expire_at.timestamp())
    return firmar_jwt(to_encode)


def create_refresh_token(usuario_id: int, *, now: datetime | None = None) -> str:
    claims = construir_claims_refresh(usuario_id=usuario_id, now=now)
    return firmar_jwt(claims)


def decodificar_y_validar_jwt(token: str, *, expected_type: str | None = None) -> dict:
    settings = obtener_config_jwt()
    try:
        payload = jwt.decode(
            token,
            settings["secret_key"],
            algorithms=[settings["algorithm"]],
            issuer=settings["issuer"],
            options={"verify_aud": False},
        )
    except ExpiredSignatureError as exc:
        raise ValueError("Token expired") from exc
    except JWTError as exc:
        raise ValueError("Invalid token") from exc

    token_type = str(payload.get("type", "")).strip().lower()
    if expected_type is not None and token_type != expected_type:
        raise ValueError("Invalid token type")
    if not str(payload.get("sub", "")).strip():
        raise ValueError("Token payload is missing subject")
    return payload


def decode_access_token(token: str) -> dict:
    return decodificar_y_validar_jwt(token, expected_type="access")


def decode_refresh_token(token: str) -> dict:
    return decodificar_y_validar_jwt(token, expected_type="refresh")


def parsear_sub_a_user_id(sub: object) -> int:
    raw = str(sub).strip() if sub is not None else ""
    if not raw:
        raise ValueError("Invalid token subject")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid token subject") from exc


def hash_refresh_token(token: str) -> str:
    normalized = token.strip()
    if not normalized:
        raise ValueError("refresh token is required")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
