"""MercadoPago-specific payload shaping: inbound payment normalization and outbound
checkout preference construction/validation.

Split out of payment_s.py, which had grown into a god file mixing this with generic
webhook event bookkeeping and admin listing queries.
"""
from __future__ import annotations

from datetime import datetime, UTC
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

from source.db.config import (
    get_mercadopago_env,
    get_mercadopago_failure_url,
    get_mercadopago_notification_url,
    get_mercadopago_pending_url,
    get_mercadopago_success_url,
)
from source.services.mercadopago_client import create_checkout_preference
from source.services.money_s import parse_amount_to_cents

MERCADOPAGO_PROVIDER_TO_INTERNAL_STATUS = {
    "approved": "paid",
    "accredited": "paid",
    "pending": "pending",
    "in_process": "pending",
    "in_mediation": "pending",
    "authorized": "pending",
    "rejected": "cancelled",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "expired": "expired",
}
MERCADOPAGO_ALLOWED_CHECKOUT_HOSTS = {
    "www.mercadopago.com",
    "mercadopago.com",
    "www.mercadopago.com.ar",
    "mercadopago.com.ar",
    "sandbox.mercadopago.com",
    "www.sandbox.mercadopago.com",
}


def _normalize_optional_str(value: str | None) -> str | None:
    # Intentionally duplicated from payment_s._normalize_optional_str: payment_s
    # imports from this module (for checkout payload building), so importing back
    # from payment_s here would create a circular import. It's a trivial pure helper.
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


def _require_normalized_str(value: object, *, field: str, lower: bool = False) -> str:
    if value is None:
        raise ValueError(f"missing mercadopago {field}")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"missing mercadopago {field}")
    if lower:
        return normalized.lower()
    return normalized


def _to_cents_or_none(value: object, *, field: str) -> int | None:
    if value is None:
        return None
    try:
        return parse_amount_to_cents(str(value))
    except ValueError:
        raise ValueError(f"invalid mercadopago {field}") from None


def _map_mercadopago_provider_status(provider_status: str) -> str:
    normalized_status = provider_status.strip().lower()
    if not normalized_status:
        raise ValueError("provider_status is required")
    mapped = MERCADOPAGO_PROVIDER_TO_INTERNAL_STATUS.get(normalized_status)
    if mapped is None:
        raise ValueError("unsupported mercadopago provider_status")
    return mapped


def normalize_mp_payment_state(mp_payment: dict) -> dict:
    if not isinstance(mp_payment, dict):
        raise ValueError("invalid mercadopago payment payload")

    provider_payment_id = _require_normalized_str(mp_payment.get("id"), field="id")
    provider_status = _require_normalized_str(
        mp_payment.get("status"), field="status", lower=True
    )
    external_reference = _require_normalized_str(
        mp_payment.get("external_reference"),
        field="external_reference",
    )
    internal_status = _map_mercadopago_provider_status(provider_status)

    raw_currency = mp_payment.get("currency_id")
    currency = None
    if raw_currency is not None:
        currency = str(raw_currency).strip().upper() or None

    amount = _to_cents_or_none(
        mp_payment.get("transaction_amount"),
        field="transaction_amount",
    )
    payer = mp_payment.get("payer")
    payer_data = payer if isinstance(payer, dict) else {}
    transaction_details = mp_payment.get("transaction_details")
    normalized_transaction_details = (
        transaction_details if isinstance(transaction_details, dict) else {}
    )

    return {
        "provider_payment_id": provider_payment_id,
        "provider_status": provider_status,
        "provider_status_detail": mp_payment.get("status_detail"),
        "internal_status": internal_status,
        "external_reference": external_reference,
        "amount": amount,
        "currency": currency,
        "date_created": mp_payment.get("date_created"),
        "date_approved": mp_payment.get("date_approved"),
        "date_last_updated": mp_payment.get("date_last_updated"),
        "payment_method_id": mp_payment.get("payment_method_id"),
        "payment_type_id": mp_payment.get("payment_type_id"),
        "payer_id": payer_data.get("id"),
        "payer_email": payer_data.get("email"),
        "metadata": (
            mp_payment.get("metadata")
            if isinstance(mp_payment.get("metadata"), dict)
            else {}
        ),
        "additional_info": (
            mp_payment.get("additional_info")
            if isinstance(mp_payment.get("additional_info"), dict)
            else {}
        ),
        "transaction_details": normalized_transaction_details,
        "raw": mp_payment,
    }


