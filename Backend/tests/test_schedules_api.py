from datetime import date, timedelta

from app.models.user import ShiftId
from app.services import schedule_service
from .conftest import TEST_PASSWORD


def test_week_requires_authentication(client, users):
    response = client.get("/api/v1/schedules/week")
    assert response.status_code == 401


def test_today_requires_authentication(client, users):
    response = client.get("/api/v1/schedules/me")
    assert response.status_code == 401


def test_week_returns_current_week_by_default(client, users, login_as):
    headers = login_as("t1@empresa.com")
    response = client.get("/api/v1/schedules/week", headers=headers)
    assert response.status_code == 200
    body = response.json()
    today = date.today()
    expected_monday = today - timedelta(days=today.weekday())
    assert date.fromisoformat(body["week_start"]) == expected_monday
    assert len(body["days"]) == 7


def test_week_explicit_start_shift1(client, users, login_as):
    headers = login_as("t1@empresa.com")
    response = client.get("/api/v1/schedules/week?week_start=2026-08-31", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["week_start"] == "2026-08-31"
    assert body["shift"] == {"id": "SHIFT_1", "name": "Turno 1"}

    days = {day["weekday"]: day for day in body["days"]}
    assert days["MONDAY"]["start"] == "07:00"
    assert days["MONDAY"]["end"] == "17:00"
    assert days["WEDNESDAY"]["date"] == "2026-09-02"
    assert days["WEDNESDAY"]["day_name"] == "Miércoles"
    assert days["WEDNESDAY"]["start"] == "07:00"
    assert days["WEDNESDAY"]["end"] == "16:00"
    assert days["SATURDAY"]["start"] is None
    assert days["SUNDAY"]["start"] is None


def test_week_normalizes_non_monday_param(client, users, login_as):
    headers = login_as("t1@empresa.com")
    response = client.get("/api/v1/schedules/week?week_start=2026-09-03", headers=headers)  # jueves
    assert response.json()["week_start"] == "2026-08-31"


def test_week_shift2_saturday_is_not_reduced(client, users, login_as):
    headers = login_as("t2@empresa.com")
    response = client.get("/api/v1/schedules/week?week_start=2026-08-31", headers=headers)
    days = {day["weekday"]: day for day in response.json()["days"]}
    assert days["WEDNESDAY"]["end"] == "14:00"
    assert days["SATURDAY"]["start"] == "07:00"
    assert days["SATURDAY"]["end"] == "16:00"


def test_week_shift4_midnight(client, users, login_as):
    headers = login_as("t4@empresa.com")
    response = client.get("/api/v1/schedules/week?week_start=2026-08-31", headers=headers)
    days = {day["weekday"]: day for day in response.json()["days"]}
    assert days["MONDAY"]["start"] == "00:00"
    assert days["MONDAY"]["end"] == "10:00"
    assert days["FRIDAY"]["end"] == "09:00"


def test_week_crosses_year(client, users, login_as):
    headers = login_as("t1@empresa.com")
    response = client.get("/api/v1/schedules/week?week_start=2026-12-28", headers=headers)
    days = response.json()["days"]
    assert days[0]["date"] == "2026-12-28"
    assert days[6]["date"] == "2027-01-03"


def test_week_invalid_date_returns_422(client, users, login_as):
    headers = login_as("t1@empresa.com")
    response = client.get("/api/v1/schedules/week?week_start=fecha-invalida", headers=headers)
    assert response.status_code == 422


def test_today_schedule_matches_service_rules(client, users, login_as):
    headers = login_as("t3@empresa.com")
    response = client.get("/api/v1/schedules/me", headers=headers)
    assert response.status_code == 200
    body = response.json()

    today = date.today()
    weekday = schedule_service.weekday_of(today)
    expected = schedule_service.get_schedule_for_day(ShiftId.SHIFT_3, weekday)

    assert body["date"] == today.isoformat()
    assert body["shift"]["id"] == "SHIFT_3"
    assert body["start"] == expected.start.strftime("%H:%M") if expected else body["start"] is None
    assert body["end"] == expected.end.strftime("%H:%M") if expected else body["end"] is None


def test_wrong_password_cannot_access_schedules(client, users):
    response = client.post(
        "/api/v1/auth/login", json={"email": "t1@empresa.com", "password": TEST_PASSWORD + "x"}
    )
    assert response.status_code == 401
    token = response.json().get("access_token")
    response = client.get("/api/v1/schedules/week", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401

def test_week_shift2_holiday_and_saturday_as_supervisor(client, users, login_as):
    # Semana del lunes 20-jul-2026 (festivo). Supervisor: turno fijo SHIFT_2.
    headers = login_as("supervisor@empresa.com")
    body = client.get("/api/v1/schedules/week?week_start=2026-07-20", headers=headers).json()

    assert body["shift"] == {"id": "SHIFT_2", "name": "Turno 2", "color": "blue"}
    days = {day["weekday"]: day for day in body["days"]}

    # Regla v0.3: el Turno 2 NO trabaja festivos (compensa con sábados).
    assert days["MONDAY"]["is_holiday"] is True
    assert days["MONDAY"]["holiday_name"] == "Día de la Independencia"
    assert days["MONDAY"]["start"] is None
    assert days["MONDAY"]["end"] is None

    # Miércoles normal: reducción aplicada.
    assert days["WEDNESDAY"]["end"] == "14:00"
    assert days["WEDNESDAY"]["is_holiday"] is False

    # Sábado especial del Turno 2, sin reducción.
    assert days["SATURDAY"]["start"] == "07:00"
    assert days["SATURDAY"]["end"] == "16:00"

    def test_week_shift1_holiday_admin(client, users, login_as):
    # Turno 1 sí trabaja festivos: jornada festiva 08:00–14:00.
        headers = login_as("admin@empresa.com")
        days = {
            d["weekday"]: d
            for d in client.get("/api/v1/schedules/week?week_start=2026-07-20", headers=headers).json()["days"]
        }
        assert days["MONDAY"]["is_holiday"] is True
        assert (days["MONDAY"]["start"], days["MONDAY"]["end"]) == ("08:00", "14:00")


def test_holidays_endpoint_local_provider(client, users, login_as):
    headers = login_as("t1@empresa.com")
    response = client.get("/api/v1/schedules/holidays?year=2026", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["year"] == 2026
    assert body["provider"] == "local"  # sin API key en el entorno de pruebas
    assert len(body["holidays"]) == 18
    assert "2026-07-20" in {item["date"] for item in body["holidays"]}


def test_holidays_endpoint_requires_auth(client, users):
    assert client.get("/api/v1/schedules/holidays").status_code == 401


def test_holidays_endpoint_invalid_year(client, users, login_as):
    headers = login_as("t1@empresa.com")
    assert client.get("/api/v1/schedules/holidays?year=1999", headers=headers).status_code == 422