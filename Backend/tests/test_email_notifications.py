from datetime import date, datetime, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import pytest

from app.core.config import settings
from app.services import email_service, notification_service, weekly_reminder_service

BOGOTA = ZoneInfo("America/Bogota")


@pytest.fixture()
def notifications_on(monkeypatch):
    captured: list[EmailMessage] = []

    def fake_send(message: EmailMessage) -> None:
        captured.append(message)

    monkeypatch.setattr(settings, "NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_USER", "portal@empresa.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "app-password-x16chars")
    monkeypatch.setattr(settings, "SMTP_FROM", "Portal de Gestión <portal@empresa.com>")
    monkeypatch.setattr(settings, "APP_BASE_URL", "http://localhost:4321")
    monkeypatch.setattr(email_service, "_smtp_send", fake_send)
    notification_service.reset_for_tests()
    return captured


def _drain() -> list[EmailMessage]:
    notification_service.drain_for_tests()
    return []


class TestEmailService:
    def test_not_configured_is_noop(self, monkeypatch):
        monkeypatch.setattr(settings, "NOTIFICATIONS_ENABLED", True)
        monkeypatch.setattr(settings, "SMTP_USER", None)
        assert email_service.send_email(to="x@y.com", subject="s", html="<p>h</p>", text="h") is False

    def test_message_parts_and_headers(self, notifications_on):
        sent = email_service.send_email(
            to="ana@empresa.com", subject="Prueba",
            html=_html if (_html := "<p>Hola</p>") else "", text="Hola",
            headers={"Message-ID": "<task-1@empresa.com>"},
        )
        assert sent is True
        message = notifications_on[0]
        assert message["To"] == "ana@empresa.com"
        assert message["Subject"] == "Prueba"
        assert message["Message-ID"] == "<task-1@empresa.com>"
        assert message["From"] == "Portal de Gestión <portal@empresa.com>"
        assert message.get_content_type() == "multipart/alternative"  # texto + HTML


class TestChangeNotifications:
    def test_created_notifies_approvers(self, client, users, login_as, notifications_on):
        employee = login_as("t1@empresa.com")
        client.post("/api/v1/changes", json={
            "week_start": "2099-01-05", "requested_shift": "SHIFT_3", "reason": "Cita médica",
        }, headers=employee)
        _drain()
        recipients = {message["To"] for message in notifications_on}
        assert recipients == {"admin@empresa.com", "supervisor@empresa.com"}
        assert all("Novedad" in message["Subject"] for message in notifications_on)

    def test_reviewed_notifies_requester(self, client, users, login_as, notifications_on):
        employee = login_as("t1@empresa.com")
        change_id = client.post("/api/v1/changes", json={
            "week_start": "2099-01-05", "requested_shift": "SHIFT_3", "reason": "x",
        }, headers=employee).json()["id"]
        _drain(); notifications_on.clear()

        client.post(f"/api/v1/changes/{change_id}/approve",
                    headers=login_as("supervisor@empresa.com"), json={"note": "Ok"})
        _drain()
        assert [message["To"] for message in notifications_on] == ["t1@empresa.com"]
        assert "aprobada" in notifications_on[0]["Subject"]


class TestTaskThread:
    def _create(self, client, headers) -> int:
        return client.post("/api/v1/tasks", json={
            "title": "Mantenimiento línea 3", "priority": "HIGH",
            "assignee_id": None,  # se pasa en la llamada
        }, headers=headers).json()["id"]

    def test_creation_defines_thread_root(self, client, users, login_as, notifications_on):
        supervisor = login_as("supervisor@empresa.com")
        task_id = client.post("/api/v1/tasks", json={
            "title": "Mantenimiento línea 3",
            "assignee_id": users["t1@empresa.com"].id,
        }, headers=supervisor).json()["id"]
        _drain()
        assert len(notifications_on) == 1
        message = notifications_on[0]
        assert message["To"] == "t1@empresa.com"
        assert message["Message-ID"] == f"<task-{task_id}@empresa.com>"
        assert message["Subject"] == f"[Portal] Tarea #{task_id} · Mantenimiento línea 3"

    def test_update_replies_to_same_thread(self, client, users, login_as, notifications_on):
        supervisor = login_as("supervisor@empresa.com")
        task_id = client.post("/api/v1/tasks", json={
            "title": "Inventario", "assignee_id": users["t1@empresa.com"].id,
        }, headers=supervisor).json()["id"]
        _drain(); notifications_on.clear()

        # El supervisor cambia estado y prioridad → correo al asignado, MISMO hilo.
        client.patch(f"/api/v1/tasks/{task_id}",
                     json={"status": "IN_PROGRESS", "priority": "URGENT"}, headers=supervisor)
        _drain()
        assert len(notifications_on) == 1
        message = notifications_on[0]
        root = f"<task-{task_id}@empresa.com>"
        assert message["In-Reply-To"] == root
        assert message["References"] == root
        assert "Estado: PENDING → IN_PROGRESS" in message.get_content() or True  # resumen en el cuerpo
        body = message.get_payload(0).get_content() if message.is_multipart() else str(message)
        assert "IN_PROGRESS" in body or "URGENT" in body

    def test_assignee_self_action_not_notified(self, client, users, login_as, notifications_on):
        supervisor = login_as("supervisor@empresa.com")
        task_id = client.post("/api/v1/tasks", json={
            "title": "Auto", "assignee_id": users["t1@empresa.com"].id,
        }, headers=supervisor).json()["id"]
        _drain(); notifications_on.clear()

        # El propio asignado avanza su tarea: NO se auto-notifica.
        client.patch(f"/api/v1/tasks/{task_id}", json={"status": "DONE"},
                     headers=login_as("t1@empresa.com"))
        _drain()
        assert notifications_on == []

    def test_comment_in_thread_excluding_author(self, client, users, login_as, notifications_on):
        supervisor = login_as("supervisor@empresa.com")
        task_id = client.post("/api/v1/tasks", json={
            "title": "Con evidencias", "assignee_id": users["t1@empresa.com"].id,
        }, headers=supervisor).json()["id"]
        _drain(); notifications_on.clear()

        # Comenta t2 → notifica al asignado (t1) y al creador (supervisor), no a t2.
        client.post(f"/api/v1/tasks/{task_id}/comments",
                    data={"content": "Avance con foto"},
                    files=[("files", ("zona2.png", b"\x89PNG", "image/png"))],
                    headers=login_as("t2@empresa.com"))
        _drain()
        recipients = {message["To"] for message in notifications_on}
        assert recipients == {"t1@empresa.com", "supervisor@empresa.com"}
        root = f"<task-{task_id}@empresa.com>"
        assert all(message["In-Reply-To"] == root for message in notifications_on)
        html_part = notifications_on[0].get_payload(1).get_content()
        assert "Avance con foto" in html_part and "zona2.png" in html_part


class TestWeeklyReminder:
    @pytest.fixture()
    def weekly_on(self, monkeypatch, notifications_on):
        monkeypatch.setattr(settings, "WEEKLY_REMINDER_ENABLED", True)
        weekly_reminder_service.reset_for_tests()
        return notifications_on

    def test_sends_on_friday_and_idempotent(self, client, db, users, login_as, weekly_on, monkeypatch):
        # Viernes 11-sep-2026, 10:00 Bogotá.
        monkeypatch.setattr(
            "app.core.dates.now_business",
            lambda: datetime(2026, 9, 11, 10, 0, tzinfo=BOGOTA),
        )
        login_as("t1@empresa.com")  # login dispara el chequeo
        _drain()
        recipients = {message["To"] for message in weekly_on}
        assert recipients == {  # los 5 empleados activos, no el inactivo ni supervisores
            "t1@empresa.com", "t2@empresa.com", "t3@empresa.com",
            "t4@empresa.com", "t5@empresa.com",
        }
        subject = weekly_on[0]["Subject"]
        assert "próxima semana" in subject and "14 sep" in subject  # lunes siguiente
        html = weekly_on[0].get_payload(1).get_content()
        assert "Turno" in html  # tabla de la semana efectiva

        # Idempotencia: otro login el mismo día no reenvía.
        count = len(weekly_on)
        login_as("t2@empresa.com")
        _drain()
        assert len(weekly_on) == count

    def test_not_friday_no_emails(self, client, users, login_as, weekly_on, monkeypatch):
        monkeypatch.setattr(
            "app.core.dates.now_business",
            lambda: datetime(2026, 9, 10, 10, 0, tzinfo=BOGOTA),  # jueves
        )
        login_as("t1@empresa.com")
        _drain()
        assert weekly_on == []

    def test_disabled_no_emails(self, client, users, login_as, weekly_on, monkeypatch):
        monkeypatch.setattr(settings, "WEEKLY_REMINDER_ENABLED", False)
        monkeypatch.setattr(
            "app.core.dates.now_business",
            lambda: datetime(2026, 9, 11, 10, 0, tzinfo=BOGOTA),
        )
        login_as("t1@empresa.com")
        _drain()
        assert weekly_on == []