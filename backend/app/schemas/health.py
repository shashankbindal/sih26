from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HealthOut(BaseModel):
    status: str
    db: str
    version: str
    seeded_at: datetime | None = None
