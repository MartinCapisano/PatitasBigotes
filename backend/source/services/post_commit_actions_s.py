from __future__ import annotations

import logging
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from source.services.email_s import (
    BankTransferInstructionsEmailPayload,
    OrderPaidEmailPayload,
    send_bank_transfer_instructions_email,
    send_email_verification,
    send_order_paid_email,
    send_password_reset,
)

logger = logging.getLogger(__name__)

POST_COMMIT_ACTIONS_KEY = "post_commit_actions"
SKIP_ORDER_PAID_EMAIL_KEY = "skip_order_paid_email"
ACTION_ORDER_PAID_EMAIL = "order_paid_email"
ACTION_BANK_TRANSFER_INSTRUCTIONS_EMAIL = "bank_transfer_instructions_email"
ACTION_EMAIL_VERIFICATION = "email_verification"
ACTION_PASSWORD_RESET = "password_reset"


class PostCommitAction(TypedDict):
    kind: str
    payload: dict[str, Any]


def enqueue_post_commit_order_paid_email(*, payload: OrderPaidEmailPayload, db: Session) -> None:
    actions = db.info.setdefault(POST_COMMIT_ACTIONS_KEY, [])
    actions.append(
        PostCommitAction(
            kind=ACTION_ORDER_PAID_EMAIL,
            payload=dict(payload),
        )
    )


def enqueue_post_commit_bank_transfer_instructions_email(
    *, payload: BankTransferInstructionsEmailPayload, db: Session
) -> None:
    actions = db.info.setdefault(POST_COMMIT_ACTIONS_KEY, [])
    actions.append(
        PostCommitAction(
            kind=ACTION_BANK_TRANSFER_INSTRUCTIONS_EMAIL,
            payload=dict(payload),
        )
    )


def enqueue_post_commit_email_verification(
    *, to_email: str, verify_link: str, db: Session
) -> None:
    actions = db.info.setdefault(POST_COMMIT_ACTIONS_KEY, [])
    actions.append(
        PostCommitAction(
            kind=ACTION_EMAIL_VERIFICATION,
            payload={"to_email": to_email, "verify_link": verify_link},
        )
    )


def enqueue_post_commit_password_reset(
    *, to_email: str, reset_link: str, db: Session
) -> None:
    actions = db.info.setdefault(POST_COMMIT_ACTIONS_KEY, [])
    actions.append(
        PostCommitAction(
            kind=ACTION_PASSWORD_RESET,
            payload={"to_email": to_email, "reset_link": reset_link},
        )
    )


def should_skip_order_paid_email(*, db: Session) -> bool:
    return bool(db.info.get(SKIP_ORDER_PAID_EMAIL_KEY, False))


def set_skip_order_paid_email(*, db: Session, value: bool) -> None:
    db.info[SKIP_ORDER_PAID_EMAIL_KEY] = bool(value)


def clear_post_commit_actions(*, db: Session) -> None:
    db.info[POST_COMMIT_ACTIONS_KEY] = []


def dispatch_post_commit_actions(*, db: Session, source: str) -> None:
    actions = list(db.info.get(POST_COMMIT_ACTIONS_KEY, []))
    clear_post_commit_actions(db=db)

    for action in actions:
        kind = str(action.get("kind") or "").strip().lower()
        payload = action.get("payload") or {}
        if kind == ACTION_ORDER_PAID_EMAIL:
            try:
                send_order_paid_email(payload=payload)
            except Exception:
                logger.exception(
                    "event=order_paid_email_failed source=%s order_id=%s payment_id=%s to_email=%s",
                    source,
                    payload.get("order_id"),
                    payload.get("payment_id"),
                    payload.get("to_email"),
                )
        elif kind == ACTION_BANK_TRANSFER_INSTRUCTIONS_EMAIL:
            # Swallowed like the one above: the order and its payment are
            # already committed, and a dead SMTP server must not undo a
            # purchase. The customer still has the instructions on screen.
            try:
                send_bank_transfer_instructions_email(payload=payload)
            except Exception:
                logger.exception(
                    "event=bank_transfer_instructions_email_failed source=%s order_id=%s payment_id=%s to_email=%s",
                    source,
                    payload.get("order_id"),
                    payload.get("payment_id"),
                    payload.get("to_email"),
                )
        elif kind == ACTION_EMAIL_VERIFICATION:
            # El link lleva el token de un solo uso, asi que nunca entra al log.
            try:
                send_email_verification(
                    to_email=str(payload.get("to_email") or ""),
                    verify_link=str(payload.get("verify_link") or ""),
                )
            except Exception:
                logger.exception(
                    "event=post_commit_action_failed kind=%s source=%s to_email=%s",
                    ACTION_EMAIL_VERIFICATION,
                    source,
                    payload.get("to_email"),
                )
        elif kind == ACTION_PASSWORD_RESET:
            try:
                send_password_reset(
                    to_email=str(payload.get("to_email") or ""),
                    reset_link=str(payload.get("reset_link") or ""),
                )
            except Exception:
                logger.exception(
                    "event=post_commit_action_failed kind=%s source=%s to_email=%s",
                    ACTION_PASSWORD_RESET,
                    source,
                    payload.get("to_email"),
                )
