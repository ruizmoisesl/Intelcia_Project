"""Novedades de horario: solicitudes de cambio de turno semanal.

Unifica dos flujos sobre la misma tabla:
- Novedad solicitada por el usuario (estado inicial PENDING, requiere aprobación).
- Asignación directa del ADMIN (se crea ya APPROVED).

Un cambio APPROVED es el único «override» del turno de esa semana; si se
aprueba otro para la misma semana, el anterior pasa a SUPERSEDED.
"""
import enum
from datetime import date, datetime
from app.core.database import Base, UTCDateTime, utcnow

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import ShiftId, User


class ChangeStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class ScheduleChange(Base):
    __tablename__ = "schedule_changes"
    __table_args__ = (Index("ix_schedule_changes_user_week", "user_id", "week_start"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)  # siempre un lunes
    requested_shift: Mapped[ShiftId] = mapped_column(
        SAEnum(ShiftId, name="user_shift", native_enum=False, length=20), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ChangeStatus] = mapped_column(
        SAEnum(ChangeStatus, name="change_status", native_enum=False, length=20),
        nullable=False,
        default=ChangeStatus.PENDING,
    )

    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at:  Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )
    reviewed_at:  Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at:  Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="selectin")
    requested_by: Mapped[User] = relationship(foreign_keys=[requested_by_id], lazy="selectin")
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id], lazy="selectin")

    def __repr__(self) -> str:
        return f"<ScheduleChange id={self.id} user={self.user_id} week={self.week_start} {self.status.value}>"