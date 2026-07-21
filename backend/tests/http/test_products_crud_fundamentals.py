from backend.tests.factories.http_catalog import create_catalog
from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import Category, Product, ProductVariant


class HttpProductsCrudFundamentalsTests(HttpFundamentalsBase):
    def _login_as_admin(self, *, email: str = "catalog-crud-admin@example.com") -> None:
        self._create_user(email=email, is_admin=True, verified=True)
        login_response = self._login(email=email)
        self.assertEqual(login_response.status_code, 200)

    def test_admin_catalog_mutations_require_admin_over_http(self) -> None:
        response = self.client.post(
            "/categories",
            json={"name": "Nueva"},
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 401)

        self._create_user(email="catalog-crud-regular@example.com", verified=True)
        login_response = self._login(email="catalog-crud-regular@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            "/categories",
            json={"name": "Nueva"},
            headers=self._origin_headers(),
        )
        self.assertEqual(response.status_code, 403)

    # -- categories --

    def test_create_category_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.post(
            "/categories",
            json={"name": "Juguetes"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["name"], "Juguetes")

        db = self._db()
        try:
            self.assertIsNotNone(db.query(Category).filter(Category.name == "Juguetes").first())
        finally:
            db.close()

    def test_create_category_rejects_duplicate_name_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.post(
            "/categories",
            json={"name": "Accesorios"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "category already exists")
        self.assertIsNotNone(ids)

    def test_update_category_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.put(
            f"/categories/{ids['category_a']}",
            json={"name": "Accesorios Renovados"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["name"], "Accesorios Renovados")

    def test_update_category_missing_returns_404_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.put(
            "/categories/999999",
            json={"name": "No existe"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Category not found")

    def test_delete_empty_category_over_http(self) -> None:
        self._login_as_admin()
        response = self.client.post(
            "/categories",
            json={"name": "Categoria Vacia"},
            headers=self._origin_headers(),
        )
        category_id = response.json()["data"]["id"]

        response = self.client.delete(
            f"/categories/{category_id}",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        db = self._db()
        try:
            self.assertIsNone(db.query(Category).filter(Category.id == category_id).first())
        finally:
            db.close()

    def test_delete_category_with_products_is_rejected_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.delete(
            f"/categories/{ids['category_b']}",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("associated product", response.json()["detail"])
        db = self._db()
        try:
            self.assertIsNotNone(db.query(Category).filter(Category.id == ids["category_b"]).first())
        finally:
            db.close()

    # -- products --

    def test_create_product_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.post(
            "/products",
            json={
                "name": "Rascador",
                "description": "Rascador para gatos",
                "category": "Accesorios",
                "active": True,
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["name"], "Rascador")
        self.assertIsNotNone(ids)

    def test_create_product_rejects_unknown_category_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.post(
            "/products",
            json={
                "name": "Producto sin categoria",
                "category": "No Existe",
                "active": True,
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "category not found")

    def test_update_product_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.put(
            f"/products/{ids['product_1']}",
            json={
                "name": "Collar A Renovado",
                "category": "Accesorios",
                "active": False,
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["name"], "Collar A Renovado")
        self.assertFalse(payload["active"])

    def test_patch_product_requires_at_least_one_field_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.patch(
            f"/products/{ids['product_1']}",
            json={},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "at least one field is required")

    def test_patch_product_partial_update_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.patch(
            f"/products/{ids['product_1']}",
            json={"active": False},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertFalse(payload["active"])
        self.assertEqual(payload["name"], "Collar A")

    def test_delete_product_missing_returns_404_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.delete(
            "/products/999999",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Product not found")

    def test_delete_product_without_variants_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
        finally:
            db.close()
        self._login_as_admin()
        create_response = self.client.post(
            "/products",
            json={"name": "Sin variantes", "category": "Accesorios", "active": True},
            headers=self._origin_headers(),
        )
        product_id = create_response.json()["data"]["id"]

        response = self.client.delete(
            f"/products/{product_id}",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        db = self._db()
        try:
            self.assertIsNone(db.query(Product).filter(Product.id == product_id).first())
        finally:
            db.close()
        self.assertIsNotNone(ids)

    def test_delete_product_with_variants_cascades_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.delete(
            f"/products/{ids['product_3']}",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        db = self._db()
        try:
            self.assertIsNone(db.query(Product).filter(Product.id == ids["product_3"]).first())
            self.assertEqual(
                db.query(ProductVariant)
                .filter(ProductVariant.product_id == ids["product_3"])
                .count(),
                0,
            )
        finally:
            db.close()

    # -- variants --

    def test_create_variant_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.post(
            "/variants",
            json={
                "product_id": ids["product_1"],
                "sku": "SKU-NEW-1",
                "size": "L",
                "color": "Black",
                "price": 15000,
                "stock": 5,
                "active": True,
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["sku"], "SKU-NEW-1")

    def test_create_variant_rejects_negative_price_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.post(
            "/variants",
            json={
                "product_id": ids["product_1"],
                "sku": "SKU-BAD-PRICE",
                "price": -1,
                "stock": 1,
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 422)

    def test_update_variant_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
            variant_id = (
                db.query(ProductVariant)
                .filter(ProductVariant.product_id == ids["product_1"], ProductVariant.sku == "SKU-A1")
                .one()
                .id
            )
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.put(
            f"/variants/{variant_id}",
            json={
                "product_id": ids["product_1"],
                "sku": "SKU-A1",
                "price": 20000,
                "stock": 3,
                "active": True,
            },
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["price"], 20000)

    def test_patch_variant_partial_update_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
            variant_id = (
                db.query(ProductVariant)
                .filter(ProductVariant.product_id == ids["product_1"], ProductVariant.sku == "SKU-A1")
                .one()
                .id
            )
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.patch(
            f"/variants/{variant_id}",
            json={"stock": 99},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["stock"], 99)
        self.assertEqual(payload["sku"], "SKU-A1")

    def test_delete_variant_over_http(self) -> None:
        db = self._db()
        try:
            ids = create_catalog(db)
            variant_id = (
                db.query(ProductVariant)
                .filter(ProductVariant.product_id == ids["product_1"], ProductVariant.sku == "SKU-A2")
                .one()
                .id
            )
        finally:
            db.close()
        self._login_as_admin()

        response = self.client.delete(
            f"/variants/{variant_id}",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        db = self._db()
        try:
            self.assertIsNone(db.query(ProductVariant).filter(ProductVariant.id == variant_id).first())
        finally:
            db.close()

    def test_delete_variant_missing_returns_404_over_http(self) -> None:
        self._login_as_admin()

        response = self.client.delete(
            "/variants/999999",
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Variant not found")
