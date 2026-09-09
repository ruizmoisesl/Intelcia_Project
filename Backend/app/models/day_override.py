"""Horario personalizado de UN usuario en UNA fecha (supervisor/admin).

Dos modos excluyentes:
- ``shift``: ese día aplican las reglas del turno indicado (incluye sus
  festivos, sábado especial y reducción de miércoles).
- ``start_time``/``end_time``: horas exactas (prioridad máxima: ignoran
  festivos y reducciones, son explícitas).

Cadena de resolución del día: horas exactas > turno del día > cambio semanal
aprobado > rotación/turno fijo > reglas del turno.
"""
from datetime import date, datetime, time

from sqlalchemy import Date, Enum as SAEnum, ForeignKey, Text, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime, utcnow
from app.models.user import ShiftId, User


class DayOverride(Base):
    __tablename__ = "day_overrides"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_day_overrides_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    shift: Mapped[ShiftId | None] = mapped_column(
        SAEnum(ShiftId, name="user_shift", native_enum=False, length=20), nullable=True
    )
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow, server_default=func.now()
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="selectin")
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id], lazy="selectin")

    def __repr__(self) -> str:
        return f"<DayOverride user={self.user_id} date={self.date}>"