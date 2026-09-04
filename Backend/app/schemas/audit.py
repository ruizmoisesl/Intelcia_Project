from datetime import datetime

from pydantic import BaseModel

from app.schemas.user import UserBrief


class AuditOut(BaseModel):
    id: int
    event: str
    actor: UserBrief | None = None
    target_user: UserBrief | None = None
    detail: str | None
    created_at: datetime


class AuditListOut(BaseModel):
    total: int
    items: list[AuditOut]