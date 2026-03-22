from __future__ import annotations


class PaymentProviderError(Exception):
    """Base error for upstream payment provider failures."""


class PaymentProviderTimeoutError(PaymentProviderError):
    """Provider request timed out or had a transient network error."""


class PaymentProviderValidationError(PaymentProviderError):
    """Provider rejected request payload or business constraints."""


class PaymentProviderAuthError(PaymentProviderError):
    """Provider credentials are invalid or not authorized."""


class PaymentProviderUnavailableError(PaymentProviderError):
    """Provider service is unavailable or dependency is missing."""


class PaymentCheckoutInitializationError(PaymentProviderError):
    """Local payment was persisted but checkout initialization failed."""
