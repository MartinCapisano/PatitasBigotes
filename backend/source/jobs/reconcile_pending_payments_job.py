from __future__ import annotations

import argparse
from datetime import UTC, datetime
import logging
import os
import time

from source.db.session import SessionLocal
from source.services.mercadopago_client import find_latest_payment_by_external_reference
from source.services.post_commit_actions_s import clear_post_commit_actions, dispatch_post_commit_actions
from source.services.mercadopago_normalization_s import normalize_mp_payment_state
from source.services.payment_s import (
    apply_mercadopago_normalized_state,
    list_reconcilable_pending_mercadopago_payments,
)

DEFAULT_INTERVAL_MINUTES = 180
DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_AGE_HOURS = 24
DEFAULT_MIN_AGE_MINUTES = 15

logger = logging.getLogger("payments_reconcile_job")


def _interval_minutes() -> int:
    raw = str(os.getenv("PAYMENTS_RECONCILE_INTERVAL_MINUTES", DEFAULT_INTERVAL_MINUTES)).strip()
    value = int(raw)
    if value <= 0:
        raise RuntimeError("PAYMENTS_RECONCILE_INTERVAL_MINUTES must be greater than 0")
    return value


def _batch_size() -> int:
    raw = str(os.getenv("PAYMENTS_RECONCILE_BATCH_SIZE", DEFAULT_BATCH_SIZE)).strip()
    value = int(raw)
    if value <= 0:
        raise RuntimeError("PAYMENTS_RECONCILE_BATCH_SIZE must be greater than 0")
    return value


def _max_age_hours() -> int:
    raw = str(os.getenv("PAYMENTS_RECONCILE_MAX_AGE_HOURS", DEFAULT_MAX_AGE_HOURS)).strip()
    value = int(raw)
    if value <= 0:
        raise RuntimeError("PAYMENTS_RECONCILE_MAX_AGE_HOURS must be greater than 0")
    return value


def _min_age_minutes() -> int:
    raw = str(os.getenv("PAYMENTS_RECONCILE_MIN_AGE_MINUTES", DEFAULT_MIN_AGE_MINUTES)).strip()
    value = int(raw)
    if value < 0:
        raise RuntimeError("PAYMENTS_RECONCILE_MIN_AGE_MINUTES must be >= 0")
    return value


def run_once(*, batch_size: int, max_age_hours: int, min_age_minutes: int) -> dict[str, int]:
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        candidates = list_reconcilable_pending_mercadopago_payments(
            db=db,
            now=now,
            limit=int(batch_size),
            max_age_hours=int(max_age_hours),
            min_age_minutes=int(min_age_minutes),
        )
        metrics = {
            "selected": int(len(candidates)),
            "reconciled": 0,
            "provider_not_found": 0,
            "failed": 0,
        }

        for payment in candidates:
            try:
                external_ref = str(payment.external_ref or "").strip()
                if not external_ref:
                    metrics["provider_not_found"] += 1
                    continue

                provider_payment = find_latest_payment_by_external_reference(external_ref)
                if provider_payment is None:
                    metrics["provider_not_found"] += 1
                    continue

                normalized_state = normalize_mp_payment_state(provider_payment)
                apply_mercadopago_normalized_state(
                    payment_id=int(payment.id),
                    normalized_state=normalized_state,
                    notification_payload={
                        "source": "batch_reconcile",
                        "external_ref": external_ref,
                    },
                    db=db,
                )
                db.commit()
                dispatch_post_commit_actions(db=db, source="payments_reconcile_job")
                metrics["reconciled"] += 1
            except Exception:
                db.rollback()
                clear_post_commit_actions(db=db)
                metrics["failed"] += 1
                logger.exception(
                    "event=payments_reconcile_item_failed payment_id=%s external_ref=%s",
                    int(payment.id),
                    str(payment.external_ref or ""),
                )

        logger.info(
            "event=payments_reconcile_run selected=%s reconciled=%s provider_not_found=%s failed=%s batch_size=%s max_age_hours=%s min_age_minutes=%s",
            metrics["selected"],
            metrics["reconciled"],
            metrics["provider_not_found"],
            metrics["failed"],
            int(batch_size),
            int(max_age_hours),
            int(min_age_minutes),
        )
        return metrics
    finally:
        db.close()


def run_forever(*, interval_minutes: int, batch_size: int, max_age_hours: int, min_age_minutes: int) -> None:
    interval_seconds = int(interval_minutes) * 60
    logger.info(
        "event=payments_reconcile_started interval_minutes=%s batch_size=%s max_age_hours=%s min_age_minutes=%s",
        int(interval_minutes),
        int(batch_size),
        int(max_age_hours),
        int(min_age_minutes),
    )
    while True:
        run_once(
            batch_size=batch_size,
            max_age_hours=max_age_hours,
            min_age_minutes=min_age_minutes,
        )
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile pending mercadopago payments")
    parser.add_argument("--once", action="store_true", help="Run reconciliation once and exit")
    parser.add_argument("--interval-minutes", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--max-age-hours", type=int, default=None)
    parser.add_argument("--min-age-minutes", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    interval_minutes = int(args.interval_minutes) if args.interval_minutes is not None else _interval_minutes()
    batch_size = int(args.batch_size) if args.batch_size is not None else _batch_size()
    max_age_hours = int(args.max_age_hours) if args.max_age_hours is not None else _max_age_hours()
    min_age_minutes = (
        int(args.min_age_minutes) if args.min_age_minutes is not None else _min_age_minutes()
    )

    if args.once:
        run_once(
            batch_size=batch_size,
            max_age_hours=max_age_hours,
            min_age_minutes=min_age_minutes,
        )
        return
    run_forever(
        interval_minutes=interval_minutes,
        batch_size=batch_size,
        max_age_hours=max_age_hours,
        min_age_minutes=min_age_minutes,
    )


if __name__ == "__main__":
    main()
