from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import CaseStatus


class SearchInstitution(BaseModel):
    id: uuid.UUID
    permanent_id: str
    name: str
    district: str | None = None
    score: float


class SearchCase(BaseModel):
    id: uuid.UUID
    display_id: str
    subject: str
    institution_name: str | None = None
    status: CaseStatus


class SearchResult(BaseModel):
    institutions: list[SearchInstitution]
    cases: list[SearchCase]
