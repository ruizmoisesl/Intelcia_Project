"""Recordatorio semanal: turno de la PRÓXIMA semana, los viernes.

Sin scheduler externo: chequeo «lazy» desde endpoints de tráfico natural
(login, /schedules/me, /schedules/week) con:
- throttle en memoria (60 s por proceso) — coste ~0 tras el primer chequeo,
- idempotencia diaria vía audit_logs (evento WEEKLY_REMINDER_SENT + fecha),
- fail-soft total: cualquier fallo se registra y no afecta la request.
Si SMTP no está configurado, no se marca el día (podrá enviarse al configurar).
"""
import logging
import time
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import dates
from app.core.config import settings
from app.models.audit import AuditLog
from app.services import (
    audit_service, day_override_service, notification_service, rotation_service, schedule_service,
)
from app.services import email_service

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 60.0
_EVENT = "WEEKLY_REMINDER_SENT"
_last_check = 0.0


def reset_for_tests() -> None:
    global _last_check
    _last_check = 0.0


def maybe_send(db: Session) -> None:
    """Hook barato: llamar desde endpoints frecuentes."""
    global _last_check
    if not settings.WEEKLY_REMINDER_ENABLED or not email_service.is_configured():
        return
    if time.monotonic() - _last_check < _CHECK_INTERVAL_SECONDS:
        return
    _last_check = time.monotonic()
    try:
        _run(db)
    except Exception:  # fail-soft absoluto
        logger.exception("Recordatorio semanal: fallo (no afecta la request)")


def _run(db: Session) -> None:
    now = dates.now_business()
    if now.weekday() != settings.WEEKLY_REMINDER_WEEKDAY:  # ¿viernes?
        return
    if now.hour < settings.WEEKLY_REMINDER_HOUR:
        return

    today = now.date()
    marker = f"fecha={today.isoformat()}"
    already = db.scalars(
        select(AuditLog).where(AuditLog.event == _EVENT, AuditLog.detail.like(f"{marker}%"))
    ).first()
    if already is not None:  # ya se envió hoy → idempotente
        return

    # Próxima semana (desde viernes → lunes que viene).
    next_monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)

    employees = rotation_service.get_rotating_employees(db)
    sent = 0
    for employee in employees:
        effective = rotation_service.get_effective_shift(db, employee, next_monday)
        week = schedule_service.get_week_schedule(effective.shift_id, next_monday)
        week = day_override_service.apply_day_overrides(db, employee.id, week)
        notification_service.notify_weekly_schedule(employee, week, effective)
        sent += 1

    # Marca del día (audit es best-effort; si fallara, a lo sumo reenvía una vez).
    audit_service.log(db, _EVENT, detail=f"{marker}; enviados={sent}")
    if sent:
        logger.info("Recordatorio semanal: %d correos encolados (semana del %s)",
                    sent, next_monday.isoformat())