"""The MercadoPago pause seen from the outside: over HTTP, with the flag off.

The service-level lock is covered in `tests/test_mercadopago_disabled_lock.py`;
these tests check that a client calling the API directly -- bypassing the
frontend that no longer offers the option -- gets a clean 4xx and not a 500.
"""
import os
from unittest.mock import patch

from backend.tests.factories.http_payments import (
    build_create_payment_payload,
    create_submitted_order_with_reservation_for_user,
)
from backend.tests.http._base import HttpFundamentalsBase


def mercadopago_disabled():
    return patch.dict(os.environ, {"MERCADOPAGO_ENABLED": "false"})


class HttpMercadoPagoDisabledCheckoutTests(HttpFundamentalsBase):
    def test_guest_checkout_with_mercadopago_is_rejected_over_http(self) -> None:
        variant_id = self._seed_variant()

        with patch(
            "source.routes.orders_r.enforce_public_guest_checkout_limits",
            return_value=None,
        ), patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference"
        ) as create_preference, mercadopago_disabled():
            response = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "guest-mp-disabled@example.com",
                        "first_name": "Guest",
                        "last_name": "Buyer",
                        "phone": "1122334455",
                    },
                    "items": [{"variant_id": variant_id, "quantity": 1}],
                    "payment_method": "mercadopago",
                    "website": None,
                },
                headers={
                    **self._origin_headers(),
                    "Idempotency-Key": "guest-mp-disabled-key-1",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("mercadopago", response.json()["detail"])
        create_preference.assert_not_called()

    def test_guest_checkout_with_bank_transfer_still_succeeds_over_http(self) -> None:
        variant_id = self._seed_variant()

        with patch(
            "source.routes.orders_r.enforce_public_guest_checkout_limits",
            return_value=None,
        ), mercadopago_disabled():
            response = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "guest-bt-while-paused@example.com",
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
                    "Idempotency-Key": "guest-bt-while-paused-key-1",
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertEqual(payload["payment"]["method"], "bank_transfer")
        self.assertEqual(payload["payment"]["status"], "pending")

    def test_order_payment_with_mercadopago_is_rejected_over_http(self) -> None:
        user_id = self._create_user(email="mp-disabled-buyer@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
        finally:
            db.close()
        self.assertEqual(
            self._login(email="mp-disabled-buyer@example.com").status_code, 200
        )

        with patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference"
        ) as create_preference, mercadopago_disabled():
            response = self.client.post(
                f"/orders/{order_id}/payments",
                json=build_create_payment_payload(method="mercadopago"),
                headers={
                    **self._origin_headers(),
                    "Idempotency-Key": "mp-disabled-payment-key-1",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("mercadopago", response.json()["detail"])
        create_preference.assert_not_called()
