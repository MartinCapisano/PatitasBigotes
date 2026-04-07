from unittest.mock import patch

from backend.tests.factories.http_payments import (
    build_create_payment_payload,
    build_resolve_refund_payload,
    create_payment_incident,
    create_public_mercadopago_payment,
    create_retryable_payment,
    create_submitted_order_with_reservation_for_user,
)
from backend.tests.http._base import HttpFundamentalsBase


class HttpPaymentsFundamentalsTests(HttpFundamentalsBase):
    def test_create_order_payment_rejects_non_ars_currency_over_http(self) -> None:
        user_id = self._create_user(email="pay-currency@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
        finally:
            db.close()
        login_response = self._login(email="pay-currency@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            f"/orders/{order_id}/payments",
            json=build_create_payment_payload(method="bank_transfer", currency="USD"),
            headers={
                **self._origin_headers(),
                "Idempotency-Key": "payment-usd-key",
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_create_mercadopago_payment_returns_public_status_token_over_http(self) -> None:
        user_id = self._create_user(email="pay-public-token@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
        finally:
            db.close()
        login_response = self._login(email="pay-public-token@example.com")
        self.assertEqual(login_response.status_code, 200)

        with patch(
            "source.services.payment_s.create_checkout_preference",
            return_value={
                "id": "pref-public-token",
                "init_point": "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-public-token",
            },
        ):
            response = self.client.post(
                f"/orders/{order_id}/payments",
                json=build_create_payment_payload(method="mercadopago"),
                headers={
                    **self._origin_headers(),
                    "Idempotency-Key": "payment-public-token-key",
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        public_status_token = payload["public_status_token"]
        self.assertIsInstance(public_status_token, str)
        self.assertGreaterEqual(len(public_status_token), 20)

        checkout_payload = payload["provider_payload_data"]["checkout"]
        self.assertEqual(checkout_payload["public_status_token"], public_status_token)

    def test_get_public_payment_status_by_public_token_over_http(self) -> None:
        db = self._db()
        try:
            public_status_token = create_public_mercadopago_payment(db, status="paid")
        finally:
            db.close()

        response = self.client.get(
            f"/payments/public/status?public_status_token={public_status_token}"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["status"], "paid")
        self.assertEqual(payload["order_status"], "paid")

    def test_get_public_payment_status_requires_public_token_over_http(self) -> None:
        response = self.client.get("/payments/public/status")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "public_status_token is required")

    def test_get_public_payment_status_rejects_legacy_lookup_params_over_http(self) -> None:
        response = self.client.get(
            "/payments/public/status?external_ref=mp-order-1-pay-1&preference_id=pref-1"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "public_status_token is required")

    def test_get_public_payment_status_unknown_token_returns_404_over_http(self) -> None:
        response = self.client.get("/payments/public/status?public_status_token=missing-public-token")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "payment not found")

    def test_retry_payment_creates_new_attempt_after_cancelled_over_http(self) -> None:
        user_id = self._create_user(email="pay-retry@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
            cancelled_id = create_retryable_payment(
                db,
                order_id=order_id,
                method="bank_transfer",
                status="cancelled",
            )
        finally:
            db.close()
        login_response = self._login(email="pay-retry@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            f"/orders/{order_id}/payments/retry",
            json=build_create_payment_payload(method="bank_transfer"),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertNotEqual(int(payload["id"]), cancelled_id)
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["method"], "bank_transfer")

    def test_retry_payment_requires_retryable_latest_status_over_http(self) -> None:
        user_id = self._create_user(email="pay-retry-blocked@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
            create_retryable_payment(
                db,
                order_id=order_id,
                method="bank_transfer",
                status="pending",
            )
        finally:
            db.close()
        login_response = self._login(email="pay-retry-blocked@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            f"/orders/{order_id}/payments/retry",
            json=build_create_payment_payload(method="bank_transfer"),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "latest payment attempt is not retryable")

    def test_submit_bank_transfer_receipt_updates_payment_over_http(self) -> None:
        user_id = self._create_user(email="pay-receipt@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
        finally:
            db.close()
        login_response = self._login(email="pay-receipt@example.com")
        self.assertEqual(login_response.status_code, 200)

        create_response = self.client.post(
            f"/orders/{order_id}/payments",
            json=build_create_payment_payload(method="bank_transfer"),
            headers={
                **self._origin_headers(),
                "Idempotency-Key": "payment-receipt-key",
            },
        )
        self.assertEqual(create_response.status_code, 201)
        payment_id = int(create_response.json()["data"]["id"])

        response = self.client.post(
            f"/orders/{order_id}/payments/{payment_id}/bank-transfer/receipt",
            files={"file": ("receipt-1.jpg", b"fake-jpeg-content", "image/jpeg")},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertIn("/receipts/payment-", payload["receipt_url"])
        self.assertEqual(payload["provider_payload_data"]["receipt"]["url"], payload["receipt_url"])
        self.assertEqual(payload["provider_payload_data"]["receipt"]["content_type"], "image/jpeg")

    def test_resolve_payment_incident_refund_success_over_http(self) -> None:
        db = self._db()
        try:
            incident_id = create_payment_incident(db)
        finally:
            db.close()
        self._create_user(email="admin-refund@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-refund@example.com")
        self.assertEqual(login_response.status_code, 200)

        with patch(
            "source.services.refund_s.create_refund",
            return_value={"id": 9001, "status": "approved"},
        ):
            response = self.client.post(
                f"/admin/payment-incidents/{incident_id}/resolve-refund",
                json=build_resolve_refund_payload(reason="cliente ya pago en local"),
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertEqual(payload["incident"]["status"], "resolved_refunded")
        self.assertEqual(payload["refund"]["status"], "approved")
        self.assertEqual(payload["refund"]["provider_refund_id"], "9001")

    def test_resolve_payment_incident_no_refund_requires_reason_over_http(self) -> None:
        db = self._db()
        try:
            incident_id = create_payment_incident(db)
        finally:
            db.close()
        admin_id = self._create_user(email="admin-no-refund@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-no-refund@example.com")
        self.assertEqual(login_response.status_code, 200)

        invalid_response = self.client.post(
            f"/admin/payment-incidents/{incident_id}/resolve-no-refund",
            json={"reason": ""},
            headers=self._origin_headers(),
        )
        self.assertEqual(invalid_response.status_code, 422)

        valid_response = self.client.post(
            f"/admin/payment-incidents/{incident_id}/resolve-no-refund",
            json={"reason": "caso validado y no corresponde devolver"},
            headers=self._origin_headers(),
        )
        self.assertEqual(valid_response.status_code, 200)
        payload = valid_response.json()["data"]
        self.assertEqual(payload["status"], "resolved_no_refund")
        self.assertEqual(payload["resolved_by_user_id"], admin_id)
