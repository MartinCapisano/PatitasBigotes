import os
import sys
import unittest
from datetime import datetime, timedelta, UTC
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DB_PATH = BACKEND_DIR / "tmp" / "test_guest_checkout_idempotency.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")

from source.db.models import Base, IdempotencyRecord
from source.db.session import SessionLocal, engine
from source.services.idempotency_s import prune_expired_records


class GuestCheckoutIdempotencyTests(unittest.TestCase):
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

    def test_idempotency_record_expiration_pruning(self) -> None:
        db = SessionLocal()
        try:
            db.add(
                IdempotencyRecord(
                    scope="checkout_guest:expired@example.com",
                    idempotency_key="expired-key",
                    request_hash="h",
                    response_payload='{"ok":true}',
                    status="completed",
                    created_at=datetime.now(UTC) - timedelta(days=2),
                    expires_at=datetime.now(UTC) - timedelta(days=1),
                )
            )
            db.add(
                IdempotencyRecord(
                    scope="checkout_guest:active@example.com",
                    idempotency_key="active-key",
                    request_hash="h2",
                    response_payload='{"ok":true}',
                    status="completed",
                    created_at=datetime.now(UTC),
                    expires_at=datetime.now(UTC) + timedelta(hours=6),
                )
            )
            db.commit()

            deleted = prune_expired_records(now=datetime.now(UTC), db=db, limit=200)
            self.assertEqual(deleted, 1)

            remaining = (
                db.query(IdempotencyRecord)
                .order_by(IdempotencyRecord.id.asc())
                .all()
            )
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0].idempotency_key, "active-key")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()

