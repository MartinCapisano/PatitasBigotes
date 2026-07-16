import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import os

os.environ.setdefault("MAIL_FROM", "no-reply@patitasbigotes.test")

from source.services.email_s import (
    send_email_verification,
    send_order_paid_email,
    send_password_reset,
)


class EmailContentTests(unittest.TestCase):
    def test_send_email_verification_builds_subject_and_link_in_body(self) -> None:
        with patch("source.services.email_s._send_message") as mocked_send:
            send_email_verification(
                to_email="user@example.com",
                verify_link="https://app.test/verify-email?token=abc123",
            )

        msg = mocked_send.call_args.args[0]
        self.assertEqual(msg["To"], "user@example.com")
        self.assertEqual(msg["Subject"], "Verifica tu email")
        body = msg.get_content()
        self.assertIn("https://app.test/verify-email?token=abc123", body)

    def test_send_password_reset_builds_subject_and_link_in_body(self) -> None:
        with patch("source.services.email_s._send_message") as mocked_send:
            send_password_reset(
                to_email="user@example.com",
                reset_link="https://app.test/reset-password?token=xyz789",
            )

        msg = mocked_send.call_args.args[0]
        self.assertEqual(msg["Subject"], "Restablecer contraseña")
        body = msg.get_content()
        self.assertIn("https://app.test/reset-password?token=xyz789", body)

    def test_send_order_paid_email_formats_currency_and_lists_items(self) -> None:
        with patch("source.services.email_s._send_message") as mocked_send:
            send_order_paid_email(
                payload={
                    "to_email": "buyer@example.com",
                    "order_id": 42,
                    "order_status": "paid",
                    "payment_id": 7,
                    "total_amount": 1234550,
                    "currency": "ARS",
                    "items": [
                        {
                            "product_name": "Collar",
                            "variant_label": "M/Azul",
                            "quantity": 2,
                            "line_total": 1234550,
                        }
                    ],
                }
            )

        msg = mocked_send.call_args.args[0]
        self.assertEqual(msg["To"], "buyer@example.com")
        self.assertEqual(msg["Subject"], "Actualizacion de tu orden #42")
        body = msg.get_content()
        self.assertIn("Estado actual: paid", body)
        self.assertIn("Pago registrado: #7", body)
        self.assertIn("ARS 12.345,50", body)
        self.assertIn("- Collar (M/Azul) x 2: ARS 12.345,50", body)

    def test_send_order_paid_email_falls_back_when_items_missing(self) -> None:
        with patch("source.services.email_s._send_message") as mocked_send:
            send_order_paid_email(
                payload={
                    "to_email": "buyer2@example.com",
                    "order_id": 43,
                    "order_status": "paid",
                    "payment_id": 8,
                    "total_amount": 500,
                    "currency": "ARS",
                    "items": [],
                }
            )

        msg = mocked_send.call_args.args[0]
        body = msg.get_content()
        self.assertIn("- Sin items disponibles", body)


if __name__ == "__main__":
    unittest.main()
