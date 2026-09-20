"""Tickets del mesón de soporte: LECTURA desde Jira (modelo pull).

v0.11 — ámbito por sede/grupo + KPIs + detalle:
- ÁMBITO (empresa global, muchas sedes): TODAS las consultas se limitan a
  este mesón (gana el primero configurado): EXTRA_JQL crudo > campo
  personalizado (cf[id]) > grupo (membersOf, opcionalmente + sin asignar).
- KPIs: abiertos · riesgo SLA (JQL configurable, JSM) · MTTR (media de
  resolución en la ventana) · satisfacción (campo CSAT opcional).
- Detalle de issue: descripción ADF→texto, comentarios y adjuntos; solo
  issues del proyecto configurado (403 en otro caso).

Base v0.10: «Mis tickets» usa el accountId vinculado (NUNCA currentUser());
caché en memoria por consulta (60 s listas, 5 min KPIs); fail-soft con
provider explícito.
"""
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations import jira
from app.models.user import User


class TicketError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── Tipos de salida ──────────────────────────────────────────────

@dataclass(frozen=True)
class TicketItem:
    key: str
    summary: str
    status_name: str
    status_category: str  # TODO | IN_PROGRESS | DONE
    priority: str
    assignee_name: str | None
    assignee_account_id: str | None
    created: str
    updated: str
    is_mine: bool


@dataclass(frozen=True)
class TicketList:
    provider: str  # jira | unconfigured | unavailable
    linked: bool
    scope_label: str | None
    items: tuple[TicketItem, ...]
    has_more: bool


@dataclass(frozen=True)
class TicketCommentItem:
    author: str | None
    created: str
    body: str


@dataclass(frozen=True)
class TicketAttachmentItem:
    filename: str
    size_kb: int
    mime: str | None


@dataclass(frozen=True)
class TicketDetail:
    key: str
    summary: str
    status_name: str
    status_category: str
    priority: str
    assignee_name: str | None
    assignee_account_id: str | None
    reporter_name: str | None
    created: str
    updated: str
    resolved: str | None
    description: str | None
    comments: tuple[TicketCommentItem, ...]
    attachments: tuple[TicketAttachmentItem, ...]
    is_mine: bool


@dataclass(frozen=True)
class TicketStats:
    provider: str
    open_count: int | None
    sla_risk: int | None
    mttr_hours: float | None
    satisfaction_pct: float | None
    rated_count: int
    resolved_count: int | None
    window_days: int


# ── Caché genérica (fallos NO se cachean: reintento en el siguiente render) ──

_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}


def reset_for_tests() -> None:
    with _lock:
        _cache.clear()


def _cached_call(key: str, ttl: float, fn):
    now = time.monotonic()
    with _lock:
        cached = _cache.get(key)
        if cached is not None and now - cached[0] < ttl:
            return cached[1]
    try:
        value = fn()
    except jira.JiraError:
        return None
    with _lock:
        _cache[key] = (now, value)
    return value


def _cached_search(jql: str) -> tuple[list[dict], bool] | None:
    def fetch() -> tuple[list[dict], bool]:
        data = jira.search_issues(jql)
        return list(data.get("issues", [])), not bool(data.get("isLast", True))

    return _cached_call(f"jql:{jql}", settings.TICKETS_CACHE_TTL_SECONDS, fetch)


# ── Ámbito del mesón (SOLO esta sede/grupo) ──────────────────────

def _scope_condition() -> str | None:
    if settings.JIRA_TICKETS_EXTRA_JQL:
        return settings.JIRA_TICKETS_EXTRA_JQL.strip()
    if settings.JIRA_TICKETS_FIELD_ID and settings.JIRA_TICKETS_FIELD_VALUE:
        value = settings.JIRA_TICKETS_FIELD_VALUE.replace('"', '\\"')
        return f'cf[{settings.JIRA_TICKETS_FIELD_ID}] = "{value}"'
    if settings.JIRA_TICKETS_GROUP:
        group = settings.JIRA_TICKETS_GROUP.replace('"', '\\"')
        condition = f'assignee in membersOf("{group}")'
        if settings.JIRA_TICKETS_INCLUDE_UNASSIGNED:
            return f"({condition} OR assignee IS EMPTY)"
        return condition
    return None


