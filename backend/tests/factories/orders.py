from datetime import UTC, datetime, timedelta

from source.db.models import (
    Category,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductVariant,
    StockReservation,
)


def create_order_graph(
    db,
    *,
    user_id: int,
    order_status: str = "submitted",
    item_qty: int = 1,
    variant_stock: int = 10,
    price: int = 10000,
    with_reservation: bool = False,
    reservation_status: str = "active",
    reservation_expires_at=None,
    add_pending_payment: bool = False,
    payment_method: str = "bank_transfer",
    payment_status: str = "pending",
    payment_provider_status: str = "pending",
    payment_expires_at=None,
    category_name: str | None = None,
    product_name: str = "Test Product",
    sku_prefix: str = "SKU",
) -> dict[str, int]:
    timestamp = datetime.now(UTC).timestamp()

    category = Category(name=category_name or f"cat-{timestamp}")
    db.add(category)
    db.flush()

    product = Product(name=product_name, description=None, category_id=int(category.id))
    db.add(product)
    db.flush()

    variant = ProductVariant(
        product_id=int(product.id),
        sku=f"{sku_prefix}-{timestamp}",
        size="M",
        color="Blue",
        price=price,
        stock=variant_stock,
        is_active=True,
    )
    db.add(variant)
    db.flush()

    total_amount = price * item_qty
    order = Order(
        user_id=int(user_id),
        status=order_status,
        currency="ARS",
        subtotal=total_amount,
        discount_total=0,
        total_amount=total_amount,
        pricing_frozen=order_status != "draft",
        submitted_at=datetime.now(UTC) if order_status in {"submitted", "paid"} else None,
        paid_at=datetime.now(UTC) if order_status == "paid" else None,
        cancelled_at=datetime.now(UTC) if order_status == "cancelled" else None,
    )
    db.add(order)
    db.flush()

    item = OrderItem(
        order_id=int(order.id),
        product_id=int(product.id),
        variant_id=int(variant.id),
        quantity=item_qty,
        unit_price=price,
        discount_id=None,
        discount_amount=0,
        final_unit_price=price,
        line_total=total_amount,
    )
    db.add(item)
    db.flush()

    result = {
        "category_id": int(category.id),
        "product_id": int(product.id),
        "variant_id": int(variant.id),
        "order_id": int(order.id),
        "order_item_id": int(item.id),
    }

    if with_reservation:
        reservation = StockReservation(
            order_id=int(order.id),
            order_item_id=int(item.id),
            variant_id=int(variant.id),
            quantity=item_qty,
            status=reservation_status,
            expires_at=reservation_expires_at
            or (datetime.now(UTC) + timedelta(hours=1)),
            reason=None,
        )
        db.add(reservation)
        db.flush()
        result["reservation_id"] = int(reservation.id)

    if add_pending_payment:
        payment = Payment(
            order_id=int(order.id),
            method=payment_method,
            status=payment_status,
            amount=total_amount,
            currency="ARS",
            idempotency_key=f"{payment_method}-{datetime.now(UTC).timestamp()}",
            external_ref=None,
            provider_status=payment_provider_status,
            provider_payload=None,
            expires_at=payment_expires_at or (datetime.now(UTC) + timedelta(hours=1)),
            paid_at=None,
        )
        db.add(payment)
        db.flush()
        result["payment_id"] = int(payment.id)

    return result
