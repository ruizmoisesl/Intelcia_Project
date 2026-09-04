"""Dominio de horarios: ÚNICA fuente de verdad de las reglas de turno.

Responsabilidades (toda la lógica de horarios vive aquí, nunca en frontend):
- Definición declarativa de los turnos con su color corporativo.
- Regla general L–V: desde el miércoles la SALIDA se reduce una hora.
- Horarios especiales por día (sábado del Turno 2 = 07:00–16:00, sin reducción).
- Festivos (v0.3, por FECHA):
  * Turno 2 NO trabaja festivos: descansa (los compensa con los sábados).
  * El resto de turnos con horario ese día trabajan la jornada festiva fija.
  * Un festivo nunca crea turno en días de descanso.
- La fuente de festivos es ``holiday_service`` (Google Calendar oficial con
  fallback local); este módulo no conoce proveedores.

Los horarios se CALCULAN. El turno semanal efectivo de cada usuario lo resuelve
``rotation_service``; este módulo no consulta la base de datos.
"""
import enum
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.schedule_change import ScheduleChange
from app.models.user import Role, ShiftId, User
from app.services import holiday_service
from app.services import schedule_change_service


class ShiftSource(str, enum.Enum):
    FIXED = "FIXED"
    ROTATION = "ROTATION"
    APPROVED_CHANGE = "APPROVED_CHANGE"


@dataclass(frozen=True)
class EffectiveShift:
    shift_id: ShiftId
    source: ShiftSource
    change_id: int | None = None


@dataclass(frozen=True)
class RotationEntry:
    week_start: date
    effective: EffectiveShift


class Weekday(str, enum.Enum):
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"


WEEKDAY_ORDER: tuple[Weekday, ...] = (
    Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY,
    Weekday.FRIDAY, Weekday.SATURDAY, Weekday.SUNDAY,
)

WEEKDAY_NAMES_ES: dict[Weekday, str] = {
    Weekday.MONDAY: "Lunes", Weekday.TUESDAY: "Martes", Weekday.WEDNESDAY: "Miércoles",
    Weekday.THURSDAY: "Jueves", Weekday.FRIDAY: "Viernes", Weekday.SATURDAY: "Sábado",
    Weekday.SUNDAY: "Domingo",
}

_MONDAY_TO_FRIDAY = frozenset(
    {Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY, Weekday.FRIDAY}
)
_DAYS_WITH_REDUCED_END = frozenset({Weekday.WEDNESDAY, Weekday.THURSDAY, Weekday.FRIDAY})


@dataclass(frozen=True)
class DaySchedule:
    start: time
    end: time


@dataclass(frozen=True)
class ShiftDefinition:
    """Definición declarativa de un turno (con color corporativo)."""

    id: ShiftId
    name: str
    weekday_start: time
    weekday_end: time
    color: str = "slate"
    end_reduction_hours: int = 1
    special_days: Mapping[Weekday, DaySchedule] = field(default_factory=dict)


#: Jornada de los días festivos de Colombia.
#: DECISIÓN (horas no especificadas en requisitos): 08:00–14:00.
#: Para cambiarla solo se edita esta constante.
HOLIDAY_DAY_SCHEDULE = DaySchedule(start=time(8, 0), end=time(14, 0))
HOLIDAY_COLOR = "purple"
HOLIDAY_SHIFT_NAME = "Jornada festiva"

#: Turnos que NO trabajan festivos (descansan ese día).
#: El Turno 2 compensa los festivos trabajando sábados (07:00–16:00).
#: DECISIÓN (festivo que cae en sábado): el festivo prevalece → también descansa.
SHIFTS_WITH_HOLIDAY_OFF: frozenset[ShiftId] = frozenset({ShiftId.SHIFT_2})

#: Los cuatro turnos de la empresa con su color:
#: verde 07:00–17:00 · azul 08:00–15:00 · rojo 13:00–22:00 · amarillo 00:00–10:00
SHIFTS: dict[ShiftId, ShiftDefinition] = {
    ShiftId.SHIFT_1: ShiftDefinition(
        id=ShiftId.SHIFT_1, name="MAÑANA",
        weekday_start=time(7, 0), weekday_end=time(17, 0), color="green",
    ),
    ShiftId.SHIFT_2: ShiftDefinition(
        id=ShiftId.SHIFT_2, name="SABADO",
        weekday_start=time(8, 0), weekday_end=time(15, 0), color="blue",
        special_days={Weekday.SATURDAY: DaySchedule(time(7, 0), time(16, 0))},
    ),
    ShiftId.SHIFT_3: ShiftDefinition(
        id=ShiftId.SHIFT_3, name="NOCHE",
        weekday_start=time(13, 0), weekday_end=time(22, 0), color="red",
    ),
    ShiftId.SHIFT_4: ShiftDefinition(
        id=ShiftId.SHIFT_4, name="MADRUGADA",
        weekday_start=time(0, 0),  # medianoche: tipo time real, no texto
        weekday_end=time(10, 0), color="yellow",
    ),
}


def to_monday(day: date) -> date:
    """Normaliza cualquier fecha al lunes de su semana."""
    return day - timedelta(days=day.weekday())


