from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.enums import Bureau


class PassportEntryOut(BaseModel):
    seq: int
    event: str
    actor_id: uuid.UUID | None = None
    actor_name: str
    actor_bureau: Bureau | None = None
    payload: dict[str, Any]
    attachment_name: str | None = None
    created_at: datetime
    hash: str
    hash_short: str
    prev_hash: str


class PassportOut(BaseModel):
    case_id: uuid.UUID
    entries: list[PassportEntryOut]


class VerifyOut(BaseModel):
    ok: bool
    count: int
    first_bad_seq: int | None = None
    checked_at: datetime
