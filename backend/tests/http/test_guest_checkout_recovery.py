"""R01-6: cobertura del camino 'failed' del guest checkout (_recover_guest_checkout).

Antes de esta extraccion la rama de recuperacion no tenia ningun test HTTP. Aca se
cubre el sub-caso determinista: un record fallido sin order_id/payment_id no puede
recuperarse y devuelve 502 con el detail guardado. El camino de re-init de Mercado
Pago (exito y fallo-de-nuevo) queda para la matriz completa de R01-10.
"""
import json
from datetime import UTC, datetime, timedelta

from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import IdempotencyRecord
from source.schemas import PublicGuestCheckoutRequest
from source.services.idempotency_s import (
    build_guest_checkout_scope,
    canonicalize_payload,
    hash_payload,
)


class GuestCheckoutRecoveryTests(HttpFundamentalsBase):
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
