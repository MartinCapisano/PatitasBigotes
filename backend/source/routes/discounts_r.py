from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from source.dependencies.auth_d import require_admin
from source.db.session import get_db, get_db_transactional
from source.errors import raise_http_error_from_exception
from source.schemas import CreateDiscountRequest, UpdateDiscountRequest
from source.services.discount_s import (
    create_discount,
    delete_discount,
    list_discounts,
    update_discount,
)

router = APIRouter()


@router.get("/discounts")
def get_discounts(
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return {"data": list_discounts(db=db)}
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)


@router.post("/discounts", status_code=status.HTTP_201_CREATED)
def post_discount(
    payload: CreateDiscountRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        discount = create_discount(payload.model_dump(), db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    return {"data": discount}


@router.patch("/discounts/{discount_id}")
def patch_discount(
    discount_id: int,
    payload: UpdateDiscountRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    updates = payload.model_dump(exclude_none=True)
    try:
        discount = update_discount(discount_id=discount_id, updates=updates, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    if discount is None:
        raise HTTPException(status_code=404, detail="discount not found")

    return {"data": discount}


@router.delete("/discounts/{discount_id}")
def remove_discount(
    discount_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        discount = delete_discount(discount_id=discount_id, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if discount is None:
        raise HTTPException(status_code=404, detail="discount not found")
    return {"data": discount}
