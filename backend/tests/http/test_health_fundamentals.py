"""Health checks: liveness (`/health`) y readiness (`/health/ready`).

Cubre el P0 de docs/17_ProductionReadiness.md §8 ("base de datos caída"): el
readiness debe **distinguir** el proceso vivo de la base inalcanzable, así el
`healthCheckPath` de Render puede sacar de rotación una instancia que no puede
atender. La liveness, en cambio, nunca debe tocar la base: un pico de Supabase no
tiene que marcar el proceso como muerto.
"""
from sqlalchemy.exc import OperationalError

from main import app
from source.db.session import get_db
from tests.http._base import HttpFundamentalsBase


class HealthFundamentalsTest(HttpFundamentalsBase):
    def test_liveness_returns_ok_without_touching_the_database_over_http(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readiness_returns_ok_when_database_is_reachable_over_http(self) -> None:
        response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "db": "ok"})

    def test_readiness_returns_503_when_database_is_unreachable_over_http(self) -> None:
        # Simula la base caída: la sesión inyectada falla al ejecutar el SELECT 1.
        class _BrokenSession:
            def execute(self, *args, **kwargs):
                raise OperationalError("SELECT 1", {}, Exception("connection refused"))

            def close(self) -> None:
                pass

        def _broken_db_override():
            yield _BrokenSession()

        original_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = _broken_db_override
        try:
            response = self.client.get("/health/ready")
        finally:
            # Restaurar el override sano de la base para no filtrar el fallo a otros tests.
            if original_override is not None:
                app.dependency_overrides[get_db] = original_override
            else:
                app.dependency_overrides.pop(get_db, None)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable", "db": "unreachable"})
