from datetime import UTC, datetime
from unittest.mock import patch

from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import Category, Order, OrderItem, Product, ProductVariant, User


class HttpCheckoutFundamentalsTests(HttpFundamentalsBase):
    def _seed_catalog_with_variants(self) -> dict[str, int]:
        db = self._db()
        try:
            category = Category(name="Draft Cat")
            db.add(category)
            db.flush()

            product = Product(
                name="Draft Product",
                description="demo",
                category_id=int(category.id),
            )
            db.add(product)
            db.flush()

            variant_a = ProductVariant(
                product_id=int(product.id),
                sku="DRAFT-SKU-A",
                size="S",
                color="Blue",
                price=10000,
                stock=8,
                is_active=True,
            )
            variant_b = ProductVariant(
                product_id=int(product.id),
                sku="DRAFT-SKU-B",
                size="M",
                color="Red",
                price=15000,
                stock=6,
                is_active=True,
            )
            variant_inactive = ProductVariant(
                product_id=int(product.id),
                sku="DRAFT-SKU-C",
                size="L",
                color="Gray",
                price=20000,
                stock=5,
                is_active=False,
            )
            db.add_all([variant_a, variant_b, variant_inactive])
            db.commit()
            return {
                "variant_a": int(variant_a.id),
                "variant_b": int(variant_b.id),
                "variant_inactive": int(variant_inactive.id),
            }
        finally:
            db.close()

    def _seed_non_account_user(self) -> int:
        db = self._db()
        try:
            user = User(
                first_name="Ana",
                last_name="Buyer",
                email=f"buyer-{datetime.now(UTC).timestamp()}@example.com",
                phone="1144455566",
                password_hash="!",
                has_account=False,
                is_admin=False,
            )
            db.add(user)
            db.commit()
            return int(user.id)
        finally:
            db.close()

    def _seed_submitted_order_for_user(self, *, user_id: int) -> int:
        db = self._db()
        try:
            category = Category(name=f"order-cat-{datetime.now(UTC).timestamp()}")
            db.add(category)
            db.flush()

            product = Product(
                name="Order Product",
                description="demo",
                category_id=int(category.id),
            )
            db.add(product)
            db.flush()

            variant = ProductVariant(
                product_id=int(product.id),
                sku=f"ORDER-SKU-{datetime.now(UTC).timestamp()}",
                size="M",
                color="Blue",
                price=10000,
                stock=10,
                is_active=True,
            )
            db.add(variant)
            db.flush()

            order = Order(
                user_id=int(user_id),
                status="submitted",
                currency="ARS",
                subtotal=10000,
                discount_total=0,
                total_amount=10000,
                pricing_frozen=True,
                submitted_at=datetime.now(UTC),
            )
            db.add(order)
            db.flush()

            item = OrderItem(
                order_id=int(order.id),
                product_id=int(product.id),
                variant_id=int(variant.id),
                quantity=1,
                unit_price=10000,
                discount_id=None,
                discount_amount=0,
                final_unit_price=10000,
                line_total=10000,
            )
            db.add(item)
            db.commit()
            return int(order.id)
        finally:
            db.close()

    def test_guest_checkout_success_over_http(self) -> None:
        variant_id = self._seed_variant()

        with patch("source.routes.orders_r.enforce_public_guest_checkout_limits", return_value=None):
            response = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "guest@example.com",
                        "first_name": "Guest",
                        "last_name": "Buyer",
                        "phone": "1122334455",
                    },
                    "items": [{"variant_id": variant_id, "quantity": 1}],
                    "website": None,
                },
                headers={
                    **self._origin_headers(),
                    "Idempotency-Key": "guest-key-1",
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertEqual(payload["order"]["status"], "submitted")
        self.assertEqual(payload["customer"]["email"], "guest@example.com")

    def test_guest_checkout_replays_same_idempotency_key_over_http(self) -> None:
        variant_id = self._seed_variant()
        headers = {
            **self._origin_headers(),
            "Idempotency-Key": "guest-replay-key",
        }
        payload = {
            "customer": {
                "email": "same@example.com",
                "first_name": "Guest",
                "last_name": "Buyer",
                "phone": "1122334455",
            },
            "items": [{"variant_id": variant_id, "quantity": 1}],
            "website": None,
        }

        with patch("source.routes.orders_r.enforce_public_guest_checkout_limits", return_value=None):
            first = self.client.post("/checkout/guest", json=payload, headers=headers)
            second = self.client.post("/checkout/guest", json=payload, headers=headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(
            first.json()["data"]["order"]["id"],
            second.json()["data"]["order"]["id"],
        )

    def test_guest_checkout_conflict_for_same_key_different_payload_over_http(self) -> None:
        variant_id = self._seed_variant()
        headers = {
            **self._origin_headers(),
            "Idempotency-Key": "guest-conflict-key",
        }

        with patch("source.routes.orders_r.enforce_public_guest_checkout_limits", return_value=None):
            first = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "conflict@example.com",
                        "first_name": "Guest",
                        "last_name": "Buyer",
                        "phone": "1122334455",
                    },
                    "items": [{"variant_id": variant_id, "quantity": 1}],
                    "website": None,
                },
                headers=headers,
            )
            second = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "conflict@example.com",
                        "first_name": "Guest",
                        "last_name": "Buyer",
                        "phone": "1122334455",
                    },
                    "items": [{"variant_id": variant_id, "quantity": 2}],
                    "website": None,
                },
                headers=headers,
            )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)

    def test_guest_checkout_rejects_registered_email_over_http(self) -> None:
        variant_id = self._seed_variant()
        self._create_user(email="registered@example.com", verified=True)

        with patch("source.routes.orders_r.enforce_public_guest_checkout_limits", return_value=None):
            response = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "registered@example.com",
                        "first_name": "Test",
                        "last_name": "User",
                        "phone": "1122334455",
                    },
                    "items": [{"variant_id": variant_id, "quantity": 1}],
                    "website": None,
                },
                headers={
                    **self._origin_headers(),
                    "Idempotency-Key": "guest-registered-user",
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "registered account requires login")

    def test_guest_checkout_missing_idempotency_key_fails_validation_over_http(self) -> None:
        variant_id = self._seed_variant()

        with patch("source.routes.orders_r.enforce_public_guest_checkout_limits", return_value=None):
            response = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "guest@example.com",
                        "first_name": "Guest",
                        "last_name": "Buyer",
                        "phone": "1122334455",
                    },
                    "items": [{"variant_id": variant_id, "quantity": 1}],
                    "website": None,
                },
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 422)

    def test_replace_draft_groups_duplicate_variants_over_http(self) -> None:
        variants = self._seed_catalog_with_variants()
        self._create_user(email="draft@example.com", verified=True)
        login_response = self._login(email="draft@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.put(
            "/orders/draft/items",
            json={
                "items": [
                    {"variant_id": variants["variant_a"], "quantity": 1},
                    {"variant_id": variants["variant_a"], "quantity": 2},
                    {"variant_id": variants["variant_b"], "quantity": 1},
                ]
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(len(payload["items"]), 2)
        grouped = {item["variant_id"]: item for item in payload["items"]}
        self.assertEqual(grouped[variants["variant_a"]]["quantity"], 3)
        self.assertEqual(grouped[variants["variant_b"]]["quantity"], 1)
        self.assertEqual(payload["total_amount"], 45000)

    def test_replace_draft_allows_empty_payload_and_clears_items_over_http(self) -> None:
        variants = self._seed_catalog_with_variants()
        self._create_user(email="draft-clear@example.com", verified=True)
        login_response = self._login(email="draft-clear@example.com")
        self.assertEqual(login_response.status_code, 200)

        first_response = self.client.put(
            "/orders/draft/items",
            json={"items": [{"variant_id": variants["variant_a"], "quantity": 2}]},
            headers=self._origin_headers(),
        )
        self.assertEqual(first_response.status_code, 200)

        clear_response = self.client.put(
            "/orders/draft/items",
            json={"items": []},
            headers=self._origin_headers(),
        )
        self.assertEqual(clear_response.status_code, 200)
        payload = clear_response.json()["data"]
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["total_amount"], 0)

    def test_replace_draft_rejects_inactive_variant_over_http(self) -> None:
        variants = self._seed_catalog_with_variants()
        self._create_user(email="draft-inactive@example.com", verified=True)
        login_response = self._login(email="draft-inactive@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.put(
            "/orders/draft/items",
            json={"items": [{"variant_id": variants["variant_inactive"], "quantity": 1}]},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], f"variant {variants['variant_inactive']} not found")

    def test_replace_draft_can_be_submitted_after_replacement_over_http(self) -> None:
        variants = self._seed_catalog_with_variants()
        self._create_user(email="draft-submit@example.com", verified=True)
        login_response = self._login(email="draft-submit@example.com")
        self.assertEqual(login_response.status_code, 200)

        replace_response = self.client.put(
            "/orders/draft/items",
            json={
                "items": [
                    {"variant_id": variants["variant_a"], "quantity": 1},
                    {"variant_id": variants["variant_b"], "quantity": 1},
                ]
            },
            headers=self._origin_headers(),
        )
        self.assertEqual(replace_response.status_code, 200)
        order_id = int(replace_response.json()["data"]["id"])

        submit_response = self.client.patch(
            f"/orders/{order_id}/status",
            json={"status": "submitted"},
            headers=self._origin_headers(),
        )
        self.assertEqual(submit_response.status_code, 200)
        self.assertEqual(submit_response.json()["data"]["status"], "submitted")

        db = self._db()
        try:
            count = db.query(OrderItem).filter(OrderItem.order_id == order_id).count()
            self.assertEqual(count, 2)
        finally:
            db.close()

    def test_update_order_status_rejects_paid_transition_over_http(self) -> None:
        user_id = self._create_user(email="status-admin@example.com", is_admin=True, verified=True)
        order_id = self._seed_submitted_order_for_user(user_id=user_id)
        login_response = self._login(email="status-admin@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.patch(
            f"/orders/{order_id}/status",
            json={
                "status": "paid",
                "payment_ref": "MANUAL-REF-1",
                "paid_amount": 10000,
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "paid status must be set through a payment endpoint")

    def test_admin_sale_existing_user_without_payment_over_http(self) -> None:
        variant_id = self._seed_variant()
        user_id = self._seed_non_account_user()
        self._create_user(email="admin-sales@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-sales@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/admin/sales",
            json={
                "customer": {"mode": "existing", "user_id": user_id},
                "items": [{"variant_id": variant_id, "quantity": 2}],
                "register_payment": False,
                "payment": None,
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["order"]["status"], "submitted")
        self.assertIsNone(payload["payment"])
        self.assertFalse(payload["meta"]["customer_created"])
        self.assertFalse(payload["meta"]["payment_registered"])

    def test_admin_sale_new_user_with_bank_transfer_payment_over_http(self) -> None:
        variant_id = self._seed_variant()
        self._create_user(email="admin-sales-bank@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-sales-bank@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/admin/sales",
            json={
                "customer": {
                    "mode": "new",
                    "first_name": "Carlos",
                    "last_name": "Perez",
                    "email": "carlos@example.com",
                    "phone": "1133344455",
                },
                "items": [{"variant_id": variant_id, "quantity": 1}],
                "register_payment": True,
                "payment": {
                    "method": "bank_transfer",
                    "amount_paid": 10000,
                    "payment_ref": "BT-0001",
                },
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["order"]["status"], "paid")
        self.assertEqual(payload["payment"]["method"], "bank_transfer")
        self.assertIsNone(payload["payment"]["change_amount"])
        self.assertTrue(payload["meta"]["payment_registered"])
        self.assertTrue(payload["meta"]["order_paid_email_suppressed"])

    def test_admin_sale_cash_requires_amount_minus_change_equals_total_over_http(self) -> None:
        variant_id = self._seed_variant()
        self._create_user(email="admin-sales-cash-invalid@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-sales-cash-invalid@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/admin/sales",
            json={
                "customer": {
                    "mode": "new",
                    "first_name": "Lara",
                    "last_name": "Gomez",
                    "email": "lara@example.com",
                    "phone": "1199911122",
                },
                "items": [{"variant_id": variant_id, "quantity": 1}],
                "register_payment": True,
                "payment": {
                    "method": "cash",
                    "amount_paid": 12000,
                    "change_amount": 500,
                },
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "amount_paid minus change_amount must match order total")

    def test_admin_sale_cash_persists_change_amount_over_http(self) -> None:
        variant_id = self._seed_variant()
        self._create_user(email="admin-sales-cash@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-sales-cash@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/admin/sales",
            json={
                "customer": {
                    "mode": "new",
                    "first_name": "Nora",
                    "last_name": "Lopez",
                    "email": "nora@example.com",
                    "phone": "1122200011",
                },
                "items": [{"variant_id": variant_id, "quantity": 1}],
                "register_payment": True,
                "payment": {
                    "method": "cash",
                    "amount_paid": 12000,
                    "change_amount": 2000,
                },
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["order"]["status"], "paid")
        self.assertEqual(payload["payment"]["method"], "cash")
        self.assertEqual(payload["payment"]["change_amount"], 2000)

    def test_admin_sale_rejects_change_for_bank_transfer_over_http(self) -> None:
        variant_id = self._seed_variant()
        self._create_user(email="admin-sales-bank-invalid@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-sales-bank-invalid@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/admin/sales",
            json={
                "customer": {
                    "mode": "new",
                    "first_name": "Mora",
                    "last_name": "Ruiz",
                    "email": "mora@example.com",
                    "phone": "1188811122",
                },
                "items": [{"variant_id": variant_id, "quantity": 1}],
                "register_payment": True,
                "payment": {
                    "method": "bank_transfer",
                    "amount_paid": 10000,
                    "change_amount": 0,
                    "payment_ref": "BT-02",
                },
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "change_amount is only allowed for cash payments")
