import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.integrations import jira as jira_module
from app.models.audit import AuditLog
from app.services import ticket_service

_ISSUES = {
    "issues": [
        {"key": "SOP-101", "fields": {
            "summary": "VPN no conecta",
            "status": {"name": "En progreso", "statusCategory": {"name": "In Progress"}},
            "priority": {"name": "Highest"},
            "assignee": {"accountId": "acc-123", "displayName": "Empleado Turno 1"},
            "created": "2026-09-01T10:00:00.000+0000", "updated": "2026-09-02T15:30:00.000+0000"}},
        {"key": "SOP-102", "fields": {
            "summary": "Impresora planta 2",
            "status": {"name": "Pendiente", "statusCategory": {"name": "To Do"}},
            "priority": {"name": "Medium"}, "assignee": None,
            "created": "2026-09-02T09:00:00.000+0000", "updated": "2026-09-02T09:00:00.000+0000"}},
    ],
    "isLast": True,
}


@pytest.fixture()
def jira_on(monkeypatch):
    monkeypatch.setattr(settings, "JIRA_BASE_URL", "https://test.atlassian.net")
    monkeypatch.setattr(settings, "JIRA_EMAIL", "bot@empresa.com")
    monkeypatch.setattr(settings, "JIRA_API_TOKEN", "tok")
    monkeypatch.setattr(settings, "JIRA_TICKETS_PROJECT", "SOP")
    monkeypatch.setattr(settings, "TICKETS_CACHE_TTL_SECONDS", 60)
    calls = {"search": [], "users": []}

    def fake_post(url, *, json, auth, headers):
        calls["search"].append(json)
        return httpx.Response(200, json=_ISSUES)

    def fake_get(url, *, params, auth, headers):
        calls["users"].append(params)
        return httpx.Response(200, json=[
            {"accountId": "acc-123", "displayName": "Empleado Turno 1",
             "emailAddress": "t1@empresa.com"},
        ])

    monkeypatch.setattr(jira_module, "_http_post", fake_post)
    monkeypatch.setattr(jira_module, "_http_get", fake_get)
    ticket_service.reset_for_tests()
    yield calls
    ticket_service.reset_for_tests()


class TestMyTickets:
    def test_requires_auth(self, client, users):
        assert client.get("/api/v1/tickets/mine").status_code == 401

    def test_unlinked_returns_empty_hint_without_querying(self, client, users, login_as, jira_on):
        headers = login_as("t1@empresa.com")
        body = client.get("/api/v1/tickets/mine", headers=headers).json()
        assert (body["linked"], body["total"], body["items"]) == (False, 0, [])
        assert jira_on["search"] == []  # no golpea Jira si no hay vinculación

    def test_jql_uses_account_id_never_currentuser(self, client, users, login_as, jira_on):
        login_as("t1@empresa.com")
        client.post("/api/v1/tickets/link", json={}, headers=login_as("t1@empresa.com"))
        client.get("/api/v1/tickets/mine", headers=login_as("t1@empresa.com"))
        jql = jira_on["search"][-1]["jql"]
        assert 'assignee = "acc-123"' in jql
        assert "currentUser" not in jql  # nunca la cuenta de la API key
        assert 'project = "SOP"' in jql and "statusCategory != Done" in jql

    def test_parsed_fields_and_is_mine(self, client, users, login_as, jira_on):
        headers = login_as("t1@empresa.com")
        client.post("/api/v1/tickets/link", json={}, headers=headers)
        body = client.get("/api/v1/tickets/mine", headers=headers).json()
        by_key = {item["key"]: item for item in body["items"]}
        assert by_key["SOP-101"]["is_mine"] is True
        assert by_key["SOP-101"]["priority"] == "Highest"
        assert by_key["SOP-101"]["url"].endswith("/browse/SOP-101")
        assert by_key["SOP-101"]["created"] == "2026-09-01 10:00"
        assert by_key["SOP-102"]["is_mine"] is False


