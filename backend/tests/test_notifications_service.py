import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base
from source.services.notifications_s import (
    create_admin_notification,
    get_unread_notification_count,
    list_notifications_for_user,
    mark_all_notifications_read,
    mark_notification_read,
)
from tests.factories.users import create_user


class NotificationsServiceTests(unittest.TestCase):
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

    def test_create_admin_notification_deduplicates_by_key(self) -> None:
        db = self.TestSession()
        try:
            first = create_admin_notification(
                event_type="payment_incident",
                title="Incidencia de pago",
                message="Revisar pago #1",
                dedupe_key="incident-1",
                db=db,
            )
            db.commit()
            second = create_admin_notification(
                event_type="payment_incident",
                title="Incidencia de pago (dup)",
                message="Revisar pago #1 (dup)",
                dedupe_key="incident-1",
                db=db,
            )
            db.commit()

            self.assertEqual(first["id"], second["id"])
            self.assertEqual(second["title"], "Incidencia de pago")
        finally:
            db.close()

    def test_list_notifications_for_user_includes_own_and_admin_broadcasts(self) -> None:
        db = self.TestSession()
        try:
            user = create_user(db, email_prefix="notif-user")
            db.commit()

            create_admin_notification(
                event_type="order_paid",
                title="Tu orden fue pagada",
                message="Gracias por tu compra",
                db=db,
            )
            db.commit()

            rows, meta = list_notifications_for_user(
                user_id=int(user.id),
                is_admin=True,
                unread_only=False,
                limit=20,
                offset=0,
                db=db,
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(meta["total"], 1)
            self.assertFalse(meta["has_more"])

            non_admin_rows, non_admin_meta = list_notifications_for_user(
                user_id=int(user.id),
                is_admin=False,
                unread_only=False,
                limit=20,
                offset=0,
                db=db,
            )
            self.assertEqual(len(non_admin_rows), 0)
            self.assertEqual(non_admin_meta["total"], 0)
        finally:
            db.close()

    def test_list_notifications_unread_only_filters_read_rows(self) -> None:
        db = self.TestSession()
        try:
            notification = create_admin_notification(
                event_type="order_paid",
                title="Orden pagada",
                message="msg",
                db=db,
            )
            db.commit()
            user = create_user(db, email_prefix="notif-unread")
            db.commit()

            mark_notification_read(
                notification_id=int(notification["id"]),
                user_id=int(user.id),
                is_admin=True,
                db=db,
            )
            db.commit()

            rows, meta = list_notifications_for_user(
                user_id=int(user.id),
                is_admin=True,
                unread_only=True,
                limit=20,
                offset=0,
                db=db,
            )
            self.assertEqual(rows, [])
            self.assertEqual(meta["total"], 0)
        finally:
            db.close()

    def test_get_unread_notification_count(self) -> None:
        db = self.TestSession()
        try:
            create_admin_notification(event_type="a", title="A", message="a", db=db)
            create_admin_notification(event_type="b", title="B", message="b", db=db)
            db.commit()
            user = create_user(db, email_prefix="notif-count")
            db.commit()

            count = get_unread_notification_count(user_id=int(user.id), is_admin=True, db=db)
            self.assertEqual(count, 2)
        finally:
            db.close()

    def test_mark_notification_read_is_idempotent(self) -> None:
        db = self.TestSession()
        try:
            notification = create_admin_notification(event_type="a", title="A", message="a", db=db)
            db.commit()
            user = create_user(db, email_prefix="notif-mark")
            db.commit()

            first = mark_notification_read(
                notification_id=int(notification["id"]),
                user_id=int(user.id),
                is_admin=True,
                db=db,
            )
            db.commit()
            self.assertTrue(first["is_read"])
            first_read_at = first["read_at"]

            second = mark_notification_read(
                notification_id=int(notification["id"]),
                user_id=int(user.id),
                is_admin=True,
                db=db,
            )
            db.commit()
            self.assertEqual(second["read_at"].replace(tzinfo=None), first_read_at.replace(tzinfo=None))
        finally:
            db.close()

    def test_mark_notification_read_rejects_other_users_notification(self) -> None:
        db = self.TestSession()
        try:
            owner = create_user(db, email_prefix="notif-owner")
            intruder = create_user(db, email_prefix="notif-intruder")
            db.commit()
            from source.db.models import Notification

            personal = Notification(
                user_id=int(owner.id),
                role_target=None,
                event_type="custom",
                title="Personal",
                message="msg",
                is_read=False,
            )
            db.add(personal)
            db.commit()

            with self.assertRaises(LookupError):
                mark_notification_read(
                    notification_id=int(personal.id),
                    user_id=int(intruder.id),
                    is_admin=False,
                    db=db,
                )
        finally:
            db.close()

    def test_mark_all_notifications_read_updates_only_unread(self) -> None:
        db = self.TestSession()
        try:
            create_admin_notification(event_type="a", title="A", message="a", db=db)
            create_admin_notification(event_type="b", title="B", message="b", db=db)
            db.commit()
            user = create_user(db, email_prefix="notif-readall")
            db.commit()

            result = mark_all_notifications_read(user_id=int(user.id), is_admin=True, db=db)
            db.commit()
            self.assertEqual(result["updated"], 2)

            unread = get_unread_notification_count(user_id=int(user.id), is_admin=True, db=db)
            self.assertEqual(unread, 0)

            second_result = mark_all_notifications_read(user_id=int(user.id), is_admin=True, db=db)
            db.commit()
            self.assertEqual(second_result["updated"], 0)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
