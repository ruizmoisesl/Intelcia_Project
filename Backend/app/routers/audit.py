"""Consulta del registro de auditoría (solo ADMIN)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_admin
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.audit import AuditListOut, AuditOut
from app.schemas.user import UserBrief
from app.services import audit_service

router = APIRouter(prefix="/api/v1/audit", tags=["Auditoría"])


def _to_out(entry: AuditLog) -> AuditOut:
    return AuditOut(
        id=entry.id,
        event=entry.event,
        actor=UserBrief.model_validate(entry.actor) if entry.actor else None,
        target_user=UserBrief.model_validate(entry.target_user) if entry.target_user else None,
        detail=entry.detail,
        created_at=entry.created_at,
    )


@router.get("", response_model=AuditListOut, summary="Registro de auditoría (admin)")
def list_audit(
    event: str | None = Query(default=None, max_length=40),
    actor_id: int | None = Query(default=None),
    target_user_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AuditListOut:
    items, total = audit_service.list_logs(
        db,
        event=event,
        actor_id=actor_id,
        target_user_id=target_user_id,
        limit=limit,
        offset=offset,
    )
    return AuditListOut(total=total, items=[_to_out(entry) for entry in items])