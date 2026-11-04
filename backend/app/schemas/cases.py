from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import (
    Bureau,
    CaseCategory,
    CaseStatus,
    LinkStatus,
    MatchStatus,
    PendingStep,
    RelationType,
    SourceChannel,
)
from app.schemas.clocks import ClockOut


class InstitutionRef(BaseModel):
    id: uuid.UUID
    permanent_id: str
    name: str
    district: str | None = None
    state: str | None = None
    ro_code: str | None = None


class InstitutionSnapshot(InstitutionRef):
    inst_type: str | None = None
    address: str | None = None
    pincode: str | None = None
    approval_status: str | None = None


class OwnerOut(BaseModel):
    id: uuid.UUID
    name: str
    designation: str | None = None


class AlertCounts(BaseModel):
    clock_amber: int = 0
    clock_breached: int = 0
    pending_links: int = 0
    conflicting: int = 0
    total: int = 0


class CaseSummary(BaseModel):
    id: uuid.UUID
    display_id: str
    source_channel: SourceChannel
    source_ref: str | None = None
    received_at: datetime
    institution: InstitutionRef | None = None
    institution_text_raw: str | None = None
    institution_match_status: MatchStatus
    category: CaseCategory
    subject: str
    owner_bureau: Bureau
    owner_ro_code: str | None = None
    owner_officer: OwnerOut | None = None
    status: CaseStatus
    pending_step: PendingStep
    pending_since: datetime | None = None
    pending_action: str | None = None
    disposed_at: datetime | None = None
    language: str | None = None
    clocks: list[ClockOut] = []
    alerts: AlertCounts = AlertCounts()
    link_relations: list[RelationType] = []  # distinct relations of active non-UNRELATED links, worst first
    overdue: bool = False


class CaseListPage(BaseModel):
    items: list[CaseSummary]
    total: int
    page: int
    page_size: int


class CaseRef(BaseModel):
    id: uuid.UUID
    display_id: str
    subject: str
    owner_bureau: Bureau
    status: CaseStatus


class LinkOut(BaseModel):
    id: uuid.UUID
    relation: RelationType
    status: LinkStatus
    score: float
    version: int
    reasons: list[str] = []
    other_case: CaseRef


class ComplainantOut(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    party_type: str | None = None


class SourceRefOut(BaseModel):
    channel: SourceChannel
    ref: str


class MatchCandidateOut(BaseModel):
    rank: int
    institution_id: uuid.UUID
    name: str
    permanent_id: str
    score: float
    reasons: list[str] = []
    status: MatchStatus


class CaseDetail(CaseSummary):
    description: str | None = None
    description_norm: str | None = None  # normalised, PII-masked; null whenever description is masked
    permanent_id_raw: str | None = None
    institution_match_score: float | None = None
    category_suggested: CaseCategory | None = None
    created_at: datetime
    updated_at: datetime
    complainant: ComplainantOut
    masked: bool
    masked_fields: list[str] = []
    institution_snapshot: InstitutionSnapshot | None = None
    match_candidates: list[MatchCandidateOut] = []
    source_refs: list[SourceRefOut] = []
    links: list[LinkOut] = []
    suggested_actions: list[str] = []


class RevealPiiRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)