def scope_label() -> str | None:
    if settings.JIRA_TICKETS_EXTRA_JQL:
        return "JQL personalizado"
    if settings.JIRA_TICKETS_FIELD_VALUE:
        return settings.JIRA_TICKETS_FIELD_VALUE
    if settings.JIRA_TICKETS_GROUP:
        return settings.JIRA_TICKETS_GROUP
    return None


def _base_conditions() -> list[str]:
    conditions = [f'project = "{settings.JIRA_TICKETS_PROJECT}"']
    scope = _scope_condition()
    if scope:
        conditions.append(scope)
    return conditions


def _jql(scope: str, account_id: str | None) -> str:
    conditions = _base_conditions()
    if scope == "open":
        conditions.append("statusCategory != Done")
    elif scope == "done":
        conditions.append("statusCategory = Done")
    if account_id:
        conditions.append(f'assignee = "{account_id}"')
    return " AND ".join(conditions) + " ORDER BY priority DESC, updated DESC"


def _ready() -> bool:
    return bool(jira.has_credentials() and settings.JIRA_TICKETS_PROJECT)


_STATUS_CATEGORY = {"To Do": "TODO", "In Progress": "IN_PROGRESS", "Done": "DONE"}


# ── Listas ───────────────────────────────────────────────────────

def list_tickets(db: Session, user: User, *, mine: bool, scope: str = "open") -> TicketList:
    if scope not in ("open", "done", "all"):
        raise TicketError("Ámbito inválido: open | done | all")
    label = scope_label()
    if not _ready():
        return TicketList("unconfigured", bool(user.jira_account_id), label, (), False)

    account_id = user.jira_account_id if mine else None
    if mine and not account_id:
        return TicketList("jira", linked=False, scope_label=label, items=(), has_more=False)

    result = _cached_search(_jql(scope, account_id))
    if result is None:
        return TicketList("unavailable", bool(user.jira_account_id), label, (), False)
    issues, has_more = result
    return TicketList(
        "jira", True, label,
        tuple(_parse(issue, account_id=account_id) for issue in issues), has_more,
    )


def _parse(issue: dict, *, account_id: str | None) -> TicketItem:
    fields = issue.get("fields") or {}
    status = fields.get("status") or {}
    category = ((status.get("statusCategory") or {}).get("name")) or ""
    assignee = fields.get("assignee") or None
    return TicketItem(
        key=issue.get("key") or "",
        summary=fields.get("summary") or "",
        status_name=status.get("name") or "",
        status_category=_STATUS_CATEGORY.get(category, "TODO"),
        priority=((fields.get("priority") or {}).get("name")) or "Medium",
        assignee_name=(assignee or {}).get("displayName"),
        assignee_account_id=assignee.get("accountId") if assignee else None,
        created=(fields.get("created") or "")[:16].replace("T", " "),
        updated=(fields.get("updated") or "")[:16].replace("T", " "),
        is_mine=bool(account_id and assignee and assignee.get("accountId") == account_id),
    )


# ── Detalle de un ticket ─────────────────────────────────────────

_TICKET_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-\d+$")
_DETAIL_FIELDS = [
    "summary", "description", "status", "priority", "assignee", "reporter",
    "created", "updated", "resolutiondate", "comment", "attachment", "project",
]


def _adf_to_text(node) -> str:
    """Convierte Atlassian Document Format a texto plano (párrafos, listas,
    encabezados, citas)."""
    if not isinstance(node, dict):
        return ""
    parts = [_adf_to_text(child) for child in node.get("content") or []]
    text = "".join(parts)
    kind = node.get("type")
    if kind in {"paragraph", "heading", "codeBlock"}:
        return text + "\n"
    if kind == "listItem":
        return f"• {text}\n"
    if kind == "blockquote":
        return f"> {text}\n"
    if kind == "text":
        return str(node.get("text") or "")
    return text


