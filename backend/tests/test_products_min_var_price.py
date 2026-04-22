import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base, Category, Discount, Product, ProductVariant
from source.services import products_s


class ProductsMinVarPriceTests(unittest.TestCase):
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

        session = self.TestSession()
        try:
            session.add_all([Category(name="cat"), Category(name="dog")])
            session.commit()
        finally:
            session.close()

    def test_create_product_without_price_and_without_variants(self) -> None:
        session = self.TestSession()
        try:
            product = products_s.create_product(
                {
                    "name": "Producto sin variantes",
                    "description": "demo",
                    "category": "cat",
                    "active": True,
                },
                db=session,
            )
            session.commit()
        finally:
            session.close()
        self.assertIn("min_var_price", product)
        self.assertIsNone(product["min_var_price"])

    def test_get_product_returns_min_var_price_from_active_variants_only(self) -> None:
        session = self.TestSession()
        try:
            p = Product(name="P1", description=None, category_id=1)
            session.add(p)
            session.flush()
            session.add_all(
                [
                    ProductVariant(
                        product_id=p.id,
                        sku="P1-A",
                        size="S",
                        color="red",
                        price=120000,
                        stock=1,
                        is_active=True,
                    ),
                    ProductVariant(
                        product_id=p.id,
                        sku="P1-B",
                        size="M",
                        color="blue",
                        price=90000,
                        stock=0,
                        is_active=False,
                    ),
                    ProductVariant(
                        product_id=p.id,
                        sku="P1-C",
                        size="L",
                        color="black",
                        price=150000,
                        stock=2,
                        is_active=True,
                    ),
                ]
            )
            session.commit()
            product_id = p.id
        finally:
            session.close()

        session = self.TestSession()
        try:
            payload = products_s.get_product_by_id(product_id, db=session)
        finally:
            session.close()
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["min_var_price"], 120000)

    def test_filter_by_min_price_uses_min_var_price(self) -> None:
        session = self.TestSession()
        try:
            p1 = Product(name="P1", description=None, category_id=1)
            p2 = Product(name="P2", description=None, category_id=1)
            session.add_all([p1, p2])
            session.flush()
            session.add_all(
                [
                    ProductVariant(
                        product_id=p1.id,
                        sku="P1-A",
                        size=None,
                        color=None,
                        price=50000,
                        stock=1,
                        is_active=True,
                    ),
                    ProductVariant(
                        product_id=p2.id,
                        sku="P2-A",
                        size=None,
                        color=None,
                        price=150000,
                        stock=1,
                        is_active=True,
                    ),
                ]
            )
            session.commit()
        finally:
            session.close()

        session = self.TestSession()
        try:
            data = products_s.filter_and_sort_products(min_price=100000, db=session)
        finally:
            session.close()
        names = [product["name"] for product in data]
        self.assertEqual(names, ["P2"])

    def test_filter_by_min_price_ignores_inactive_variants(self) -> None:
        session = self.TestSession()
        try:
            p1 = Product(name="P1", description=None, category_id=1)
            session.add(p1)
            session.flush()
            session.add_all(
                [
                    ProductVariant(
                        product_id=p1.id,
                        sku="P1-ACTIVE",
                        size=None,
                        color=None,
                        price=120000,
                        stock=1,
                        is_active=True,
                    ),
                    ProductVariant(
                        product_id=p1.id,
                        sku="P1-INACTIVE",
                        size=None,
                        color=None,
                        price=50000,
                        stock=0,
                        is_active=False,
                    ),
                ]
            )
            session.commit()
        finally:
            session.close()

        session = self.TestSession()
        try:
            data = products_s.filter_and_sort_products(max_price=100000, db=session)
        finally:
            session.close()
        self.assertEqual(data, [])

    def test_sort_by_price_orders_by_min_var_price(self) -> None:
        session = self.TestSession()
        try:
            p1 = Product(name="P1", description=None, category_id=1)
            p2 = Product(name="P2", description=None, category_id=1)
            session.add_all([p1, p2])
            session.flush()
            session.add_all(
                [
                    ProductVariant(
                        product_id=p1.id,
                        sku="P1-A",
                        size=None,
                        color=None,
                        price=200000,
                        stock=1,
                        is_active=True,
                    ),
                    ProductVariant(
                        product_id=p2.id,
                        sku="P2-A",
                        size=None,
                        color=None,
                        price=100000,
                        stock=1,
                        is_active=True,
                    ),
                ]
            )
            session.commit()
        finally:
            session.close()

        session = self.TestSession()
        try:
            data = products_s.filter_and_sort_products(
                sort_by="price",
                sort_order="asc",
                db=session,
            )
        finally:
            session.close()
        names = [product["name"] for product in data if product["min_var_price"] is not None]
        self.assertEqual(names[:2], ["P2", "P1"])

    def test_storefront_price_filter_uses_discounted_min_final_price(self) -> None:
        session = self.TestSession()
        try:
            p1 = Product(name="P1", description=None, category_id=1)
            p2 = Product(name="P2", description=None, category_id=1)
            session.add_all([p1, p2])
            session.flush()
            session.add_all(
                [
                    ProductVariant(
                        product_id=p1.id,
                        sku="P1-A",
                        size=None,
                        color=None,
                        price=100000,
                        stock=1,
                        is_active=True,
                    ),
                    ProductVariant(
                        product_id=p2.id,
                        sku="P2-A",
                        size=None,
                        color=None,
                        price=70000,
                        stock=1,
                        is_active=True,
                    ),
                    Discount(
                        name="Half off P1",
                        type="percent",
                        value=50,
                        scope="product",
                        product_id=p1.id,
                        is_active=True,
                    ),
                ]
            )
            session.commit()
        finally:
            session.close()

        session = self.TestSession()
        try:
            data, total = products_s.list_storefront_products(max_price=60000, db=session)
        finally:
            session.close()
        self.assertEqual(total, 1)
        self.assertEqual([product["name"] for product in data], ["P1"])
        self.assertEqual(data[0]["min_var_price_original"], 100000)
        self.assertEqual(data[0]["min_var_price_final"], 50000)

    def test_storefront_price_sort_uses_discounted_min_final_price(self) -> None:
        session = self.TestSession()
        try:
            p1 = Product(name="P1", description=None, category_id=1)
            p2 = Product(name="P2", description=None, category_id=1)
            session.add_all([p1, p2])
            session.flush()
            session.add_all(
                [
                    ProductVariant(
                        product_id=p1.id,
                        sku="P1-A",
                        size=None,
                        color=None,
                        price=100000,
                        stock=1,
                        is_active=True,
                    ),
                    ProductVariant(
                        product_id=p2.id,
                        sku="P2-A",
                        size=None,
                        color=None,
                        price=70000,
                        stock=1,
                        is_active=True,
                    ),
                    Discount(
                        name="Half off P1",
                        type="percent",
                        value=50,
                        scope="product",
                        product_id=p1.id,
                        is_active=True,
                    ),
                ]
            )
            session.commit()
        finally:
            session.close()

        session = self.TestSession()
        try:
            data, total = products_s.list_storefront_products(
                sort_by="price",
                sort_order="asc",
                db=session,
            )
        finally:
            session.close()
        self.assertEqual(total, 2)
        self.assertEqual([product["name"] for product in data], ["P1", "P2"])


if __name__ == "__main__":
    unittest.main()
