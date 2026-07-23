"""The instructions arriving by email, not just on a page the customer closed.

Until this existed the only email of the payment cycle was the paid-order one,
which arrives *after* the admin confirms -- long after the customer needed to
know where to send the money. A guest who closed the tab had nothing at all.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base, Payment, User
from source.services.bank_transfer_s import TRANSFER_DEADLINE_HOURS
from source.services.email_s import send_bank_transfer_instructions_email
from source.services.payment_s import (
    create_payment_for_order,
    create_retry_payment_for_order,
)
from source.services.post_commit_actions_s import (
    ACTION_BANK_TRANSFER_INSTRUCTIONS_EMAIL,
    POST_COMMIT_ACTIONS_KEY,
    dispatch_post_commit_actions,
)
from tests.factories.orders import create_order_graph
from tests.factories.users import create_user

SHOP_CONFIG = {
    "BANK_TRANSFER_ALIAS": "patitas.bigotes.real",
    "BANK_TRANSFER_CBU": "0110599520000012345678",
    "BANK_TRANSFER_BANK_NAME": "Banco Nacion",
    "BANK_TRANSFER_HOLDER": "Martin Capisano",
    "BANK_TRANSFER_CUIT": "20-35123456-7",
    "WHATSAPP_NUMBER": "+54 9 351 123-4567",
    "APP_BASE_URL": "https://tienda.test",
}


class BankTransferInstructionsEmailQueueTests(unittest.TestCase):
    """Where the email gets queued, and where it must not be."""

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

    def _seed_submitted_order(self, *, email_prefix: str = "jane", **graph_kwargs):
        session = self.TestSession()
        try:
            user = create_user(
                session,
                first_name="Jane",
                last_name="Doe",
                email_prefix=email_prefix,
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
            return int(graph["order_id"]), int(user.id), str(user.email)
        finally:
            session.close()

    @staticmethod
    def _queued_instruction_emails(session) -> list[dict]:
        return [
            action["payload"]
            for action in session.info.get(POST_COMMIT_ACTIONS_KEY, [])
            if action["kind"] == ACTION_BANK_TRANSFER_INSTRUCTIONS_EMAIL
        ]

    def test_a_new_transfer_payment_queues_the_email(self) -> None:
        order_id, user_id, email = self._seed_submitted_order()
        session = self.TestSession()
        try:
            with patch.dict(os.environ, SHOP_CONFIG):
                payment = create_payment_for_order(
                    order_id=order_id,
                    method="bank_transfer",
                    db=session,
                    user_id=user_id,
                    idempotency_key="idemp-email-1",
                    currency="ARS",
                )
            queued = self._queued_instruction_emails(session)
            session.commit()
        finally:
            session.close()

        self.assertEqual(len(queued), 1)
        payload = queued[0]
        self.assertEqual(payload["to_email"], email)
        self.assertEqual(payload["order_id"], order_id)
        self.assertEqual(payload["payment_id"], payment["id"])
        self.assertEqual(payload["amount"], payment["amount"])
        self.assertEqual(payload["alias"], "patitas.bigotes.real")
        self.assertEqual(payload["cbu"], "0110599520000012345678")
        self.assertEqual(payload["reference"], f"ORDER-{order_id}-PAY-{payment['id']}")
        self.assertEqual(payload["deadline_hours"], TRANSFER_DEADLINE_HOURS)
        # Tambien es el mail de confirmacion de la orden, asi que lleva lo que
        # se compro y no solo el monto.
        self.assertEqual(
            payload["items"],
            [
                {
                    "product_name": "Test Product",
                    "variant_label": "M/Blue",
                    "quantity": 1,
                    "line_total": 10000,
                }
            ],
        )

    def test_the_email_carries_the_link_back_to_the_instructions(self) -> None:
        """A guest has no account, so the link is their only way back."""
        order_id, user_id, _ = self._seed_submitted_order()
        session = self.TestSession()
        try:
            with patch.dict(os.environ, SHOP_CONFIG):
                payment = create_payment_for_order(
                    order_id=order_id,
                    method="bank_transfer",
                    db=session,
                    user_id=user_id,
                    idempotency_key="idemp-email-link",
                    currency="ARS",
                )
            queued = self._queued_instruction_emails(session)
            session.commit()
        finally:
            session.close()

        self.assertEqual(
            queued[0]["status_url"],
            f"https://tienda.test/transferencia?token={payment['public_status_token']}",
        )

    def test_cash_does_not_queue_a_transfer_email(self) -> None:
        order_id, user_id, _ = self._seed_submitted_order()
        session = self.TestSession()
        try:
            with patch.dict(os.environ, SHOP_CONFIG):
                create_payment_for_order(
                    order_id=order_id,
                    method="cash",
                    db=session,
                    user_id=user_id,
                    idempotency_key="idemp-email-cash",
                    currency="ARS",
                )
            queued = self._queued_instruction_emails(session)
            session.commit()
        finally:
            session.close()

        self.assertEqual(queued, [])

    def test_mercadopago_does_not_queue_a_transfer_email(self) -> None:
        order_id, user_id, _ = self._seed_submitted_order()
        session = self.TestSession()
        try:
            with patch.dict(os.environ, {**SHOP_CONFIG, "MERCADOPAGO_ENABLED": "true"}), patch(
                "source.services.mercadopago_normalization_s.create_checkout_preference",
                return_value={
                    "id": "pref-1",
                    "init_point": "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-1",
                },
            ):
                create_payment_for_order(
                    order_id=order_id,
                    method="mercadopago",
                    db=session,
                    user_id=user_id,
                    idempotency_key="idemp-email-mp",
                    currency="ARS",
                )
            queued = self._queued_instruction_emails(session)
            session.commit()
        finally:
            session.close()

        self.assertEqual(queued, [])

    def test_an_idempotent_replay_does_not_queue_a_second_email(self) -> None:
        """The same checkout submitted twice is one purchase, so one email."""
        order_id, user_id, _ = self._seed_submitted_order()
        session = self.TestSession()
        try:
            with patch.dict(os.environ, SHOP_CONFIG):
                first = create_payment_for_order(
                    order_id=order_id,
                    method="bank_transfer",
                    db=session,
                    user_id=user_id,
                    idempotency_key="idemp-email-replay",
                    currency="ARS",
                )
                session.commit()
                second = create_payment_for_order(
                    order_id=order_id,
                    method="bank_transfer",
                    db=session,
                    user_id=user_id,
                    idempotency_key="idemp-email-replay",
                    currency="ARS",
                )
            queued = self._queued_instruction_emails(session)
            session.commit()
        finally:
            session.close()

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(queued), 1)

    def test_a_retry_queues_a_fresh_email_with_the_new_reference(self) -> None:
        """A retry is a different payment, so the old reference no longer applies."""
        order_id, user_id, _ = self._seed_submitted_order(
            add_pending_payment=True,
            payment_method="bank_transfer",
            payment_status="cancelled",
        )
        session = self.TestSession()
        try:
            with patch.dict(os.environ, SHOP_CONFIG):
                retry = create_retry_payment_for_order(
                    order_id=order_id,
                    method="bank_transfer",
                    db=session,
                    user_id=user_id,
                    idempotency_key="idemp-email-retry",
                    currency="ARS",
                )
            queued = self._queued_instruction_emails(session)
            session.commit()
        finally:
            session.close()

        self.assertEqual(len(queued), 1)
        self.assertEqual(
            queued[0]["reference"],
            f"ORDER-{order_id}-PAY-{retry['id']}",
        )

    def test_a_buyer_with_no_email_is_skipped_not_crashed(self) -> None:
        order_id, user_id, _ = self._seed_submitted_order(email_prefix="sinmail")
        session = self.TestSession()
        try:
            user = session.query(User).filter(User.id == user_id).one()
            user.email = ""
            session.commit()

            with patch.dict(os.environ, SHOP_CONFIG):
                payment = create_payment_for_order(
                    order_id=order_id,
                    method="bank_transfer",
                    db=session,
                    user_id=user_id,
                    idempotency_key="idemp-email-missing",
                    currency="ARS",
                )
            queued = self._queued_instruction_emails(session)
            session.commit()
        finally:
            session.close()

        # The purchase goes through; only the email is skipped.
        self.assertEqual(payment["method"], "bank_transfer")
        self.assertEqual(queued, [])

    def test_a_dead_mail_server_does_not_undo_the_purchase(self) -> None:
        """The order is already committed when the email is attempted."""
        order_id, user_id, _ = self._seed_submitted_order()
        session = self.TestSession()
        try:
            with patch.dict(os.environ, SHOP_CONFIG):
                create_payment_for_order(
                    order_id=order_id,
                    method="bank_transfer",
                    db=session,
                    user_id=user_id,
                    idempotency_key="idemp-email-smtp-down",
                    currency="ARS",
                )
            session.commit()

            with patch(
                "source.services.post_commit_actions_s.send_bank_transfer_instructions_email",
                side_effect=RuntimeError("smtp down"),
            ):
                # Must not raise.
                dispatch_post_commit_actions(db=session, source="test")
        finally:
            session.close()

        session = self.TestSession()
        try:
            payment = session.query(Payment).one()
            self.assertEqual(str(payment.status), "pending")
            self.assertEqual(str(payment.method), "bank_transfer")
        finally:
            session.close()


class BankTransferInstructionsEmailContentTests(unittest.TestCase):
    """What the customer actually reads."""

    PAYLOAD = {
        "to_email": "buyer@example.com",
        "order_id": 42,
        "payment_id": 7,
        "amount": 25990,
        "currency": "ARS",
        "deadline_hours": 24,
        "alias": "patitas.bigotes.real",
        "cbu": "0110599520000012345678",
        "bank_name": "Banco Nacion",
        "holder": "Martin Capisano",
        "tax_id": "20-35123456-7",
        "reference": "ORDER-42-PAY-7",
        "items": [
            {
                "product_name": "Collar Urban Paseo",
                "variant_label": "M/Azul",
                "quantity": 2,
                "line_total": 19990,
            },
            {
                "product_name": "Correa Retractil",
                "variant_label": "U/Negro",
                "quantity": 1,
                "line_total": 6000,
            },
        ],
        "whatsapp_number": "5493511234567",
        "whatsapp_url": "https://wa.me/5493511234567?text=Referencia",
        "status_url": "https://tienda.test/transferencia?token=tok-42",
    }

    def _sent_body(self, **overrides) -> str:
        with patch("source.services.email_s._send_message") as mocked_send:
            send_bank_transfer_instructions_email(payload={**self.PAYLOAD, **overrides})
        self.msg = mocked_send.call_args.args[0]
        return self.msg.get_content()

    def test_it_carries_every_field_needed_to_transfer(self) -> None:
        body = self._sent_body()

        self.assertEqual(self.msg["To"], "buyer@example.com")
        # Es tambien el mail de confirmacion de la orden: con transferencia como
        # unico metodo, "recibimos tu orden" y "datos para transferir" son el
        # mismo mail.
        self.assertEqual(self.msg["Subject"], "Recibimos tu orden #42")
        for expected in (
            "patitas.bigotes.real",
            "0110599520000012345678",
            "Banco Nacion",
            "Martin Capisano",
            "20-35123456-7",
            "ORDER-42-PAY-7",
        ):
            self.assertIn(expected, body)

    def test_the_amount_keeps_its_cents(self) -> None:
        # Same reason as on screen: the customer types this into their bank.
        body = self._sent_body()

        self.assertIn("ARS 259,90", body)
        self.assertNotIn("ARS 260,00", body)

    def test_it_states_the_deadline(self) -> None:
        body = self._sent_body()

        self.assertIn("24 hs", body)

    def test_it_carries_both_links(self) -> None:
        body = self._sent_body()

        self.assertIn("https://wa.me/5493511234567?text=Referencia", body)
        self.assertIn("https://tienda.test/transferencia?token=tok-42", body)

    def test_it_lists_what_was_ordered(self) -> None:
        body = self._sent_body()

        self.assertIn("- Collar Urban Paseo (M/Azul) x 2: ARS 199,90", body)
        self.assertIn("- Correa Retractil (U/Negro) x 1: ARS 60,00", body)

    def test_the_bank_details_come_before_the_item_list(self) -> None:
        """Este mail tiene un solo trabajo, que es cobrar.

        Si el detalle del pedido va arriba, en un celular el CBU queda abajo del
        pliegue y el cliente tiene que scrollear para pagar.
        """
        body = self._sent_body()

        self.assertLess(body.index("0110599520000012345678"), body.index("Collar Urban Paseo"))
        self.assertLess(body.index("ORDER-42-PAY-7"), body.index("Collar Urban Paseo"))

    def test_an_order_with_no_items_still_gets_its_bank_details(self) -> None:
        body = self._sent_body(items=[])

        self.assertIn("0110599520000012345678", body)
        self.assertIn("- Sin items disponibles", body)


if __name__ == "__main__":
    unittest.main()
