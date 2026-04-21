from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH)


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url and database_url.strip():
        return database_url.strip()
    raise RuntimeError("DATABASE_URL is required")


def get_mercadopago_access_token() -> str:
    access_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if access_token:
        return access_token
    raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN is required")


def get_mercadopago_env() -> str:
    env = os.getenv("MERCADOPAGO_ENV", "sandbox").strip().lower()
    if env not in {"sandbox", "production"}:
        raise RuntimeError("MERCADOPAGO_ENV must be 'sandbox' or 'production'")
    return env


def get_mercadopago_timeout_seconds() -> int:
    raw_timeout = os.getenv("MERCADOPAGO_TIMEOUT_SECONDS", "10").strip()
    timeout = int(raw_timeout)
    if timeout <= 0:
        raise RuntimeError("MERCADOPAGO_TIMEOUT_SECONDS must be greater than 0")
    return timeout


def get_mercadopago_success_url() -> str:
    return os.getenv(
        "MERCADOPAGO_SUCCESS_URL",
        "http://localhost:8000/payments/success",
    ).strip()


def get_mercadopago_failure_url() -> str:
    return os.getenv(
        "MERCADOPAGO_FAILURE_URL",
        "http://localhost:8000/payments/failure",
    ).strip()


def get_mercadopago_pending_url() -> str:
    return os.getenv(
        "MERCADOPAGO_PENDING_URL",
        "http://localhost:8000/payments/pending",
    ).strip()


def get_mercadopago_notification_url() -> str:
    return os.getenv(
        "MERCADOPAGO_NOTIFICATION_URL",
        "http://localhost:8000/payments/webhook/mercadopago",
    ).strip()


def get_mercadopago_webhook_token() -> str:
    return os.getenv("MERCADOPAGO_WEBHOOK_TOKEN", "").strip()


def get_mercadopago_webhook_secret() -> str:
    secret = os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "").strip()
    if secret:
        return secret
    raise RuntimeError("MERCADOPAGO_WEBHOOK_SECRET is required")


def get_mercadopago_webhook_max_age_seconds() -> int:
    raw_value = os.getenv("MERCADOPAGO_WEBHOOK_MAX_AGE_SECONDS", "300").strip()
    max_age = int(raw_value)
    if max_age <= 0:
        raise RuntimeError("MERCADOPAGO_WEBHOOK_MAX_AGE_SECONDS must be greater than 0")
    return max_age


def get_app_base_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:5173").strip().rstrip("/")


def get_cors_allow_origins() -> list[str]:
    raw_origins = os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip().rstrip("/") for origin in raw_origins.split(",") if origin.strip()]


def get_auth_cookie_access_name() -> str:
    return os.getenv("AUTH_COOKIE_ACCESS_NAME", "pb_at").strip() or "pb_at"


def get_auth_cookie_refresh_name() -> str:
    return os.getenv("AUTH_COOKIE_REFRESH_NAME", "pb_rt").strip() or "pb_rt"


def get_auth_cookie_samesite() -> str:
    value = os.getenv("AUTH_COOKIE_SAMESITE", "lax").strip().lower()
    if value not in {"lax", "strict", "none"}:
        raise RuntimeError("AUTH_COOKIE_SAMESITE must be one of: lax, strict, none")
    return value


def get_auth_cookie_secure() -> bool:
    raw = os.getenv("AUTH_COOKIE_SECURE", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    app_base_url = get_app_base_url()
    parsed = urlparse(app_base_url)
    return parsed.scheme.lower() == "https"


def get_auth_cookie_domain() -> str | None:
    value = os.getenv("AUTH_COOKIE_DOMAIN", "").strip()
    return value or None


def get_auth_cookie_path_access() -> str:
    return os.getenv("AUTH_COOKIE_PATH_ACCESS", "/").strip() or "/"


def get_auth_cookie_path_refresh() -> str:
    return os.getenv("AUTH_COOKIE_PATH_REFRESH", "/auth").strip() or "/auth"


def get_smtp_host() -> str:
    host = os.getenv("SMTP_HOST", "").strip()
    if host:
        return host
    raise RuntimeError("SMTP_HOST is required")


def get_smtp_port() -> int:
    raw_value = os.getenv("SMTP_PORT", "587").strip()
    port = int(raw_value)
    if port <= 0:
        raise RuntimeError("SMTP_PORT must be greater than 0")
    return port


def get_smtp_username() -> str:
    return os.getenv("SMTP_USERNAME", "").strip()


def get_smtp_password() -> str:
    return os.getenv("SMTP_PASSWORD", "").strip()


def get_smtp_use_tls() -> bool:
    raw_value = os.getenv("SMTP_USE_TLS", "true").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def get_mail_from() -> str:
    value = os.getenv("MAIL_FROM", "").strip()
    if value:
        return value
    raise RuntimeError("MAIL_FROM is required")
