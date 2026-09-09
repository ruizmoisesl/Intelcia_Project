from datetime import timedelta

import httpx

from app.core import dates
from app.core.config import settings
from app.integrations import jira as jira_module
from app.integrations import trello as trello_module


def _create_task(client, headers, **overrides):
    payload = {"title": "Tarea de integración", "priority": "HIGH",
               "due_date": (dates.today() + timedelta(days=3)).isoformat(),
               "assignee_id": None}
    payload.update(overrides)
    return client.post("/api/v1/tasks", json=payload, headers=headers).json()


class TestPushJira:
    def test_not_configured_returns_400(self, client, users, login_as):
        headers = login_as("supervisor@empresa.com")
        task = _create_task(client, headers)
        response = client.post(f"/api/v1/tasks/{task['id']}/push",
                               json={"target": "jira"}, headers=headers)
        assert response.status_code == 400
        assert "Jira no está configurado" in response.json()["detail"]

    def test_creates_issue_and_links_task(self, client, db, users, login_as, monkeypatch):
        for key in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"):
            monkeypatch.setattr(settings, key, {"JIRA_BASE_URL": "https://test.atlassian.net",
                                                 "JIRA_EMAIL": "bot@empresa.com",
                                                 "JIRA_API_TOKEN": "tok", "JIRA_PROJECT_KEY": "PORT"}[key])
        captured = {}
        def fake_post(url, *, json, auth, headers):
            captured["url"], captured["payload"], captured["auth"] = url, json, auth
            return httpx.Response(201, json={"key": "PORT-42"})
        monkeypatch.setattr(jira_module, "_http_post", fake_post)

        headers = login_as("supervisor@empresa.com")
        task = _create_task(client, headers)
        response = client.post(f"/api/v1/tasks/{task['id']}/push",
                               json={"target": "jira"}, headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["external"] == {"system": "jira", "id": "PORT-42",
                                    "url": "https://test.atlassian.net/browse/PORT-42"}
        # El issue se crea con los datos de la tarea:
        fields = captured["payload"]["fields"]
        assert fields["project"]["key"] == "PORT"
        assert fields["summary"] == "Tarea de integración"
        assert fields["issuetype"]["name"] == "Task"
        assert fields["priority"]["name"] == "High"
        assert fields["duedate"] == (dates.today() + timedelta(days=3)).isoformat()
        # Historial + auditoría:
        assert any(e["event"] == "PUSHED" for e in body["events"])

    def test_http_error_becomes_400(self, client, users, login_as, monkeypatch):
        # config + mock que responde 403 → 400 con mensaje claro, tarea intacta
        for key, value in {
            "JIRA_BASE_URL": "https://test.atlassian.net",
            "JIRA_EMAIL": "bot@empresa.com",
            "JIRA_API_TOKEN": "tok",
            "JIRA_PROJECT_KEY": "PORT",
        }.items():
            monkeypatch.setattr(settings, key, value)

        def fake_post(url, *, json, auth, headers):
            return httpx.Response(403, json={"errorMessages": ["Forbidden"]})

        monkeypatch.setattr(jira_module, "_http_post", fake_post)
        headers = login_as("supervisor@empresa.com")
        task = _create_task(client, headers)
        response = client.post(
            f"/api/v1/tasks/{task['id']}/push",
            json={"target": "jira"},
            headers=headers,
        )
        assert response.status_code == 400
        assert "Jira" in response.json()["detail"]

class TestPushTrello:
    def test_not_configured_returns_400(self, client, login_as):
        headers = login_as("supervisor@empresa.com")
        task = _create_task(client, headers)
        response = client.post(
            f"/api/v1/tasks/{task['id']}/push",
            json={"target": "trello"},
            headers=headers,
        )
        assert response.status_code == 400

    def test_creates_card_and_links_task(self, client, login_as, monkeypatch):
        for key, value in {
            "TRELLO_API_KEY": "key",
            "TRELLO_TOKEN": "tok",
            "TRELLO_BOARD_ID": "board1",
            "TRELLO_LIST_ID": "list1",
        }.items():
            monkeypatch.setattr(settings, key, value)

        def fake_post(url, *, json, auth, headers):
            return httpx.Response(
                200,
                json={"id": "card1", "shortUrl": "https://trello.com/c/abc"},
            )

        monkeypatch.setattr(trello_module, "_http_post", fake_post)
        headers = login_as("supervisor@empresa.com")
        task = _create_task(client, headers)
        response = client.post(
            f"/api/v1/tasks/{task['id']}/push",
            json={"target": "trello"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["external"] == {
            "system": "trello",
            "id": "card1",
            "url": "https://trello.com/c/abc",
        }

    def test_unknown_target_400(self, client, login_as):
        headers = login_as("supervisor@empresa.com")
        task = _create_task(client, headers)
        response = client.post(
            f"/api/v1/tasks/{task['id']}/push",
            json={"target": "unknown"},
            headers=headers,
        )
        assert response.status_code == 400

    def test_employee_forbidden(self, client, login_as):
        headers = login_as("empleado@empresa.com")
        task = _create_task(client, headers)
        response = client.post(
            f"/api/v1/tasks/{task['id']}/push",
            json={"target": "trello"},
            headers=headers,
        )
        assert response.status_code == 403