from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import logging
import os
import time

from sqlalchemy.exc import ProgrammingError

from source.db.session import SessionLocal
from source.services.mercadopago_client import (
    WebhookNoOpError,
    _is_retryable_noop_error,
    process_mercadopago_event_payload,
)
from source.services.post_commit_actions_s import clear_post_commit_actions, dispatch_post_commit_actions
from source.services.webhook_events_s import (
    acquire_webhook_event,
    get_webhook_reprocess_metrics,
    list_retryable_failed_webhook_events,
    mark_webhook_event_failed,
    mark_webhook_event_processed,
)

DEFAULT_INTERVAL_MINUTES = 30
DEFAULT_BATCH_SIZE = 25
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BASE_DELAY_MINUTES = 30
DEFAULT_MAX_DELAY_MINUTES = 720
PROVIDER = "mercadopago"

logger = logging.getLogger("webhook_reprocess_job")


def _interval_minutes() -> int:
    raw = str(os.getenv("WEBHOOK_REPROCESS_INTERVAL_MINUTES", DEFAULT_INTERVAL_MINUTES)).strip()
    interval = int(raw)
    if interval <= 0:
        raise RuntimeError("WEBHOOK_REPROCESS_INTERVAL_MINUTES must be greater than 0")
    return interval


def _batch_size() -> int:
    raw = str(os.getenv("WEBHOOK_REPROCESS_BATCH_SIZE", DEFAULT_BATCH_SIZE)).strip()
    size = int(raw)
    if size <= 0:
        raise RuntimeError("WEBHOOK_REPROCESS_BATCH_SIZE must be greater than 0")
    return size


