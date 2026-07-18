from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from source.dependencies.auth_d import require_admin
from source.db.session import get_db, get_db_transactional
from source.errors import raise_http_error_from_exception
from source.schemas import (
    CreateCategoryRequest,
    CreateProductRequest,
    CreateVariantRequest,
    PatchCategoryRequest,
    PatchProductRequest,
    PatchVariantRequest,
    UpdateCategoryRequest,
    UpdateProductRequest,
    UpdateVariantRequest,
)
from source.services.products_s import (
    create_category as create_category_s,
    create_product as create_product_s,
    create_variant as create_variant_s,
    delete_category_hard,
    delete_product_hard,
    delete_variant_hard,
    filter_and_sort_products,
    get_category_by_id,
    get_product_by_id,
    get_variant_by_id,
    list_admin_catalog,
    list_admin_products_with_variants,
    list_categories as list_categories_s,
    update_category as update_category_s,
    update_product as update_product_s,
    update_variant as update_variant_s,
)

router = APIRouter()


@router.get("/products")
def get_products(
    min_price: Optional[int] = Query(None),
    max_price: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    sort_by: Optional[Literal["price", "name"]] = Query(None),
    sort_order: Literal["asc", "desc"] = Query("asc"),
    include_variants: bool = Query(False),
    limit: Optional[int] = Query(None),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    safe_limit = None if limit is None else max(1, min(int(limit), 1000))

    if include_variants:
        payload = list_admin_products_with_variants(
            db=db,
            min_price=min_price,
            max_price=max_price,
            category=category,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=safe_limit,
        )
    else:
        payload = filter_and_sort_products(
            db=db,
            min_price=min_price,
            max_price=max_price,
            category=category,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=safe_limit,
        )

    return {
        "data": payload,
        "meta": {
            "filters": {
                "min_price": min_price,
                "max_price": max_price,
                "category": category,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
            "include_variants": include_variants,
            "limit": safe_limit,
        },
    }


@router.get("/admin/catalog")
def get_admin_catalog(
    limit: int = Query(200),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    safe_limit = max(1, min(int(limit), 1000))
    return {"data": list_admin_catalog(db=db, limit=safe_limit)}


@router.get("/products/{product_id}")
def get_product(
    product_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    product = get_product_by_id(product_id, db=db)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return {"data": product}


@router.post("/products")
def create_product(
    payload: CreateProductRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        product = create_product_s(payload=payload.model_dump(), db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": product}


@router.put("/products/{product_id}")
def update_product(
    product_id: int,
    payload: UpdateProductRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        product = update_product_s(
            product_id=product_id,
            updates=payload.model_dump(),
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"data": product}


@router.patch("/products/{product_id}")
def patch_product(
    product_id: int,
    payload: PatchProductRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="at least one field is required")
    try:
        product = update_product_s(
            product_id=product_id,
            updates=updates,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"data": product}


@router.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        product = delete_product_hard(product_id=product_id, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"data": product}


@router.get("/categories")
def list_categories(
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {"data": list_categories_s(db=db)}


@router.get("/categories/{category_id}")
def get_category(
    category_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    category = get_category_by_id(category_id=category_id, db=db)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"data": category}


@router.post("/categories")
def create_category(
    payload: CreateCategoryRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        category = create_category_s(payload=payload.model_dump(), db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": category}


@router.put("/categories/{category_id}")
def update_category(
    category_id: int,
    payload: UpdateCategoryRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        category = update_category_s(
            category_id=category_id,
            updates=payload.model_dump(),
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"data": category}


@router.patch("/categories/{category_id}")
def patch_category(
    category_id: int,
    payload: PatchCategoryRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="at least one field is required")
    try:
        category = update_category_s(
            category_id=category_id,
            updates=updates,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"data": category}


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        category = delete_category_hard(category_id=category_id, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"data": category}


@router.get("/variants/{variant_id}")
def get_variant(
    variant_id: int,
    include_inactive: bool = Query(True),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    variant = get_variant_by_id(variant_id=variant_id, include_inactive=include_inactive, db=db)
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")
    return {"data": variant}


@router.post("/variants")
def create_variant(
    payload: CreateVariantRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        variant = create_variant_s(payload=payload.model_dump(), db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": variant}


@router.put("/variants/{variant_id}")
def update_variant(
    variant_id: int,
    payload: UpdateVariantRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        variant = update_variant_s(
            variant_id=variant_id,
            updates=payload.model_dump(),
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")
    return {"data": variant}


@router.patch("/variants/{variant_id}")
def patch_variant(
    variant_id: int,
    payload: PatchVariantRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="at least one field is required")
    try:
        variant = update_variant_s(
            variant_id=variant_id,
            updates=updates,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")
    return {"data": variant}


@router.delete("/variants/{variant_id}")
def delete_variant(
    variant_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        variant = delete_variant_hard(variant_id=variant_id, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")
    return {"data": variant}
