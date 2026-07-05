from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response, status
import logging
from sqlalchemy.orm import Session

from source.dependencies.auth_d import get_current_user, get_current_user_id, require_admin
from source.db.session import get_db, get_db_transactional
from source.errors import raise_http_error_from_exception
from source.schemas import (
    AdminRegisterPaymentRequest,
    CreateAdminSaleRequest,
    CreateOrderPaymentRequest,
    PublicOrderSnapshotResponse,
    PublicGuestCheckoutRequest,
    ReplaceDraftItemsRequest,
    UpdateOrderStatusRequest,
)
from source.services.orders_s import (
    change_order_status,
    create_admin_sale,
    create_manual_submitted_order,
    get_draft_order,
    get_order_for_admin,
    get_order_reservations_for_user,
    get_or_create_draft_order,
    get_order_for_user,
    get_public_order_snapshot_by_payment_token,
    list_orders_for_admin,
    list_orders_for_user,
    replace_draft_order_items,
)
from source.services.anti_abuse_s import enforce_public_guest_checkout_limits
from source.services.idempotency_s import (
    IDEMPOTENCY_TTL_HOURS,
    acquire_record,
    build_guest_checkout_scope,
    canonicalize_payload,
    hash_payload,
    load_replay_payload,
    mark_record_completed,
    mark_record_failed,
    normalize_idempotency_key,
    prune_expired_records,
)
from source.services.payment_errors import PaymentCheckoutInitializationError
from source.services.payment_s import (
    PAYMENT_PROVIDER_SETUP_FAILED,
    RETRY_FAILED_MERCADOPAGO_CHECKOUT_UNAVAILABLE,
    confirm_manual_payment_for_order,
    create_payment_for_order,
    create_retry_payment_for_order,
    create_retry_payment_for_payment_token,
    initialize_mercadopago_checkout_for_payment,
    list_payments_for_order_admin,
    list_payments_for_order,
    mark_payment_checkout_setup_failed,
)
from source.services.post_commit_actions_s import clear_post_commit_actions, dispatch_post_commit_actions

router = APIRouter()
logger = logging.getLogger(__name__)
MERCADOPAGO_CHECKOUT_SETUP_ERROR_DETAIL = "no se pudo inicializar el checkout de Mercado Pago"


