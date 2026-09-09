"""CRUD de tareas + envío a Jira/Trello."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core import dates
from app.core.database import get_db
from app.dependencies.auth import get_current_user, require_supervisor
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.schemas.task import (
    TaskCreateRequest, TaskDetailOut, TaskListOut, TaskOut, TaskPushRequest, TaskUpdateRequest,
)
from app.schemas.user import UserBrief
from app.services import audit_service, task_service, task_sync_service

router = APIRouter(prefix="/api/v1/tasks", tags=["Tareas"])


def _task_out(task: Task, today: date) -> TaskOut:
    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        assignee=UserBrief.model_validate(task.assignee) if task.assignee else None,
        created_by=UserBrief.model_validate(task.created_by),
        due_date=task.due_date,
        is_overdue=task.due_date is not None
        and task.due_date < today
        and task.status != TaskStatus.DONE,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        external=(
            {"system": task.external_system, "id": task.external_id, "url": task.external_url}
            if task.external_id
            else None
        ),
    )


def _detail_out(task: Task, today: date) -> TaskDetailOut:
    detail = TaskDetailOut(**_task_out(task, today).model_dump())
    detail.events = [
        {"id": event.id, "user": UserBrief.model_validate(event.user), "event": event.event,
         "detail": event.detail, "created_at": event.created_at}
        for event in task.events
    ]
    return detail


@router.post("", response_model=TaskDetailOut, status_code=201, summary="Crear tarea (supervisor/admin)")
def create_task(
    payload: TaskCreateRequest,
    supervisor: User = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    try:
        task = task_service.create_task(
            db, title=payload.title, description=payload.description, priority=payload.priority,
            due_date=payload.due_date, assignee_id=payload.assignee_id, created_by=supervisor,
        )
    except task_service.TaskError as exc:
        raise HTTPException(exc.status_code, exc.message)
    audit_service.log(db, "TASK_CREATED", actor=supervisor, target=task.assignee, detail=task.title)
    return _detail_out(task, dates.today())


@router.get("", response_model=TaskListOut, summary="Listar tareas (empleados: solo las suyas)")
def list_tasks(
    status: TaskStatus | None = Query(default=None),
    priority: TaskPriority | None = Query(default=None),
    assignee_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = dates.today()
    items, total = task_service.list_tasks(
        db, requester=current_user, status=status, priority=priority,
        assignee_id=assignee_id, limit=limit, offset=offset,
    )
    return TaskListOut(total=total, today=today, items=[_task_out(task, today) for task in items])


@router.get("/{task_id}", response_model=TaskDetailOut, summary="Detalle con historial")
def get_task(task_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        task = task_service.get_task_for(db, current_user, task_id)
    except task_service.TaskError as exc:
        raise HTTPException(exc.status_code, exc.message)
    return _detail_out(task, dates.today())


@router.patch("/{task_id}", response_model=TaskDetailOut, summary="Actualizar tarea")
def update_task(
    task_id: int,
    payload: TaskUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        task = task_service.get_task_for(db, current_user, task_id)
        task = task_service.update_task(db, task, requester=current_user,
                                        changes=payload.model_dump(exclude_unset=True))
    except task_service.TaskError as exc:
        raise HTTPException(exc.status_code, exc.message)
    audit_service.log(db, "TASK_UPDATED", actor=current_user, target=task.assignee, detail=task.title)
    return _detail_out(task, dates.today())


@router.delete("/{task_id}", status_code=204, summary="Eliminar tarea (supervisor/admin)")
def delete_task(task_id: int, supervisor: User = Depends(require_supervisor), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Tarea no encontrada")
    audit_service.log(db, "TASK_DELETED", actor=supervisor, target=task.assignee, detail=task.title)
    task_service.delete_task(db, task)
    return None


@router.post("/{task_id}/push", response_model=TaskDetailOut, summary="Enviar a Jira/Trello (supervisor/admin)")
def push_task(
    task_id: int,
    payload: TaskPushRequest,
    supervisor: User = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Tarea no encontrada")
    try:
        task = task_sync_service.push_task(db, task, target=payload.target, actor=supervisor)
    except task_sync_service.SyncError as exc:
        raise HTTPException(exc.status_code, exc.message)
    audit_service.log(db, "TASK_PUSHED", actor=supervisor, target=task.assignee,
                      detail=f"{task.title} → {task.external_system}")
    return _detail_out(task, dates.today())