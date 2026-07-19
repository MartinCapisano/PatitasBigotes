from unittest.mock import patch

from backend.tests.factories.orders import create_order_graph
from backend.tests.factories.http_payments import (
    build_create_payment_payload,
    build_resolve_refund_payload,
    create_payment_incident,
    create_public_mercadopago_payment,
    create_public_mercadopago_payment_graph,
    create_retryable_payment,
    create_submitted_order_with_reservation_for_user,
)
from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import Payment, StockReservation


class HttpPaymentsFundamentalsTests(HttpFundamentalsBase):
    @staticmethod
    def _retry_headers(key: str) -> dict[str, str]:
        return {
            "Origin": "http://localhost:5173",
            "Idempotency-Key": key,
        }

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
            "source.services.mercadopago_normalization_s.create_checkout_preference",
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

    def test_get_public_order_snapshot_by_payment_token_returns_pending_checkout_over_http(self) -> None:
        db = self._db()
        try:
            graph = create_public_mercadopago_payment_graph(
                db,
                status="pending",
                checkout_url="https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-public-snapshot",
            )
        finally:
            db.close()

        response = self.client.get(
            f"/public/orders/by-payment-token?public_status_token={graph['public_status_token']}"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["order"]["status"], "submitted")
        self.assertEqual(payload["payment"]["status"], "pending")
        self.assertEqual(payload["payment"]["method"], "mercadopago")
        self.assertEqual(
            payload["payment"]["checkout_url"],
            "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-public-snapshot",
        )
        self.assertTrue(payload["flags"]["can_continue_payment"])
        self.assertFalse(payload["flags"]["can_retry_payment"])
        self.assertTrue(payload["flags"]["is_order_open"])
        self.assertFalse(payload["flags"]["is_payment_terminal"])
        self.assertIsNone(payload["blocking_reason"])
        self.assertNotIn("id", payload["order"])
        self.assertNotIn("customer", payload["order"])
        self.assertNotIn("email", payload["order"])
        self.assertNotIn("phone", payload["order"])
        self.assertNotIn("dni", payload["order"])
        self.assertNotIn("external_ref", payload["payment"])
        self.assertNotIn("idempotency_key", payload["payment"])
        self.assertNotIn("provider_payload", payload["payment"])
        self.assertNotIn("preference_id", payload["payment"])

    def test_get_public_order_snapshot_by_payment_token_marks_retryable_cancelled_payment_over_http(self) -> None:
        db = self._db()
        try:
            graph = create_public_mercadopago_payment_graph(db, status="cancelled")
        finally:
            db.close()

        response = self.client.get(
            f"/public/orders/by-payment-token?public_status_token={graph['public_status_token']}"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["payment"]["status"], "cancelled")
        self.assertFalse(payload["flags"]["can_continue_payment"])
        self.assertTrue(payload["flags"]["can_retry_payment"])
        self.assertTrue(payload["flags"]["is_order_open"])
        self.assertTrue(payload["flags"]["is_payment_terminal"])
        self.assertIsNone(payload["blocking_reason"])

    def test_get_public_order_snapshot_by_payment_token_marks_paid_order_blocked_over_http(self) -> None:
        db = self._db()
        try:
            graph = create_public_mercadopago_payment_graph(db, status="paid", order_status="paid")
        finally:
            db.close()

        response = self.client.get(
            f"/public/orders/by-payment-token?public_status_token={graph['public_status_token']}"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["order"]["status"], "paid")
        self.assertFalse(payload["flags"]["can_continue_payment"])
        self.assertFalse(payload["flags"]["can_retry_payment"])
        self.assertFalse(payload["flags"]["is_order_open"])
        self.assertTrue(payload["flags"]["is_payment_terminal"])
        self.assertEqual(payload["blocking_reason"], "order_paid")

    def test_get_public_order_snapshot_by_payment_token_marks_cancelled_order_blocked_over_http(self) -> None:
        db = self._db()
        try:
            graph = create_public_mercadopago_payment_graph(db, status="cancelled", order_status="cancelled")
        finally:
            db.close()

        response = self.client.get(
            f"/public/orders/by-payment-token?public_status_token={graph['public_status_token']}"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["order"]["status"], "cancelled")
        self.assertFalse(payload["flags"]["can_continue_payment"])
        self.assertFalse(payload["flags"]["can_retry_payment"])
        self.assertFalse(payload["flags"]["is_order_open"])
        self.assertTrue(payload["flags"]["is_payment_terminal"])
        self.assertEqual(payload["blocking_reason"], "order_cancelled")

    def test_get_public_order_snapshot_by_payment_token_prefers_new_pending_attempt_over_http(self) -> None:
        db = self._db()
        try:
            graph = create_public_mercadopago_payment_graph(db, status="cancelled")
            create_retryable_payment(
                db,
                order_id=int(graph["order_id"]),
                method="mercadopago",
                status="pending",
                provider_payload={
                    "checkout": {
                        "checkout_url": "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-public-retry",
                    }
                },
            )
        finally:
            db.close()

        response = self.client.get(
            f"/public/orders/by-payment-token?public_status_token={graph['public_status_token']}"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["payment"]["status"], "pending")
        self.assertEqual(
            payload["payment"]["checkout_url"],
            "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-public-retry",
        )
        self.assertTrue(payload["flags"]["can_continue_payment"])
        self.assertFalse(payload["flags"]["can_retry_payment"])
        self.assertIsNone(payload["blocking_reason"])

    def test_get_public_order_snapshot_by_payment_token_requires_token_over_http(self) -> None:
        response = self.client.get("/public/orders/by-payment-token")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "public_status_token is required")

    def test_get_public_order_snapshot_by_payment_token_unknown_token_returns_404_over_http(self) -> None:
        response = self.client.get("/public/orders/by-payment-token?public_status_token=missing-public-token")

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
            headers=self._retry_headers("retry-payment-bank-transfer"),
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
            headers=self._retry_headers("retry-payment-blocked"),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "retry not allowed: payment state changed")

    def test_retry_mercadopago_creates_new_checkout_after_cancelled_over_http(self) -> None:
        user_id = self._create_user(email="pay-retry-mp@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
            create_retryable_payment(
                db,
                order_id=order_id,
                method="mercadopago",
                status="cancelled",
            )
        finally:
            db.close()
        login_response = self._login(email="pay-retry-mp@example.com")
        self.assertEqual(login_response.status_code, 200)

        with patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference",
            return_value={
                "id": "pref-retry-mp",
                "init_point": "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-retry-mp",
            },
        ):
            response = self.client.post(
                f"/orders/{order_id}/payments/retry",
                json=build_create_payment_payload(method="mercadopago"),
                headers=self._retry_headers("retry-payment-mp"),
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertEqual(payload["method"], "mercadopago")
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["preference_id"], "pref-retry-mp")
        self.assertEqual(
            payload["provider_payload_data"]["checkout"]["checkout_url"],
            "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-retry-mp",
        )

    def test_retry_payment_rejects_cancelled_order_over_http(self) -> None:
        user_id = self._create_user(email="pay-retry-order-cancelled@example.com", verified=True)
        db = self._db()
        try:
            graph = create_order_graph(
                db,
                user_id=user_id,
                order_status="cancelled",
                with_reservation=False,
                add_pending_payment=False,
            )
            create_retryable_payment(
                db,
                order_id=int(graph["order_id"]),
                method="mercadopago",
                status="cancelled",
            )
        finally:
            db.close()
        login_response = self._login(email="pay-retry-order-cancelled@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            f"/orders/{graph['order_id']}/payments/retry",
            json=build_create_payment_payload(method="mercadopago"),
            headers=self._retry_headers("retry-order-cancelled"),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "retry not allowed: order cancelled")

    def test_retry_payment_rejects_order_cancelled_by_reservation_expiration_over_http(self) -> None:
        user_id = self._create_user(email="pay-retry-reservation-expired@example.com", verified=True)
        db = self._db()
        try:
            graph = create_order_graph(
                db,
                user_id=user_id,
                order_status="cancelled",
                with_reservation=True,
                reservation_status="expired",
            )
            payment_id = create_retryable_payment(
                db,
                order_id=int(graph["order_id"]),
                method="mercadopago",
                status="cancelled",
            )
            stock_reservation = (
                db.query(StockReservation)
                .filter(StockReservation.order_id == int(graph["order_id"]))
                .first()
            )
            self.assertIsNotNone(stock_reservation)
            assert stock_reservation is not None
            stock_reservation.reason = "reservation_expired"
            db.commit()
        finally:
            db.close()
        login_response = self._login(email="pay-retry-reservation-expired@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            f"/orders/{graph['order_id']}/payments/retry",
            json=build_create_payment_payload(method="mercadopago"),
            headers=self._retry_headers("retry-order-reservation-expired"),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            "retry not allowed: order cancelled because stock reservation expired",
        )

    def test_retry_payment_rejects_paid_order_over_http(self) -> None:
        user_id = self._create_user(email="pay-retry-paid-order@example.com", verified=True)
        db = self._db()
        try:
            graph = create_order_graph(
                db,
                user_id=user_id,
                order_status="paid",
                with_reservation=False,
            )
            create_retryable_payment(
                db,
                order_id=int(graph["order_id"]),
                method="mercadopago",
                status="cancelled",
            )
        finally:
            db.close()
        login_response = self._login(email="pay-retry-paid-order@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            f"/orders/{graph['order_id']}/payments/retry",
            json=build_create_payment_payload(method="mercadopago"),
            headers=self._retry_headers("retry-order-paid"),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "retry not allowed: order already paid")

    def test_retry_mercadopago_returns_checkout_unavailable_on_provider_failure_over_http(self) -> None:
        user_id = self._create_user(email="pay-retry-provider-fail@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
            create_retryable_payment(
                db,
                order_id=order_id,
                method="mercadopago",
                status="cancelled",
            )
        finally:
            db.close()
        login_response = self._login(email="pay-retry-provider-fail@example.com")
        self.assertEqual(login_response.status_code, 200)

        with patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference",
            side_effect=RuntimeError("boom"),
        ):
            response = self.client.post(
                f"/orders/{order_id}/payments/retry",
                json=build_create_payment_payload(method="mercadopago"),
                headers=self._retry_headers("retry-order-provider-failed"),
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"],
            "retry failed: mercadopago checkout unavailable",
        )

    def test_retry_payment_requires_idempotency_key_over_http(self) -> None:
        user_id = self._create_user(email="pay-retry-missing-key@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
            create_retryable_payment(
                db,
                order_id=order_id,
                method="mercadopago",
                status="cancelled",
            )
        finally:
            db.close()
        login_response = self._login(email="pay-retry-missing-key@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            f"/orders/{order_id}/payments/retry",
            json=build_create_payment_payload(method="mercadopago"),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 422)

    def test_retry_payment_with_same_idempotency_key_replays_same_attempt_over_http(self) -> None:
        user_id = self._create_user(email="pay-retry-same-key@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
            create_retryable_payment(
                db,
                order_id=order_id,
                method="mercadopago",
                status="cancelled",
            )
        finally:
            db.close()
        login_response = self._login(email="pay-retry-same-key@example.com")
        self.assertEqual(login_response.status_code, 200)

        with patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference",
            return_value={
                "id": "pref-retry-same-key",
                "init_point": "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-retry-same-key",
            },
        ):
            first_response = self.client.post(
                f"/orders/{order_id}/payments/retry",
                json=build_create_payment_payload(method="mercadopago"),
                headers=self._retry_headers("retry-order-same-key"),
            )
            second_response = self.client.post(
                f"/orders/{order_id}/payments/retry",
                json=build_create_payment_payload(method="mercadopago"),
                headers=self._retry_headers("retry-order-same-key"),
            )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(
            first_response.json()["data"]["id"],
            second_response.json()["data"]["id"],
        )

    def test_retry_payment_with_different_idempotency_keys_creates_distinct_attempts_over_http(self) -> None:
        user_id = self._create_user(email="pay-retry-different-keys@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
            create_retryable_payment(
                db,
                order_id=order_id,
                method="bank_transfer",
                status="cancelled",
            )
        finally:
            db.close()
        login_response = self._login(email="pay-retry-different-keys@example.com")
        self.assertEqual(login_response.status_code, 200)

        first_response = self.client.post(
            f"/orders/{order_id}/payments/retry",
            json=build_create_payment_payload(method="bank_transfer"),
            headers=self._retry_headers("retry-order-key-1"),
        )
        db = self._db()
        try:
            latest_payment = (
                db.query(Payment)
                .filter(
                    Payment.order_id == order_id,
                    Payment.method == "bank_transfer",
                )
                .order_by(
                    Payment.created_at.desc(),
                    Payment.id.desc(),
                )
                .first()
            )
            assert latest_payment is not None
            latest_payment.status = "cancelled"
            db.commit()
        finally:
            db.close()
        second_response = self.client.post(
            f"/orders/{order_id}/payments/retry",
            json=build_create_payment_payload(method="bank_transfer"),
            headers=self._retry_headers("retry-order-key-2"),
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)
        self.assertNotEqual(
            first_response.json()["data"]["id"],
            second_response.json()["data"]["id"],
        )

    def test_retry_guest_payment_requires_idempotency_key_over_http(self) -> None:
        guest_user_id = self._create_guest_user(email="guest-retry-missing-key@example.com")
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=guest_user_id)
            payment_id = create_retryable_payment(
                db,
                order_id=order_id,
                method="mercadopago",
                status="cancelled",
            )
            public_status_token = str(db.query(Payment).filter(Payment.id == payment_id).first().public_status_token)
        finally:
            db.close()

        response = self.client.post(
            f"/payments/{public_status_token}/retry",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 422)

    def test_retry_guest_payment_with_same_idempotency_key_replays_same_attempt_over_http(self) -> None:
        guest_user_id = self._create_guest_user(email="guest-retry-same-key@example.com")
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=guest_user_id)
            payment_id = create_retryable_payment(
                db,
                order_id=order_id,
                method="mercadopago",
                status="cancelled",
            )
            public_status_token = str(db.query(Payment).filter(Payment.id == payment_id).first().public_status_token)
        finally:
            db.close()

        with patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference",
            return_value={
                "id": "pref-guest-retry-same-key",
                "init_point": "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-guest-retry-same-key",
            },
        ):
            first_response = self.client.post(
                f"/payments/{public_status_token}/retry",
                headers=self._retry_headers("retry-guest-same-key"),
            )
            second_response = self.client.post(
                f"/payments/{public_status_token}/retry",
                headers=self._retry_headers("retry-guest-same-key"),
            )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(
            first_response.json()["data"]["id"],
            second_response.json()["data"]["id"],
        )

    def test_retry_guest_payment_with_different_idempotency_keys_creates_distinct_attempts_over_http(self) -> None:
        guest_user_id = self._create_guest_user(email="guest-retry-different-key@example.com")
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=guest_user_id)
            payment_id = create_retryable_payment(
                db,
                order_id=order_id,
                method="mercadopago",
                status="cancelled",
            )
            public_status_token = str(db.query(Payment).filter(Payment.id == payment_id).first().public_status_token)
        finally:
            db.close()

        with patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference",
            return_value={
                "id": "pref-guest-retry-different-key",
                "init_point": "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-guest-retry-different-key",
            },
        ):
            first_response = self.client.post(
                f"/payments/{public_status_token}/retry",
                headers=self._retry_headers("retry-guest-key-1"),
            )
            db = self._db()
            try:
                latest_payment = (
                    db.query(Payment)
                    .filter(
                        Payment.order_id == order_id,
                        Payment.method == "mercadopago",
                    )
                    .order_by(
                        Payment.created_at.desc(),
                        Payment.id.desc(),
                    )
                    .first()
                )
                assert latest_payment is not None
                latest_payment.status = "cancelled"
                db.commit()
            finally:
                db.close()
            second_response = self.client.post(
                f"/payments/{public_status_token}/retry",
                headers=self._retry_headers("retry-guest-key-2"),
            )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)
        self.assertNotEqual(
            first_response.json()["data"]["id"],
            second_response.json()["data"]["id"],
        )

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

    def test_get_payment_by_id_over_http(self) -> None:
        user_id = self._create_user(email="pay-get-owner@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
            payment_id = create_retryable_payment(
                db,
                order_id=order_id,
                method="bank_transfer",
                status="pending",
            )
        finally:
            db.close()
        login_response = self._login(email="pay-get-owner@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get(f"/payments/{payment_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(int(payload["id"]), payment_id)
        self.assertEqual(payload["method"], "bank_transfer")

    def test_get_payment_by_id_rejects_other_users_payment_over_http(self) -> None:
        owner_id = self._create_user(email="pay-get-owner-2@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=owner_id)
            payment_id = create_retryable_payment(
                db,
                order_id=order_id,
                method="bank_transfer",
                status="pending",
            )
        finally:
            db.close()
        self._create_user(email="pay-get-intruder@example.com", verified=True)
        login_response = self._login(email="pay-get-intruder@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get(f"/payments/{payment_id}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "payment not found")

    def test_admin_list_pending_bank_transfer_payments_over_http(self) -> None:
        user_id = self._create_user(email="pay-bank-owner@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
            pending_id = create_retryable_payment(
                db,
                order_id=order_id,
                method="bank_transfer",
                status="pending",
            )
        finally:
            db.close()
        self._create_user(email="pay-bank-admin@example.com", is_admin=True, verified=True)
        login_response = self._login(email="pay-bank-admin@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/admin/payments/bank-transfer/pending")

        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["id"]), pending_id)

    def test_admin_list_pending_bank_transfer_payments_requires_admin_over_http(self) -> None:
        response = self.client.get("/admin/payments/bank-transfer/pending")
        self.assertEqual(response.status_code, 401)

        self._create_user(email="pay-bank-regular@example.com", verified=True)
        login_response = self._login(email="pay-bank-regular@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/admin/payments/bank-transfer/pending")
        self.assertEqual(response.status_code, 403)

    def test_admin_list_payments_filters_by_status_over_http(self) -> None:
        user_id = self._create_user(email="pay-list-owner@example.com", verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_with_reservation_for_user(db, user_id=user_id)
            create_retryable_payment(db, order_id=order_id, method="bank_transfer", status="pending")
            create_retryable_payment(db, order_id=order_id, method="mercadopago", status="cancelled")
        finally:
            db.close()
        self._create_user(email="pay-list-admin@example.com", is_admin=True, verified=True)
        login_response = self._login(email="pay-list-admin@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/admin/payments", params={"status": "cancelled"})

        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "cancelled")

    def test_admin_list_payments_rejects_invalid_status_over_http(self) -> None:
        self._create_user(email="pay-list-admin-2@example.com", is_admin=True, verified=True)
        login_response = self._login(email="pay-list-admin-2@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/admin/payments", params={"status": "bogus"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "invalid status")

    def test_admin_list_payment_incidents_over_http(self) -> None:
        db = self._db()
        try:
            incident_id = create_payment_incident(db)
        finally:
            db.close()
        self._create_user(email="pay-incidents-admin@example.com", is_admin=True, verified=True)
        login_response = self._login(email="pay-incidents-admin@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/admin/payment-incidents")

        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["id"]), incident_id)
        self.assertEqual(rows[0]["status"], "pending_review")
        self.assertEqual(rows[0]["payment"]["method"], "mercadopago")

    def test_admin_list_payment_incidents_filters_by_status_over_http(self) -> None:
        db = self._db()
        try:
            create_payment_incident(db)
        finally:
            db.close()
        self._create_user(email="pay-incidents-admin-2@example.com", is_admin=True, verified=True)
        login_response = self._login(email="pay-incidents-admin-2@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/admin/payment-incidents", params={"status": "resolved_refunded"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], [])

    def test_admin_list_payment_incidents_requires_admin_over_http(self) -> None:
        response = self.client.get("/admin/payment-incidents")
        self.assertEqual(response.status_code, 401)

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
