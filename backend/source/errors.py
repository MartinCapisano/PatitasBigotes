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
    # Log exception details to aid debugging
    logger.exception("Exception routed to HTTP error handler: %s", exc)

    # If the exception is already an HTTPException, re-raise it unchanged.
    if isinstance(exc, HTTPException):
        raise exc from exc

    if db is not None and isinstance(exc, (IntegrityError, SQLAlchemyError)):
        db.rollback()

    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, OrderStatusTransitionError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, PaymentRetryConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, RegisteredAccountCheckoutConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, WebhookReplayConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, CategoryHasProductsError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Listed before the generic ValueError branch so the status stays 400 on purpose
    # rather than by accident of ordering.
    if isinstance(exc, PaymentMethodDisabledError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, PaymentProviderValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, PaymentCheckoutInitializationError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, PaymentProviderAuthError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, PaymentProviderTimeoutError):
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    if isinstance(exc, PaymentProviderUnavailableError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, IntegrityError):
        raise HTTPException(
            status_code=409,
            detail="database constraint violation",
        ) from exc
    if isinstance(exc, SQLAlchemyError):
        raise HTTPException(
            status_code=500,
            detail="database error",
        ) from exc

    raise HTTPException(status_code=500, detail="internal server error") from exc
