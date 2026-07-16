import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import AuthLoginThrottle, Base
from source.jobs import prune_auth_login_throttles_job


class PruneAuthLoginThrottlesJobRunOnceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine("sqlite:///:memory:")
        cls.TestSession = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=cls.engine,
        )
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self._session_local_patch = patch.object(
            prune_auth_login_throttles_job,
            "SessionLocal",
            self.TestSession,
        )
        self._session_local_patch.start()

    def tearDown(self) -> None:
        self._session_local_patch.stop()

    def test_run_once_deletes_old_rows_and_returns_count(self) -> None:
        db = self.TestSession()
        try:
            old_ts = datetime.now(UTC) - timedelta(days=30)
            db.add(
                AuthLoginThrottle(
                    scope="email",
                    key="job-old@example.com",
                    failed_count=1,
                    window_started_at=old_ts,
                    blocked_until=None,
                    updated_at=old_ts,
                )
            )
            db.commit()
        finally:
            db.close()

        deleted = prune_auth_login_throttles_job.run_once(older_than_days=14, batch_size=1000)

        self.assertEqual(deleted, 1)

    def test_run_once_keeps_recent_rows(self) -> None:
        db = self.TestSession()
        try:
            recent_ts = datetime.now(UTC) - timedelta(days=1)
            db.add(
                AuthLoginThrottle(
                    scope="ip",
                    key="1.2.3.4",
                    failed_count=1,
                    window_started_at=recent_ts,
                    blocked_until=None,
                    updated_at=recent_ts,
                )
            )
            db.commit()
        finally:
            db.close()

        deleted = prune_auth_login_throttles_job.run_once(older_than_days=14, batch_size=1000)

        self.assertEqual(deleted, 0)
        db = self.TestSession()
        try:
            self.assertEqual(db.query(AuthLoginThrottle).count(), 1)
        finally:
            db.close()

    def test_run_once_respects_batch_size(self) -> None:
        db = self.TestSession()
        try:
            old_ts = datetime.now(UTC) - timedelta(days=30)
            db.add_all(
                [
                    AuthLoginThrottle(
                        scope="email",
                        key=f"job-batch-{i}@example.com",
                        failed_count=1,
                        window_started_at=old_ts,
                        blocked_until=None,
                        updated_at=old_ts,
                    )
                    for i in range(3)
                ]
            )
            db.commit()
        finally:
            db.close()

        deleted = prune_auth_login_throttles_job.run_once(older_than_days=14, batch_size=2)

        self.assertEqual(deleted, 2)


if __name__ == "__main__":
    unittest.main()
