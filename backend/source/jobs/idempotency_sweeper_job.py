from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timedelta, UTC

from source.db.session import SessionLocal
from source.services.idempotency_s import prune_expired_records, mark_record_failed
from source.db.models import IdempotencyRecord

logger = logging.getLogger("idempotency_sweeper")

DEFAULT_PROCESSING_TIMEOUT_MINUTES = 30
DEFAULT_LIMIT = 200
DEFAULT_INTERVAL_MINUTES = 60


def run_once(*, processing_timeout_minutes: int, limit: int) -> dict[str, int]:
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        pruned = prune_expired_records(now=now, db=db, limit=int(limit))
        logger.info("pruned_expired_idempotency_records=%s", int(pruned or 0))

        cutoff = now - timedelta(minutes=int(processing_timeout_minutes))
        candidates = (
            db.query(IdempotencyRecord)
            .filter(IdempotencyRecord.status == "processing", IdempotencyRecord.created_at <= cutoff)
            .order_by(IdempotencyRecord.created_at.asc(), IdempotencyRecord.id.asc())
            .limit(int(limit))
            .all()
        )
        marked = 0
        for record in candidates:
            try:
                payload = {"detail": "processing timeout", "timed_out_at": now.astimezone(UTC).isoformat().replace('+00:00', 'Z')}
                mark_record_failed(record=record, response_payload=payload, db=db)
                marked += 1
            except Exception:
                logger.exception("failed to mark idempotency record failed id=%s scope=%s key=%s", getattr(record, "id", None), getattr(record, "scope", None), getattr(record, "idempotency_key", None))
                db.rollback()
        db.commit()
        return {"pruned": int(pruned or 0), "marked_failed": int(marked)}
    finally:
        db.close()


def run_forever(*, interval_minutes: int, processing_timeout_minutes: int, limit: int) -> None:
    interval_seconds = int(interval_minutes) * 60
    logger.info("idempotency_sweeper_started interval_minutes=%s processing_timeout_minutes=%s limit=%s", interval_minutes, processing_timeout_minutes, limit)
    while True:
        try:
            run_once(processing_timeout_minutes=processing_timeout_minutes, limit=limit)
        except Exception:
            logger.exception("idempotency_sweeper_iteration_failed")
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Idempotency sweeper: prune expired records and mark stuck processing records as failed")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval-minutes", type=int, default=None)
    parser.add_argument("--processing-timeout-minutes", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    interval_minutes = int(args.interval_minutes) if args.interval_minutes is not None else int(os.getenv("IDEMPOTENCY_SWEEPER_INTERVAL_MINUTES", DEFAULT_INTERVAL_MINUTES))
    processing_timeout_minutes = int(args.processing_timeout_minutes) if args.processing_timeout_minutes is not None else int(os.getenv("IDEMPOTENCY_PROCESSING_TIMEOUT_MINUTES", DEFAULT_PROCESSING_TIMEOUT_MINUTES))
    limit = int(args.limit) if args.limit is not None else int(os.getenv("IDEMPOTENCY_SWEEPER_LIMIT", DEFAULT_LIMIT))

    if args.once:
        run_once(processing_timeout_minutes=processing_timeout_minutes, limit=limit)
        return
    run_forever(interval_minutes=interval_minutes, processing_timeout_minutes=processing_timeout_minutes, limit=limit)


if __name__ == "__main__":
    main()
