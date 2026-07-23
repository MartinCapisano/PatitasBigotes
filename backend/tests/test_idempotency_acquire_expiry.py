import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base, IdempotencyRecord
from source.services.idempotency_s import (
    acquire_record,
    mark_record_completed,
)

SCOPE = "checkout_guest:a@b.com"


class AcquireExpiryTests(unittest.TestCase):
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
        self.db = self.TestSession()
        self.addCleanup(self.db.close)

    def _acquire(self, *, key="key-1", request_hash="hash-1", now=None, ttl_hours=24):
        moment = now or datetime.now(UTC)
        return acquire_record(
            scope=SCOPE,
            idempotency_key=key,
            request_hash=request_hash,
            expires_at=moment + timedelta(hours=ttl_hours),
            now=moment,
            db=self.db,
        )

    def _rows(self):
        return self.db.query(IdempotencyRecord).order_by(IdempotencyRecord.id).all()

    def test_a_live_collision_still_reports_the_existing_record(self) -> None:
        # The behaviour everything else depends on must not change.
        first, created = self._acquire()
        self.assertTrue(created)

        existing, created_again = self._acquire()
        self.assertFalse(created_again)
        self.assertEqual(existing.id, first.id)

    def test_an_expired_completed_record_does_not_replay_forever(self) -> None:
        # This is the failure the inline prune was covering: without an expiry
        # check the unique index keeps handing back a record past its TTL, and
        # the caller replays a stale response.
        stale = datetime.now(UTC) - timedelta(hours=25)
        record, _ = self._acquire(now=stale)
        mark_record_completed(record=record, response_payload={"old": True}, db=self.db)
        self.db.commit()

        fresh, created = self._acquire()

        self.assertTrue(created)
        self.assertEqual(fresh.status, "processing")
        self.assertEqual(fresh.response_payload, "{}")

    def test_an_expired_processing_record_does_not_wedge_the_key(self) -> None:
        # The other half: a stranded 'processing' would answer 409 forever.
        self._acquire(now=datetime.now(UTC) - timedelta(hours=25))
        self.db.commit()

        _, created = self._acquire()

        self.assertTrue(created)

    def test_the_expired_row_is_replaced_not_duplicated(self) -> None:
        self._acquire(now=datetime.now(UTC) - timedelta(hours=25))
        self.db.commit()
        self._acquire()

        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "processing")

    def test_the_replacement_carries_the_new_request_hash(self) -> None:
        # An expired key is genuinely free: a different payload may take it,
        # and must not trip the 409-on-different-hash check.
        self._acquire(request_hash="old-hash", now=datetime.now(UTC) - timedelta(hours=25))
        self.db.commit()

        fresh, created = self._acquire(request_hash="new-hash")

        self.assertTrue(created)
        self.assertEqual(fresh.request_hash, "new-hash")

    def test_expiry_is_inclusive_at_the_boundary(self) -> None:
        moment = datetime.now(UTC)
        self._acquire(now=moment - timedelta(hours=24))
        self.db.commit()

        _, created = self._acquire(now=moment)

        self.assertTrue(created)

    def test_a_record_one_second_from_expiring_is_still_live(self) -> None:
        moment = datetime.now(UTC)
        first, _ = self._acquire(now=moment - timedelta(hours=24) + timedelta(seconds=1))
        self.db.commit()

        existing, created = self._acquire(now=moment)

        self.assertFalse(created)
        self.assertEqual(existing.id, first.id)

    def test_only_the_acquired_key_is_touched(self) -> None:
        # The point of moving the expiry check in here: other requests' expired
        # rows are none of this transaction's business. The sweeper owns those.
        stale = datetime.now(UTC) - timedelta(hours=25)
        self._acquire(key="key-1", now=stale)
        self._acquire(key="key-2", now=stale)
        self._acquire(key="key-3", now=stale)
        self.db.commit()

        self._acquire(key="key-1")

        surviving = {row.idempotency_key for row in self._rows()}
        self.assertEqual(surviving, {"key-1", "key-2", "key-3"})

    def test_expired_rows_left_behind_are_still_individually_claimable(self) -> None:
        # Corollary of the above: nothing accumulates in a way that blocks a
        # caller. Bulk cleanup is a disk concern, not a correctness one.
        stale = datetime.now(UTC) - timedelta(hours=25)
        self._acquire(key="key-1", now=stale)
        self._acquire(key="key-2", now=stale)
        self.db.commit()

        _, first_created = self._acquire(key="key-1")
        _, second_created = self._acquire(key="key-2")

        self.assertTrue(first_created)
        self.assertTrue(second_created)

    def test_the_expiry_replacement_survives_a_commit(self) -> None:
        self._acquire(now=datetime.now(UTC) - timedelta(hours=25))
        self.db.commit()
        self._acquire(request_hash="new-hash")
        self.db.commit()

        other = self.TestSession()
        try:
            rows = other.query(IdempotencyRecord).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].request_hash, "new-hash")
            self.assertEqual(rows[0].status, "processing")
        finally:
            other.close()


if __name__ == "__main__":
    unittest.main()
