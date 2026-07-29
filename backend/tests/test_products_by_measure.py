"""Fase 1 de products_by_measure: modelo de medida, disponibilidad por is_active,
guarda del checkout self-service y reservas exentas. Ver docs/products_by_measure.md.
"""
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base, Category, Order, ProductVariant, StockReservation
from source.services import orders_s, products_s, products_storefront_s
from source.services.stock_reservations_s import (
    NON_EXPIRING_RESERVATION_AT,
    consume_reservations_for_paid_order,
    expire_active_reservations,
)
from tests.factories.users import create_user


class ProductsByMeasureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine("sqlite:///:memory:")
        cls.TestSession = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        session = self.TestSession()
        try:
            session.add(Category(name="cat"))
            session.commit()
        finally:
            session.close()

    def _create_product(self, session, name: str = "Alimento a granel") -> int:
        product = products_s.create_product(
            {"name": name, "description": None, "category": "cat", "active": True},
            db=session,
        )
        session.commit()
        return int(product["id"])

    def _add_variant(
        self,
        session,
        *,
        product_id: int,
        sku: str,
        price: int = 200,
        stock: int = 0,
        is_active: bool = True,
        sold_by: str = "unit",
        measure_unit: str | None = None,
        step: int = 1,
    ) -> int:
        variant = ProductVariant(
            product_id=product_id,
            sku=sku,
            price=price,
            stock=stock,
            is_active=is_active,
            sold_by=sold_by,
            measure_unit=measure_unit,
            step=step,
        )
        session.add(variant)
        session.flush()
        variant_id = int(variant.id)
        session.commit()
        return variant_id

    # --- 5.3/5.4 DTOs y servicio: creación/edición por medida ------------------

    def test_create_measure_variant_persists_fields(self) -> None:
        session = self.TestSession()
        try:
            product_id = self._create_product(session)
            variant = products_s.create_variant(
                {
                    "product_id": product_id,
                    "sku": "GRANEL-100",
                    "price": 200,
                    "stock": 0,
                    "sold_by": "measure",
                    "measure_unit": "g",
                    "step": 100,
                },
                db=session,
            )
            session.commit()
        finally:
            session.close()
        self.assertEqual(variant["sold_by"], "measure")
        self.assertEqual(variant["measure_unit"], "g")
        self.assertEqual(variant["step"], 100)

    def test_create_measure_variant_requires_measure_unit(self) -> None:
        session = self.TestSession()
        try:
            product_id = self._create_product(session)
            with self.assertRaises(ValueError):
                products_s.create_variant(
                    {
                        "product_id": product_id,
                        "sku": "GRANEL-BAD",
                        "price": 200,
                        "sold_by": "measure",
                        "step": 100,
                    },
                    db=session,
                )
        finally:
            session.close()

    def test_update_variant_to_measure_without_unit_raises(self) -> None:
        session = self.TestSession()
        try:
            product_id = self._create_product(session)
            variant_id = self._add_variant(session, product_id=product_id, sku="U-1")
            with self.assertRaises(ValueError):
                products_s.update_variant(variant_id, {"sold_by": "measure"}, db=session)
        finally:
            session.close()

    # --- 5.5 Storefront: disponibilidad por is_active (divergencia) ------------

    def test_storefront_shows_inactive_measure_product_as_out_of_stock(self) -> None:
        session = self.TestSession()
        try:
            product_id = self._create_product(session, name="Granel sin stock")
            self._add_variant(
                session,
                product_id=product_id,
                sku="GRANEL-OFF",
                is_active=False,
                sold_by="measure",
                measure_unit="g",
                step=100,
            )
        finally:
            session.close()

        session = self.TestSession()
        try:
            data, total = products_storefront_s.list_storefront_products(db=session)
            detail = products_storefront_s.get_storefront_product_by_id(product_id, db=session)
        finally:
            session.close()

        self.assertEqual(total, 1)
        self.assertEqual(data[0]["name"], "Granel sin stock")
        self.assertFalse(data[0]["in_stock"])
        self.assertIsNotNone(detail)
        assert detail is not None
        option = detail["options"][0]
        self.assertEqual(option["sold_by"], "measure")
        self.assertEqual(option["measure_unit"], "g")
        self.assertEqual(option["step"], 100)
        self.assertFalse(option["in_stock"])

    def test_storefront_active_measure_product_is_in_stock(self) -> None:
        session = self.TestSession()
        try:
            product_id = self._create_product(session, name="Granel disponible")
            self._add_variant(
                session,
                product_id=product_id,
                sku="GRANEL-ON",
                is_active=True,
                sold_by="measure",
                measure_unit="g",
                step=100,
            )
        finally:
            session.close()

        session = self.TestSession()
        try:
            detail = products_storefront_s.get_storefront_product_by_id(product_id, db=session)
        finally:
            session.close()
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertTrue(detail["in_stock"])
        self.assertTrue(detail["options"][0]["in_stock"])

    def test_storefront_still_hides_inactive_normal_product(self) -> None:
        session = self.TestSession()
        try:
            product_id = self._create_product(session, name="Normal oculto")
            self._add_variant(session, product_id=product_id, sku="NORM-OFF", is_active=False)
        finally:
            session.close()

        session = self.TestSession()
        try:
            data, total = products_storefront_s.list_storefront_products(db=session)
            detail = products_storefront_s.get_storefront_product_by_id(product_id, db=session)
        finally:
            session.close()
        self.assertEqual(total, 0)
        self.assertIsNone(detail)

    # --- 5.7 Guarda del checkout self-service ----------------------------------

    def test_guest_checkout_rejects_measure_item(self) -> None:
        session = self.TestSession()
        try:
            product_id = self._create_product(session)
            variant_id = self._add_variant(
                session,
                product_id=product_id,
                sku="GRANEL-CK",
                sold_by="measure",
                measure_unit="g",
                step=100,
            )
            with self.assertRaises(ValueError) as ctx:
                orders_s.create_manual_submitted_order(
                    email="guest@example.com",
                    first_name="Guest",
                    last_name="User",
                    phone="1122334455",
                    items=[{"variant_id": variant_id, "quantity": 5}],
                    db=session,
                )
            self.assertIn("availability confirmation", str(ctx.exception))
        finally:
            session.close()

    def test_admin_path_allows_measure_item(self) -> None:
        session = self.TestSession()
        try:
            user = create_user(session, email_prefix="admin-buyer", has_account=False)
            product_id = self._create_product(session)
            variant_id = self._add_variant(
                session,
                product_id=product_id,
                sku="GRANEL-ADM",
                price=200,
                sold_by="measure",
                measure_unit="g",
                step=100,
            )
            order = orders_s._create_submitted_order_for_user(
                user_id=int(user.id),
                items=[{"variant_id": variant_id, "quantity": 5}],
                db=session,
                allow_measure=True,
            )
            session.commit()
        finally:
            session.close()
        self.assertEqual(order["status"], "submitted")
        self.assertEqual(len(order["items"]), 1)
        item = order["items"][0]
        self.assertEqual(item["sold_by"], "measure")
        self.assertEqual(item["quantity"], 5)
        # line_total = pasos (5) x precio por paso (200)
        self.assertEqual(item["line_total"], 1000)

    # --- 4.3 Reservas exentas de inventario ------------------------------------

    def _create_measure_order(self, session, *, quantity: int = 5) -> tuple[int, int]:
        user = create_user(session, email_prefix="measure-buyer", has_account=False)
        product_id = self._create_product(session)
        variant_id = self._add_variant(
            session,
            product_id=product_id,
            sku="GRANEL-RES",
            price=200,
            stock=0,
            sold_by="measure",
            measure_unit="g",
            step=100,
        )
        order = orders_s._create_submitted_order_for_user(
            user_id=int(user.id),
            items=[{"variant_id": variant_id, "quantity": quantity}],
            db=session,
            allow_measure=True,
        )
        session.commit()
        return int(order["id"]), variant_id

    def test_measure_reservation_is_non_expiring(self) -> None:
        session = self.TestSession()
        try:
            order_id, _ = self._create_measure_order(session)
            reservation = (
                session.query(StockReservation)
                .filter(StockReservation.order_id == order_id)
                .first()
            )
            self.assertIsNotNone(reservation)
            assert reservation is not None
            self.assertEqual(reservation.expires_at.year, NON_EXPIRING_RESERVATION_AT.year)
            self.assertEqual(reservation.status, "active")
        finally:
            session.close()

    def test_expiration_does_not_break_when_measure_variant_inactive(self) -> None:
        session = self.TestSession()
        try:
            order_id, variant_id = self._create_measure_order(session)
            # El admin marca el producto "sin stock" con la orden aún impaga.
            variant = session.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
            assert variant is not None
            variant.is_active = False
            session.commit()
        finally:
            session.close()

        session = self.TestSession()
        try:
            # No debe lanzar aunque la variante esté inactiva.
            expired = expire_active_reservations(now=datetime.now(UTC) + timedelta(days=3), db=session)
            session.commit()
        finally:
            session.close()

        self.assertEqual(expired, 0)
        session = self.TestSession()
        try:
            order = session.query(Order).filter(Order.id == order_id).first()
            reservation = (
                session.query(StockReservation)
                .filter(StockReservation.order_id == order_id)
                .first()
            )
        finally:
            session.close()
        assert order is not None and reservation is not None
        self.assertEqual(order.status, "submitted")
        self.assertEqual(reservation.status, "active")

    def test_consume_measure_reservation_does_not_touch_stock(self) -> None:
        session = self.TestSession()
        try:
            order_id, variant_id = self._create_measure_order(session)
        finally:
            session.close()

        session = self.TestSession()
        try:
            consume_reservations_for_paid_order(order_id=order_id, db=session)
            session.commit()
        finally:
            session.close()

        session = self.TestSession()
        try:
            variant = session.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
            reservation = (
                session.query(StockReservation)
                .filter(StockReservation.order_id == order_id)
                .first()
            )
        finally:
            session.close()
        assert variant is not None and reservation is not None
        self.assertEqual(int(variant.stock), 0)
        self.assertEqual(reservation.status, "consumed")


if __name__ == "__main__":
    unittest.main()
