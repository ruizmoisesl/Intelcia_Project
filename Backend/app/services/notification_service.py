"""Notificaciones por correo: cola en memoria + worker demonio.

Diseño:
- Los routers llaman a notify_* DENTRO del request (sesión viva); los datos
  se extraen a primitivos inmediatamente y la cola solo transporta jobs
  autónomos. El worker envía en background sin bloquear la API.
- HILO POR TAREA (Gmail): el correo de creación lleva
  Message-ID: <task-{id}@dominio>; actualizaciones y comentarios responden
  a ese raíz (In-Reply-To + References) → una única conversación por tarea.
- Nunca se auto-notifica al actor de la acción.
- Fail-soft total. Limitación MVP: la cola no es persistente ni reintenta;
  si el proceso cae con correos pendientes, se pierden (queda en el log).
"""
import logging
import queue
import threading
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.schedule_change import ChangeStatus, ScheduleChange
from app.models.task import Task, TaskComment
from app.models.user import Role, User
from app.services import email_service

logger = logging.getLogger(__name__)

# ── Cola + worker ────────────────────────────────────────────────

@dataclass(frozen=True)
class EmailJob:
    to: str
    subject: str
    html: str
    text: str
    headers: dict[str, str] | None = None


_queue: queue.Queue[EmailJob] = queue.Queue()
_worker_lock = threading.Lock()
_worker_started = False


def _deliver(job: EmailJob) -> None:
    email_service.send_email(
        to=job.to, subject=job.subject, html=job.html, text=job.text, headers=job.headers
    )


def _worker_loop() -> None:
    while True:
        job = _queue.get()
        try:
            _deliver(job)
        except Exception:  # pragma: no cover - defensa extra del worker
            logger.exception("Worker de correo: fallo inesperado")
        finally:
            _queue.task_done()


def _ensure_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        threading.Thread(target=_worker_loop, daemon=True, name="portal-email-worker").start()
        _worker_started = True


def _enqueue(job: EmailJob) -> None:
    if not email_service.is_configured():
        return
    _ensure_worker()
    _queue.put(job)


# Utilidades para pruebas (drenan/procesan la cola de forma síncrona).
def drain_for_tests() -> list[EmailJob]:
    jobs: list[EmailJob] = []
    while True:
        try:
            jobs.append(_queue.get_nowait())
        except queue.Empty:
            break
    for job in jobs:
        _deliver(job)
    return jobs


def reset_for_tests() -> None:
    while True:
        try:
            _queue.get_nowait()
        except queue.Empty:
            break


# ── Plantillas HTML ──────────────────────────────────────────────

MONTHS_ES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
             7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}

SHIFT_HEX = {"green": "#059669", "blue": "#0284c7", "red": "#dc2626",
             "yellow": "#d97706", "purple": "#7c3aed", "slate": "#64748b",
             "indigo": "#4f46e5"}


def _fmt(day: date) -> str:
    return f"{day.day} {MONTHS_ES[day.month]}"


