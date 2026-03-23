import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base
from source.exceptions import OrderStatusTransitionError
from source.services.orders_s import change_order_status
from tests.factories.orders import create_order_graph
from tests.factories.users import create_user


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
            user = create_user(
                session,
                first_name="Order",
                last_name="Tester",
                email_prefix="order",
                has_account=False,
            )
            graph = create_order_graph(
                session,
                user_id=int(user.id),
                order_status=order_status,
                item_qty=item_qty,
                variant_stock=variant_stock,
                with_reservation=with_reservation,
                product_name="Order Product",
                sku_prefix="ORDER-SKU",
            )
            session.commit()
            return int(graph["order_id"]), int(user.id)
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
