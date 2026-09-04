"""Novedades de horario (cambios de turno semanales)."""
from datetime import date, datetime, timezone
from app.core import dates

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.schedule_change import ChangeStatus, ScheduleChange
from app.models.user import Role, ShiftId, User
from app.services.schedule_service import to_monday


class ChangeError(Exception):
    """Error de regla de negocio; el router lo traduce a código HTTP."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_change(db: Session, change_id: int) -> ScheduleChange | None:
    return db.get(ScheduleChange, change_id)


def get_pending_change(db: Session, user_id: int, week_start: date) -> ScheduleChange | None:
    stmt = select(ScheduleChange).where(
        ScheduleChange.user_id == user_id,
        ScheduleChange.week_start == week_start,
        ScheduleChange.status == ChangeStatus.PENDING,
    )
    return db.scalars(stmt).first()


def get_effective_change(db: Session, user_id: int, week_start: date) -> ScheduleChange | None:
    """El override vigente: cambio APROBADO para esa semana (el más reciente)."""
    stmt = (
        select(ScheduleChange)
        .where(
            ScheduleChange.user_id == user_id,
            ScheduleChange.week_start == week_start,
            ScheduleChange.status == ChangeStatus.APPROVED,
        )
        .order_by(ScheduleChange.reviewed_at.desc().nulls_last(), ScheduleChange.id.desc())
    )
    return db.scalars(stmt).first()


def list_user_changes(db: Session, user_id: int) -> list[ScheduleChange]:
    stmt = (
        select(ScheduleChange)
        .where(ScheduleChange.user_id == user_id)
        .order_by(ScheduleChange.week_start.desc(), ScheduleChange.id.desc())
    )
    return list(db.scalars(stmt))


def list_changes(
    db: Session,
    status: ChangeStatus | None = None,
    week_start: date | None = None,
    limit: int = 50,
) -> list[ScheduleChange]:
    stmt = select(ScheduleChange).order_by(ScheduleChange.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(ScheduleChange.status == status)
    if week_start is not None:
        stmt = stmt.where(ScheduleChange.week_start == week_start)
    return list(db.scalars(stmt))


def create_change(
    db: Session,
    *,
    user: User,
    week_start: date,
    requested_shift: ShiftId,
    reason: str | None,
    requested_by: User,
) -> ScheduleChange:
    """Crea una novedad.

    - Empleado/Supervisor: PENDING (requiere aprobación y motivo).
    - ADMIN: se crea APPROVED (asignación directa) y reemplaza cualquier
      override anterior de esa semana.
    """
    monday = to_monday(week_start)
    if monday < to_monday(dates.today()):
        raise ChangeError("No se pueden registrar novedades para semanas pasadas.")

    reason_clean = (reason or "").strip() or None
    if requested_by.role != Role.ADMIN and reason_clean is None:
        raise ChangeError("El motivo es obligatorio para solicitar una novedad.")

    if get_pending_change(db, user.id, monday) is not None:
        raise ChangeError("Ya existe una novedad pendiente para esa semana.", 409)

    auto_approved = requested_by.role == Role.ADMIN
    now = datetime.now(timezone.utc)

    if auto_approved:
        previous = get_effective_change(db, user.id, monday)
        if previous is not None:
            previous.status = ChangeStatus.SUPERSEDED
            db.add(previous)

    change = ScheduleChange(
        user_id=user.id,
        week_start=monday,
        requested_shift=requested_shift,
        reason=reason_clean,
        status=ChangeStatus.APPROVED if auto_approved else ChangeStatus.PENDING,
        requested_by_id=requested_by.id,
        reviewed_by_id=requested_by.id if auto_approved else None,
        reviewed_at=now if auto_approved else None,
        review_note="Asignación directa de la administración" if auto_approved else None,
    )
    db.add(change)
    db.commit()
    db.refresh(change)
    return change


def review_change(
    db: Session,
    change: ScheduleChange,
    reviewer: User,
    decision: str,
    note: str | None,
) -> ScheduleChange:
    """Aprueba o rechaza una novedad PENDING.

    Al aprobar, cualquier override anterior de la misma semana pasa a SUPERSEDED.
    """
    if change.status != ChangeStatus.PENDING:
        raise ChangeError("Solo se pueden revisar novedades pendientes.", 409)
    if decision not in ("approve", "reject"):
        raise ChangeError("Decisión inválida.")

    if decision == "approve":
        previous = get_effective_change(db, change.user_id, change.week_start)
        if previous is not None and previous.id != change.id:
            previous.status = ChangeStatus.SUPERSEDED
            db.add(previous)
        change.status = ChangeStatus.APPROVED
    else:
        change.status = ChangeStatus.REJECTED

    change.reviewed_by_id = reviewer.id
    change.reviewed_at = datetime.now(timezone.utc)
    change.review_note = (note or "").strip() or None
    db.add(change)
    db.commit()
    return change


def revert_change(db: Session, change: ScheduleChange) -> None:
    """ADMIN: elimina un cambio aprobado (vuelve a la rotación/turno fijo)."""
    if change.status != ChangeStatus.APPROVED:
        raise ChangeError("Solo se pueden revertir cambios aprobados.", 409)
    db.delete(change)
    db.commit()