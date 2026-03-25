import sys
import unittest
from datetime import datetime, timedelta, UTC
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import (
    Base,
    Order,
    Payment,
    PaymentIncident,
    StockReservation,
)
from source.services.payment_s import (
    _build_mercadopago_payload,
    apply_mercadopago_normalized_state,
    create_payment_for_order,
)
from tests.factories.orders import create_order_graph
from tests.factories.users import create_user


class PaymentsMoneyConsistencyTests(unittest.TestCase):
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

    def _seed_submitted_order_with_reservation(self) -> tuple[int, int]:
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
            )
            session.commit()
            return int(graph["order_id"]), int(user.id)
        finally:
            session.close()

    def test_create_payment_uses_exact_order_total(self) -> None:
        order_id, user_id = self._seed_submitted_order_with_reservation()
        session = self.TestSession()
        try:
            payment = create_payment_for_order(
                order_id=order_id,
                method="bank_transfer",
                db=session,
                user_id=user_id,
                idempotency_key=f"idemp-{datetime.now(UTC).timestamp()}",
                currency="ARS",
            )
            session.commit()
        finally:
            session.close()
        self.assertEqual(payment["amount"], 10000)
        self.assertIn("provider_payload_data", payment)
        self.assertIsInstance(payment["provider_payload_data"], dict)

    def test_create_cash_payment_has_no_expiration(self) -> None:
        order_id, user_id = self._seed_submitted_order_with_reservation()
        session = self.TestSession()
        try:
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
        self.assertEqual(payment["status"], "pending")
        self.assertIsNone(payment["expires_at"])

    def test_build_mercadopago_payload_rejects_invalid_checkout_url(self) -> None:
        with patch(
            "source.services.payment_s.create_checkout_preference",
            return_value={
                "id": "pref-invalid",
                "init_point": "https://evil.example.com/pay?pref_id=pref-invalid",
            },
        ):
            with self.assertRaises(ValueError) as ctx:
                _build_mercadopago_payload(
                    order_id=10,
                    payment_id=20,
                    amount=10000,
                    currency="ARS",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                    payment_idempotency_key="idemp-test",
                    public_status_token="public-status-token-test",
                )
        self.assertEqual(str(ctx.exception), "invalid mercadopago checkout_url")

    def test_webhook_amount_mismatch_raises(self) -> None:
        order_id, _ = self._seed_submitted_order_with_reservation()
        session = self.TestSession()
        try:
            payment = Payment(
                order_id=order_id,
                method="mercadopago",
                status="pending",
                amount=10000,
                currency="ARS",
                idempotency_key=f"idemp-mp-{datetime.now(UTC).timestamp()}",
                external_ref=f"mp-order-{order_id}-pay-1",
                provider_status="preference_created",
                provider_payload=None,
                receipt_url=None,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                paid_at=None,
            )
            session.add(payment)
            session.flush()
            with self.assertRaises(ValueError):
                apply_mercadopago_normalized_state(
                    payment_id=int(payment.id),
                    normalized_state={
                        "provider_status": "approved",
                        "internal_status": "paid",
                        "external_reference": payment.external_ref,
                        "amount": 10001,
                        "currency": "ARS",
                        "provider_payment_id": "123",
                    },
                    db=session,
                )
        finally:
            session.close()

    def test_webhook_cancelled_payment_does_not_cancel_order(self) -> None:
        order_id, user_id = self._seed_submitted_order_with_reservation()
        session = self.TestSession()
        try:
            payment = Payment(
                order_id=order_id,
                method="mercadopago",
                status="pending",
                amount=10000,
                currency="ARS",
                idempotency_key=f"idemp-mp-cancel-{datetime.now(UTC).timestamp()}",
                external_ref=f"mp-order-{order_id}-pay-1",
                provider_status="preference_created",
                provider_payload=None,
                receipt_url=None,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                paid_at=None,
            )
            session.add(payment)
            session.flush()

            updated = apply_mercadopago_normalized_state(
                payment_id=int(payment.id),
                normalized_state={
                    "provider_status": "cancelled",
                    "internal_status": "cancelled",
                    "external_reference": payment.external_ref,
                    "amount": 10000,
                    "currency": "ARS",
                    "provider_payment_id": "321",
                },
                db=session,
            )

            order = session.query(Order).filter(Order.id == order_id).first()
            reservation = (
                session.query(StockReservation)
                .filter(
                    StockReservation.order_id == order_id,
                    StockReservation.status == "active",
                )
                .first()
            )
        finally:
            session.close()

        self.assertEqual(updated["status"], "cancelled")
        self.assertIsNotNone(order)
        self.assertEqual(order.status, "submitted")
        self.assertIsNotNone(reservation)

    def test_webhook_paid_on_cancelled_order_creates_incident_and_keeps_order_cancelled(self) -> None:
        order_id, _ = self._seed_submitted_order_with_reservation()
        session = self.TestSession()
        try:
            order = session.query(Order).filter(Order.id == order_id).first()
            assert order is not None
            order.status = "cancelled"
            order.cancelled_at = datetime.now(UTC)

            payment = Payment(
                order_id=order_id,
                method="mercadopago",
                status="pending",
                amount=10000,
                currency="ARS",
                idempotency_key=f"idemp-mp-late-cancel-{datetime.now(UTC).timestamp()}",
                external_ref=f"mp-order-{order_id}-pay-late-cancel",
                provider_status="preference_created",
                provider_payload=None,
                receipt_url=None,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                paid_at=None,
            )
            session.add(payment)
            session.flush()

            updated = apply_mercadopago_normalized_state(
                payment_id=int(payment.id),
                normalized_state={
                    "provider_status": "approved",
                    "internal_status": "paid",
                    "external_reference": payment.external_ref,
                    "amount": 10000,
                    "currency": "ARS",
                    "provider_payment_id": "444",
                },
                db=session,
            )
            incidents = (
                session.query(PaymentIncident)
                .filter(PaymentIncident.payment_id == int(payment.id))
                .all()
            )
        finally:
            session.close()

        self.assertEqual(updated["status"], "paid")
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].status, "pending_review")

    def test_webhook_paid_on_already_paid_order_creates_duplicate_incident(self) -> None:
        order_id, user_id = self._seed_submitted_order_with_reservation()
        session = self.TestSession()
        try:
            order = session.query(Order).filter(Order.id == order_id).first()
            assert order is not None
            existing_paid = Payment(
                order_id=order_id,
                method="cash",
                status="paid",
                amount=10000,
                currency="ARS",
                idempotency_key=f"idemp-paid-existing-{datetime.now(UTC).timestamp()}",
                external_ref=f"cash-ref-{order_id}",
                provider_status="manual_confirmed",
                provider_payload=None,
                receipt_url=None,
                expires_at=None,
                paid_at=datetime.now(UTC),
            )
            session.add(existing_paid)
            order.status = "paid"
            order.paid_at = datetime.now(UTC)

            late_payment = Payment(
                order_id=order_id,
                method="mercadopago",
                status="pending",
                amount=10000,
                currency="ARS",
                idempotency_key=f"idemp-late-{datetime.now(UTC).timestamp()}",
                external_ref=f"mp-order-{order_id}-pay-late",
                provider_status="preference_created",
                provider_payload=None,
                receipt_url=None,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                paid_at=None,
            )
            session.add(late_payment)
            session.flush()

            updated = apply_mercadopago_normalized_state(
                payment_id=int(late_payment.id),
                normalized_state={
                    "provider_status": "approved",
                    "internal_status": "paid",
                    "external_reference": late_payment.external_ref,
                    "amount": 10000,
                    "currency": "ARS",
                    "provider_payment_id": "555",
                },
                db=session,
            )
            incidents = (
                session.query(PaymentIncident)
                .filter(PaymentIncident.payment_id == int(late_payment.id))
                .all()
            )
            self.assertEqual(updated["status"], "paid")
            self.assertEqual(order.status, "paid")
            self.assertEqual(len(incidents), 1)
            self.assertEqual(incidents[0].status, "pending_review")
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()

