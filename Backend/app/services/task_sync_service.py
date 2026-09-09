"""Envío de tareas a Jira/Trello (push, unidireccional, opcional).

El portal es la fuente de verdad: la tarea NO depende del sistema externo.
El envío crea el issue/tarjeta y guarda el enlace (external_*). Reenviar
sobrescribe el enlace anterior (permite cambiar de destino).
"""
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.integrations import jira, trello
from app.models.task import Task, TaskEvent
from app.models.user import User


class SyncError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def push_task(db: Session, task: Task, *, target: str, actor: User) -> Task:
    if target == "jira":
        try:
            key, url = jira.create_issue(task)
        except jira.JiraError as exc:
            raise SyncError(str(exc), 400) from exc
        system, external_id = "jira", key
    elif target == "trello":
        try:
            card_id, url = trello.create_card(task)
        except trello.TrelloError as exc:
            raise SyncError(str(exc), 400) from exc
        system, external_id = "trello", card_id
    else:
        raise SyncError("Destino inválido: usa 'jira' o 'trello'")

    task.external_system = system
    task.external_id = external_id
    task.external_url = url
    task.updated_at = utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)

    db.add(TaskEvent(task_id=task.id, user_id=actor.id, event="PUSHED",
                     detail=f"{system}: {external_id}"))
    db.commit()
    return task