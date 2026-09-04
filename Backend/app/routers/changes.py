"""Endpoints de novedades de horario (cambios de turno semanales)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from datetime import date

from app.services import schedule_change_service
from app.core.database import get_db
from app.dependencies.auth import get_current_user, require_admin, require_supervisor
from app.models.schedule_change import ChangeStatus
from app.models.user import Role, User
from app.schemas.change import ChangeCreateRequest, ChangeOut, ReviewRequest
from app.schemas.schedule import shift_info
from app.schemas.user import UserBrief
from app.services import audit_service, auth_service, rotation_service, schedule_change_service
from app.services.schedule_service import to_monday

router = APIRouter(prefix="/api/v1/changes", tags=["Novedades de horario"])


def _change_to_out(db: Session, change) -> ChangeOut:
    current = rotation_service.get_effective_shift(db, change.user, change.week_start)
    return ChangeOut(
        id=change.id,
        user=UserBrief.model_validate(change.user),
        week_start=change.week_start,
        requested_shift=shift_info(change.requested_shift),
        reason=change.reason,
        status=change.status,
        review_note=change.review_note,
        requested_by=UserBrief.model_validate(change.requested_by),
        reviewed_by=UserBrief.model_validate(change.reviewed_by) if change.reviewed_by else None,
        created_at=change.created_at,
        reviewed_at=change.reviewed_at,
        current_shift=shift_info(current.shift_id),
    )


@router.post("", response_model=ChangeOut, status_code=201, summary="Crear novedad/asignación")
def create_change(
    payload: ChangeCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Empleado/Supervisor: solicitud PENDING para sí mismos.
    ADMIN: asignación directa (APPROVED), para sí o para otro usuario."""
    if payload.user_id is not None and payload.user_id != current_user.id:
        if current_user.role != Role.ADMIN:
            raise HTTPException(403, "Solo un administrador puede gestionar horarios de otros usuarios")
        target = auth_service.get_user_by_id(db, payload.user_id)
        if target is None:
            raise HTTPException(404, "Usuario no encontrado")
    else:
        target = current_user

    try:
        change = schedule_change_service.create_change(
            db,
            user=target,
            week_start=payload.week_start,
            requested_shift=payload.requested_shift,
            reason=payload.reason,
            requested_by=current_user,
        )
    except schedule_change_service.ChangeError as exc:
        raise HTTPException(exc.status_code, exc.message)

    audit_service.log(
        db, "CHANGE_CREATED", actor=current_user, target=target,
        detail=f"semana {change.week_start} → {change.requested_shift.value} ({change.status.value})",
    )

    return _change_to_out(db, change)


@router.get("/me", response_model=list[ChangeOut], summary="Mis novedades")
def my_changes(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ChangeOut]:
    return [_change_to_out(db, change) for change in schedule_change_service.list_user_changes(db, current_user.id)]


@router.get("/pending", response_model=list[ChangeOut], summary="Novedades pendientes (supervisor/admin)")
def pending_changes(
    week_start=None,
    supervisor: User = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    week = to_monday(week_start) if week_start else None
    changes = schedule_change_service.list_changes(db, status=ChangeStatus.PENDING, week_start=week)
    return [_change_to_out(db, change) for change in changes]


@router.get("", response_model=list[ChangeOut], summary="Historial de novedades (supervisor/admin)")
def all_changes(
    status_filter: ChangeStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    supervisor: User = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    changes = schedule_change_service.list_changes(db, status=status_filter, limit=limit)
    return [_change_to_out(db, change) for change in changes]


@router.post("/{change_id}/approve", response_model=ChangeOut, summary="Aprobar novedad")
def approve_change(
    change_id: int,
    payload: ReviewRequest | None = None,
    supervisor: User = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    change = schedule_change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(404, "Novedad no encontrada")
    try:
        change = schedule_change_service.review_change(
            db, change, supervisor, "approve", payload.note if payload else None
        )
    except schedule_change_service.ChangeError as exc:
        raise HTTPException(exc.status_code, exc.message)

    audit_service.log(
        db, "CHANGE_APPROVED", actor=supervisor, target=change.user,
        detail=f"semana {change.week_start} → {change.requested_shift.value}",
    )

    return _change_to_out(db, change)


@router.post("/{change_id}/reject", response_model=ChangeOut, summary="Rechazar novedad")
def reject_change(
    change_id: int,
    payload: ReviewRequest | None = None,
    supervisor: User = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    change = schedule_change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(404, "Novedad no encontrada")
    try:
        change = schedule_change_service.review_change(
            db, change, supervisor, "reject", payload.note if payload else None
        )
    except schedule_change_service.ChangeError as exc:
        raise HTTPException(exc.status_code, exc.message)

    audit_service.log(
        db, "CHANGE_REJECTED", actor=supervisor, target=change.user,
        detail=f"semana {change.week_start} → {change.requested_shift.value}",
    )
    
    return _change_to_out(db, change)


@router.delete("/{change_id}", status_code=204, summary="Revertir cambio aprobado (admin)")
def revert_change(
    change_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Elimina el override: el usuario vuelve a rotación/turno fijo esa semana."""
    change = schedule_change_service.get_change(db, change_id)
    if change is None:
        raise HTTPException(404, "Novedad no encontrada")
    try:
        schedule_change_service.revert_change(db, change)
    except schedule_change_service.ChangeError as exc:
        raise HTTPException(exc.status_code, exc.message)

    audit_service.log(
        db, "CHANGE_REVERTED", actor=admin, target=change.user,
        detail=f"semana {change.week_start} → {change.requested_shift.value}",
    )
    
    return None