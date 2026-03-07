import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base, Category, Product, ProductVariant, User
from source.services.orders_s import create_admin_sale
from source.services.post_commit_actions_s import POST_COMMIT_ACTIONS_KEY
from source.services.stock_reservations_s import list_active_reservations_for_order


class AdminSalesTests(unittest.TestCase):
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

    def _seed_variant(self) -> int:
        session = self.TestSession()
        try:
            category = Category(name=f"cat-{datetime.now(UTC).timestamp()}")
            session.add(category)
            session.flush()
            product = Product(
                name="Prod test",
                description=None,
                category_id=category.id,
            )
            session.add(product)
            session.flush()
            variant = ProductVariant(
                product_id=product.id,
                sku=f"SKU-{datetime.now(UTC).timestamp()}",
                size="M",
                color="Negro",
                price=10000,
                stock=10,
                is_active=True,
            )
            session.add(variant)
            session.commit()
            return int(variant.id)
        finally:
            session.close()

    def _seed_user(self) -> int:
        session = self.TestSession()
        try:
            user = User(
                first_name="Ana",
                last_name="Admin",
                email=f"ana-{datetime.now(UTC).timestamp()}@example.com",
                phone="1144455566",
                password_hash="!",
                has_account=False,
                is_admin=False,
            )
            session.add(user)
            session.commit()
            return int(user.id)
        finally:
            session.close()

    def test_create_admin_sale_existing_user_without_payment(self) -> None:
        variant_id = self._seed_variant()
        user_id = self._seed_user()
        session = self.TestSession()
        try:
            result = create_admin_sale(
                admin_user_id=1,
                customer={
                    "mode": "existing",
                    "user_id": user_id,
                },
                items=[{"variant_id": variant_id, "quantity": 2}],
                register_payment=False,
                payment=None,
                db=session,
            )
            session.commit()
        finally:
            session.close()

        self.assertEqual(result["order"]["status"], "submitted")
        self.assertIsNone(result["payment"])
        self.assertFalse(result["meta"]["customer_created"])
        self.assertFalse(result["meta"]["payment_registered"])

    def test_create_admin_sale_new_user_with_bank_transfer_payment(self) -> None:
        variant_id = self._seed_variant()
        session = self.TestSession()
        try:
            result = create_admin_sale(
                admin_user_id=1,
                customer={
                    "mode": "new",
                    "first_name": "Carlos",
                    "last_name": "Perez",
                    "email": f"carlos-{datetime.now(UTC).timestamp()}@example.com",
                    "phone": "1133344455",
                },
                items=[{"variant_id": variant_id, "quantity": 1}],
                register_payment=True,
                payment={
                    "method": "bank_transfer",
                    "amount_paid": 10000,
                    "payment_ref": "BT-0001",
                },
                db=session,
            )
            queued_actions = list(session.info.get(POST_COMMIT_ACTIONS_KEY, []))
            session.commit()
        finally:
            session.close()

        self.assertEqual(result["order"]["status"], "paid")
        self.assertIsNotNone(result["payment"])
        self.assertEqual(result["payment"]["method"], "bank_transfer")
        self.assertIsNone(result["payment"]["change_amount"])
        self.assertTrue(result["meta"]["payment_registered"])
        self.assertTrue(result["meta"]["order_paid_email_suppressed"])
        self.assertEqual(queued_actions, [])

    def test_create_admin_sale_cash_requires_amount_minus_change_equals_total(self) -> None:
        variant_id = self._seed_variant()
        session = self.TestSession()
        try:
            with self.assertRaises(ValueError) as ctx:
                create_admin_sale(
                    admin_user_id=1,
                    customer={
                        "mode": "new",
                        "first_name": "Lara",
                        "last_name": "Gomez",
                        "email": f"lara-{datetime.now(UTC).timestamp()}@example.com",
                        "phone": "1199911122",
                    },
                    items=[{"variant_id": variant_id, "quantity": 1}],
                    register_payment=True,
                    payment={
                        "method": "cash",
                        "amount_paid": 12000,
                        "change_amount": 500,
                    },
                    db=session,
                )
            self.assertEqual(
                str(ctx.exception),
                "amount_paid minus change_amount must match order total",
            )
        finally:
            session.close()

    def test_create_admin_sale_cash_persists_change_amount(self) -> None:
        variant_id = self._seed_variant()
        session = self.TestSession()
        try:
            result = create_admin_sale(
                admin_user_id=1,
                customer={
                    "mode": "new",
                    "first_name": "Nora",
                    "last_name": "Lopez",
                    "email": f"nora-{datetime.now(UTC).timestamp()}@example.com",
                    "phone": "1122200011",
                },
                items=[{"variant_id": variant_id, "quantity": 1}],
                register_payment=True,
                payment={
                    "method": "cash",
                    "amount_paid": 12000,
                    "change_amount": 2000,
                },
                db=session,
            )
            session.commit()
        finally:
            session.close()

        self.assertEqual(result["order"]["status"], "paid")
        self.assertEqual(result["payment"]["method"], "cash")
        self.assertEqual(result["payment"]["change_amount"], 2000)

        session = self.TestSession()
        try:
            active = list_active_reservations_for_order(
                order_id=int(result["order"]["id"]),
                db=session,
            )
        finally:
            session.close()
        self.assertEqual(len(active), 0)

    def test_create_admin_sale_rejects_change_for_bank_transfer(self) -> None:
        variant_id = self._seed_variant()
        session = self.TestSession()
        try:
            with self.assertRaises(ValueError) as ctx:
                create_admin_sale(
                    admin_user_id=1,
                    customer={
                        "mode": "new",
                        "first_name": "Mora",
                        "last_name": "Ruiz",
                        "email": f"mora-{datetime.now(UTC).timestamp()}@example.com",
                        "phone": "1188811122",
                    },
                    items=[{"variant_id": variant_id, "quantity": 1}],
                    register_payment=True,
                    payment={
                        "method": "bank_transfer",
                        "amount_paid": 10000,
                        "change_amount": 0,
                        "payment_ref": "BT-02",
                    },
                    db=session,
                )
            self.assertEqual(
                str(ctx.exception),
                "change_amount is only allowed for cash payments",
            )
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
