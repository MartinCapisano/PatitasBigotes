from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from backend.tests.http._base import HttpFundamentalsBase
from source.db.models import (
    Category,
    Order,
    OrderItem,
    Payment,
    PaymentIncident,
    Product,
    ProductVariant,
    StockReservation,
    User,
)


class HttpPaymentsFundamentalsTests(HttpFundamentalsBase):
    def _seed_submitted_order_with_reservation_for_user(self, *, user_id: int) -> int:
        db = self._db()
        try:
            category = Category(name=f"pay-cat-{datetime.now(UTC).timestamp()}")
            db.add(category)
            db.flush()

            product = Product(
                name="Payment Product",
                description="demo",
                category_id=int(category.id),
            )
            db.add(product)
            db.flush()

            variant = ProductVariant(
                product_id=int(product.id),
                sku=f"PAY-SKU-{datetime.now(UTC).timestamp()}",
                size="M",
                color="Blue",
                price=10000,
                stock=10,
                is_active=True,
            )
            db.add(variant)
            db.flush()

            order = Order(
                user_id=int(user_id),
                status="submitted",
                currency="ARS",
                subtotal=10000,
                discount_total=0,
                total_amount=10000,
                pricing_frozen=True,
                submitted_at=datetime.now(UTC),
            )
            db.add(order)
            db.flush()

            item = OrderItem(
                order_id=int(order.id),
                product_id=int(product.id),
                variant_id=int(variant.id),
                quantity=1,
                unit_price=10000,
                discount_id=None,
                discount_amount=0,
                final_unit_price=10000,
                line_total=10000,
            )
            db.add(item)
            db.flush()

            reservation = StockReservation(
                order_id=int(order.id),
                order_item_id=int(item.id),
                variant_id=int(variant.id),
                quantity=1,
                status="active",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            db.add(reservation)
            db.commit()
            return int(order.id)
        finally:
            db.close()

    def _seed_retryable_payment(self, *, order_id: int, method: str, status: str) -> int:
        db = self._db()
        try:
            payment = Payment(
                order_id=int(order_id),
                method=method,
                status=status,
                amount=10000,
                currency="ARS",
                idempotency_key=f"{method}-{status}-{datetime.now(UTC).timestamp()}",
                external_ref=f"{method}-ref-{datetime.now(UTC).timestamp()}",
                provider_status=status,
                provider_payload=None,
                receipt_url=None,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                paid_at=None,
            )
            db.add(payment)
            db.commit()
            return int(payment.id)
        finally:
            db.close()

    def _seed_payment_incident(self) -> int:
        db = self._db()
        try:
            customer = User(
                first_name="Jane",
                last_name="Customer",
                email=f"customer-{datetime.now(UTC).timestamp()}@example.com",
                phone="1122334455",
                password_hash="!",
                has_account=False,
                is_admin=False,
            )
            db.add(customer)
            db.flush()

            order = Order(
                user_id=int(customer.id),
                status="paid",
                currency="ARS",
                subtotal=10000,
                discount_total=0,
                total_amount=10000,
                pricing_frozen=True,
                submitted_at=datetime.now(UTC),
                paid_at=datetime.now(UTC),
            )
            db.add(order)
            db.flush()

            payment = Payment(
                order_id=int(order.id),
                method="mercadopago",
                status="paid",
                amount=10000,
                currency="ARS",
                idempotency_key=f"idemp-paid-{datetime.now(UTC).timestamp()}",
                external_ref=f"mp-order-{order.id}-pay-2",
                provider_status="approved",
                provider_payload='{"reconciliation":{"provider_payment_id":"123456"}}',
                receipt_url=None,
                expires_at=None,
                paid_at=datetime.now(UTC),
            )
            db.add(payment)
            db.flush()

            incident = PaymentIncident(
                order_id=int(order.id),
                payment_id=int(payment.id),
                type="late_paid_duplicate",
                status="pending_review",
                reason="late approval",
            )
            db.add(incident)
            db.commit()
            return int(incident.id)
        finally:
            db.close()

    def test_create_order_payment_rejects_non_ars_currency_over_http(self) -> None:
        user_id = self._create_user(email="pay-currency@example.com", verified=True)
        order_id = self._seed_submitted_order_with_reservation_for_user(user_id=user_id)
        login_response = self._login(email="pay-currency@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            f"/orders/{order_id}/payments",
            json={"method": "bank_transfer", "currency": "USD"},
            headers={
                **self._origin_headers(),
                "Idempotency-Key": "payment-usd-key",
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_retry_payment_creates_new_attempt_after_cancelled_over_http(self) -> None:
        user_id = self._create_user(email="pay-retry@example.com", verified=True)
        order_id = self._seed_submitted_order_with_reservation_for_user(user_id=user_id)
        cancelled_id = self._seed_retryable_payment(
            order_id=order_id,
            method="bank_transfer",
            status="cancelled",
        )
        login_response = self._login(email="pay-retry@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            f"/orders/{order_id}/payments/retry",
            json={"method": "bank_transfer", "currency": "ARS"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertNotEqual(int(payload["id"]), cancelled_id)
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["method"], "bank_transfer")

    def test_retry_payment_requires_retryable_latest_status_over_http(self) -> None:
        user_id = self._create_user(email="pay-retry-blocked@example.com", verified=True)
        order_id = self._seed_submitted_order_with_reservation_for_user(user_id=user_id)
        self._seed_retryable_payment(
            order_id=order_id,
            method="bank_transfer",
            status="pending",
        )
        login_response = self._login(email="pay-retry-blocked@example.com")
        self.assertEqual(login_response.status_code, 200)

        response = self.client.post(
            f"/orders/{order_id}/payments/retry",
            json={"method": "bank_transfer", "currency": "ARS"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "latest payment attempt is not retryable")

    def test_submit_bank_transfer_receipt_updates_payment_over_http(self) -> None:
        user_id = self._create_user(email="pay-receipt@example.com", verified=True)
        order_id = self._seed_submitted_order_with_reservation_for_user(user_id=user_id)
        login_response = self._login(email="pay-receipt@example.com")
        self.assertEqual(login_response.status_code, 200)

        create_response = self.client.post(
            f"/orders/{order_id}/payments",
            json={"method": "bank_transfer", "currency": "ARS"},
            headers={
                **self._origin_headers(),
                "Idempotency-Key": "payment-receipt-key",
            },
        )
        self.assertEqual(create_response.status_code, 201)
        payment_id = int(create_response.json()["data"]["id"])

        response = self.client.post(
            f"/orders/{order_id}/payments/{payment_id}/bank-transfer/receipt",
            json={"receipt_url": "https://example.com/receipt-1.jpg"},
            headers=self._origin_headers(),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["receipt_url"], "https://example.com/receipt-1.jpg")
        self.assertEqual(payload["provider_payload_data"]["receipt"]["url"], "https://example.com/receipt-1.jpg")

    def test_resolve_payment_incident_refund_success_over_http(self) -> None:
        incident_id = self._seed_payment_incident()
        self._create_user(email="admin-refund@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-refund@example.com")
        self.assertEqual(login_response.status_code, 200)

        with patch(
            "source.services.refund_s.create_refund",
            return_value={"id": 9001, "status": "approved"},
        ):
            response = self.client.post(
                f"/admin/payment-incidents/{incident_id}/resolve-refund",
                json={"reason": "cliente ya pago en local"},
                headers=self._origin_headers(),
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["data"]
        self.assertEqual(payload["incident"]["status"], "resolved_refunded")
        self.assertEqual(payload["refund"]["status"], "approved")
        self.assertEqual(payload["refund"]["provider_refund_id"], "9001")

    def test_resolve_payment_incident_refund_is_idempotent_over_http(self) -> None:
        incident_id = self._seed_payment_incident()
        self._create_user(email="admin-refund-idemp@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-refund-idemp@example.com")
        self.assertEqual(login_response.status_code, 200)

        with patch(
            "source.services.refund_s.create_refund",
            return_value={"id": 9010, "status": "approved"},
        ):
            first = self.client.post(
                f"/admin/payment-incidents/{incident_id}/resolve-refund",
                json={"amount": 10000, "reason": "cliente ya pago en local"},
                headers=self._origin_headers(),
            )
            second = self.client.post(
                f"/admin/payment-incidents/{incident_id}/resolve-refund",
                json={"amount": 10000, "reason": "cliente ya pago en local"},
                headers=self._origin_headers(),
            )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["data"]["refund"]["id"], second.json()["data"]["refund"]["id"])
        self.assertEqual(second.json()["data"]["incident"]["status"], "resolved_refunded")

    def test_resolve_payment_incident_no_refund_requires_reason_over_http(self) -> None:
        incident_id = self._seed_payment_incident()
        admin_id = self._create_user(email="admin-no-refund@example.com", is_admin=True, verified=True)
        login_response = self._login(email="admin-no-refund@example.com")
        self.assertEqual(login_response.status_code, 200)

        invalid_response = self.client.post(
            f"/admin/payment-incidents/{incident_id}/resolve-no-refund",
            json={"reason": ""},
            headers=self._origin_headers(),
        )
        self.assertEqual(invalid_response.status_code, 422)

        valid_response = self.client.post(
            f"/admin/payment-incidents/{incident_id}/resolve-no-refund",
            json={"reason": "caso validado y no corresponde devolver"},
            headers=self._origin_headers(),
        )
        self.assertEqual(valid_response.status_code, 200)
        payload = valid_response.json()["data"]
        self.assertEqual(payload["status"], "resolved_no_refund")
        self.assertEqual(payload["resolved_by_user_id"], admin_id)
