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
