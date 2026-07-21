import os
from unittest.mock import patch

os.environ.setdefault("MAINTENANCE_RUN_TOKEN", "test-maint-token")

from tests.http._base import HttpFundamentalsBase

TOKEN = "test-maint-token"
ENDPOINT = "/internal/maintenance/run"


class MaintenanceEndpointTests(HttpFundamentalsBase):
    def test_rejects_request_without_token(self):
        resp = self.client.post(ENDPOINT)
        self.assertEqual(resp.status_code, 401)

    def test_rejects_request_with_wrong_token(self):
        resp = self.client.post(ENDPOINT, headers={"Authorization": "Bearer not-the-token"})
        self.assertEqual(resp.status_code, 401)

    def test_runs_with_valid_token_and_without_browser_origin(self):
        canned = {
            "status": "ok",
            "jobs": {"reconcile_pending_payments": {"ok": True, "result": {"selected": 0}}},
        }
        # No Origin header is sent: passing here also proves the endpoint is
        # exempt from the CSRF Origin/Referer check (it is token-authenticated).
        with patch("source.routes.maintenance_r.run_all_maintenance", return_value=canned) as mock_run:
            resp = self.client.post(ENDPOINT, headers={"Authorization": f"Bearer {TOKEN}"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "ok")
        mock_run.assert_called_once()

    def test_returns_503_when_token_not_configured(self):
        with patch(
            "source.routes.maintenance_r.get_maintenance_run_token",
            side_effect=RuntimeError("MAINTENANCE_RUN_TOKEN is required"),
        ):
            resp = self.client.post(ENDPOINT, headers={"Authorization": f"Bearer {TOKEN}"})

        self.assertEqual(resp.status_code, 503)
