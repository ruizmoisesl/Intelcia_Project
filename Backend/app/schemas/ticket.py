from pydantic import BaseModel, EmailStr

from app.schemas.user import UserBrief


class TicketOut(BaseModel):
    key: str
    url: str
    summary: str
    status_name: str
    status_category: str  # TODO | IN_PROGRESS | DONE
    priority: str
    assignee_name: str | None
    assignee_account_id: str | None
    created: str
    updated: str
    is_mine: bool


class TicketListOut(BaseModel):
    provider: str        # jira | unconfigured | unavailable
    linked: bool
    total: int           # traídos (el endpoint nuevo de Jira no devuelve total global)
    has_more: bool
    account_id: str | None = None
    items: list[TicketOut]


class LinkRequest(BaseModel):
    email: EmailStr | None = None
    user_id: int | None = None  # solo ADMIN: vincular a otro usuario


class LinkOut(BaseModel):
    linked: bool
    account_id: str | None
    display_name: str | None
    user: UserBrief

class TicketListOut(BaseModel):
    provider: str
    linked: bool
    scope_label: str | None = None   # ← nuevo: sede/grupo configurado
    total: int
    has_more: bool
    account_id: str | None = None
    items: list[TicketOut]


class TicketCommentOut(BaseModel):
    author: str | None
    created: str
    body: str


class TicketAttachmentOut(BaseModel):
    filename: str
    size_kb: int
    mime: str | None


class TicketDetailOut(BaseModel):
    key: str
    url: str
    summary: str
    status_name: str
    status_category: str
    priority: str
    assignee_name: str | None
    reporter_name: str | None
    created: str
    updated: str
    resolved: str | None
    description: str | None
    comments_count: int
    comments: list[TicketCommentOut]
    attachments: list[TicketAttachmentOut]
    is_mine: bool


class TicketStatsOut(BaseModel):
    provider: str
    open_count: int | None
    sla_risk: int | None
    sla_configured: bool
    mttr_hours: float | None
    satisfaction_pct: float | None
    rated_count: int
    resolved_count: int | None
    window_days: int


class JiraGroupOut(BaseModel):
    name: str
    group_id: str | None = None