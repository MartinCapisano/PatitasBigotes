"""R01-3: el handler central mapea IdempotencyError -> 409.

Los endpoints todavia lanzan HTTPException inline (hasta R01-5/R01-7), asi que
aca se ejerce el handler de main sobre un app-probe con rutas de prueba, y se
verifica ademas que quedo registrado en el app real.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.tests.http._base import HttpFundamentalsBase  # noqa: F401  (setea env + importa app)
from main import app as main_app, handle_idempotency_error
from source.services.idempotency_s import (
    IdempotencyError,
    IdempotencyInProgressError,
    IdempotencyKeyReusedError,
)

import unittest


class IdempotencyErrorHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        probe = FastAPI()
        probe.add_exception_handler(IdempotencyError, handle_idempotency_error)

        @probe.get("/reused")
        def _reused():
            raise IdempotencyKeyReusedError("checkout_guest:x@example.com", "k1")

        @probe.get("/inprogress")
        def _inprogress():
            raise IdempotencyInProgressError("admin_sales:1", "k2")

        self.client = TestClient(probe)

    def tearDown(self) -> None:
        self.client.close()

    def test_handler_is_registered_on_the_real_app(self) -> None:
        self.assertIn(IdempotencyError, main_app.exception_handlers)

    def test_reused_key_maps_to_409_with_stable_detail(self) -> None:
        response = self.client.get("/reused")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            "idempotency key already used with a different payload",
        )

    def test_in_progress_maps_to_409_with_stable_detail(self) -> None:
        response = self.client.get("/inprogress")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            "idempotent request already in progress",
        )


if __name__ == "__main__":
    unittest.main()
