"""R03-5: matriz HTTP del checkout autenticado unificado (`POST /checkout`).

Espeja la matriz del guest (`test_checkout_fundamentals`, `test_guest_checkout_recovery`,
`test_provider_failure_checkout`) para el endpoint autenticado, con foco en el gap que
R-03 cierra: colapsar los 3 requests encadenados en una sola transacción idempotente
con recuperación de Mercado Pago y sin dejar un `submitted` sin pago.

Los 4 caminos (bank_transfer, cash, MP ok, MP falla→recuperación) + replay + acquire
concurrente. El acquire concurrente se ejerce de forma determinista sembrando un record
'processing' con el mismo request_hash (misma técnica que test_idempotency_twin_key):
la carrera real de dos conexiones necesita el índice único de PostgreSQL, no reproducible
en el SQLite/StaticPool del suite.
"""
import json
from unittest.mock import patch

from datetime import UTC, datetime, timedelta

from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import IdempotencyRecord, Order, Payment
from source.schemas import AuthenticatedCheckoutRequest
from source.services.idempotency_s import (
    build_authenticated_checkout_scope,
    canonicalize_payload,
    hash_payload,
)
from source.services.payment_s import PAYMENT_PROVIDER_SETUP_FAILED

_MP_SUCCESS = {
    "id": "pref-auth-mp",
    "init_point": "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-auth-mp",
}


