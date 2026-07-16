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

from source.db.models import Base
from source.jobs import expire_stock_reservations_job
from tests.factories.orders import create_order_graph
from tests.factories.users import create_user


class ExpireStockReservationsJobRunOnceTests(unittest.TestCase):
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
            expire_stock_reservations_job,
            "SessionLocal",
            self.TestSession,
        )
        self._session_local_patch.start()

    def tearDown(self) -> None:
        self._session_local_patch.stop()

    def _seed_expired_cancellable_reservation(self, *, sku_prefix: str) -> None:
        db = self.TestSession()
        try:
            user = create_user(db, email_prefix=sku_prefix)
            create_order_graph(
                db,
                user_id=int(user.id),
                order_status="submitted",
                variant_stock=1,
                item_qty=2,
                with_reservation=True,
                reservation_expires_at=datetime.now(UTC) - timedelta(minutes=1),
                sku_prefix=sku_prefix,
            )
            db.commit()
        finally:
            db.close()

    def test_run_once_stops_early_when_batch_returns_zero(self) -> None:
        self._seed_expired_cancellable_reservation(sku_prefix="JOB-SKU-1")
        self._seed_expired_cancellable_reservation(sku_prefix="JOB-SKU-2")

        processed = expire_stock_reservations_job.run_once(batch_limit=10, max_batches=20)

        self.assertEqual(processed, 2)

    def test_run_once_respects_batch_limit_across_multiple_batches(self) -> None:
        self._seed_expired_cancellable_reservation(sku_prefix="JOB-SKU-3")
        self._seed_expired_cancellable_reservation(sku_prefix="JOB-SKU-4")
        self._seed_expired_cancellable_reservation(sku_prefix="JOB-SKU-5")

        processed = expire_stock_reservations_job.run_once(batch_limit=1, max_batches=2)

        self.assertEqual(processed, 2)

    def test_run_once_caps_at_max_batches_even_with_more_pending(self) -> None:
        self._seed_expired_cancellable_reservation(sku_prefix="JOB-SKU-6")
        self._seed_expired_cancellable_reservation(sku_prefix="JOB-SKU-7")
        self._seed_expired_cancellable_reservation(sku_prefix="JOB-SKU-8")

        processed = expire_stock_reservations_job.run_once(batch_limit=1, max_batches=1)

        self.assertEqual(processed, 1)

    def test_run_once_returns_zero_when_nothing_expired(self) -> None:
        processed = expire_stock_reservations_job.run_once(batch_limit=10, max_batches=5)

        self.assertEqual(processed, 0)


if __name__ == "__main__":
    unittest.main()