def weekday_of(day: date) -> Weekday:
    return WEEKDAY_ORDER[day.weekday()]


def get_shift_definition(shift_id: ShiftId) -> ShiftDefinition:
    return SHIFTS[shift_id]


def is_holiday(day: date) -> bool:
    return holiday_service.is_holiday(day)


def holiday_name(day: date) -> str | None:
    return holiday_service.holiday_name(day)


def get_schedule_for_weekday(shift_id: ShiftId, weekday: Weekday) -> DaySchedule | None:
    """Horario de un día de semana concreto; ``None`` si no hay turno.

    Orden de resolución:
      1. Horario especial del día (si existe) — sin reducción.
      2. Lunes–viernes: horario base, con salida reducida desde el miércoles.
      3. Sábado sin regla especial y domingos: sin turno.
    """
    definition = SHIFTS[shift_id]

    special = definition.special_days.get(weekday)
    if special is not None:
        return special

    if weekday not in _MONDAY_TO_FRIDAY:
        return None

    end = definition.weekday_end
    if weekday in _DAYS_WITH_REDUCED_END and definition.end_reduction_hours > 0:
        end = _subtract_hours(end, definition.end_reduction_hours)

    return DaySchedule(start=definition.weekday_start, end=end)


def get_schedule_for_date(shift_id: ShiftId, day: date) -> DaySchedule | None:
    """Horario de una FECHA concreta, aplicando festivos de Colombia.

    - Festivo + Turno 2: DESCANSO (compensa los festivos trabajando sábados),
      incluso si el festivo cae en sábado.
    - Festivo + resto de turnos con horario ese día: jornada festiva fija
      (sin reducción de miércoles).
    - Festivo en día de descanso: sigue siendo descanso.
    """
    base = get_schedule_for_weekday(shift_id, weekday_of(day))
    if base is None:
        return None
    if is_holiday(day):
        if shift_id in SHIFTS_WITH_HOLIDAY_OFF:
            return None
        return HOLIDAY_DAY_SCHEDULE
    return base


@dataclass(frozen=True)
class DayEntry:
    date: date
    weekday: Weekday
    day_name: str
    start: time | None
    end: time | None
    is_holiday: bool = False
    holiday_name: str | None = None


@dataclass(frozen=True)
class WeekSchedule:
    week_start: date  # siempre un lunes
    shift_id: ShiftId
    days: tuple[DayEntry, ...]


def get_week_schedule(shift_id: ShiftId, reference: date) -> WeekSchedule:
    """Semana completa (lunes–domingo) que contiene la fecha de referencia."""
    monday = to_monday(reference)

    days: list[DayEntry] = []
    for offset in range(7):
        current = monday + timedelta(days=offset)
        weekday = weekday_of(current)
        schedule = get_schedule_for_date(shift_id, current)
        festivo = is_holiday(current)
        days.append(
            DayEntry(
                date=current,
                weekday=weekday,
                day_name=WEEKDAY_NAMES_ES[weekday],
                start=schedule.start if schedule else None,
                end=schedule.end if schedule else None,
                is_holiday=festivo,
                holiday_name=holiday_name(current) if festivo else None,
            )
        )

    return WeekSchedule(week_start=monday, shift_id=shift_id, days=tuple(days))


def _subtract_hours(value: time, hours: int) -> time:
    total_minutes = value.hour * 60 + value.minute - hours * 60
    if total_minutes < 0:
        raise ValueError(f"No se pueden restar {hours} h a {value.isoformat()}")
    return time(total_minutes // 60, total_minutes % 60)


ROTATION_ANCHOR = date(2025, 1, 6)


def get_rotating_employees(db: Session) -> list[User]:
    stmt = (
        select(User)
        .where(
            User.role == Role.EMPLOYEE,
            User.is_active.is_(True),
            User.rotation_position.is_not(None),
        )
        .order_by(User.rotation_position.asc(), User.id.asc())
    )
    return list(db.scalars(stmt))


def _rotated_shift(user: User, week_start: date) -> ShiftId:
    weeks_since_anchor = (to_monday(week_start) - ROTATION_ANCHOR).days // 7
    shift_index = (user.rotation_position - 1 + weeks_since_anchor) % len(ShiftId)
    return list(ShiftId)[shift_index]


def get_effective_shift(db: Session, user: User, reference: date) -> EffectiveShift:
    monday = to_monday(reference)
    change = schedule_change_service.get_effective_change(db, user.id, monday)
    if change is not None:
        return EffectiveShift(
            shift_id=change.requested_shift,
            source=ShiftSource.APPROVED_CHANGE,
            change_id=change.id,
        )
    if user.role == Role.EMPLOYEE and user.rotation_position is not None:
        return EffectiveShift(shift_id=_rotated_shift(user, monday), source=ShiftSource.ROTATION)
    return EffectiveShift(shift_id=user.shift, source=ShiftSource.FIXED)


def get_rotation_preview(
    db: Session, user: User, reference: date, weeks: int
) -> list[RotationEntry]:
    monday = to_monday(reference)
    return [
        RotationEntry(
            week_start=monday + timedelta(weeks=offset),
            effective=get_effective_shift(db, user, monday + timedelta(weeks=offset)),
        )
        for offset in range(weeks)
    ]