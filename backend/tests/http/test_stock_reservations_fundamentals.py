from datetime import UTC, datetime, timedelta

from backend.tests.factories.orders import create_order_graph
from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import Order


class HttpStockReservationsFundamentalsTests(HttpFundamentalsBase):
    def _seed_expired_cancellable_reservation(self) -> int:
        db = self._db()
        try:
            user_id = self._create_guest_user(email="stock-expire-owner@example.com")
            graph = create_order_graph(
                db,
                user_id=user_id,
                order_status="submitted",
                variant_stock=1,
                item_qty=2,
                with_reservation=True,
                reservation_expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
            db.commit()
            return int(graph["order_id"])
        finally:
            db.close()

    def test_expire_stock_reservations_requires_admin_over_http(self) -> None:
        anon_response = self.client.post(
            "/admin/stock-reservations/expire",
            headers=self._origin_headers(),
        )
        self.assertEqual(anon_response.status_code, 401)

        self._create_user(email="stock-expire-regular@example.com", verified=True)
        login_response = self._login(email="stock-expire-regular@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/admin/stock-reservations/expire",
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Admin permissions required")

    def test_expire_stock_reservations_cancels_order_without_stock_over_http(self) -> None:
        order_id = self._seed_expired_cancellable_reservation()
        self._create_user(email="stock-expire-admin@example.com", is_admin=True, verified=True)
        login_response = self._login(email="stock-expire-admin@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/admin/stock-reservations/expire",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["expired_count"], 1)

        db = self._db()
        try:
            order = db.query(Order).filter(Order.id == order_id).first()
            self.assertIsNotNone(order)
            assert order is not None
            self.assertEqual(order.status, "cancelled")
        finally:
            db.close()

    def test_expire_stock_reservations_returns_zero_when_nothing_expired_over_http(self) -> None:
        self._create_user(email="stock-expire-admin-2@example.com", is_admin=True, verified=True)
        login_response = self._login(email="stock-expire-admin-2@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/admin/stock-reservations/expire",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["expired_count"], 0)
