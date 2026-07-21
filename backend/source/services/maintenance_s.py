"""On-demand maintenance runner for the production (external-ping) model.

In local dev the maintenance jobs run as long-lived loops (Windows Task
Scheduler). In production the backend runs on a free tier that sleeps, so
there is no reliable in-process scheduler. Instead an external cron (GitHub
Actions) pings POST /internal/maintenance/run every few minutes; that ping
drives this runner, which executes one pass of each job.

Design notes:
- The ping cadence IS the interval. Each underlying job already guards its own
  work (min-age windows for reconcile, older-than for prunes, exponential
  backoff for webhook reprocess), so running them on every ping is safe and
  idempotent; there is no separate per-job "last run" bookkeeping to maintain.
- Orchestration lives here so the job modules stay untouched: each job exposes
  a `run_once(...)` that opens and closes its own DB session and returns a
  metrics dict/int. We resolve each job's env-based defaults through its own
  existing resolver helpers (single source of truth for the parameters).
- A per-process lock prevents two overlapping pings from running the jobs
  concurrently (Render free tier is a single instance).
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Callable

from source.jobs import expire_stock_reservations_job as _expire
from source.jobs import idempotency_sweeper_job as _sweeper
from source.jobs import prune_auth_action_tokens_job as _prune_tokens
from source.jobs import prune_auth_login_throttles_job as _prune_throttles
from source.jobs import reconcile_pending_payments_job as _reconcile
from source.jobs import reprocess_failed_webhooks_job as _reprocess

logger = logging.getLogger(__name__)

_run_lock = threading.Lock()


@dataclass(frozen=True)
class MaintenanceJob:
    name: str
    run: Callable[[], object]


def _run_expire_stock_reservations() -> dict[str, int]:
    processed = _expire.run_once(
        batch_limit=_expire._batch_limit(),
        max_batches=_expire._max_batches(),
    )
    return {"processed": int(processed)}


def _run_idempotency_sweeper() -> dict[str, int]:
    return _sweeper.run_once(
        processing_timeout_minutes=int(
            os.getenv(
                "IDEMPOTENCY_PROCESSING_TIMEOUT_MINUTES",
                _sweeper.DEFAULT_PROCESSING_TIMEOUT_MINUTES,
            )
        ),
        limit=int(os.getenv("IDEMPOTENCY_SWEEPER_LIMIT", _sweeper.DEFAULT_LIMIT)),
    )


def _run_reconcile_pending_payments() -> dict[str, int]:
    return _reconcile.run_once(
        batch_size=_reconcile._batch_size(),
        max_age_hours=_reconcile._max_age_hours(),
        min_age_minutes=_reconcile._min_age_minutes(),
    )


def _run_reprocess_failed_webhooks() -> dict[str, int]:
    return _reprocess.run_once(
        batch_size=_reprocess._batch_size(),
        max_attempts=_reprocess._max_attempts(),
        base_delay_minutes=_reprocess._base_delay_minutes(),
        max_delay_minutes=_reprocess._max_delay_minutes(),
    )


def _run_prune_auth_action_tokens() -> dict[str, int]:
    deleted = _prune_tokens.run_once(
        older_than_days=_prune_tokens._older_than_days(),
        batch_size=_prune_tokens._batch_size(),
    )
    return {"deleted": int(deleted)}


def _run_prune_auth_login_throttles() -> dict[str, int]:
    deleted = _prune_throttles.run_once(
        older_than_days=_prune_throttles._older_than_days(),
        batch_size=_prune_throttles._batch_size(),
    )
    return {"deleted": int(deleted)}


# Ordered so the payment-critical jobs (reconcile pending payments, reprocess
# failed webhooks) run first, since those most affect user-visible outcomes.
JOBS: list[MaintenanceJob] = [
    MaintenanceJob("reconcile_pending_payments", _run_reconcile_pending_payments),
    MaintenanceJob("reprocess_failed_webhooks", _run_reprocess_failed_webhooks),
    MaintenanceJob("expire_stock_reservations", _run_expire_stock_reservations),
    MaintenanceJob("idempotency_sweeper", _run_idempotency_sweeper),
    MaintenanceJob("prune_auth_action_tokens", _run_prune_auth_action_tokens),
    MaintenanceJob("prune_auth_login_throttles", _run_prune_auth_login_throttles),
]


def run_all_maintenance() -> dict:
    """Run one pass of every maintenance job.

    Returns a per-job result map. A failure in one job is isolated and does not
    stop the others. If another run is already in progress, returns busy without
    running anything.
    """
    if not _run_lock.acquire(blocking=False):
        logger.info("event=maintenance_run_skipped reason=busy")
        return {"status": "busy", "jobs": {}}

    jobs_result: dict[str, dict] = {}
    try:
        for job in JOBS:
            try:
                result = job.run()
                jobs_result[job.name] = {"ok": True, "result": result}
            except Exception as exc:  # isolate one job's failure from the rest
                logger.exception("event=maintenance_job_failed name=%s", job.name)
                jobs_result[job.name] = {"ok": False, "error": str(exc)}
    finally:
        _run_lock.release()

    all_ok = all(entry["ok"] for entry in jobs_result.values())
    status = "ok" if all_ok else "partial"
    logger.info("event=maintenance_run_completed status=%s", status)
    return {"status": status, "jobs": jobs_result}
