"""T-04 — Concurrencia: dos compras de la última unidad.

Dos órdenes distintas quieren reservar la misma variante con `stock=1`. El motor
de reservas bloquea la fila de la variante con `with_for_update()`
(`_available_stock_for_variant`), así que en PostgreSQL las dos reservas se
serializan: la primera reserva la unidad, la segunda ve `disponible=0` y es
rechazada. En SQLite el lock es un no-op y ambas reservarían (sobreventa), por eso
este test solo tiene sentido contra Postgres.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from source.db.models import (
    Category,
    Order,
    OrderItem,
    Product,
    ProductVariant,
    StockReservation,
)
from source.services.stock_reservations_s import reserve_stock_for_submitted_order
from tests.concurrency._base import ConcurrencyTestBase
from tests.factories.users import create_user


@pytest.mark.concurrency
class OversellConcurrencyTest(ConcurrencyTestBase):
    def _seed_last_unit_two_orders(self) -> tuple[int, int, int]:
        """Una variante con una sola unidad y dos órdenes submitted que la piden."""
        session = self.SessionLocal()
        try:
            user = create_user(session)

            category = Category(name="oversell-cat")
            session.add(category)
            session.flush()

            product = Product(
                name="Última unidad",
                description=None,
                category_id=int(category.id),
            )
            session.add(product)
            session.flush()

            variant = ProductVariant(
                product_id=int(product.id),
                sku="OVERSELL-SKU-1",
                size="M",
                color="Blue",
                price=10000,
                stock=1,  # la última unidad en juego
                is_active=True,
            )
            session.add(variant)
            session.flush()

            order_ids: list[int] = []
            for _ in range(2):
                order = Order(
                    user_id=int(user.id),
                    status="submitted",
                    currency="ARS",
                    subtotal=10000,
                    discount_total=0,
                    total_amount=10000,
                    pricing_frozen=True,
                    submitted_at=datetime.now(UTC),
                )
                session.add(order)
                session.flush()

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
                session.add(item)
                session.flush()
                order_ids.append(int(order.id))

            session.commit()
            return int(variant.id), order_ids[0], order_ids[1]
        finally:
            session.close()

    def test_two_orders_racing_for_the_last_unit_only_one_reserves(self) -> None:
        variant_id, order_a, order_b = self._seed_last_unit_two_orders()

        # La orden A reserva y retiene su transacción; la B corre en paralelo. Con el
        # lock FOR UPDATE sobre la variante, B se bloquea hasta que A commitea y luego
        # ve que ya no hay stock. Sin el lock, B no se bloquearía y sobrevendería.
        outcome = self.run_gated(
            lambda session: reserve_stock_for_submitted_order(order_a, session),
            lambda session: reserve_stock_for_submitted_order(order_b, session),
        )

        self.assertTrue(
            outcome.second_blocked,
            "la 2da reserva no se bloqueó: el lock FOR UPDATE de la variante no está "
            "actuando (sobreventa posible)",
        )
        kind, payload = outcome.second_outcome
        self.assertEqual(
            kind, "error", f"la 2da reserva debería ser rechazada, fue {outcome.second_outcome}"
        )
        self.assertIn("insufficient stock", str(payload))

        verify = self.SessionLocal()
        try:
            active_reservations = (
                verify.query(StockReservation)
                .filter(
                    StockReservation.variant_id == variant_id,
                    StockReservation.status == "active",
                )
                .count()
            )
            self.assertEqual(
                active_reservations,
                1,
                "no puede haber más reservas activas que stock disponible",
            )

            variant = verify.get(ProductVariant, variant_id)
            self.assertEqual(
                int(variant.stock),
                1,
                "reservar no descuenta stock; eso pasa recién al pagar",
            )
        finally:
            verify.close()
