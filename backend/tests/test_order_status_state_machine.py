import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base, Category, Order, OrderItem, Product, ProductVariant, StockReservation, User
from source.exceptions import OrderStatusTransitionError
from source.services.orders_s import change_order_status


class OrderStatusStateMachineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine("sqlite:///:memory:")
        cls.TestSession = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=cls.engine,
        )
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def _seed_order(
        self,
        *,
        order_status: str,
        with_reservation: bool = False,
        item_qty: int = 1,
        variant_stock: int = 10,
    ) -> tuple[int, int]:
        session = self.TestSession()
        try:
            user = User(
                first_name="Order",
                last_name="Tester",
                email=f"order-{datetime.now(UTC).timestamp()}@example.com",
                password_hash="!",
                has_account=False,
                is_admin=False,
            )
            category = Category(name=f"cat-{datetime.now(UTC).timestamp()}")
            session.add_all([user, category])
            session.flush()

            product = Product(name="Order Product", description=None, category_id=category.id)
            session.add(product)
            session.flush()

            variant = ProductVariant(
                product_id=product.id,
                sku=f"ORDER-SKU-{datetime.now(UTC).timestamp()}",
                size="M",
                color="Blue",
                price=10000,
                stock=variant_stock,
                is_active=True,
            )
            session.add(variant)
            session.flush()

            order = Order(
                user_id=user.id,
                status=order_status,
                currency="ARS",
                subtotal=10000 * item_qty,
                discount_total=0,
                total_amount=10000 * item_qty,
                pricing_frozen=order_status != "draft",
                submitted_at=datetime.now(UTC) if order_status in {"submitted", "paid"} else None,
                paid_at=datetime.now(UTC) if order_status == "paid" else None,
                cancelled_at=datetime.now(UTC) if order_status == "cancelled" else None,
            )
            session.add(order)
            session.flush()

            item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                variant_id=variant.id,
                quantity=item_qty,
                unit_price=10000,
                discount_id=None,
                discount_amount=0,
                final_unit_price=10000,
                line_total=10000 * item_qty,
            )
            session.add(item)
            session.flush()

            if with_reservation:
                session.add(
                    StockReservation(
                        order_id=order.id,
                        order_item_id=item.id,
                        variant_id=variant.id,
                        quantity=item_qty,
                        status="active",
                        expires_at=datetime.now(UTC) + timedelta(hours=1),
                    )
                )

            session.commit()
            return int(order.id), int(user.id)
        finally:
            session.close()

    def test_draft_to_submitted_allowed(self) -> None:
        order_id, user_id = self._seed_order(order_status="draft")
        session = self.TestSession()
        try:
            order = change_order_status(
                user_id=user_id,
                order_id=order_id,
                new_status="submitted",
                db=session,
                is_admin=False,
            )
            session.commit()
        finally:
            session.close()
        self.assertEqual(order["status"], "submitted")

    def test_submitted_to_paid_allowed_admin_manual_payment(self) -> None:
        order_id, user_id = self._seed_order(order_status="submitted", with_reservation=True)
        session = self.TestSession()
        try:
            order = change_order_status(
                user_id=user_id,
                order_id=order_id,
                new_status="paid",
                db=session,
                is_admin=True,
                payment_ref="MANUAL-REF-1",
                paid_amount=10000,
            )
            session.commit()
        finally:
            session.close()
        self.assertEqual(order["status"], "paid")

    def test_submitted_to_cancelled_allowed(self) -> None:
        order_id, user_id = self._seed_order(order_status="submitted", with_reservation=True)
        session = self.TestSession()
        try:
            order = change_order_status(
                user_id=user_id,
                order_id=order_id,
                new_status="cancelled",
                db=session,
                is_admin=False,
            )
            session.commit()
        finally:
            session.close()
        self.assertEqual(order["status"], "cancelled")

    def test_paid_to_submitted_rejected_409(self) -> None:
        order_id, user_id = self._seed_order(order_status="paid")
        session = self.TestSession()
        try:
            with self.assertRaises(OrderStatusTransitionError):
                change_order_status(
                    user_id=user_id,
                    order_id=order_id,
                    new_status="submitted",
                    db=session,
                    is_admin=False,
                )
        finally:
            session.close()

    def test_cancelled_to_submitted_rejected_409(self) -> None:
        order_id, user_id = self._seed_order(order_status="cancelled")
        session = self.TestSession()
        try:
            with self.assertRaises(OrderStatusTransitionError):
                change_order_status(
                    user_id=user_id,
                    order_id=order_id,
                    new_status="submitted",
                    db=session,
                    is_admin=False,
                )
        finally:
            session.close()

    def test_invalid_transition_logs_rejected_event(self) -> None:
        order_id, user_id = self._seed_order(order_status="paid")
        session = self.TestSession()
        try:
            with self.assertLogs("source.services.orders_s", level="INFO") as logs:
                with self.assertRaises(OrderStatusTransitionError):
                    change_order_status(
                        user_id=user_id,
                        order_id=order_id,
                        new_status="cancelled",
                        db=session,
                        is_admin=False,
                    )
        finally:
            session.close()

        self.assertTrue(any("event=order_status_transition_rejected" in row for row in logs.output))

    def test_valid_transition_logs_applied_event(self) -> None:
        order_id, user_id = self._seed_order(order_status="draft")
        session = self.TestSession()
        try:
            with self.assertLogs("source.services.orders_s", level="INFO") as logs:
                change_order_status(
                    user_id=user_id,
                    order_id=order_id,
                    new_status="submitted",
                    db=session,
                    is_admin=False,
                )
                session.commit()
        finally:
            session.close()

        self.assertTrue(any("event=order_status_transition_applied" in row for row in logs.output))


if __name__ == "__main__":
    unittest.main()
