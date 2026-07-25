from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from source.exceptions import (
    CategoryHasProductsError,
    OrderStatusTransitionError,
    PaymentMethodDisabledError,
    PaymentRetryConflictError,
    RegisteredAccountCheckoutConflictError,
    WebhookReplayConflictError,
)
from source.services.payment_errors import (
    PaymentCheckoutInitializationError,
    PaymentProviderAuthError,
    PaymentProviderTimeoutError,
    PaymentProviderUnavailableError,
    PaymentProviderValidationError,
)


import logging
logger = logging.getLogger(__name__)

def raise_http_error_from_exception(exc: Exception, db: Session | None = None) -> None:
    # If the exception is already an HTTPException, re-raise it unchanged.
    # It represents a decision already taken by the caller, not an error to diagnose,
    # so it is passed through without logging a stack trace.
    if isinstance(exc, HTTPException):
        raise exc from exc

    if db is not None and isinstance(exc, (IntegrityError, SQLAlchemyError)):
        db.rollback()

    # Business-expected exceptions (4xx). These are the normal outcome of a request
    # that broke a business rule, not a bug, so they are logged at INFO without a
    # stack trace: piling `logger.exception` on every rejected transition or missing
    # resource drowns the logs in noise and hides the errors that do matter.
    if isinstance(exc, LookupError):
        logger.info("event=business_error status=404 detail=%s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, OrderStatusTransitionError):
        logger.info("event=business_error status=409 detail=%s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, PaymentRetryConflictError):
        logger.info("event=business_error status=409 detail=%s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, RegisteredAccountCheckoutConflictError):
        logger.info("event=business_error status=409 detail=%s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, WebhookReplayConflictError):
        logger.info("event=business_error status=409 detail=%s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, CategoryHasProductsError):
        logger.info("event=business_error status=409 detail=%s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Listed before the generic ValueError branch so the status stays 400 on purpose
    # rather than by accident of ordering.
    if isinstance(exc, PaymentMethodDisabledError):
        logger.info("event=business_error status=400 detail=%s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        logger.info("event=business_error status=400 detail=%s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, PaymentProviderValidationError):
        logger.info("event=business_error status=400 detail=%s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Provider infrastructure failures (5xx from an upstream we called). Expected in
    # the sense that a third party can be down; logged at WARNING (no stack trace,
    # since the interesting part is which provider failed, not our call stack).
    if isinstance(exc, PaymentCheckoutInitializationError):
        logger.warning("event=provider_error status=502 detail=%s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, PaymentProviderAuthError):
        logger.warning("event=provider_error status=502 detail=%s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, PaymentProviderTimeoutError):
        logger.warning("event=provider_error status=504 detail=%s", exc)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    if isinstance(exc, PaymentProviderUnavailableError):
        logger.warning("event=provider_error status=503 detail=%s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Genuinely unexpected: a database failure or an exception we did not map. These
    # keep the full stack trace via logger.exception -- this is exactly what stack
    # traces are for.
    if isinstance(exc, IntegrityError):
        logger.exception("event=unexpected_error status=409 exc=%s", exc)
        raise HTTPException(
            status_code=409,
            detail="database constraint violation",
        ) from exc
    if isinstance(exc, SQLAlchemyError):
        logger.exception("event=unexpected_error status=500 exc=%s", exc)
        raise HTTPException(
            status_code=500,
            detail="database error",
        ) from exc

    logger.exception("event=unexpected_error status=500 exc=%s", exc)
    raise HTTPException(status_code=500, detail="internal server error") from exc
