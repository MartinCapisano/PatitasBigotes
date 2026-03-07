from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from source.db.models import Notification

ROLE_TARGET_ADMIN = "admin"


def _serialize_notification(row: Notification) -> dict:
    return {
        "id": int(row.id),
        "user_id": int(row.user_id) if row.user_id is not None else None,
        "role_target": row.role_target,
        "event_type": str(row.event_type),
        "title": str(row.title),
        "message": str(row.message),
        "order_id": int(row.order_id) if row.order_id is not None else None,
        "payment_id": int(row.payment_id) if row.payment_id is not None else None,
        "incident_id": int(row.incident_id) if row.incident_id is not None else None,
        "is_read": bool(row.is_read),
        "created_at": row.created_at,
        "read_at": row.read_at,
    }


def _find_by_dedupe_key(*, dedupe_key: str | None, db: Session) -> Notification | None:
    normalized = str(dedupe_key or "").strip()
    if not normalized:
        return None
    return db.query(Notification).filter(Notification.dedupe_key == normalized).first()


def create_admin_notification(
    *,
    event_type: str,
    title: str,
    message: str,
    db: Session,
    order_id: int | None = None,
    payment_id: int | None = None,
    incident_id: int | None = None,
    dedupe_key: str | None = None,
) -> dict:
    existing = _find_by_dedupe_key(dedupe_key=dedupe_key, db=db)
    if existing is not None:
        return _serialize_notification(existing)

    row = Notification(
        user_id=None,
        role_target=ROLE_TARGET_ADMIN,
        event_type=str(event_type).strip(),
        title=str(title).strip(),
        message=str(message).strip(),
        order_id=int(order_id) if order_id is not None else None,
        payment_id=int(payment_id) if payment_id is not None else None,
        incident_id=int(incident_id) if incident_id is not None else None,
        dedupe_key=str(dedupe_key).strip() if dedupe_key else None,
        is_read=False,
    )
    db.add(row)
    db.flush()
    return _serialize_notification(row)


def list_notifications_for_user(
    *,
    user_id: int,
    is_admin: bool,
    unread_only: bool,
    limit: int,
    offset: int,
    db: Session,
) -> tuple[list[dict], dict]:
    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))
    filters = [Notification.user_id == int(user_id)]
    if bool(is_admin):
        filters.append(Notification.role_target == ROLE_TARGET_ADMIN)

    query = db.query(Notification).filter(or_(*filters))
    if bool(unread_only):
        query = query.filter(Notification.is_read.is_(False))

    total = int(query.count())
    rows = (
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(safe_offset)
        .limit(safe_limit)
        .all()
    )

    return (
        [_serialize_notification(row) for row in rows],
        {
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
            "has_more": safe_offset + len(rows) < total,
        },
    )


def get_unread_notification_count(
    *,
    user_id: int,
    is_admin: bool,
    db: Session,
) -> int:
    filters = [Notification.user_id == int(user_id)]
    if bool(is_admin):
        filters.append(Notification.role_target == ROLE_TARGET_ADMIN)

    unread_count = (
        db.query(Notification)
        .filter(or_(*filters), Notification.is_read.is_(False))
        .count()
    )
    return int(unread_count or 0)


def mark_notification_read(
    *,
    notification_id: int,
    user_id: int,
    is_admin: bool,
    db: Session,
) -> dict:
    filters = [Notification.user_id == int(user_id)]
    if bool(is_admin):
        filters.append(Notification.role_target == ROLE_TARGET_ADMIN)

    row = (
        db.query(Notification)
        .filter(Notification.id == int(notification_id), or_(*filters))
        .with_for_update()
        .first()
    )
    if row is None:
        raise LookupError("notification not found")
    if not bool(row.is_read):
        row.is_read = True
        row.read_at = datetime.now(UTC)
        db.flush()
    return _serialize_notification(row)


def mark_all_notifications_read(
    *,
    user_id: int,
    is_admin: bool,
    db: Session,
) -> dict:
    filters = [Notification.user_id == int(user_id)]
    if bool(is_admin):
        filters.append(Notification.role_target == ROLE_TARGET_ADMIN)

    now = datetime.now(UTC)
    query = (
        db.query(Notification)
        .filter(or_(*filters), Notification.is_read.is_(False))
    )
    updated = int(
        query.update(
            {
                Notification.is_read: True,
                Notification.read_at: now,
            },
            synchronize_session=False,
        )
        or 0
    )
    db.flush()
    return {"updated": int(updated)}
