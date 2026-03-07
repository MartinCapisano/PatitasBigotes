import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base, Notification, User
from source.routes.notifications_r import (
    list_notifications,
    read_all_notifications,
    unread_notification_count,
)
from source.services.domain_events_s import publish_domain_event
from source.services.post_commit_actions_s import (
    POST_COMMIT_ACTIONS_KEY,
    clear_post_commit_actions,
    dispatch_post_commit_actions,
)


class DomainEventsNotificationsTests(unittest.TestCase):
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

    def _seed_user(self, *, is_admin: bool = False, email: str | None = None) -> User:
        db = self.TestSession()
        try:
            user = User(
                first_name="Jane",
                last_name="Doe",
                email=email or f"user-{datetime.now(UTC).timestamp()}@example.com",
                password_hash="!",
                has_account=True,
                is_admin=is_admin,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.expunge(user)
            return user
        finally:
            db.close()

    def test_publish_order_submitted_creates_admin_notification(self) -> None:
        db = self.TestSession()
        try:
            publish_domain_event(
                event_type="order_submitted",
                payload={"order_id": 10, "user_id": 5},
                db=db,
            )
            rows = db.query(Notification).all()
        finally:
            db.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].role_target, "admin")
        self.assertEqual(rows[0].event_type, "order_submitted")

    def test_publish_order_paid_creates_admin_notification_and_enqueues_post_commit_email(self) -> None:
        user = self._seed_user()
        db = self.TestSession()
        try:
            publish_domain_event(
                event_type="order_paid",
                payload={
                    "order_id": 11,
                    "user_id": int(user.id),
                    "payment_id": 22,
                    "payment_method": "mercadopago",
                    "order_status": "paid",
                    "total_amount": 10000,
                    "currency": "ARS",
                    "items": [
                        {
                            "product_name": "Balanceado",
                            "variant_label": "M/Negro",
                            "quantity": 2,
                            "line_total": 10000,
                        }
                    ],
                },
                db=db,
            )
            rows = db.query(Notification).order_by(Notification.id.asc()).all()
            actions = list(db.info.get(POST_COMMIT_ACTIONS_KEY, []))
        finally:
            db.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].role_target, "admin")
        self.assertEqual(rows[0].event_type, "order_paid")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["kind"], "order_paid_email")
        self.assertEqual(actions[0]["payload"]["to_email"], user.email)
        self.assertEqual(actions[0]["payload"]["order_status"], "paid")
        self.assertEqual(actions[0]["payload"]["total_amount"], 10000)

    def test_dispatch_post_commit_actions_sends_email_and_clears_queue(self) -> None:
        db = self.TestSession()
        try:
            db.info[POST_COMMIT_ACTIONS_KEY] = [
                {
                    "kind": "order_paid_email",
                    "payload": {
                        "to_email": "buyer@example.com",
                        "order_id": 11,
                        "order_status": "paid",
                        "payment_id": 22,
                        "total_amount": 10000,
                        "currency": "ARS",
                        "items": [
                            {
                                "product_name": "Balanceado",
                                "variant_label": "M/Negro",
                                "quantity": 2,
                                "line_total": 10000,
                            }
                        ],
                    },
                }
            ]
            with patch("source.services.post_commit_actions_s.send_order_paid_email") as mocked_send:
                dispatch_post_commit_actions(db=db, source="unit_test")
        finally:
            db.close()

        mocked_send.assert_called_once()

    def test_dispatch_post_commit_actions_logs_and_does_not_raise_when_email_fails(self) -> None:
        db = self.TestSession()
        try:
            db.info[POST_COMMIT_ACTIONS_KEY] = [
                {
                    "kind": "order_paid_email",
                    "payload": {
                        "to_email": "buyer@example.com",
                        "order_id": 11,
                        "order_status": "paid",
                        "payment_id": 22,
                        "total_amount": 10000,
                        "currency": "ARS",
                        "items": [],
                    },
                }
            ]
            with patch(
                "source.services.post_commit_actions_s.send_order_paid_email",
                side_effect=RuntimeError("smtp down"),
            ):
                dispatch_post_commit_actions(db=db, source="unit_test")
                actions = list(db.info.get(POST_COMMIT_ACTIONS_KEY, []))
        finally:
            db.close()

        self.assertEqual(actions, [])

    def test_clear_post_commit_actions_resets_queue(self) -> None:
        db = self.TestSession()
        try:
            db.info[POST_COMMIT_ACTIONS_KEY] = [{"kind": "order_paid_email", "payload": {}}]
            clear_post_commit_actions(db=db)
            actions = list(db.info.get(POST_COMMIT_ACTIONS_KEY, []))
        finally:
            db.close()

        self.assertEqual(actions, [])

    def test_publish_possible_refund_detected_creates_admin_notification(self) -> None:
        db = self.TestSession()
        try:
            publish_domain_event(
                event_type="possible_refund_detected",
                payload={"order_id": 7, "payment_id": 8, "incident_id": 9},
                db=db,
            )
            rows = db.query(Notification).all()
        finally:
            db.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].event_type, "possible_refund")
        self.assertEqual(rows[0].incident_id, 9)

    def test_unread_count_route_returns_user_and_admin_notifications(self) -> None:
        user = self._seed_user(is_admin=True)
        db = self.TestSession()
        try:
            publish_domain_event(
                event_type="order_submitted",
                payload={"order_id": 1, "user_id": int(user.id)},
                db=db,
            )
            db.add(
                Notification(
                    user_id=int(user.id),
                    role_target=None,
                    event_type="custom",
                    title="Hola",
                    message="Tu alerta",
                    is_read=False,
                )
            )
            db.commit()

            payload = unread_notification_count(
                current_user={"sub": str(user.id), "is_admin": True},
                db=db,
            )
        finally:
            db.close()

        self.assertEqual(payload["data"]["unread_count"], 2)

    def test_list_notifications_keeps_full_list_shape(self) -> None:
        user = self._seed_user()
        db = self.TestSession()
        try:
            db.add(
                Notification(
                    user_id=int(user.id),
                    role_target=None,
                    event_type="custom",
                    title="Titulo",
                    message="Mensaje",
                    is_read=False,
                )
            )
            db.commit()

            payload = list_notifications(
                unread_only=False,
                limit=20,
                offset=0,
                current_user={"sub": str(user.id), "is_admin": False},
                db=db,
            )
        finally:
            db.close()

        self.assertEqual(len(payload["data"]), 1)
        self.assertIn("total", payload["meta"])
        self.assertIn("has_more", payload["meta"])
        self.assertNotIn("unread_count", payload["meta"])

    def test_read_all_notifications_marks_everything_visible_as_read(self) -> None:
        user = self._seed_user(is_admin=True)
        db = self.TestSession()
        try:
            db.add_all(
                [
                    Notification(
                        user_id=int(user.id),
                        role_target=None,
                        event_type="custom",
                        title="Uno",
                        message="M1",
                        is_read=False,
                    ),
                    Notification(
                        user_id=None,
                        role_target="admin",
                        event_type="admin",
                        title="Dos",
                        message="M2",
                        is_read=False,
                    ),
                ]
            )
            db.commit()

            payload = read_all_notifications(
                current_user={"sub": str(user.id), "is_admin": True},
                db=db,
            )
            unread = (
                db.query(Notification)
                .filter(Notification.is_read.is_(False))
                .count()
            )
        finally:
            db.close()

        self.assertEqual(payload["data"]["updated"], 2)
        self.assertEqual(unread, 0)


if __name__ == "__main__":
    unittest.main()
