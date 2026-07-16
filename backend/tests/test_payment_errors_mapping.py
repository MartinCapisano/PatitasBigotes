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

from source.services.mercadopago_client import (
    _handle_response_status,
    create_checkout_preference,
    create_refund,
    get_payment_by_id,
)
from source.services.payment_errors import (
    PaymentProviderAuthError,
    PaymentProviderError,
    PaymentProviderTimeoutError,
    PaymentProviderUnavailableError,
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


class _QueuedResource:
    """Fake mercadopago SDK sub-resource (preference()/payment()/refund()) that
    replays a fixed sequence of responses or exceptions, one per call."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)

    def _next(self, *args, **kwargs) -> dict:
        if not self._responses:
            raise AssertionError("no more queued fake SDK responses")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    create = _next
    get = _next
    search = _next


class _FakeSdk:
    def __init__(self, *, preference=None, payment=None, refund=None) -> None:
        self._preference = _QueuedResource(preference or [])
        self._payment = _QueuedResource(payment or [])
        self._refund = _QueuedResource(refund or [])

    def preference(self) -> _QueuedResource:
        return self._preference

    def payment(self) -> _QueuedResource:
        return self._payment

    def refund(self) -> _QueuedResource:
        return self._refund


def _ok_response(status: int, data: dict) -> dict:
    return {"status": status, "response": data}


class MercadopagoClientFullFunctionTests(unittest.TestCase):
    def _patched_sdk(self, fake_sdk: _FakeSdk):
        return patch("source.services.mercadopago_client._get_sdk", return_value=fake_sdk)

    def _no_sleep(self):
        return patch("source.services.mercadopago_client.time.sleep")

    def test_create_checkout_preference_happy_path(self) -> None:
        fake_sdk = _FakeSdk(
            preference=[
                _ok_response(201, {"id": "pref-1", "init_point": "https://mp.test/checkout/pref-1"}),
            ]
        )
        with self._patched_sdk(fake_sdk), self._no_sleep():
            data = create_checkout_preference({"items": []})

        self.assertEqual(data["id"], "pref-1")

    def test_create_checkout_preference_retries_after_5xx_then_succeeds(self) -> None:
        fake_sdk = _FakeSdk(
            preference=[
                _ok_response(500, {}),
                _ok_response(201, {"id": "pref-2", "init_point": "https://mp.test/checkout/pref-2"}),
            ]
        )
        with self._patched_sdk(fake_sdk), self._no_sleep():
            data = create_checkout_preference({"items": []})

        self.assertEqual(data["id"], "pref-2")

    def test_create_checkout_preference_raises_after_exhausting_retries_on_5xx(self) -> None:
        fake_sdk = _FakeSdk(
            preference=[_ok_response(500, {}), _ok_response(500, {}), _ok_response(500, {})]
        )
        with self._patched_sdk(fake_sdk), self._no_sleep():
            with self.assertRaises(PaymentProviderUnavailableError):
                create_checkout_preference({"items": []})

    def test_create_checkout_preference_rejects_response_missing_checkout_url(self) -> None:
        fake_sdk = _FakeSdk(preference=[_ok_response(201, {"id": "pref-3"})])
        with self._patched_sdk(fake_sdk), self._no_sleep():
            with self.assertRaises(PaymentProviderValidationError):
                create_checkout_preference({"items": []})

    def test_create_checkout_preference_maps_validation_status_from_sdk(self) -> None:
        fake_sdk = _FakeSdk(preference=[_ok_response(400, {})])
        with self._patched_sdk(fake_sdk), self._no_sleep():
            with self.assertRaises(PaymentProviderValidationError):
                create_checkout_preference({"items": []})

    def test_get_payment_by_id_happy_path(self) -> None:
        fake_sdk = _FakeSdk(payment=[_ok_response(200, {"id": "pay-1", "status": "approved"})])
        with self._patched_sdk(fake_sdk), self._no_sleep():
            data = get_payment_by_id("pay-1")

        self.assertEqual(data["status"], "approved")

    def test_get_payment_by_id_raises_after_exhausting_retries_on_generic_sdk_exception(self) -> None:
        fake_sdk = _FakeSdk(
            payment=[RuntimeError("network down"), RuntimeError("network down"), RuntimeError("network down")]
        )
        with self._patched_sdk(fake_sdk), self._no_sleep():
            with self.assertRaises(PaymentProviderUnavailableError):
                get_payment_by_id("pay-1")

    def test_create_refund_happy_path(self) -> None:
        fake_sdk = _FakeSdk(refund=[_ok_response(201, {"id": "refund-1", "status": "approved"})])
        with self._patched_sdk(fake_sdk), self._no_sleep():
            data = create_refund(payment_id="pay-1", amount=1000)

        self.assertEqual(data["id"], "refund-1")

    def test_create_refund_raises_when_response_payload_is_not_a_dict(self) -> None:
        fake_sdk = _FakeSdk(
            refund=[
                _ok_response(201, None),
                _ok_response(201, None),
                _ok_response(201, None),
            ]
        )
        with self._patched_sdk(fake_sdk), self._no_sleep():
            with self.assertRaises(PaymentProviderUnavailableError):
                create_refund(payment_id="pay-1")

    def test_create_refund_rejects_non_positive_amount(self) -> None:
        with self.assertRaises(PaymentProviderValidationError):
            create_refund(payment_id="pay-1", amount=0)


if __name__ == "__main__":
    unittest.main()
