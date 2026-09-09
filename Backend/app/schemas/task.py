from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.task import TaskPriority, TaskStatus
from app.schemas.user import UserBrief


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=5000)
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: date | None = None
    assignee_id: int | None = None


class TaskUpdateRequest(BaseModel):
    """Solo se aplican los campos presentes (exclude_unset)."""
    title: str | None = Field(default=None, min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=5000)
    priority: TaskPriority | None = None
    due_date: date | None = None
    assignee_id: int | None = None
    status: TaskStatus | None = None


class TaskPushRequest(BaseModel):
    target: str  # "jira" | "trello"


class ExternalRefOut(BaseModel):
    system: str
    id: str
    url: str


class TaskEventOut(BaseModel):
    id: int
    user: UserBrief
    event: str
    detail: str | None
    created_at: datetime


class TaskOut(BaseModel):
    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    assignee: UserBrief | None = None
    created_by: UserBrief
    due_date: date | None
    is_overdue: bool = False
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    external: ExternalRefOut | None = None


class TaskDetailOut(TaskOut):
    events: list[TaskEventOut] = []


class TaskListOut(BaseModel):
    total: int
    today: date
    items: list[TaskOut]