import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, String, func, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.database import Base, UTCDateTime, utcnow


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    SUPERVISOR = "SUPERVISOR"
    EMPLOYEE = "EMPLOYEE"


class ShiftId(str, enum.Enum):
    """Representación controlada de turnos (nunca texto libre)."""
    SHIFT_1 = "SHIFT_1"
    SHIFT_2 = "SHIFT_2"
    SHIFT_3 = "SHIFT_3"
    SHIFT_4 = "SHIFT_4"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="user_role", native_enum=False, length=20),
        nullable=False,
        default=Role.EMPLOYEE,
    )
    shift: Mapped[ShiftId] = mapped_column(
        SAEnum(ShiftId, name="user_shift", native_enum=False, length=20),
        nullable=False,
    )
    # ... tras la columna shift:
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    #: Posición dentro de la rotación semanal de turnos (solo EMPLOYEE).
    #: Orden: rotation_position NULLS LAST, luego id.
    rotation_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role.value}>"