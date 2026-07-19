from __future__ import annotations

from dataclasses import dataclass
import time

from sqlalchemy.orm import Session

from source.dependencies.mercadopago_d import (
    _extract_mercadopago_data_id,
    is_mercadopago_signature_valid,
)
from source.db.config import (
    get_mercadopago_access_token,
    get_mercadopago_timeout_seconds,
)
from source.services.payment_errors import (
    PaymentProviderAuthError,
    PaymentProviderError,
    PaymentProviderTimeoutError,
    PaymentProviderUnavailableError,
    PaymentProviderValidationError,
)

try:
    import mercadopago
    from mercadopago.config.request_options import RequestOptions
except ImportError as exc:  # pragma: no cover - dependency availability
    mercadopago = None
    RequestOptions = None
    _import_error = exc
else:
    _import_error = None

MAX_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 0.2


@dataclass(frozen=True)
class WebhookResult:
    processed: bool
    reason: str | None = None
    payment: dict | None = None


class WebhookNoOpError(Exception):
    pass


class WebhookInvalidSignatureError(Exception):
    pass


def _is_retryable_noop_error(exc: WebhookNoOpError) -> bool:
    message = str(exc or "").strip().lower()
    return message == "payment not found"


def _normalize_event_key_part(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    return normalized


def _build_mp_event_key(payload: dict, data_id: str | int) -> str:
    event_id = _normalize_event_key_part(payload.get("id"))
    if event_id is not None:
        return f"mp:event:{event_id}"

    topic = _normalize_event_key_part(payload.get("type") or payload.get("topic")) or "payment"
    action = _normalize_event_key_part(payload.get("action")) or "unknown"
    return f"mp:{topic}:{data_id}:{action}"


def _get_sdk():
    if mercadopago is None:
        raise PaymentProviderUnavailableError(
            "mercadopago SDK is not installed. Install with: pip install mercadopago"
        ) from _import_error

    return mercadopago.SDK(get_mercadopago_access_token())


def _build_request_options(
    *,
    idempotency_key: str | None = None,
) -> RequestOptions:
    if RequestOptions is None:
        raise PaymentProviderUnavailableError(
            "mercadopago SDK request options are unavailable"
        ) from _import_error
    custom_headers = None
    if idempotency_key:
        custom_headers = {"x-idempotency-key": idempotency_key}
    return RequestOptions(
        connection_timeout=float(get_mercadopago_timeout_seconds()),
        custom_headers=custom_headers,
    )


def _handle_response_status(status: int, *, operation: str) -> None:
    if status in {400, 402, 404, 409, 422}:
        raise PaymentProviderValidationError(f"mercadopago {operation} rejected")
    if status in {401, 403}:
        raise PaymentProviderAuthError("mercadopago credentials rejected")
    if status >= 400:
        raise PaymentProviderError(f"mercadopago {operation} failed")


def create_checkout_preference(
    preference_payload: dict,
    *,
    idempotency_key: str | None = None,
) -> dict:
    sdk = _get_sdk()
    request_options = _build_request_options(idempotency_key=idempotency_key)
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            response = sdk.preference().create(
                preference_payload,
                request_options=request_options,
            )
        except TimeoutError as exc:
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderTimeoutError(
                    "mercadopago request timed out"
                ) from exc
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue
        except Exception as exc:
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderUnavailableError(
                    "mercadopago request failed"
                ) from exc
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue

        status = int(response.get("status", 0))
        data = response.get("response")
        if status >= 500:
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderUnavailableError("mercadopago unavailable")
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue
        _handle_response_status(status, operation="preference creation")
        if not isinstance(data, dict):
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderUnavailableError(
                    "mercadopago invalid response payload"
                )
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue

        preference_id = data.get("id")
        init_point = data.get("init_point")
        sandbox_init_point = data.get("sandbox_init_point")
        if not preference_id:
            raise PaymentProviderValidationError("mercadopago preference id missing")
        if not init_point and not sandbox_init_point:
            raise PaymentProviderValidationError("mercadopago checkout url missing")

        return data

    raise PaymentProviderUnavailableError("mercadopago preference creation failed")


def get_payment_by_id(payment_id: str | int) -> dict:
    sdk = _get_sdk()
    payment_id_str = str(payment_id).strip()
    if not payment_id_str:
        raise PaymentProviderValidationError("mercadopago payment id is required")

    request_options = _build_request_options()
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            response = sdk.payment().get(
                payment_id_str,
                request_options=request_options,
            )
        except TimeoutError as exc:
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderTimeoutError(
                    "mercadopago request timed out"
                ) from exc
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue
        except Exception as exc:
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderUnavailableError(
                    "mercadopago request failed"
                ) from exc
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue

        status = int(response.get("status", 0))
        data = response.get("response")
        if status >= 500:
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderUnavailableError("mercadopago unavailable")
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue

        _handle_response_status(status, operation="payment lookup")
        if not isinstance(data, dict):
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderUnavailableError(
                    "mercadopago invalid response payload"
                )
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue
        return data

    raise PaymentProviderUnavailableError("mercadopago payment lookup failed")


def find_latest_payment_by_external_reference(external_reference: str) -> dict | None:
    sdk = _get_sdk()
    normalized_external_ref = str(external_reference).strip()
    if not normalized_external_ref:
        raise PaymentProviderValidationError("mercadopago external_reference is required")

    request_payload = {
        "external_reference": normalized_external_ref,
        "sort": "date_created",
        "criteria": "desc",
        "limit": 1,
    }
    request_options = _build_request_options()
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            response = sdk.payment().search(
                request_payload,
                request_options=request_options,
            )
        except TimeoutError as exc:
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderTimeoutError("mercadopago request timed out") from exc
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue
        except Exception as exc:
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderUnavailableError("mercadopago request failed") from exc
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue

        status = int(response.get("status", 0))
        data = response.get("response")
        if status >= 500:
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderUnavailableError("mercadopago unavailable")
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue

        _handle_response_status(status, operation="payment search")
        if not isinstance(data, dict):
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderUnavailableError("mercadopago invalid response payload")
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue

        results = data.get("results")
        if not isinstance(results, list) or not results:
            return None
        first = results[0]
        if not isinstance(first, dict):
            return None
        return first

    raise PaymentProviderUnavailableError("mercadopago payment search failed")


def create_refund(
    *,
    payment_id: str | int,
    amount: int | None = None,
    idempotency_key: str | None = None,
) -> dict:
    sdk = _get_sdk()
    payment_id_str = str(payment_id).strip()
    if not payment_id_str:
        raise PaymentProviderValidationError("mercadopago payment id is required")

    payload: dict = {}
    if amount is not None:
        if int(amount) <= 0:
            raise PaymentProviderValidationError("mercadopago refund amount must be greater than 0")
        payload["amount"] = float(int(amount)) / 100.0

    request_options = _build_request_options(idempotency_key=idempotency_key)
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            response = sdk.refund().create(
                payment_id_str,
                payload if payload else None,
                request_options=request_options,
            )
        except TimeoutError as exc:
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderTimeoutError("mercadopago refund request timed out") from exc
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue
        except Exception as exc:
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderUnavailableError("mercadopago refund request failed") from exc
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue

        status = int(response.get("status", 0))
        data = response.get("response")
        if status >= 500:
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderUnavailableError("mercadopago unavailable")
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue
        _handle_response_status(status, operation="refund creation")
        if not isinstance(data, dict):
            if attempt == MAX_RETRY_ATTEMPTS:
                raise PaymentProviderUnavailableError("mercadopago invalid refund response payload")
            time.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
            continue
        return data

    raise PaymentProviderUnavailableError("mercadopago refund creation failed")


def process_mercadopago_event_payload(
    *,
    payload: dict,
    data_id: str,
    db: Session,
) -> dict:
    # Local imports avoid a module cycle: mercadopago_normalization_s imports this
    # client module at module level (for create_checkout_preference).
    from source.services.mercadopago_normalization_s import normalize_mp_payment_state
    from source.services.payment_s import (
        apply_mercadopago_normalized_state,
        find_payment_for_mercadopago_event,
    )

    mp_payment = get_payment_by_id(data_id)
    normalized_state = normalize_mp_payment_state(mp_payment)
    external_ref = str(normalized_state["external_reference"])
    payment = find_payment_for_mercadopago_event(
        preference_id=None,
        external_ref=external_ref,
        db=db,
    )
    if payment is None:
        raise WebhookNoOpError("payment not found")

    return apply_mercadopago_normalized_state(
        payment_id=int(payment["id"]),
        normalized_state=normalized_state,
        notification_payload=payload,
        db=db,
    )


def resolver_evento_webhook_mercadopago(
    *,
    payload: dict,
    x_signature: str | None,
    x_request_id: str | None,
    db: Session,
) -> WebhookResult:
    if not isinstance(payload, dict):
        raise WebhookNoOpError("invalid webhook payload")

    topic = str(payload.get("type") or payload.get("topic") or "").strip().lower()
    if topic and topic not in {"payment"}:
        raise WebhookNoOpError("unsupported topic")

    data_id = _extract_mercadopago_data_id(payload)
    if data_id is None:
        raise WebhookNoOpError("missing data.id")

    is_signature_valid = is_mercadopago_signature_valid(
        data_id=data_id,
        request_id=x_request_id,
        signature_header=x_signature,
    )
    if not is_signature_valid:
        raise WebhookInvalidSignatureError("invalid signature")

    event_key = _build_mp_event_key(payload, data_id)

    from source.services.webhook_events_s import (
        acquire_webhook_event,
        mark_webhook_event_failed,
        mark_webhook_event_processed,
    )

    acquired = acquire_webhook_event(
        provider="mercadopago",
        event_key=event_key,
        payload=payload,
        db=db,
    )
    if not acquired:
        raise WebhookNoOpError("duplicate webhook event")

    try:
        updated_payment = process_mercadopago_event_payload(
            payload=payload,
            data_id=data_id,
            db=db,
        )
    except WebhookNoOpError as exc:
        if _is_retryable_noop_error(exc):
            mark_webhook_event_failed(
                provider="mercadopago",
                event_key=event_key,
                error_message=str(exc),
                db=db,
            )
        else:
            mark_webhook_event_processed(
                provider="mercadopago",
                event_key=event_key,
                db=db,
            )
        raise
    except Exception as exc:
        mark_webhook_event_failed(
            provider="mercadopago",
            event_key=event_key,
            error_message=str(exc),
            db=db,
        )
        raise

    mark_webhook_event_processed(
        provider="mercadopago",
        event_key=event_key,
        db=db,
    )
    return WebhookResult(processed=True, payment=updated_payment)
