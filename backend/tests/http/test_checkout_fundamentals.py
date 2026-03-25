from unittest.mock import patch

from backend.tests.factories.http_checkout import (
    create_catalog_with_variants,
    create_non_account_user,
    create_submitted_order_for_user,
)
from backend.tests.http._base import HttpFundamentalsBase


class HttpCheckoutFundamentalsTests(HttpFundamentalsBase):
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

    def test_guest_checkout_mercadopago_success_over_http(self) -> None:
        variant_id = self._seed_variant()

        with patch("source.routes.orders_r.enforce_public_guest_checkout_limits", return_value=None), patch(
            "source.services.payment_s.create_checkout_preference",
            return_value={
                "id": "pref-guest-mp",
                "init_point": "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-guest-mp",
            },
        ):
            response = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "guest-mp@example.com",
                        "first_name": "Guest",
                        "last_name": "Buyer",
                        "phone": "1122334455",
                    },
                    "items": [{"variant_id": variant_id, "quantity": 1}],
                    "payment_method": "mercadopago",
                    "website": None,
                },
                headers={
                    **self._origin_headers(),
                    "Idempotency-Key": "guest-mp-key-1",
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertEqual(payload["payment"]["method"], "mercadopago")
        self.assertEqual(payload["payment"]["provider_status"], "preference_created")
        self.assertIsNotNone(payload["payment"]["provider_payload_data"]["checkout"]["checkout_url"])

    def test_guest_checkout_cash_creates_pending_payment_without_expiration_over_http(self) -> None:
        variant_id = self._seed_variant()

        with patch("source.routes.orders_r.enforce_public_guest_checkout_limits", return_value=None):
            response = self.client.post(
                "/checkout/guest",
                json={
                    "customer": {
                        "email": "guest-cash@example.com",
                        "first_name": "Guest",
                        "last_name": "Cash",
                        "phone": "1122334455",
                    },
                    "items": [{"variant_id": variant_id, "quantity": 1}],
                    "payment_method": "cash",
                    "website": None,
                },
                headers={
                    **self._origin_headers(),
                    "Idempotency-Key": "guest-cash-key-1",
                },
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertEqual(payload["order"]["status"], "submitted")
        self.assertIsNotNone(payload["payment"])
        self.assertEqual(payload["payment"]["method"], "cash")
        self.assertEqual(payload["payment"]["status"], "pending")
        self.assertIsNone(payload["payment"]["expires_at"])

    def test_replace_draft_groups_duplicate_variants_over_http(self) -> None:
        db = self._db()
        try:
            variants = create_catalog_with_variants(db)
        finally:
            db.close()
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
        db = self._db()
        try:
            variants = create_catalog_with_variants(db)
        finally:
            db.close()
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
        db = self._db()
        try:
            variants = create_catalog_with_variants(db)
        finally:
            db.close()
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
        db = self._db()
        try:
            variants = create_catalog_with_variants(db)
        finally:
            db.close()
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

    def test_authenticated_order_payment_accepts_cash_and_keeps_pending_without_expiration_over_http(self) -> None:
        db = self._db()
        try:
            variants = create_catalog_with_variants(db)
        finally:
            db.close()
        self._create_user(email="draft-cash@example.com", verified=True)
        login_response = self._login(email="draft-cash@example.com")
        self.assertEqual(login_response.status_code, 200)

        replace_response = self.client.put(
            "/orders/draft/items",
            json={"items": [{"variant_id": variants["variant_a"], "quantity": 1}]},
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

        payment_response = self.client.post(
            f"/orders/{order_id}/payments",
            json={"method": "cash", "currency": "ARS", "expires_in_minutes": 60},
            headers={**self._origin_headers(), "Idempotency-Key": "logged-cash-payment-1"},
        )

        self.assertEqual(payment_response.status_code, 201)
        payload = payment_response.json()["data"]
        self.assertEqual(payload["method"], "cash")
        self.assertEqual(payload["status"], "pending")
        self.assertIsNone(payload["expires_at"])

    def test_update_order_status_rejects_paid_transition_over_http(self) -> None:
        user_id = self._create_user(email="status-admin@example.com", is_admin=True, verified=True)
        db = self._db()
        try:
            order_id = create_submitted_order_for_user(db, user_id=user_id)
        finally:
            db.close()
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
        db = self._db()
        try:
            user_id = create_non_account_user(db)
        finally:
            db.close()
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

    def test_admin_register_manual_payment_reuses_existing_cash_pending_payment_over_http(self) -> None:
        variant_id = self._seed_variant()
        self._create_user(email="cash-owner@example.com", verified=True)
        admin_user_id = self._create_user(email="admin-register-cash@example.com", is_admin=True, verified=True)
        self.assertGreater(admin_user_id, 0)

        owner_login = self._login(email="cash-owner@example.com")
        self.assertEqual(owner_login.status_code, 200)

        draft_response = self.client.put(
            "/orders/draft/items",
            json={"items": [{"variant_id": variant_id, "quantity": 1}]},
            headers=self._origin_headers(),
        )
        self.assertEqual(draft_response.status_code, 200)
        order_id = int(draft_response.json()["data"]["id"])

        submit_response = self.client.patch(
            f"/orders/{order_id}/status",
            json={"status": "submitted"},
            headers=self._origin_headers(),
        )
        self.assertEqual(submit_response.status_code, 200)

        pending_response = self.client.post(
            f"/orders/{order_id}/payments",
            json={"method": "cash", "currency": "ARS", "expires_in_minutes": 60},
            headers={**self._origin_headers(), "Idempotency-Key": "cash-pending-admin-confirm"},
        )
        self.assertEqual(pending_response.status_code, 201)
        pending_payment = pending_response.json()["data"]
        self.assertEqual(pending_payment["status"], "pending")

        admin_login = self._login(email="admin-register-cash@example.com")
        self.assertEqual(admin_login.status_code, 200)

        confirm_response = self.client.post(
            f"/admin/orders/{order_id}/payments/manual",
            json={
                "method": "cash",
                "paid_amount": 12000,
                "change_amount": 2000,
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(confirm_response.status_code, 200)
        payload = confirm_response.json()["data"]
        self.assertEqual(payload["order"]["status"], "paid")
        self.assertEqual(payload["payment"]["id"], pending_payment["id"])
        self.assertEqual(payload["payment"]["method"], "cash")
        self.assertEqual(payload["payment"]["status"], "paid")
        self.assertEqual(payload["payment"]["change_amount"], 2000)

    def test_admin_register_manual_payment_rejects_order_without_pending_payment_over_http(self) -> None:
        variant_id = self._seed_variant()
        self._create_user(email="no-pending-owner@example.com", verified=True)
        self._create_user(email="admin-no-pending@example.com", is_admin=True, verified=True)

        owner_login = self._login(email="no-pending-owner@example.com")
        self.assertEqual(owner_login.status_code, 200)

        draft_response = self.client.put(
            "/orders/draft/items",
            json={"items": [{"variant_id": variant_id, "quantity": 1}]},
            headers=self._origin_headers(),
        )
        self.assertEqual(draft_response.status_code, 200)
        order_id = int(draft_response.json()["data"]["id"])

        submit_response = self.client.patch(
            f"/orders/{order_id}/status",
            json={"status": "submitted"},
            headers=self._origin_headers(),
        )
        self.assertEqual(submit_response.status_code, 200)

        admin_login = self._login(email="admin-no-pending@example.com")
        self.assertEqual(admin_login.status_code, 200)

        confirm_response = self.client.post(
            f"/admin/orders/{order_id}/payments/manual",
            json={
                "method": "cash",
                "paid_amount": 12000,
                "change_amount": 2000,
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(confirm_response.status_code, 400)
        self.assertEqual(confirm_response.json()["detail"], "pending payment not found for order and method")

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
