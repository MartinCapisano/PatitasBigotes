"""The MercadoPago pause, tested as a server-side lock.

Hiding the option in the checkout is not a lock: these tests go through the
service layer directly, the way a client calling the API by hand would, and
assert that nothing is persisted and the provider is never contacted.
"""
import os
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db import config
from source.db.models import Base, Payment
from source.exceptions import PaymentMethodDisabledError
from source.services.payment_provider_s import (
    initialize_mercadopago_checkout_for_payment,
)
from source.services.payment_s import (
    create_payment_for_order,
    create_retry_payment_for_order,
)
from tests.factories.orders import create_order_graph
from tests.factories.users import create_user


def mercadopago_disabled():
    return patch.dict(os.environ, {"MERCADOPAGO_ENABLED": "false"})


class MercadoPagoDisabledLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine("sqlite:///:memory:")
        cls.TestSession = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=cls.engine,
        )
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def _seed_submitted_order(self, **graph_kwargs) -> tuple[int, int]:
        session = self.TestSession()
        try:
            user = create_user(
                session,
                first_name="Jane",
                last_name="Doe",
                email_prefix="jane",
                has_account=False,
            )
            graph = create_order_graph(
                session,
                user_id=int(user.id),
                order_status="submitted",
                variant_stock=5,
                with_reservation=True,
                **graph_kwargs,
            )
            session.commit()
            return int(graph["order_id"]), int(user.id)
        finally:
            session.close()

    def _count_payments(self) -> int:
        session = self.TestSession()
        try:
            return session.query(Payment).count()
        finally:
            session.close()

    def test_checkout_rejects_mercadopago_when_disabled(self) -> None:
        order_id, user_id = self._seed_submitted_order()
        session = self.TestSession()
        try:
            with mercadopago_disabled():
                with self.assertRaises(PaymentMethodDisabledError) as ctx:
                    create_payment_for_order(
                        order_id=order_id,
                        method="mercadopago",
                        db=session,
                        user_id=user_id,
                        idempotency_key="idemp-mp-disabled",
                        currency="ARS",
                    )
            session.commit()
        finally:
            session.close()

        self.assertIn("mercadopago", str(ctx.exception))
        self.assertEqual(self._count_payments(), 0)

    def test_disabled_checkout_never_reaches_the_provider(self) -> None:
        """The rejection happens before any preference is requested, not after."""
        order_id, user_id = self._seed_submitted_order()
        session = self.TestSession()
        try:
            with patch(
                "source.services.mercadopago_normalization_s.create_checkout_preference"
            ) as create_preference:
                with mercadopago_disabled():
                    with self.assertRaises(PaymentMethodDisabledError):
                        create_payment_for_order(
                            order_id=order_id,
                            method="mercadopago",
                            db=session,
                            user_id=user_id,
                            idempotency_key="idemp-mp-no-provider",
                            currency="ARS",
                        )
            session.commit()
        finally:
            session.close()

        create_preference.assert_not_called()

    def test_retry_rejects_mercadopago_when_disabled(self) -> None:
        order_id, user_id = self._seed_submitted_order(
            add_pending_payment=True,
            payment_method="mercadopago",
            payment_status="cancelled",
        )
        session = self.TestSession()
        try:
            with mercadopago_disabled():
                with self.assertRaises(PaymentMethodDisabledError):
                    create_retry_payment_for_order(
                        order_id=order_id,
                        method="mercadopago",
                        db=session,
                        user_id=user_id,
                        idempotency_key="idemp-mp-retry-disabled",
                        currency="ARS",
                    )
            session.commit()
        finally:
            session.close()

        # Only the seeded attempt survives: the retry created nothing.
        self.assertEqual(self._count_payments(), 1)

    def test_resuming_a_pre_pause_checkout_is_rejected(self) -> None:
        """A payment created before the pause cannot be resumed from "continuar pago"."""
        order_id, _ = self._seed_submitted_order(
            add_pending_payment=True,
            payment_method="mercadopago",
            payment_status="pending",
        )
        session = self.TestSession()
        try:
            payment = (
                session.query(Payment)
                .filter(Payment.order_id == order_id)
                .one()
            )
            with mercadopago_disabled():
                with self.assertRaises(PaymentMethodDisabledError):
                    initialize_mercadopago_checkout_for_payment(
                        payment_id=int(payment.id),
                        db=session,
                    )
        finally:
            session.close()

    def test_bank_transfer_still_works_while_mercadopago_is_disabled(self) -> None:
        order_id, user_id = self._seed_submitted_order()
        session = self.TestSession()
        try:
            with mercadopago_disabled():
                payment = create_payment_for_order(
                    order_id=order_id,
                    method="bank_transfer",
                    db=session,
                    user_id=user_id,
                    idempotency_key=f"idemp-bt-{datetime.now(UTC).timestamp()}",
                    currency="ARS",
                )
            session.commit()
        finally:
            session.close()

        self.assertEqual(payment["method"], "bank_transfer")
        self.assertEqual(payment["status"], "pending")

    def test_cash_still_works_while_mercadopago_is_disabled(self) -> None:
        order_id, user_id = self._seed_submitted_order()
        session = self.TestSession()
        try:
            with mercadopago_disabled():
                payment = create_payment_for_order(
                    order_id=order_id,
                    method="cash",
                    db=session,
                    user_id=user_id,
                    idempotency_key=f"idemp-cash-{datetime.now(UTC).timestamp()}",
                    currency="ARS",
                )
            session.commit()
        finally:
            session.close()

        self.assertEqual(payment["method"], "cash")


class MercadoPagoEnabledFlagTests(unittest.TestCase):
    def test_defaults_to_disabled_when_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MERCADOPAGO_ENABLED", None)
            self.assertFalse(config.get_mercadopago_enabled())

    def test_accepts_the_usual_truthy_spellings(self) -> None:
        for raw_value in ("1", "true", "TRUE", " yes ", "on"):
            with self.subTest(raw_value=raw_value):
                with patch.dict(os.environ, {"MERCADOPAGO_ENABLED": raw_value}):
                    self.assertTrue(config.get_mercadopago_enabled())

    def test_accepts_the_usual_falsy_spellings(self) -> None:
        for raw_value in ("0", "false", "FALSE", " no ", "off", ""):
            with self.subTest(raw_value=raw_value):
                with patch.dict(os.environ, {"MERCADOPAGO_ENABLED": raw_value}):
                    self.assertFalse(config.get_mercadopago_enabled())

    def test_rejects_a_value_that_is_not_a_boolean(self) -> None:
        """A typo must be loud: silently guessing either way is worse."""
        with patch.dict(os.environ, {"MERCADOPAGO_ENABLED": "tru"}):
            with self.assertRaises(RuntimeError):
                config.get_mercadopago_enabled()


if __name__ == "__main__":
    unittest.main()
