"""Fecha «hoy» del negocio.

Toda la app debe obtener «hoy» desde aquí (nunca ``date.today()`` directo):
el servidor puede correr en UTC (Docker) mientras la empresa opera en otra
zona. La zona del negocio se configura con BUSINESS_TIMEZONE.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def now_business() -> datetime:
    return datetime.now(ZoneInfo(settings.BUSINESS_TIMEZONE))


def today() -> date:
    """Fecha actual en la zona horaria del negocio (no la del servidor)."""
    return now_business().date()