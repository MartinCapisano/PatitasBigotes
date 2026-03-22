from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import Category, Product, ProductVariant


class HttpCatalogFundamentalsTests(HttpFundamentalsBase):
    def _seed_catalog(self) -> dict[str, int]:
        db = self._db()
        try:
            cat_a = Category(name="Accesorios")
            cat_b = Category(name="Alimento")
            db.add_all([cat_a, cat_b])
            db.flush()

            p1 = Product(name="Collar A", description="d1", category_id=int(cat_a.id))
            p2 = Product(name="Correa B", description="d2", category_id=int(cat_a.id))
            p3 = Product(name="Comida C", description="d3", category_id=int(cat_b.id))
            db.add_all([p1, p2, p3])
            db.flush()

            db.add_all(
                [
                    ProductVariant(
                        product_id=int(p1.id),
                        sku="SKU-A1",
                        size="S",
                        color="Red",
                        price=10000,
                        stock=2,
                        is_active=True,
                    ),
                    ProductVariant(
                        product_id=int(p1.id),
                        sku="SKU-A2",
                        size="M",
                        color="Blue",
                        price=12000,
                        stock=0,
                        is_active=False,
                    ),
                    ProductVariant(
                        product_id=int(p2.id),
                        sku="SKU-B1",
                        size="U",
                        color="Black",
                        price=25000,
                        stock=0,
                        is_active=True,
                    ),
                    ProductVariant(
                        product_id=int(p3.id),
                        sku="SKU-C1",
                        size="L",
                        color="Green",
                        price=40000,
                        stock=5,
                        is_active=True,
                    ),
                ]
            )
            db.commit()
            return {
                "category_a": int(cat_a.id),
                "category_b": int(cat_b.id),
                "product_1": int(p1.id),
                "product_2": int(p2.id),
                "product_3": int(p3.id),
            }
        finally:
            db.close()

    def test_storefront_products_pagination_meta_is_consistent_over_http(self) -> None:
        self._seed_catalog()

        response = self.client.get(
            "/storefront/products",
            params={
                "sort_by": "created_at",
                "sort_order": "desc",
                "limit": 2,
                "offset": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        meta = payload["meta"]
        self.assertEqual(meta["limit"], 2)
        self.assertEqual(meta["offset"], 0)
        self.assertEqual(meta["total"], 3)
        self.assertTrue(meta["has_more"])
        self.assertEqual(len(payload["data"]), 2)

    def test_storefront_products_filter_combination_category_and_price_over_http(self) -> None:
        ids = self._seed_catalog()

        response = self.client.get(
            "/storefront/products",
            params={
                "category_id": ids["category_a"],
                "min_price": 9000,
                "max_price": 20000,
                "sort_by": "price",
                "sort_order": "asc",
            },
        )

        self.assertEqual(response.status_code, 200)
        product_ids = [item["id"] for item in response.json()["data"]]
        self.assertEqual(product_ids, [ids["product_1"]])

    def test_storefront_products_invalid_range_returns_400_over_http(self) -> None:
        self._seed_catalog()

        response = self.client.get(
            "/storefront/products",
            params={
                "min_price": 30000,
                "max_price": 10000,
                "sort_by": "price",
                "sort_order": "asc",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "min_price must be less than or equal to max_price",
        )

    def test_storefront_product_detail_returns_only_public_fields_over_http(self) -> None:
        ids = self._seed_catalog()

        response = self.client.get(f"/storefront/products/{ids['product_1']}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertNotIn("stock", payload)
        self.assertNotIn("active", payload)
        self.assertIn("option_axis", payload)
        self.assertIn("options", payload)
        self.assertEqual(len(payload["options"]), 1)
        option_payload = payload["options"][0]
        self.assertIn("in_stock", option_payload)
        self.assertIn("variant_id", option_payload)
        self.assertIn("label", option_payload)
        self.assertNotIn("stock", option_payload)
        self.assertNotIn("sku", option_payload)

    def test_storefront_products_search_by_name_over_http(self) -> None:
        ids = self._seed_catalog()

        response = self.client.get(
            "/storefront/products",
            params={
                "q": "comida",
                "sort_by": "name",
                "sort_order": "asc",
            },
        )

        self.assertEqual(response.status_code, 200)
        product_ids = [item["id"] for item in response.json()["data"]]
        self.assertEqual(product_ids, [ids["product_3"]])

    def test_storefront_product_detail_404_for_non_visible_product_over_http(self) -> None:
        self._seed_catalog()
        db = self._db()
        try:
            hidden_category = Category(name="Hidden")
            db.add(hidden_category)
            db.flush()

            hidden_product = Product(
                name="Hidden Product",
                description="hidden",
                category_id=int(hidden_category.id),
            )
            db.add(hidden_product)
            db.flush()

            db.add(
                ProductVariant(
                    product_id=int(hidden_product.id),
                    sku="SKU-HIDDEN-1",
                    size="U",
                    color="Gray",
                    price=9000,
                    stock=3,
                    is_active=False,
                )
            )
            db.commit()
            hidden_product_id = int(hidden_product.id)
        finally:
            db.close()

        response = self.client.get(f"/storefront/products/{hidden_product_id}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Product not found")

    def test_admin_catalog_returns_categories_products_and_variants_by_product_over_http(self) -> None:
        self._seed_catalog()
        self._create_user(email="catalog-admin@example.com", is_admin=True, verified=True)
        login_response = self._login(email="catalog-admin@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get("/admin/catalog")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertIn("categories", payload)
        self.assertIn("products", payload)
        self.assertIn("variants_by_product", payload)
        self.assertEqual(len(payload["categories"]), 2)
        self.assertEqual(len(payload["products"]), 3)
        self.assertIn("1", payload["variants_by_product"])
        self.assertEqual(len(payload["variants_by_product"]["1"]), 2)
        self.assertEqual(payload["variants_by_product"]["1"][0]["sku"], "SKU-A1")
        self.assertEqual(payload["variants_by_product"]["1"][1]["sku"], "SKU-A2")

    def test_get_products_include_variants_returns_aggregated_shape_over_http(self) -> None:
        self._seed_catalog()
        self._create_user(email="products-admin@example.com", is_admin=True, verified=True)
        login_response = self._login(email="products-admin@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get(
            "/products",
            params={
                "category": "Accesorios",
                "sort_by": "name",
                "sort_order": "asc",
                "include_variants": "true",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        meta = response.json()["meta"]
        self.assertIn("products", payload)
        self.assertIn("variants_by_product", payload)
        self.assertEqual(
            [product["name"] for product in payload["products"]],
            ["Collar A", "Correa B"],
        )
        self.assertEqual(sorted(payload["variants_by_product"].keys()), ["1", "2"])
        self.assertTrue(meta["include_variants"])

    def test_get_products_without_include_variants_keeps_legacy_shape_over_http(self) -> None:
        self._seed_catalog()
        self._create_user(email="products-legacy-admin@example.com", is_admin=True, verified=True)
        login_response = self._login(email="products-legacy-admin@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.get(
            "/products",
            params={
                "sort_order": "asc",
                "include_variants": "false",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertIsInstance(payload, list)
        self.assertEqual(len(payload), 3)
        self.assertIn("name", payload[0])
        self.assertNotIn("variants_by_product", response.json()["data"])
