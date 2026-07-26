"""T-08 — Matriz de flags del snapshot público.

Ejercita el núcleo de decisión puro de `orders_public_s` (`_evaluate_public_snapshot`
y `_select_relevant_payment`) sin HTTP ni sesión de base: los `Payment` son
instancias transitorias del modelo. La red HTTP de `test_payments_fundamentals.py`
cubre el cableado end-to-end; acá cubrimos la combinatoria de estados que allá
sería carísima de montar caso por caso.
"""
import json
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Payment
from source.services.orders_public_s import (
    PublicSnapshotDecision,
    _evaluate_public_snapshot,
    _select_relevant_payment,
)

_ALLOWED_CHECKOUT_URL = (
    "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-matrix"
)


def _mp_payment(
    *,
    payment_id: int = 1,
    status: str = "pending",
    method: str = "mercadopago",
    checkout_url: str | None = None,
) -> Payment:
    """Un `Payment` transitorio (sin sesión). Si se pasa `checkout_url`, se
    serializa en el `provider_payload` con la forma que espera el extractor."""
    provider_payload = None
    if checkout_url is not None:
        provider_payload = json.dumps({"checkout": {"checkout_url": checkout_url}})
    return Payment(
        id=payment_id,
        status=status,
        method=method,
        amount=1000,
        currency="ARS",
        provider_payload=provider_payload,
    )


def _evaluate(
    *,
    order_status: str,
    token_payment_status: str,
    relevant_payment: Payment,
    mercadopago_payments: list[Payment] | None = None,
    has_stock_reservation_expired: bool = False,
) -> PublicSnapshotDecision:
    from source.services.orders_public_s import _extract_public_checkout_url

    payments = mercadopago_payments if mercadopago_payments is not None else [relevant_payment]
    return _evaluate_public_snapshot(
        order_status=order_status,
        token_payment_status=token_payment_status,
        relevant_payment=relevant_payment,
        relevant_checkout_url=_extract_public_checkout_url(relevant_payment),
        mercadopago_payments=payments,
        has_stock_reservation_expired=has_stock_reservation_expired,
    )


class SelectRelevantPaymentTests(unittest.TestCase):
    def test_prefers_pending_over_everything(self) -> None:
        cancelled = _mp_payment(payment_id=1, status="cancelled")
        pending = _mp_payment(payment_id=2, status="pending")
        token = cancelled
        selected = _select_relevant_payment([pending, cancelled], token_payment=token)
        self.assertEqual(int(selected.id), 2)

    def test_falls_back_to_token_payment_when_no_pending(self) -> None:
        token = _mp_payment(payment_id=5, status="cancelled")
        other = _mp_payment(payment_id=9, status="expired")
        selected = _select_relevant_payment([other, token], token_payment=token)
        self.assertEqual(int(selected.id), 5)

    def test_falls_back_to_first_when_token_absent_from_list(self) -> None:
        first = _mp_payment(payment_id=9, status="expired")
        second = _mp_payment(payment_id=8, status="cancelled")
        token = _mp_payment(payment_id=99, status="cancelled")
        selected = _select_relevant_payment([first, second], token_payment=token)
        self.assertEqual(int(selected.id), 9)