def get_ticket(user: User, key: str) -> TicketDetail:
    if not _ready():
        raise TicketError("Tickets de Jira no están configurados", 503)
    if not _TICKET_KEY_RE.match(key or ""):
        raise TicketError("Clave de ticket inválida", 400)
    try:
        issue = jira.get_issue(key, fields=_DETAIL_FIELDS)
    except jira.JiraNotFoundError as exc:
        raise TicketError(str(exc), 404)
    except jira.JiraError as exc:
        raise TicketError(str(exc), 503)

    fields = issue.get("fields") or {}
    project_key = ((fields.get("project") or {}).get("key")) or ""
    if settings.JIRA_TICKETS_PROJECT and project_key != settings.JIRA_TICKETS_PROJECT:
        raise TicketError("El ticket no pertenece al proyecto del mesón", 403)

    status = fields.get("status") or {}
    category = ((status.get("statusCategory") or {}).get("name")) or ""
    assignee = fields.get("assignee") or {}
    reporter = fields.get("reporter") or {}
    resolution = (fields.get("resolutiondate") or "")[:16].replace("T", " ")

    comments = tuple(
        TicketCommentItem(
            author=((comment.get("author") or {}).get("displayName")),
            created=(comment.get("created") or "")[:16].replace("T", " "),
            body=_adf_to_text(comment.get("body")).strip(),
        )
        for comment in ((fields.get("comment") or {}).get("comments") or [])
    )
    attachments = tuple(
        TicketAttachmentItem(
            filename=attachment.get("filename") or "",
            size_kb=max(1, round((attachment.get("size") or 0) / 1024)),
            mime=attachment.get("mimeType"),
        )
        for attachment in (fields.get("attachment") or [])
    )

    return TicketDetail(
        key=key,
        summary=fields.get("summary") or "",
        status_name=status.get("name") or "",
        status_category=_STATUS_CATEGORY.get(category, "TODO"),
        priority=((fields.get("priority") or {}).get("name")) or "Medium",
        assignee_name=assignee.get("displayName"),
        assignee_account_id=assignee.get("accountId"),
        reporter_name=reporter.get("displayName"),
        created=(fields.get("created") or "")[:16].replace("T", " "),
        updated=(fields.get("updated") or "")[:16].replace("T", " "),
        resolved=resolution or None,
        description=_adf_to_text(fields.get("description")).strip() or None,
        comments=comments,
        attachments=attachments,
        is_mine=bool(user.jira_account_id and assignee.get("accountId") == user.jira_account_id),
    )


# ── KPIs del mesón ───────────────────────────────────────────────

def _parse_jira_dt(value) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        match = re.match(r"^(.*[+-]\d{2})(\d{2})$", text)  # +0000 → +00:00
        if match:
            try:
                return datetime.fromisoformat(f"{match.group(1)}:{match.group(2)}")
            except ValueError:
                return None
        return None


