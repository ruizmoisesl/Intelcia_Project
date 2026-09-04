"""CRUD de usuarios (solo ADMIN)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_admin
from app.models.user import Role, User
from app.schemas.user import UserAdminOut, UserCreate, UserListOut, UserUpdate
from app.services import user_service, audit_service


router = APIRouter(prefix="/api/v1/users", tags=["Usuarios"])

@router.get("", response_model=UserListOut, summary="Listar usuarios (admin)")
def list_users(
    role: Role | None = Query(default=None),
    active: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserListOut:
    items, total = user_service.list_users(db, role=role, active=active, limit=limit, offset=offset)
    return UserListOut(total=total, items=items)


# create_user, antes del return:
    audit_service.log(
        db, "USER_CREATED", actor=admin, target=user,
        detail=f"email={user.email}; rol={user.role.value}; turno={user.shift.value}",
    )
    return user

# update_user, tras user_service.update_user(...) y antes del return:
    event = (
        "USER_ACTIVATED" if changes.get("is_active") is True
        else "USER_DEACTIVATED" if changes.get("is_active") is False
        else "USER_UPDATED"
    )
    audit_service.log(db, event, actor=admin, target=user, detail=f"campos: {', '.join(sorted(changes))}")
    return user

# deactivate_user, antes del return None:
    audit_service.log(db, "USER_DEACTIVATED", actor=admin, target=user)
    return None


@router.post("", response_model=UserAdminOut, status_code=201, summary="Crear usuario (admin)")
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    try:
        return user_service.create_user(
            db,
            name=payload.name,
            email=payload.email,
            password=payload.password,
            role=payload.role,
            shift=payload.shift,
            rotation_position=payload.rotation_position,
            is_active=payload.is_active,
        )
    except user_service.UserError as exc:
        raise HTTPException(exc.status_code, exc.message)


@router.get("/{user_id}", response_model=UserAdminOut, summary="Detalle de usuario (admin)")
def get_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado")
    return user


@router.patch("/{user_id}", response_model=UserAdminOut, summary="Actualizar usuario (admin)")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado")
    changes = payload.model_dump(exclude_unset=True)  # solo lo enviado
    try:
        return user_service.update_user(db, user, changes=changes, actor=admin)
    except user_service.UserError as exc:
        raise HTTPException(exc.status_code, exc.message)


@router.delete("/{user_id}", status_code=204, summary="Desactivar usuario (admin)")
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Borrado lógico: el usuario queda inactivo (se conserva el histórico)."""
    user = user_service.get_user(db, user_id)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado")
    try:
        user_service.deactivate_user(db, user, actor=admin)
    except user_service.UserError as exc:
        raise HTTPException(exc.status_code, exc.message)
    return None