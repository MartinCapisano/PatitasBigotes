"""R01-10: camino 'processing' (clave gemela en curso) para ambos endpoints.

Cierra la cuarta celda de la matriz de idempotencia: un request gemelo que llega
mientras otro con la misma Idempotency-Key sigue en vuelo. El primero deja el record
en 'processing' (via acquire_record, bajo el indice unico scope+key); el segundo lo
encuentra asi y `resolve_idempotency` lanza IdempotencyInProgressError, que el handler
central (R01-3) mapea a 409.

Se ejerce de forma determinista sembrando el record 'processing' con el MISMO
request_hash que calcula el endpoint (si el hash difiere se caeria en el conflicto de
clave reusada, otro camino). Es el equivalente en estado del test de concurrencia real
de dos threads: reproduce exactamente lo que ve el gemelo sin depender del scheduling.
La verificacion de la carrera real con dos conexiones concurrentes necesita el indice
unico de PostgreSQL (T-02); en SQLite/StaticPool del suite no es reproducible.
"""
from datetime import UTC, datetime, timedelta

from backend.tests.factories.http_checkout import create_non_account_user
from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import IdempotencyRecord
from source.schemas import CreateAdminSaleRequest, PublicGuestCheckoutRequest
from source.services.idempotency_s import (
    build_guest_checkout_scope,
    canonicalize_payload,
    hash_payload,
)


def _seed_processing_record(db, *, scope: str, key: str, request_hash: str) -> None:
    now = datetime.now(UTC)
    db.add(
        IdempotencyRecord(
            scope=scope,
            idempotency_key=key,
            request_hash=request_hash,
            response_payload="{}",
            status="processing",
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
    )
    db.commit()


class GuestTwinKeyInProgressTests(HttpFundamentalsBase):
    def test_twin_key_in_progress_conflicts_409(self) -> None:
        variant_id = self._seed_variant()
        email = "guest-twin@example.com"
        key = "guest-twin-key"
        raw = {
            "customer": {
                "email": email,
                "first_name": "Guest",
                "last_name": "Buyer",
                "phone": "1122334455",
            },
            "items": [{"variant_id": variant_id, "quantity": 1}],
            "website": None,
        }
        request_hash = hash_payload(
            canonicalize_payload(PublicGuestCheckoutRequest(**raw).model_dump())
        )
        db = self._db()
        try:
            _seed_processing_record(
                db,
                scope=build_guest_checkout_scope(email),
                key=key,
                request_hash=request_hash,
            )
        finally:
            db.close()

        response = self.client.post(
            "/checkout/guest",
            json=raw,
            headers={**self._origin_headers(), "Idempotency-Key": key},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], "idempotent request already in progress"
        )


class AdminSalesTwinKeyInProgressTests(HttpFundamentalsBase):
    def test_twin_key_in_progress_conflicts_409(self) -> None:
        variant_id = self._seed_variant()
        db = self._db()
        try:
            user_id = create_non_account_user(db)
        finally:
            db.close()
        admin_user_id = self._create_user(
            email="admin-twin@example.com", is_admin=True, verified=True
        )
        login = self._login(email="admin-twin@example.com")
        self.assertEqual(login.status_code, 200)

        key = "admin-twin-key"
        body = {
            "customer": {"mode": "existing", "user_id": user_id},
            "items": [{"variant_id": variant_id, "quantity": 1}],
            "register_payment": False,
            "payment": None,
        }
        request_hash = hash_payload(
            canonicalize_payload(CreateAdminSaleRequest(**body).model_dump())
        )
        db = self._db()
        try:
            _seed_processing_record(
                db,
                scope=f"admin_sales:{int(admin_user_id)}",
                key=key,
                request_hash=request_hash,
            )
        finally:
            db.close()

        response = self.client.post(
            "/admin/sales",
            json=body,
            headers={**self._origin_headers(), "Idempotency-Key": key},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"], "idempotent request already in progress"
        )
