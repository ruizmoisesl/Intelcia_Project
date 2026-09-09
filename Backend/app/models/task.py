"""Tareas: creación, asignación, estados, prioridades, fechas límite e historial.

- Fuente de verdad: el portal. Jira/Trello son destinos de envío opcionales
  (``task_sync_service``) enlazados en ``external_*``.
- Empleados: ven y avanzan SUS tareas (Pendiente → En proceso → Completada).
- Supervisores/admin: todo.
"""
import enum
from datetime import date, datetime

from sqlalchemy import Date, Enum as SAEnum, ForeignKey, String, Text, func, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime, utcnow
from app.models.user import User

class TaskComment(Base):
    """Comentario con evidencias (todos los usuarios autenticados)."""
    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="selectin")
    attachments: Mapped[list["TaskAttachment"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="TaskAttachment.id.asc()"
    )

class TaskAttachment(Base):
    """Archivo adjunto de un comentario. En disco se guarda con nombre UUID;
    el original se conserva aquí para la descarga."""
    __tablename__ = "task_attachments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    comment_id: Mapped[int] = mapped_column(ForeignKey("task_comments.id"), nullable=False, index=True)
    stored_name: Mapped[str] = mapped_column(String(100), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utcnow, server_default=func.now()
    )


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


class TaskPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status", native_enum=False, length=20),
        nullable=False, default=TaskStatus.PENDING,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SAEnum(TaskPriority, name="task_priority", native_enum=False, length=20),
        nullable=False, default=TaskPriority.MEDIUM,
    )
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    #: Enlace con Jira/Trello tras un envío (push).
    external_system: Mapped[str | None] = mapped_column(String(20), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow, server_default=func.now())

    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id], lazy="selectin")
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id], lazy="selectin")
    events: Mapped[list["TaskEvent"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin",
        order_by="TaskEvent.created_at.desc(), TaskEvent.id.desc()",
    )

    comments: Mapped[list["TaskComment"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin",
        order_by="TaskComment.created_at.asc(), TaskComment.id.asc()",
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} {self.title!r} {self.status.value}>"


class TaskEvent(Base):
    """Historial de la tarea (quién, qué, cuándo)."""
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, server_default=func.now())

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="selectin")