import os
import sys
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from source.services.auth_s import (
    issue_token_pair,
    logout_with_refresh_token,
    refresh_with_token,
)
from source.services.auth_security_s import create_access_token, decode_access_token
from source.db.models import Base, User, UserRefreshSession
from source.dependencies.auth_d import get_current_user
from tests.factories.users import create_user


class AuthTokenVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._env_backup = dict(os.environ)
        os.environ["JWT_SECRET"] = "test-secret-auth-token-version"
        os.environ["JWT_ALGORITHM"] = "HS256"
        os.environ["JWT_ISSUER"] = "patitasbigotes-api"
        os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "120"
        os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "30"

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
        os.environ.clear()
        os.environ.update(cls._env_backup)

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def _create_user(self, db) -> User:
        user = create_user(
            db,
            first_name="Auth",
            last_name="User",
            email="auth.user@example.com",
            token_version=1,
        )
        return user

    def _request_with_access_cookie(self, token: str) -> Request:
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/auth/me",
            "headers": [
                (b"cookie", f"pb_at={token}".encode("utf-8")),
            ],
            "client": ("127.0.0.1", 12345),
        }
        return Request(scope)

    def test_issue_token_pair_includes_tv_claim(self) -> None:
        db = self.TestSession()
        try:
            user = self._create_user(db)
            tokens = issue_token_pair(user=user, db=db)
            payload = decode_access_token(tokens["access_token"])
            self.assertEqual(payload.get("tv"), 1)
        finally:
            db.close()

    def test_get_current_user_rejects_legacy_token_without_tv(self) -> None:
        db = self.TestSession()
        try:
            user = self._create_user(db)
            legacy_access = create_access_token({"sub": str(user.id), "is_admin": False})
            with self.assertRaises(HTTPException) as ctx:
                get_current_user(request=self._request_with_access_cookie(legacy_access), db=db)
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertEqual(ctx.exception.detail, "Invalid or expired token")
        finally:
            db.close()

    def test_refresh_bumps_token_version_and_invalidates_old_access(self) -> None:
        db = self.TestSession()
        try:
            user = self._create_user(db)
            issued = issue_token_pair(user=user, db=db)
            db.commit()
            old_access = issued["access_token"]
            refreshed = refresh_with_token(refresh_token=issued["refresh_token"], db=db)

            db.refresh(user)
            self.assertEqual(int(user.token_version), 2)
            self.assertEqual(decode_access_token(refreshed["access_token"]).get("tv"), 2)

            with self.assertRaises(HTTPException) as old_ctx:
                get_current_user(request=self._request_with_access_cookie(old_access), db=db)
            self.assertEqual(old_ctx.exception.status_code, 401)

            payload = get_current_user(request=self._request_with_access_cookie(refreshed["access_token"]), db=db)
            self.assertEqual(payload.get("sub"), str(user.id))
        finally:
            db.close()

    def test_logout_bumps_token_version_and_clears_refresh_session(self) -> None:
        db = self.TestSession()
        try:
            user = self._create_user(db)
            tokens = issue_token_pair(user=user, db=db)
            db.commit()
            logout_with_refresh_token(refresh_token=tokens["refresh_token"], db=db)
            db.commit()

            db.refresh(user)
            self.assertEqual(int(user.token_version), 2)
            refresh_session = (
                db.query(UserRefreshSession)
                .filter(UserRefreshSession.user_id == user.id)
                .first()
            )
            self.assertIsNone(refresh_session)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
