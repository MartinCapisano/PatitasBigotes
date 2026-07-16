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

from source.db.models import AuthActionToken, Base
from source.jobs import prune_auth_action_tokens_job
from source.services.auth_tokens_s import prune_auth_action_tokens
from tests.factories.users import create_user


class PruneAuthActionTokensServiceTests(unittest.TestCase):
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

    def _seed_token(
        self,
        db,
        *,
        expires_at: datetime,
        used_at: datetime | None,
        token_hash: str,
    ) -> None:
        user = create_user(db, email_prefix=token_hash)
        db.add(
            AuthActionToken(
                user_id=int(user.id),
                action="password_reset",
                token_hash=token_hash,
                expires_at=expires_at,
                used_at=used_at,
            )
        )
        db.flush()

    def test_prune_deletes_expired_and_stale_used_tokens_with_limit(self) -> None:
        db = self.TestSession()
        try:
            now = datetime.now(UTC)
            self._seed_token(
                db,
                expires_at=now - timedelta(days=1),
                used_at=None,
                token_hash="expired-unused",
            )
            self._seed_token(
                db,
                expires_at=now + timedelta(days=1),
                used_at=now - timedelta(days=30),
                token_hash="stale-used",
            )
            self._seed_token(
                db,
                expires_at=now + timedelta(days=1),
                used_at=now - timedelta(hours=1),
                token_hash="recently-used",
            )
            self._seed_token(
                db,
                expires_at=now + timedelta(days=1),
                used_at=None,
                token_hash="active-unused",
            )
            db.commit()

            deleted_first = prune_auth_action_tokens(
                now=now,
                older_than_days=7,
                limit=1,
                db=db,
            )
            db.commit()
            self.assertEqual(deleted_first, 1)

            deleted_second = prune_auth_action_tokens(
                now=now,
                older_than_days=7,
                limit=10,
                db=db,
            )
            db.commit()
            self.assertEqual(deleted_second, 1)

            remaining = {row.token_hash for row in db.query(AuthActionToken).all()}
            self.assertEqual(remaining, {"recently-used", "active-unused"})
        finally:
            db.close()

    def test_prune_returns_zero_when_nothing_matches(self) -> None:
        db = self.TestSession()
        try:
            now = datetime.now(UTC)
            self._seed_token(
                db,
                expires_at=now + timedelta(days=1),
                used_at=None,
                token_hash="fresh",
            )
            db.commit()

            deleted = prune_auth_action_tokens(now=now, older_than_days=7, limit=10, db=db)
            db.commit()

            self.assertEqual(deleted, 0)
        finally:
            db.close()


class PruneAuthActionTokensJobRunOnceTests(unittest.TestCase):
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
            prune_auth_action_tokens_job,
            "SessionLocal",
            self.TestSession,
        )
        self._session_local_patch.start()

    def tearDown(self) -> None:
        self._session_local_patch.stop()

    def test_run_once_deletes_expired_tokens_and_returns_count(self) -> None:
        db = self.TestSession()
        try:
            user = create_user(db, email_prefix="job-expired")
            db.add(
                AuthActionToken(
                    user_id=int(user.id),
                    action="email_verify",
                    token_hash="job-expired-token",
                    expires_at=datetime.now(UTC) - timedelta(days=1),
                    used_at=None,
                )
            )
            db.commit()
        finally:
            db.close()

        deleted = prune_auth_action_tokens_job.run_once(older_than_days=7, batch_size=500)

        self.assertEqual(deleted, 1)

    def test_run_once_returns_zero_when_nothing_to_prune(self) -> None:
        deleted = prune_auth_action_tokens_job.run_once(older_than_days=7, batch_size=500)

        self.assertEqual(deleted, 0)


if __name__ == "__main__":
    unittest.main()
