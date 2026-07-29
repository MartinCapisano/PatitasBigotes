"""T-03 — Concurrencia: dos pagos simultáneos sobre la misma orden.

Dos requests con claves de idempotencia **distintas** intentan crear un pago para
la misma orden submitted a la vez. El invariante a proteger: la orden termina con
**un solo** pago pending, no dos (doble cobro).

Dos guardas lo sostienen en profundidad y este test los ejercita end-to-end sobre
un Postgres real:
- el índice único parcial `uq_payments_one_pending_per_order_method`
  (WHERE status='pending'): el 2º INSERT se **bloquea** contra el índice hasta que
  el 1º commitea y luego falla con IntegrityError, que `create_payment_for_order`
  atrapa y resuelve al pending ya existente;
- el `with_for_update()` sobre la fila de la orden, que serializa el resto del
  read-modify-write.

Con conexiones reales y bloqueo a nivel de fila —lo que SQLite (StaticPool, una
sola conexión) no puede reproducir— el resultado es determinista: exactamente un
pending. Por eso el test solo tiene sentido contra Postgres.
"""
from __future__ import annotations

import pytest

from source.db.models import Payment
from source.services.payment_s import create_payment_for_order
from tests.concurrency._base import ConcurrencyTestBase
from tests.factories.orders import create_order_graph
from tests.factories.users import create_user


@pytest.mark.concurrency
class DoublePaymentConcurrencyTest(ConcurrencyTestBase):
    def _seed_submitted_order_with_reservation(self) -> int:
        """Orden submitted con una reserva activa (requisito para crear el pago)."""
        session = self.SessionLocal()
        try:
            user = create_user(session)
            graph = create_order_graph(
                session,
                user_id=int(user.id),
                order_status="submitted",
                item_qty=1,
                variant_stock=10,
                with_reservation=True,
            )
            session.commit()
            return int(graph["order_id"])
        finally:
            session.close()

    def test_two_concurrent_payments_create_a_single_pending_payment(self) -> None:
        order_id = self._seed_submitted_order_with_reservation()

        # La 1ra request crea el pago y retiene su transacción; la 2da corre en paralelo
        # con OTRA clave de idempotencia (si fuera la misma, la idempotencia sola la
        # cubriría y no probaría la concurrencia). La 2da se bloquea contra el índice
        # único parcial de pending y, al commitear la 1ra, falla con IntegrityError que
        # el servicio resuelve al pending ya existente. Sin ese bloqueo no vería el
        # pending sin commitear (READ COMMITTED) y crearía un segundo → doble cobro.
        outcome = self.run_gated(
            lambda session: create_payment_for_order(
                order_id, "cash", session, idempotency_key="race-key-a"
            ),
            lambda session: create_payment_for_order(
                order_id, "cash", session, idempotency_key="race-key-b"
            ),
        )

        self.assertTrue(
            outcome.second_blocked,
            "el 2do pago no se bloqueó: el lock de la orden no está actuando (doble cobro posible)",
        )
        kind, payload = outcome.second_outcome
        self.assertEqual(
            kind, "ok", f"el 2do pago debería resolver al pending existente, fue {outcome.second_outcome}"
        )
        self.assertEqual(
            outcome.first_value["id"],
            payload["id"],
            "ambas requests deberían resolver al mismo pago, no a dos distintos",
        )

        verify = self.SessionLocal()
        try:
            pending_payments = (
                verify.query(Payment)
                .filter(Payment.order_id == order_id, Payment.status == "pending")
                .all()
            )
            self.assertEqual(
                len(pending_payments),
                1,
                "dos requests concurrentes generaron pagos pending duplicados (doble cobro)",
            )
        finally:
            verify.close()
