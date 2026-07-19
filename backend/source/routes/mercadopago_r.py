import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from source.dependencies.auth_d import require_admin
from source.db.session import get_db
from source.errors import raise_http_error_from_exception
from source.schemas import AdminWebhookReplayRequest
from source.services.mercadopago_client import (
    WebhookInvalidSignatureError,
    WebhookNoOpError,
    resolver_evento_webhook_mercadopago,
)
from source.services.webhook_events_s import replay_webhook_event_by_key
from source.services.post_commit_actions_s import clear_post_commit_actions, dispatch_post_commit_actions

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/payments/webhook/mercadopago")
def mercadopago_webhook(
    payload: dict,
    x_signature: str | None = Header(default=None, alias="x-signature"),
    x_request_id: str | None = Header(default=None, alias="x-request-id"),
    db: Session = Depends(get_db),
):
    try:
        result = resolver_evento_webhook_mercadopago(
            payload=payload,
            x_signature=x_signature,
            x_request_id=x_request_id,
            db=db,
        )
        db.commit()
    except WebhookInvalidSignatureError:
        db.rollback()
        clear_post_commit_actions(db=db)
        logger.warning(
            "event=mp_signature_failed request_id=%s",
            x_request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid signature",
        )
    except WebhookNoOpError as exc:
        db.rollback()
        clear_post_commit_actions(db=db)
        logger.info(
            "event=mp_webhook_noop request_id=%s reason=%s",
            x_request_id,
            str(exc),
        )
        return {"data": {"processed": False, "reason": str(exc)}}
    except Exception:
        db.rollback()
        clear_post_commit_actions(db=db)
        logger.exception("event=mp_webhook_error request_id=%s", x_request_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="mercadopago webhook processing failed",
        )

    dispatch_post_commit_actions(db=db, source="mercadopago_webhook")
    logger.info(
        "event=mp_webhook_processed request_id=%s processed=%s",
        x_request_id,
        bool(result.processed),
    )
    return {
        "data": {
            "processed": bool(result.processed),
            "payment": result.payment,
        }
    }


@router.post("/admin/webhooks/mercadopago/replay")
def replay_mercadopago_webhook_event(
    payload: AdminWebhookReplayRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        result = replay_webhook_event_by_key(
            provider="mercadopago",
            event_key=payload.event_key,
            db=db,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        clear_post_commit_actions(db=db)
        raise_http_error_from_exception(exc, db=db)
    dispatch_post_commit_actions(db=db, source="replay_mercadopago_webhook_event")
    return {"data": result}
