import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.services.idempotency_s import build_authenticated_checkout_scope


class AuthenticatedCheckoutScopeTests(unittest.TestCase):
    def test_scope_shape(self) -> None:
        self.assertEqual(build_authenticated_checkout_scope(42), "checkout:42")

    def test_distinct_users_get_distinct_scopes(self) -> None:
        self.assertNotEqual(
            build_authenticated_checkout_scope(1),
            build_authenticated_checkout_scope(2),
        )

    def test_user_id_is_coerced_to_int(self) -> None:
        self.assertEqual(build_authenticated_checkout_scope("7"), "checkout:7")

    def test_non_numeric_user_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_authenticated_checkout_scope("not-a-number")


if __name__ == "__main__":
    unittest.main()
