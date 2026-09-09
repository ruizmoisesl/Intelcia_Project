from datetime import date, time

from pydantic import BaseModel, Field

from app.models.user import ShiftId


class DayOverrideCreateRequest(BaseModel):
    user_id: int
    date: date
    shift: ShiftId | None = None       # modo «turno de un día»
    start: time | None = None          # modo «horas exactas» ("HH:MM")
    end: time | None = None
    reason: str | None = Field(default=None, max_length=500)