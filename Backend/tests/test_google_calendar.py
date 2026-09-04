from datetime import date

import httpx
import pytest

from app.core.config import settings
from app.integrations import google_calendar as gc


def make_response(status: int = 200, items: list | None = None) -> httpx.Response:
    return httpx.Response(status_code=status, json={"items": items or []})


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    gc.clear_cache()
    monkeypatch.setattr(settings, "GOOGLE_CALENDAR_API_KEY", None)
    yield
    gc.clear_cache()  # no contaminar a otros módulos con datos simulados


class TestFetchHolidays:
    def test_no_api_key_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "GOOGLE_CALENDAR_API_KEY", None)
        with pytest.raises(gc.GoogleCalendarError):
            gc.fetch_holidays(2026)

    def test_maps_all_day_events(self, monkeypatch):
        monkeypatch.setattr(settings, "GOOGLE_CALENDAR_API_KEY", "key")
        calls: list[str] = []

        def fake_get(url: str, params: dict) -> httpx.Response:
            calls.append(url)
            return make_response(items=[
                {"summary": "Día de la Independencia", "start": {"date": "2026-07-20"}},
                {"summary": "Navidad", "start": {"date": "2026-12-25"}},
                {"summary": "Con dateTime", "start": {"dateTime": "2026-01-01T00:00:00-05:00"}},
            ])

        monkeypatch.setattr(gc, "_http_get", fake_get)
        holidays = gc.fetch_holidays(2026)
        assert holidays == {
            date(2026, 7, 20): "Día de la Independencia",
            date(2026, 12, 25): "Navidad",
            date(2026, 1, 1): "Con dateTime",
        }
        # El ID del calendario viaja URL-encodeado en la ruta.
        assert "calendars/" in calls[0] and "#" not in calls[0]

    def test_http_error_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "GOOGLE_CALENDAR_API_KEY", "key")
        monkeypatch.setattr(gc, "_http_get", lambda url, params: make_response(status=403))
        with pytest.raises(gc.GoogleCalendarError):
            gc.fetch_holidays(2026)

    def test_network_error_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "GOOGLE_CALENDAR_API_KEY", "key")

        def boom(url: str, params: dict) -> httpx.Response:
            raise httpx.ConnectError("sin red")

        monkeypatch.setattr(gc, "_http_get", boom)
        with pytest.raises(gc.GoogleCalendarError):
            gc.fetch_holidays(2026)

    def test_empty_response_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "GOOGLE_CALENDAR_API_KEY", "key")
        monkeypatch.setattr(gc, "_http_get", lambda url, params: make_response(items=[]))
        with pytest.raises(gc.GoogleCalendarError):
            gc.fetch_holidays(2026)

    def test_success_is_cached(self, monkeypatch):
        monkeypatch.setattr(settings, "GOOGLE_CALENDAR_API_KEY", "key")
        counter = {"n": 0}

        def fake_get(url: str, params: dict) -> httpx.Response:
            counter["n"] += 1
            year = params["timeMin"][:4]
            return make_response(items=[{"summary": "Año Nuevo", "start": {"date": f"{year}-01-01"}}])

        monkeypatch.setattr(gc, "_http_get", fake_get)
        gc.fetch_holidays(2026)
        gc.fetch_holidays(2026)
        assert counter["n"] == 1  # la segunda llamada sale de caché