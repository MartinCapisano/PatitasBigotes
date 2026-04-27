from __future__ import annotations

from contextlib import contextmanager
from typing import Literal

from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session, joinedload

from source.db.models import Category, Product, ProductVariant
from source.db.session import SessionLocal
from source.services.discount_s import (
    DiscountDTO,
    calculate_line_pricing,
    get_applicable_discounts_for_product,
    list_discounts,
    select_best_discount,
)


@contextmanager
def _read_session_scope(db: Session | None):
    owns_session = db is None
    session = db or SessionLocal()
    try:
        yield session, owns_session
    finally:
        if owns_session:
            session.close()


@contextmanager
def _write_session_scope(db: Session):
    if db is None:
        raise RuntimeError("db session is required for mutating operations")
    yield db, False


def _product_inventory(product: Product) -> tuple[int, int]:
    active_variants = [variant for variant in product.variants if variant.is_active]
    total_stock = sum(int(variant.stock) for variant in active_variants)
    active_flag = 1 if active_variants else 0
    return total_stock, active_flag


def _compute_min_var_price(product: Product) -> int | None:
    prices = [int(variant.price) for variant in product.variants if variant.is_active]
    if not prices:
        return None
    return int(min(prices))


def _product_to_dict(product: Product) -> dict:
    stock, active = _product_inventory(product)
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "img_url": product.img_url,
        "min_var_price": _compute_min_var_price(product),
        "category_id": product.category_id,
        "category": product.category.name if product.category is not None else None,
        "stock": stock,
        "active": active,
    }


def _variant_to_dict(variant: ProductVariant) -> dict:
    return {
        "id": variant.id,
        "product_id": variant.product_id,
        "sku": variant.sku,
        "size": variant.size,
        "color": variant.color,
        "img_url": variant.img_url,
        "price": int(variant.price),
        "stock": int(variant.stock),
        "active": 1 if variant.is_active else 0,
    }


def _variant_to_storefront_dict(variant: ProductVariant, *, price_original: int, price_final: int) -> dict:
    return {
        "id": int(variant.id),
        "size": variant.size,
        "color": variant.color,
        "img_url": variant.img_url,
        "price": int(price_final),
        "price_original": int(price_original),
        "price_final": int(price_final),
        "has_discount": int(price_final) < int(price_original),
        "in_stock": int(variant.stock) > 0,
    }


def _storefront_option_axis(active_variants: list[ProductVariant]) -> str:
    if any((variant.size or "").strip() for variant in active_variants):
        return "size"
    if any((variant.color or "").strip() for variant in active_variants):
        return "color"
    return "variant"


def _storefront_option_label(variant: ProductVariant, axis: str) -> str:
    size_label = str(variant.size or "").strip()
    color_label = str(variant.color or "").strip()
    if axis == "size" and size_label:
        return size_label
    if axis == "color" and color_label:
        return color_label
    if size_label and color_label:
        return f"{size_label} / {color_label}"
    if size_label:
        return size_label
    if color_label:
        return color_label
    return f"Variante {int(variant.id)}"


def _variant_to_storefront_option(
    variant: ProductVariant,
    axis: str,
    *,
    price_original: int,
    price_final: int,
) -> dict:
    return {
        "variant_id": int(variant.id),
        "label": _storefront_option_label(variant, axis),
        "size": variant.size,
        "color": variant.color,
        "img_url": variant.img_url,
        "price": int(price_final),
        "price_original": int(price_original),
        "price_final": int(price_final),
        "has_discount": int(price_final) < int(price_original),
        "in_stock": int(variant.stock) > 0,
    }


def _product_to_storefront_dict(
    *,
    product: Product,
    min_var_price_original: int | None,
    min_var_price_final: int | None,
    active_stock_sum: int,
    has_discount: bool,
) -> dict:
    return {
        "id": int(product.id),
        "name": product.name,
        "description": product.description,
        "img_url": product.img_url,
        "category_id": int(product.category_id),
        "category_name": product.category.name if product.category is not None else None,
        "min_var_price": None if min_var_price_final is None else int(min_var_price_final),
        "min_var_price_original": None if min_var_price_original is None else int(min_var_price_original),
        "min_var_price_final": None if min_var_price_final is None else int(min_var_price_final),
        "has_discount": bool(has_discount),
        "in_stock": int(active_stock_sum or 0) > 0,
    }


