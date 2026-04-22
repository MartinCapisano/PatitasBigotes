from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from source.dependencies.auth_d import get_current_user, get_current_user_id
from source.db.session import get_db, get_db_transactional
from source.errors import raise_http_error_from_exception
from source.services.notifications_s import (
    get_unread_notification_count,
    list_notifications_for_user,
    mark_all_notifications_read,
    mark_notification_read,
)

router = APIRouter()


@router.get("/notifications")
def list_notifications(
    unread_only: bool = False,
    limit: int = 20,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(current_user)
    try:
        rows, meta = list_notifications_for_user(
            user_id=int(user_id),
            is_admin=bool(current_user.get("is_admin", False)),
            unread_only=bool(unread_only),
            limit=limit,
            offset=offset,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": rows, "meta": meta}


@router.get("/notifications/unread-count")
def unread_notification_count(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = get_current_user_id(current_user)
    try:
        unread_count = get_unread_notification_count(
            user_id=int(user_id),
            is_admin=bool(current_user.get("is_admin", False)),
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": {"unread_count": int(unread_count)}}


@router.post("/notifications/{notification_id}/read")
def read_notification(
    notification_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_transactional),
):
    user_id = get_current_user_id(current_user)
    try:
        row = mark_notification_read(
            notification_id=notification_id,
            user_id=int(user_id),
            is_admin=bool(current_user.get("is_admin", False)),
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": row}


@router.post("/notifications/read-all")
def read_all_notifications(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_transactional),
):
    user_id = get_current_user_id(current_user)
    try:
        payload = mark_all_notifications_read(
            user_id=int(user_id),
            is_admin=bool(current_user.get("is_admin", False)),
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": payload}