def _client_ip_from_request(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def _sanitize_response_payload(payload: object) -> object:
    """Recursively redact obvious secrets from response payloads before persisting."""
    if isinstance(payload, dict):
        out = {}
        for k, v in payload.items():
            kl = k.lower()
            if any(s in kl for s in ("token", "secret", "access", "password", "card", "cvv", "number")):
                out[k] = "<redacted>"
            else:
                out[k] = _sanitize_response_payload(v)
        return out
    if isinstance(payload, list):
        return [_sanitize_response_payload(i) for i in payload]
    return payload


def _initialize_mercadopago_payment_or_raise(*, payment: dict, db: Session) -> dict:
    if payment.get("method") != "mercadopago":
        return payment
    if payment.get("preference_id") is not None:
        return payment
    if payment.get("provider_status") == PAYMENT_PROVIDER_SETUP_FAILED:
        raise PaymentCheckoutInitializationError(
            MERCADOPAGO_CHECKOUT_SETUP_ERROR_DETAIL
        )

    payment_id = int(payment["id"])
    try:
        return initialize_mercadopago_checkout_for_payment(payment_id=payment_id, db=db)
    except Exception as exc:
        # Attempt to mark the payment as setup failed before rolling back to avoid
        # losing the payment row if it's uncommitted in the current session.
        try:
            mark_payment_checkout_setup_failed(
                payment_id=payment_id,
                error_detail=str(exc),
                db=db,
            )
            db.commit()
        except Exception:
            # If marking failed errors (e.g., payment row not found), rollback to
            # leave DB in a consistent state and surface the initialization error.
            try:
                db.rollback()
            except Exception:
                pass
        raise PaymentCheckoutInitializationError(
            MERCADOPAGO_CHECKOUT_SETUP_ERROR_DETAIL
        ) from exc


def _build_guest_checkout_recovery_payload(
    *,
    order_id: int,
    payment_id: int,
    db: Session,
) -> dict:
    order = get_order_for_admin(order_id=order_id, db=db)
    if order is None:
        raise LookupError("order not found")
    payments = list_payments_for_order_admin(order_id=order_id, db=db)
    payment = next(
        (row for row in payments if int(row["id"]) == int(payment_id)),
        None,
    )
    if payment is None:
        raise LookupError("payment not found")
    return {
        "customer": order.get("customer"),
        "order": order,
        "payment": payment,
    }


@router.post("/checkout/guest", status_code=status.HTTP_201_CREATED)
def create_guest_checkout_order(
    payload: PublicGuestCheckoutRequest,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    record_created = False
    claimed_record = None
    try:
        now = datetime.now(UTC)
        prune_expired_records(now=now, db=db)

        normalized_key = normalize_idempotency_key(idempotency_key)
        scope = build_guest_checkout_scope(payload.customer.email)
        canonical_payload = canonicalize_payload(payload.model_dump())
        request_hash = hash_payload(canonical_payload)
        claimed_record, record_created = acquire_record(
            scope=scope,
            idempotency_key=normalized_key,
            request_hash=request_hash,
            expires_at=now + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
            db=db,
        )
        if not record_created:
            if claimed_record.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="idempotency key already used with a different payload",
                )
            if claimed_record.status == "completed":
                return {"data": load_replay_payload(claimed_record)}
            if claimed_record.status == "failed":
                failed_payload = load_replay_payload(claimed_record)
                payment_id = failed_payload.get("payment_id")
                order_id = failed_payload.get("order_id")
                if payment_id is None or order_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=str(
                            failed_payload.get("detail")
                            or MERCADOPAGO_CHECKOUT_SETUP_ERROR_DETAIL
                        ),
                    )
                try:
                    recovered_payment = _initialize_mercadopago_payment_or_raise(
                        payment={"id": int(payment_id), "method": "mercadopago"},
                        db=db,
                    )
                    result = _build_guest_checkout_recovery_payload(
                        order_id=int(order_id),
                        payment_id=int(recovered_payment["id"]),
                        db=db,
                    )
                    mark_record_completed(
                        record=claimed_record,
                        response_payload=result,
                        db=db,
                    )
                    db.commit()
                    return {"data": result}
                except PaymentCheckoutInitializationError as exc:
                    mark_record_failed(
                        record=claimed_record,
                        response_payload={
                            "detail": str(exc),
                            "order_id": int(order_id),
                            "payment_id": int(payment_id),
                        },
                        db=db,
                    )
                    db.commit()
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=str(exc),
                    )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="idempotent request already in progress",
            )

        enforce_public_guest_checkout_limits(
            client_ip=_client_ip_from_request(request),
            email=payload.customer.email,
            website=payload.website,
            db=db,
        )
        result = create_manual_submitted_order(
            email=payload.customer.email,
            first_name=payload.customer.first_name,
            last_name=payload.customer.last_name,
            phone=payload.customer.phone,
            items=[item.model_dump() for item in payload.items],
            db=db,
        )
        if payload.payment_method is not None:
            order_payload = result.get("order") if isinstance(result, dict) else None
            order_id = int(order_payload.get("id")) if isinstance(order_payload, dict) and order_payload.get("id") is not None else None
            if order_id is None:
                raise ValueError("invalid guest checkout response: missing order id")
            payment = create_payment_for_order(
                order_id=order_id,
                method=payload.payment_method,
                db=db,
                user_id=None,
                idempotency_key=f"guest-payment-{order_id}-{normalized_key}",
                currency="ARS",
                expires_in_minutes=60,
                initialize_provider=False,
            )
            result["payment"] = payment
            if payment["method"] == "mercadopago":
                db.flush()
                payment = _initialize_mercadopago_payment_or_raise(payment=payment, db=db)
                result["payment"] = payment
                mark_record_completed(
                    record=claimed_record,
                    response_payload=result,
                    db=db,
                )
                db.commit()
                return {"data": result}
        mark_record_completed(
            record=claimed_record,
            response_payload=result,
            db=db,
        )
        db.commit()
    except PaymentCheckoutInitializationError as exc:
        if record_created and claimed_record is not None and claimed_record.status == "processing":
            mark_record_failed(
                record=claimed_record,
                response_payload={
                    "detail": str(exc),
                    "order_id": int(result["order"]["id"]),
                    "payment_id": int(result["payment"]["id"]),
                },
                db=db,
            )
            db.commit()
        raise_http_error_from_exception(exc, db=db)
    except Exception as exc:
        # Ensure idempotency records created by this request don't remain stuck in 'processing'.
        if record_created and claimed_record is not None and getattr(claimed_record, "status", None) == "processing":
            try:
                mark_record_failed(
                    record=claimed_record,
                    response_payload={"detail": str(exc)},
                    db=db,
                )
                db.commit()
            except Exception:
                # If marking failed itself errors, rollback to avoid partial state.
                db.rollback()
        else:
            db.rollback()
        raise_http_error_from_exception(exc, db=db)
    return {"data": result}


