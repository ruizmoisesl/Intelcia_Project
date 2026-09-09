"""Horarios personalizados por día: CRUD + resolución.

Reglas:
- Solo SUPERVISOR/ADMIN los crean (se exige en el router): sin flujo de
  aprobación, se aplican de inmediato.
- Modos excluyentes: turno para ese día, u horas exactas (prioridad máxima).
- Un único override por (usuario, fecha): crear de nuevo lo REEMPLAZA.
- Fechas pasadas rechazadas; hoy permitido.
"""
from dataclasses import replace
from datetime import date, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import dates
from app.models.day_override import DayOverride
from app.models.user import ShiftId, User
from app.services import schedule_service
from app.services.schedule_service import DaySchedule, WeekSchedule


class OverrideError(Exception):
    """Error de regla de negocio; el router lo traduce a código HTTP."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------- Consultas ----------

def get_override(db: Session, user_id: int, day: date) -> DayOverride | None:
    stmt = select(DayOverride).where(DayOverride.user_id == user_id, DayOverride.date == day)
    return db.scalars(stmt).first()


def get_overrides_for_range(db: Session, user_id: int, start: date, end: date) -> dict[date, DayOverride]:
    stmt = select(DayOverride).where(
        DayOverride.user_id == user_id,
        DayOverride.date >= start,
        DayOverride.date <= end,
    )
    return {override.date: override for override in db.scalars(stmt)}


# ---------- CRUD ----------

def create_or_replace(
    db: Session,
    *,
    user: User,
    day: date,
    shift: ShiftId | None,
    start: time | None,
    end: time | None,
    reason: str | None,
    created_by: User,
) -> DayOverride:
    has_shift = shift is not None
    has_hours = start is not None and end is not None

    if has_shift == has_hours:  # ambos o ninguno
        raise OverrideError("Indica un turno para el día, O una hora de inicio y fin (no ambos).")
    if (start is not None) != (end is not None):
        raise OverrideError("Las horas personalizadas requieren inicio y fin.")
    if has_hours and start >= end:
        raise OverrideError("La hora de inicio debe ser anterior a la de fin.")
    if day < dates.today():
        raise OverrideError("No se pueden personalizar fechas pasadas.")
    if not user.is_active:
        raise OverrideError("El usuario está inactivo.")

    override = get_override(db, user.id, day)
    if override is None:
        override = DayOverride(user_id=user.id, date=day, created_by_id=created_by.id)
        db.add(override)

    override.shift = shift
    override.start_time = start
    override.end_time = end
    override.reason = (reason or "").strip() or None
    override.created_by_id = created_by.id
    db.commit()
    db.refresh(override)
    return override


def delete_override(db: Session, override: DayOverride) -> None:
    db.delete(override)
    db.commit()


# ---------- Resolución ----------

def resolve_day(db: Session, user_id: int, day: date, base_shift: ShiftId) -> DaySchedule | None:
    """Horario efectivo de una fecha: override > reglas del turno base."""
    override = get_override(db, user_id, day)
    if override is not None:
        if override.start_time is not None and override.end_time is not None:
            return DaySchedule(start=override.start_time, end=override.end_time)
        if override.shift is not None:
            return schedule_service.get_schedule_for_date(override.shift, day)
    return schedule_service.get_schedule_for_date(base_shift, day)


def apply_day_overrides(db: Session, user_id: int, week: WeekSchedule) -> WeekSchedule:
    """Aplica los overrides de la semana sobre un WeekSchedule ya calculado.

    Marca los días afectados (``is_custom`` + ``custom_shift_id``) para que
    la API/UI pueda distinguirlos; el resto de días queda intacto.
    """
    week_end = week.week_start + timedelta(days=6)
    overrides = get_overrides_for_range(db, user_id, week.week_start, week_end)
    if not overrides:
        return week

    days = []
    for entry in week.days:
        override = overrides.get(entry.date)
        if override is None:
            days.append(entry)
        elif override.start_time is not None and override.end_time is not None:
            days.append(
                replace(
                    entry,
                    start=override.start_time,
                    end=override.end_time,
                    is_custom=True,
                    custom_shift_id=None,
                )
            )
        else:
            schedule = schedule_service.get_schedule_for_date(override.shift, entry.date)
            days.append(
                replace(
                    entry,
                    start=schedule.start if schedule else None,
                    end=schedule.end if schedule else None,
                    is_custom=True,
                    custom_shift_id=override.shift,
                )
            )
    return replace(week, days=tuple(days))