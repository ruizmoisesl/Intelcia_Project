"""Endpoints de horarios.

Devuelven el horario EFECTIVO: novedad aprobada > rotación semanal (empleados)
> turno fijo (supervisor/admin), con festivos de Colombia aplicados por fecha.
Toda la lógica vive en los servicios; aquí solo se orquesta y serializa.
"""
from datetime import date
from app.core import dates
from datetime import timedelta
from app.services import day_override_service
from app.schemas.schedule import day_override_out


from app.schemas.schedule import (
    # ... (imports existentes) ...
    HolidayOut,
    HolidaysOut,
)
from app.services import holiday_service, rotation_service, schedule_service

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user, require_supervisor
from app.models.user import Role, ShiftId, User
from app.schemas.schedule import (
    DayScheduleOut,
    RotationEntryOut,
    RotationPreviewOut,
    ShiftInfo,
    ShiftOut,
    TeamMemberOut,
    TeamWeekOut,
    TodayScheduleOut,
    WeekScheduleOut,
    day_out,
    hhmm,
    shift_info,
)
from app.schemas.user import UserBrief
from app.services import rotation_service, schedule_service

router = APIRouter(prefix="/api/v1/schedules", tags=["Horarios"])


@router.get("/shifts", response_model=list[ShiftOut], summary="Catálogo de turnos y colores")
def list_shifts(current_user: User = Depends(get_current_user)) -> list[ShiftOut]:
    out = [
        ShiftOut(
            id=definition.id.value,
            name=definition.name,
            color=definition.color,
            start=definition.weekday_start.strftime("%H:%M"),
            end=definition.weekday_end.strftime("%H:%M"),
        )
        for definition in schedule_service.SHIFTS.values()
    ]
    out.append(
        ShiftOut(
            id="HOLIDAY",
            name=schedule_service.HOLIDAY_SHIFT_NAME,
            color=schedule_service.HOLIDAY_COLOR,
            start=schedule_service.HOLIDAY_DAY_SCHEDULE.start.strftime("%H:%M"),
            end=schedule_service.HOLIDAY_DAY_SCHEDULE.end.strftime("%H:%M"),
        )
    )
    return out


@router.get("/me", response_model=TodayScheduleOut, summary="Horario de hoy del usuario")
def my_schedule_for_today(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> TodayScheduleOut:
    today = dates.today()
    effective = rotation_service.get_effective_shift(db, current_user, today)
    day = day_override_service.resolve_day(db, current_user.id, today, effective.shift_id)
    override = day_override_service.get_override(db, current_user.id, today)
    weekday = schedule_service.weekday_of(today)
    festivo = schedule_service.is_holiday(today)

    return TodayScheduleOut(
        date=today,
        weekday=weekday,
        day_name=schedule_service.WEEKDAY_NAMES_ES[weekday],
        start=hhmm(day.start if day else None),
        end=hhmm(day.end if day else None),
        is_holiday=festivo,
        holiday_name=schedule_service.holiday_name(today) if festivo else None,
        is_custom=override is not None,
        custom_shift=shift_info(override.shift) if override and override.shift else None,
        shift=shift_info(effective.shift_id),
        source=effective.source,
    )


@router.get("/week", response_model=WeekScheduleOut, summary="Semana laboral del usuario")
def my_week_schedule(
    week_start: date | None = Query(default=None, description="Cualquier fecha de la semana (se normaliza a su lunes). ISO: YYYY-MM-DD."),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeekScheduleOut:
    monday = schedule_service.to_monday(week_start or dates.today())
    effective = rotation_service.get_effective_shift(db, current_user, monday)
    week = schedule_service.get_week_schedule(effective.shift_id, monday)
    week = day_override_service.apply_day_overrides(db, current_user.id, week)

    return WeekScheduleOut(
        week_start=week.week_start,
        today=dates.today(),
        shift=shift_info(effective.shift_id),
        source=effective.source,
        days=[day_out(entry) for entry in week.days],
    )

@router.get(
    "/me/rotation",
    response_model=RotationPreviewOut,
    summary="Turno efectivo de las próximas semanas",
)
def my_rotation_preview(
    weeks: int = Query(default=4, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RotationPreviewOut:
    entries = rotation_service.get_rotation_preview(db, current_user, dates.today(), weeks)
    return RotationPreviewOut(
        weeks=[
            RotationEntryOut(
                week_start=entry.week_start,
                shift=shift_info(entry.effective.shift_id),
                source=entry.effective.source,
            )
            for entry in entries
        ]
    )


@router.get("/team/week", response_model=TeamWeekOut, summary="Semana de todo el personal")
def team_week(
    week_start: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),  # antes require_supervisor
    db: Session = Depends(get_db),
) -> TeamWeekOut:
    """Semana efectiva de todo el personal (rotación, cambios aprobados y
    horarios personalizados por día). Abierta a usuarios autenticados para
    que los empleados vean con quién pueden intercambiar turnos al crear
    una novedad; las acciones de gestión siguen en /dashboard/personal."""
    monday = schedule_service.to_monday(week_start or dates.today())
    week_end = monday + timedelta(days=6)

    employees = rotation_service.get_rotating_employees(db)
    staff = db.scalars(
        select(User).where(User.role == Role.SUPERVISOR, User.is_active.is_(True)).order_by(User.name)
    ).all()

    members: list[TeamMemberOut] = []
    for user in [*employees, *staff]:
        effective = rotation_service.get_effective_shift(db, user, monday)
        week = schedule_service.get_week_schedule(effective.shift_id, monday)
        week = day_override_service.apply_day_overrides(db, user.id, week)
        overrides = day_override_service.get_overrides_for_range(db, user.id, monday, week_end)
        members.append(
            TeamMemberOut(
                user=UserBrief.model_validate(user),
                shift=shift_info(effective.shift_id),
                source=effective.source,
                override_change_id=effective.change_id,
                days=[day_out(entry) for entry in week.days],
                day_overrides=[day_override_out(override) for override in overrides.values()],
            )
        )
    return TeamWeekOut(week_start=monday, today=dates.today(), members=members)

@router.get(
    "/holidays",
    response_model=HolidaysOut,
    summary="Festivos del año (calendario oficial)",
)
def list_holidays(
    year: int | None = Query(default=None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
) -> HolidaysOut:
    """Festivos oficiales del año según el proveedor configurado
    (Google Calendar por defecto; cálculo local como respaldo)."""
    target = year if year is not None else dates.today().year
    data = holiday_service.get_holidays(target)
    return HolidaysOut(
        year=target,
        provider=holiday_service.provider_name(target),
        holidays=[HolidayOut(date=day, name=name) for day, name in sorted(data.items())],
    )