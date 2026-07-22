"""Coming back to the transfer link after closing the tab.

A guest has no account, so this token is the only way back to their own
instructions. The tests care about two things: that the right person gets their
data, and that nobody is invited to transfer for an order that can no longer
take the money.
"""
import os
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base, Order, Payment, StockReservation
from source.services.bank_transfer_s import get_public_bank_transfer_status
from source.services.payment_s import create_payment_for_order
from tests.factories.orders import create_order_graph
from tests.factories.users import create_user

SHOP_CONFIG = {
    "BANK_TRANSFER_ALIAS": "patitas.bigotes.real",
    "BANK_TRANSFER_CBU": "0110599520000012345678",
    "BANK_TRANSFER_BANK_NAME": "Banco Nacion",
    "BANK_TRANSFER_HOLDER": "Martin Capisano",
    "BANK_TRANSFER_CUIT": "20-35123456-7",
    "WHATSAPP_NUMBER": "+54 9 351 123-4567",
}


class PublicBankTransferStatusTests(unittest.TestCase):
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

    def _seed_transfer_payment(self, **graph_kwargs) -> tuple[int, int, str]:
        """Creates a submitted order with a real bank transfer payment on it."""
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
            order_id = int(graph["order_id"])
            with patch.dict(os.environ, SHOP_CONFIG):
                payment = create_payment_for_order(
                    order_id=order_id,
                    method="bank_transfer",
                    db=session,
                    user_id=int(user.id),
                    idempotency_key=f"idemp-{datetime.now(UTC).timestamp()}",
                    currency="ARS",
                )
            session.commit()
            return order_id, int(payment["id"]), str(payment["public_status_token"])
        finally:
            session.close()

    def _status(self, token: str) -> dict:
        session = self.TestSession()
        try:
            result = get_public_bank_transfer_status(
                public_status_token=token,
                db=session,
            )
            session.commit()
            return result
        finally:
            session.close()

    def test_the_token_gives_back_the_same_instructions_as_the_checkout(self) -> None:
        order_id, payment_id, token = self._seed_transfer_payment()

        result = self._status(token)

        self.assertTrue(result["can_pay"])
        self.assertEqual(result["order_id"], order_id)
        self.assertEqual(result["payment_id"], payment_id)
        self.assertEqual(result["order_status"], "submitted")
        self.assertEqual(result["payment_status"], "pending")
        instructions = result["instructions"]
        self.assertEqual(instructions["alias"], "patitas.bigotes.real")
        self.assertEqual(instructions["cbu"], "0110599520000012345678")
        self.assertEqual(instructions["reference"], f"ORDER-{order_id}-PAY-{payment_id}")
        self.assertIn(instructions["reference"], instructions["whatsapp_url"])

    def test_it_says_what_the_customer_bought(self) -> None:
        """Someone with two pending orders has to be able to tell them apart.

        The amount alone does not do it, and a guest has no order history to
        look the difference up in.
        """
        order_id, _, token = self._seed_transfer_payment()

        result = self._status(token)

        self.assertEqual(result["order_id"], order_id)
        self.assertEqual(result["currency"], "ARS")
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["product_name"], "Test Product")
        self.assertEqual(item["quantity"], 1)
        self.assertEqual(item["line_total"], result["order_total"])
        self.assertIn("/", item["variant_label"])

    def test_the_detail_survives_a_settled_order(self) -> None:
        """The data goes away; what they bought does not.

        Someone checking on a paid order still deserves to see what it was.
        """
        _, payment_id, token = self._seed_transfer_payment()
        session = self.TestSession()
        try:
            payment = session.query(Payment).filter(Payment.id == payment_id).one()
            payment.status = "paid"
            payment.order.status = "paid"
            session.commit()
        finally:
            session.close()

        result = self._status(token)

        self.assertIsNone(result["instructions"])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["product_name"], "Test Product")

    def test_a_paid_payment_shows_its_state_and_no_instructions(self) -> None:
        """Nobody should be invited to transfer twice for the same order."""
        _, payment_id, token = self._seed_transfer_payment()
        session = self.TestSession()
        try:
            payment = session.query(Payment).filter(Payment.id == payment_id).one()
            payment.status = "paid"
            payment.order.status = "paid"
            session.commit()
        finally:
            session.close()

        result = self._status(token)

        self.assertFalse(result["can_pay"])
        self.assertIsNone(result["instructions"])
        self.assertEqual(result["payment_status"], "paid")
        self.assertEqual(result["order_status"], "paid")

    def test_a_cancelled_order_shows_its_state_and_no_instructions(self) -> None:
        _, payment_id, token = self._seed_transfer_payment()
        session = self.TestSession()
        try:
            payment = session.query(Payment).filter(Payment.id == payment_id).one()
            payment.order.status = "cancelled"
            session.commit()
        finally:
            session.close()

        result = self._status(token)

        self.assertFalse(result["can_pay"])
        self.assertIsNone(result["instructions"])
        self.assertEqual(result["order_status"], "cancelled")

    def _lapse_reservation(self, order_id: int, *, reactivations_used: int = 0) -> None:
        session = self.TestSession()
        try:
            reservation = (
                session.query(StockReservation)
                .filter(StockReservation.order_id == order_id)
                .one()
            )
            reservation.expires_at = datetime.now(UTC) - timedelta(hours=1)
            reservation.reactivation_count = reactivations_used
            session.commit()
        finally:
            session.close()

    def test_a_first_lapse_renews_the_reservation_and_keeps_the_order_payable(self) -> None:
        """The customer gets their one extension, so the instructions stay up.

        Answering "cancelled" here would be wrong: the order is still alive for
        another 12 h and the transfer would still be honoured.
        """
        order_id, _, token = self._seed_transfer_payment()
        self._lapse_reservation(order_id, reactivations_used=0)

        result = self._status(token)

        self.assertTrue(result["can_pay"])
        self.assertIsNotNone(result["instructions"])
        self.assertEqual(result["order_status"], "submitted")

    def test_a_lapse_with_no_extension_left_stops_inviting_the_transfer(self) -> None:
        """The sweep runs before answering, so a dead order reads as cancelled.

        Without it the page would tell someone to go transfer for an order the
        next job is about to cancel -- money arriving with nothing to match it.
        """
        order_id, _, token = self._seed_transfer_payment()
        self._lapse_reservation(order_id, reactivations_used=1)

        result = self._status(token)

        self.assertFalse(result["can_pay"])
        self.assertIsNone(result["instructions"])
        self.assertEqual(result["order_status"], "cancelled")

        session = self.TestSession()
        try:
            order = session.query(Order).filter(Order.id == order_id).one()
            self.assertEqual(str(order.status), "cancelled")
            payment = (
                session.query(Payment)
                .filter(Payment.order_id == order_id, Payment.method == "bank_transfer")
                .one()
            )
            self.assertEqual(str(payment.status), "cancelled")
        finally:
            session.close()

    def test_an_unknown_token_is_not_found(self) -> None:
        with self.assertRaises(LookupError):
            self._status("no-existe-este-token")

    def test_a_missing_token_is_rejected(self) -> None:
        for token in (None, "", "   "):
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    self._status(token)

    def test_an_oversized_token_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._status("x" * 256)

    def test_a_mercadopago_token_does_not_open_the_transfer_view(self) -> None:
        """Each method answers for its own payments only."""
        order_id, _, _ = self._seed_transfer_payment()
        session = self.TestSession()
        try:
            mp_payment = Payment(
                order_id=order_id,
                method="mercadopago",
                status="pending",
                amount=10000,
                currency="ARS",
                idempotency_key="idemp-mp-token",
                public_status_token="token-de-mercadopago",
            )
            session.add(mp_payment)
            session.commit()
        finally:
            session.close()

        with self.assertRaises(LookupError):
            self._status("token-de-mercadopago")


if __name__ == "__main__":
    unittest.main()
