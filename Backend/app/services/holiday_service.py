"""Resolución de festivos de Colombia: Google Calendar (oficial) + fallback local.

Política según ``HOLIDAYS_PROVIDER``:
- ``auto`` (por defecto): Google Calendar si hay API key; ante cualquier fallo
  se sirve el cálculo local (la app nunca se cae por una incidencia de Google).
- ``google``: igual que auto, pero el fallo se registra como ERROR.
- ``local``: nunca consulta Google (offline / pruebas).

Los fallos de Google se recuerdan 60 s (anti-bombardeo: cada página renderiza
varias fechas); los éxitos los cachea el propio cliente por año.
"""
import logging
import time
from datetime import date

from app.core.config import settings
from app.integrations import google_calendar
from app.services import colombian_holidays

logger = logging.getLogger(__name__)

_FAILURE_TTL_SECONDS = 60.0
_failures: dict[int, float] = {}  # {año: time.monotonic() del último fallo}
_sources: dict[int, str] = {}     # {año: proveedor que sirvió los datos}


def _google_holidays(year: int) -> dict[date, str] | None:
    """Festivos de Google, o None si falló hace menos de 60 s."""
    failed_at = _failures.get(year)
    if failed_at is not None and (time.monotonic() - failed_at) < _FAILURE_TTL_SECONDS:
        return None
    try:
        return google_calendar.fetch_holidays(year)
    except google_calendar.GoogleCalendarError as exc:
        _failures[year] = time.monotonic()
        if settings.HOLIDAYS_PROVIDER == "google":
            logger.error("Proveedor 'google' obligatorio y la API falló: %s", exc)
        else:
            logger.warning(
                "Festivos: Google Calendar no disponible (%s); se usa el cálculo local", exc
            )
        return None


def get_holidays(year: int) -> dict[date, str]:
    """Festivos del año {fecha: nombre} según el proveedor configurado."""
    if settings.HOLIDAYS_PROVIDER != "local":
        holidays = _google_holidays(year)
        if holidays is not None:
            _sources[year] = "google"
            return holidays
    _sources[year] = "local"
    return colombian_holidays.colombian_holidays(year)


def is_holiday(day: date) -> bool:
    return day in get_holidays(day.year)


def holiday_name(day: date) -> str | None:
    return get_holidays(day.year).get(day)


def provider_name(year: int) -> str:
    """Proveedor que sirvió los datos del año ('google' | 'local'). Diagnóstico."""
    return _sources.get(year, "desconocido")


def reset_state() -> None:
    """Limpia el estado interno de proveedor/fallos (pruebas y diagnóstico)."""
    _failures.clear()
    _sources.clear()