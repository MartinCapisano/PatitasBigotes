import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "test-secret-maintenance")
os.environ.setdefault("MERCADOPAGO_WEBHOOK_SECRET", "test-webhook-secret")

from source.services import maintenance_s
from source.services.maintenance_s import MaintenanceJob


class MaintenanceServiceTests(unittest.TestCase):
    def test_aggregates_results_and_reports_ok(self):
        fake_jobs = [
            MaintenanceJob("job_a", lambda: {"deleted": 2}),
            MaintenanceJob("job_b", lambda: {"selected": 0}),
        ]
        with patch.object(maintenance_s, "JOBS", fake_jobs):
            result = maintenance_s.run_all_maintenance()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["jobs"]["job_a"], {"ok": True, "result": {"deleted": 2}})
        self.assertEqual(result["jobs"]["job_b"], {"ok": True, "result": {"selected": 0}})

    def test_isolates_a_failing_job_and_reports_partial(self):
        def failing():
            raise ValueError("boom")

        fake_jobs = [
            MaintenanceJob("ok_job", lambda: {"deleted": 1}),
            MaintenanceJob("bad_job", failing),
            MaintenanceJob("also_ok", lambda: {"processed": 3}),
        ]
        with patch.object(maintenance_s, "JOBS", fake_jobs):
            result = maintenance_s.run_all_maintenance()

        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["jobs"]["ok_job"]["ok"])
        self.assertTrue(result["jobs"]["also_ok"]["ok"])  # ran despite earlier failure
        self.assertFalse(result["jobs"]["bad_job"]["ok"])
        self.assertIn("boom", result["jobs"]["bad_job"]["error"])

    def test_returns_busy_when_another_run_holds_the_lock(self):
        acquired = maintenance_s._run_lock.acquire(blocking=False)
        self.assertTrue(acquired)
        try:
            result = maintenance_s.run_all_maintenance()
        finally:
            maintenance_s._run_lock.release()

        self.assertEqual(result["status"], "busy")
        self.assertEqual(result["jobs"], {})


if __name__ == "__main__":
    unittest.main()