class EvaluatePublicSnapshotTests(unittest.TestCase):
    def test_pending_with_checkout_can_continue(self) -> None:
        payment = _mp_payment(status="pending", checkout_url=_ALLOWED_CHECKOUT_URL)
        decision = _evaluate(
            order_status="submitted",
            token_payment_status="pending",
            relevant_payment=payment,
        )
        self.assertTrue(decision.can_continue_payment)
        self.assertFalse(decision.can_retry_payment)
        self.assertTrue(decision.is_order_open)
        self.assertFalse(decision.is_payment_terminal)
        self.assertIsNone(decision.blocking_reason)

    def test_pending_without_checkout_is_blocked_unavailable(self) -> None:
        payment = _mp_payment(status="pending", checkout_url=None)
        decision = _evaluate(
            order_status="submitted",
            token_payment_status="pending",
            relevant_payment=payment,
        )
        self.assertFalse(decision.can_continue_payment)
        self.assertFalse(decision.can_retry_payment)
        self.assertEqual(decision.blocking_reason, "checkout_unavailable")

    def test_cancelled_payment_on_open_order_can_retry(self) -> None:
        payment = _mp_payment(status="cancelled")
        decision = _evaluate(
            order_status="submitted",
            token_payment_status="cancelled",
            relevant_payment=payment,
        )
        self.assertFalse(decision.can_continue_payment)
        self.assertTrue(decision.can_retry_payment)
        self.assertTrue(decision.is_payment_terminal)
        self.assertIsNone(decision.blocking_reason)

    def test_expired_token_payment_on_open_order_can_retry(self) -> None:
        payment = _mp_payment(status="expired")
        decision = _evaluate(
            order_status="submitted",
            token_payment_status="expired",
            relevant_payment=payment,
        )
        self.assertTrue(decision.can_retry_payment)
        self.assertTrue(decision.is_payment_terminal)
        self.assertIsNone(decision.blocking_reason)

    def test_cancelled_token_but_live_pending_attempt_blocks_retry(self) -> None:
        # El token apunta a un intento cancelado, pero ya existe un intento
        # pendiente continuable: no se debe ofrecer reintentar.
        pending = _mp_payment(payment_id=2, status="pending", checkout_url=_ALLOWED_CHECKOUT_URL)
        cancelled = _mp_payment(payment_id=1, status="cancelled")
        decision = _evaluate(
            order_status="submitted",
            token_payment_status="cancelled",
            relevant_payment=pending,
            mercadopago_payments=[pending, cancelled],
        )
        self.assertTrue(decision.can_continue_payment)
        self.assertFalse(decision.can_retry_payment)
        self.assertIsNone(decision.blocking_reason)

    def test_paid_order_is_blocked_order_paid(self) -> None:
        payment = _mp_payment(status="paid")
        decision = _evaluate(
            order_status="paid",
            token_payment_status="paid",
            relevant_payment=payment,
        )
        self.assertFalse(decision.can_continue_payment)
        self.assertFalse(decision.can_retry_payment)
        self.assertFalse(decision.is_order_open)
        self.assertTrue(decision.is_payment_terminal)
        self.assertEqual(decision.blocking_reason, "order_paid")

    def test_cancelled_order_without_expired_reservation_is_order_cancelled(self) -> None:
        payment = _mp_payment(status="cancelled")
        decision = _evaluate(
            order_status="cancelled",
            token_payment_status="cancelled",
            relevant_payment=payment,
            has_stock_reservation_expired=False,
        )
        self.assertEqual(decision.blocking_reason, "order_cancelled")

    def test_cancelled_order_with_expired_reservation_reports_reservation(self) -> None:
        payment = _mp_payment(status="cancelled")
        decision = _evaluate(
            order_status="cancelled",
            token_payment_status="cancelled",
            relevant_payment=payment,
            has_stock_reservation_expired=True,
        )
        self.assertEqual(decision.blocking_reason, "stock_reservation_expired")

    def test_open_order_relevant_pending_no_checkout_reports_unavailable(self) -> None:
        # Orden abierta, pago pendiente sin checkout y token no reintentable:
        # no continúa (sin URL) ni reintenta -> checkout no disponible.
        decision = _evaluate(
            order_status="submitted",
            token_payment_status="paid",  # no reintentable
            relevant_payment=_mp_payment(status="pending", checkout_url=None),
        )
        self.assertFalse(decision.can_continue_payment)
        self.assertFalse(decision.can_retry_payment)
        self.assertEqual(decision.blocking_reason, "checkout_unavailable")

    def test_non_open_order_pending_with_checkout_reports_payment_pending(self) -> None:
        # Pago pendiente con checkout válido pero la orden no está abierta
        # (ni paid ni cancelled): no se puede continuar por el estado de la
        # orden, y el motivo cae en payment_pending.
        payment = _mp_payment(status="pending", checkout_url=_ALLOWED_CHECKOUT_URL)
        decision = _evaluate(
            order_status="draft",
            token_payment_status="pending",
            relevant_payment=payment,
        )
        self.assertFalse(decision.can_continue_payment)
        self.assertFalse(decision.can_retry_payment)
        self.assertFalse(decision.is_order_open)
        self.assertEqual(decision.blocking_reason, "payment_pending")

    def test_terminal_payment_not_retryable_default_reason(self) -> None:
        # Orden abierta, pago del token pagado (no reintentable), relevant paid.
        payment = _mp_payment(status="paid")
        decision = _evaluate(
            order_status="submitted",
            token_payment_status="paid",
            relevant_payment=payment,
        )
        self.assertFalse(decision.can_continue_payment)
        self.assertFalse(decision.can_retry_payment)
        self.assertTrue(decision.is_order_open)
        self.assertEqual(decision.blocking_reason, "payment_not_retryable")


if __name__ == "__main__":
    unittest.main()
