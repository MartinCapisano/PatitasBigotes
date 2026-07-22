"""The transfer instructions as the customer's browser receives them.

The service-level tests live in `tests/test_bank_transfer_instructions.py`;
this one checks the data actually survives the trip to the client, which is
what the checkout screen will render.
"""
import os
from unittest.mock import patch

from backend.tests.factories.http_payments import (
    build_create_payment_payload,
    create_submitted_order_with_reservation_for_user,
)
from backend.tests.http._base import HttpFundamentalsBase

SHOP_CONFIG = {
    "BANK_TRANSFER_ALIAS": "patitas.bigotes.real",
    "BANK_TRANSFER_CBU": "0110599520000012345678",
    "BANK_TRANSFER_BANK_NAME": "Banco Nacion",
    "BANK_TRANSFER_HOLDER": "Martin Capisano",
    "BANK_TRANSFER_CUIT": "20-35123456-7",
    "WHATSAPP_NUMBER": "+54 9 351 123-4567",
}


class HttpBankTransferInstructionsTests(HttpFundamentalsBase):
    def test_guest_checkout_returns_the_transfer_instructions_over_http(self) -> None:
        variant_id = self._seed_variant()

        with patch(
            "source.routes.orders_r.enforce_public_guest_checkout_limits",
            return_value=None,
        ), patch.dict(os.environ, SHOP_CONFIG):
            response = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "guest-bt-instructions@example.com",
                        "first_name": "Guest",
                        "last_name": "Buyer",
                        "phone": "1122334455",
                    },
                    "items": [{"variant_id": variant_id, "quantity": 1}],
                    "payment_method": "bank_transfer",
                    "website": None,
                },
                headers={
                    **self._origin_headers(),
                    "Idempotency-Key": "guest-bt-instructions-key-1",
                },
            )

        self.assertEqual(response.status_code, 201)
        payment = response.json()["data"]["payment"]
        instructions = payment["provider_payload_data"]["instructions"]

        self.assertEqual(instructions["alias"], "patitas.bigotes.real")
        self.assertEqual(instructions["cbu"], "0110599520000012345678")
        self.assertEqual(instructions["bank_name"], "Banco Nacion")
        self.assertEqual(instructions["holder"], "Martin Capisano")
        self.assertEqual(instructions["tax_id"], "20-35123456-7")
        self.assertEqual(instructions["whatsapp_number"], "5493511234567")
        self.assertEqual(
            instructions["reference"],
            f"ORDER-{payment['order_id']}-PAY-{payment['id']}",
        )
        self.assertEqual(instructions["amount"], payment["amount"])
        self.assertIn(instructions["reference"], instructions["whatsapp_url"])

    def test_logged_in_checkout_returns_the_same_instructions_over_http(self) -> None:
        """The account checkout uses a different endpoint than the guest one.

        Both have to hand the customer the same screen, so both are checked.
        """
        user_id = self._create_user(email="bt-instructions@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
        finally:
            db.close()
        self.assertEqual(self._login(email="bt-instructions@example.com").status_code, 200)

        with patch.dict(os.environ, SHOP_CONFIG):
            response = self.client.post(
                f"/orders/{order_id}/payments",
                json=build_create_payment_payload(method="bank_transfer"),
                headers={
                    **self._origin_headers(),
                    "Idempotency-Key": "bt-instructions-logged-in-key-1",
                },
            )

        self.assertEqual(response.status_code, 201)
        payment = response.json()["data"]
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
        self.assertEqual(instructions["alias"], "patitas.bigotes.real")
        self.assertEqual(
            instructions["reference"],
            f"ORDER-{order_id}-PAY-{payment['id']}",
        )
        self.assertEqual(instructions["amount"], payment["amount"])

    def test_a_guest_reopens_their_instructions_with_the_token_over_http(self) -> None:
        """No session, no account: the token is the whole credential."""
        variant_id = self._seed_variant()

        with patch(
            "source.routes.orders_r.enforce_public_guest_checkout_limits",
            return_value=None,
        ), patch.dict(os.environ, SHOP_CONFIG):
            checkout = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "guest-reopens@example.com",
                        "first_name": "Guest",
                        "last_name": "Buyer",
                        "phone": "1122334455",
                    },
                    "items": [{"variant_id": variant_id, "quantity": 1}],
                    "payment_method": "bank_transfer",
                    "website": None,
                },
                headers={
                    **self._origin_headers(),
                    "Idempotency-Key": "guest-reopens-key-1",
                },
            )
        self.assertEqual(checkout.status_code, 201)
        payment = checkout.json()["data"]["payment"]
        token = payment["public_status_token"]
        self.assertTrue(token)

        response = self.client.get(
            "/payments/public/bank-transfer",
            params={"public_status_token": token},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertTrue(payload["can_pay"])
        self.assertEqual(payload["order_id"], payment["order_id"])
        self.assertEqual(payload["payment_id"], payment["id"])
        self.assertEqual(
            payload["instructions"],
            payment["provider_payload_data"]["instructions"],
        )

    def test_the_guest_checkout_actually_sends_the_instructions_email(self) -> None:
        """The queue is drained by the route, not just filled by the service.

        Before this the checkout routes never dispatched post-commit actions,
        so an email queued there would have been silently dropped.
        """
        variant_id = self._seed_variant()

        with patch(
            "source.routes.orders_r.enforce_public_guest_checkout_limits",
            return_value=None,
        ), patch(
            "source.services.post_commit_actions_s.send_bank_transfer_instructions_email"
        ) as send_email, patch.dict(os.environ, SHOP_CONFIG):
            response = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "guest-mail@example.com",
                        "first_name": "Guest",
                        "last_name": "Buyer",
                        "phone": "1122334455",
                    },
                    "items": [{"variant_id": variant_id, "quantity": 1}],
                    "payment_method": "bank_transfer",
                    "website": None,
                },
                headers={
                    **self._origin_headers(),
                    "Idempotency-Key": "guest-mail-key-1",
                },
            )

        self.assertEqual(response.status_code, 201)
        send_email.assert_called_once()
        payload = send_email.call_args.kwargs["payload"]
        payment = response.json()["data"]["payment"]
        self.assertEqual(payload["to_email"], "guest-mail@example.com")
        self.assertEqual(payload["reference"], f"ORDER-{payment['order_id']}-PAY-{payment['id']}")
        self.assertEqual(payload["amount"], payment["amount"])
        self.assertIn(payment["public_status_token"], payload["status_url"])

    def test_a_cash_guest_checkout_sends_no_transfer_email(self) -> None:
        variant_id = self._seed_variant()

        with patch(
            "source.routes.orders_r.enforce_public_guest_checkout_limits",
            return_value=None,
        ), patch(
            "source.services.post_commit_actions_s.send_bank_transfer_instructions_email"
        ) as send_email, patch.dict(os.environ, SHOP_CONFIG):
            response = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "guest-cash@example.com",
                        "first_name": "Guest",
                        "last_name": "Buyer",
                        "phone": "1122334455",
                    },
                    "items": [{"variant_id": variant_id, "quantity": 1}],
                    "payment_method": "cash",
                    "website": None,
                },
                headers={
                    **self._origin_headers(),
                    "Idempotency-Key": "guest-cash-mail-key-1",
                },
            )

        self.assertEqual(response.status_code, 201)
        send_email.assert_not_called()

    def test_an_unknown_token_is_a_404_over_http(self) -> None:
        response = self.client.get(
            "/payments/public/bank-transfer",
            params={"public_status_token": "no-existe"},
        )

        self.assertEqual(response.status_code, 404)

    def test_a_missing_token_is_a_400_over_http(self) -> None:
        response = self.client.get("/payments/public/bank-transfer")

        self.assertEqual(response.status_code, 400)
