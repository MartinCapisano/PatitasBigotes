class OrderStatusTransitionError(ValueError):
    pass


class PaymentRetryConflictError(ValueError):
    pass


class RegisteredAccountCheckoutConflictError(ValueError):
    pass


class WebhookReplayConflictError(ValueError):
    pass


class CategoryHasProductsError(ValueError):
    pass
