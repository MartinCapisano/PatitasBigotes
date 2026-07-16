from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import Discount


class HttpDiscountsFundamentalsTests(HttpFundamentalsBase):
    def _login_as_admin(self, *, email: str = "discounts-admin@example.com") -> None:
        self._create_user(email=email, is_admin=True, verified=True)
        login_response = self._login(email=email)
        self.assertEqual(login_response.status_code, 200)

    def _discount_payload(self, **overrides) -> dict:
        payload = {
            "name": "10% off",
            "type": "percent",
            "value": 10,
            "scope": "all",
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    def test_discounts_mutations_require_admin_over_http(self) -> None:
        response = self.client.post(
            "/discounts",
            json=self._discount_payload(),
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 401)

        self._create_user(email="discounts-regular@example.com", verified=True)
        login_response = self._login(email="discounts-regular@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/discounts",
            json=self._discount_payload(),
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 403)

    def test_create_discount_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.post(
            "/discounts",
            json=self._discount_payload(),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertEqual(payload["name"], "10% off")
        self.assertEqual(payload["scope"], "all")

        db = self._db()
        try:
            self.assertIsNotNone(db.query(Discount).filter(Discount.id == payload["id"]).first())
        finally:
            db.close()

    def test_create_discount_rejects_empty_name_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.post(
            "/discounts",
            json=self._discount_payload(name="   "),
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "name is required")

    def test_list_discounts_over_http(self) -> None:
        self._login_as_admin()
        create_response = self.client.post(
            "/discounts",
            json=self._discount_payload(),
            headers=self._origin_headers(),
        )
        self.assertEqual(create_response.status_code, 201)

        response = self.client.get("/discounts")

        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "10% off")

    def test_list_discounts_requires_admin_over_http(self) -> None:
        response = self.client.get("/discounts")
        self.assertEqual(response.status_code, 401)

    def test_patch_discount_over_http(self) -> None:
        self._login_as_admin()
        create_response = self.client.post(
            "/discounts",
            json=self._discount_payload(),
            headers=self._origin_headers(),
        )
        discount_id = create_response.json()["data"]["id"]

        response = self.client.patch(
            f"/discounts/{discount_id}",
            json={"is_active": False},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["is_active"])

    def test_patch_discount_missing_returns_404_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.patch(
            "/discounts/999999",
            json={"is_active": False},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "discount not found")

    def test_delete_discount_over_http(self) -> None:
        self._login_as_admin()
        create_response = self.client.post(
            "/discounts",
            json=self._discount_payload(),
            headers=self._origin_headers(),
        )
        discount_id = create_response.json()["data"]["id"]

        response = self.client.delete(
            f"/discounts/{discount_id}",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        db = self._db()
        try:
            self.assertIsNone(db.query(Discount).filter(Discount.id == discount_id).first())
        finally:
            db.close()

    def test_delete_discount_missing_returns_404_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.delete(
            "/discounts/999999",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "discount not found")
