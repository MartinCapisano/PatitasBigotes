import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base, Order, StockReservation
from source.services.orders_s import create_authenticated_checkout_order
from tests.factories.orders import create_order_graph
from tests.factories.users import create_user


class AuthenticatedCheckoutServiceTests(unittest.TestCase):
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

    def _seed_user_and_variant(self) -> tuple[int, int]:
        """Devuelve (user_id, variant_id). El order del graph queda 'submitted'
        aparte y no lo usa el checkout — sólo reutilizamos su variante."""
        session = self.TestSession()
        try:
            user = create_user(session, email_prefix="auth-checkout")
            graph = create_order_graph(
                session,
                user_id=int(user.id),
                order_status="submitted",
                variant_stock=10,
            )
            session.commit()
            return int(user.id), int(graph["variant_id"])
        finally:
            session.close()

    def test_creates_submitted_order_with_reservation_and_frozen_pricing(self) -> None:
        user_id, variant_id = self._seed_user_and_variant()
        session = self.TestSession()
        try:
            result = create_authenticated_checkout_order(
                user_id=user_id,
                items=[{"variant_id": variant_id, "quantity": 2}],
                db=session,
            )
            session.commit()

            self.assertEqual(set(result.keys()), {"order", "customer"})
            order = result["order"]
            self.assertEqual(order["status"], "submitted")
            self.assertTrue(order["pricing_frozen"])
            self.assertEqual(result["customer"]["id"], user_id)

            reservations = (
                session.query(StockReservation)
                .filter(StockReservation.order_id == int(order["id"]))
                .all()
            )
            self.assertTrue(reservations)
            self.assertTrue(all(r.status == "active" for r in reservations))
        finally:
            session.close()

    def test_same_shape_as_guest_envelope(self) -> None:
        user_id, variant_id = self._seed_user_and_variant()
        session = self.TestSession()
        try:
            result = create_authenticated_checkout_order(
                user_id=user_id,
                items=[{"variant_id": variant_id, "quantity": 1}],
                db=session,
            )
            # Mismo envelope {order, customer} que el guest.
            self.assertIn("order", result)
            self.assertIn("customer", result)
            self.assertEqual(
                set(result["customer"].keys()),
                {"id", "first_name", "last_name", "email", "dni", "phone", "has_account"},
            )
        finally:
            session.close()

    def test_preexisting_draft_does_not_block_checkout(self) -> None:
        """El helper crea un Order transitorio en 'draft' antes de flipear a
        'submitted'. Un draft preexistente del mismo usuario no debe interferir:
        el checkout crea una orden NUEVA submitted y deja el draft intacto."""
        session = self.TestSession()
        try:
            user = create_user(session, email_prefix="auth-draft")
            existing = create_order_graph(
                session,
                user_id=int(user.id),
                order_status="draft",
                variant_stock=10,
            )
            session.commit()
            user_id = int(user.id)
            draft_order_id = int(existing["order_id"])
            variant_id = int(existing["variant_id"])
        finally:
            session.close()

        session = self.TestSession()
        try:
            result = create_authenticated_checkout_order(
                user_id=user_id,
                items=[{"variant_id": variant_id, "quantity": 1}],
                db=session,
            )
            session.commit()
            new_order_id = int(result["order"]["id"])

            self.assertNotEqual(new_order_id, draft_order_id)
            self.assertEqual(result["order"]["status"], "submitted")

            draft = session.query(Order).filter(Order.id == draft_order_id).first()
            self.assertIsNotNone(draft)
            self.assertEqual(draft.status, "draft")
        finally:
            session.close()

    def test_unknown_user_raises_lookup_error(self) -> None:
        _, variant_id = self._seed_user_and_variant()
        session = self.TestSession()
        try:
            with self.assertRaises(LookupError):
                create_authenticated_checkout_order(
                    user_id=999_999,
                    items=[{"variant_id": variant_id, "quantity": 1}],
                    db=session,
                )
        finally:
            session.close()

    def test_empty_items_raises_value_error(self) -> None:
        user_id, _ = self._seed_user_and_variant()
        session = self.TestSession()
        try:
            with self.assertRaises(ValueError):
                create_authenticated_checkout_order(
                    user_id=user_id,
                    items=[],
                    db=session,
                )
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
