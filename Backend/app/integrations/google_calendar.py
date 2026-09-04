"""Cliente de la API de Google Calendar para el calendario OFICIAL de festivos.

Se consulta el calendario público de festivos de Colombia:
    es.colombian#holiday@group.v.calendar.google.com

Autenticación con API key (suficiente para calendarios públicos). Pasos:
Google Cloud Console → proyecto → habilitar «Calendar API» → Credenciales →
Clave de API → copiar a backend/.env (GOOGLE_CALENDAR_API_KEY).

Diseño:
- ``fetch_holidays(year)`` devuelve {fecha: nombre}; lanza
  ``GoogleCalendarError`` ante cualquier fallo (sin clave, red, HTTP != 200,
  respuesta vacía). El llamador decide cómo degradar (fallback local).
- Cache en memoria por año con TTL (los festivos de un año no cambian,
  pero así se limitan llamadas y se permite corrección de datos).
- Los festivos son eventos de día completo (``start.date``); por robustez
  también se acepta ``start.dateTime`` tomando su parte de fecha.
- Sin dependencias nuevas: ``httpx`` ya está en el proyecto.
"""
import threading
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import httpx

from app.core.config import settings

BASE_URL = "https://www.googleapis.com/calendar/v3/calendars"
TIMEOUT_SECONDS = 10.0
MAX_RESULTS = 250


class GoogleCalendarError(Exception):
    """Fallo al consultar Google Calendar (la app debe degradar a fallback)."""


_cache_lock = threading.Lock()
_cache: dict[int, tuple[datetime, dict[date, str]]] = {}


def _http_get(url: str, params: dict[str, str]) -> httpx.Response:
    """Indirección de HTTP (permite simular la API en pruebas)."""
    return httpx.get(url, params=params, timeout=TIMEOUT_SECONDS)


def fetch_holidays(
    year: int,
    *,
    api_key: str | None = None,
    calendar_id: str | None = None,
) -> dict[date, str]:
    """Festivos {fecha: nombre} del año según Google Calendar.

    Lanza ``GoogleCalendarError`` si no hay clave o la consulta falla.
    El resultado exitoso se cachea por año durante HOLIDAYS_CACHE_TTL_HOURS.
    """
    key = api_key if api_key is not None else settings.GOOGLE_CALENDAR_API_KEY
    if not key:
        raise GoogleCalendarError("GOOGLE_CALENDAR_API_KEY no configurada")

    now = datetime.now(timezone.utc)
    with _cache_lock:
        cached = _cache.get(year)
        if cached is not None and now - cached[0] < timedelta(hours=settings.HOLIDAYS_CACHE_TTL_HOURS):
            return dict(cached[1])

    calendar = calendar_id or settings.GOOGLE_CALENDAR_ID
    # El ID contiene '#' y '@': viaja URL-encodeado en la ruta.
    url = f"{BASE_URL}/{quote(calendar, safe='')}/events"
    params = {
        "key": key,
        "timeMin": f"{year}-01-01T00:00:00Z",
        "timeMax": f"{year + 1}-01-01T00:00:00Z",
        "maxResults": str(MAX_RESULTS),
        "singleEvents": "true",
        "orderBy": "startTime",
    }

    try:
        response = _http_get(url, params)
    except httpx.HTTPError as exc:  # errores de red / timeout
        raise GoogleCalendarError(f"Error de red contra Google Calendar: {exc}") from exc

    if response.status_code != 200:
        raise GoogleCalendarError(f"Google Calendar respondió {response.status_code}")

    holidays = _parse_events(response.json())
    if not holidays:
        raise GoogleCalendarError("La respuesta de Google Calendar no contiene festivos")

    with _cache_lock:
        _cache[year] = (now, dict(holidays))
    return holidays


def _parse_events(payload: dict) -> dict[date, str]:
    """Extrae {fecha: nombre} de la respuesta de la API."""
    holidays: dict[date, str] = {}
    for item in payload.get("items", []):
        start = item.get("start") or {}
        raw = start.get("date") or (start.get("dateTime") or "")[:10]
        if not raw:
            continue
        try:
            day = date.fromisoformat(raw)
        except ValueError:
            continue
        name = item.get("summary", "Festivo")
        if day in holidays:  # dos eventos el mismo día: se combinan los nombres
            holidays[day] = f"{holidays[day]} / {name}"
        else:
            holidays[day] = name
    return holidays


def clear_cache() -> None:
    """Vacía la caché (pruebas y administración)."""
    with _cache_lock:
        _cache.clear()