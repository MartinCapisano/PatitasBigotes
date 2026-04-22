import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.schemas.products_s import (
    CreateProductRequest,
    CreateVariantRequest,
    PatchProductRequest,
    PatchVariantRequest,
)


class ProductSchemaConstraintsTests(unittest.TestCase):
    def test_product_name_and_category_must_not_be_blank(self) -> None:
        with self.assertRaises(ValidationError):
            CreateProductRequest(name="   ", category="cat")

        with self.assertRaises(ValidationError):
            CreateProductRequest(name="Collar", category="   ")

    def test_product_name_has_max_length(self) -> None:
        with self.assertRaises(ValidationError):
            PatchProductRequest(name="x" * 121)

    def test_variant_price_must_be_positive_and_stock_non_negative(self) -> None:
        with self.assertRaises(ValidationError):
            CreateVariantRequest(product_id=1, sku="SKU-1", price=0)

        with self.assertRaises(ValidationError):
            CreateVariantRequest(product_id=1, sku="SKU-1", price=1000, stock=-1)

    def test_variant_identity_fields_are_constrained(self) -> None:
        with self.assertRaises(ValidationError):
            CreateVariantRequest(product_id=0, sku="SKU-1", price=1000)

        with self.assertRaises(ValidationError):
            PatchVariantRequest(sku="   ")

    def test_valid_payloads_still_parse(self) -> None:
        product = CreateProductRequest(name="  Collar  ", category="  Accesorios  ")
        variant = CreateVariantRequest(product_id=1, sku="  SKU-1  ", price=1000, stock=0)

        self.assertEqual(product.name, "Collar")
        self.assertEqual(product.category, "Accesorios")
        self.assertEqual(variant.sku, "SKU-1")
        self.assertEqual(variant.stock, 0)


if __name__ == "__main__":
    unittest.main()
