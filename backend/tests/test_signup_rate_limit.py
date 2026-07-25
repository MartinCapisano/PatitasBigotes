import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import AuthLoginThrottle, Base
from source.exceptions import RateLimitExceededError
from source.services.anti_abuse_s import enforce_public_signup_limits


class SignupRateLimitTests(unittest.TestCase):
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

    def test_second_signup_attempt_too_soon_is_blocked(self) -> None:
        db = self.TestSession()
        try:
            enforce_public_signup_limits(
                client_ip="10.0.0.1",
                email="signup@example.com",
                db=db,
            )
            db.flush()

            with self.assertRaises(RateLimitExceededError) as ctx:
                enforce_public_signup_limits(
                    client_ip="10.0.0.1",
                    email="signup@example.com",
                    db=db,
                )
            self.assertEqual(str(ctx.exception), "please wait before retrying signup")
        finally:
            db.close()

    def test_signup_limit_blocks_by_ip(self) -> None:
        db = self.TestSession()
        try:
            now = datetime.now(timezone.utc)
            db.add(
                AuthLoginThrottle(
                    scope="public_signup_ip",
                    key="10.0.0.2",
                    failed_count=20,
                    window_started_at=now,
                    blocked_until=None,
                    updated_at=now,
                )
            )
            db.add(
                AuthLoginThrottle(
                    scope="public_signup_email_window",
                    key="overflow@example.com",
                    failed_count=0,
                    window_started_at=now - timedelta(minutes=15),
                    blocked_until=None,
                    updated_at=now - timedelta(minutes=15),
                )
            )
            db.add(
                AuthLoginThrottle(
                    scope="public_signup_email_interval",
                    key="overflow@example.com",
                    failed_count=0,
                    window_started_at=now - timedelta(minutes=15),
                    blocked_until=None,
                    updated_at=now - timedelta(minutes=15),
                )
            )
            db.commit()

            with self.assertRaises(RateLimitExceededError) as ctx:
                enforce_public_signup_limits(
                    client_ip="10.0.0.2",
                    email="overflow@example.com",
                    db=db,
                )
            self.assertEqual(str(ctx.exception), "too many signup attempts from this ip")
        finally:
            db.close()

    def test_signup_limit_blocks_by_email_window(self) -> None:
        db = self.TestSession()
        try:
            now = datetime.now(timezone.utc)
            db.add(
                AuthLoginThrottle(
                    scope="public_signup_ip",
                    key="10.0.0.3",
                    failed_count=0,
                    window_started_at=now,
                    blocked_until=None,
                    updated_at=now,
                )
            )
            db.add(
                AuthLoginThrottle(
                    scope="public_signup_email_window",
                    key="busy@example.com",
                    failed_count=6,
                    window_started_at=now,
                    blocked_until=None,
                    updated_at=now,
                )
            )
            db.add(
                AuthLoginThrottle(
                    scope="public_signup_email_interval",
                    key="busy@example.com",
                    failed_count=0,
                    window_started_at=now - timedelta(minutes=15),
                    blocked_until=None,
                    updated_at=now - timedelta(minutes=15),
                )
            )
            db.commit()

            with self.assertRaises(RateLimitExceededError) as ctx:
                enforce_public_signup_limits(
                    client_ip="10.0.0.3",
                    email="busy@example.com",
                    db=db,
                )
            self.assertEqual(str(ctx.exception), "too many signup attempts for this email")
        finally:
            db.close()

    def test_signup_limit_resets_after_window_expiration(self) -> None:
        db = self.TestSession()
        try:
            old = datetime.now(timezone.utc) - timedelta(minutes=30)
            db.add(
                AuthLoginThrottle(
                    scope="public_signup_ip",
                    key="10.0.0.4",
                    failed_count=20,
                    window_started_at=old,
                    blocked_until=None,
                    updated_at=old,
                )
            )
            db.add(
                AuthLoginThrottle(
                    scope="public_signup_email_window",
                    key="reset@example.com",
                    failed_count=6,
                    window_started_at=old,
                    blocked_until=None,
                    updated_at=old,
                )
            )
            db.add(
                AuthLoginThrottle(
                    scope="public_signup_email_interval",
                    key="reset@example.com",
                    failed_count=0,
                    window_started_at=old,
                    blocked_until=None,
                    updated_at=old,
                )
            )
            db.commit()

            enforce_public_signup_limits(
                client_ip="10.0.0.4",
                email="reset@example.com",
                db=db,
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
