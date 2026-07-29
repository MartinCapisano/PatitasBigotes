"""Inicialización de Sentry: error tracking + tracing/APM + cron monitoring.

Diseño (ver docs/17_ProductionReadiness.md §4):
- **Se activa solo si hay `SENTRY_DSN`.** Sin DSN, `init_sentry()` es un no-op, así
  local y los tests nunca mandan eventos. Todas las APIs de Sentry (incluido el
  monitor del cron) son no-op cuando el SDK no se inicializó.
- **`send_default_pii=False`.** El sistema loguea emails en claro en varios puntos
  (§4.1); no queremos que además viajen a Sentry en el contexto del request.
- **Tracing con sample rate bajo** (`SENTRY_TRACES_SAMPLE_RATE`, default 0.2) para
  no reventar la cuota del free tier. FastAPI, SQLAlchemy y las llamadas HTTP
  salientes se auto-instrumentan (queries lentas, latencia p50/p95 por endpoint).
"""
from __future__ import annotations

import logging

from source.db.config import (
    get_app_env,
    get_sentry_dsn,
    get_sentry_release,
    get_sentry_traces_sample_rate,
)

logger = logging.getLogger(__name__)

# Slug del monitor del cron de mantenimiento (Sentry Crons). Es el dead-man's switch
# que el `if: failure()` del workflow no puede cubrir: si el cron deja de correr del
# todo, no llega el check-in y Sentry alerta. Ver docs/17 §4.5.
MAINTENANCE_MONITOR_SLUG = "maintenance-run"

# El cron pega cada ~13 min (.github/workflows/maintenance.yml). El margen y el
# runtime máximo dan aire al cold start de Render (30-60 s) sin marcar falsos fallos.
MAINTENANCE_MONITOR_CONFIG = {
    "schedule": {"type": "crontab", "value": "*/13 * * * *"},
    "checkin_margin": 5,      # minutos de tolerancia antes de marcar "missed"
    "max_runtime": 5,         # minutos; si supera esto, "timeout"
    "timezone": "UTC",
    "failure_issue_threshold": 1,
    "recovery_threshold": 1,
}


def init_sentry() -> bool:
    """Inicializa Sentry si hay DSN. Devuelve True si quedó activo."""
    dsn = get_sentry_dsn()
    if not dsn:
        return False

    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=get_app_env(),
        release=get_sentry_release(),
        # Tracing/APM. FastAPI + SQLAlchemy se instrumentan solos con el SDK.
        traces_sample_rate=get_sentry_traces_sample_rate(),
        # PII apagado a propósito (ver docstring del módulo).
        send_default_pii=False,
    )
    logger.info("event=sentry_initialized environment=%s", get_app_env())
    return True
