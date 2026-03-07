from __future__ import annotations

from datetime import datetime, timedelta, UTC

from sqlalchemy import func
from sqlalchemy.orm import Session

from source.db.models import Order, OrderItem, Payment, ProductVariant, StockReservation
from source.services.domain_events_s import publish_domain_event

RESERVATION_TTL_HOURS = 42
RESERVATION_REACTIVATION_TTL_HOURS = 12
MAX_RESERVATION_REACTIVATIONS = 1
RESERVATION_ACTIVE = "active"
RESERVATION_CONSUMED = "consumed"
RESERVATION_RELEASED = "released"
RESERVATION_EXPIRED = "expired"


def _reservation_to_dict(reservation: StockReservation) -> dict:
    return {
        "id": reservation.id,
        "order_id": reservation.order_id,
        "order_item_id": reservation.order_item_id,
        "variant_id": reservation.variant_id,
        "quantity": int(reservation.quantity),
        "status": reservation.status,
        "reactivation_count": int(reservation.reactivation_count or 0),
        "expires_at": reservation.expires_at,
        "consumed_at": reservation.consumed_at,
        "released_at": reservation.released_at,
        "reason": reservation.reason,
        "created_at": reservation.created_at,
        "updated_at": reservation.updated_at,
    }


def _lock_order_items_for_order(order_id: int, db: Session) -> tuple[Order, list[OrderItem]]:
    order = db.query(Order).filter(Order.id == order_id).with_for_update().first()
    if order is None:
        raise LookupError("order not found")

    items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order_id)
        .order_by(OrderItem.id.asc())
        .with_for_update()
        .all()
    )
    if not items:
        raise ValueError("order has no items")
    return order, items


def _get_active_reservation_by_item(order_item_id: int, db: Session) -> StockReservation | None:
    return (
        db.query(StockReservation)
        .filter(
            StockReservation.order_item_id == order_item_id,
            StockReservation.status == RESERVATION_ACTIVE,
        )
        .with_for_update()
        .first()
    )


def _available_stock_for_variant(
    variant_id: int,
    db: Session,
    *,
    now: datetime,
) -> tuple[ProductVariant, int]:
    variant = (
        db.query(ProductVariant)
        .filter(
            ProductVariant.id == variant_id,
            ProductVariant.is_active.is_(True),
        )
        .with_for_update()
        .first()
    )
    if variant is None:
        raise ValueError(f"variant {variant_id} not found")

    reserved_qty = (
        db.query(func.coalesce(func.sum(StockReservation.quantity), 0))
        .filter(
            StockReservation.variant_id == variant_id,
            StockReservation.status == RESERVATION_ACTIVE,
            StockReservation.expires_at > now,
        )
        .scalar()
    )
    available = int(variant.stock) - int(reserved_qty or 0)
    return variant, max(0, available)


def _cancel_pending_payments_for_order(order_id: int, *, now: datetime, db: Session) -> None:
    db.query(Payment).filter(
        Payment.order_id == order_id,
        Payment.status == "pending",
    ).update(
        {
            Payment.status: "cancelled",
            Payment.provider_status: "order_cancelled_reservation_expired",
            Payment.updated_at: now,
        },
        synchronize_session=False,
    )


def expire_active_reservations(now: datetime, db: Session, *, limit: int | None = None) -> int:
    return _expire_active_reservations_internal(now=now, db=db, order_id=None, limit=limit)


def expire_active_reservations_for_order(*, order_id: int, now: datetime, db: Session) -> int:
    return _expire_active_reservations_internal(now=now, db=db, order_id=order_id)


