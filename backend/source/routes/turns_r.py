from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from source.dependencies.auth_d import get_current_user, get_current_user_id, require_admin
from source.db.session import get_db, get_db_transactional
from source.errors import raise_http_error_from_exception
from source.schemas import CreateTurnRequest, UpdateTurnStatusRequest
from source.services.turns_s import create_turn_for_user, list_turns_for_admin, update_turn_status_for_admin

router = APIRouter()


@router.post("/turns")
def create_turn(
    payload: CreateTurnRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_transactional),
):
    user_id = get_current_user_id(current_user)
    try:
        turn = create_turn_for_user(
            user_id=user_id,
            scheduled_at=payload.scheduled_at,
            notes=payload.notes,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": turn}


@router.get("/admin/turns")
def admin_list_turns(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        turns = list_turns_for_admin(
            db=db,
            status=status,
            limit=limit,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": turns}


@router.patch("/admin/turns/{turn_id}/status")
def admin_update_turn_status(
    turn_id: int,
    payload: UpdateTurnStatusRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        turn = update_turn_status_for_admin(
            turn_id=turn_id,
            new_status=payload.status,
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)
    return {"data": turn}
