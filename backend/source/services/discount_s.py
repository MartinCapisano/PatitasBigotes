from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, TypedDict

from sqlalchemy import insert
from sqlalchemy.orm import Session, joinedload

from source.db.models import Category, Discount, DiscountProduct, Product
from source.services.money_s import calcular_amount, parse_amount_to_cents

ALLOWED_DISCOUNT_TYPES = {"percent", "fixed"}
ALLOWED_DISCOUNT_SCOPES = {"all", "category", "product", "product_list"}


class DiscountDTO(TypedDict):
    id: int
    name: str
    type: str
    value: int
    scope: str
    category_id: int | None
    product_id: int | None
    is_active: bool
    starts_at: datetime | None
    ends_at: datetime | None
    product_ids: list[int]


def _coerce_datetime(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _normalize_discount_value(discount_type: str, value: object) -> int:
    if value is None:
        raise ValueError("discount value must be greater than 0")
    if discount_type == "percent":
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("discount percent must be an integer") from exc
        if normalized < 1 or normalized > 100:
            raise ValueError("percent discount must be between 1 and 100")
        return normalized
    return parse_amount_to_cents(value if isinstance(value, (int, Decimal)) else str(value))


def _discount_to_dict(discount: Discount) -> DiscountDTO:
    product_ids = [link.product_id for link in discount.product_links]
    return {
        "id": discount.id,
        "name": discount.name,
        "type": discount.type,
        "value": int(discount.value),
        "scope": discount.scope,
        "category_id": None if discount.category_id is None else int(discount.category_id),
        "product_id": None if discount.product_id is None else int(discount.product_id),
        "is_active": bool(discount.is_active),
        "starts_at": discount.starts_at,
        "ends_at": discount.ends_at,
        "product_ids": product_ids,
    }


def list_discounts(db: Session) -> list[DiscountDTO]:
    discounts = (
        db.query(Discount)
        .options(joinedload(Discount.product_links))
        .order_by(Discount.id.asc())
        .all()
    )
    return [_discount_to_dict(discount) for discount in discounts]


def get_discount_by_id(discount_id: int, db: Session) -> DiscountDTO | None:
    discount = (
        db.query(Discount)
        .options(joinedload(Discount.product_links))
        .filter(Discount.id == discount_id)
        .first()
    )
    if discount is None:
        return None
    return _discount_to_dict(discount)


def _set_discount_product_list(db: Session, discount: Discount, product_ids: list[int]) -> None:
    unique_ids = list(dict.fromkeys(product_ids))
    if unique_ids:
        existing_count = (
            db.query(Product.id)
            .filter(Product.id.in_(unique_ids))
            .count()
        )
        if existing_count != len(unique_ids):
            raise ValueError("one or more product_ids do not exist")

    db.query(DiscountProduct).filter(
        DiscountProduct.discount_id == discount.id
    ).delete(synchronize_session=False)
    if unique_ids:
        rows = [{"discount_id": discount.id, "product_id": product_id} for product_id in unique_ids]
        db.execute(insert(DiscountProduct), rows)


def create_discount(payload: dict, db: Session) -> DiscountDTO:
    _validate_discount_payload(payload, db=db)
    normalized_value = _normalize_discount_value(payload["type"], payload["value"])

    discount = Discount(
        name=payload["name"],
        type=payload["type"],
        value=normalized_value,
        scope=payload["scope"],
        category_id=payload.get("category_id"),
        product_id=payload.get("product_id"),
        is_active=bool(payload.get("is_active", True)),
        starts_at=_coerce_datetime(payload.get("starts_at")),
        ends_at=_coerce_datetime(payload.get("ends_at")),
    )
    db.add(discount)
    db.flush()

    if discount.scope == "product_list":
        _set_discount_product_list(
            db=db,
            discount=discount,
            product_ids=payload.get("product_ids", []),
        )

    db.flush()
    db.refresh(discount)
    result = get_discount_by_id(discount.id, db=db)
    if result is None:
        raise LookupError("discount not found")
    return result


def update_discount(discount_id: int, updates: dict, db: Session) -> DiscountDTO | None:
    discount = db.query(Discount).filter(Discount.id == discount_id).first()
    if discount is None:
        return None

    current = get_discount_by_id(discount_id=discount_id, db=db)
    if current is None:
        return None

    merged = {**current, **updates}
    _validate_discount_payload(merged, db=db)
    normalized_value = _normalize_discount_value(merged["type"], merged["value"])

    discount.name = merged["name"]
    discount.type = merged["type"]
    discount.value = normalized_value
    discount.scope = merged["scope"]
    discount.category_id = merged.get("category_id")
    discount.product_id = merged.get("product_id")
    discount.is_active = bool(merged.get("is_active", True))
    discount.starts_at = _coerce_datetime(merged.get("starts_at"))
    discount.ends_at = _coerce_datetime(merged.get("ends_at"))

    if merged["scope"] == "product_list":
        _set_discount_product_list(
            db=db,
            discount=discount,
            product_ids=merged.get("product_ids", []),
        )
    else:
        db.query(DiscountProduct).filter(DiscountProduct.discount_id == discount.id).delete()

    db.flush()
    db.refresh(discount)
    return get_discount_by_id(discount_id, db=db)


def delete_discount(discount_id: int, db: Session) -> DiscountDTO | None:
    discount = (
        db.query(Discount)
        .options(joinedload(Discount.product_links))
        .filter(Discount.id == discount_id)
        .first()
    )
    if discount is None:
        return None
    serialized = _discount_to_dict(discount)
    db.delete(discount)
    db.flush()
    return serialized


def _validate_discount_payload(payload: dict, *, db: Session) -> None:
    discount_type = payload.get("type")
    scope = payload.get("scope")
    value = payload.get("value")
    category_id = payload.get("category_id")
    product_id = payload.get("product_id")
    product_ids = payload.get("product_ids", [])
    starts_at = _coerce_datetime(payload.get("starts_at"))
    ends_at = _coerce_datetime(payload.get("ends_at"))

    if not str(payload.get("name", "")).strip():
        raise ValueError("name is required")
    if discount_type not in ALLOWED_DISCOUNT_TYPES:
        raise ValueError("invalid discount type")
    if scope not in ALLOWED_DISCOUNT_SCOPES:
        raise ValueError("invalid discount scope")
    _normalize_discount_value(discount_type, value)
    if starts_at is not None and ends_at is not None and starts_at > ends_at:
        raise ValueError("starts_at must be before or equal to ends_at")

    if scope == "all":
        if category_id is not None or product_id is not None:
            raise ValueError("category_id and product_id must be null for all scope")
    if scope == "category":
        if category_id is None:
            raise ValueError("category_id is required for category scope")
        if product_id is not None:
            raise ValueError("product_id must be null for category scope")
        exists = (
            db.query(Category.id)
            .filter(Category.id == int(category_id))
            .first()
        )
        if exists is None:
            raise ValueError("category_id does not exist")
    if scope == "product":
        if product_id is None:
            raise ValueError("product_id is required for product scope")
        if category_id is not None:
            raise ValueError("category_id must be null for product scope")
        exists = (
            db.query(Product.id)
            .filter(Product.id == int(product_id))
            .first()
        )
        if exists is None:
            raise ValueError("product_id does not exist")
    if scope == "product_list":
        if category_id is not None or product_id is not None:
            raise ValueError("category_id and product_id must be null for product_list scope")
        if not product_ids:
            raise ValueError("product_ids is required for product_list scope")


def is_discount_currently_valid(discount: DiscountDTO, at: datetime | None = None) -> bool:
    if at is None:
        now = datetime.now(timezone.utc)
    elif at.tzinfo is None:
        now = at.replace(tzinfo=timezone.utc)
    else:
        now = at.astimezone(timezone.utc)
    if not discount.get("is_active", False):
        return False

    starts_at = _coerce_datetime(discount.get("starts_at"))
    ends_at = _coerce_datetime(discount.get("ends_at"))

    if starts_at is not None and now < starts_at:
        return False
    if ends_at is not None and now > ends_at:
        return False
    return True


def calculate_line_discount(unit_price: int, discount: DiscountDTO) -> int:
    discount_type = discount.get("type")
    value = int(discount.get("value", 0))

    if unit_price <= 0 or value <= 0:
        return 0

    if discount_type == "percent":
        pricing = calcular_amount(
            unit_price=unit_price,
            quantity=1,
            discount_type="percent",
            discount_value=value,
        )
    elif discount_type == "fixed":
        pricing = calcular_amount(
            unit_price=unit_price,
            quantity=1,
            discount_type="fixed",
            discount_value=value,
        )
    else:
        return 0
    return int(pricing["discount_amount"])


def select_best_discount(discounts: Iterable[DiscountDTO], unit_price: int) -> DiscountDTO | None:
    best: DiscountDTO | None = None
    best_amount = 0

    for discount in discounts:
        amount = calculate_line_discount(unit_price=unit_price, discount=discount)
        if amount > best_amount:
            best = discount
            best_amount = amount

    return best


def calculate_line_pricing(unit_price: int, quantity: int, discount: DiscountDTO | None) -> dict:
    if quantity <= 0:
        raise ValueError("quantity must be greater than 0")

    discount_type = None
    discount_value = None
    discount_id = None
    if discount is not None:
        discount_type = str(discount.get("type"))
        discount_value = int(discount.get("value", 0))
        discount_id = discount.get("id")

    pricing = calcular_amount(
        unit_price=unit_price,
        quantity=quantity,
        discount_type=discount_type,
        discount_value=discount_value,
    )
    return {
        "unit_price": int(pricing["unit_price"]),
        "quantity": quantity,
        "discount_id": discount_id,
        "discount_amount": int(pricing["discount_amount"]),
        "final_unit_price": int(pricing["final_unit_price"]),
        "line_total": int(pricing["line_total"]),
    }


def get_applicable_discounts_for_product(product: dict, discounts: Iterable[DiscountDTO]) -> list[DiscountDTO]:
    applicable: list[DiscountDTO] = []
    product_id = product.get("id")
    category_id = product.get("category_id")

    for discount in discounts:
        if not is_discount_currently_valid(discount):
            continue

        scope = discount.get("scope")

        if scope == "all":
            applicable.append(discount)
        elif scope == "category" and int(discount.get("category_id") or 0) == int(category_id):
            applicable.append(discount)
        elif scope == "product" and int(discount.get("product_id") or 0) == int(product_id):
            applicable.append(discount)
        elif scope == "product_list":
            product_ids = discount.get("product_ids", [])
            if str(product_id) in {str(pid) for pid in product_ids}:
                applicable.append(discount)

    return applicable


def reprice_order_items(order: dict, discounts: Iterable[DiscountDTO], products_by_id: dict[int, dict]) -> dict:
    for item in order.get("items", []):
        product = products_by_id.get(item["product_id"])
        if product is None:
            continue

        applicable = get_applicable_discounts_for_product(product=product, discounts=discounts)
        best = select_best_discount(applicable, unit_price=int(item["unit_price"]))
        pricing = calculate_line_pricing(
            unit_price=int(item["unit_price"]),
            quantity=int(item["quantity"]),
            discount=best,
        )

        item["discount_id"] = pricing["discount_id"]
        item["discount_amount"] = pricing["discount_amount"]
        item["final_unit_price"] = pricing["final_unit_price"]
        item["line_total"] = pricing["line_total"]

    return recalculate_order_totals(order)


def recalculate_order_totals(order: dict) -> dict:
    subtotal = 0
    discount_total = 0
    total_amount = 0

    for item in order.get("items", []):
        unit_price = int(item.get("unit_price", 0))
        qty = int(item.get("quantity", 0))
        line_total = int(item.get("line_total", unit_price * qty))
        line_discount = int(item.get("discount_amount", 0)) * qty

        subtotal += unit_price * qty
        discount_total += line_discount
        total_amount += line_total

    order["subtotal"] = subtotal
    order["discount_total"] = discount_total
    order["total_amount"] = total_amount
    return order


def validate_order_pricing_before_submit(order: dict) -> None:
    if not order.get("items"):
        raise ValueError("cannot submit an empty order")
    if int(order.get("total_amount", 0)) < 0:
        raise ValueError("order total cannot be negative")


