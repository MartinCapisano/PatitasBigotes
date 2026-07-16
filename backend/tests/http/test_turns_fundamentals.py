from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import Turn


class HttpTurnsFundamentalsTests(HttpFundamentalsBase):
    def _create_turn_payload(self, *, hour: int = 14) -> dict:
        return {
            "scheduled_at": f"2026-03-02T{hour:02d}:00:00-03:00",
            "notes": "quiero corte",
        }

    def test_create_turn_requires_auth_over_http(self) -> None:
        response = self.client.post(
            "/turns",
            json=self._create_turn_payload(),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 401)

    def test_create_turn_success_over_http(self) -> None:
        self._create_user(email="turns-user@example.com", verified=True)
        login_response = self._login(email="turns-user@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/turns",
            json=self._create_turn_payload(),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["status"], "pending")

    def test_create_turn_rejects_out_of_business_hours_over_http(self) -> None:
        self._create_user(email="turns-early@example.com", verified=True)
        login_response = self._login(email="turns-early@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/turns",
            json=self._create_turn_payload(hour=7),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "turn hour must be between 13:00 and 20:00")

    def test_admin_list_turns_requires_admin_over_http(self) -> None:
        anon_response = self.client.get("/admin/turns")
        self.assertEqual(anon_response.status_code, 401)

        self._create_user(email="turns-regular@example.com", verified=True)
        login_response = self._login(email="turns-regular@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/admin/turns")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Admin permissions required")

    def test_admin_list_turns_returns_created_turn_over_http(self) -> None:
        self._create_user(email="turns-customer@example.com", verified=True)
        customer_login = self._login(email="turns-customer@example.com")
        self.assertEqual(customer_login.status_code, 200)
        create_response = self.client.post(
            "/turns",
            json=self._create_turn_payload(),
            headers=self._origin_headers(),
        )
        self.assertEqual(create_response.status_code, 200)
        turn_id = create_response.json()["data"]["id"]

        self.client.cookies.clear()
        self._create_user(email="turns-admin@example.com", is_admin=True, verified=True)
        admin_login = self._login(email="turns-admin@example.com")
        self.assertEqual(admin_login.status_code, 200)

        response = self.client.get("/admin/turns")

        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["id"]), int(turn_id))
        self.assertEqual(rows[0]["customer"]["first_name"], "Test")

    def test_admin_list_turns_rejects_invalid_status_filter_over_http(self) -> None:
        self._create_user(email="turns-admin-filter@example.com", is_admin=True, verified=True)
        login_response = self._login(email="turns-admin-filter@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/admin/turns", params={"status": "bogus"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "invalid status filter")

    def test_admin_update_turn_status_over_http(self) -> None:
        self._create_user(email="turns-customer-2@example.com", verified=True)
        customer_login = self._login(email="turns-customer-2@example.com")
        self.assertEqual(customer_login.status_code, 200)
        create_response = self.client.post(
            "/turns",
            json=self._create_turn_payload(),
            headers=self._origin_headers(),
        )
        turn_id = create_response.json()["data"]["id"]

        self.client.cookies.clear()
        self._create_user(email="turns-admin-2@example.com", is_admin=True, verified=True)
        admin_login = self._login(email="turns-admin-2@example.com")
        self.assertEqual(admin_login.status_code, 200)

        response = self.client.patch(
            f"/admin/turns/{turn_id}/status",
            json={"status": "confirmed"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "confirmed")

        db = self._db()
        try:
            persisted = db.query(Turn).filter(Turn.id == int(turn_id)).first()
            self.assertIsNotNone(persisted)
            assert persisted is not None
            self.assertEqual(persisted.status, "confirmed")
        finally:
            db.close()

    def test_admin_update_turn_status_requires_admin_over_http(self) -> None:
        response = self.client.patch(
            "/admin/turns/1/status",
            json={"status": "confirmed"},
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 401)

    def test_admin_update_turn_status_rejects_invalid_literal_over_http(self) -> None:
        self._create_user(email="turns-admin-3@example.com", is_admin=True, verified=True)
        login_response = self._login(email="turns-admin-3@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.patch(
            "/admin/turns/1/status",
            json={"status": "bogus"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 422)

    def test_admin_update_turn_status_missing_turn_returns_404_over_http(self) -> None:
        self._create_user(email="turns-admin-4@example.com", is_admin=True, verified=True)
        login_response = self._login(email="turns-admin-4@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.patch(
            "/admin/turns/999999/status",
            json={"status": "confirmed"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "turn not found")