class TestGlobalTickets:
    def test_jql_without_assignee(self, client, users, login_as, jira_on):
        client.get("/api/v1/tickets/global", headers=login_as("t1@empresa.com"))
        jql = jira_on["search"][0]["jql"]
        assert "assignee" not in jql
        assert "statusCategory != Done" in jql

    def test_scope_done_and_all(self, client, users, login_as, jira_on):
        headers = login_as("supervisor@empresa.com")
        client.get("/api/v1/tickets/global?scope=done", headers=headers)
        assert "statusCategory = Done" in jira_on["search"][-1]["jql"]
        client.get("/api/v1/tickets/global?scope=all", headers=headers)
        assert "statusCategory" not in jira_on["search"][-1]["jql"]

    def test_invalid_scope_400(self, client, users, login_as, jira_on):
        assert client.get("/api/v1/tickets/global?scope=x",
                          headers=login_as("supervisor@empresa.com")).status_code == 400


class TestCacheAndFailSoft:
    def test_cache_avoids_second_query(self, client, users, login_as, jira_on):
        headers = login_as("supervisor@empresa.com")
        client.get("/api/v1/tickets/global", headers=headers)
        client.get("/api/v1/tickets/global", headers=headers)
        assert len(jira_on["search"]) == 1

    def test_unavailable_on_network_error(self, client, users, login_as, jira_on, monkeypatch):
        def boom(url, *, json, auth, headers):
            raise httpx.ConnectError("sin red")
        monkeypatch.setattr(jira_module, "_http_post", boom)
        body = client.get("/api/v1/tickets/global",
                          headers=login_as("supervisor@empresa.com")).json()
        assert body["provider"] == "unavailable" and body["items"] == []

    def test_unconfigured_without_project(self, client, users, login_as, monkeypatch):
        monkeypatch.setattr(settings, "JIRA_TICKETS_PROJECT", None)
        body = client.get("/api/v1/tickets/global",
                          headers=login_as("supervisor@empresa.com")).json()
        assert body["provider"] == "unconfigured"


class TestLink:
    def test_link_stores_account_id_and_audits(self, client, db, users, login_as, jira_on):
        headers = login_as("t1@empresa.com")
        response = client.post("/api/v1/tickets/link", json={}, headers=headers)
        assert response.status_code == 200
        assert response.json()["account_id"] == "acc-123"
        assert users["t1@empresa.com"].jira_account_id == "acc-123"
        assert db.scalars(select(AuditLog).where(AuditLog.event == "TICKET_LINKED")).first() is not None
        assert jira_on["users"][0]["query"] == "t1@empresa.com"

    def test_link_no_results_404(self, client, users, login_as, jira_on, monkeypatch):
        monkeypatch.setattr(jira_module, "_http_get",
                            lambda url, *, params, auth, headers: httpx.Response(200, json=[]))
        response = client.post("/api/v1/tickets/link", json={},
                               headers=login_as("t1@empresa.com"))
        assert response.status_code == 404

    def test_link_for_other_user_requires_admin(self, client, users, login_as, jira_on):
        headers = login_as("t1@empresa.com")
        response = client.post("/api/v1/tickets/link",
                               json={"user_id": users["t2@empresa.com"].id}, headers=headers)
        assert response.status_code == 403

    def test_admin_links_other_user(self, client, users, login_as, jira_on):
        admin = login_as("admin@empresa.com")
        response = client.post("/api/v1/tickets/link",
                               json={"email": "t1@empresa.com"}, headers=admin)
        assert response.status_code == 200
        assert users["t1@empresa.com"].jira_account_id == "acc-123"

    def test_unlink(self, client, users, login_as, jira_on):
        headers = login_as("t1@empresa.com")
        client.post("/api/v1/tickets/link", json={}, headers=headers)
        assert client.delete("/api/v1/tickets/link", headers=headers).status_code == 204
        assert users["t1@empresa.com"].jira_account_id is None