@router.post("/admin/sales")
def create_admin_sale_endpoint(
    payload: CreateAdminSaleRequest,
    admin_user: dict = Depends(require_admin),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_transactional),
):
    """Create an in-person admin sale, optionally creating its paid manual payment."""
    admin_user_id = get_current_user_id(admin_user)
    record_created = False
    claimed_record = None
    try:
        if idempotency_key is not None and str(idempotency_key).strip():
            now = datetime.now(UTC)
            prune_expired_records(now=now, db=db)
            normalized_key = normalize_idempotency_key(idempotency_key)
            scope = f"admin_sales:{int(admin_user_id)}"
            canonical_payload = canonicalize_payload(payload.model_dump())
            request_hash = hash_payload(canonical_payload)
            claimed_record, record_created = acquire_record(
                scope=scope,
                idempotency_key=normalized_key,
                request_hash=request_hash,
                expires_at=now + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
                db=db,
            )
            if not record_created:
                if claimed_record.request_hash != request_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="idempotency key already used with a different payload",
                    )
                if claimed_record.status == "completed":
                    return {"data": load_replay_payload(claimed_record)}
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="idempotent request already in progress",
                )

        result = create_admin_sale(
            admin_user_id=int(admin_user_id),
            customer=payload.customer.model_dump(),
            items=[item.model_dump() for item in payload.items],
            register_payment=bool(payload.register_payment),
            payment=payload.payment.model_dump() if payload.payment is not None else None,
            db=db,
        )
        if record_created and claimed_record is not None:
            mark_record_completed(
                record=claimed_record,
                response_payload=result,
                db=db,
            )
    except Exception as exc:
        if record_created and claimed_record is not None and getattr(claimed_record, "status", None) == "processing":
            failed_payload = {"error": "internal_server_error", "message": str(exc)}
            sanitized = _sanitize_response_payload(failed_payload)
            try:
                mark_record_failed(
                    record=claimed_record,
                    response_payload=sanitized,
                    db=db,
                )
                db.flush()
            except Exception:
                logger.exception("Failed to mark idempotency record as failed; deleting record. scope=%s key=%s", getattr(claimed_record, "scope", None), getattr(claimed_record, "idempotency_key", None))
                try:
                    db.delete(claimed_record)
                    db.flush()
                except Exception:
                    logger.exception("Failed to delete idempotency record after failed mark; scope=%s key=%s", getattr(claimed_record, "scope", None), getattr(claimed_record, "idempotency_key", None))
        logger.exception("Error processing create_admin_sale_endpoint; scope=%s key=%s", getattr(claimed_record, "scope", None) if claimed_record else None, getattr(claimed_record, "idempotency_key", None) if claimed_record else None)
        raise_http_error_from_exception(exc, db=db)
    return {"data": result}


