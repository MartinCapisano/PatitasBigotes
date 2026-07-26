"""R01-5: idempotencia de POST /admin/sales tras migrar al context manager.

El endpoint corre bajo get_db_transactional (FailurePolicy.DISCARD). Aca se blinda
lo que la migracion cambio: el replay de una venta ya realizada y el conflicto de
clave reusada, que ahora sube al handler central (R01-3) en vez de pasar por
raise_http_error_from_exception. La matriz completa + concurrencia queda en R01-10.
"""
from backend.tests.factories.http_checkout import create_non_account_user
from backend.tests.http._base import HttpFundamentalsBase


class AdminSalesIdempotencyTests(HttpFundamentalsBase):
    def _login_admin(self) -> None:
        self._create_user(email="admin-idem@example.com", is_admin=True, verified=True)
        login = self._login(email="admin-idem@example.com")
        self.assertEqual(login.status_code, 200)

    def _sale_payload(self, user_id: int, variant_id: int) -> dict:
        return {
            "customer": {"mode": "existing", "user_id": user_id},
            "items": [{"variant_id": variant_id, "quantity": 1}],
            "register_payment": False,
            "payment": None,
        }

    def test_same_key_replays_without_creating_a_second_sale(self) -> None:
        variant_id = self._seed_variant()
        db = self._db()
        try:
            user_id = create_non_account_user(db)
        finally:
            db.close()
        self._login_admin()
        headers = {**self._origin_headers(), "Idempotency-Key": "admin-sale-key-1"}
        body = self._sale_payload(user_id, variant_id)

        first = self.client.post("/admin/sales", json=body, headers=headers)
        self.assertEqual(first.status_code, 200)

        second = self.client.post("/admin/sales", json=body, headers=headers)
        self.assertEqual(second.status_code, 200)
        # Replay: misma respuesta, misma orden, sin crear una segunda venta.
        self.assertEqual(
            second.json()["data"]["order"]["id"],
            first.json()["data"]["order"]["id"],
        )

    def test_same_key_different_payload_conflicts_409(self) -> None:
        variant_id = self._seed_variant()
        db = self._db()
        try:
            user_id = create_non_account_user(db)
        finally:
            db.close()
        self._login_admin()
        headers = {**self._origin_headers(), "Idempotency-Key": "admin-sale-key-2"}

        first = self.client.post(
            "/admin/sales",
            json=self._sale_payload(user_id, variant_id),
            headers=headers,
        )
        self.assertEqual(first.status_code, 200)

        # Misma clave, payload distinto (cantidad 2) -> conflicto via handler central.
        conflicting = dict(self._sale_payload(user_id, variant_id))
        conflicting["items"] = [{"variant_id": variant_id, "quantity": 2}]
        second = self.client.post("/admin/sales", json=conflicting, headers=headers)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(
            second.json()["detail"],
            "idempotency key already used with a different payload",
        )

    def test_without_key_idempotency_is_disabled(self) -> None:
        variant_id = self._seed_variant()
        db = self._db()
        try:
            user_id = create_non_account_user(db)
        finally:
            db.close()
        self._login_admin()
        body = self._sale_payload(user_id, variant_id)

        # Sin Idempotency-Key: cada request crea su propia venta.
        first = self.client.post("/admin/sales", json=body, headers=self._origin_headers())
        second = self.client.post("/admin/sales", json=body, headers=self._origin_headers())
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(
            first.json()["data"]["order"]["id"],
            second.json()["data"]["order"]["id"],
        )
