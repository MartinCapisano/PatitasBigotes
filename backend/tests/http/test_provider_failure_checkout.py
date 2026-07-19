from unittest.mock import patch
import json

from backend.tests.http._base import HttpFundamentalsBase
from source.services.idempotency_s import build_guest_checkout_scope
from source.db.models import IdempotencyRecord, Payment
from source.services.payment_s import PAYMENT_PROVIDER_SETUP_FAILED


class ProviderFailureCheckoutTests(HttpFundamentalsBase):
    def test_guest_checkout_mercadopago_failure_marks_payment_and_idempotency_failed(self) -> None:
        variant_id = self._seed_variant()
        email = "guest-mp-fail@example.com"
        payload = {
            "customer": {"email": email, "first_name": "Guest", "last_name": "Buyer", "phone": "1122334455"},
            "items": [{"variant_id": variant_id, "quantity": 1}],
            "payment_method": "mercadopago",
            "website": None,
        }
        headers = {**self._origin_headers(), "Idempotency-Key": "guest-mp-fail-1"}

        # Simulate provider failure during checkout preference creation
        with patch("source.routes.orders_r.enforce_public_guest_checkout_limits", return_value=None), patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference", side_effect=Exception("mp down")
        ):
            response = self.client.post("/checkout/guest", json=payload, headers=headers)

        self.assertEqual(response.status_code, 502)

        db = self._db()
        try:
            scope = build_guest_checkout_scope(email)
            record = (
                db.query(IdempotencyRecord)
                .filter(IdempotencyRecord.scope == scope, IdempotencyRecord.idempotency_key == "guest-mp-fail-1")
                .first()
            )
            self.assertIsNotNone(record, "expected an idempotency record to exist")
            self.assertEqual(str(record.status), "failed")

            rp = json.loads(record.response_payload)
            self.assertIn("order_id", rp)
            self.assertIn("payment_id", rp)

            payment = db.query(Payment).filter(Payment.id == int(rp["payment_id"])).first()
            self.assertIsNotNone(payment, "expected payment record to exist")
            self.assertEqual(str(payment.provider_status), PAYMENT_PROVIDER_SETUP_FAILED)
        finally:
            db.close()