def _calculate_variant_pricing_for_storefront(
    *,
    variant: ProductVariant,
    product_discounts: list[DiscountDTO],
) -> tuple[int, int]:
    unit_price = int(variant.price)
    best_discount = select_best_discount(product_discounts, unit_price=unit_price)
    pricing = calculate_line_pricing(unit_price=unit_price, quantity=1, discount=best_discount)
    return unit_price, int(pricing["final_unit_price"])


def _build_storefront_product_pricing(
    *,
    product: Product,
    discounts: list[DiscountDTO],
) -> tuple[int | None, int | None, bool]:
    active_variants = [variant for variant in product.variants if bool(variant.is_active)]
    if not active_variants:
        return None, None, False

    product_stub = {
        "id": int(product.id),
        "category_id": int(product.category_id),
    }
    applicable_discounts = get_applicable_discounts_for_product(product=product_stub, discounts=discounts)
    min_original: int | None = None
    min_final: int | None = None

    for variant in active_variants:
        original, final = _calculate_variant_pricing_for_storefront(
            variant=variant,
            product_discounts=applicable_discounts,
        )
        if min_original is None or original < min_original:
            min_original = original
        if min_final is None or final < min_final:
            min_final = final

    has_discount = bool(min_original is not None and min_final is not None and min_final < min_original)
    return min_original, min_final, has_discount


def _category_to_dict(category: Category) -> dict:
    return {
        "id": int(category.id),
        "name": category.name,
    }


def _variants_by_product_to_dict(products: list[Product]) -> dict[str, list[dict]]:
    payload: dict[str, list[dict]] = {}
    for product in products:
        sorted_variants = sorted(product.variants, key=lambda row: int(row.id))
        payload[str(int(product.id))] = [_variant_to_dict(variant) for variant in sorted_variants]
    return payload


def _query_admin_products(
    session: Session,
    *,
    min_price: int | None = None,
    max_price: int | None = None,
    category: str | None = None,
    sort_by: Literal["price", "name"] | None = None,
    sort_order: Literal["asc", "desc"] = "asc",
) -> list[Product]:
    min_price_subquery = (
        session.query(
            ProductVariant.product_id.label("product_id"),
            func.min(ProductVariant.price).label("min_var_price"),
        )
        .filter(ProductVariant.is_active.is_(True))
        .group_by(ProductVariant.product_id)
        .subquery()
    )

    query = (
        session.query(Product)
        .outerjoin(min_price_subquery, Product.id == min_price_subquery.c.product_id)
        .options(
            joinedload(Product.category),
            joinedload(Product.variants),
        )
    )

    if min_price is not None:
        query = query.filter(min_price_subquery.c.min_var_price >= min_price)
    if max_price is not None:
        query = query.filter(min_price_subquery.c.min_var_price <= max_price)
    if category is not None:
        query = query.join(Product.category).filter_by(name=category)

    if sort_by is not None:
        column = min_price_subquery.c.min_var_price if sort_by == "price" else Product.name
        query = query.order_by(desc(column) if sort_order == "desc" else asc(column))
    else:
        query = query.order_by(Product.id.asc())

    return query.all()


