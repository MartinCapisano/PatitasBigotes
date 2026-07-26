import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.schemas import AuthenticatedCheckoutRequest
from source.schemas.orders_s import PublicGuestCheckoutItemRequest


class AuthenticatedCheckoutRequestTests(unittest.TestCase):
    def test_reuses_guest_item_schema(self) -> None:
        request = AuthenticatedCheckoutRequest(items=[{"variant_id": 1, "quantity": 2}])
        self.assertIsInstance(request.items[0], PublicGuestCheckoutItemRequest)
        self.assertEqual(request.currency, "ARS")
        self.assertEqual(request.expires_in_minutes, 60)
        self.assertIsNone(request.payment_method)

    def test_empty_items_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            AuthenticatedCheckoutRequest(items=[])

    def test_invalid_payment_method_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            AuthenticatedCheckoutRequest(
                items=[{"variant_id": 1, "quantity": 1}],
                payment_method="crypto",
            )

    def test_item_quantity_bounds_come_from_guest_schema(self) -> None:
        with self.assertRaises(ValidationError):
            AuthenticatedCheckoutRequest(items=[{"variant_id": 1, "quantity": 11}])

    def test_customer_and_website_are_forbidden(self) -> None:
        with self.assertRaises(ValidationError):
            AuthenticatedCheckoutRequest(
                items=[{"variant_id": 1, "quantity": 1}],
                website="",
            )

    def test_expires_in_minutes_must_be_positive(self) -> None:
        with self.assertRaises(ValidationError):
            AuthenticatedCheckoutRequest(
                items=[{"variant_id": 1, "quantity": 1}],
                expires_in_minutes=0,
            )


if __name__ == "__main__":
    unittest.main()
