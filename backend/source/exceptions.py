class OrderStatusTransitionError(ValueError):
    pass


class PaymentRetryConflictError(ValueError):
    pass


class PaymentMethodDisabledError(ValueError):
    """A payment method that exists in the code but is switched off by configuration."""


class RegisteredAccountCheckoutConflictError(ValueError):
    pass


class WebhookReplayConflictError(ValueError):
    pass


class CategoryHasProductsError(ValueError):
    pass


class EmailAlreadyExistsError(ValueError):
    """An account already exists for the given email."""


class UserNotAdminError(ValueError):
    """An admin-only operation targeted a user that is not an admin."""


class ContactDataMismatchError(ValueError):
    """Contact data provided does not match the existing user for that email."""


class RateLimitExceededError(Exception):
    """An anti-abuse rate limit was hit. Maps to HTTP 429. Not a ValueError:
    it is not a validation error and must not be swallowed by the 400 branch."""
