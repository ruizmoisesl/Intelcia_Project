"""Horarios personalizados por día (solo supervisor/admin)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_supervisor
from app.models.day_override import DayOverride
from app.models.user import User
from app.schemas.day_override import DayOverrideCreateRequest
from app.schemas.schedule import DayOverrideOut, day_override_out
from app.services import audit_service, auth_service, day_override_service

router = APIRouter(prefix="/api/v1/day-overrides", tags=["Horarios personalizados"])


@router.post("", response_model=DayOverrideOut, status_code=201, summary="Personalizar un día (supervisor/admin)")
def create_day_override(
    payload: DayOverrideCreateRequest,
    supervisor: User = Depends(require_supervisor),
    db: Session = Depends(get_db),
) -> DayOverrideOut:
    """Cambia el turno de UN día, o fija horas exactas. Reemplaza si ya existía."""
    target = auth_service.get_user_by_id(db, payload.user_id)
    if target is None:
        raise HTTPException(404, "Usuario no encontrado")
    try:
        override = day_override_service.create_or_replace(
            db,
            user=target,
            day=payload.date,
            shift=payload.shift,
            start=payload.start,
            end=payload.end,
            reason=payload.reason,
            created_by=supervisor,
        )
    except day_override_service.OverrideError as exc:
        raise HTTPException(exc.status_code, exc.message)

    mode = (
        f"turno {override.shift.value}"
        if override.shift
        else f"{override.start_time:%H:%M}–{override.end_time:%H:%M}"
    )
    audit_service.log(
        db, "CUSTOM_DAY_SET", actor=supervisor, target=target,
        detail=f"{target.name}: {override.date} → {mode}",
    )
    return day_override_out(override)


@router.delete("/{override_id}", status_code=204, summary="Quitar personalización (supervisor/admin)")
def delete_day_override(
    override_id: int,
    supervisor: User = Depends(require_supervisor),
    db: Session = Depends(get_db),
) -> None:
    override = db.get(DayOverride, override_id)
    if override is None:
        raise HTTPException(404, "Personalización no encontrada")
    audit_service.log(
        db, "CUSTOM_DAY_REMOVED", actor=supervisor,
        detail=f"{override.user.name}: {override.date}",
    )
    day_override_service.delete_override(db, override)
    return None