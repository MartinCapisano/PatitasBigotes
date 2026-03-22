from unittest.mock import patch

from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import AuthActionToken


class HttpAuthFundamentalsTests(HttpFundamentalsBase):
    def test_register_login_and_me_flow_over_http(self) -> None:
        with patch("source.routes.auth_r.send_email_verification") as mocked_send:
            register_response = self.client.post(
                "/auth/register",
                json={
                    "first_name": "Ana",
                    "last_name": "Lopez",
                    "email": "ana@example.com",
                    "password": "Strong!123",
                },
                headers=self._origin_headers(),
            )
        self.assertEqual(register_response.status_code, 201)
        self.assertEqual(register_response.json()["data"]["registered"], True)
        mocked_send.assert_called_once()

        token = self._extract_token_from_mock(mocked_send, field="verify_link")
        verify_response = self.client.post(
            "/auth/email/verify/confirm",
            json={"token": token},
            headers=self._origin_headers(),
        )
        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.json()["data"]["verified"], True)

        login_response = self._login(email="ana@example.com")
        self.assertEqual(login_response.status_code, 200)
        payload = login_response.json()["data"]
        self.assertTrue(payload["logged_in"])
        self.assertNotIn("access_token", payload)
        self.assertNotIn("refresh_token", payload)
        self.assertIn("pb_at", login_response.cookies)
        self.assertIn("pb_rt", login_response.cookies)

        me_response = self.client.get("/auth/me")
        self.assertEqual(me_response.status_code, 200)
        me_payload = me_response.json()["data"]
        self.assertEqual(me_payload["email"], "ana@example.com")
        self.assertEqual(me_payload["email_verified"], True)

    def test_login_unverified_user_returns_403_over_http(self) -> None:
        self._create_user(
            email="nover@example.com",
            verified=False,
        )

        response = self._login(email="nover@example.com")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "email not verified")

    def test_refresh_and_logout_work_over_http(self) -> None:
        self._create_user(email="refresh@example.com")

        login_response = self._login(email="refresh@example.com")
        self.assertEqual(login_response.status_code, 200)

        refresh_response = self.client.post(
            "/auth/refresh",
            headers=self._origin_headers(),
        )
        self.assertEqual(refresh_response.status_code, 200)
        self.assertEqual(refresh_response.json()["data"]["refreshed"], True)
        self.assertIn("pb_at", refresh_response.cookies)
        self.assertIn("pb_rt", refresh_response.cookies)

        logout_response = self.client.post(
            "/auth/logout",
            headers=self._origin_headers(),
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.json()["data"]["logged_out"], True)

        me_response = self.client.get("/auth/me")
        self.assertEqual(me_response.status_code, 401)

    def test_email_verify_request_returns_200_and_resends_token_over_http(self) -> None:
        self._create_user(email="verify-request@example.com", verified=False)

        with patch("source.routes.auth_r.send_email_verification") as mocked_send:
            response = self.client.post(
                "/auth/email/verify/request",
                json={"email": "verify-request@example.com"},
                headers=self._origin_headers(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["requested"], True)
        mocked_send.assert_called_once()

    def test_email_verify_confirm_token_is_single_use_over_http(self) -> None:
        with patch("source.routes.auth_r.send_email_verification") as mocked_send:
            register_response = self.client.post(
                "/auth/register",
                json={
                    "first_name": "Vic",
                    "last_name": "Tor",
                    "email": "victor@example.com",
                    "password": "Strong!123",
                },
                headers=self._origin_headers(),
            )
        self.assertEqual(register_response.status_code, 201)

        token = self._extract_token_from_mock(mocked_send, field="verify_link")
        first_confirm = self.client.post(
            "/auth/email/verify/confirm",
            json={"token": token},
            headers=self._origin_headers(),
        )
        second_confirm = self.client.post(
            "/auth/email/verify/confirm",
            json={"token": token},
            headers=self._origin_headers(),
        )

        self.assertEqual(first_confirm.status_code, 200)
        self.assertEqual(second_confirm.status_code, 400)
        self.assertEqual(second_confirm.json()["detail"], "token already used")

    def test_email_verify_confirm_rejects_expired_token_over_http(self) -> None:
        with patch("source.routes.auth_r.send_email_verification") as mocked_send:
            register_response = self.client.post(
                "/auth/register",
                json={
                    "first_name": "Ex",
                    "last_name": "Pired",
                    "email": "expired@example.com",
                    "password": "Strong!123",
                },
                headers=self._origin_headers(),
            )
        self.assertEqual(register_response.status_code, 201)
        token = self._extract_token_from_mock(mocked_send, field="verify_link")

        db = self._db()
        try:
            row = db.query(AuthActionToken).filter(AuthActionToken.action == "email_verify").first()
            self.assertIsNotNone(row)
            assert row is not None
            from datetime import UTC, datetime, timedelta

            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            db.commit()
        finally:
            db.close()

        response = self.client.post(
            "/auth/email/verify/confirm",
            json={"token": token},
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "token expired")

    def test_email_verify_resend_invalidates_previous_token_over_http(self) -> None:
        with patch("source.routes.auth_r.send_email_verification") as mocked_send:
            register_response = self.client.post(
                "/auth/register",
                json={
                    "first_name": "Re",
                    "last_name": "Send",
                    "email": "resend@example.com",
                    "password": "Strong!123",
                },
                headers=self._origin_headers(),
            )
            self.assertEqual(register_response.status_code, 201)
            first_token = self._extract_token_from_mock(mocked_send, field="verify_link")

            resend_response = self.client.post(
                "/auth/email/verify/request",
                json={"email": "resend@example.com"},
                headers=self._origin_headers(),
            )
            self.assertEqual(resend_response.status_code, 200)
            second_token = self._extract_token_from_mock(mocked_send, field="verify_link")

        self.assertNotEqual(first_token, second_token)

        old_response = self.client.post(
            "/auth/email/verify/confirm",
            json={"token": first_token},
            headers=self._origin_headers(),
        )
        new_response = self.client.post(
            "/auth/email/verify/confirm",
            json={"token": second_token},
            headers=self._origin_headers(),
        )

        self.assertEqual(old_response.status_code, 400)
        self.assertEqual(old_response.json()["detail"], "token already used")
        self.assertEqual(new_response.status_code, 200)

    def test_password_reset_request_is_non_enumerable_over_http(self) -> None:
        self._create_user(email="reset@example.com", verified=True)

        with patch("source.routes.auth_r.send_password_reset") as mocked_send:
            existing = self.client.post(
                "/auth/password/reset/request",
                json={"email": "reset@example.com"},
                headers=self._origin_headers(),
            )
            missing = self.client.post(
                "/auth/password/reset/request",
                json={"email": "missing@example.com"},
                headers=self._origin_headers(),
            )
        self.assertEqual(existing.status_code, 200)
        self.assertEqual(missing.status_code, 200)
        self.assertEqual(existing.json(), missing.json())
        mocked_send.assert_called_once()

    def test_password_reset_confirm_updates_password_over_http(self) -> None:
        self._create_user(email="reset-confirm@example.com", verified=True)

        with patch("source.routes.auth_r.send_password_reset") as mocked_send:
            request_response = self.client.post(
                "/auth/password/reset/request",
                json={"email": "reset-confirm@example.com"},
                headers=self._origin_headers(),
            )
        self.assertEqual(request_response.status_code, 200)
        token = self._extract_token_from_mock(mocked_send, field="reset_link")

        confirm_response = self.client.post(
            "/auth/password/reset/confirm",
            json={"token": token, "new_password": "Changed!123"},
            headers=self._origin_headers(),
        )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(confirm_response.json()["data"]["password_reset"], True)

        login_response = self._login(
            email="reset-confirm@example.com",
            password="Changed!123",
        )
        self.assertEqual(login_response.status_code, 200)

    def test_password_reset_invalidates_existing_access_and_refresh_tokens_over_http(self) -> None:
        self._create_user(email="reset-session@example.com", verified=True)
        login_response = self._login(email="reset-session@example.com")
        self.assertEqual(login_response.status_code, 200)

        with patch("source.routes.auth_r.send_password_reset") as mocked_send:
            request_response = self.client.post(
                "/auth/password/reset/request",
                json={"email": "reset-session@example.com"},
                headers=self._origin_headers(),
            )
        self.assertEqual(request_response.status_code, 200)
        token = self._extract_token_from_mock(mocked_send, field="reset_link")

        confirm_response = self.client.post(
            "/auth/password/reset/confirm",
            json={"token": token, "new_password": "Changed!123"},
            headers=self._origin_headers(),
        )
        self.assertEqual(confirm_response.status_code, 200)

        me_response = self.client.get("/auth/me")
        self.assertEqual(me_response.status_code, 401)
        self.assertEqual(me_response.json()["detail"], "Invalid or expired token")

        refresh_response = self.client.post(
            "/auth/refresh",
            headers=self._origin_headers(),
        )
        self.assertEqual(refresh_response.status_code, 404)
        self.assertEqual(refresh_response.json()["detail"], "refresh session not found")

    def test_password_change_requires_current_password_over_http(self) -> None:
        self._create_user(email="change@example.com", verified=True)
        login_response = self._login(email="change@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/auth/password/change",
            json={
                "current_password": "wrong!123",
                "new_password": "Another!123",
            },
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "current password is invalid")

    def test_password_change_invalidates_existing_access_and_refresh_tokens_over_http(self) -> None:
        self._create_user(email="change-session@example.com", verified=True)
        login_response = self._login(email="change-session@example.com")
        self.assertEqual(login_response.status_code, 200)

        change_response = self.client.post(
            "/auth/password/change",
            json={
                "current_password": "Strong!123",
                "new_password": "Another!123",
            },
            headers=self._origin_headers(),
        )
        self.assertEqual(change_response.status_code, 200)

        me_response = self.client.get("/auth/me")
        self.assertEqual(me_response.status_code, 401)
        self.assertEqual(me_response.json()["detail"], "Invalid or expired token")

        refresh_response = self.client.post(
            "/auth/refresh",
            headers=self._origin_headers(),
        )
        self.assertEqual(refresh_response.status_code, 404)
        self.assertEqual(refresh_response.json()["detail"], "refresh session not found")

    def test_password_reset_request_rate_limit_returns_429_over_http(self) -> None:
        first = self.client.post(
            "/auth/password/reset/request",
            json={"email": "rate-reset@example.com"},
            headers=self._origin_headers(),
        )
        second = self.client.post(
            "/auth/password/reset/request",
            json={"email": "rate-reset@example.com"},
            headers=self._origin_headers(),
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_email_verify_request_rate_limit_returns_429_over_http(self) -> None:
        first = self.client.post(
            "/auth/email/verify/request",
            json={"email": "rate-verify@example.com"},
            headers=self._origin_headers(),
        )
        second = self.client.post(
            "/auth/email/verify/request",
            json={"email": "rate-verify@example.com"},
            headers=self._origin_headers(),
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
