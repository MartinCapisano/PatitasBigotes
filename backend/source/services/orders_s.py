from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session, joinedload

from source.db.models import Order, OrderItem, ProductVariant, User
from source.exceptions import (
    OrderStatusTransitionError,
    RegisteredAccountCheckoutConflictError,
)
from source.services.discount_s import (
    calculate_line_pricing,
    list_discounts,
    reprice_order_items,
    validate_order_pricing_before_submit,
)
from source.services.payment_s import (
    confirm_manual_payment_for_order,
    list_payments_for_orders,
)
from source.services.products_s import list_products_by_ids
from source.services.stock_reservations_s import (
    expire_active_reservations_for_order,
    list_reservations_for_order,
    release_reservations_for_cancelled_order,
    reserve_stock_for_submitted_order,
)
from source.services.domain_events_s import publish_domain_event
from source.services.post_commit_actions_s import set_skip_order_paid_email
from source.services.users_s import get_or_create_user_by_contact, serialize_user_basic

ALLOWED_ORDER_STATUS = {"draft", "submitted", "paid", "cancelled"}
ORDER_TERMINAL_STATUSES = {"paid", "cancelled"}
ORDER_ALLOWED_TRANSITIONS = {
    "draft": {"draft", "submitted"},
    "submitted": {"submitted", "cancelled"},
    "paid": {"paid"},
    "cancelled": {"cancelled"},
}

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _validate_order_transition(*, current_status: str, new_status: str) -> None:
    allowed = ORDER_ALLOWED_TRANSITIONS.get(current_status, set())
    if new_status in allowed:
        return
    if current_status in ORDER_TERMINAL_STATUSES:
        raise OrderStatusTransitionError(
            f"cannot transition terminal order from {current_status} to {new_status}"
        )
    raise OrderStatusTransitionError(f"invalid transition {current_status} -> {new_status}")


def _assert_transition_preconditions(
    *,
    order: Order,
    new_status: str,
) -> None:
    if new_status not in ALLOWED_ORDER_STATUS:
        raise ValueError("invalid status")

    if new_status == "paid":
        raise ValueError("paid status must be set through a payment endpoint")

    if order.status == "draft" and new_status != "draft" and not order.items:
        raise ValueError("cannot leave draft with an empty order")


def _order_query(db: Session):
    return db.query(Order).options(
        joinedload(Order.user),
        joinedload(Order.items).joinedload(OrderItem.variant),
        joinedload(Order.items).joinedload(OrderItem.product),
    )


def _order_lock_query(db: Session):
    return db.query(Order)


def _variant_label(variant: ProductVariant | None) -> str:
    if variant is None:
        return "-/-"
    return f"{variant.size or '-'}/{variant.color or '-'}"


def _order_to_dict(order: Order) -> dict:
    items = []
    for item in sorted(order.items, key=lambda x: x.id):
        items.append(
            {
                "id": item.id,
                "product_id": item.product_id,
                "variant_id": item.variant_id,
                "product_name": item.product.name if item.product is not None else None,
                "variant_label": _variant_label(item.variant),
                "quantity": int(item.quantity),
                "unit_price": int(item.unit_price),
                "discount_id": item.discount_id,
                "discount_amount": int(item.discount_amount or 0),
                "final_unit_price": int(item.final_unit_price or 0),
                "line_total": int(item.line_total or 0),
            }
        )

    return {
        "id": order.id,
        "user_id": order.user_id,
        "customer": serialize_user_basic(order.user) if order.user is not None else None,
        "status": order.status,
        "currency": order.currency,
        "items": items,
        "subtotal": int(order.subtotal or 0),
        "discount_total": int(order.discount_total or 0),
        "total_amount": int(order.total_amount or 0),
        "pricing_frozen": bool(order.pricing_frozen),
        "pricing_frozen_at": order.pricing_frozen_at,
        "submitted_at": order.submitted_at,
        "paid_at": order.paid_at,
        "cancelled_at": order.cancelled_at,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def _recalculate_order_total(order: Order, db: Session, *, force: bool = False) -> None:
    if bool(order.pricing_frozen) and not force:
        raise ValueError("cannot recalculate a frozen order")

    order_payload = {
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "variant_id": item.variant_id,
                "quantity": int(item.quantity),
                "unit_price": int(item.unit_price),
                "discount_id": item.discount_id,
                "discount_amount": int(item.discount_amount or 0),
                "final_unit_price": int(item.final_unit_price or 0),
                "line_total": int(item.line_total or 0),
            }
            for item in order.items
        ],
        "subtotal": int(order.subtotal or 0),
        "discount_total": int(order.discount_total or 0),
        "total_amount": int(order.total_amount or 0),
        "pricing_frozen": bool(order.pricing_frozen),
    }

    products_by_id = list_products_by_ids(
        [item["product_id"] for item in order_payload["items"]], db=db
    )

    reprice_order_items(
        order=order_payload,
        discounts=list_discounts(db=db),
        products_by_id=products_by_id,
    )

    item_by_id = {item.id: item for item in order.items}
    for item_payload in order_payload["items"]:
        item = item_by_id.get(int(item_payload["id"]))
        if item is None:
            continue
        item.discount_id = item_payload.get("discount_id")
        item.discount_amount = int(item_payload.get("discount_amount", 0))
        item.final_unit_price = int(item_payload.get("final_unit_price", 0))
        item.line_total = int(item_payload.get("line_total", 0))

    order.subtotal = int(order_payload.get("subtotal", 0))
    order.discount_total = int(order_payload.get("discount_total", 0))
    order.total_amount = int(order_payload.get("total_amount", 0))


