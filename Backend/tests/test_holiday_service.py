from datetime import date

import httpx
import pytest

from app.core.config import settings
from app.integrations import google_calendar as gc
from app.services import colombian_holidays, holiday_service


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    gc.clear_cache()
    holiday_service.reset_state()
    monkeypatch.setattr(settings, "GOOGLE_CALENDAR_API_KEY", None)
    monkeypatch.setattr(settings, "HOLIDAYS_PROVIDER", "auto")
    yield
    gc.clear_cache()
    holiday_service.reset_state()


class TestProvider:
    def test_without_key_uses_local(self):
        holidays = holiday_service.get_holidays(2026)
        assert holidays == colombian_holidays.colombian_holidays(2026)
        assert holiday_service.provider_name(2026) == "local"

    def test_with_google_success(self, monkeypatch):
        monkeypatch.setattr(settings, "GOOGLE_CALENDAR_API_KEY", "key")
        monkeypatch.setattr(
            gc, "_http_get",
            lambda url, params: httpx.Response(200, json={"items": [
                {"summary": "Año Nuevo", "start": {"date": "2026-01-01"}},
            ]}),
        )
        assert holiday_service.get_holidays(2026) == {date(2026, 1, 1): "Año Nuevo"}
        assert holiday_service.provider_name(2026) == "google"

    def test_google_failure_falls_back_to_local(self, monkeypatch):
        monkeypatch.setattr(settings, "GOOGLE_CALENDAR_API_KEY", "key")
        monkeypatch.setattr(gc, "_http_get", lambda url, params: httpx.Response(503, json={}))
        assert holiday_service.get_holidays(2026) == colombian_holidays.colombian_holidays(2026)
        assert holiday_service.provider_name(2026) == "local"

    def test_provider_local_never_calls_google(self, monkeypatch):
        monkeypatch.setattr(settings, "HOLIDAYS_PROVIDER", "local")
        monkeypatch.setattr(settings, "GOOGLE_CALENDAR_API_KEY", "key")

        def fail(url, params):
            raise AssertionError("No debería llamarse a Google con provider=local")

        monkeypatch.setattr(gc, "_http_get", fail)
        assert holiday_service.get_holidays(2026) == colombian_holidays.colombian_holidays(2026)


class TestQueries:
    def test_is_holiday_and_name(self):
        assert holiday_service.is_holiday(date(2026, 7, 20))
        assert holiday_service.holiday_name(date(2026, 7, 20)) == "Día de la Independencia"
        assert not holiday_service.is_holiday(date(2026, 9, 15))
        assert holiday_service.holiday_name(date(2026, 9, 15)) is None