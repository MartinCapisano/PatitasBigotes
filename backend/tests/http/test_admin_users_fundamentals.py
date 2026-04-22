from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import User, UserRefreshSession


class HttpAdminUsersFundamentalsTests(HttpFundamentalsBase):
    def _admin_payload(self, *, email: str = "new-admin@example.com") -> dict:
        return {
            "first_name": "New",
            "last_name": "Admin",
            "email": email,
            "password": "Admin!123",
            "phone": "1122334455",
        }

    def test_require_admin_uses_current_db_admin_status_over_http(self) -> None:
        user_id = self._create_user(
            email="stale-admin@example.com",
            is_admin=True,
            verified=True,
        )
        login_response = self._login(email="stale-admin@example.com")
        self.assertEqual(login_response.status_code, 200)

        db = self._db()
        try:
            user = db.query(User).filter(User.id == int(user_id)).one()
            user.is_admin = False
            db.commit()
        finally:
            db.close()

        response = self.client.get("/admin/catalog")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Admin permissions required")

    def test_admin_can_create_admin_user_over_http(self) -> None:
        self._create_user(email="creator@example.com", is_admin=True, verified=True)
        login_response = self._login(email="creator@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/admin/users",
            json=self._admin_payload(),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertEqual(payload["email"], "new-admin@example.com")
        self.assertTrue(payload["has_account"])
        self.assertTrue(payload["is_admin"])
        self.assertTrue(payload["email_verified"])

        new_admin_login = self._login(email="new-admin@example.com", password="Admin!123")
        self.assertEqual(new_admin_login.status_code, 200)

    def test_create_admin_rejects_existing_email_over_http(self) -> None:
        self._create_user(email="creator-existing@example.com", is_admin=True, verified=True)
        self._create_user(email="already@example.com", is_admin=False, verified=True)
        login_response = self._login(email="creator-existing@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/admin/users",
            json=self._admin_payload(email="already@example.com"),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "email already exists")

    def test_create_admin_requires_admin_auth_over_http(self) -> None:
        response = self.client.post(
            "/admin/users",
            json=self._admin_payload(email="anon-admin@example.com"),
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 401)

        self._create_user(email="regular@example.com", is_admin=False, verified=True)
        login_response = self._login(email="regular@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/admin/users",
            json=self._admin_payload(email="blocked-admin@example.com"),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Admin permissions required")

    def test_admin_can_revoke_other_admin_and_invalidate_sessions_over_http(self) -> None:
        target_user_id = self._create_user(
            email="target-admin@example.com",
            is_admin=True,
            verified=True,
        )
        self._create_user(email="actor-admin@example.com", is_admin=True, verified=True)

        target_login = self._login(email="target-admin@example.com")
        self.assertEqual(target_login.status_code, 200)
        target_access_token = target_login.cookies["pb_at"]

        actor_login = self._login(email="actor-admin@example.com")
        self.assertEqual(actor_login.status_code, 200)

        response = self.client.post(
            f"/admin/users/{target_user_id}/revoke-admin",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["id"], target_user_id)
        self.assertEqual(payload["email"], "target-admin@example.com")
        self.assertFalse(payload["is_admin"])
        self.assertEqual(payload["token_version"], 2)
        self.assertTrue(payload["admin_revoked"])

        db = self._db()
        try:
            target = db.query(User).filter(User.id == int(target_user_id)).one()
            self.assertFalse(target.is_admin)
            self.assertEqual(int(target.token_version), 2)
            refresh_session = (
                db.query(UserRefreshSession)
                .filter(UserRefreshSession.user_id == int(target_user_id))
                .first()
            )
            self.assertIsNone(refresh_session)
        finally:
            db.close()

        self.client.cookies.clear()
        self.client.cookies.set("pb_at", target_access_token)
        stale_response = self.client.get("/admin/catalog")
        self.assertEqual(stale_response.status_code, 401)

    def test_revoke_admin_rejects_self_missing_and_non_admin_over_http(self) -> None:
        actor_user_id = self._create_user(
            email="revoke-actor@example.com",
            is_admin=True,
            verified=True,
        )
        non_admin_user_id = self._create_user(
            email="not-admin@example.com",
            is_admin=False,
            verified=True,
        )
        login_response = self._login(email="revoke-actor@example.com")
        self.assertEqual(login_response.status_code, 200)

        self_response = self.client.post(
            f"/admin/users/{actor_user_id}/revoke-admin",
            headers=self._origin_headers(),
        )
        self.assertEqual(self_response.status_code, 400)
        self.assertEqual(self_response.json()["detail"], "cannot revoke own admin status")

        missing_response = self.client.post(
            "/admin/users/999999/revoke-admin",
            headers=self._origin_headers(),
        )
        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(missing_response.json()["detail"], "user not found")

        non_admin_response = self.client.post(
            f"/admin/users/{non_admin_user_id}/revoke-admin",
            headers=self._origin_headers(),
        )
        self.assertEqual(non_admin_response.status_code, 409)
        self.assertEqual(non_admin_response.json()["detail"], "user is not admin")
