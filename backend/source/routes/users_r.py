from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from source.dependencies.auth_d import get_current_user_id, require_admin
from source.db.session import get_db_transactional
from source.errors import raise_http_error_from_exception
from source.schemas import CreateAdminUserRequest, ResolveUserRequest
from source.services.users_s import create_admin_user as create_admin_user_service
from source.services.users_s import revoke_admin_status as revoke_admin_status_service
from source.services.users_s import resolve_user as resolve_user_service
from source.services.users_s import search_users as search_users_service

router = APIRouter()


@router.get("/users/search")
def search_users(
    email: str | None = None,
    dni: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    limit: int = 20,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        users = search_users_service(
            db=db,
            email=email,
            dni=dni,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            limit=limit,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    return {"data": users}


@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
def create_admin_user(
    payload: CreateAdminUserRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        result = create_admin_user_service(payload=payload, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    return {"data": result}


@router.post("/admin/users/{user_id}/revoke-admin")
def revoke_admin_user(
    user_id: int,
    admin_user: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    actor_user_id = get_current_user_id(admin_user)
    try:
        result = revoke_admin_status_service(
            target_user_id=int(user_id),
            actor_user_id=int(actor_user_id),
            db=db,
        )
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    return {"data": result}


@router.post("/users/resolve")
def resolve_user(
    payload: ResolveUserRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db_transactional),
):
    try:
        result = resolve_user_service(payload=payload, db=db)
    except Exception as exc:
        raise_http_error_from_exception(exc, db=db)

    return {"data": result}