@router.get("/orders/draft")
def get_draft(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(current_user)
    try:
        order = get_draft_order(user_id=user_id, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if order is None:
        raise HTTPException(status_code=404, detail="Draft order not found")
    return {"data": order}


@router.post("/orders/draft", status_code=status.HTTP_200_OK)
def create_draft(
    response: Response,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_transactional),
):
    user_id = get_current_user_id(current_user)
    try:
        order, created = get_or_create_draft_order(user_id=user_id, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if created:
        response.status_code = status.HTTP_201_CREATED
    return {
        "data": order,
        "meta": {
            "created": created,
        },
    }


@router.put("/orders/draft/items")
def replace_draft_items(
    payload: ReplaceDraftItemsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_transactional),
):
    user_id = get_current_user_id(current_user)
    try:
        order = replace_draft_order_items(
            user_id=user_id,
            items=[item.model_dump() for item in payload.items],
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    return {"data": order}


@router.patch("/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    payload: UpdateOrderStatusRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_transactional),
):
    user_id = get_current_user_id(current_user)
    try:
        order = change_order_status(
            user_id=user_id,
            order_id=order_id,
            new_status=payload.status,
            is_admin=bool(current_user.get("is_admin", False)),
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    return {"data": order}


@router.get("/orders/{order_id}")
def get_order(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(current_user)
    try:
        order = get_order_for_user(user_id=user_id, order_id=order_id, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"data": order}


@router.get("/orders")
def list_orders(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(current_user)
    try:
        orders = list_orders_for_user(user_id=user_id, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": orders}


@router.get("/public/orders/by-payment-token", response_model=dict[str, PublicOrderSnapshotResponse])
def get_public_order_snapshot_by_payment_token_endpoint(
    public_status_token: str | None = None,
    # This GET may expire stale reservations before building the public
    # snapshot, so the transactional session persists that cleanup.
    db: Session = Depends(get_db_transactional),
):
    try:
        snapshot = get_public_order_snapshot_by_payment_token(
            public_status_token=public_status_token,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": snapshot}


@router.get("/admin/orders/{order_id}")
def get_order_admin(
    order_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        order = get_order_for_admin(order_id=order_id, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"data": order}


@router.get("/admin/orders")
def list_orders_admin(
    status: str | None = None,
    limit: int = 10,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        rows = list_orders_for_admin(
            status=status,
            limit=limit,
            sort_by=sort_by,
            sort_dir=sort_dir,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": rows}


@router.post("/admin/orders/{order_id}/payments/manual")
def admin_register_manual_payment(
    order_id: int,
    payload: AdminRegisterPaymentRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Confirm an existing pending manual payment for an already-created order."""
    try:
        order = get_order_for_admin(order_id=order_id, db=db)
        if order is None:
            raise LookupError("order not found")
        payment = confirm_manual_payment_for_order(
            order_id=order_id,
            user_id=int(order["user_id"]),
            payment_ref=str(payload.payment_ref or ""),
            paid_amount=int(payload.paid_amount),
            method=payload.method,
            change_amount=payload.change_amount,
            # Existing orders must already have a pending manual payment; this
            # endpoint confirms it instead of creating a new payment record.
            allow_create_if_missing=False,
            db=db,
        )
        updated_order = get_order_for_admin(order_id=order_id, db=db)
        db.commit()
    except Exception as exc:
        db.rollback()
        clear_post_commit_actions(db=db)
        raise_http_error_from_exception(exc, db=db)
    dispatch_post_commit_actions(db=db, source="admin_register_manual_payment")
    return {
        "data": {
            "order": updated_order,
            "payment": payment,
        }
    }


@router.post("/orders/{order_id}/payments", status_code=status.HTTP_201_CREATED)
def create_order_payment(
    order_id: int,
    payload: CreateOrderPaymentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(current_user)

    try:
        payment = create_payment_for_order(
            order_id=order_id,
            method=payload.method,
            db=db,
            user_id=user_id,
            idempotency_key=idempotency_key,
            currency=payload.currency,
            expires_in_minutes=payload.expires_in_minutes,
            initialize_provider=False,
        )
        db.flush()
        payment = _initialize_mercadopago_payment_or_raise(payment=payment, db=db)
        if payment.get("method") == "mercadopago" and payment.get("provider_status") != PAYMENT_PROVIDER_SETUP_FAILED:
            db.commit()
    except Exception as exc:
        db.rollback()
        raise_http_error_from_exception(exc, db=db)

    return {"data": payment}


@router.get("/orders/{order_id}/payments")
def list_order_payments(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(current_user)

    try:
        payments = list_payments_for_order(
            order_id=order_id,
            user_id=user_id,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    return {"data": payments}


@router.get("/admin/orders/{order_id}/payments")
def list_order_payments_admin(
    order_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        payments = list_payments_for_order_admin(
            order_id=order_id,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": payments}


@router.post("/orders/{order_id}/payments/retry", status_code=status.HTTP_201_CREATED)
def retry_order_payment(
    order_id: int,
    payload: CreateOrderPaymentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(current_user)
    try:
        payment = create_retry_payment_for_order(
            order_id=order_id,
            method=payload.method,
            db=db,
            user_id=user_id,
            idempotency_key=idempotency_key,
            currency=payload.currency,
            expires_in_minutes=payload.expires_in_minutes,
            initialize_provider=False,
        )
        db.flush()
        payment = _initialize_mercadopago_payment_or_raise(payment=payment, db=db)
        if payment.get("method") == "mercadopago" and payment.get("provider_status") != PAYMENT_PROVIDER_SETUP_FAILED:
            db.commit()
    except PaymentCheckoutInitializationError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=RETRY_FAILED_MERCADOPAGO_CHECKOUT_UNAVAILABLE,
        ) from exc
    except Exception as exc:
        db.rollback()
        raise_http_error_from_exception(exc, db=db)

    return {"data": payment}


@router.post("/payments/{public_status_token}/retry", status_code=status.HTTP_201_CREATED)
def retry_guest_payment(
    public_status_token: str,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    """
    Retry a payment for a guest user using their payment's public status token.
    No authentication required - the token grants access to retry this specific payment.
    """
    try:
        payment = create_retry_payment_for_payment_token(
            public_status_token=public_status_token,
            db=db,
            idempotency_key=idempotency_key,
            expires_in_minutes=60,
            initialize_provider=False,
        )
        db.flush()
        payment = _initialize_mercadopago_payment_or_raise(payment=payment, db=db)
        if payment.get("method") == "mercadopago" and payment.get("provider_status") != PAYMENT_PROVIDER_SETUP_FAILED:
            db.commit()
    except PaymentCheckoutInitializationError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=RETRY_FAILED_MERCADOPAGO_CHECKOUT_UNAVAILABLE,
        ) from exc
    except Exception as exc:
        db.rollback()
        raise_http_error_from_exception(exc, db=db)

    return {"data": payment}


@router.get("/orders/{order_id}/reservations")
def list_order_reservations(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    # Listing reservations also expires stale active reservations first, and
    # the transactional session commits that state transition.
    db: Session = Depends(get_db_transactional),
):
    user_id = get_current_user_id(current_user)
    try:
        reservations = get_order_reservations_for_user(
            user_id=user_id,
            order_id=order_id,
            is_admin=bool(current_user.get("is_admin", False)),
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    return {"data": reservations}

