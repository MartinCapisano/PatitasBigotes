import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base, Turn
from source.services.turns_s import (
    create_turn_for_user,
    list_turns_for_admin,
    update_turn_status_for_admin,
)
from tests.factories.users import create_user


class TurnsFlowTests(unittest.TestCase):
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

    def _seed_user(self) -> int:
        db = self.TestSession()
        try:
            user = create_user(
                db,
                first_name="Ana",
                last_name="Lopez",
                email_prefix="turns",
                phone="1122334455",
                has_account=True,
                email_verified_at=datetime.now(UTC),
            )
            db.commit()
            return int(user.id)
        finally:
            db.close()

    def test_create_turn_rejects_out_of_business_hours(self) -> None:
        user_id = self._seed_user()
        db = self.TestSession()
        try:
            with self.assertRaises(ValueError) as ctx:
                create_turn_for_user(
                    user_id=user_id,
                    scheduled_at=datetime.fromisoformat("2026-03-02T07:00:00-03:00"),
                    notes=None,
                    db=db,
                )
            self.assertEqual(str(ctx.exception), "turn hour must be between 13:00 and 20:00")
        finally:
            db.close()

    def test_admin_list_turns_includes_customer_contact(self) -> None:
        user_id = self._seed_user()
        db = self.TestSession()
        try:
            created = create_turn_for_user(
                user_id=user_id,
                scheduled_at=datetime.fromisoformat("2026-03-02T14:00:00-03:00"),
                notes="quiero corte",
                db=db,
            )
            db.commit()
            rows = list_turns_for_admin(db=db, status=None, limit=50)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(int(row["id"]), int(created["id"]))
            self.assertEqual(row["customer"]["first_name"], "Ana")
            self.assertEqual(row["customer"]["last_name"], "Lopez")
            self.assertEqual(row["customer"]["phone"], "1122334455")
            self.assertIsNotNone(row["scheduled_at"])
        finally:
            db.close()

    def test_admin_can_confirm_pending_turn(self) -> None:
        user_id = self._seed_user()
        db = self.TestSession()
        try:
            created = create_turn_for_user(
                user_id=user_id,
                scheduled_at=datetime.fromisoformat("2026-03-03T15:00:00-03:00"),
                notes=None,
                db=db,
            )
            db.commit()

            updated = update_turn_status_for_admin(
                turn_id=int(created["id"]),
                new_status="confirmed",
                db=db,
            )
            db.commit()

            persisted = db.query(Turn).filter(Turn.id == int(created["id"])).first()
            self.assertIsNotNone(persisted)
            assert persisted is not None
            self.assertEqual(persisted.status, "confirmed")
            self.assertEqual(updated["status"], "confirmed")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()

