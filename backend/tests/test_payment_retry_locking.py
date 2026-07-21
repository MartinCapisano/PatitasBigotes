import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from source.db.models import Base
from source.services.payment_s import _latest_attempt_query


class PaymentRetryLockingTests(unittest.TestCase):
    """Guards the row lock both retry entrypoints depend on.

    The lock cannot be exercised for real here: the suite runs on SQLite, which has no
    SELECT ... FOR UPDATE and where SQLAlchemy silently drops the clause. Racing two
    sessions would therefore pass whether or not the lock is requested. What this test
    does check is that the statement carries FOR UPDATE once rendered for the dialect
    production actually uses, so a refactor that drops `.with_for_update()` fails here.
    """

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

    def _compiled_latest_attempt_sql(self, *, method: str) -> str:
        db = self.TestSession()
        try:
            query = _latest_attempt_query(db, order_id=1, method=method)
            return str(query.statement.compile(dialect=postgresql.dialect())).upper()
        finally:
            db.close()

    def test_latest_attempt_lookup_locks_the_row(self) -> None:
        # Both retry entrypoints reach the same query, so covering the two methods they
        # pass is enough to cover both flows.
        for method in ("mercadopago", "bank_transfer"):
            with self.subTest(method=method):
                self.assertIn("FOR UPDATE", self._compiled_latest_attempt_sql(method=method))

    def test_latest_attempt_lookup_orders_by_newest(self) -> None:
        # The guard reads .first(), so the ordering is part of what makes the lock useful:
        # both racers must lock the same row for the serialisation to mean anything.
        sql = self._compiled_latest_attempt_sql(method="mercadopago")
        self.assertIn("ORDER BY", sql)
        self.assertIn("CREATED_AT DESC", sql)


if __name__ == "__main__":
    unittest.main()
