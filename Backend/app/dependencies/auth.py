from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import security
from app.core.database import get_db
from app.models.user import Role, User
from app.services import auth_service

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resuelve el usuario autenticado a partir del Bearer token."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido, expirado o ausente",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = security.decode_access_token(credentials.credentials)
    if payload is None or "sub" not in payload:
        raise unauthorized

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise unauthorized

    user = auth_service.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user

from collections.abc import Callable


def _require_role(*allowed: Role) -> Callable[..., User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para realizar esta acción",
            )
        return user
    return checker


#: Solo ADMIN (asignaciones directas, reversiones).
require_admin: Callable[..., User] = _require_role(Role.ADMIN)
#: SUPERVISOR o ADMIN (aprobadores de novedades, vista de personal).
require_supervisor: Callable[..., User] = _require_role(Role.SUPERVISOR, Role.ADMIN)    