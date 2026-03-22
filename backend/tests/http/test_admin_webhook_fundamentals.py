from unittest.mock import patch

from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import WebhookEvent, User
from source.services.mercadopago_client import WebhookNoOpError


class HttpAdminAndWebhookFundamentalsTests(HttpFundamentalsBase):
    def _seed_webhook_event(self, *, event_key: str, status: str) -> None:
        db = self._db()
        try:
            db.add(
                WebhookEvent(
                    provider="mercadopago",
                    event_key=event_key,
                    status=status,
                    payload='{"type":"payment","data":{"id":"123"}}',
                    last_error="boom" if status == "dead_letter" else None,
                    attempt_count=3 if status == "dead_letter" else 1,
                )
            )
            db.commit()
        finally:
            db.close()

    def test_admin_route_requires_authentication_over_http(self) -> None:
        response = self.client.get("/admin/catalog")
        self.assertEqual(response.status_code, 401)

    def test_admin_route_rejects_non_admin_user_over_http(self) -> None:
        self._create_user(email="user@example.com", is_admin=False, verified=True)
        login_response = self._login(email="user@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/admin/catalog")
        self.assertEqual(response.status_code, 403)

    def test_admin_route_allows_admin_user_over_http(self) -> None:
        self._create_user(email="admin@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/admin/catalog")
        self.assertEqual(response.status_code, 200)

    def test_admin_access_still_works_after_demotion_until_token_changes(self) -> None:
        user_id = self._create_user(email="demoted@example.com", is_admin=True, verified=True)
        login_response = self._login(email="demoted@example.com")
        self.assertEqual(login_response.status_code, 200)

        db = self._db()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            assert user is not None
            user.is_admin = False
            db.commit()
        finally:
            db.close()

        response = self.client.get("/admin/catalog")
        self.assertEqual(response.status_code, 200)

    def test_webhook_invalid_signature_returns_401_over_http(self) -> None:
        with patch(
            "source.services.mercadopago_client.is_mercadopago_signature_valid",
            return_value=False,
        ):
            response = self.client.post(
                "/payments/webhook/mercadopago",
                json={"type": "payment", "data": {"id": "123"}, "id": "evt-1"},
                headers={"x-signature": "bad", "x-request-id": "req-1"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "invalid signature")

    def test_webhook_success_returns_200_over_http(self) -> None:
        with patch(
            "source.services.mercadopago_client.is_mercadopago_signature_valid",
            return_value=True,
        ), patch(
            "source.services.mercadopago_client.process_mercadopago_event_payload",
            return_value={"id": 99, "status": "paid"},
        ):
            response = self.client.post(
                "/payments/webhook/mercadopago",
                json={"type": "payment", "data": {"id": "123"}, "id": "evt-2"},
                headers={"x-signature": "ok", "x-request-id": "req-2"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["processed"], True)
        self.assertEqual(payload["payment"]["status"], "paid")

    def test_webhook_duplicate_event_returns_processed_false_over_http(self) -> None:
        payload = {"type": "payment", "data": {"id": "555"}, "id": "evt-3"}
        with patch(
            "source.services.mercadopago_client.is_mercadopago_signature_valid",
            return_value=True,
        ), patch(
            "source.services.mercadopago_client.process_mercadopago_event_payload",
            return_value={"id": 100, "status": "paid"},
        ) as mocked_process:
            first = self.client.post(
                "/payments/webhook/mercadopago",
                json=payload,
                headers={"x-signature": "ok", "x-request-id": "req-3"},
            )
            second = self.client.post(
                "/payments/webhook/mercadopago",
                json=payload,
                headers={"x-signature": "ok", "x-request-id": "req-3"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["data"]["processed"], False)
        self.assertEqual(second.json()["data"]["reason"], "duplicate webhook event")
        self.assertEqual(mocked_process.call_count, 1)

    def test_webhook_processing_error_returns_503_over_http(self) -> None:
        with patch(
            "source.services.mercadopago_client.is_mercadopago_signature_valid",
            return_value=True,
        ), patch(
            "source.services.mercadopago_client.process_mercadopago_event_payload",
            side_effect=RuntimeError("boom"),
        ):
            response = self.client.post(
                "/payments/webhook/mercadopago",
                json={"type": "payment", "data": {"id": "999"}, "id": "evt-4"},
                headers={"x-signature": "ok", "x-request-id": "req-4"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "mercadopago webhook processing failed",
        )

        db = self._db()
        try:
            event = db.query(WebhookEvent).filter(WebhookEvent.event_key == "mp:event:evt-4").first()
            self.assertIsNotNone(event)
            assert event is not None
            self.assertEqual(event.status, "processing")
        finally:
            db.close()

    def test_webhook_retryable_noop_returns_processed_false_and_marks_failed_over_http(self) -> None:
        with patch(
            "source.services.mercadopago_client.is_mercadopago_signature_valid",
            return_value=True,
        ), patch(
            "source.services.mercadopago_client.process_mercadopago_event_payload",
            side_effect=WebhookNoOpError("payment not found"),
        ):
            response = self.client.post(
                "/payments/webhook/mercadopago",
                json={"type": "payment", "data": {"id": "123"}, "id": "evt-noop-1"},
                headers={"x-signature": "ok", "x-request-id": "req-noop-1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["processed"], False)
        self.assertEqual(response.json()["data"]["reason"], "payment not found")

    def test_webhook_non_retryable_noop_returns_processed_false_and_marks_processed_over_http(self) -> None:
        with patch(
            "source.services.mercadopago_client.is_mercadopago_signature_valid",
            return_value=True,
        ), patch(
            "source.services.mercadopago_client.process_mercadopago_event_payload",
            side_effect=WebhookNoOpError("unsupported topic"),
        ):
            response = self.client.post(
                "/payments/webhook/mercadopago",
                json={"type": "payment", "data": {"id": "456"}, "id": "evt-noop-2"},
                headers={"x-signature": "ok", "x-request-id": "req-noop-2"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["processed"], False)
        self.assertEqual(response.json()["data"]["reason"], "unsupported topic")

    def test_admin_webhook_replay_success_over_http(self) -> None:
        self._create_user(email="admin-replay@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-replay@example.com")
        self.assertEqual(login_response.status_code, 200)
        self._seed_webhook_event(event_key="mp:event:replay-1", status="dead_letter")

        with patch(
            "source.services.mercadopago_client.process_mercadopago_event_payload",
            return_value={"id": 99, "status": "paid"},
        ):
            response = self.client.post(
                "/admin/webhooks/mercadopago/replay",
                json={"event_key": "mp:event:replay-1"},
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertTrue(payload["processed"])
        self.assertEqual(payload["new_status"], "processed")

    def test_admin_webhook_replay_payment_not_found_stays_retryable_over_http(self) -> None:
        self._create_user(email="admin-replay-noop@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-replay-noop@example.com")
        self.assertEqual(login_response.status_code, 200)
        self._seed_webhook_event(event_key="mp:event:replay-2", status="dead_letter")

        with patch(
            "source.services.mercadopago_client.process_mercadopago_event_payload",
            side_effect=WebhookNoOpError("payment not found"),
        ):
            response = self.client.post(
                "/admin/webhooks/mercadopago/replay",
                json={"event_key": "mp:event:replay-2"},
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertFalse(payload["processed"])
        self.assertEqual(payload["reason"], "payment not found")
        self.assertEqual(payload["new_status"], "dead_letter")

    def test_admin_webhook_replay_processed_status_conflict_over_http(self) -> None:
        self._create_user(email="admin-replay-conflict@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-replay-conflict@example.com")
        self.assertEqual(login_response.status_code, 200)
        self._seed_webhook_event(event_key="mp:event:replay-3", status="processed")

        response = self.client.post(
            "/admin/webhooks/mercadopago/replay",
            json={"event_key": "mp:event:replay-3"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            "webhook event can only be replayed from failed/dead_letter status",
        )

    def test_admin_webhook_replay_unknown_event_returns_not_found_over_http(self) -> None:
        self._create_user(email="admin-replay-missing@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-replay-missing@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/admin/webhooks/mercadopago/replay",
            json={"event_key": "mp:event:404"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "webhook event not found")
