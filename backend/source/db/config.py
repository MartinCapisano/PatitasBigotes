from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

logger = logging.getLogger(__name__)


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url and database_url.strip():
        return database_url.strip()
    raise RuntimeError("DATABASE_URL is required")


def get_app_env() -> str:
    return os.getenv("APP_ENV", "local").strip().lower() or "local"


def get_maintenance_run_token() -> str:
    token = os.getenv("MAINTENANCE_RUN_TOKEN", "").strip()
    if token:
        return token
    raise RuntimeError("MAINTENANCE_RUN_TOKEN is required")


def get_mercadopago_enabled() -> bool:
    """Whether MercadoPago may be used as a payment method.

    Defaults to disabled: MercadoPago is paused and bank transfer is the only
    online method, so an environment that forgets to declare the flag must fall
    on the safe side instead of silently accepting card payments the business
    is not ready to reconcile. Reactivating it is flipping this to true.
    """
    raw_value = os.getenv("MERCADOPAGO_ENABLED", "").strip().lower()
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"", "0", "false", "no", "off"}:
        return False
    raise RuntimeError("MERCADOPAGO_ENABLED must be a boolean value (true/false)")


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


BANK_TRANSFER_ENV_VARS = (
    "BANK_TRANSFER_ALIAS",
    "BANK_TRANSFER_CBU",
    "BANK_TRANSFER_BANK_NAME",
    "BANK_TRANSFER_HOLDER",
    "BANK_TRANSFER_CUIT",
    "WHATSAPP_NUMBER",
)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    raise RuntimeError(f"{name} is required")


def get_bank_transfer_alias() -> str:
    return _require_env("BANK_TRANSFER_ALIAS")


def get_bank_transfer_cbu() -> str:
    return _require_env("BANK_TRANSFER_CBU")


def get_bank_transfer_bank_name() -> str:
    return _require_env("BANK_TRANSFER_BANK_NAME")


def get_bank_transfer_holder() -> str:
    return _require_env("BANK_TRANSFER_HOLDER")


def get_bank_transfer_cuit() -> str:
    return _require_env("BANK_TRANSFER_CUIT")


def get_whatsapp_number() -> str:
    """The shop's WhatsApp in international digits, ready for a wa.me link.

    Accepts the way a human writes it down (`+54 9 351 123-4567`) and keeps only
    the digits, because that is the single form wa.me understands.
    """
    raw_value = _require_env("WHATSAPP_NUMBER")
    digits = "".join(char for char in raw_value if char.isdigit())
    if not digits:
        raise RuntimeError("WHATSAPP_NUMBER must contain digits")
    return digits


def validate_bank_transfer_config() -> None:
    """Fail at boot if the shop cannot be paid.

    Bank transfer is the only online payment method, so an environment missing
    these values cannot take money at all. Reporting every missing variable at
    once turns a misconfigured deploy into one fix instead of six redeploys --
    and failing here beats showing empty bank details to a customer who is
    about to send money to them.
    """
    missing = [name for name in BANK_TRANSFER_ENV_VARS if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError(
            "missing required bank transfer configuration: " + ", ".join(missing)
        )
    # Catches values that are present but unusable, e.g. a WhatsApp number with
    # no digits in it.
    get_whatsapp_number()


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
    # Browsers reject `SameSite=None` cookies that are not also `Secure`, which
    # would silently drop the auth cookie in the cross-origin production setup.
    # Fail fast instead of shipping a login that appears to work but never
    # persists the session.
    if value == "none" and not get_auth_cookie_secure():
        raise RuntimeError("AUTH_COOKIE_SAMESITE=none requires AUTH_COOKIE_SECURE=true")
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


SMTP_ENV_VARS = (
    "SMTP_HOST",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "MAIL_FROM",
)

# Los mismos entornos donde `seed_demo` se deja correr: son los que trabajan con
# datos de mentira y a los que no les importa si el mail sale. Cualquier otro
# valor -- incluido un typo -- cae del lado estricto a proposito.
EMAIL_OPTIONAL_ENVIRONMENTS = {"local", "demo"}


def validate_smtp_config() -> None:
    """Ruidoso al arrancar, silencioso en runtime.

    Los envios de email se despachan despues del commit y se tragan sus
    excepciones (`post_commit_actions_s`): un Gmail caido a las 3 AM no puede
    voltear una venta. El costo de esa decision es que una credencial revocada o
    una variable borrada en Render no producen ningun error visible -- la tienda
    funciona perfecto y nadie recibe nada.

    Este chequeo es la contraparte: un deploy sin credenciales muere en el boot,
    donde se ve en rojo al instante. En local avisa y sigue, porque ahi no tener
    SMTP es lo normal.
    """
    missing = [name for name in SMTP_ENV_VARS if not os.getenv(name, "").strip()]
    if not missing:
        return

    detail = "missing required SMTP configuration: " + ", ".join(missing)
    if get_app_env() in EMAIL_OPTIONAL_ENVIRONMENTS:
        logger.warning("event=smtp_config_incomplete detail=%s", detail)
        return
    raise RuntimeError(detail)
