"""The transfer instructions a customer reads before sending real money.

Everything here is about one risk: the customer transferring to the wrong place,
or to a placeholder left over from development. So the tests care about where
the values come from (configuration, never hardcoded) and about the reference
travelling with the WhatsApp message, which is the only thing tying the money
in the bank account back to an order.
"""
import os
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db import config
from source.db.models import Base
from source.services.bank_transfer_s import (
    build_bank_transfer_payload,
    build_payment_reference,
    build_whatsapp_receipt_url,
)
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


def shop_configured():
    return patch.dict(os.environ, SHOP_CONFIG)


class BankTransferPayloadTests(unittest.TestCase):
    def test_instructions_come_from_configuration(self) -> None:
        with shop_configured():
            payload = build_bank_transfer_payload(
                order_id=12,
                payment_id=34,
                amount=250000,
                currency="ARS",
            )

        instructions = payload["instructions"]
        self.assertEqual(instructions["alias"], "patitas.bigotes.real")
        self.assertEqual(instructions["cbu"], "0110599520000012345678")
        self.assertEqual(instructions["bank_name"], "Banco Nacion")
        self.assertEqual(instructions["holder"], "Martin Capisano")
        self.assertEqual(instructions["tax_id"], "20-35123456-7")
        self.assertEqual(instructions["amount"], 250000)
        self.assertEqual(instructions["currency"], "ARS")

    def test_no_demo_placeholder_survives_in_the_payload(self) -> None:
        """The old hardcoded `patitas.bigotes` / `Banco Demo` must be gone."""
        with shop_configured():
            payload = build_bank_transfer_payload(
                order_id=1,
                payment_id=1,
                amount=1000,
                currency="ARS",
            )

        serialized = str(payload).lower()
        self.assertNotIn("banco demo", serialized)
        self.assertNotIn("demo", serialized)

    def test_reference_identifies_the_order_and_the_payment(self) -> None:
        self.assertEqual(build_payment_reference(12, 34), "ORDER-12-PAY-34")

    def test_whatsapp_url_carries_the_reference_in_the_message(self) -> None:
        with shop_configured():
            url = build_whatsapp_receipt_url("ORDER-12-PAY-34")

        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "wa.me")
        self.assertEqual(parsed.path, "/5493511234567")
        message = parse_qs(parsed.query)["text"][0]
        self.assertIn("ORDER-12-PAY-34", message)
        self.assertIn("comprobante", message.lower())

    def test_whatsapp_number_keeps_only_digits(self) -> None:
        """Written the way a human writes it, usable the way wa.me needs it."""
        with shop_configured():
            payload = build_bank_transfer_payload(
                order_id=1,
                payment_id=2,
                amount=1000,
                currency="ARS",
            )

        self.assertEqual(payload["instructions"]["whatsapp_number"], "5493511234567")
        self.assertIn(
            "wa.me/5493511234567", payload["instructions"]["whatsapp_url"]
        )


class BankTransferConfigTests(unittest.TestCase):
    def test_each_missing_value_is_rejected(self) -> None:
        for name in config.BANK_TRANSFER_ENV_VARS:
            with self.subTest(missing=name):
                with patch.dict(os.environ, {**SHOP_CONFIG, name: ""}):
                    with self.assertRaises(RuntimeError) as ctx:
                        config.validate_bank_transfer_config()
                self.assertIn(name, str(ctx.exception))

    def test_every_missing_value_is_reported_at_once(self) -> None:
        """One fix instead of six redeploys."""
        blanked = {name: "" for name in config.BANK_TRANSFER_ENV_VARS}
        with patch.dict(os.environ, blanked):
            with self.assertRaises(RuntimeError) as ctx:
                config.validate_bank_transfer_config()

        message = str(ctx.exception)
        for name in config.BANK_TRANSFER_ENV_VARS:
            self.assertIn(name, message)

    def test_a_whatsapp_number_without_digits_is_rejected(self) -> None:
        with patch.dict(os.environ, {**SHOP_CONFIG, "WHATSAPP_NUMBER": "no-tenemos"}):
            with self.assertRaises(RuntimeError):
                config.validate_bank_transfer_config()

    def test_a_fully_configured_shop_passes(self) -> None:
        with shop_configured():
            config.validate_bank_transfer_config()


class BankTransferCheckoutTests(unittest.TestCase):
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

    def _seed_submitted_order(self) -> tuple[int, int]:
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

    def test_a_new_payment_carries_the_full_instructions(self) -> None:
        order_id, user_id = self._seed_submitted_order()
        session = self.TestSession()
        try:
            with shop_configured():
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

        instructions = payment["provider_payload_data"]["instructions"]
        self.assertEqual(
            set(instructions),
            {
                "alias",
                "cbu",
                "bank_name",
                "holder",
                "tax_id",
                "reference",
                "amount",
                "currency",
                "whatsapp_number",
                "whatsapp_url",
            },
        )
        self.assertEqual(
            instructions["reference"],
            f"ORDER-{order_id}-PAY-{payment['id']}",
        )
        self.assertEqual(instructions["amount"], payment["amount"])
        self.assertIn(instructions["reference"], instructions["whatsapp_url"])


if __name__ == "__main__":
    unittest.main()