def _normalize_requested_items(items: list[dict]) -> dict[int, int]:
    aggregated_items: dict[int, int] = {}
    for item in items:
        variant_id = int(item["variant_id"])
        quantity = int(item["quantity"])
        if quantity <= 0:
            raise ValueError("quantity must be greater than 0")
        aggregated_items[variant_id] = aggregated_items.get(variant_id, 0) + quantity
    return aggregated_items


def _build_order_item_fields(*, variant: ProductVariant, quantity: int) -> dict:
    pricing = calculate_line_pricing(
        unit_price=int(variant.price),
        quantity=quantity,
        discount=None,
    )
    return {
        "product_id": variant.product_id,
        "variant_id": variant.id,
        "quantity": quantity,
        "unit_price": pricing["unit_price"],
        "discount_id": pricing["discount_id"],
        "discount_amount": pricing["discount_amount"],
        "final_unit_price": pricing["final_unit_price"],
        "line_total": pricing["line_total"],
    }


def get_draft_order(user_id: int, db: Session) -> dict | None:
    draft = (
        _order_query(db)
        .filter(
            Order.user_id == user_id,
            Order.status == "draft",
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
        .first()
    )
    if draft is None:
        return None
    return _order_to_dict(draft)


def get_or_create_draft_order(user_id: int, db: Session) -> tuple[dict, bool]:
    draft = get_draft_order(user_id=user_id, db=db)
    if draft is not None:
        return draft, False

    created = Order(
        user_id=user_id,
        status="draft",
        currency="ARS",
        subtotal=0,
        discount_total=0,
        total_amount=0,
        pricing_frozen=False,
    )
    db.add(created)
    db.flush()
    db.refresh(created)
    return _order_to_dict(created), True


def _get_or_create_draft_order_model(user_id: int, db: Session) -> tuple[Order, bool]:
    draft = (
        _order_lock_query(db)
        .filter(
            Order.user_id == user_id,
            Order.status == "draft",
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
        .with_for_update()
        .first()
    )
    if draft is not None:
        return draft, False

    draft = Order(
        user_id=user_id,
        status="draft",
        currency="ARS",
        subtotal=0,
        discount_total=0,
        total_amount=0,
        pricing_frozen=False,
    )
    db.add(draft)
    db.flush()
    db.refresh(draft)
    return draft, True


def get_order_for_user(user_id: int, order_id: int, db: Session) -> dict | None:
    order = (
        _order_query(db)
        .filter(
            Order.id == order_id,
            Order.user_id == user_id,
        )
        .first()
    )
    if order is None:
        return None
    return _order_to_dict(order)


def list_orders_for_user(user_id: int, db: Session) -> list[dict]:
    orders = (
        _order_query(db)
        .filter(Order.user_id == user_id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )
    return [_order_to_dict(order) for order in orders]


def list_orders_with_payments_for_user(user_id: int, db: Session) -> dict:
    orders = list_orders_for_user(user_id, db=db)
    payments_by_order_id = list_payments_for_orders([order["id"] for order in orders], db=db)
    return {"orders": orders, "payments_by_order_id": payments_by_order_id}


def get_order_for_admin(order_id: int, db: Session) -> dict | None:
    order = _order_query(db).filter(Order.id == order_id).first()
    if order is None:
        return None
    return _order_to_dict(order)


def list_orders_for_admin(
    *,
    status: str | None,
    limit: int,
    sort_by: str,
    sort_dir: str,
    db: Session,
) -> list[dict]:
    safe_limit = max(1, min(int(limit), 500))
    query = _order_query(db)
    if status is not None:
        normalized_status = status.strip().lower()
        if normalized_status not in ALLOWED_ORDER_STATUS:
            raise ValueError("invalid status")
        query = query.filter(Order.status == normalized_status)

    if sort_by not in {"created_at", "id"}:
        raise ValueError("invalid sort_by")
    if sort_dir not in {"asc", "desc"}:
        raise ValueError("invalid sort_dir")

    sort_column = Order.created_at if sort_by == "created_at" else Order.id
    if sort_dir == "asc":
        query = query.order_by(sort_column.asc(), Order.id.asc())
    else:
        query = query.order_by(sort_column.desc(), Order.id.desc())

    rows = query.limit(safe_limit).all()
    return [_order_to_dict(order) for order in rows]


def replace_draft_order_items(user_id: int, items: list[dict], db: Session) -> dict:
    order, _ = _get_or_create_draft_order_model(user_id=user_id, db=db)
    if order.status != "draft":
        raise ValueError("items can only be edited in draft status")

    aggregated_items = _normalize_requested_items(items)
    requested_variant_ids = list(aggregated_items.keys())

    variants_by_id: dict[int, ProductVariant] = {}
    if requested_variant_ids:
        variants = (
            db.query(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .filter(
                ProductVariant.id.in_(requested_variant_ids),
                ProductVariant.is_active.is_(True),
            )
            .all()
        )
        variants_by_id = {int(variant.id): variant for variant in variants}
        missing_variant_ids = sorted(
            variant_id for variant_id in requested_variant_ids if variant_id not in variants_by_id
        )
        if missing_variant_ids:
            if len(missing_variant_ids) == 1:
                raise ValueError(f"variant {missing_variant_ids[0]} not found")
            raise ValueError("some variants were not found")

    (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order.id)
        .delete(synchronize_session=False)
    )

    for variant_id, quantity in aggregated_items.items():
        variant = variants_by_id[variant_id]
        item_fields = _build_order_item_fields(variant=variant, quantity=quantity)
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item_fields["product_id"],
                variant_id=item_fields["variant_id"],
                quantity=item_fields["quantity"],
                unit_price=item_fields["unit_price"],
                discount_id=item_fields["discount_id"],
                discount_amount=item_fields["discount_amount"],
                final_unit_price=item_fields["final_unit_price"],
                line_total=item_fields["line_total"],
            )
        )

    db.flush()
    db.refresh(order)
    _recalculate_order_total(order, db=db)
    db.flush()
    db.refresh(order)
    return _order_to_dict(order)


def change_order_status(
    user_id: int,
    order_id: int,
    new_status: str,
    db: Session,
    *,
    is_admin: bool = False,
) -> dict:
    expire_active_reservations_for_order(order_id=order_id, now=_utc_now(), db=db)

    order_filter = [Order.id == order_id]
    if not is_admin:
        order_filter.append(Order.user_id == user_id)

    order = (
        _order_lock_query(db)
        .filter(*order_filter)
        .with_for_update()
        .first()
    )
    if order is None:
        raise LookupError("order not found")
    current_status = str(order.status)
    logger.info(
        "event=order_status_transition_attempt order_id=%s user_id=%s is_admin=%s from=%s to=%s",
        int(order.id),
        int(user_id),
        bool(is_admin),
        current_status,
        str(new_status),
    )
    try:
        _assert_transition_preconditions(
            order=order,
            new_status=new_status,
        )
        _validate_order_transition(current_status=current_status, new_status=new_status)
    except Exception as exc:
        logger.warning(
            "event=order_status_transition_rejected order_id=%s user_id=%s is_admin=%s from=%s to=%s reason=%s",
            int(order.id),
            int(user_id),
            bool(is_admin),
            current_status,
            str(new_status),
            str(exc),
        )
        raise

    if order.status == new_status:
        logger.info(
            "event=order_status_transition_applied order_id=%s user_id=%s is_admin=%s from=%s to=%s",
            int(order.id),
            int(user_id),
            bool(is_admin),
            current_status,
            str(new_status),
        )
        return _order_to_dict(order)

    if order.status == "draft" and new_status == "submitted":
        _recalculate_order_total(order, db=db, force=True)
        validate_order_pricing_before_submit(_order_to_dict(order))
        reserve_stock_for_submitted_order(order_id=order.id, db=db)
        order.pricing_frozen = True
        if order.pricing_frozen_at is None:
            order.pricing_frozen_at = _utc_now()
        if order.submitted_at is None:
            order.submitted_at = _utc_now()

    if new_status == "cancelled":
        release_reservations_for_cancelled_order(
            order_id=order.id,
            reason="order_cancelled",
            db=db,
        )
        if order.cancelled_at is None:
            order.cancelled_at = _utc_now()

    order.status = new_status
    db.flush()
    db.refresh(order)
    if current_status != str(order.status):
        if str(order.status) == "submitted":
            publish_domain_event(
                event_type="order_submitted",
                payload={
                    "order_id": int(order.id),
                    "user_id": int(order.user_id) if order.user_id is not None else None,
                },
                db=db,
            )
        elif str(order.status) == "cancelled":
            publish_domain_event(
                event_type="order_cancelled",
                payload={
                    "order_id": int(order.id),
                    "user_id": int(order.user_id) if order.user_id is not None else None,
                    "reason": None,
                },
                db=db,
            )
    logger.info(
        "event=order_status_transition_applied order_id=%s user_id=%s is_admin=%s from=%s to=%s",
        int(order.id),
        int(user_id),
        bool(is_admin),
        current_status,
        str(order.status),
    )
    return _order_to_dict(order)


def _create_submitted_order_for_user(
    *,
    user_id: int,
    items: list[dict],
    db: Session,
) -> dict:
    if not items:
        raise ValueError("items are required")

    order = Order(
        user_id=int(user_id),
        status="draft",
        currency="ARS",
        subtotal=0,
        discount_total=0,
        total_amount=0,
        pricing_frozen=False,
    )
    db.add(order)
    db.flush()

    aggregated_items = _normalize_requested_items(items)

    for variant_id, quantity in aggregated_items.items():
        variant = (
            db.query(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .filter(
                ProductVariant.id == variant_id,
                ProductVariant.is_active.is_(True),
            )
            .first()
        )
        if variant is None:
            raise ValueError(f"variant {variant_id} not found")
        item_fields = _build_order_item_fields(variant=variant, quantity=quantity)

        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item_fields["product_id"],
                variant_id=item_fields["variant_id"],
                quantity=item_fields["quantity"],
                unit_price=item_fields["unit_price"],
                discount_id=item_fields["discount_id"],
                discount_amount=item_fields["discount_amount"],
                final_unit_price=item_fields["final_unit_price"],
                line_total=item_fields["line_total"],
            )
        )

    db.flush()
    db.refresh(order)
    _recalculate_order_total(order, db=db, force=True)
    validate_order_pricing_before_submit(_order_to_dict(order))
    reserve_stock_for_submitted_order(order_id=order.id, db=db)
    order.pricing_frozen = True
    if order.pricing_frozen_at is None:
        order.pricing_frozen_at = _utc_now()
    if order.submitted_at is None:
        order.submitted_at = _utc_now()
    order.status = "submitted"
    db.flush()
    db.refresh(order)
    publish_domain_event(
        event_type="order_submitted",
        payload={
            "order_id": int(order.id),
            "user_id": int(order.user_id) if order.user_id is not None else None,
        },
        db=db,
    )
    return _order_to_dict(order)


