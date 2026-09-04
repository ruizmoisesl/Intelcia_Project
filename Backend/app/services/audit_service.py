"""Auditoría de acciones relevantes (quién, qué, a quién, cuándo).

Diseño:
- ``log`` es best-effort: si la escritura falla se registra en el log del
  servidor, pero NUNCA rompe la operación de negocio que la origina.
- Se llama siempre DESPUÉS del commit de la operación principal.
- Nunca se registran contraseñas (solo nombres de campos).
"""
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)


def log(
    db: Session,
    event: str,
    *,
    actor: User | None = None,
    target: User | None = None,
    detail: str | None = None,
) -> None:
    try:
        db.add(
            AuditLog(
                event=event,
                actor_id=actor.id if actor is not None else None,
                target_user_id=target.id if target is not None else None,
                detail=detail,
            )
        )
        db.commit()
    except Exception:  # pragma: no cover - la auditoría nunca rompe el flujo
        db.rollback()
        logger.exception("No se pudo escribir el evento de auditoría %s", event)


def list_logs(
    db: Session,
    *,
    event: str | None = None,
    actor_id: int | None = None,
    target_user_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    conditions = []
    if event is not None:
        conditions.append(AuditLog.event == event)
    if actor_id is not None:
        conditions.append(AuditLog.actor_id == actor_id)
    if target_user_id is not None:
        conditions.append(AuditLog.target_user_id == target_user_id)

    count_stmt = select(func.count()).select_from(AuditLog)
    stmt = select(AuditLog)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
        stmt = stmt.where(*conditions)

    total = db.scalar(count_stmt) or 0
    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt)), total