def _rating_to_score(value) -> float | None:
    """4 o '4' → 4 · {'value': 'Extremely satisfied'} → 5 · None si no se entiende."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            lowered = value.strip().lower()
            return {"extremely satisfied": 5, "satisfied": 4, "neutral": 3,
                    "unsatisfied": 2, "extremely unsatisfied": 1}.get(lowered)
    if isinstance(value, dict):
        for candidate in (value.get("value"), value.get("rating")):
            if candidate is not None:
                score = _rating_to_score(candidate)
                if score is not None:
                    return score
    return None


def _done_window_jql(window: int) -> str:
    return " AND ".join(
        [*_base_conditions(), "statusCategory = Done", f"resolved >= -{window}d"]
    ) + " ORDER BY resolved DESC"


def get_stats() -> TicketStats:
    window = settings.JIRA_TICKETS_MTTR_WINDOW_DAYS
    if not _ready():
        return TicketStats("unconfigured", None, None, None, None, 0, None, window)

    open_data = _cached_search(_jql("open", None))  # misma caché que el mesón
    any_ok = open_data is not None
    open_count = len(open_data[0]) if open_data else None

    # Riesgo SLA: consulta propia (solo si hay fragmento configurado).
    sla_risk = None
    if settings.JIRA_TICKETS_SLA_RISK_JQL:
        fragment = settings.JIRA_TICKETS_SLA_RISK_JQL.strip()
        sla_jql = " AND ".join([*_base_conditions(), "statusCategory != Done", fragment])
        result = _cached_call(
            f"jql:{sla_jql}", settings.TICKETS_STATS_CACHE_TTL_SECONDS,
            lambda: jira.search_issues(sla_jql, max_results=50, fields=["summary"]),
        )
        if result is not None:
            any_ok = True
            sla_risk = len(result.get("issues", []))

    # Resueltos de la ventana → MTTR (+ CSAT si hay campo configurado).
    fields = ["created", "resolutiondate"]
    if settings.JIRA_TICKETS_CSAT_FIELD:
        fields.append(settings.JIRA_TICKETS_CSAT_FIELD)
    done_jql = _done_window_jql(window)
    done = _cached_call(
        f"jql:{done_jql}", settings.TICKETS_STATS_CACHE_TTL_SECONDS,
        lambda: jira.search_issues(done_jql, max_results=100, fields=fields),
    )

    mttr_hours = satisfaction_pct = None
    resolved_count = None
    rated_count = 0
    if done is not None:
        any_ok = True
        issues = done.get("issues", [])
        resolved_count = len(issues)
        durations = []
        for issue in issues:
            issue_fields = issue.get("fields") or {}
            created = _parse_jira_dt(issue_fields.get("created"))
            resolved = _parse_jira_dt(issue_fields.get("resolutiondate"))
            if created is not None and resolved is not None and resolved >= created:
                durations.append((resolved - created).total_seconds() / 3600)
        if durations:
            mttr_hours = round(sum(durations) / len(durations), 1)
        if settings.JIRA_TICKETS_CSAT_FIELD:
            scores = [
                score for issue in issues
                if (score := _rating_to_score(
                    (issue.get("fields") or {}).get(settings.JIRA_TICKETS_CSAT_FIELD))) is not None
            ]
            rated_count = len(scores)
            if scores:
                satisfaction_pct = round(100 * sum(1 for s in scores if s >= 4) / len(scores), 1)

    return TicketStats(
        "jira" if any_ok else "unavailable",
        open_count, sla_risk, mttr_hours, satisfaction_pct, rated_count, resolved_count, window,
    )


# ── Vinculación de cuentas (v0.10, sin cambios) ──────────────────

def link_account(db: Session, user: User, *, email: str | None = None) -> dict:
    target_email = (email or user.email).strip().lower()
    candidates = jira.find_user_by_email(target_email)
    exact = [c for c in candidates if str(c.get("emailAddress") or "").lower() == target_email]
    pool = exact or candidates
    if not pool:
        raise TicketError("Jira no devolvió usuarios para ese correo", 404)
    if len(pool) > 1:
        names = ", ".join(str(c.get("displayName") or "?") for c in pool[:5])
        raise TicketError(f"Varios usuarios de Jira coinciden ({names}): usa el correo exacto", 409)
    chosen = pool[0]
    account_id = chosen.get("accountId")
    if not account_id:
        raise TicketError("Jira no devolvió el accountId de ese usuario", 400)
    user.jira_account_id = account_id
    db.add(user)
    db.commit()
    return {"account_id": account_id, "display_name": chosen.get("displayName")}


def unlink_account(db: Session, user: User) -> None:
    user.jira_account_id = None
    db.add(user)
    db.commit()