import os
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DB_PATH = BACKEND_DIR / "tmp" / "tests" / "test_idempotency_resolve.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")

from source.db.models import Base
from source.db.session import SessionLocal, engine
from source.services.idempotency_s import (
    IdempotencyInProgressError,
    IdempotencyKeyReusedError,
    Outcome,
    acquire_record,
    canonicalize_payload,
    hash_payload,
    mark_record_completed,
    mark_record_failed,
    resolve_idempotency,
)

SCOPE = "checkout_guest:buyer@example.com"
KEY = "key-123"


class ResolveIdempotencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        if DB_PATH.exists():
            DB_PATH.unlink()
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        if DB_PATH.exists():
            DB_PATH.unlink()

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()

    def tearDown(self) -> None:
        self.db.close()

    def _seed_record(self, *, payload: dict, status: str, response: dict) -> None:
        """Toma la clave y la deja en el estado deseado, como haria un request previo."""
        request_hash = hash_payload(canonicalize_payload(payload))
        record, created = acquire_record(
            scope=SCOPE, idempotency_key=KEY, request_hash=request_hash, db=self.db
        )
        assert created
        if status == "completed":
            mark_record_completed(record=record, response_payload=response, db=self.db)
        elif status == "failed":
            mark_record_failed(record=record, response_payload=response, db=self.db)
        # status == "processing": queda como lo dejo acquire_record
        self.db.commit()

    def test_disabled_when_key_is_none(self) -> None:
        res = resolve_idempotency(scope=SCOPE, key=None, payload={"a": 1}, db=self.db)
        self.assertEqual(res.outcome, Outcome.EXECUTE)
        self.assertIsNone(res.record)
        self.assertIsNone(res.stored_payload)

    def test_disabled_when_key_is_blank(self) -> None:
        res = resolve_idempotency(scope=SCOPE, key="   ", payload={"a": 1}, db=self.db)
        self.assertEqual(res.outcome, Outcome.EXECUTE)
        self.assertIsNone(res.record)

    def test_fresh_key_acquires_and_executes(self) -> None:
        res = resolve_idempotency(scope=SCOPE, key=KEY, payload={"a": 1}, db=self.db)
        self.assertEqual(res.outcome, Outcome.EXECUTE)
        self.assertIsNotNone(res.record)
        self.assertEqual(res.record.status, "processing")
        self.assertIsNone(res.stored_payload)

    def test_reused_key_with_different_payload_raises(self) -> None:
        self._seed_record(payload={"a": 1}, status="completed", response={"ok": True})
        with self.assertRaises(IdempotencyKeyReusedError) as ctx:
            resolve_idempotency(scope=SCOPE, key=KEY, payload={"a": 2}, db=self.db)
        self.assertEqual(ctx.exception.scope, SCOPE)
        self.assertEqual(ctx.exception.idempotency_key, KEY)

    def test_completed_key_replays_stored_payload(self) -> None:
        self._seed_record(
            payload={"a": 1}, status="completed", response={"order_id": 7}
        )
        res = resolve_idempotency(scope=SCOPE, key=KEY, payload={"a": 1}, db=self.db)
        self.assertEqual(res.outcome, Outcome.REPLAY)
        self.assertEqual(res.stored_payload, {"order_id": 7})

    def test_failed_key_returns_recover(self) -> None:
        self._seed_record(
            payload={"a": 1},
            status="failed",
            response={"detail": "boom", "order_id": 7, "payment_id": 9},
        )
        res = resolve_idempotency(scope=SCOPE, key=KEY, payload={"a": 1}, db=self.db)
        self.assertEqual(res.outcome, Outcome.RECOVER)
        self.assertEqual(res.stored_payload["order_id"], 7)

    def test_processing_key_raises_in_progress(self) -> None:
        self._seed_record(payload={"a": 1}, status="processing", response={})
        with self.assertRaises(IdempotencyInProgressError) as ctx:
            resolve_idempotency(scope=SCOPE, key=KEY, payload={"a": 1}, db=self.db)
        self.assertEqual(ctx.exception.idempotency_key, KEY)


if __name__ == "__main__":
    unittest.main()
