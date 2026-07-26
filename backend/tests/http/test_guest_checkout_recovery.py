"""R01-6 / R01-10: cobertura del camino 'failed' (RECOVER) del guest checkout
(`_recover_guest_checkout`).

R01-6 cubrio el sub-caso determinista: un record fallido sin order_id/payment_id no
puede recuperarse y devuelve 502 con el detail guardado. R01-10 completa las dos
celdas que faltaban de la matriz: el re-init de Mercado Pago que sale bien (RECOVER
-> 201, record completed) y el que vuelve a fallar (RECOVER -> 502, record sigue
failed). Ambas parten del estado real que deja un primer checkout que revienta en la
inicializacion de MP (mismo montaje que test_provider_failure_checkout).
"""
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import IdempotencyRecord, Payment
from source.schemas import PublicGuestCheckoutRequest
from source.services.idempotency_s import (
    build_guest_checkout_scope,
    canonicalize_payload,
    hash_payload,
)
from source.services.payment_s import PAYMENT_PROVIDER_SETUP_FAILED


class GuestCheckoutRecoveryTests(HttpFundamentalsBase):
    def _mp_payload(self, variant_id: int, email: str) -> dict:
        return {
            "customer": {
                "email": email,
                "first_name": "Guest",
                "last_name": "Buyer",
                "phone": "1122334455",
            },
            "items": [{"variant_id": variant_id, "quantity": 1}],
            "payment_method": "mercadopago",
            "website": None,
        }

    def _fail_first_checkout(self, *, variant_id: int, email: str, key: str) -> dict:
        """Corre un primer checkout que revienta en el init de MP y deja el estado
        real que dispara el camino RECOVER: order + payment en setup_failed + record
        'failed' con order_id/payment_id. Devuelve el response_payload guardado."""
        payload = self._mp_payload(variant_id, email)
        headers = {**self._origin_headers(), "Idempotency-Key": key}
        with patch(
            "source.routes.orders_r.enforce_public_guest_checkout_limits",
            return_value=None,
        ), patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference",
            side_effect=Exception("mp down"),
        ):
            first = self.client.post("/checkout/guest", json=payload, headers=headers)
        self.assertEqual(first.status_code, 502)

        db = self._db()
        try:
            record = (
                db.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.scope == build_guest_checkout_scope(email),
                    IdempotencyRecord.idempotency_key == key,
                )
                .first()
            )
            self.assertIsNotNone(record)
            self.assertEqual(str(record.status), "failed")
            stored = json.loads(record.response_payload)
            self.assertIn("order_id", stored)
            self.assertIn("payment_id", stored)
            return stored
        finally:
            db.close()

    def test_failed_record_recovers_when_mp_reinit_succeeds(self) -> None:
        variant_id = self._seed_variant()
        email = "guest-recover-ok@example.com"
        key = "guest-recover-ok-key"
        stored = self._fail_first_checkout(variant_id=variant_id, email=email, key=key)

        # Reintento con la misma clave y el mismo payload: cae en RECOVER y el re-init
        # de MP ahora sale bien.
        payload = self._mp_payload(variant_id, email)
        headers = {**self._origin_headers(), "Idempotency-Key": key}
        with patch(
            "source.routes.orders_r.enforce_public_guest_checkout_limits",
            return_value=None,
        ), patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference",
            return_value={
                "id": "pref-recovered",
                "init_point": "https://www.mercadopago.com/checkout/v1/redirect?pref_id=pref-recovered",
            },
        ):
            second = self.client.post("/checkout/guest", json=payload, headers=headers)

        self.assertEqual(second.status_code, 201)
        data = second.json()["data"]
        self.assertEqual(int(data["order"]["id"]), int(stored["order_id"]))
        self.assertEqual(int(data["payment"]["id"]), int(stored["payment_id"]))
        self.assertEqual(data["payment"]["provider_status"], "preference_created")

        db = self._db()
        try:
            record = (
                db.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.scope == build_guest_checkout_scope(email),
                    IdempotencyRecord.idempotency_key == key,
                )
                .first()
            )
            self.assertEqual(str(record.status), "completed")
            payment = (
                db.query(Payment).filter(Payment.id == int(stored["payment_id"])).first()
            )
            self.assertNotEqual(str(payment.provider_status), PAYMENT_PROVIDER_SETUP_FAILED)
        finally:
            db.close()

    def test_failed_record_stays_failed_when_mp_reinit_fails_again(self) -> None:
        variant_id = self._seed_variant()
        email = "guest-recover-again@example.com"
        key = "guest-recover-again-key"
        stored = self._fail_first_checkout(variant_id=variant_id, email=email, key=key)

        payload = self._mp_payload(variant_id, email)
        headers = {**self._origin_headers(), "Idempotency-Key": key}
        with patch(
            "source.routes.orders_r.enforce_public_guest_checkout_limits",
            return_value=None,
        ), patch(
            "source.services.mercadopago_normalization_s.create_checkout_preference",
            side_effect=Exception("mp still down"),
        ):
            second = self.client.post("/checkout/guest", json=payload, headers=headers)

        self.assertEqual(second.status_code, 502)
        db = self._db()
        try:
            record = (
                db.query(IdempotencyRecord)
                .filter(
                    IdempotencyRecord.scope == build_guest_checkout_scope(email),
                    IdempotencyRecord.idempotency_key == key,
                )
                .first()
            )
            # Sigue failed y recuperable: un tercer intento volveria a entrar a RECOVER.
            self.assertEqual(str(record.status), "failed")
            stored_again = json.loads(record.response_payload)
            self.assertEqual(int(stored_again["order_id"]), int(stored["order_id"]))
            self.assertEqual(int(stored_again["payment_id"]), int(stored["payment_id"]))
        finally:
            db.close()

    def test_failed_record_without_ids_returns_502_with_stored_detail(self) -> None:
        variant_id = self._seed_variant()
        email = "guest-recover@example.com"
        key = "guest-recover-key-1"
        raw = {
            "customer": {
                "email": email,
                "first_name": "Guest",
                "last_name": "Buyer",
                "phone": "1122334455",
            },
            "items": [{"variant_id": variant_id, "quantity": 1}],
            "payment_method": "mercadopago",
            "website": None,
        }
        # Hash igual al que calcula el endpoint (model_dump del schema), para caer en
        # el camino 'failed' y no en el conflicto de clave reusada.
        scope = build_guest_checkout_scope(email)
        request_hash = hash_payload(
            canonicalize_payload(PublicGuestCheckoutRequest(**raw).model_dump())
        )

        db = self._db()
        try:
            now = datetime.now(UTC)
            db.add(
                IdempotencyRecord(
                    scope=scope,
                    idempotency_key=key,
                    request_hash=request_hash,
                    response_payload=json.dumps({"detail": "mp exploded earlier"}),
                    status="failed",
                    created_at=now,
                    expires_at=now + timedelta(hours=24),
                )
            )
            db.commit()
        finally:
            db.close()

        response = self.client.post(
            "/checkout/guest",
            json=raw,
            headers={**self._origin_headers(), "Idempotency-Key": key},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "mp exploded earlier")
