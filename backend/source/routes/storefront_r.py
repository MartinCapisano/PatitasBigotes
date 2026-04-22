from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from source.db.session import get_db
from source.errors import raise_http_error_from_exception
from source.services.products_s import (
    get_storefront_product_by_id,
    list_storefront_categories,
    list_storefront_products,
)

router = APIRouter()


@router.get("/storefront/categories")
def storefront_categories(
    db: Session = Depends(get_db),
):
    try:
        data = list_storefront_categories(db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {
        "data": data,
        "meta": {
            "total": len(data),
        },
    }


@router.get("/storefront/products")
def storefront_products(
    category_id: int | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1),
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    sort_by: Literal["price", "name", "created_at"] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    normalized_q = str(q).strip() if isinstance(q, str) else None
    if normalized_q == "":
        normalized_q = None

    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=400, detail="min_price must be less than or equal to max_price")

    try:
        data, total = list_storefront_products(
            db=db,
            category_id=category_id,
            name_query=normalized_q,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    return {
        "data": data,
        "meta": {
            "total": int(total),
            "limit": int(limit),
            "offset": int(offset),
            "has_more": int(offset) + len(data) < int(total),
            "filters_applied": {
                "category_id": category_id,
                "q": normalized_q,
                "min_price": min_price,
                "max_price": max_price,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
        },
    }


@router.get("/storefront/products/{product_id}")
def storefront_product_detail(
    product_id: int,
    db: Session = Depends(get_db),
):
    try:
        product = get_storefront_product_by_id(product_id=product_id, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"data": product}
