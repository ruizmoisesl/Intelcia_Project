"""Contratos de API del módulo de horarios."""
from datetime import date, time

from pydantic import BaseModel

from app.models.user import ShiftId
from app.schemas.user import UserBrief
from app.services.rotation_service import ShiftSource
from app.services.schedule_service import (
    DayEntry,
    Weekday,
    get_shift_definition,
)


def hhmm(value: time | None) -> str | None:
    """Serializa una hora al formato «HH:MM» que consume el frontend."""
    return None if value is None else value.strftime("%H:%M")


def shift_info(shift_id: ShiftId) -> "ShiftInfo":
    definition = get_shift_definition(shift_id)
    return ShiftInfo(id=definition.id, name=definition.name, color=definition.color)


class ShiftInfo(BaseModel):
    id: ShiftId
    name: str
    color: str


class ShiftOut(BaseModel):
    """Entrada del catálogo de turnos (incluye la jornada festiva)."""
    id: str
    name: str
    color: str
    start: str
    end: str


class DayScheduleOut(BaseModel):
    date: date
    weekday: Weekday
    day_name: str
    start: str | None
    end: str | None
    is_holiday: bool = False
    holiday_name: str | None = None


class TodayScheduleOut(BaseModel):
    date: date
    weekday: Weekday
    day_name: str
    start: str | None
    end: str | None
    is_holiday: bool = False
    holiday_name: str | None = None
    shift: ShiftInfo
    source: ShiftSource


class WeekScheduleOut(BaseModel):
    week_start: date
    shift: ShiftInfo
    source: ShiftSource
    days: list[DayScheduleOut]


class RotationEntryOut(BaseModel):
    week_start: date
    shift: ShiftInfo
    source: ShiftSource


class RotationPreviewOut(BaseModel):
    weeks: list[RotationEntryOut]


class TeamMemberOut(BaseModel):
    user: UserBrief
    shift: ShiftInfo
    source: ShiftSource
    override_change_id: int | None = None
    days: list[DayScheduleOut]


class TeamWeekOut(BaseModel):
    week_start: date
    members: list[TeamMemberOut]


def day_out(entry: DayEntry) -> DayScheduleOut:
    return DayScheduleOut(
        date=entry.date,
        weekday=entry.weekday,
        day_name=entry.day_name,
        start=hhmm(entry.start),
        end=hhmm(entry.end),
        is_holiday=entry.is_holiday,
        holiday_name=entry.holiday_name,
    )

class HolidayOut(BaseModel):
    date: date
    name: str


class HolidaysOut(BaseModel):
    year: int
    provider: str  # "google" | "local"
    holidays: list[HolidayOut]

class WeekScheduleOut(BaseModel):
    week_start: date
    today: date  # «hoy» en la zona del negocio: el frontend no calcula fechas
    shift: ShiftInfo
    source: ShiftSource
    days: list[DayScheduleOut]


class TeamWeekOut(BaseModel):
    week_start: date
    today: date
    members: list[TeamMemberOut]