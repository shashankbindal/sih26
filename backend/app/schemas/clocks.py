from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ClockState, ClockType


class ClockOut(BaseModel):
    clock: ClockType
    state: ClockState
    started_at: datetime
    due_at: datetime
    elapsed_ratio: float
    label: str
    short_label: str
    long_label: str
    rule: str
    met_at: datetime | None = None
    paused_at: datetime | None = None
    overdue_seconds: int = 0
