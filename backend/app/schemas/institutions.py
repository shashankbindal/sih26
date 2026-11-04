from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import Bureau
from app.schemas.cases import CaseRef, CaseSummary, LinkOut


class InstitutionBrief(BaseModel):
    id: uuid.UUID
    permanent_id: str
    name: str
    district: str | None = None
    state: str | None = None
    ro_code: str | None = None


class InstitutionListItem(InstitutionBrief):
    inst_type: str | None = None
    approval_status: str
    pincode: str | None = None
    open_cases: int = 0
    overdue: int = 0
    open_alerts: int = 0
    score: float | None = None


class InstitutionListPage(BaseModel):
    items: list[InstitutionListItem]
    total: int
    page: int
    page_size: int


class AliasOut(BaseModel):
    id: uuid.UUID
    alias_raw: str
    alias_norm: str
    source: str


class InstitutionSummaryOut(BaseModel):
    open_by_bureau: dict[Bureau, int]
    open_total: int
    overdue: int
    open_alerts: int
    last_action_at: datetime | None = None


class InstitutionDetail(InstitutionBrief):
    inst_type: str | None = None
    address: str | None = None
    pincode: str | None = None
    email_domain: str | None = None
    phone: str | None = None
    approval_status: str
    established_year: int | None = None
    aliases: list[AliasOut]
    summary: InstitutionSummaryOut


class TimelineItem(CaseSummary):
    relations: list[LinkOut] = []


class InstitutionTimeline(BaseModel):
    items: list[TimelineItem]
    total: int


class InstitutionLinkOut(BaseModel):
    id: uuid.UUID
    relation: str
    status: str
    score: float
    version: int
    reasons: list[str] = []
    features: dict = {}
    case_a: CaseRef
    case_b: CaseRef
    decided_at: datetime | None = None
