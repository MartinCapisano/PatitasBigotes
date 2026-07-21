"""Vista storefront del catálogo: lo que ve un comprador anónimo.

Divergencia legítima respecto de `products_s` (el catálogo administrado): la
vitrina cotiza **con descuentos aplicados** y el catálogo administrado no. No
es un bug latente, son dos vistas del negocio con dos reglas de precio.

La dependencia hacia `products_s` es de una sola vía (vitrina -> administrado,
nunca al revés).
"""
from __future__ import annotations

from typing import Literal

from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session, joinedload, selectinload

from source.db.models import Product, ProductVariant
from source.db.session import read_session_scope
from source.services.discount_s import (
    DiscountDTO,
    calculate_line_pricing,
    get_applicable_discounts_for_product,
    list_discounts,
    select_best_discount,
)
from source.services.products_s import list_categories


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

    with read_session_scope(db) as (session, _):
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
            .options(joinedload(Product.category), selectinload(Product.variants))
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

        # min_price/max_price and sort_by="price" need the discount-aware final price,
        # which is only computable in Python (see _build_storefront_product_pricing) —
        # those paths must fetch every matching row before filtering/sorting/paging.
        # Without them, name-sorted browsing (the common case) can page in SQL directly.
        can_paginate_in_sql = min_price is None and max_price is None and sort_by == "name"

        if can_paginate_in_sql:
            total = query.count()
            rows = query.offset(safe_offset).limit(safe_limit).all()
        else:
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

        if can_paginate_in_sql:
            return data, total

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
    with read_session_scope(db) as (session, _):
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
