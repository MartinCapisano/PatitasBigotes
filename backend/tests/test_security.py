import sys
import unittest
import json
import base64
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.services import auth_security_s as security


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._env_backup = dict(os.environ)
        os.environ["JWT_SECRET"] = "test-secret-for-security-tests"
        os.environ["JWT_ALGORITHM"] = "HS256"
        os.environ["JWT_ISSUER"] = "patitasbigotes-api"
        os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "120"
        os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "30"

    @classmethod
    def tearDownClass(cls) -> None:
        os.environ.clear()
        os.environ.update(cls._env_backup)

    @staticmethod
    def _decode_payload_without_verification(token: str) -> dict:
        payload_segment = token.split(".")[1]
        padding = "=" * (-len(payload_segment) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_segment + padding)
        return json.loads(payload_bytes.decode("utf-8"))

    def test_verify_password_invalid_hash_returns_false(self) -> None:
        self.assertFalse(security.verify_password("plain", "not-a-valid-hash"))

    def test_create_access_token_zero_delta_uses_immediate_expiry(self) -> None:
        token = security.create_access_token(
            {"sub": "1"},
            expires_delta=timedelta(0),
        )
        claims = self._decode_payload_without_verification(token)
        exp_ts = claims["exp"]
        now_ts = datetime.now(timezone.utc).timestamp()

        self.assertLessEqual(abs(exp_ts - now_ts), 5)

    def test_decode_access_token_invalid_token_sets_cause(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            security.decode_access_token("invalid-token")

        self.assertEqual(str(ctx.exception), "Invalid token")
        self.assertIsNotNone(ctx.exception.__cause__)

    def test_create_access_token_default_expiration_is_120_minutes(self) -> None:
        now_ts = datetime.now(timezone.utc).timestamp()
        token = security.create_access_token({"sub": "1"})
        claims = self._decode_payload_without_verification(token)
        exp_ts = claims["exp"]

        self.assertGreaterEqual(exp_ts - now_ts, 119 * 60)
        self.assertLessEqual(exp_ts - now_ts, 121 * 60)

    def test_decode_access_token_rejects_refresh_token(self) -> None:
        refresh = security.create_refresh_token(usuario_id=1)
        with self.assertRaises(ValueError) as ctx:
            security.decode_access_token(refresh)
        self.assertEqual(str(ctx.exception), "Invalid token type")

    def test_missing_access_token_expire_minutes_raises(self) -> None:
        previous = os.environ.pop("ACCESS_TOKEN_EXPIRE_MINUTES", None)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                security.obtener_config_jwt()
            self.assertEqual(
                str(ctx.exception),
                "ACCESS_TOKEN_EXPIRE_MINUTES is required",
            )
        finally:
            if previous is not None:
                os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = previous

    def test_password_policy_requires_minimum_length(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            security.ensure_password_policy("Ab$12")
        self.assertEqual(
            str(ctx.exception),
            "password must be at least 8 characters long",
        )

    def test_password_policy_requires_special_character(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            security.ensure_password_policy("Abcdef12")
        self.assertEqual(
            str(ctx.exception),
            "password must include at least one special character",
        )

    def test_password_policy_accepts_valid_password(self) -> None:
        security.ensure_password_policy("Abcdef1!")


if __name__ == "__main__":
    unittest.main()
