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

from source.db.models import Base, IdempotencyRecord
from source.jobs import idempotency_sweeper_job


class IdempotencySweeperJobRunOnceTests(unittest.TestCase):
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
            idempotency_sweeper_job,
            "SessionLocal",
            self.TestSession,
        )
        self._session_local_patch.start()

    def tearDown(self) -> None:
        self._session_local_patch.stop()

    def _seed_record(
        self,
        *,
        scope: str,
        key: str,
        status: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        db = self.TestSession()
        try:
            db.add(
                IdempotencyRecord(
                    scope=scope,
                    idempotency_key=key,
                    request_hash="hash",
                    response_payload="{}",
                    status=status,
                    created_at=created_at,
                    expires_at=expires_at,
                )
            )
            db.commit()
        finally:
            db.close()

    def test_run_once_prunes_expired_records(self) -> None:
        now = datetime.now(UTC)
        self._seed_record(
            scope="checkout",
            key="expired-1",
            status="completed",
            created_at=now - timedelta(days=2),
            expires_at=now - timedelta(hours=1),
        )

        result = idempotency_sweeper_job.run_once(processing_timeout_minutes=30, limit=200)

        self.assertEqual(result, {"pruned": 1, "marked_failed": 0})

    def test_run_once_marks_stuck_processing_records_as_failed(self) -> None:
        now = datetime.now(UTC)
        self._seed_record(
            scope="checkout",
            key="stuck-1",
            status="processing",
            created_at=now - timedelta(minutes=60),
            expires_at=now + timedelta(hours=1),
        )

        result = idempotency_sweeper_job.run_once(processing_timeout_minutes=30, limit=200)

        self.assertEqual(result, {"pruned": 0, "marked_failed": 1})

        db = self.TestSession()
        try:
            record = db.query(IdempotencyRecord).filter(IdempotencyRecord.idempotency_key == "stuck-1").first()
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record.status, "failed")
            self.assertIn("processing timeout", record.response_payload)
        finally:
            db.close()

    def test_run_once_ignores_recent_processing_records(self) -> None:
        now = datetime.now(UTC)
        self._seed_record(
            scope="checkout",
            key="recent-1",
            status="processing",
            created_at=now - timedelta(minutes=5),
            expires_at=now + timedelta(hours=1),
        )

        result = idempotency_sweeper_job.run_once(processing_timeout_minutes=30, limit=200)

        self.assertEqual(result, {"pruned": 0, "marked_failed": 0})

    def test_run_once_respects_limit(self) -> None:
        now = datetime.now(UTC)
        for i in range(3):
            self._seed_record(
                scope="checkout",
                key=f"expired-limit-{i}",
                status="completed",
                created_at=now - timedelta(days=2),
                expires_at=now - timedelta(hours=1),
            )

        result = idempotency_sweeper_job.run_once(processing_timeout_minutes=30, limit=2)

        self.assertEqual(result["pruned"], 2)


if __name__ == "__main__":
    unittest.main()
