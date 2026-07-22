"""La cola de transferencias pendientes que mira el admin.

No hay webhook: la verificación entera es un humano cruzando una línea del
extracto bancario con una orden. Estos tests cuidan que la fila traiga lo que
hace falta para ese cruce -- referencia, cliente, monto exacto y cuándo vence la
reserva -- y que solo aparezca lo que todavía se puede cobrar.
"""
import os
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

from source.db.models import Base, Order, Payment
from source.services.payment_admin_queries_s import (
    list_pending_bank_transfer_payments_for_admin,
)
from source.services.payment_s import create_payment_for_order
from tests.factories.orders import create_order_graph
from tests.factories.users import create_user

SHOP_CONFIG = {
    "BANK_TRANSFER_ALIAS": "patitas.bigotes.real",
    "BANK_TRANSFER_CBU": "0110599520000012345678",
    "BANK_TRANSFER_BANK_NAME": "Banco Nacion",
    "BANK_TRANSFER_HOLDER": "Martin Capisano",
    "BANK_TRANSFER_CUIT": "20-35123456-7",
    "WHATSAPP_NUMBER": "+54 9 351 123-4567",
}


class AdminBankTransferQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine("sqlite:///:memory:")
        cls.TestSession = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def _seed_transfer(
        self,
        *,
        first_name: str = "Jane",
        last_name: str = "Doe",
        price: int = 25990,
        reservation_expires_at=None,
        created_at=None,
    ) -> dict:
        session = self.TestSession()
        try:
            user = create_user(
                session,
                first_name=first_name,
                last_name=last_name,
                email_prefix=first_name.lower(),
                has_account=False,
            )
            graph = create_order_graph(
                session,
                user_id=int(user.id),
                order_status="submitted",
                price=price,
                variant_stock=5,
                with_reservation=True,
                reservation_expires_at=reservation_expires_at,
            )
            session.commit()
            order_id = int(graph["order_id"])
            with patch.dict(os.environ, SHOP_CONFIG):
                payment = create_payment_for_order(
                    order_id=order_id,
                    method="bank_transfer",
                    db=session,
                    user_id=int(user.id),
                    idempotency_key=f"idemp-{datetime.now(UTC).timestamp()}",
                    currency="ARS",
                )
            if created_at is not None:
                row = session.query(Payment).filter(Payment.id == int(payment["id"])).one()
                row.created_at = created_at
            session.commit()
            return {
                "order_id": order_id,
                "payment_id": int(payment["id"]),
                "user_id": int(user.id),
            }
        finally:
            session.close()

    def _queue(self) -> list[dict]:
        session = self.TestSession()
        try:
            return list_pending_bank_transfer_payments_for_admin(db=session)
        finally:
            session.close()

    def test_the_row_carries_what_the_admin_needs_to_cross_the_money(self) -> None:
        seeded = self._seed_transfer(first_name="Ana", last_name="Perez", price=25990)

        rows = self._queue()

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["order_id"], seeded["order_id"])
        self.assertEqual(row["id"], seeded["payment_id"])
        self.assertEqual(
            row["reference"],
            f"ORDER-{seeded['order_id']}-PAY-{seeded['payment_id']}",
        )
        self.assertEqual(row["amount"], 25990)
        self.assertEqual(row["order_total"], 25990)
        self.assertEqual(row["currency"], "ARS")
        self.assertEqual(row["customer"]["first_name"], "Ana")
        self.assertEqual(row["customer"]["last_name"], "Perez")
        self.assertIsNotNone(row["reservation_expires_at"])

    def test_the_reference_is_the_one_the_customer_was_shown(self) -> None:
        """La fila repite el string que viajó a la pantalla y al WhatsApp.

        Si acá se armara uno nuevo, el admin buscaría una referencia que el
        cliente nunca escribió en su transferencia.
        """
        seeded = self._seed_transfer()

        session = self.TestSession()
        try:
            payment = session.query(Payment).filter(Payment.id == seeded["payment_id"]).one()
            from source.services.payment_core_s import deserialize_provider_payload

            shown = deserialize_provider_payload(payment.provider_payload)["instructions"]["reference"]
        finally:
            session.close()

        self.assertEqual(self._queue()[0]["reference"], shown)

    def test_it_says_when_the_reservation_lapses(self) -> None:
        """Es el reloj que efectivamente cancela: sirve para priorizar la cola."""
        deadline = datetime.now(UTC) + timedelta(hours=3)
        self._seed_transfer(reservation_expires_at=deadline)

        expires_at = self._queue()[0]["reservation_expires_at"]

        self.assertIsNotNone(expires_at)
        parsed = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
        self.assertLess(abs((parsed - deadline).total_seconds()), 2)

    def test_the_oldest_transfer_comes_first(self) -> None:
        """La que más esperó es la que está más cerca de caerse."""
        now = datetime.now(UTC)
        old = self._seed_transfer(first_name="Vieja", created_at=now - timedelta(hours=30))
        new = self._seed_transfer(first_name="Nueva", created_at=now - timedelta(hours=1))

        rows = self._queue()

        self.assertEqual([row["order_id"] for row in rows], [old["order_id"], new["order_id"]])

    def test_a_confirmed_transfer_leaves_the_queue(self) -> None:
        seeded = self._seed_transfer()
        session = self.TestSession()
        try:
            payment = session.query(Payment).filter(Payment.id == seeded["payment_id"]).one()
            payment.status = "paid"
            payment.order.status = "paid"
            session.commit()
        finally:
            session.close()

        self.assertEqual(self._queue(), [])

    def test_a_cancelled_order_leaves_the_queue(self) -> None:
        seeded = self._seed_transfer()
        session = self.TestSession()
        try:
            order = session.query(Order).filter(Order.id == seeded["order_id"]).one()
            order.status = "cancelled"
            session.commit()
        finally:
            session.close()

        self.assertEqual(self._queue(), [])

    def test_cash_and_mercadopago_do_not_show_up(self) -> None:
        """La cola es de transferencias: el efectivo no espera comprobante."""
        session = self.TestSession()
        try:
            user = create_user(session, email_prefix="cash", has_account=False)
            create_order_graph(
                session,
                user_id=int(user.id),
                order_status="submitted",
                add_pending_payment=True,
                payment_method="cash",
            )
            create_order_graph(
                session,
                user_id=int(user.id),
                order_status="submitted",
                add_pending_payment=True,
                payment_method="mercadopago",
            )
            session.commit()
        finally:
            session.close()

        self.assertEqual(self._queue(), [])


if __name__ == "__main__":
    unittest.main()
