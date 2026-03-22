class OrderStatusTransitionError(ValueError):
    pass


class RegisteredAccountCheckoutConflictError(ValueError):
    pass


class WebhookReplayConflictError(ValueError):
    pass