def _layout(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="es"><body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;">
<tr><td style="background:#4f46e5;padding:16px 24px;color:#ffffff;font-size:15px;font-weight:600;">Portal de Gestión</td></tr>
<tr><td style="padding:24px;"><h1 style="margin:0 0 14px;font-size:17px;color:#0f172a;">{title}</h1>{body}</td></tr>
<tr><td style="padding:14px 24px;background:#f8fafc;color:#94a3b8;font-size:11px;">Mensaje automático del Portal de Gestión Empresarial. No respondas a este correo.</td></tr>
</table></td></tr></table></body></html>"""


def _pill(label: str, color: str) -> str:
    return (f"<span style=\"display:inline-block;padding:2px 10px;border-radius:999px;"
            f"background:{SHIFT_HEX.get(color, '#64748b')}1a;color:{SHIFT_HEX.get(color, '#64748b')};"
            f"font-size:12px;font-weight:600;\">{label}</span>")


def _row(label: str, value_html: str) -> str:
    return (f"<tr><td style=\"padding:6px 12px 6px 0;color:#64748b;font-size:13px;white-space:nowrap;"
            f"vertical-align:top;\">{label}</td>"
            f"<td style=\"padding:6px 0;color:#0f172a;font-size:13px;\">{value_html}</td></tr>")


def _button(url: str, label: str) -> str:
    return (f"<p style=\"margin:18px 0 0;\"><a href=\"{url}\" style=\"display:inline-block;"
            f"background:#4f46e5;color:#ffffff;text-decoration:none;padding:10px 18px;"
            f"border-radius:8px;font-size:13px;font-weight:600;\">{label}</a></p>")


def _base_url() -> str:
    return settings.APP_BASE_URL.rstrip("/")


# ── Threading por tarea ──────────────────────────────────────────

def _domain() -> str:
    user = settings.SMTP_USER or ""
    return user.split("@")[-1] if "@" in user else "portal.local"


def _task_thread_headers(task_id: int, *, is_first: bool) -> dict[str, str]:
    """Raíz determinista: la creación define el Message-ID del hilo; el resto
    responde a él (In-Reply-To + References) → una conversación por tarea."""
    root = f"<task-{task_id}@{_domain()}>"
    if is_first:
        return {"Message-ID": root}
    return {"In-Reply-To": root, "References": root}


def _task_subject(task: Task) -> str:
    return f"[Portal] Tarea #{task.id} · {task.title}"


# ── Destinatarios ────────────────────────────────────────────────

def _approvers_emails(db: Session) -> list[str]:
    stmt = select(User.email).where(
        User.role.in_([Role.ADMIN, Role.SUPERVISOR]), User.is_active.is_(True)
    )
    return list(db.scalars(stmt))


# ── Novedades de horario ─────────────────────────────────────────

def notify_change_created(db: Session, change: ScheduleChange) -> None:
    """Novedad PENDING → a todos los ADMIN/SUPERVISOR activos."""
    from app.services.schedule_service import get_shift_definition

    recipients = _approvers_emails(db)
    if not recipients:
        return
    target_def = get_shift_definition(change.requested_shift)
    current = change.current_shift if hasattr(change, "current_shift") else None  # primitivo extraído abajo

    subject = f"[Portal] Novedad de horario · {change.user.name} · semana del {_fmt(change.week_start)}"
    body = (
        f"<p style=\"margin:0 0 10px;color:#334155;font-size:13px;\">"
        f"<strong>{change.user.name}</strong> solicitó un cambio de turno.</p>"
        "<table cellpadding=\"0\" cellspacing=\"0\">"
        + _row("Semana", f"del {_fmt(change.week_start)} al {_fmt(change.week_start.toordinal() and __import__('datetime').date.fromordinal(change.week_start.toordinal() + 6))}")
        + _row("Turno solicitado", _pill(target_def.name, target_def.color))
        + _row("Motivo", change.reason or "—")
        + "</table>"
        + _button(f"{_base_url()}/dashboard/novedades", "Revisar novedad")
    )
    text = (f"{change.user.name} solicitó cambio de turno para la semana del "
            f"{_fmt(change.week_start)}.\nTurno solicitado: {target_def.name} "
            f"({target_def.weekday_start:%H:%M}-{target_def.weekday_end:%H:%M}).\n"
            f"Motivo: {change.reason or '—'}\nRevisa: {_base_url()}/dashboard/novedades")
    for to in recipients:
        _enqueue(EmailJob(to=to, subject=subject, html=_layout("Novedad de horario pendiente", body), text=text))


def notify_change_reviewed(db: Session, change: ScheduleChange) -> None:
    """APPROVED/REJECTED → al usuario afectado."""
    from app.services.schedule_service import get_shift_definition

    approved = change.status == ChangeStatus.APPROVED
    target_def = get_shift_definition(change.requested_shift)
    verb = "aprobada" if approved else "rechazada"
    subject = f"[Portal] Tu novedad fue {verb} · semana del {_fmt(change.week_start)}"

    details = "<table cellpadding=\"0\" cellspacing=\"0\">"
    details += _row("Turno solicitado", _pill(target_def.name, target_def.color))
    if approved:
        details += _row("Efecto", "Este turno reemplaza tu rotación de esa semana.")
    if change.review_note:
        details += _row("Nota del revisor", change.review_note)
    if change.reviewed_by is not None:
        details += _row("Revisada por", change.reviewed_by.name)
    details += "</table>" + _button(f"{_base_url()}/dashboard/horarios?week={change.week_start}", "Ver mi horario")

    text = (f"Tu novedad para la semana del {_fmt(change.week_start)} fue {verb}.\n"
            f"Turno solicitado: {target_def.name}."
            + (f"\nNota: {change.review_note}" if change.review_note else ""))

    _enqueue(EmailJob(
        to=change.user.email, subject=subject,
        html=_layout(f"Tu novedad fue {verb}", details), text=text,
    ))


def notify_change_assigned(db: Session, change: ScheduleChange, *, actor: User) -> None:
    """Asignación directa del admin → al usuario afectado (nunca al propio admin)."""
    if change.user_id == actor.id:
        return
    from app.services.schedule_service import get_shift_definition

    target_def = get_shift_definition(change.requested_shift)
    subject = f"[Portal] Turno asignado · semana del {_fmt(change.week_start)}"
    body = ("<p style=\"margin:0 0 10px;color:#334155;font-size:13px;\">La administración "
            "te asignó un turno para esta semana:</p>"
            "<table cellpadding=\"0\" cellspacing=\"0\">"
            + _row("Turno", _pill(target_def.name, target_def.color))
            + (f"<tr>...</tr>" if change.reason else "")
            + "</table>"
            + _button(f"{_base_url()}/dashboard/horarios?week={change.week_start}", "Ver mi horario"))
    text = (f"Se te asignó {target_def.name} para la semana del {_fmt(change.week_start)}. "
            f"Ver: {_base_url()}/dashboard/horarios?week={change.week_start}")
    _enqueue(EmailJob(to=change.user.email, subject=subject, html=_layout("Turno asignado", body), text=text))


# ── Tareas (todas en el MISMO hilo) ──────────────────────────────

def notify_task_created(db: Session, task: Task, *, actor: User) -> None:
    if task.assignee is None or task.assignee.id == actor.id:
        return
    subject = _task_subject(task)
    details = "<table cellpadding=\"0\" cellspacing=\"0\">"
    details += _row("Asignada a", task.assignee.name)
    details += _row("Creada por", task.created_by.name)
    details += _row("Prioridad", _pill(task.priority.value, "indigo" if task.priority.value == "URGENT" else "slate"))
    if task.due_date:
        details += _row("Vence", _fmt(task.due_date))
    if task.description:
        details += _row("Descripción", task.description.replace("\n", "<br>"))
    details += "</table>" + _button(f"{_base_url()}/dashboard/tareas/{task.id}", "Ver tarea")

    text = (f"Se te asignó la tarea «{task.title}» (#{task.id}).\n"
            f"Prioridad: {task.priority.value}."
            + (f"\nVence: {_fmt(task.due_date)}" if task.due_date else "")
            + f"\nVer: {_base_url()}/dashboard/tareas/{task.id}")

    _enqueue(EmailJob(
        to=task.assignee.email, subject=subject,
        html=_layout("Nueva tarea asignada", details), text=text,
        headers=_task_thread_headers(task.id, is_first=True),  # raíz del hilo
    ))


def notify_task_updated(db: Session, task: Task, summary: list[str], *, actor: User) -> None:
    if task.assignee is None or task.assignee.id == actor.id:
        return
    if not summary:
        return
    subject = _task_subject(task)
    changes = "".join(f"<li style=\"margin:4px 0;color:#334155;font-size:13px;\">{line}</li>"
                      for line in summary)
    body = (f"<p style=\"margin:0 0 8px;color:#334155;font-size:13px;\">"
            f"<strong>{actor.name}</strong> actualizó la tarea:</p>"
            f"<ul style=\"margin:0;padding-left:20px;\">{changes}</ul>"
            + _button(f"{_base_url()}/dashboard/tareas/{task.id}", "Ver tarea"))
    text = f"{actor.name} actualizó «{task.title}»:\n- " + "\n- ".join(summary)

    _enqueue(EmailJob(
        to=task.assignee.email, subject=subject,
        html=_layout("Tarea actualizada", body), text=text,
        headers=_task_thread_headers(task.id, is_first=False),  # mismo hilo
    ))


def notify_task_commented(db: Session, task: Task, comment: TaskComment) -> None:
    """Comentario → al asignado y al creador de la tarea, menos su autor."""
    recipients: dict[int, str] = {}
    if task.assignee is not None and task.assignee.id != comment.user_id:
        recipients[task.assignee.id] = task.assignee.email
    if task.created_by_id != comment.user_id and task.created_by_id not in recipients:
        creator = db.get(User, task.created_by_id)
        if creator is not None and creator.is_active:
            recipients[creator.id] = creator.email
    if not recipients:
        return

    subject = _task_subject(task)
    attachments = ""
    if comment.attachments:
        names = " · ".join(att.original_name for att in comment.attachments)
        attachments = _row("Evidencias adjuntas", names)
    body = (f"<p style=\"margin:0 0 8px;color:#334155;font-size:13px;\">"
            f"<strong>{comment.user.name}</strong> comentó:</p>"
            f"<blockquote style=\"margin:0 0 12px;padding:8px 14px;border-left:3px solid #4f46e5;"
            f"background:#f8fafc;border-radius:6px;color:#0f172a;font-size:13px;\">"
            f"{(comment.content or '').replace(chr(10), '<br>')}</blockquote>"
            "<table cellpadding=\"0\" cellspacing=\"0\">" + attachments + "</table>"
            + _button(f"{_base_url()}/dashboard/tareas/{task.id}", "Ver comentario"))
    text = (f"{comment.user.name} comentó en «{task.title}»:\n{comment.content or ''}\n"
            + (f"Adjuntos: {names}\n" if comment.attachments else "")
            + f"Ver: {_base_url()}/dashboard/tareas/{task.id}")

    for to in recipients.values():
        _enqueue(EmailJob(
            to=to, subject=subject, html=_layout("Nuevo comentario en tu tarea", body), text=text,
            headers=_task_thread_headers(task.id, is_first=False),  # mismo hilo
        ))


# ── Recordatorio semanal (lo lanza weekly_reminder_service) ──────

def notify_weekly_schedule(user: User, week, effective) -> None:
    """week: WeekSchedule (ya con overrides); effective: EffectiveShift."""
    from app.services.schedule_service import get_shift_definition

    definition = get_shift_definition(effective.shift_id)
    monday, sunday = week.days[0].date, week.days[-1].date
    subject = f"[Portal] Tu turno de la próxima semana ({_fmt(monday)} — {_fmt(sunday)})"

    rows = ""
    for day in week.days:
        if day.start is None:
            hours = "Descanso"
            color = "#94a3b8"
        else:
            hours = f"{day.start:%H:%M} – {day.end:%H:%M}" + (" · personalizado" if day.is_custom else "")
            color = SHIFT_HEX.get("purple") if day.is_holiday else SHIFT_HEX.get(definition.color, "#0f172a")
        label = f"{day.day_name} {_fmt(day.date)}"
        if day.is_holiday and day.holiday_name:
            label += f" · {day.holiday_name}"
        rows += (f"<tr style=\"border-bottom:1px solid #eef2f7;\">"
                 f"<td style=\"padding:7px 12px 7px 0;color:#475569;font-size:13px;\">{label}</td>"
                 f"<td style=\"padding:7px 0;font-size:13px;font-weight:600;color:{color};\">{hours}</td></tr>")

    body = (f"<p style=\"margin:0 0 10px;color:#334155;font-size:13px;\">Hola {user.name.split()[0]}, "
            f"estos son tus horarios de la próxima semana:</p>"
            f"<p style=\"margin:0 0 12px;\">{_pill(definition.name, definition.color)} "
            f"<span style=\"color:#94a3b8;font-size:12px;\">"
            + ("rotación semanal" if effective.source.value == "ROTATION"
               else "cambio aprobado" if effective.source.value == "APPROVED_CHANGE" else "turno fijo")
            + "</span></p>"
            f"<table cellpadding=\"0\" cellspacing=\"0\" width=\"100%\">{rows}</table>"
            + _button(f"{_base_url()}/dashboard/horarios?week={monday}", "Ver mi horario completo"))

    plain_days = "\n".join(
        f"{day.day_name} {_fmt(day.date)}: "
        + ("Descanso" if day.start is None else f"{day.start:%H:%M}-{day.end:%H:%M}"
           + (" (festivo)" if day.is_holiday else ""))
        for day in week.days
    )
    text = (f"Hola {user.name}, tu turno de la próxima semana ({_fmt(monday)} — {_fmt(sunday)}) "
            f"es {definition.name}:\n\n{plain_days}\n\nVer: {_base_url()}/dashboard/horarios?week={monday}")

    _enqueue(EmailJob(
        to=user.email, subject=subject, html=_layout("Tu turno de la próxima semana", body), text=text,
    ))