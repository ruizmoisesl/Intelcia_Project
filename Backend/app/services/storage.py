"""Almacenamiento local de adjuntos (futuro: Google Drive con el mismo patrón).

- Nombre en disco: UUID + extensión (irrepetible, sin caracteres peligrosos).
- El nombre original vive en la BD (TaskAttachment) para la descarga.
- Validaciones: extensión permitida y tamaño máximo por archivo.
"""
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings

ALLOWED_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",           # imágenes
    ".pdf", ".txt", ".md", ".csv",                               # documentos ligeros
    ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".zip",           # office / comprimidos
})


class StorageError(Exception):
    """Error de validación/escritura de adjuntos (→ HTTP 400)."""


def uploads_dir() -> Path:
    path = Path(settings.UPLOADS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(upload: UploadFile) -> tuple[str, int, str | None]:
    """Guarda el archivo; devuelve (stored_name, size_bytes, content_type)."""
    original = (upload.filename or "").strip()
    ext = Path(original).suffix.lower()
    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise StorageError(
            f"Tipo de archivo no permitido ({ext or 'sin extensión'}). "
            "Permitidos: imágenes, PDF, Office, txt/csv, zip."
        )

    data = upload.file.read()
    if not data:
        raise StorageError("El archivo está vacío.")
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise StorageError(f"El archivo supera el máximo de {settings.MAX_UPLOAD_MB} MB.")

    stored_name = f"{uuid4().hex}{ext}"
    (uploads_dir() / stored_name).write_bytes(data)
    return stored_name, len(data), upload.content_type


def attachment_path(stored_name: str) -> Path:
    # Defensa contra path traversal (stored_name viene de la BD).
    if "/" in stored_name or ".." in stored_name or stored_name.startswith("."):
        raise StorageError("Nombre de archivo inválido")
    return uploads_dir() / stored_name


def remove_file(stored_name: str) -> None:
    """Elimina el archivo de disco (best-effort: nunca rompe el flujo)."""
    try:
        attachment_path(stored_name).unlink(missing_ok=True)
    except (OSError, StorageError):
        pass