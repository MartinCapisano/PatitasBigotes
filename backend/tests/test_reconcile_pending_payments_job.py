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

from source.db.models import Base, Payment
from source.jobs import reconcile_pending_payments_job
from tests.factories.orders import create_order_graph
from tests.factories.users import create_user


class ReconcilePendingPaymentsJobRunOnceTests(unittest.TestCase):
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
        self._session_local_patch = patch.object(
            reconcile_pending_payments_job,
            "SessionLocal",
            self.TestSession,
        )
        self._session_local_patch.start()

    def tearDown(self) -> None:
        self._session_local_patch.stop()

    def _seed_reconcilable_payment(self, *, external_ref: str, sku_prefix: str) -> int:
        db = self.TestSession()
        try:
            user = create_user(db, email_prefix=sku_prefix)
            graph = create_order_graph(
                db,
                user_id=int(user.id),
                order_status="submitted",
                with_reservation=False,
                sku_prefix=sku_prefix,
            )
            payment = Payment(
                order_id=int(graph["order_id"]),
                method="mercadopago",
                status="pending",
                amount=10000,
                currency="ARS",
                idempotency_key=f"idemp-{sku_prefix}",
                external_ref=external_ref,
                provider_status="pending",
                created_at=datetime.now(UTC) - timedelta(hours=1),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            db.add(payment)
            db.commit()
            return int(payment.id)
        finally:
            db.close()

    def test_run_once_reconciles_found_payment(self) -> None:
        self._seed_reconcilable_payment(external_ref="mp-ref-found", sku_prefix="RECON-1")

        with patch.object(
            reconcile_pending_payments_job,
            "find_latest_payment_by_external_reference",
            return_value={"id": "mp-999"},
        ), patch.object(
            reconcile_pending_payments_job,
            "normalize_mp_payment_state",
            return_value={
                "provider_status": "approved",
                "internal_status": "paid",
                "external_reference": "mp-ref-found",
            },
        ), patch.object(
            reconcile_pending_payments_job,
            "apply_mercadopago_normalized_state",
            return_value={"id": 1, "status": "paid"},
        ) as mocked_apply, patch.object(
            reconcile_pending_payments_job,
            "dispatch_post_commit_actions",
        ) as mocked_dispatch:
            metrics = reconcile_pending_payments_job.run_once(
                batch_size=50,
                max_age_hours=24,
                min_age_minutes=0,
            )

        self.assertEqual(metrics, {"selected": 1, "reconciled": 1, "provider_not_found": 0, "failed": 0})
        mocked_apply.assert_called_once()
        mocked_dispatch.assert_called_once()

    def test_run_once_counts_provider_not_found_when_lookup_returns_none(self) -> None:
        self._seed_reconcilable_payment(external_ref="mp-ref-missing", sku_prefix="RECON-2")

        with patch.object(
            reconcile_pending_payments_job,
            "find_latest_payment_by_external_reference",
            return_value=None,
        ):
            metrics = reconcile_pending_payments_job.run_once(
                batch_size=50,
                max_age_hours=24,
                min_age_minutes=0,
            )

        self.assertEqual(
            metrics,
            {"selected": 1, "reconciled": 0, "provider_not_found": 1, "failed": 0},
        )

    def test_run_once_counts_failed_and_continues_after_exception(self) -> None:
        self._seed_reconcilable_payment(external_ref="mp-ref-fail", sku_prefix="RECON-3")
        self._seed_reconcilable_payment(external_ref="mp-ref-ok", sku_prefix="RECON-4")

        def fake_find(external_ref: str):
            return {"id": "mp-999", "external_ref": external_ref}

        def fake_apply(*, payment_id, normalized_state, notification_payload=None, db):
            if normalized_state.get("external_reference") == "mp-ref-fail":
                raise RuntimeError("boom")
            return {"id": payment_id, "status": "paid"}

        with patch.object(
            reconcile_pending_payments_job,
            "find_latest_payment_by_external_reference",
            side_effect=fake_find,
        ), patch.object(
            reconcile_pending_payments_job,
            "normalize_mp_payment_state",
            side_effect=lambda provider_payment: {
                "provider_status": "approved",
                "internal_status": "paid",
                "external_reference": provider_payment["external_ref"],
            },
        ), patch.object(
            reconcile_pending_payments_job,
            "apply_mercadopago_normalized_state",
            side_effect=fake_apply,
        ), patch.object(
            reconcile_pending_payments_job,
            "dispatch_post_commit_actions",
        ), patch.object(
            reconcile_pending_payments_job,
            "clear_post_commit_actions",
        ) as mocked_clear:
            metrics = reconcile_pending_payments_job.run_once(
                batch_size=50,
                max_age_hours=24,
                min_age_minutes=0,
            )

        self.assertEqual(metrics["selected"], 2)
        self.assertEqual(metrics["reconciled"], 1)
        self.assertEqual(metrics["failed"], 1)
        mocked_clear.assert_called_once()

    def test_run_once_returns_zero_metrics_when_nothing_to_reconcile(self) -> None:
        metrics = reconcile_pending_payments_job.run_once(
            batch_size=50,
            max_age_hours=24,
            min_age_minutes=0,
        )

        self.assertEqual(
            metrics,
            {"selected": 0, "reconciled": 0, "provider_not_found": 0, "failed": 0},
        )


if __name__ == "__main__":
    unittest.main()
