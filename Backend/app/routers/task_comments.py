"""Comentarios y adjuntos de tareas (todos los usuarios autenticados)."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.task import Task, TaskAttachment, TaskComment, TaskEvent
from app.models.user import Role, User
from app.schemas.task import TaskCommentOut, comment_out
from app.services import audit_service, notification_service, storage

router = APIRouter(tags=["Tareas · comentarios"])


@router.post(
    "/api/v1/tasks/{task_id}/comments",
    response_model=TaskCommentOut,
    status_code=201,
    summary="Comentar una tarea (texto y/o archivos)",
)
def create_comment(
    task_id: int,
    content: str | None = Form(default=None),
    files: list[UploadFile] | None = File(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskCommentOut:
    """Cualquier usuario autenticado. Archivos: máx. MAX_UPLOAD_MB por archivo,
    extensiones permitidas (ver storage.ALLOWED_EXTENSIONS)."""
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Tarea no encontrada")

    text = (content or "").strip()
    uploads = [upload for upload in (files or []) if upload.filename]
    if not text and not uploads:
        raise HTTPException(400, "El comentario necesita texto o al menos un archivo")

    comment = TaskComment(task_id=task.id, user_id=current_user.id, content=text or None)
    db.add(comment)
    db.flush()

    saved: list[str] = []
    try:
        for upload in uploads:
            stored_name, size, media_type = storage.save_upload(upload)
            db.add(
                TaskAttachment(
                    comment_id=comment.id, stored_name=stored_name,
                    original_name=(upload.filename or stored_name)[:255],
                    content_type=media_type, size_bytes=size,
                )
            )
            saved.append(stored_name)
        db.flush()
    except storage.StorageError as exc:
        db.rollback()
        for name in saved:  # limpia los ya escritos
            storage.remove_file(name)
        raise HTTPException(400, str(exc))

    preview = text[:80] + ("…" if len(text) > 80 else "")
    db.add(TaskEvent(
        task_id=task.id, user_id=current_user.id, event="COMMENTED",
        detail=preview + (f" · {len(saved)} adjunto(s)" if saved else ""),
    ))
    db.commit()
    db.refresh(comment)
    notification_service.notify_task_commented(db, task, comment)
    return comment_out(comment)


@router.delete("/api/v1/comments/{comment_id}", status_code=204, summary="Eliminar comentario")
def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """El autor o supervisión (admin/supervisor)."""
    comment = db.get(TaskComment, comment_id)
    if comment is None:
        raise HTTPException(404, "Comentario no encontrado")
    if current_user.role not in (Role.SUPERVISOR, Role.ADMIN) and comment.user_id != current_user.id:
        raise HTTPException(403, "Solo puedes eliminar tus propios comentarios")

    stored = [att.stored_name for att in comment.attachments]
    db.add(TaskEvent(task_id=comment.task_id, user_id=current_user.id, event="COMMENT_REMOVED",
                     detail=f"comentario de {comment.user.name}"))
    audit_service.log(db, "TASK_COMMENT_DELETED", actor=current_user,
                      detail=f"tarea {comment.task_id}: comentario de {comment.user.name}")
    db.delete(comment)  # adjuntos en cascada
    db.commit()
    for name in stored:
        storage.remove_file(name)
    return None


@router.get(
    "/api/v1/attachments/{attachment_id}/content",
    summary="Contenido del adjunto (Bearer; el frontend lo proxéa)",
)
def get_attachment_content(
    attachment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    attachment = db.get(TaskAttachment, attachment_id)
    if attachment is None:
        raise HTTPException(404, "Adjunto no encontrado")
    try:
        path = storage.attachment_path(attachment.stored_name)
    except storage.StorageError:
        raise HTTPException(404, "Adjunto no encontrado")
    if not path.exists():
        raise HTTPException(404, "El archivo ya no existe en disco")

    return FileResponse(
        path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.original_name,
        content_disposition_type="inline",  # las imágenes se renderizan; el resto se descarga
    )