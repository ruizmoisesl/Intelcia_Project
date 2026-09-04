from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import rate_limit, security
from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse
from app.schemas.user import UserPublic
from app.services import audit_service, auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["Autenticación"])


@router.post("/login", response_model=TokenResponse, summary="Iniciar sesión")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.strip().lower()

    if rate_limit.is_blocked(email):
        audit_service.log(db, "LOGIN_RATE_LIMITED", detail=f"email={email}")
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.",
        )

    user = auth_service.authenticate(db, payload.email, payload.password)
    if user is None:
        rate_limit.record_failure(email)
        audit_service.log(db, "LOGIN_FAILED", detail=f"email={email}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    if not user.is_active:
        rate_limit.record_failure(email)
        audit_service.log(db, "LOGIN_FAILED", detail=f"email={email} (cuenta desactivada)")
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="La cuenta está desactivada")

    rate_limit.reset(email)
    audit_service.log(db, "LOGIN_SUCCESS", actor=user)

    token = security.create_access_token(user_id=user.id, role=user.role.value)
    return TokenResponse(access_token=token, user=UserPublic.model_validate(user))


@router.get("/me", response_model=UserPublic, summary="Usuario autenticado")
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/change-password", status_code=204, summary="Cambiar mi contraseña")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        auth_service.change_password(db, current_user, payload.current_password, payload.new_password)
    except auth_service.AuthError as exc:
        raise HTTPException(exc.status_code, exc.message)
    audit_service.log(db, "PASSWORD_CHANGED", actor=current_user)
    return None