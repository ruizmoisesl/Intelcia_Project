"""Dominio de horarios: ÚNICA fuente de verdad de las reglas de turno.

Responsabilidades (toda la lógica de horarios vive aquí, nunca en frontend):
- Definición declarativa de los turnos con su color corporativo.
- Regla general L–V: desde el miércoles la SALIDA se reduce una hora.
- Horarios especiales por día (sábado del Turno 2 = 07:00–16:00, sin reducción).
- Festivos de Colombia: reemplazan el horario del día por la jornada festiva
  (fija, sin reducción) únicamente si ese turno tendría horario ese día.

Los horarios se CALCULAN. El turno semanal efectivo de cada usuario lo resuelve
``rotation_service`` (rotación / turno fijo / novedad aprobada); este módulo no
consulta la base de datos.

Nota v0.2: ``get_schedule_for_day(shift, weekday)`` pasó a llamarse
``get_schedule_for_weekday`` porque ahora existe ``get_schedule_for_date``,
que además aplica festivos (necesita la fecha, no solo el día de semana).
"""
import enum
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Mapping

from app.models.user import ShiftId
from app.services import colombian_holidays


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

#: Los cuatro turnos de la empresa con su color:
#: verde 07:00–17:00 · azul 08:00–15:00 · rojo 13:00–22:00 · amarillo 00:00–10:00
SHIFTS: dict[ShiftId, ShiftDefinition] = {
    ShiftId.SHIFT_1: ShiftDefinition(
        id=ShiftId.SHIFT_1, name="Mañana",
        weekday_start=time(7, 0), weekday_end=time(17, 0), color="green",
    ),
    ShiftId.SHIFT_2: ShiftDefinition(
        id=ShiftId.SHIFT_2, name="Sabado",
        weekday_start=time(8, 0), weekday_end=time(15, 0), color="blue",
        special_days={Weekday.SATURDAY: DaySchedule(time(7, 0), time(16, 0))},
    ),
    ShiftId.SHIFT_3: ShiftDefinition(
        id=ShiftId.SHIFT_3, name="Noche",
        weekday_start=time(13, 0), weekday_end=time(22, 0), color="red",
    ),
    ShiftId.SHIFT_4: ShiftDefinition(
        id=ShiftId.SHIFT_4, name="Madrugada",
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
    return colombian_holidays.is_colombian_holiday(day)


def holiday_name(day: date) -> str | None:
    return colombian_holidays.holiday_name(day)


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


def get_schedule_for_day(shift_id: ShiftId, weekday: Weekday) -> DaySchedule | None:
    """Compatibilidad con el nombre público usado por clientes anteriores."""
    return get_schedule_for_weekday(shift_id, weekday)


def get_schedule_for_date(shift_id: ShiftId, day: date) -> DaySchedule | None:
    """Horario de una FECHA concreta, aplicando festivos de Colombia.

    Un festivo reemplaza el horario normal (jornada fija, sin reducción de
    miércoles) solo para turnos que ese día tendrían horario; nunca crea
    turno en días de descanso.
    """
    base = get_schedule_for_weekday(shift_id, weekday_of(day))
    if base is None:
        return None
    if is_holiday(day):
        if shift_id == ShiftId.SHIFT_2:
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