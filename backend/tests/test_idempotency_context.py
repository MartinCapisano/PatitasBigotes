import os
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DB_PATH = BACKEND_DIR / "tmp" / "tests" / "test_idempotency_context.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")

from source.db.models import Base, IdempotencyRecord
from source.db.session import SessionLocal, engine
from source.services.idempotency_s import (
    FailurePolicy,
    IdempotencyKeyReusedError,
    acquire_record,
    canonicalize_payload,
    get_record,
    hash_payload,
    idempotent,
    load_replay_payload,
    mark_record_completed,
    mark_record_failed,
)

SCOPE = "checkout_guest:buyer@example.com"
KEY = "key-123"


class IdempotentContextManagerTests(unittest.TestCase):
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

    def _seed(self, *, payload: dict, status: str, response: dict) -> None:
        request_hash = hash_payload(canonicalize_payload(payload))
        record, created = acquire_record(
            scope=SCOPE, idempotency_key=KEY, request_hash=request_hash, db=self.db
        )
        assert created
        if status == "completed":
            mark_record_completed(record=record, response_payload=response, db=self.db)
        elif status == "failed":
            mark_record_failed(record=record, response_payload=response, db=self.db)
        self.db.commit()

    def _record(self) -> IdempotencyRecord | None:
        return get_record(scope=SCOPE, idempotency_key=KEY, db=self.db)

    def test_replay_short_circuits_before_executing(self) -> None:
        self._seed(payload={"a": 1}, status="completed", response={"order_id": 5})
        executed = False
        with idempotent(scope=SCOPE, key=KEY, payload={"a": 1}, db=self.db) as ctx:
            if ctx.replay is not None:
                self.assertEqual(ctx.replay, {"order_id": 5})
                self.assertIsNone(ctx.recover_from)
            else:
                executed = True
        self.assertFalse(executed)

    def test_recover_exposes_failed_payload(self) -> None:
        self._seed(
            payload={"a": 1},
            status="failed",
            response={"detail": "boom", "order_id": 5, "payment_id": 9},
        )
        with idempotent(scope=SCOPE, key=KEY, payload={"a": 1}, db=self.db) as ctx:
            self.assertIsNone(ctx.replay)
            self.assertEqual(ctx.recover_from["order_id"], 5)

    def test_fresh_execute_then_complete_marks_completed(self) -> None:
        with idempotent(scope=SCOPE, key=KEY, payload={"a": 1}, db=self.db) as ctx:
            self.assertIsNone(ctx.replay)
            self.assertIsNone(ctx.recover_from)
            ctx.complete({"order_id": 9})
        record = self._record()
        self.assertEqual(record.status, "completed")
        self.assertEqual(load_replay_payload(record), {"order_id": 9})

    def test_disabled_key_makes_complete_a_noop(self) -> None:
        with idempotent(scope=SCOPE, key=None, payload={"a": 1}, db=self.db) as ctx:
            self.assertIsNone(ctx.replay)
            self.assertIsNone(ctx.recover_from)
            ctx.complete({"x": 1})  # sin record: no debe romper
        self.assertEqual(self.db.query(IdempotencyRecord).count(), 0)

    def test_persist_safety_net_marks_failed_and_commits(self) -> None:
        with self.assertRaises(RuntimeError):
            with idempotent(
                scope=SCOPE, key=KEY, payload={"a": 1}, db=self.db,
                failure=FailurePolicy.PERSIST,
            ):
                raise RuntimeError("boom")
        record = self._record()
        self.assertEqual(record.status, "failed")
        self.assertEqual(load_replay_payload(record), {"detail": "boom"})

    def test_safety_net_does_not_overwrite_explicit_fail(self) -> None:
        with self.assertRaises(RuntimeError):
            with idempotent(
                scope=SCOPE, key=KEY, payload={"a": 1}, db=self.db,
                failure=FailurePolicy.PERSIST,
            ) as ctx:
                ctx.fail({"detail": "domain", "order_id": 7, "payment_id": 3})
                self.db.commit()
                raise RuntimeError("boom")
        record = self._record()
        self.assertEqual(record.status, "failed")
        payload = load_replay_payload(record)
        self.assertEqual(payload["order_id"], 7)  # payload de dominio, no el generico

    def test_discard_leaves_record_untouched_on_failure(self) -> None:
        with self.assertRaises(RuntimeError):
            with idempotent(
                scope=SCOPE, key=KEY, payload={"a": 1}, db=self.db,
                failure=FailurePolicy.DISCARD,
            ):
                raise RuntimeError("boom")
        # El CM no hace bookkeeping bajo DISCARD; la reversion del acquire es
        # responsabilidad de la dependencia transaccional (aca no hay ninguna).
        record = self._record()
        self.assertEqual(record.status, "processing")

    def test_reused_key_conflict_propagates_on_enter(self) -> None:
        self._seed(payload={"a": 1}, status="completed", response={"ok": True})
        with self.assertRaises(IdempotencyKeyReusedError):
            with idempotent(scope=SCOPE, key=KEY, payload={"a": 2}, db=self.db):
                self.fail("no deberia entrar al cuerpo con clave reusada")


if __name__ == "__main__":
    unittest.main()
