from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == email.strip().lower())
    return db.scalars(stmt).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Usuario si email+contraseña son correctos; None en caso contrario.

    No filtra aquí por `is_active`: el router decide el código de respuesta.
    """
    user = get_user_by_email(db, email)
    if user is None:
        return None
    if not security.verify_password(password, user.password_hash):
        return None
    return user

class AuthError(Exception):
    """Error de regla de negocio; el router lo traduce a código HTTP."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    """Cambia la contraseña verificando la actual. Nunca guarda texto plano."""
    if not security.verify_password(current_password, user.password_hash):
        raise AuthError("La contraseña actual no es correcta", 401)
    if current_password == new_password:
        raise AuthError("La nueva contraseña debe ser diferente a la actual", 400)
    user.password_hash = security.hash_password(new_password)
    db.add(user)
    db.commit()