def _expire_active_reservations_internal(
    *,
    now: datetime,
    db: Session,
    order_id: int | None,
    limit: int | None = None,
    ) -> int:
    query = (
        db.query(StockReservation)
        .filter(
            StockReservation.status == RESERVATION_ACTIVE,
            StockReservation.expires_at <= now,
        )
        .order_by(StockReservation.order_id.asc(), StockReservation.id.asc())
        .with_for_update()
    )
    if order_id is not None:
        query = query.filter(StockReservation.order_id == order_id)
    if limit is not None:
        query = query.limit(max(1, int(limit)))
    expiring_reservations = query.all()
    if not expiring_reservations:
        return 0

    expired_count = 0
    reservations_by_order: dict[int, list[StockReservation]] = {}
    for reservation in expiring_reservations:
        reservations_by_order.setdefault(int(reservation.order_id), []).append(reservation)

    for order_id, reservations in reservations_by_order.items():
        order, items = _lock_order_items_for_order(order_id=order_id, db=db)

        for reservation in reservations:
            reservation.status = RESERVATION_EXPIRED
            reservation.released_at = now
            reservation.reason = "reservation_expired"

        if order.status != "submitted":
            expired_count += len(reservations)
            continue

        can_reactivate_by_policy = all(
            int(reservation.reactivation_count or 0) < MAX_RESERVATION_REACTIVATIONS
            for reservation in reservations
        )
        if not can_reactivate_by_policy:
            if order.status != "cancelled":
                order.status = "cancelled"
            if order.cancelled_at is None:
                order.cancelled_at = now
            publish_domain_event(
                event_type="order_cancelled",
                payload={
                    "order_id": int(order_id),
                    "user_id": int(order.user_id) if order.user_id is not None else None,
                    "reason": "expiracion de reserva",
                },
                db=db,
            )
            _cancel_pending_payments_for_order(order_id=order_id, now=now, db=db)
            expired_count += len(reservations)
            continue

        can_reactivate_all = True
        for item in items:
            _, available = _available_stock_for_variant(
                variant_id=int(item.variant_id),
                db=db,
                now=now,
            )
            if available < int(item.quantity):
                can_reactivate_all = False
                break

        if can_reactivate_all:
            renewed_expires_at = now + timedelta(hours=RESERVATION_REACTIVATION_TTL_HOURS)
            for reservation in reservations:
                reservation.status = RESERVATION_ACTIVE
                reservation.reactivation_count = int(reservation.reactivation_count or 0) + 1
                reservation.expires_at = renewed_expires_at
                reservation.released_at = None
                reservation.consumed_at = None
                reservation.reason = None
            continue

        if order.status != "cancelled":
            order.status = "cancelled"
        if order.cancelled_at is None:
            order.cancelled_at = now
        publish_domain_event(
            event_type="order_cancelled",
            payload={
                "order_id": int(order_id),
                "user_id": int(order.user_id) if order.user_id is not None else None,
                "reason": "expiracion de reserva",
            },
            db=db,
        )
        _cancel_pending_payments_for_order(order_id=order_id, now=now, db=db)
        expired_count += len(reservations)

    db.flush()
    return int(expired_count)


def reserve_stock_for_submitted_order(order_id: int, db: Session) -> list[dict]:
    now = datetime.now(UTC)
    expire_active_reservations_for_order(order_id=order_id, now=now, db=db)
    order, items = _lock_order_items_for_order(order_id=order_id, db=db)
    if order.status not in {"draft", "submitted"}:
        raise ValueError("stock can only be reserved for draft/submitted orders")

    existing_active = (
        db.query(StockReservation)
        .filter(
            StockReservation.order_id == order_id,
            StockReservation.status == RESERVATION_ACTIVE,
        )
        .order_by(StockReservation.id.asc())
        .with_for_update()
        .all()
    )
    if existing_active and len(existing_active) == len(items):
        return [_reservation_to_dict(reservation) for reservation in existing_active]

    # First pass validates stock availability for all missing reservations.
    missing_items: list[OrderItem] = []
    for item in items:
        if _get_active_reservation_by_item(order_item_id=item.id, db=db) is not None:
            continue
        _, available = _available_stock_for_variant(
            variant_id=int(item.variant_id),
            db=db,
            now=now,
        )
        if available < int(item.quantity):
            raise ValueError(f"insufficient stock for variant {item.variant_id}")
        missing_items.append(item)

    expires_at = now + timedelta(hours=RESERVATION_TTL_HOURS)
    for item in missing_items:
        db.add(
            StockReservation(
                order_id=order_id,
                order_item_id=int(item.id),
                variant_id=int(item.variant_id),
                quantity=int(item.quantity),
                status=RESERVATION_ACTIVE,
                reactivation_count=0,
                expires_at=expires_at,
                reason=None,
            )
        )
    db.flush()

    active = (
        db.query(StockReservation)
        .filter(
            StockReservation.order_id == order_id,
            StockReservation.status == RESERVATION_ACTIVE,
        )
        .order_by(StockReservation.id.asc())
        .all()
    )
    return [_reservation_to_dict(reservation) for reservation in active]


