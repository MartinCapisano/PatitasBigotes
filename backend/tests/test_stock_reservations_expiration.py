import sys
import unittest
from datetime import datetime, timedelta, UTC
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import (
    Base,
    Category,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductVariant,
    StockReservation,
    User,
)
from source.services.stock_reservations_s import expire_active_reservations


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class StockReservationExpirationTests(unittest.TestCase):
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

    def _seed_order_with_reservation(
        self,
        *,
        order_status: str,
        variant_stock: int,
        item_qty: int,
        add_pending_payment: bool = False,
    ) -> tuple[int, int, int]:
        session = self.TestSession()
        try:
            user = User(
                first_name="John",
                last_name="Doe",
                email=f"john-{datetime.now(UTC).timestamp()}@example.com",
                password_hash="!",
                has_account=False,
                is_admin=False,
            )
            category = Category(name=f"cat-{datetime.now(UTC).timestamp()}")
            session.add_all([user, category])
            session.flush()

            product = Product(
                name="Test Product",
                description=None,
                category_id=category.id,
            )
            session.add(product)
            session.flush()

            variant = ProductVariant(
                product_id=product.id,
                sku=f"SKU-{datetime.now(UTC).timestamp()}",
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
                subtotal=10000,
                discount_total=0,
                total_amount=10000,
                pricing_frozen=True,
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

            reservation = StockReservation(
                order_id=order.id,
                order_item_id=item.id,
                variant_id=variant.id,
                quantity=item_qty,
                status="active",
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
                reason=None,
            )
            session.add(reservation)

            if add_pending_payment:
                session.add(
                    Payment(
                        order_id=order.id,
                        method="bank_transfer",
                        status="pending",
                        amount=int(order.total_amount),
                        currency="ARS",
                        idempotency_key=f"pay-{datetime.now(UTC).timestamp()}",
                        external_ref=None,
                        provider_status="pending",
                        provider_payload=None,
                        receipt_url=None,
                        expires_at=datetime.now(UTC) + timedelta(hours=1),
                        paid_at=None,
                    )
                )

            session.commit()
            return int(order.id), int(reservation.id), int(variant.id)
        finally:
            session.close()

    def test_expire_reactivates_submitted_order_once_with_12h_ttl(self) -> None:
        order_id, reservation_id, _ = self._seed_order_with_reservation(
            order_status="submitted",
            variant_stock=10,
            item_qty=2,
        )

        session = self.TestSession()
        try:
            expired_count = expire_active_reservations(now=datetime.now(UTC), db=session)
            session.commit()
        finally:
            session.close()

        self.assertEqual(expired_count, 0)

        session = self.TestSession()
        try:
            order = session.query(Order).filter(Order.id == order_id).first()
            reservation = (
                session.query(StockReservation)
                .filter(StockReservation.id == reservation_id)
                .first()
            )
        finally:
            session.close()

        self.assertIsNotNone(order)
        self.assertIsNotNone(reservation)
        assert order is not None
        assert reservation is not None
        reservation_expires_at = _as_utc(reservation.expires_at)
        self.assertEqual(order.status, "submitted")
        self.assertEqual(reservation.status, "active")
        self.assertEqual(int(reservation.reactivation_count), 1)
        self.assertGreater(
            reservation_expires_at,
            datetime.now(UTC) + timedelta(hours=11),
        )
        self.assertLess(
            reservation_expires_at,
            datetime.now(UTC) + timedelta(hours=13),
        )

    def test_expire_cancels_submitted_order_and_pending_payments_when_stock_missing(self) -> None:
        order_id, reservation_id, _ = self._seed_order_with_reservation(
            order_status="submitted",
            variant_stock=1,
            item_qty=2,
            add_pending_payment=True,
        )

        session = self.TestSession()
        try:
            expired_count = expire_active_reservations(now=datetime.now(UTC), db=session)
            session.commit()
        finally:
            session.close()

        self.assertEqual(expired_count, 1)

        session = self.TestSession()
        try:
            order = session.query(Order).filter(Order.id == order_id).first()
            reservation = (
                session.query(StockReservation)
                .filter(StockReservation.id == reservation_id)
                .first()
            )
            payment = (
                session.query(Payment)
                .filter(Payment.order_id == order_id, Payment.status == "cancelled")
                .first()
            )
        finally:
            session.close()

        self.assertIsNotNone(order)
        self.assertIsNotNone(reservation)
        self.assertIsNotNone(payment)
        assert order is not None
        assert reservation is not None
        assert payment is not None
        self.assertEqual(order.status, "cancelled")
        self.assertIsNotNone(order.cancelled_at)
        self.assertEqual(reservation.status, "expired")
        self.assertEqual(payment.provider_status, "order_cancelled_reservation_expired")

    def test_expire_does_not_reactivate_non_submitted_order(self) -> None:
        order_id, reservation_id, _ = self._seed_order_with_reservation(
            order_status="draft",
            variant_stock=10,
            item_qty=2,
        )

        session = self.TestSession()
        try:
            expired_count = expire_active_reservations(now=datetime.now(UTC), db=session)
            session.commit()
        finally:
            session.close()

        self.assertEqual(expired_count, 1)

        session = self.TestSession()
        try:
            order = session.query(Order).filter(Order.id == order_id).first()
            reservation = (
                session.query(StockReservation)
                .filter(StockReservation.id == reservation_id)
                .first()
            )
        finally:
            session.close()

        self.assertIsNotNone(order)
        self.assertIsNotNone(reservation)
        assert order is not None
        assert reservation is not None
        self.assertEqual(order.status, "draft")
        self.assertEqual(reservation.status, "expired")

    def test_second_expiration_after_reactivation_cancels_order(self) -> None:
        order_id, reservation_id, _ = self._seed_order_with_reservation(
            order_status="submitted",
            variant_stock=10,
            item_qty=1,
            add_pending_payment=True,
        )

        session = self.TestSession()
        try:
            first = expire_active_reservations(now=datetime.now(UTC), db=session)
            reservation = (
                session.query(StockReservation)
                .filter(StockReservation.id == reservation_id)
                .first()
            )
            assert reservation is not None
            reservation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            session.flush()
            second = expire_active_reservations(now=datetime.now(UTC), db=session)
            session.commit()
        finally:
            session.close()

        self.assertEqual(first, 0)
        self.assertEqual(second, 1)

        session = self.TestSession()
        try:
            order = session.query(Order).filter(Order.id == order_id).first()
            reservation = (
                session.query(StockReservation)
                .filter(StockReservation.id == reservation_id)
                .first()
            )
            payment = (
                session.query(Payment)
                .filter(Payment.order_id == order_id, Payment.status == "cancelled")
                .first()
            )
        finally:
            session.close()

        self.assertIsNotNone(order)
        self.assertIsNotNone(reservation)
        self.assertIsNotNone(payment)
        assert order is not None
        assert reservation is not None
        assert payment is not None
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(reservation.status, "expired")
        self.assertEqual(int(reservation.reactivation_count), 1)


if __name__ == "__main__":
    unittest.main()

