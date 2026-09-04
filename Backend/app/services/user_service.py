"""CRUD de usuarios. Reglas:
- Solo ADMIN accede (se exige en el router).
- DELETE = desactivación lógica: se conserva el histórico de novedades.
- Protección de autoadministración: nadie se desactiva ni se cambia su
  propio rol (evita quedarse sin acceso administrativo).
- Emails normalizados (minúsculas, sin espacios) y únicos.
"""
from datetime import datetime, timezone

from sqlalchemy import func,select
from sqlalchemy.orm import Session

from app.core import security
from app.models.user import Role, ShiftId, User


class UserError(Exception):
    """Error de regla de negocio; el router lo traduce a código HTTP."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def list_users(
    db: Session,
    *,
    role: Role | None = None,
    active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[User], int]:
    conditions = []
    if role is not None:
        conditions.append(User.role == role)
    if active is not None:
        conditions.append(User.is_active.is_(active))

    count_stmt = select(func.count()).select_from(User)
    stmt = select(User)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
        stmt = stmt.where(*conditions)

    total = db.scalar(count_stmt) or 0
    items = list(db.scalars(stmt.order_by(User.name).limit(limit).offset(offset)))
    return items, total


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _assert_email_free(db: Session, email: str, *, exclude_id: int | None = None) -> None:
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing is not None and existing.id != exclude_id:
        raise UserError("Ya existe un usuario con ese correo", 409)


def create_user(
    db: Session,
    *,
    name: str,
    email: str,
    password: str,
    role: Role,
    shift: ShiftId,
    rotation_position: int | None,
    is_active: bool,
) -> User:
    email = _normalize_email(email)
    _assert_email_free(db, email)
    user = User(
        name=name.strip(),
        email=email,
        password_hash=security.hash_password(password),  # nunca texto plano
        role=role,
        shift=shift,
        rotation_position=rotation_position if role == Role.EMPLOYEE else None,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


#: Campos editables vía PATCH (la validación de tipos la hacen los schemas).
EDITABLE_FIELDS = {"name", "email", "password", "role", "shift", "rotation_position", "is_active"}


def update_user(db: Session, user: User, *, changes: dict, actor: User) -> User:
    """Actualiza un usuario aplicando SOLO los campos presentes en ``changes``.

    ``changes`` proviene de ``UserUpdate.model_dump(exclude_unset=True)``:
    una clave presente con ``None`` significa «borrar el valor» (p. ej.
    limpiar la posición de rotación).
    """
    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise UserError(f"Campos no editables: {', '.join(sorted(unknown))}")

    if user.id == actor.id:
        if changes.get("is_active") is False:
            raise UserError("No puedes desactivar tu propia cuenta", 400)
        if "role" in changes and changes["role"] != user.role:
            raise UserError("No puedes cambiar tu propio rol", 400)

    if "name" in changes:
        user.name = str(changes["name"]).strip()
    if "email" in changes:
        email = _normalize_email(str(changes["email"]))
        _assert_email_free(db, email, exclude_id=user.id)
        user.email = email
    if "password" in changes and changes["password"]:
        user.password_hash = security.hash_password(str(changes["password"]))
    if "role" in changes:
        user.role = changes["role"]
        if user.role != Role.EMPLOYEE:
            user.rotation_position = None  # la rotación solo aplica a empleados
    if "shift" in changes:
        user.shift = changes["shift"]
    if "rotation_position" in changes:
        position = changes["rotation_position"]
        if user.role != Role.EMPLOYEE and position is not None:
            raise UserError("La posición de rotación solo aplica a empleados", 400)
        user.rotation_position = position
    if "is_active" in changes:
        user.is_active = bool(changes["is_active"])

    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def deactivate_user(db: Session, user: User, *, actor: User) -> None:
    """Borrado lógico: desactiva en lugar de eliminar (preserva histórico)."""
    if user.id == actor.id:
        raise UserError("No puedes desactivar tu propia cuenta", 400)
    user.is_active = False
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()