"""Ruidoso al arrancar, silencioso en runtime.

Los envios de email se tragan sus excepciones a proposito (ver
`post_commit_actions_s`), asi que una credencial revocada o una variable borrada
en Render no producen ningun sintoma: la tienda anda y nadie recibe nada. El
boot es el unico momento en que ese problema se puede ver, y este test es el que
lo mantiene visible.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.config import SMTP_ENV_VARS, validate_smtp_config

COMPLETE_SMTP_CONFIG = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_USERNAME": "patitasbigotes@gmail.com",
    "SMTP_PASSWORD": "app-password",
    "MAIL_FROM": "patitasbigotes@gmail.com",
}


class SmtpConfigValidationTests(unittest.TestCase):
    def test_production_boot_fails_and_names_every_missing_variable(self) -> None:
        env = {**COMPLETE_SMTP_CONFIG, "APP_ENV": "production"}
        env["SMTP_PASSWORD"] = ""
        env["MAIL_FROM"] = ""

        with patch.dict(os.environ, env):
            with self.assertRaises(RuntimeError) as ctx:
                validate_smtp_config()

        message = str(ctx.exception)
        # Las dos juntas: un deploy mal configurado se arregla de una y no de a
        # un redeploy por variable.
        self.assertIn("SMTP_PASSWORD", message)
        self.assertIn("MAIL_FROM", message)
        self.assertNotIn("SMTP_HOST", message)

    def test_production_boot_passes_with_the_full_set(self) -> None:
        with patch.dict(os.environ, {**COMPLETE_SMTP_CONFIG, "APP_ENV": "production"}):
            validate_smtp_config()

    def test_an_unknown_app_env_falls_on_the_strict_side(self) -> None:
        """Un typo en APP_ENV no puede degradar el chequeo a un warning."""
        env = {**COMPLETE_SMTP_CONFIG, "APP_ENV": "prod-uction", "SMTP_HOST": ""}

        with patch.dict(os.environ, env):
            with self.assertRaises(RuntimeError):
                validate_smtp_config()

    def test_local_boots_without_smtp_and_warns(self) -> None:
        env = {name: "" for name in SMTP_ENV_VARS}
        env["APP_ENV"] = "local"

        with patch.dict(os.environ, env):
            with self.assertLogs("source.db.config", level="WARNING") as logs:
                validate_smtp_config()

        self.assertTrue(any("smtp_config_incomplete" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
