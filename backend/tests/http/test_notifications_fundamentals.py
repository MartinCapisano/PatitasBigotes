from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import Notification


class HttpNotificationsFundamentalsTests(HttpFundamentalsBase):
    def _seed_admin_notification(self, *, event_type: str = "order_paid") -> int:
        db = self._db()
        try:
            row = Notification(
                user_id=None,
                role_target="admin",
                event_type=event_type,
                title="Titulo",
                message="Mensaje",
                is_read=False,
            )
            db.add(row)
            db.commit()
            return int(row.id)
        finally:
            db.close()

    def test_list_notifications_requires_auth_over_http(self) -> None:
        response = self.client.get("/notifications")
        self.assertEqual(response.status_code, 401)

    def test_list_notifications_returns_admin_broadcasts_for_admin_over_http(self) -> None:
        notification_id = self._seed_admin_notification()
        self._create_user(email="notif-http-admin@example.com", is_admin=True, verified=True)
        login_response = self._login(email="notif-http-admin@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/notifications")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["data"]), 1)
        self.assertEqual(payload["data"][0]["id"], notification_id)
        self.assertEqual(payload["meta"]["total"], 1)

    def test_list_notifications_hides_admin_broadcasts_from_regular_user_over_http(self) -> None:
        self._seed_admin_notification()
        self._create_user(email="notif-http-regular@example.com", verified=True)
        login_response = self._login(email="notif-http-regular@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/notifications")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], [])

    def test_unread_count_over_http(self) -> None:
        self._seed_admin_notification()
        self._seed_admin_notification(event_type="payment_incident")
        self._create_user(email="notif-http-count@example.com", is_admin=True, verified=True)
        login_response = self._login(email="notif-http-count@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/notifications/unread-count")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["unread_count"], 2)

    def test_read_notification_over_http(self) -> None:
        notification_id = self._seed_admin_notification()
        self._create_user(email="notif-http-read@example.com", is_admin=True, verified=True)
        login_response = self._login(email="notif-http-read@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            f"/notifications/{notification_id}/read",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["is_read"])

    def test_read_notification_missing_returns_404_over_http(self) -> None:
        self._create_user(email="notif-http-read-404@example.com", is_admin=True, verified=True)
        login_response = self._login(email="notif-http-read-404@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/notifications/999999/read",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "notification not found")

    def test_read_all_notifications_over_http(self) -> None:
        self._seed_admin_notification()
        self._seed_admin_notification(event_type="payment_incident")
        self._create_user(email="notif-http-read-all@example.com", is_admin=True, verified=True)
        login_response = self._login(email="notif-http-read-all@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/notifications/read-all",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["updated"], 2)

        follow_up = self.client.get("/notifications/unread-count")
        self.assertEqual(follow_up.json()["data"]["unread_count"], 0)