def filter_and_sort_products(
    db: Session | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    category: str | None = None,
    sort_by: Literal["price", "name"] | None = None,
    sort_order: Literal["asc", "desc"] = "asc",
) -> list[dict]:
    with _read_session_scope(db) as (session, _):
        products = _query_admin_products(
            session,
            min_price=min_price,
            max_price=max_price,
            category=category,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return [_product_to_dict(product) for product in products]


def list_admin_products_with_variants(
    *,
    db: Session | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    category: str | None = None,
    sort_by: Literal["price", "name"] | None = None,
    sort_order: Literal["asc", "desc"] = "asc",
) -> dict:
    with _read_session_scope(db) as (session, _):
        products = _query_admin_products(
            session,
            min_price=min_price,
            max_price=max_price,
            category=category,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return {
            "products": [_product_to_dict(product) for product in products],
            "variants_by_product": _variants_by_product_to_dict(products),
        }


def list_admin_catalog(*, db: Session | None = None) -> dict:
    with _read_session_scope(db) as (session, _):
        products = _query_admin_products(session)
        categories = session.query(Category).order_by(Category.id.asc()).all()
        return {
            "categories": [_category_to_dict(category) for category in categories],
            "products": [_product_to_dict(product) for product in products],
            "variants_by_product": _variants_by_product_to_dict(products),
        }


def get_product_by_id(product_id: int, db: Session | None = None) -> dict | None:
    with _read_session_scope(db) as (session, _):
        product = (
            session.query(Product)
            .options(joinedload(Product.category), joinedload(Product.variants))
            .filter(Product.id == product_id)
            .first()
        )
        if product is None:
            return None
        return _product_to_dict(product)


def update_product(product_id: int, updates: dict, db: Session) -> dict | None:
    allowed_fields = {"name", "description", "img_url", "category", "active"}
    with _write_session_scope(db) as (session, _):
        product = (
            session.query(Product)
            .options(joinedload(Product.category), joinedload(Product.variants))
            .filter(Product.id == product_id)
            .first()
        )
        if product is None:
            return None

        for field, value in updates.items():
            if field not in allowed_fields:
                continue
            if field == "category":
                category = session.query(Category).filter(Category.name == str(value)).first()
                if category is None:
                    raise ValueError("category not found")
                product.category_id = category.id
            elif field == "active":
                active_flag = bool(value)
                if active_flag:
                    for variant in product.variants:
                        variant.is_active = True
                else:
                    for variant in product.variants:
                        variant.is_active = False
            else:
                setattr(product, field, value)

        session.flush()
        session.refresh(product)
        return _product_to_dict(product)


def create_product(payload: dict, db: Session) -> dict:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("name is required")

    category_name = str(payload.get("category", "")).strip()
    if not category_name:
        raise ValueError("category is required")

    description = payload.get("description")
    normalized_description = None if description is None else str(description).strip() or None
    raw_img_url = payload.get("img_url")
    normalized_img_url = None if raw_img_url is None else str(raw_img_url).strip() or None

    with _write_session_scope(db) as (session, _):
        category = session.query(Category).filter(Category.name == category_name).first()
        if category is None:
            raise ValueError("category not found")

        product = Product(
            name=name,
            description=normalized_description,
            img_url=normalized_img_url,
            category_id=category.id,
        )
        session.add(product)
        session.flush()

        session.refresh(product)
        return _product_to_dict(product)


def delete_product_hard(product_id: int, db: Session) -> dict | None:
    with _write_session_scope(db) as (session, _):
        product = (
            session.query(Product)
            .options(joinedload(Product.category), joinedload(Product.variants))
            .filter(Product.id == product_id)
            .first()
        )
        if product is None:
            return None

        product_data = _product_to_dict(product)
        session.delete(product)
        session.flush()
        return product_data


def deactivate_product(product_id: int, db: Session) -> dict | None:
    return update_product(product_id=product_id, updates={"active": 0}, db=db)


def activate_product(product_id: int, db: Session) -> dict | None:
    return update_product(product_id=product_id, updates={"active": 1}, db=db)


def ensure_product_has_variant(product_id: int, db: Session | None = None) -> list[dict]:
    with _read_session_scope(db) as (session, _):
        product = (
            session.query(Product)
            .options(joinedload(Product.variants))
            .filter(Product.id == product_id)
            .first()
        )
        if product is None:
            raise LookupError("product not found")

        active_variants = [variant for variant in product.variants if variant.is_active]
        if active_variants:
            return [_variant_to_dict(variant) for variant in active_variants]

        raise LookupError("product has no active variants")


def add_stock(product_id: int, quantity: int, db: Session) -> dict:
    if quantity <= 0:
        raise ValueError("quantity must be greater than 0")

    with _write_session_scope(db) as (session, _):
        variants = ensure_product_has_variant(product_id=product_id, db=session)
        if not variants:
            raise ValueError("product has no active variants")

        add_variant_stock(variant_id=variants[0]["id"], quantity=quantity, db=session)

        product = get_product_by_id(product_id=product_id, db=session)
        if product is None:
            raise LookupError("product not found")
        return product


def decrement_stock(product_id: int, quantity: int, db: Session) -> dict:
    if quantity <= 0:
        raise ValueError("quantity must be greater than 0")

    with _write_session_scope(db) as (session, _):
        product = (
            session.query(Product)
            .options(joinedload(Product.variants), joinedload(Product.category))
            .filter(Product.id == product_id)
            .first()
        )
        if product is None:
            raise LookupError("product not found")

        active_variants = [variant for variant in product.variants if variant.is_active]
        total_stock = sum(int(variant.stock) for variant in active_variants)
        if total_stock < quantity:
            raise ValueError("insufficient stock")

        remaining = quantity
        for variant in active_variants:
            if remaining == 0:
                break
            current_stock = int(variant.stock)
            if current_stock == 0:
                continue
            taken = min(current_stock, remaining)
            variant.stock = current_stock - taken
            remaining -= taken

        session.flush()

        return _product_to_dict(product)


def get_variant_by_id(
    variant_id: int,
    db: Session | None = None,
    *,
    include_inactive: bool = False,
) -> dict | None:
    with _read_session_scope(db) as (session, _):
        query = (
            session.query(ProductVariant)
            .options(joinedload(ProductVariant.product).joinedload(Product.category))
            .filter(ProductVariant.id == variant_id)
        )
        if not include_inactive:
            query = query.filter(ProductVariant.is_active.is_(True))
        variant = query.first()
        if variant is None or variant.product is None:
            return None
        return _variant_to_dict(variant)


def list_categories(db: Session | None = None) -> list[dict]:
    with _read_session_scope(db) as (session, _):
        categories = session.query(Category).order_by(Category.id.asc()).all()
        return [_category_to_dict(category) for category in categories]


def list_storefront_categories(db: Session | None = None) -> list[dict]:
    return list_categories(db=db)


def list_storefront_products(
    *,
    db: Session | None = None,
    category_id: int | None = None,
    name_query: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    sort_by: Literal["price", "name"] = "name",
    sort_order: Literal["asc", "desc"] = "desc",
    limit: int = 24,
    offset: int = 0,
) -> tuple[list[dict], int]:
    safe_limit = max(1, min(int(limit), 100))
    safe_offset = max(0, int(offset))

    with _read_session_scope(db) as (session, _):
        aggregates_subquery = (
            session.query(
                ProductVariant.product_id.label("product_id"),
                func.min(ProductVariant.price).label("min_var_price"),
                func.sum(ProductVariant.stock).label("active_stock_sum"),
                func.count(ProductVariant.id).label("active_variant_count"),
            )
            .filter(ProductVariant.is_active.is_(True))
            .group_by(ProductVariant.product_id)
            .subquery()
        )

        query = (
            session.query(
                Product,
                aggregates_subquery.c.min_var_price,
                aggregates_subquery.c.active_stock_sum,
            )
            .join(
                aggregates_subquery,
                Product.id == aggregates_subquery.c.product_id,
            )
            .options(joinedload(Product.category), joinedload(Product.variants))
            .filter(aggregates_subquery.c.active_variant_count > 0)
        )

        if category_id is not None:
            query = query.filter(Product.category_id == int(category_id))
        if name_query is not None:
            normalized_query = str(name_query).strip()
            if normalized_query:
                query = query.filter(Product.name.ilike(f"%{normalized_query}%"))
        if sort_by == "name":
            query = query.order_by(
                desc(Product.name) if sort_order == "desc" else asc(Product.name)
            )
        rows = query.all()
        discounts = list_discounts(db=session)

        data = []
        for product, _min_var_price, active_stock_sum in rows:
            min_original, min_final, has_discount = _build_storefront_product_pricing(
                product=product,
                discounts=discounts,
            )
            data.append(
                _product_to_storefront_dict(
                    product=product,
                    min_var_price_original=min_original,
                    min_var_price_final=min_final,
                    active_stock_sum=int(active_stock_sum or 0),
                    has_discount=has_discount,
                )
            )
        if min_price is not None:
            data = [
                product
                for product in data
                if product["min_var_price_final"] is not None
                and int(product["min_var_price_final"]) >= int(min_price)
            ]
        if max_price is not None:
            data = [
                product
                for product in data
                if product["min_var_price_final"] is not None
                and int(product["min_var_price_final"]) <= int(max_price)
            ]
        if sort_by == "price":
            data.sort(
                key=lambda product: int(product["min_var_price_final"]),
                reverse=sort_order == "desc",
            )
        total = len(data)
        data = data[safe_offset : safe_offset + safe_limit]
        return data, total


def get_storefront_product_by_id(product_id: int, db: Session | None = None) -> dict | None:
    with _read_session_scope(db) as (session, _):
        product = (
            session.query(Product)
            .options(
                joinedload(Product.category),
                joinedload(Product.variants),
            )
            .filter(Product.id == product_id)
            .first()
        )
        if product is None:
            return None

        active_variants = [
            variant
            for variant in product.variants
            if bool(variant.is_active)
        ]
        if not active_variants:
            return None

        discounts = list_discounts(db=session)
        product_stub = {
            "id": int(product.id),
            "category_id": int(product.category_id),
        }
        applicable_discounts = get_applicable_discounts_for_product(product=product_stub, discounts=discounts)
        min_var_price_original, min_var_price_final, has_discount = _build_storefront_product_pricing(
            product=product,
            discounts=discounts,
        )
        active_stock_sum = sum(int(variant.stock) for variant in active_variants)

        payload = _product_to_storefront_dict(
            product=product,
            min_var_price_original=min_var_price_original,
            min_var_price_final=min_var_price_final,
            active_stock_sum=active_stock_sum,
            has_discount=has_discount,
        )
        sorted_active_variants = sorted(active_variants, key=lambda row: int(row.id))
        option_axis = _storefront_option_axis(sorted_active_variants)
        pricing_by_variant_id: dict[int, tuple[int, int]] = {}
        for variant in sorted_active_variants:
            pricing_by_variant_id[int(variant.id)] = _calculate_variant_pricing_for_storefront(
                variant=variant,
                product_discounts=applicable_discounts,
            )
        payload["option_axis"] = option_axis
        payload["options"] = [
            _variant_to_storefront_option(
                variant,
                option_axis,
                price_original=pricing_by_variant_id[int(variant.id)][0],
                price_final=pricing_by_variant_id[int(variant.id)][1],
            )
            for variant in sorted_active_variants
        ]
        for option in payload["options"]:
            option["effective_img_url"] = option.get("img_url") or payload.get("img_url")
        # Backward compatibility for existing consumers that still read `variants`.
        payload["variants"] = [
            _variant_to_storefront_dict(
                variant,
                price_original=pricing_by_variant_id[int(variant.id)][0],
                price_final=pricing_by_variant_id[int(variant.id)][1],
            )
            for variant in sorted_active_variants
        ]
        return payload


def get_category_by_id(category_id: int, db: Session | None = None) -> dict | None:
    with _read_session_scope(db) as (session, _):
        category = session.query(Category).filter(Category.id == category_id).first()
        if category is None:
            return None
        return _category_to_dict(category)


def create_category(payload: dict, db: Session) -> dict:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("name is required")

    with _write_session_scope(db) as (session, _):
        existing = session.query(Category).filter(Category.name == name).first()
        if existing is not None:
            raise ValueError("category already exists")

        category = Category(name=name)
        session.add(category)
        session.flush()
        return _category_to_dict(category)


def update_category(category_id: int, updates: dict, db: Session) -> dict | None:
    with _write_session_scope(db) as (session, _):
        category = session.query(Category).filter(Category.id == category_id).first()
        if category is None:
            return None

        if "name" in updates:
            new_name = str(updates.get("name", "")).strip()
            if not new_name:
                raise ValueError("name is required")
            duplicate = (
                session.query(Category)
                .filter(Category.name == new_name, Category.id != category_id)
                .first()
            )
            if duplicate is not None:
                raise ValueError("category already exists")
            category.name = new_name

        session.flush()
        return _category_to_dict(category)


def delete_category_hard(category_id: int, db: Session) -> dict | None:
    with _write_session_scope(db) as (session, _):
        category = session.query(Category).filter(Category.id == category_id).first()
        if category is None:
            return None
        payload = _category_to_dict(category)
        session.delete(category)
        session.flush()
        return payload


def create_variant(payload: dict, db: Session) -> dict:
    try:
        product_id = int(payload.get("product_id"))
    except (TypeError, ValueError) as exc:
        raise ValueError("product_id is required") from exc
    sku = str(payload.get("sku", "")).strip()
    if not sku:
        raise ValueError("sku is required")

    try:
        price = int(payload.get("price"))
    except (TypeError, ValueError) as exc:
        raise ValueError("price is required") from exc
    try:
        stock = int(payload.get("stock", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("stock must be greater than or equal to 0") from exc
    if price < 0:
        raise ValueError("price must be greater than or equal to 0")
    if stock < 0:
        raise ValueError("stock must be greater than or equal to 0")
    raw_img_url = payload.get("img_url")
    normalized_img_url = None if raw_img_url is None else str(raw_img_url).strip() or None

    with _write_session_scope(db) as (session, _):
        product = session.query(Product).filter(Product.id == product_id).first()
        if product is None:
            raise ValueError("product not found")

        existing = session.query(ProductVariant).filter(ProductVariant.sku == sku).first()
        if existing is not None:
            raise ValueError("variant sku already exists")

        variant = ProductVariant(
            product_id=product_id,
            sku=sku,
            size=None if payload.get("size") is None else str(payload.get("size")).strip() or None,
            color=None if payload.get("color") is None else str(payload.get("color")).strip() or None,
            img_url=normalized_img_url,
            price=price,
            stock=stock,
            is_active=bool(payload.get("active", True)),
        )
        session.add(variant)
        session.flush()
        return _variant_to_dict(variant)


def update_variant(variant_id: int, updates: dict, db: Session) -> dict | None:
    allowed_fields = {"product_id", "sku", "size", "color", "img_url", "price", "stock", "active"}
    with _write_session_scope(db) as (session, _):
        variant = session.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
        if variant is None:
            return None

        for field, value in updates.items():
            if field not in allowed_fields:
                continue
            if field == "product_id":
                try:
                    product_id = int(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError("product_id is required") from exc
                product = session.query(Product).filter(Product.id == product_id).first()
                if product is None:
                    raise ValueError("product not found")
                variant.product_id = product_id
            elif field == "sku":
                sku = str(value).strip()
                if not sku:
                    raise ValueError("sku is required")
                duplicate = (
                    session.query(ProductVariant)
                    .filter(ProductVariant.sku == sku, ProductVariant.id != variant_id)
                    .first()
                )
                if duplicate is not None:
                    raise ValueError("variant sku already exists")
                variant.sku = sku
            elif field == "size":
                variant.size = None if value is None else str(value).strip() or None
            elif field == "color":
                variant.color = None if value is None else str(value).strip() or None
            elif field == "img_url":
                variant.img_url = None if value is None else str(value).strip() or None
            elif field == "price":
                try:
                    price = int(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError("price is required") from exc
                if price < 0:
                    raise ValueError("price must be greater than or equal to 0")
                variant.price = price
            elif field == "stock":
                try:
                    stock = int(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError("stock must be greater than or equal to 0") from exc
                if stock < 0:
                    raise ValueError("stock must be greater than or equal to 0")
                variant.stock = stock
            elif field == "active":
                variant.is_active = bool(value)

        session.flush()
        return _variant_to_dict(variant)


def delete_variant_hard(variant_id: int, db: Session) -> dict | None:
    with _write_session_scope(db) as (session, _):
        variant = session.query(ProductVariant).filter(ProductVariant.id == variant_id).first()
        if variant is None:
            return None
        payload = _variant_to_dict(variant)
        session.delete(variant)
        session.flush()
        return payload


def add_variant_stock(variant_id: int, quantity: int, db: Session) -> dict:
    if quantity <= 0:
        raise ValueError("quantity must be greater than 0")

    with _write_session_scope(db) as (session, _):
        variant = (
            session.query(ProductVariant)
            .filter(ProductVariant.id == variant_id, ProductVariant.is_active.is_(True))
            .first()
        )
        if variant is None:
            raise LookupError("variant not found")

        variant.stock = int(variant.stock) + quantity
        session.flush()
        return _variant_to_dict(variant)


def decrement_variant_stock(variant_id: int, quantity: int, db: Session) -> dict:
    if quantity <= 0:
        raise ValueError("quantity must be greater than 0")

    with _write_session_scope(db) as (session, _):
        variant = (
            session.query(ProductVariant)
            .filter(ProductVariant.id == variant_id, ProductVariant.is_active.is_(True))
            .first()
        )
        if variant is None:
            raise LookupError("variant not found")

        current_stock = int(variant.stock)
        if current_stock < quantity:
            raise ValueError("insufficient stock")

        variant.stock = current_stock - quantity
        session.flush()
        return _variant_to_dict(variant)
