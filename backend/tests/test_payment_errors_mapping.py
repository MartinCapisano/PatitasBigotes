import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import os

os.environ.setdefault("MERCADOPAGO_ACCESS_TOKEN", "test-access-token")
os.environ.setdefault("MERCADOPAGO_TIMEOUT_SECONDS", "10")

from source.services.mercadopago_client import _handle_response_status, get_payment_by_id
from source.services.payment_errors import (
    PaymentProviderAuthError,
    PaymentProviderError,
    PaymentProviderTimeoutError,
    PaymentProviderValidationError,
)


class HandleResponseStatusTests(unittest.TestCase):
    def test_validation_status_codes_raise_validation_error(self) -> None:
        for status in (400, 402, 404, 409, 422):
            with self.subTest(status=status):
                with self.assertRaises(PaymentProviderValidationError):
                    _handle_response_status(status, operation="preference creation")

    def test_auth_status_codes_raise_auth_error(self) -> None:
        for status in (401, 403):
            with self.subTest(status=status):
                with self.assertRaises(PaymentProviderAuthError):
                    _handle_response_status(status, operation="preference creation")

    def test_other_4xx_status_raises_generic_provider_error(self) -> None:
        with self.assertRaises(PaymentProviderError):
            _handle_response_status(418, operation="preference creation")

    def test_success_status_does_not_raise(self) -> None:
        try:
            _handle_response_status(200, operation="preference creation")
            _handle_response_status(201, operation="preference creation")
        except PaymentProviderError:
            self.fail("_handle_response_status raised for a successful status code")


class MercadopagoClientTimeoutMappingTests(unittest.TestCase):
    def test_get_payment_by_id_maps_sdk_timeout_to_provider_timeout_error(self) -> None:
        fake_sdk = type("FakeSdk", (), {})()
        fake_payment_client = type(
            "FakePaymentClient",
            (),
            {"get": lambda self, *args, **kwargs: (_ for _ in ()).throw(TimeoutError("boom"))},
        )()
        fake_sdk.payment = lambda: fake_payment_client

        with patch("source.services.mercadopago_client._get_sdk", return_value=fake_sdk), patch(
            "source.services.mercadopago_client.time.sleep"
        ):
            with self.assertRaises(PaymentProviderTimeoutError):
                get_payment_by_id("123")


if __name__ == "__main__":
    unittest.main()
