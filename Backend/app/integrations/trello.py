"""Envío de tareas a Trello (REST API con key + token).

Setup:
1. https://trello.com/power-ups/admin → crear integración → obtener Key y Token.
2. idList: abre la lista en el navegador y añade «.json» a su URL (o vía GET /1/lists).
3. .env: TRELLO_KEY, TRELLO_TOKEN, TRELLO_LIST_ID.
Fail-soft: sin configuración, ``create_card`` lanza TrelloError con mensaje claro.
"""
import httpx

from app.core.config import settings

BASE_URL = "https://api.trello.com/1"


class TrelloError(Exception):
    """Fallo al consultar Trello (se degrada; nunca rompe el flujo del portal)."""


def _http_post(url: str, *, params: dict, json: dict) -> httpx.Response:
    """Indirección de HTTP (permite simular Trello en pruebas)."""
    return httpx.post(url, params=params, json=json, timeout=15.0)


def is_configured() -> bool:
    return all([settings.TRELLO_KEY, settings.TRELLO_TOKEN, settings.TRELLO_LIST_ID])


def create_card(task) -> tuple[str, str]:
    """Crea la tarjeta a partir de la tarea; devuelve (id, shortUrl)."""
    if not is_configured():
        raise TrelloError("Trello no está configurado (TRELLO_KEY / TRELLO_TOKEN / TRELLO_LIST_ID)")

    payload: dict = {"idList": settings.TRELLO_LIST_ID, "name": task.title}
    if task.description:
        payload["desc"] = task.description
    if task.due_date:
        payload["due"] = f"{task.due_date.isoformat()}T16:00:00.000Z"

    try:
        response = _http_post(
            f"{BASE_URL}/cards",
            params={"key": settings.TRELLO_KEY, "token": settings.TRELLO_TOKEN},
            json=payload,
        )
    except httpx.HTTPError as exc:
        raise TrelloError(f"Error de red contra Trello: {exc}") from exc

    if response.status_code not in (200, 201):
        raise TrelloError(f"Trello respondió {response.status_code}")

    data = response.json()
    card_id, url = data.get("id", ""), data.get("shortUrl", "")
    if not card_id or not url:
        raise TrelloError("Trello no devolvió los datos de la tarjeta")
    return card_id, url