def _get_checkout_payload(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    checkout = payload.get("checkout")
    if not isinstance(checkout, dict):
        return None
    return checkout


def _get_checkout_preference_id(payload: dict | None) -> str | None:
    checkout = _get_checkout_payload(payload)
    if checkout is None:
        return None
    return _normalize_optional_str(checkout.get("preference_id"))


def _get_checkout_external_ref(payload: dict | None) -> str | None:
    checkout = _get_checkout_payload(payload)
    if checkout is None:
        return None
    return _normalize_optional_str(checkout.get("external_ref"))


def _has_checkout_preference(payload: dict | None) -> bool:
    return _get_checkout_preference_id(payload) is not None


def _append_public_status_token_to_url(url: str, public_status_token: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["public_status_token"] = public_status_token
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query, doseq=True),
            parts.fragment,
        )
    )


def _is_allowed_mercadopago_checkout_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    normalized = hostname.strip().lower().rstrip(".")
    if not normalized:
        return False
    return normalized in MERCADOPAGO_ALLOWED_CHECKOUT_HOSTS


def normalize_and_validate_mercadopago_checkout_url(
    provider_response: dict,
    env: str,
) -> str:
    if not isinstance(provider_response, dict):
        raise ValueError("invalid mercadopago provider response")

    normalized_env = str(env or "").strip().lower()
    primary_url = (
        provider_response.get("sandbox_init_point")
        if normalized_env == "sandbox"
        else provider_response.get("init_point")
    )
    fallback_url = (
        provider_response.get("init_point")
        if normalized_env == "sandbox"
        else provider_response.get("sandbox_init_point")
    )

    for raw_url in (primary_url, fallback_url):
        if raw_url is None:
            continue
        checkout_url = str(raw_url).strip()
        if not checkout_url:
            continue
        parsed = urlparse(checkout_url)
        if parsed.scheme.lower() != "https":
            continue
        if not _is_allowed_mercadopago_checkout_host(parsed.hostname):
            continue
        return checkout_url

    raise ValueError("invalid mercadopago checkout_url")


def _build_mercadopago_payload(
    order_id: int,
    payment_id: int,
    amount: int,
    currency: str,
    expires_at: datetime,
    payment_idempotency_key: str,
    public_status_token: str,
) -> tuple[str, dict]:
    external_ref = f"mp-order-{order_id}-pay-{payment_id}"
    provider_idempotency_key = f"mp-preference-{payment_idempotency_key}"
    unit_price = int(amount) / 100
    preference_payload = {
        "external_reference": external_ref,
        "items": [
            {
                "id": str(payment_id),
                "title": f"Order #{order_id}",
                "quantity": 1,
                "currency_id": currency,
                "unit_price": unit_price,
            }
        ],
        "back_urls": {
            "success": _append_public_status_token_to_url(
                get_mercadopago_success_url(), public_status_token
            ),
            "failure": _append_public_status_token_to_url(
                get_mercadopago_failure_url(), public_status_token
            ),
            "pending": _append_public_status_token_to_url(
                get_mercadopago_pending_url(), public_status_token
            ),
        },
        "notification_url": get_mercadopago_notification_url(),
        "expires": True,
        "date_of_expiration": (
            expires_at.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        ),
        "metadata": {
            "order_id": order_id,
            "payment_id": payment_id,
            "external_ref": external_ref,
            "public_status_token": public_status_token,
            "currency": currency,
            "amount": amount,
        },
    }
    provider_response = create_checkout_preference(
        preference_payload,
        idempotency_key=provider_idempotency_key,
    )
    env = get_mercadopago_env()
    checkout_url = normalize_and_validate_mercadopago_checkout_url(provider_response, env)
    payload = {
        "checkout": {
            "provider": "mercadopago",
            "environment": env,
            "external_ref": external_ref,
            "public_status_token": public_status_token,
            "provider_idempotency_key": provider_idempotency_key,
            "preference_id": provider_response.get("id"),
            "checkout_url": checkout_url,
            "init_point": provider_response.get("init_point"),
            "sandbox_init_point": provider_response.get("sandbox_init_point"),
            "amount": amount,
            "currency": currency,
        }
    }
    return external_ref, payload
