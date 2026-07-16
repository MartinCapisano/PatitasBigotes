import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base, WebhookEvent
from source.jobs import reprocess_failed_webhooks_job as job
from source.services.mercadopago_client import WebhookNoOpError


class RetryDelayForAttemptTests(unittest.TestCase):
    def test_first_attempt_uses_base_delay(self) -> None:
        delay = job._retry_delay_minutes_for_attempt(
            attempt_number=1,
            base_delay_minutes=30,
            max_delay_minutes=720,
        )
        self.assertEqual(delay, 30)

    def test_delay_doubles_each_attempt(self) -> None:
        self.assertEqual(
            job._retry_delay_minutes_for_attempt(attempt_number=2, base_delay_minutes=30, max_delay_minutes=720),
            60,
        )
        self.assertEqual(
            job._retry_delay_minutes_for_attempt(attempt_number=3, base_delay_minutes=30, max_delay_minutes=720),
            120,
        )

    def test_delay_is_capped_at_max_delay(self) -> None:
        delay = job._retry_delay_minutes_for_attempt(
            attempt_number=10,
            base_delay_minutes=30,
            max_delay_minutes=720,
        )
        self.assertEqual(delay, 720)

    def test_non_positive_attempt_number_uses_base_delay(self) -> None:
        delay = job._retry_delay_minutes_for_attempt(
            attempt_number=0,
            base_delay_minutes=30,
            max_delay_minutes=720,
        )
        self.assertEqual(delay, 30)


class ParsePayloadTests(unittest.TestCase):
    def test_parses_valid_json_object(self) -> None:
        self.assertEqual(job._parse_payload('{"a": 1}'), {"a": 1})

    def test_returns_none_for_empty_or_missing_payload(self) -> None:
        self.assertIsNone(job._parse_payload(None))
        self.assertIsNone(job._parse_payload(""))

    def test_returns_none_for_invalid_json(self) -> None:
        self.assertIsNone(job._parse_payload("not json"))

    def test_returns_none_for_non_object_json(self) -> None:
        self.assertIsNone(job._parse_payload("[1, 2, 3]"))
        self.assertIsNone(job._parse_payload("42"))


class ExtractDataIdTests(unittest.TestCase):
    def test_extracts_string_id_from_data(self) -> None:
        self.assertEqual(job._extract_data_id({"data": {"id": "12345"}}), "12345")

    def test_extracts_and_normalizes_numeric_id(self) -> None:
        self.assertEqual(job._extract_data_id({"data": {"id": 12345}}), "12345")

    def test_returns_none_when_data_missing_or_not_dict(self) -> None:
        self.assertIsNone(job._extract_data_id({}))
        self.assertIsNone(job._extract_data_id({"data": "not-a-dict"}))

    def test_returns_none_when_id_missing_or_blank(self) -> None:
        self.assertIsNone(job._extract_data_id({"data": {}}))
        self.assertIsNone(job._extract_data_id({"data": {"id": "  "}}))


class ReprocessFailedWebhooksJobRunOnceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
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

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self._session_local_patch = patch.object(job, "SessionLocal", self.TestSession)
        self._session_local_patch.start()

    def tearDown(self) -> None:
        self._session_local_patch.stop()

    def _seed_failed_event(self, *, event_key: str, attempt_count: int, payload: dict | str | None) -> None:
        db = self.TestSession()
        try:
            import json as json_module

            serialized = (
                payload
                if isinstance(payload, str) or payload is None
                else json_module.dumps(payload)
            )
            db.add(
                WebhookEvent(
                    provider="mercadopago",
                    event_key=event_key,
                    status="failed",
                    payload=serialized,
                    received_at=datetime.now(UTC) - timedelta(hours=1),
                    attempt_count=attempt_count,
                    next_retry_at=None,
                    dead_letter_at=None,
                )
            )
            db.commit()
        finally:
            db.close()

    def test_run_once_reprocesses_event_successfully(self) -> None:
        self._seed_failed_event(
            event_key="mp:event:1",
            attempt_count=0,
            payload={"data": {"id": "123"}},
        )

        with patch.object(job, "process_mercadopago_event_payload", return_value={"id": 1}), patch.object(
            job, "dispatch_post_commit_actions"
        ):
            metrics = job.run_once(
                batch_size=25,
                max_attempts=4,
                base_delay_minutes=30,
                max_delay_minutes=720,
            )

        self.assertEqual(metrics["selected"], 1)
        self.assertEqual(metrics["reprocessed"], 1)
        self.assertEqual(metrics["still_failed"], 0)
        self.assertEqual(metrics["dead_lettered"], 0)

        db = self.TestSession()
        try:
            event = db.query(WebhookEvent).filter(WebhookEvent.event_key == "mp:event:1").first()
            self.assertIsNotNone(event)
            assert event is not None
            self.assertEqual(event.status, "processed")
        finally:
            db.close()

    def test_run_once_dead_letters_event_after_max_attempts(self) -> None:
        self._seed_failed_event(
            event_key="mp:event:dead",
            attempt_count=3,
            payload={"data": {"id": "456"}},
        )

        with patch.object(
            job,
            "process_mercadopago_event_payload",
            side_effect=RuntimeError("provider unavailable"),
        ):
            metrics = job.run_once(
                batch_size=25,
                max_attempts=4,
                base_delay_minutes=30,
                max_delay_minutes=720,
            )

        self.assertEqual(metrics["selected"], 1)
        self.assertEqual(metrics["dead_lettered"], 1)
        self.assertEqual(metrics["still_failed"], 0)

        db = self.TestSession()
        try:
            event = db.query(WebhookEvent).filter(WebhookEvent.event_key == "mp:event:dead").first()
            self.assertIsNotNone(event)
            assert event is not None
            self.assertEqual(event.status, "dead_letter")
            self.assertIsNotNone(event.dead_letter_at)
        finally:
            db.close()

    def test_run_once_marks_invalid_payload_as_still_failed_without_calling_processor(self) -> None:
        self._seed_failed_event(event_key="mp:event:badpayload", attempt_count=0, payload="not json")

        with patch.object(job, "process_mercadopago_event_payload") as mocked_process:
            metrics = job.run_once(
                batch_size=25,
                max_attempts=4,
                base_delay_minutes=30,
                max_delay_minutes=720,
            )

        mocked_process.assert_not_called()
        self.assertEqual(metrics["still_failed"], 1)
        self.assertEqual(metrics["reprocessed"], 0)

    def test_run_once_counts_retryable_noop_as_still_failed(self) -> None:
        self._seed_failed_event(
            event_key="mp:event:noop-retryable",
            attempt_count=0,
            payload={"data": {"id": "789"}},
        )

        with patch.object(
            job,
            "process_mercadopago_event_payload",
            side_effect=WebhookNoOpError("payment not found"),
        ):
            metrics = job.run_once(
                batch_size=25,
                max_attempts=4,
                base_delay_minutes=30,
                max_delay_minutes=720,
            )

        self.assertEqual(metrics["still_failed"], 1)
        self.assertEqual(metrics["reprocessed_noop"], 0)

    def test_run_once_counts_non_retryable_noop_as_reprocessed_noop(self) -> None:
        self._seed_failed_event(
            event_key="mp:event:noop-final",
            attempt_count=0,
            payload={"data": {"id": "789"}},
        )

        with patch.object(
            job,
            "process_mercadopago_event_payload",
            side_effect=WebhookNoOpError("unsupported topic"),
        ):
            metrics = job.run_once(
                batch_size=25,
                max_attempts=4,
                base_delay_minutes=30,
                max_delay_minutes=720,
            )

        self.assertEqual(metrics["reprocessed_noop"], 1)
        self.assertEqual(metrics["still_failed"], 0)

    def test_run_once_returns_zero_metrics_when_nothing_to_reprocess(self) -> None:
        metrics = job.run_once(
            batch_size=25,
            max_attempts=4,
            base_delay_minutes=30,
            max_delay_minutes=720,
        )

        self.assertEqual(metrics["selected"], 0)
        self.assertEqual(metrics["reprocessed"], 0)


if __name__ == "__main__":
    unittest.main()
