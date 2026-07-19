from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from source.dependencies.auth_d import get_current_user, get_current_user_id, require_admin
from source.db.session import get_db, get_db_transactional
from source.errors import raise_http_error_from_exception
from source.schemas import (
    PaymentIncidentResolveNoRefundRequest,
    PaymentIncidentResolveRefundRequest,
)
from source.services.payment_s import (
    get_payment_for_user,
    get_payment_public_status,
    list_payments_for_admin,
    list_pending_bank_transfer_payments_for_admin,
)
from source.services.refund_s import (
    create_mercadopago_refund,
    list_payment_incidents_for_admin,
    resolve_payment_incident_no_refund,
)

router = APIRouter()


@router.get("/payments/{payment_id}")
def get_payment(
    payment_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(current_user)

    try:
        payment = get_payment_for_user(
            payment_id=payment_id,
            user_id=user_id,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    return {"data": payment}


@router.get("/payments/public/status")
def get_public_payment_status(
    public_status_token: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        payment = get_payment_public_status(
            public_status_token=public_status_token,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": payment}


@router.get("/admin/payments/bank-transfer/pending")
def list_pending_bank_transfer_payments(
    limit: int = Query(default=100, ge=1, le=500),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        payments = list_pending_bank_transfer_payments_for_admin(
            db=db,
            limit=limit,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": payments}


@router.get("/admin/payments")
def list_admin_payments(
    status: str | None = None,
    limit: int = Query(default=10, ge=1, le=500),
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        rows = list_payments_for_admin(
            status=status,
            limit=limit,
            sort_by=sort_by,
            sort_dir=sort_dir,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": rows}


@router.get("/admin/payment-incidents")
def list_admin_payment_incidents(
    status: str | None = "pending_review",
    limit: int = Query(default=100, ge=1, le=500),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        rows = list_payment_incidents_for_admin(
            status=status,
            limit=limit,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": rows}


@router.post("/admin/payment-incidents/{incident_id}/resolve-refund", status_code=status.HTTP_201_CREATED)
def resolve_admin_payment_incident_refund(
    incident_id: int,
    payload: PaymentIncidentResolveRefundRequest,
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    admin_user_id = get_current_user_id(admin_user)
    try:
        result = create_mercadopago_refund(
            incident_id=incident_id,
            amount=payload.amount,
            admin_user_id=int(admin_user_id),
            reason=payload.reason,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": result}


@router.post("/admin/payment-incidents/{incident_id}/resolve-no-refund")
def resolve_admin_payment_incident_no_refund(
    incident_id: int,
    payload: PaymentIncidentResolveNoRefundRequest,
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    admin_user_id = get_current_user_id(admin_user)
    try:
        incident = resolve_payment_incident_no_refund(
            incident_id=incident_id,
            admin_user_id=int(admin_user_id),
            reason=payload.reason,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": incident}
