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


class TaskAttachmentOut(BaseModel):
    id: int
    original_name: str
    content_type: str | None
    size_bytes: int
    url: str  # ruta autenticada del frontend (/archivos/{id})


class TaskCommentOut(BaseModel):
    id: int
    user: UserBrief
    content: str | None
    attachments: list[TaskAttachmentOut]
    created_at: datetime


class TaskDetailOut(TaskOut):
    events: list[TaskEventOut] = []
    comments: list[TaskCommentOut] = []


def attachment_out(attachment) -> TaskAttachmentOut:
    return TaskAttachmentOut(
        id=attachment.id, original_name=attachment.original_name,
        content_type=attachment.content_type, size_bytes=attachment.size_bytes,
        url=f"/archivos/{attachment.id}",
    )


def comment_out(comment) -> TaskCommentOut:
    return TaskCommentOut(
        id=comment.id, user=UserBrief.model_validate(comment.user),
        content=comment.content,
        attachments=[attachment_out(att) for att in comment.attachments],
        created_at=comment.created_at,
    )