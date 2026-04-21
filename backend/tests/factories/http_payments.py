from datetime import UTC, datetime, timedelta
import json

from source.db.models import (
    Order,
    Payment,
    PaymentIncident,
)
from tests.factories.orders import create_order_graph
from tests.factories.users import create_user


def create_submitted_order_with_reservation_for_user(db, *, user_id: int) -> int:
    graph = create_order_graph(
        db,
        user_id=int(user_id),
        order_status="submitted",
        with_reservation=True,
        product_name="Payment Product",
        sku_prefix="PAY-SKU",
    )
    db.commit()
    return int(graph["order_id"])


def create_retryable_payment(
    db,
    *,
    order_id: int,
    method: str,
    status: str,
    provider_payload: dict | None = None,
) -> int:
    payment = Payment(
        order_id=int(order_id),
        method=method,
        status=status,
        amount=10000,
        currency="ARS",
        idempotency_key=f"{method}-{status}-{datetime.now(UTC).timestamp()}",
        external_ref=f"{method}-ref-{datetime.now(UTC).timestamp()}",
        provider_status=status,
        provider_payload=json.dumps(provider_payload) if provider_payload is not None else None,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        paid_at=None,
    )
    db.add(payment)
    db.commit()
    return int(payment.id)


def create_payment_incident(db) -> int:
    customer = create_user(
        db,
        first_name="Jane",
        last_name="Customer",
        email_prefix="customer",
        phone="1122334455",
        has_account=False,
    )

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


def create_public_mercadopago_payment_graph(
    db,
    *,
    status: str = "pending",
    order_status: str | None = None,
    checkout_url: str | None = None,
) -> dict[str, int | str]:
    customer = create_user(
        db,
        first_name="Pay",
        last_name="Lookup",
        email_prefix="lookup",
        phone="1122334455",
        has_account=False,
    )

    order = Order(
        user_id=int(customer.id),
        status=order_status or ("submitted" if status != "paid" else "paid"),
        currency="ARS",
        subtotal=10000,
        discount_total=0,
        total_amount=10000,
        pricing_frozen=True,
        submitted_at=datetime.now(UTC),
        paid_at=datetime.now(UTC) if status == "paid" else None,
    )
    db.add(order)
    db.flush()

    provider_payload = None
    if checkout_url is not None:
        provider_payload = json.dumps(
            {
                "checkout": {
                    "checkout_url": checkout_url,
                }
            }
        )

    payment = Payment(
        order_id=int(order.id),
        method="mercadopago",
        status=status,
        amount=10000,
        currency="ARS",
        idempotency_key=f"idemp-public-{datetime.now(UTC).timestamp()}",
        external_ref=f"mp-order-{order.id}-pay-public",
        preference_id=f"pref-public-{datetime.now(UTC).timestamp()}",
        provider_status="approved" if status == "paid" else "pending",
        provider_payload=provider_payload,
        expires_at=None,
        paid_at=datetime.now(UTC) if status == "paid" else None,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {
        "order_id": int(order.id),
        "payment_id": int(payment.id),
        "public_status_token": str(payment.public_status_token),
    }


def create_public_mercadopago_payment(db, *, status: str = "pending") -> str:
    graph = create_public_mercadopago_payment_graph(db, status=status)
    return str(graph["public_status_token"])


def build_create_payment_payload(*, method: str, currency: str = "ARS") -> dict[str, str]:
    return {"method": method, "currency": currency}


def build_resolve_refund_payload(*, reason: str, amount: int | None = None) -> dict[str, int | str]:
    payload: dict[str, int | str] = {"reason": reason}
    if amount is not None:
        payload["amount"] = amount
    return payload
