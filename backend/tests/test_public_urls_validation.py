"""Las dos variables que, mal puestas, no fallaban en ningun lado.

`APP_BASE_URL` y `CORS_ALLOW_ORIGINS` tienen default a `localhost`, y eso las
volvia el peor caso de la configuracion de produccion: sin ellas no hay
`RuntimeError`, no hay log y no hay sintoma del lado del servidor. El unico que
se entera es el cliente, cuando abre el link de verificacion que le llego por
mail y apunta a localhost.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.config import validate_public_urls_config

REAL_URLS = {
    "APP_BASE_URL": "https://patitasbigotes.vercel.app",
    "CORS_ALLOW_ORIGINS": "https://patitasbigotes.vercel.app",
}


class PublicUrlsValidationTests(unittest.TestCase):
    def test_production_boot_passes_with_real_urls(self) -> None:
        with patch.dict(os.environ, {**REAL_URLS, "APP_ENV": "production"}):
            validate_public_urls_config()

    def test_a_localhost_app_base_url_stops_the_boot(self) -> None:
        # Este es el que manda links rotos al inbox del cliente.
        env = {**REAL_URLS, "APP_ENV": "production", "APP_BASE_URL": "http://localhost:5173"}

        with patch.dict(os.environ, env):
            with self.assertRaises(RuntimeError) as ctx:
                validate_public_urls_config()

        self.assertIn("APP_BASE_URL", str(ctx.exception))
        self.assertNotIn("CORS_ALLOW_ORIGINS", str(ctx.exception))

    def test_a_localhost_origin_anywhere_in_the_cors_list_stops_the_boot(self) -> None:
        env = {
            **REAL_URLS,
            "APP_ENV": "production",
            "CORS_ALLOW_ORIGINS": "https://patitasbigotes.vercel.app,http://127.0.0.1:5173",
        }

        with patch.dict(os.environ, env):
            with self.assertRaises(RuntimeError) as ctx:
                validate_public_urls_config()

        self.assertIn("CORS_ALLOW_ORIGINS", str(ctx.exception))

    def test_an_absent_variable_is_caught_like_a_localhost_one(self) -> None:
        """Ausente y mal cargada son el mismo bug: el valor efectivo es localhost."""
        env = {**REAL_URLS, "APP_ENV": "production", "APP_BASE_URL": ""}

        with patch.dict(os.environ, env):
            with self.assertRaises(RuntimeError) as ctx:
                validate_public_urls_config()

        self.assertIn("APP_BASE_URL", str(ctx.exception))

    def test_it_names_both_when_both_are_wrong(self) -> None:
        env = {
            "APP_ENV": "production",
            "APP_BASE_URL": "http://localhost:5173",
            "CORS_ALLOW_ORIGINS": "http://localhost:5173",
        }

        with patch.dict(os.environ, env):
            with self.assertRaises(RuntimeError) as ctx:
                validate_public_urls_config()

        message = str(ctx.exception)
        self.assertIn("APP_BASE_URL", message)
        self.assertIn("CORS_ALLOW_ORIGINS", message)

    def test_a_url_without_a_scheme_is_still_recognised(self) -> None:
        env = {**REAL_URLS, "APP_ENV": "production", "APP_BASE_URL": "localhost:5173"}

        with patch.dict(os.environ, env):
            with self.assertRaises(RuntimeError):
                validate_public_urls_config()

    def test_a_real_domain_is_not_confused_with_localhost(self) -> None:
        # El chequeo mira el hostname, no si la cadena contiene "localhost".
        env = {
            "APP_ENV": "production",
            "APP_BASE_URL": "https://localhost-tools.com",
            "CORS_ALLOW_ORIGINS": "https://localhost-tools.com",
        }

        with patch.dict(os.environ, env):
            validate_public_urls_config()

    def test_local_boots_with_the_localhost_defaults(self) -> None:
        # Es el caso normal en desarrollo: no puede ser un error.
        env = {"APP_ENV": "local", "APP_BASE_URL": "", "CORS_ALLOW_ORIGINS": ""}

        with patch.dict(os.environ, env):
            validate_public_urls_config()

    def test_an_unknown_app_env_falls_on_the_strict_side(self) -> None:
        env = {**REAL_URLS, "APP_ENV": "produccion", "APP_BASE_URL": "http://localhost:5173"}

        with patch.dict(os.environ, env):
            with self.assertRaises(RuntimeError):
                validate_public_urls_config()


if __name__ == "__main__":
    unittest.main()