def consume_reservations_for_paid_order(order_id: int, db: Session) -> list[dict]:
    now = datetime.now(UTC)
    expire_active_reservations_for_order(order_id=order_id, now=now, db=db)
    order, _ = _lock_order_items_for_order(order_id=order_id, db=db)
    if order.status not in {"submitted", "paid"}:
        raise ValueError("order can only be paid from submitted status")

    active_reservations = (
        db.query(StockReservation)
        .filter(
            StockReservation.order_id == order_id,
            StockReservation.status == RESERVATION_ACTIVE,
        )
        .order_by(StockReservation.id.asc())
        .with_for_update()
        .all()
    )

    if not active_reservations:
        consumed = (
            db.query(StockReservation)
            .filter(
                StockReservation.order_id == order_id,
                StockReservation.status == RESERVATION_CONSUMED,
            )
            .order_by(StockReservation.id.asc())
            .all()
        )
        if consumed and order.status == "paid":
            return [_reservation_to_dict(reservation) for reservation in consumed]
        raise ValueError("no active reservations for order")

    for reservation in active_reservations:
        updated = (
            db.query(ProductVariant)
            .filter(
                ProductVariant.id == reservation.variant_id,
                ProductVariant.stock >= int(reservation.quantity),
            )
            .update(
                {ProductVariant.stock: ProductVariant.stock - int(reservation.quantity)},
                synchronize_session=False,
            )
        )
        if int(updated or 0) != 1:
            raise ValueError(f"insufficient stock for variant {reservation.variant_id}")

        reservation.status = RESERVATION_CONSUMED
        reservation.consumed_at = now
        reservation.reason = "order_paid"

    db.flush()
    return [_reservation_to_dict(reservation) for reservation in active_reservations]


def release_reservations_for_cancelled_order(
    order_id: int,
    reason: str,
    db: Session,
) -> int:
    now = datetime.now(UTC)
    expire_active_reservations_for_order(order_id=order_id, now=now, db=db)
    _, _ = _lock_order_items_for_order(order_id=order_id, db=db)
    active_reservations = (
        db.query(StockReservation)
        .filter(
            StockReservation.order_id == order_id,
            StockReservation.status == RESERVATION_ACTIVE,
        )
        .with_for_update()
        .all()
    )
    for reservation in active_reservations:
        reservation.status = RESERVATION_RELEASED
        reservation.released_at = now
        reservation.reason = reason
    if active_reservations:
        db.flush()
    return len(active_reservations)


def list_active_reservations_for_order(order_id: int, db: Session) -> list[dict]:
    now = datetime.now(UTC)
    expire_active_reservations_for_order(order_id=order_id, now=now, db=db)
    rows = (
        db.query(StockReservation)
        .filter(
            StockReservation.order_id == order_id,
            StockReservation.status == RESERVATION_ACTIVE,
        )
        .order_by(StockReservation.id.asc())
        .all()
    )
    return [_reservation_to_dict(row) for row in rows]


def list_reservations_for_order(order_id: int, db: Session) -> list[dict]:
    now = datetime.now(UTC)
    expire_active_reservations_for_order(order_id=order_id, now=now, db=db)
    rows = (
        db.query(StockReservation)
        .filter(StockReservation.order_id == order_id)
        .order_by(StockReservation.id.asc())
        .all()
    )
    return [_reservation_to_dict(row) for row in rows]

