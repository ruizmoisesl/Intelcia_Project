"""Contratos de API de novedades de horario."""
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.schedule_change import ChangeStatus
from app.models.user import ShiftId
from app.schemas.schedule import ShiftInfo
from app.schemas.user import UserBrief


class ChangeCreateRequest(BaseModel):
    week_start: date
    requested_shift: ShiftId  # el enum solo admite SHIFT_1..4 (no HOLIDAY)
    reason: str | None = Field(default=None, max_length=500)
    user_id: int | None = None  # solo ADMIN: asignación para otro usuario


class ReviewRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class ChangeOut(BaseModel):
    id: int
    user: UserBrief
    week_start: date
    requested_shift: ShiftInfo
    reason: str | None
    status: ChangeStatus
    review_note: str | None
    requested_by: UserBrief
    reviewed_by: UserBrief | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
    current_shift: ShiftInfo | None = None  # turno vigente esa semana (para el aprobador)  