class AuthenticatedCheckoutFundamentalsTests(HttpFundamentalsBase):
    def _auth(self, email: str) -> int:
        """Crea un usuario con cuenta, lo loguea (setea cookies en el client) y
        devuelve su id."""
        user_id = self._create_user(email=email, verified=True)
        login = self._login(email=email)
        self.assertEqual(login.status_code, 200, login.text)
        return user_id

    def _headers(self, key: str) -> dict:
        return {**self._origin_headers(), "Idempotency-Key": key}

    def _body(self, variant_id: int, *, payment_method: str | None = None, quantity: int = 1) -> dict:
        body: dict = {"items": [{"variant_id": variant_id, "quantity": quantity}]}
        if payment_method is not None:
            body["payment_method"] = payment_method
        return body

    # --- Los 4 caminos --------------------------------------------------------

    def test_bank_transfer_success(self) -> None:
        variant_id = self._seed_variant()
        self._auth("auth-bank@example.com")

        response = self.client.post(
            "/checkout",
            json=self._body(variant_id, payment_method="bank_transfer", quantity=2),
            headers=self._headers("auth-bank-1"),
        )

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()["data"]
        self.assertEqual(set(payload.keys()), {"order", "customer", "payment"})
        self.assertEqual(payload["order"]["status"], "submitted")
        self.assertTrue(payload["order"]["pricing_frozen"])
        self.assertEqual(payload["customer"]["email"], "auth-bank@example.com")
        self.assertEqual(payload["payment"]["method"], "bank_transfer")
        self.assertEqual(payload["payment"]["status"], "pending")
        # El pago se serializa client-safe: nunca expone el crudo del webhook.
        self.assertNotIn("provider_payload", payload["payment"])

    def test_cash_creates_pending_payment_without_expiration(self) -> None:
        variant_id = self._seed_variant()
        self._auth("auth-cash@example.com")

        response = self.client.post(
            "/checkout",
            json=self._body(variant_id, payment_method="cash"),
            headers=self._headers("auth-cash-1"),
        )

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()["data"]
        self.assertEqual(payload["order"]["status"], "submitted")
        self.assertEqual(payload["payment"]["method"], "cash")
        self.assertEqual(payload["payment"]["status"], "pending")
        self.assertIsNone(payload["payment"]["expires_at"])

    def test_mercadopago_success(self) -> None:
        variant_id = self._seed_variant()
        self._auth("auth-mp@example.com")

        with patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference",
            return_value=_MP_SUCCESS,
        ):
            response = self.client.post(
                "/checkout",
                json=self._body(variant_id, payment_method="mercadopago"),
                headers=self._headers("auth-mp-1"),
            )

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()["data"]
        self.assertEqual(payload["payment"]["method"], "mercadopago")
        self.assertEqual(payload["payment"]["provider_status"], "preference_created")
        self.assertIsNotNone(
            payload["payment"]["provider_payload_data"]["checkout"]["checkout_url"]
        )

    def test_mercadopago_failure_marks_failed_without_orphan_submitted(self) -> None:
        """Invariante del gap: un fallo de MP NUNCA deja un `submitted` sin pago
        silencioso. La orden queda submitted PERO con su pago en setup_failed, y el
        record queda 'failed' enlazando order_id+payment_id → recuperable."""
        variant_id = self._seed_variant()
        user_id = self._auth("auth-mp-fail@example.com")

        with patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference",
            side_effect=Exception("mp down"),
        ):
            response = self.client.post(
                "/checkout",
                json=self._body(variant_id, payment_method="mercadopago"),
                headers=self._headers("auth-mp-fail-1"),
            )

        self.assertEqual(response.status_code, 502, response.text)

        db = self._db()
        try:
            order = db.query(Order).filter(Order.user_id == user_id).first()
            self.assertIsNotNone(order)
            self.assertEqual(str(order.status), "submitted")

            # No es un submitted huérfano: existe el pago (en setup_failed).
            payment = db.query(Payment).filter(Payment.order_id == int(order.id)).first()
            self.assertIsNotNone(payment)
            self.assertEqual(str(payment.provider_status), PAYMENT_PROVIDER_SETUP_FAILED)

            # Y el record 'failed' enlaza order_id+payment_id → un retry puede recuperar.
            record = (
                db.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.scope == build_authenticated_checkout_scope(user_id),
                    IdempotencyRecord.idempotency_key == "auth-mp-fail-1",
                )
                .first()
            )
            self.assertIsNotNone(record)
            self.assertEqual(str(record.status), "failed")
            stored = json.loads(record.response_payload)
            self.assertEqual(int(stored["order_id"]), int(order.id))
            self.assertEqual(int(stored["payment_id"]), int(payment.id))
        finally:
            db.close()

    def test_failed_mp_recovers_same_order_and_payment_on_retry(self) -> None:
        """Reintento con la MISMA key tras un fallo de MP: cae en RECOVER, re-inicializa
        el checkout y devuelve el MISMO pago y la MISMA orden (no crea una nueva)."""
        variant_id = self._seed_variant()
        user_id = self._auth("auth-mp-recover@example.com")
        body = self._body(variant_id, payment_method="mercadopago")
        headers = self._headers("auth-mp-recover-1")

        with patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference",
            side_effect=Exception("mp down"),
        ):
            first = self.client.post("/checkout", json=body, headers=headers)
        self.assertEqual(first.status_code, 502, first.text)

        with patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference",
            return_value=_MP_SUCCESS,
        ):
            second = self.client.post("/checkout", json=body, headers=headers)

        self.assertEqual(second.status_code, 201, second.text)
        payload = second.json()["data"]
        self.assertEqual(payload["payment"]["provider_status"], "preference_created")

        db = self._db()
        try:
            orders = db.query(Order).filter(Order.user_id == user_id).all()
            self.assertEqual(len(orders), 1, "el retry NO debe crear una orden nueva")
            self.assertEqual(int(payload["order"]["id"]), int(orders[0].id))

            payments = (
                db.query(Payment).filter(Payment.order_id == int(orders[0].id)).all()
            )
            self.assertEqual(len(payments), 1, "el retry NO debe crear un pago nuevo")
            self.assertEqual(int(payload["payment"]["id"]), int(payments[0].id))

            record = (
                db.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.scope == build_authenticated_checkout_scope(user_id),
                    IdempotencyRecord.idempotency_key == "auth-mp-recover-1",
                )
                .first()
            )
            self.assertEqual(str(record.status), "completed")
        finally:
            db.close()

    # --- Replay + concurrencia ------------------------------------------------

    def test_replay_same_key_does_not_create_double_order(self) -> None:
        variant_id = self._seed_variant()
        user_id = self._auth("auth-replay@example.com")
        body = self._body(variant_id, payment_method="bank_transfer")
        headers = self._headers("auth-replay-1")

        first = self.client.post("/checkout", json=body, headers=headers)
        second = self.client.post("/checkout", json=body, headers=headers)

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(
            int(first.json()["data"]["order"]["id"]),
            int(second.json()["data"]["order"]["id"]),
        )

        db = self._db()
        try:
            self.assertEqual(
                db.query(Order).filter(Order.user_id == user_id).count(),
                1,
                "el replay NO debe crear una segunda orden",
            )
        finally:
            db.close()

    def test_twin_key_in_progress_conflicts_409(self) -> None:
        variant_id = self._seed_variant()
        user_id = self._auth("auth-twin@example.com")
        key = "auth-twin-key"
        body = self._body(variant_id, payment_method="bank_transfer")

        # Se siembra un record 'processing' con el MISMO request_hash que calcula el
        # endpoint (model_dump del schema), para caer en el camino 'processing' y no en
        # el conflicto de clave reusada.
        request_hash = hash_payload(
            canonicalize_payload(AuthenticatedCheckoutRequest(**body).model_dump())
        )
        db = self._db()
        try:
            now = datetime.now(UTC)
            db.add(
                IdempotencyRecord(
                    scope=build_authenticated_checkout_scope(user_id),
                    idempotency_key=key,
                    request_hash=request_hash,
                    response_payload="{}",
                    status="processing",
                    created_at=now,
                    expires_at=now + timedelta(hours=24),
                )
            )
            db.commit()
        finally:
            db.close()

        response = self.client.post("/checkout", json=body, headers=self._headers(key))

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            response.json()["detail"], "idempotent request already in progress"
        )

    # --- Bordes ---------------------------------------------------------------

    def test_conflict_same_key_different_payload_409(self) -> None:
        variant_id = self._seed_variant()
        self._auth("auth-conflict@example.com")
        headers = self._headers("auth-conflict-1")

        first = self.client.post(
            "/checkout",
            json=self._body(variant_id, payment_method="bank_transfer", quantity=1),
            headers=headers,
        )
        second = self.client.post(
            "/checkout",
            json=self._body(variant_id, payment_method="bank_transfer", quantity=2),
            headers=headers,
        )

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 409, second.text)

    def test_requires_authentication_401(self) -> None:
        variant_id = self._seed_variant()
        response = self.client.post(
            "/checkout",
            json=self._body(variant_id, payment_method="bank_transfer"),
            headers=self._headers("auth-noauth-1"),
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_missing_idempotency_key_is_422(self) -> None:
        variant_id = self._seed_variant()
        self._auth("auth-nokey@example.com")
        response = self.client.post(
            "/checkout",
            json=self._body(variant_id, payment_method="bank_transfer"),
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 422, response.text)