def create_manual_submitted_order(
    *,
    email: str,
    first_name: str,
    last_name: str,
    phone: str,
    items: list[dict],
    db: Session,
) -> dict:
    if not items:
        raise ValueError("items are required")

    normalized_email = str(email or "").strip().lower()
    existing_auth_user = (
        db.query(User)
        .filter(
            User.email == normalized_email,
            User.has_account.is_(True),
        )
        .first()
    )
    if existing_auth_user is not None:
        raise RegisteredAccountCheckoutConflictError(
            "registered account requires login"
        )

    user, user_created = get_or_create_user_by_contact(
        email=email,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        db=db,
    )

    order_payload = _create_submitted_order_for_user(
        user_id=int(user.id),
        items=items,
        db=db,
    )

    return {
        "customer": serialize_user_basic(user),
        "order": order_payload,
        "meta": {"user_created": user_created},
    }


def create_admin_sale(
    *,
    admin_user_id: int,
    customer: dict,
    items: list[dict],
    register_payment: bool,
    payment: dict | None,
    db: Session,
) -> dict:
    if not items:
        raise ValueError("items are required")
    mode = str(customer.get("mode") or "").strip().lower()
    if mode not in {"existing", "new"}:
        raise ValueError("customer.mode must be 'existing' or 'new'")

    selected_user: User | None = None
    user_created = False
    if mode == "existing":
        selected_user_id = customer.get("user_id")
        if selected_user_id is None:
            raise ValueError("customer.user_id is required when mode is existing")
        selected_user = db.query(User).filter(User.id == int(selected_user_id)).first()
        if selected_user is None:
            raise LookupError("user not found")
        for field in ("first_name", "last_name", "email", "phone", "dni"):
            if customer.get(field) not in (None, ""):
                raise ValueError(
                    f"customer.{field} is not allowed when mode is existing"
                )
    else:
        first_name = str(customer.get("first_name") or "").strip()
        last_name = str(customer.get("last_name") or "").strip()
        email = str(customer.get("email") or "").strip()
        phone = str(customer.get("phone") or "").strip()
        dni = customer.get("dni")
        if not first_name or not last_name or not email or not phone:
            raise ValueError(
                "first_name, last_name, email and phone are required when mode is new"
            )
        selected_user, user_created = get_or_create_user_by_contact(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            dni=str(dni).strip() if dni not in (None, "") else None,
            db=db,
        )

    assert selected_user is not None
    order_payload = _create_submitted_order_for_user(
        user_id=int(selected_user.id),
        items=items,
        db=db,
    )

    payment_payload = None
    if register_payment:
        if payment is None:
            raise ValueError("payment is required when register_payment is true")
        method = str(payment.get("method") or "").strip().lower()
        if method not in {"cash", "bank_transfer"}:
            raise ValueError("payment.method must be cash or bank_transfer")
        amount_paid = payment.get("amount_paid")
        if amount_paid is None:
            raise ValueError("payment.amount_paid is required")
        change_amount = payment.get("change_amount")
        payment_ref = str(payment.get("payment_ref") or "").strip()
        if method == "bank_transfer" and not payment_ref:
            raise ValueError("payment.payment_ref is required for bank_transfer")
        if method == "cash" and not payment_ref:
            payment_ref = f"cash-order-{int(order_payload['id'])}-{_utc_now().strftime('%Y%m%d%H%M%S')}"
        previous_skip_value = bool(db.info.get("skip_order_paid_email", False))
        set_skip_order_paid_email(db=db, value=True)
        try:
            payment_payload = confirm_manual_payment_for_order(
                order_id=int(order_payload["id"]),
                user_id=int(selected_user.id),
                payment_ref=payment_ref,
                paid_amount=int(amount_paid),
                method=method,
                change_amount=int(change_amount) if change_amount is not None else None,
                # In-person admin sales create the order and collect payment in
                # one flow, so there may be no pending payment to confirm yet.
                allow_create_if_missing=True,
                db=db,
            )
        finally:
            set_skip_order_paid_email(db=db, value=previous_skip_value)
        order_after_payment = get_order_for_admin(order_id=int(order_payload["id"]), db=db)
        if order_after_payment is not None:
            order_payload = order_after_payment
    elif payment is not None:
        raise ValueError("payment must be null when register_payment is false")

    logger.info(
        "event=admin_sale_created admin_user_id=%s order_id=%s customer_mode=%s register_payment=%s payment_method=%s",
        int(admin_user_id),
        int(order_payload["id"]),
        mode,
        bool(register_payment),
        (payment_payload or {}).get("method"),
    )

    return {
        "customer": serialize_user_basic(selected_user),
        "order": order_payload,
        "payment": payment_payload,
        "meta": {
            "customer_created": bool(user_created),
            "payment_registered": bool(payment_payload is not None),
            "order_paid_email_suppressed": bool(payment_payload is not None),
        },
    }


def get_order_reservations_for_user(
    *,
    user_id: int,
    order_id: int,
    is_admin: bool,
    db: Session,
) -> list[dict]:
    expire_active_reservations_for_order(order_id=order_id, now=_utc_now(), db=db)
    query = _order_query(db).filter(Order.id == order_id)
    if not is_admin:
        query = query.filter(Order.user_id == user_id)
    order = query.first()
    if order is None:
        raise LookupError("order not found")
    return list_reservations_for_order(order_id=order.id, db=db)