def _max_attempts() -> int:
    raw = str(os.getenv("WEBHOOK_REPROCESS_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)).strip()
    max_attempts = int(raw)
    if max_attempts <= 0:
        raise RuntimeError("WEBHOOK_REPROCESS_MAX_ATTEMPTS must be greater than 0")
    return max_attempts


def _base_delay_minutes() -> int:
    raw = str(os.getenv("WEBHOOK_REPROCESS_BASE_DELAY_MINUTES", DEFAULT_BASE_DELAY_MINUTES)).strip()
    delay = int(raw)
    if delay <= 0:
        raise RuntimeError("WEBHOOK_REPROCESS_BASE_DELAY_MINUTES must be greater than 0")
    return delay


def _max_delay_minutes() -> int:
    raw = str(os.getenv("WEBHOOK_REPROCESS_MAX_DELAY_MINUTES", DEFAULT_MAX_DELAY_MINUTES)).strip()
    delay = int(raw)
    if delay <= 0:
        raise RuntimeError("WEBHOOK_REPROCESS_MAX_DELAY_MINUTES must be greater than 0")
    return delay


def _retry_delay_minutes_for_attempt(
    *,
    attempt_number: int,
    base_delay_minutes: int,
    max_delay_minutes: int,
) -> int:
    if attempt_number <= 0:
        return int(base_delay_minutes)
    exponent = max(0, int(attempt_number) - 1)
    computed = int(base_delay_minutes) * (2**exponent)
    return min(int(max_delay_minutes), computed)


def _parse_payload(raw_payload: str | None) -> dict | None:
    if not raw_payload:
        return None
    try:
        parsed = json.loads(raw_payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _extract_data_id(payload: dict) -> str | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    raw = data.get("id")
    if raw is None:
        return None
    normalized = str(raw).strip()
    if not normalized:
        return None
    return normalized


def run_once(
    *,
    batch_size: int,
    max_attempts: int,
    base_delay_minutes: int,
    max_delay_minutes: int,
) -> dict[str, int]:
    db = SessionLocal()
    now = datetime.now(UTC)
    try:
        metrics_before = get_webhook_reprocess_metrics(provider=PROVIDER, now=now, db=db)
    except ProgrammingError as exc:
        db.rollback()
        raise RuntimeError(
            "webhook_events schema is outdated; apply dead-letter migration first"
        ) from exc
    metrics = {
        "selected": 0,
        "reprocessed": 0,
        "reprocessed_noop": 0,
        "still_failed": 0,
        "dead_lettered": 0,
        "skipped": 0,
        "failed_due_before": int(metrics_before["failed_due"]),
        "failed_not_due_before": int(metrics_before["failed_not_due"]),
        "dead_letter_before": int(metrics_before["dead_letter"]),
        "oldest_failed_age_seconds_before": int(metrics_before["oldest_failed_age_seconds"]),
    }
    try:
        failed_events = list_retryable_failed_webhook_events(
            provider=PROVIDER,
            limit=int(batch_size),
            now=now,
            db=db,
        )
        metrics["selected"] = len(failed_events)

        for event in failed_events:
            event_key = str(event.event_key)
            attempt_number = int(event.attempt_count or 0) + 1
            retry_delay_minutes = _retry_delay_minutes_for_attempt(
                attempt_number=attempt_number,
                base_delay_minutes=base_delay_minutes,
                max_delay_minutes=max_delay_minutes,
            )
            will_dead_letter = attempt_number >= int(max_attempts)
            payload = _parse_payload(event.payload)
            if payload is None:
                mark_webhook_event_failed(
                    provider=PROVIDER,
                    event_key=event_key,
                    error_message="invalid stored webhook payload",
                    retry_delay_minutes=retry_delay_minutes,
                    max_attempts=max_attempts,
                    db=db,
                )
                db.commit()
                if will_dead_letter:
                    metrics["dead_lettered"] += 1
                else:
                    metrics["still_failed"] += 1
                continue

            data_id = _extract_data_id(payload)
            if data_id is None:
                mark_webhook_event_failed(
                    provider=PROVIDER,
                    event_key=event_key,
                    error_message="missing data.id in stored webhook payload",
                    retry_delay_minutes=retry_delay_minutes,
                    max_attempts=max_attempts,
                    db=db,
                )
                db.commit()
                if will_dead_letter:
                    metrics["dead_lettered"] += 1
                else:
                    metrics["still_failed"] += 1
                continue

            acquired = acquire_webhook_event(
                provider=PROVIDER,
                event_key=event_key,
                payload=payload,
                db=db,
            )
            if not acquired:
                metrics["skipped"] += 1
                db.rollback()
                clear_post_commit_actions(db=db)
                continue

            try:
                process_mercadopago_event_payload(
                    payload=payload,
                    data_id=data_id,
                    db=db,
                )
            except WebhookNoOpError as exc:
                if _is_retryable_noop_error(exc):
                    mark_webhook_event_failed(
                        provider=PROVIDER,
                        event_key=event_key,
                        error_message=str(exc),
                        retry_delay_minutes=retry_delay_minutes,
                        max_attempts=max_attempts,
                        db=db,
                    )
                    db.commit()
                    if will_dead_letter:
                        metrics["dead_lettered"] += 1
                    else:
                        metrics["still_failed"] += 1
                else:
                    mark_webhook_event_processed(
                        provider=PROVIDER,
                        event_key=event_key,
                        db=db,
                    )
                    db.commit()
                    metrics["reprocessed_noop"] += 1
                    logger.info(
                        "event=webhook_reprocess_noop provider=%s event_key=%s reason=%s",
                        PROVIDER,
                        event_key,
                        str(exc),
                    )
            except Exception as exc:
                mark_webhook_event_failed(
                    provider=PROVIDER,
                    event_key=event_key,
                    error_message=str(exc),
                    retry_delay_minutes=retry_delay_minutes,
                    max_attempts=max_attempts,
                    db=db,
                )
                db.commit()
                if will_dead_letter:
                    metrics["dead_lettered"] += 1
                else:
                    metrics["still_failed"] += 1
            else:
                mark_webhook_event_processed(
                    provider=PROVIDER,
                    event_key=event_key,
                    db=db,
                )
                db.commit()
                dispatch_post_commit_actions(db=db, source="reprocess_failed_webhooks_job")
                metrics["reprocessed"] += 1

        after_now = datetime.now(UTC)
        metrics_after = get_webhook_reprocess_metrics(provider=PROVIDER, now=after_now, db=db)
        metrics["failed_due_after"] = int(metrics_after["failed_due"])
        metrics["failed_not_due_after"] = int(metrics_after["failed_not_due"])
        metrics["dead_letter_after"] = int(metrics_after["dead_letter"])
        metrics["oldest_failed_age_seconds_after"] = int(metrics_after["oldest_failed_age_seconds"])

        logger.info(
            (
                "event=webhook_reprocess_run provider=%s selected=%s reprocessed=%s "
                "reprocessed_noop=%s still_failed=%s dead_lettered=%s skipped=%s "
                "failed_due_before=%s failed_not_due_before=%s dead_letter_before=%s "
                "oldest_failed_age_seconds_before=%s failed_due_after=%s "
                "failed_not_due_after=%s dead_letter_after=%s "
                "oldest_failed_age_seconds_after=%s"
            ),
            PROVIDER,
            metrics["selected"],
            metrics["reprocessed"],
            metrics["reprocessed_noop"],
            metrics["still_failed"],
            metrics["dead_lettered"],
            metrics["skipped"],
            metrics["failed_due_before"],
            metrics["failed_not_due_before"],
            metrics["dead_letter_before"],
            metrics["oldest_failed_age_seconds_before"],
            metrics["failed_due_after"],
            metrics["failed_not_due_after"],
            metrics["dead_letter_after"],
            metrics["oldest_failed_age_seconds_after"],
        )
        return metrics
    except Exception:
        db.rollback()
        clear_post_commit_actions(db=db)
        logger.exception("event=webhook_reprocess_failed provider=%s", PROVIDER)
        raise
    finally:
        db.close()


def run_forever(
    *,
    interval_minutes: int,
    batch_size: int,
    max_attempts: int,
    base_delay_minutes: int,
    max_delay_minutes: int,
) -> None:
    interval_seconds = int(interval_minutes) * 60
    logger.info(
        (
            "event=webhook_reprocess_started provider=%s interval_minutes=%s "
            "batch_size=%s max_attempts=%s base_delay_minutes=%s max_delay_minutes=%s"
        ),
        PROVIDER,
        int(interval_minutes),
        int(batch_size),
        int(max_attempts),
        int(base_delay_minutes),
        int(max_delay_minutes),
    )
    while True:
        run_once(
            batch_size=batch_size,
            max_attempts=max_attempts,
            base_delay_minutes=base_delay_minutes,
            max_delay_minutes=max_delay_minutes,
        )
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocess failed Mercadopago webhook events")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run reprocess once and exit",
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=None,
        help=(
            "Run interval in minutes "
            "(defaults to WEBHOOK_REPROCESS_INTERVAL_MINUTES or 30)"
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Batch size (defaults to WEBHOOK_REPROCESS_BATCH_SIZE or 25)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=None,
        help="Attempts before dead-letter (defaults to WEBHOOK_REPROCESS_MAX_ATTEMPTS or 4)",
    )
    parser.add_argument(
        "--base-delay-minutes",
        type=int,
        default=None,
        help=(
            "Initial retry delay for failed events "
            "(defaults to WEBHOOK_REPROCESS_BASE_DELAY_MINUTES or 30)"
        ),
    )
    parser.add_argument(
        "--max-delay-minutes",
        type=int,
        default=None,
        help=(
            "Max retry delay cap for exponential backoff "
            "(defaults to WEBHOOK_REPROCESS_MAX_DELAY_MINUTES or 720)"
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    interval_minutes = int(args.interval_minutes) if args.interval_minutes is not None else _interval_minutes()
    batch_size = int(args.batch_size) if args.batch_size is not None else _batch_size()
    max_attempts = int(args.max_attempts) if args.max_attempts is not None else _max_attempts()
    base_delay_minutes = (
        int(args.base_delay_minutes)
        if args.base_delay_minutes is not None
        else _base_delay_minutes()
    )
    max_delay_minutes = (
        int(args.max_delay_minutes)
        if args.max_delay_minutes is not None
        else _max_delay_minutes()
    )
    if interval_minutes <= 0:
        raise RuntimeError("interval must be greater than 0")
    if batch_size <= 0:
        raise RuntimeError("batch_size must be greater than 0")
    if max_attempts <= 0:
        raise RuntimeError("max_attempts must be greater than 0")
    if base_delay_minutes <= 0:
        raise RuntimeError("base_delay_minutes must be greater than 0")
    if max_delay_minutes <= 0:
        raise RuntimeError("max_delay_minutes must be greater than 0")

    if args.once:
        run_once(
            batch_size=batch_size,
            max_attempts=max_attempts,
            base_delay_minutes=base_delay_minutes,
            max_delay_minutes=max_delay_minutes,
        )
        return
    run_forever(
        interval_minutes=interval_minutes,
        batch_size=batch_size,
        max_attempts=max_attempts,
        base_delay_minutes=base_delay_minutes,
        max_delay_minutes=max_delay_minutes,
    )


if __name__ == "__main__":
    main()


