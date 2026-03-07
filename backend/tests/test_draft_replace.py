import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

from fastapi.routing import APIRoute
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base, Category, Order, OrderItem, Product, ProductVariant, User
from source.routes.orders_r import router as orders_router
from source.services.orders_s import change_order_status, replace_draft_order_items


class ReplaceDraftItemsTests(unittest.TestCase):
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

    def _seed_catalog_and_user(self) -> tuple[int, dict[str, int]]:
        session = self.TestSession()
        try:
            user = User(
                first_name="Draft",
                last_name="Tester",
                email=f"draft-{datetime.now(UTC).timestamp()}@example.com",
                password_hash="!",
                has_account=False,
                is_admin=False,
            )
            category = Category(name=f"draft-cat-{datetime.now(UTC).timestamp()}")
            session.add_all([user, category])
            session.flush()

            product = Product(name="Draft Product", description=None, category_id=category.id)
            session.add(product)
            session.flush()

            variant_a = ProductVariant(
                product_id=product.id,
                sku=f"DRAFT-A-{datetime.now(UTC).timestamp()}",
                size="S",
                color="Blue",
                price=10000,
                stock=8,
                is_active=True,
            )
            variant_b = ProductVariant(
                product_id=product.id,
                sku=f"DRAFT-B-{datetime.now(UTC).timestamp()}",
                size="M",
                color="Red",
                price=15000,
                stock=6,
                is_active=True,
            )
            variant_inactive = ProductVariant(
                product_id=product.id,
                sku=f"DRAFT-C-{datetime.now(UTC).timestamp()}",
                size="L",
                color="Gray",
                price=20000,
                stock=5,
                is_active=False,
            )
            session.add_all([variant_a, variant_b, variant_inactive])
            session.commit()
            return int(user.id), {
                "variant_a": int(variant_a.id),
                "variant_b": int(variant_b.id),
                "variant_inactive": int(variant_inactive.id),
            }
        finally:
            session.close()

    def test_replace_draft_creates_draft_and_groups_duplicate_variants(self) -> None:
        user_id, variants = self._seed_catalog_and_user()
        session = self.TestSession()
        try:
            draft = replace_draft_order_items(
                user_id=user_id,
                items=[
                    {"variant_id": variants["variant_a"], "quantity": 1},
                    {"variant_id": variants["variant_a"], "quantity": 2},
                    {"variant_id": variants["variant_b"], "quantity": 1},
                ],
                db=session,
            )
            session.commit()
        finally:
            session.close()

        self.assertEqual(draft["status"], "draft")
        self.assertEqual(len(draft["items"]), 2)
        grouped = {item["variant_id"]: item for item in draft["items"]}
        self.assertEqual(grouped[variants["variant_a"]]["quantity"], 3)
        self.assertEqual(grouped[variants["variant_b"]]["quantity"], 1)
        self.assertEqual(draft["total_amount"], 45000)

    def test_replace_draft_allows_empty_payload_and_clears_items(self) -> None:
        user_id, variants = self._seed_catalog_and_user()
        session = self.TestSession()
        try:
            replace_draft_order_items(
                user_id=user_id,
                items=[{"variant_id": variants["variant_a"], "quantity": 2}],
                db=session,
            )
            cleared = replace_draft_order_items(
                user_id=user_id,
                items=[],
                db=session,
            )
            session.commit()
        finally:
            session.close()

        self.assertEqual(cleared["status"], "draft")
        self.assertEqual(cleared["items"], [])
        self.assertEqual(cleared["total_amount"], 0)

    def test_replace_draft_rejects_inactive_variant(self) -> None:
        user_id, variants = self._seed_catalog_and_user()
        session = self.TestSession()
        try:
            with self.assertRaises(ValueError):
                replace_draft_order_items(
                    user_id=user_id,
                    items=[{"variant_id": variants["variant_inactive"], "quantity": 1}],
                    db=session,
                )
        finally:
            session.close()

    def test_replace_draft_can_be_submitted_after_replacement(self) -> None:
        user_id, variants = self._seed_catalog_and_user()
        session = self.TestSession()
        try:
            draft = replace_draft_order_items(
                user_id=user_id,
                items=[
                    {"variant_id": variants["variant_a"], "quantity": 1},
                    {"variant_id": variants["variant_b"], "quantity": 1},
                ],
                db=session,
            )
            submitted = change_order_status(
                user_id=user_id,
                order_id=int(draft["id"]),
                new_status="submitted",
                db=session,
                is_admin=False,
            )
            session.commit()

            order_model = session.query(Order).filter(Order.id == int(draft["id"])).first()
            self.assertIsNotNone(order_model)
            self.assertEqual(order_model.status, "submitted")
            self.assertEqual(session.query(OrderItem).filter(OrderItem.order_id == int(draft["id"])).count(), 2)
        finally:
            session.close()

        self.assertEqual(submitted["status"], "submitted")

    def test_replace_draft_route_exists_and_is_not_deprecated(self) -> None:
        route_map: dict[tuple[str, str], APIRoute] = {}
        for route in orders_router.routes:
            if isinstance(route, APIRoute):
                for method in sorted(route.methods or []):
                    route_map[(method, route.path)] = route

        replace_route = route_map.get(("PUT", "/orders/draft/items"))

        self.assertIsNotNone(replace_route)
        self.assertFalse(bool(replace_route.deprecated))


if __name__ == "__main__":
    unittest.main()
