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
    Order,
    Payment,
    StockReservation,
)
from source.services.stock_reservations_s import expire_active_reservations
from tests.factories.orders import create_order_graph
from tests.factories.users import create_user


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
            user = create_user(
                session,
                first_name="John",
                last_name="Doe",
                email_prefix="john",
                has_account=False,
            )
            graph = create_order_graph(
                session,
                user_id=int(user.id),
                order_status=order_status,
                item_qty=item_qty,
                variant_stock=variant_stock,
                with_reservation=True,
                reservation_expires_at=datetime.now(UTC) - timedelta(minutes=1),
                add_pending_payment=add_pending_payment,
            )
            session.commit()
            return (
                int(graph["order_id"]),
                int(graph["reservation_id"]),
                int(graph["variant_id"]),
            )
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

