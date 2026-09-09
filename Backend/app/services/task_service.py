"""Tareas: reglas de negocio, permisos, transiciones e historial."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models.task import Task, TaskEvent, TaskPriority, TaskStatus
from app.models.user import Role, User
from app.services import auth_service


class TaskError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


#: Transiciones que un EMPLEADO puede hacer por sí mismo (solo hacia delante).
_FORWARD: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.DONE}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.DONE}),
    TaskStatus.DONE: frozenset(),
}

_EDITABLE_FIELDS = {"title", "description", "priority", "due_date", "assignee_id", "status"}


def _log_event(db: Session, task: Task, user: User, event: str, detail: str | None = None) -> None:
    db.add(TaskEvent(task_id=task.id, user_id=user.id, event=event, detail=detail))


def _resolve_assignee(db: Session, assignee_id: int | None) -> User | None:
    if assignee_id is None:
        return None
    assignee = auth_service.get_user_by_id(db, assignee_id)
    if assignee is None:
        raise TaskError("El usuario asignado no existe", 404)
    if not assignee.is_active:
        raise TaskError("El usuario asignado está inactivo", 400)
    return assignee


def create_task(
    db: Session, *, title: str, description: str | None, priority: TaskPriority,
    due_date: date | None, assignee_id: int | None, created_by: User,
) -> Task:
    assignee = _resolve_assignee(db, assignee_id)
    task = Task(
        title=title.strip(),
        description=(description or "").strip() or None,
        priority=priority,
        due_date=due_date,
        assignee_id=assignee.id if assignee else None,
        created_by_id=created_by.id,
    )
    db.add(task)
    db.flush()
    _log_event(db, task, created_by, "CREATED",
               f"prioridad {priority.value}" + (f"; vence {due_date}" if due_date else ""))
    if assignee is not None:
        _log_event(db, task, created_by, "ASSIGNED", f"asignada a {assignee.name}")
    db.commit()
    db.refresh(task)
    return task


def list_tasks(
    db: Session, *, requester: User, status: TaskStatus | None = None,
    priority: TaskPriority | None = None, assignee_id: int | None = None,
    limit: int = 50, offset: int = 0,
) -> tuple[list[Task], int]:
    conditions = []
    if requester.role == Role.EMPLOYEE:
        conditions.append(Task.assignee_id == requester.id)  # solo SUS tareas
    elif assignee_id is not None:
        conditions.append(Task.assignee_id == assignee_id)
    if status is not None:
        conditions.append(Task.status == status)
    if priority is not None:
        conditions.append(Task.priority == priority)

    count_stmt = select(func.count()).select_from(Task)
    stmt = select(Task)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
        stmt = stmt.where(*conditions)

    total = db.scalar(count_stmt) or 0
    stmt = stmt.order_by(Task.created_at.desc(), Task.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt)), total


def get_task_for(db: Session, requester: User, task_id: int) -> Task:
    """Acceso con control: empleado solo a sus tareas."""
    task = db.get(Task, task_id)
    if task is None:
        raise TaskError("Tarea no encontrada", 404)
    if requester.role == Role.EMPLOYEE and task.assignee_id != requester.id:
        raise TaskError("No tienes acceso a esta tarea", 403)
    return task


def update_task(db: Session, task: Task, *, requester: User, changes: dict) -> Task:
    """Actualización parcial (exclude_unset). Empleado: solo estado, solo avanzar."""
    unknown = set(changes) - _EDITABLE_FIELDS
    if unknown:
        raise TaskError(f"Campos no editables: {', '.join(sorted(unknown))}")

    if requester.role == Role.EMPLOYEE:
        if task.assignee_id != requester.id:
            raise TaskError("No tienes acceso a esta tarea", 403)
        forbidden = set(changes) - {"status"}
        if forbidden:
            raise TaskError("Solo puedes cambiar el estado de tus tareas", 403)
        new_status = changes.get("status")
        if new_status is not None and new_status != task.status:
            if new_status not in _FORWARD[task.status]:
                raise TaskError(
                    "Solo puedes avanzar el estado: Pendiente → En proceso → Completada", 403
                )

    touched: list[str] = []

    if "title" in changes:
        task.title = str(changes["title"]).strip()
        touched.append("title")
    if "description" in changes:
        task.description = (changes["description"] or "").strip() or None
        touched.append("description")
    if "priority" in changes and changes["priority"] != task.priority:
        old = task.priority
        task.priority = changes["priority"]
        _log_event(db, task, requester, "PRIORITY_CHANGED", f"{old.value} → {task.priority.value}")
    if "due_date" in changes and changes["due_date"] != task.due_date:
        task.due_date = changes["due_date"]
        _log_event(db, task, requester, "DUE_CHANGED",
                   f"vence {task.due_date}" if task.due_date else "sin fecha límite")
    if "assignee_id" in changes and changes["assignee_id"] != task.assignee_id:
        assignee = _resolve_assignee(db, changes["assignee_id"])
        task.assignee_id = assignee.id if assignee else None
        _log_event(db, task, requester, "ASSIGNED",
                   f"asignada a {assignee.name}" if assignee else "sin asignar")
    if "status" in changes and changes["status"] != task.status:
        old = task.status
        task.status = changes["status"]
        task.completed_at = utcnow() if task.status == TaskStatus.DONE else None
        _log_event(db, task, requester, "STATUS_CHANGED", f"{old.value} → {task.status.value}")

    if touched:
        _log_event(db, task, requester, "UPDATED", f"campos: {', '.join(sorted(touched))}")

    task.updated_at = utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: Task) -> None:
    db.delete(task)  # los eventos se eliminan en cascada (ORM)
    db.commit()