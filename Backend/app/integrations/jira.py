"""Envío de tareas a Jira Cloud (REST API v3, auth básica email + API token).

Setup:
1. Atlassian → Cuenta → Seguridad → «Crear y gestionar tokens de API».
2. .env: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY.
   (El proyecto debe tener un tipo de issue llamado «Task».)
Sin configuración completa, ``create_issue`` lanza JiraError con mensaje claro:
el portal funciona igual (la integración es opcional y fail-soft).
"""
import httpx

from app.core.config import settings

_JIRA_PRIORITY = {"URGENT": "Highest", "HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}


class JiraError(Exception):
    """Fallo al consultar Jira (se degrada; nunca rompe el flujo del portal)."""


def _http_post(url: str, *, json: dict, auth: tuple, headers: dict) -> httpx.Response:
    """Indirección de HTTP (permite simular Jira en pruebas)."""
    return httpx.post(url, json=json, auth=auth, headers=headers, timeout=15.0)


def is_configured() -> bool:
    return all(
        [settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN, settings.JIRA_PROJECT_KEY]
    )


def _adf(text: str) -> dict:
    """Description en Atlassian Document Format (mínimo: un párrafo)."""
    return {
        "type": "doc", "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def create_issue(task) -> tuple[str, str]:
    """Crea el issue a partir de la tarea; devuelve (clave, url)."""
    if not is_configured():
        raise JiraError("Jira no está configurado (JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN / JIRA_PROJECT_KEY)")

    fields: dict = {
        "project": {"key": settings.JIRA_PROJECT_KEY},
        "summary": task.title,
        "issuetype": {"name": "Task"},
        "priority": {"name": _JIRA_PRIORITY.get(task.priority.value, "Medium")},
    }
    if task.description:
        fields["description"] = _adf(task.description)
    if task.due_date:
        fields["duedate"] = task.due_date.isoformat()

    try:
        response = _http_post(
            f"{settings.JIRA_BASE_URL}/rest/api/3/issue",
            json={"fields": fields},
            auth=(settings.JIRA_EMAIL, settings.JIRA_API_TOKEN),
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise JiraError(f"Error de red contra Jira: {exc}") from exc

    if response.status_code not in (200, 201):
        raise JiraError(f"Jira respondió {response.status_code}")

    key = response.json().get("key", "")
    if not key:
        raise JiraError("Jira no devolvió la clave del issue")
    return key, f"{settings.JIRA_BASE_URL}/browse/{key}"

def has_credentials() -> bool:
    """Credenciales base (sin proyecto): válido para búsqueda de usuarios."""
    return all([settings.JIRA_BASE_URL, settings.JIRA_EMAIL, settings.JIRA_API_TOKEN])


def _http_get(url: str, *, params: dict, auth: tuple, headers: dict) -> httpx.Response:
    """Indirección de HTTP (permite simular Jira en pruebas)."""
    return httpx.get(url, params=params, auth=auth, headers=headers, timeout=15.0)


def search_issues(jql: str, *, max_results: int = 100, fields: list[str] | None = None) -> dict:
    """POST /rest/api/3/search/jql (el clásico /search está deprecado).

    Devuelve {"issues": [...], "isLast": bool, "nextPageToken": ...}.
    Lanza JiraError si no hay credenciales o la consulta falla.
    """
    if not has_credentials():
        raise JiraError("Jira no está configurado (JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN)")
    payload = {
        "jql": jql,
        "maxResults": max_results,
        "fields": fields or ["summary", "status", "priority", "assignee", "created", "updated"],
    }
    try:
        response = _http_post(
            f"{settings.JIRA_BASE_URL}/rest/api/3/search/jql",
            json=payload,
            auth=(settings.JIRA_EMAIL, settings.JIRA_API_TOKEN),
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise JiraError(f"Error de red contra Jira: {exc}") from exc
    if response.status_code != 200:
        raise JiraError(f"Jira respondió {response.status_code}")
    data = response.json()
    if "issues" not in data:
        raise JiraError("Respuesta de Jira sin issues")
    return data


def find_user_by_email(email: str) -> list[dict]:
    """GET /rest/api/3/user/search?query=<email> → candidatos con accountId.

    Nota de privacidad: emailAddress puede venir oculto; por eso el servicio
    exige match exacto de email o candidato único.
    """
    if not has_credentials():
        raise JiraError("Jira no está configurado (JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN)")
    try:
        response = _http_get(
            f"{settings.JIRA_BASE_URL}/rest/api/3/user/search",
            params={"query": email},
            auth=(settings.JIRA_EMAIL, settings.JIRA_API_TOKEN),
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise JiraError(f"Error de red contra Jira: {exc}") from exc
    if response.status_code != 200:
        raise JiraError(f"Jira respondió {response.status_code} buscando el usuario")
    return list(response.json())

class JiraNotFoundError(JiraError):
    """El issue/ticket consultado no existe."""


def get_issue(issue_key: str, *, fields: list[str]) -> dict:
    """GET /rest/api/3/issue/{key} — detalle (descripción ADF, comentarios,
    adjuntos si se piden en ``fields``)."""
    if not has_credentials():
        raise JiraError("Jira no está configurado (JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN)")
    try:
        response = _http_get(
            f"{settings.JIRA_BASE_URL}/rest/api/3/issue/{issue_key}",
            params={"fields": ",".join(fields)},
            auth=(settings.JIRA_EMAIL, settings.JIRA_API_TOKEN),
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise JiraError(f"Error de red contra Jira: {exc}") from exc
    if response.status_code == 404:
        raise JiraNotFoundError(f"El ticket {issue_key} no existe en Jira")
    if response.status_code != 200:
        raise JiraError(f"Jira respondió {response.status_code} al pedir {issue_key}")
    return response.json()


def find_groups(query: str = "") -> list[dict]:
    """GET /rest/api/3/groups/picker — descubrir el nombre exacto del grupo."""
    if not has_credentials():
        raise JiraError("Jira no está configurado (JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN)")
    try:
        response = _http_get(
            f"{settings.JIRA_BASE_URL}/rest/api/3/groups/picker",
            params={"query": query},
            auth=(settings.JIRA_EMAIL, settings.JIRA_API_TOKEN),
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise JiraError(f"Error de red contra Jira: {exc}") from exc
    if response.status_code != 200:
        raise JiraError(f"Jira respondió {response.status_code} al buscar grupos")
    return list(response.json().get("groups", []))