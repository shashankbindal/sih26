"""Schemas for case writes, institution-match review, links, Pre-Action Check, clearances,
notifications and institution creation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import (
    Bureau,
    CaseCategory,
    CaseStatus,
    ClearanceResponse,
    InstActionType,
    LinkStatus,
    MatchStatus,
    PendingStep,
    RelationType,
)
from app.schemas.cases import CaseDetail, InstitutionRef
from app.schemas.clocks import ClockOut
from app.schemas.intake import CreatedLink, ResolutionCandidate
from app.schemas.passport import PassportEntryOut


# ------------------------------------------------------------------ case writes
class CasePatch(BaseModel):
    """Only fields present in the body are applied (model_fields_set)."""

    status: CaseStatus | None = None
    pending_step: PendingStep | None = None
    pending_action: str | None = Field(None, max_length=500)
    category: CaseCategory | None = None
    owner_officer_id: uuid.UUID | None = None
    remark: str | None = Field(None, max_length=2000)
    atr_received: bool = False


class CaseTransfer(BaseModel):
    to_bureau: Bureau
    to_officer_id: uuid.UUID | None = None
    to_ro_code: str | None = Field(None, max_length=10)
    remark: str = Field(min_length=1, max_length=2000)


class CaseRemark(BaseModel):
    remark: str = Field(min_length=1, max_length=2000)
    attachment_name: str | None = Field(None, max_length=255)


class AtrReceived(BaseModel):
    remark: str | None = Field(None, max_length=2000)


class CaseDispose(BaseModel):
    remark: str = Field(min_length=1, max_length=2000)


# ------------------------------------------------------------------ institutions
class InstitutionCreate(BaseModel):
    name: str = Field(min_length=3, max_length=300)
    inst_type: str | None = Field(None, max_length=60)
    address: str | None = Field(None, max_length=500)
    district: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=100)
    pincode: str | None = Field(None, pattern=r"^\d{6}$")
    ro_code: str | None = Field(None, max_length=10)
    email_domain: str | None = Field(None, max_length=120)
    phone: str | None = Field(None, max_length=40)
    permanent_id: str | None = Field(None, pattern=r"^1-\d{7,11}$")
    established_year: int | None = Field(None, ge=1800, le=2100)
    from_case_id: uuid.UUID | None = None


class AliasCreate(BaseModel):
    alias_raw: str = Field(min_length=2, max_length=300)


# ------------------------------------------------------------------ institution match review
class ReviewCandidate(ResolutionCandidate):
    pass


class ReviewItem(BaseModel):
    case_id: uuid.UUID
    display_id: str
    subject: str
    source_channel: str
    received_at: datetime
    owner_bureau: Bureau
    institution_text_raw: str | None = None
    normalised_text: str | None = None
    permanent_id_raw: str | None = None
    language: str | None = None
    match_status: MatchStatus
    top_score: float | None = None
    candidates: list[ReviewCandidate] = []


class ReviewQueue(BaseModel):
    items: list[ReviewItem]
    total: int


class InstitutionMatchDecision(BaseModel):
    decision: Literal["CONFIRM", "REJECT", "CREATE_NEW"]
    institution_id: uuid.UUID | None = None
    reason: str = Field(min_length=3, max_length=1000)
    new_institution: InstitutionCreate | None = None


class InstitutionMatchResult(BaseModel):
    case: CaseDetail
    decision: str
    institution: InstitutionRef | None = None
    alias_added: str | None = None
    links: list[CreatedLink] = []


# ------------------------------------------------------------------ links
class LinkCaseBrief(BaseModel):
    id: uuid.UUID
    display_id: str
    owner_bureau: Bureau
    owner_officer_name: str | None = None
    status: CaseStatus
    category: CaseCategory
    subject: str


class LinkListItem(BaseModel):
    id: uuid.UUID
    relation: RelationType
    status: LinkStatus
    score: float
    version: int
    top_reason: str | None = None
    reasons: list[str] = []
    institution: InstitutionRef | None = None
    case_a: LinkCaseBrief
    case_b: LinkCaseBrief
    suggested_next_action: str | None = None
    lead_bureau: Bureau | None = None
    created_at: datetime
    decided_at: datetime | None = None
    needs_my_decision: bool = False


class LinkListPage(BaseModel):
    items: list[LinkListItem]
    total: int
    page: int
    page_size: int


class ThreadMessageOut(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID | None = None
    author_name: str
    author_bureau: Bureau | None = None
    body: str
    created_at: datetime


class ThreadOut(BaseModel):
    id: uuid.UUID
    lead_bureau: Bureau | None = None
    shared_next_action: str | None = None
    status: str
    messages: list[ThreadMessageOut] = []


class LinkVersionOut(BaseModel):
    version: int
    relation: RelationType
    status: LinkStatus
    score: float
    reasons: list[str] = []
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None
    archived_at: datetime | None = None
    current: bool = False


class FeatureRow(BaseModel):
    key: str
    label: str
    value: float | bool | int | str | None


class LinkDetail(BaseModel):
    id: uuid.UUID
    relation: RelationType
    status: LinkStatus
    score: float
    version: int
    reasons: list[str] = []
    features: dict[str, Any] = {}
    feature_rows: list[FeatureRow] = []
    suggested_next_action: str | None = None
    lead_bureau: Bureau | None = None
    institution: InstitutionRef | None = None
    case_a: CaseDetail
    case_b: CaseDetail
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None
    created_at: datetime
    history: list[LinkVersionOut] = []
    thread: ThreadOut | None = None
    can_decide: bool = False


class LinkDecision(BaseModel):
    decision: Literal["CONFIRM", "REJECT", "DEFER"]
    reason: str = Field(min_length=3, max_length=1000)


class LinkRevert(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class ThreadMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ThreadPatch(BaseModel):
    lead_bureau: Bureau | None = None
    shared_next_action: str | None = Field(None, max_length=2000)


# ------------------------------------------------------------------ pre-action check
class PreActionRequest(BaseModel):
    action_type: InstActionType


class PanelInstitution(BaseModel):
    id: uuid.UUID
    name: str
    permanent_id: str


class PanelClock(BaseModel):
    clock: str
    state: str
    label: str


class OpenMatter(BaseModel):
    case_id: uuid.UUID
    display_id: str
    owner_bureau: Bureau
    owner_officer: str | None = None
    category: CaseCategory
    status: CaseStatus
    pending_step: PendingStep
    pending_days: int
    clocks: list[PanelClock] = []
    relevance: Literal["HIGH", "MEDIUM", "LOW"]
    why: str
    conflicting: bool = False
    link_ids: list[uuid.UUID] = []


class PanelSummary(BaseModel):
    total_open: int
    by_bureau: dict[str, int]
    overdue: int
    conflicting: int


class ChainStep(BaseModel):
    step_order: int
    bureau: Bureau
    state: Literal[
        "NOT_REQUESTED", "PENDING", "CLEARED", "NOT_CLEARED", "CLEARED_WITH_REMARKS", "PENDING_PREVIOUS"
    ]
    label: str | None = None
    clearance_id: uuid.UUID | None = None
    responded_at: datetime | None = None
    remarks: str | None = None


class PreActionPanel(BaseModel):
    institution_action_id: uuid.UUID
    action_type: InstActionType
    institution: PanelInstitution
    rule_note: str
    open_matters: list[OpenMatter]
    summary: PanelSummary
    clearance_chain: list[ChainStep]
    advisory: str


class AcknowledgeRequest(BaseModel):
    remark: str | None = Field(None, max_length=2000)
    proceed: bool
    # The UI checkbox "I have seen the N open matters". Required only to proceed; hold needs none.
    acknowledged: bool = True


class ActorBrief(BaseModel):
    id: uuid.UUID
    name: str
    bureau: Bureau | None = None


class ClearanceOut(BaseModel):
    id: uuid.UUID
    institution_action_id: uuid.UUID
    institution: PanelInstitution
    action_type: InstActionType
    action_status: str
    target_bureau: Bureau
    step_order: int
    step_label: str
    requested_by: ActorBrief
    requested_at: datetime
    request_remark: str | None = None
    response: ClearanceResponse
    responded_by: ActorBrief | None = None
    responded_at: datetime | None = None
    remarks: str | None = None
    snapshot_summary: dict[str, Any] = {}
    open_matter_count: int = 0


class ClearanceRequestCreate(BaseModel):
    target_bureau: Bureau
    remark: str | None = Field(None, max_length=2000)


class ClearanceRespond(BaseModel):
    response: Literal["CLEARED", "NOT_CLEARED", "CLEARED_WITH_REMARKS"]
    remarks: str | None = Field(None, max_length=2000)


class ClearanceListPage(BaseModel):
    items: list[ClearanceOut]
    total: int


class InstitutionActionOut(BaseModel):
    id: uuid.UUID
    institution: PanelInstitution
    action_type: InstActionType
    status: str
    initiated_by: ActorBrief
    initiated_bureau: Bureau
    open_matter_count: int
    created_at: datetime
    acknowledged_at: datetime | None = None
    ack_remark: str | None = None
    clearance_chain: list[ChainStep] = []


class InstitutionActionPage(BaseModel):
    items: list[InstitutionActionOut]
    total: int
    page: int
    page_size: int


class InstitutionActionDetail(InstitutionActionOut):
    panel: dict[str, Any] = {}
    clearances: list[ClearanceOut] = []
    passport: list[PassportEntryOut] = []


class ActionPassport(BaseModel):
    institution_action_id: uuid.UUID
    entries: list[PassportEntryOut]


class AcknowledgeResult(BaseModel):
    action: InstitutionActionOut
    passport_entry: PassportEntryOut


# ------------------------------------------------------------------ notifications
class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None = None
    link_path: str | None = None
    case_id: uuid.UUID | None = None
    institution_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    bureau: Bureau | None = None
    read_at: datetime | None = None
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int


class ReadAllResult(BaseModel):
    updated: int


__all__ = [
    "AcknowledgeRequest",
    "AcknowledgeResult",
    "ActionPassport",
    "ActorBrief",
    "AliasCreate",
    "AtrReceived",
    "CaseDispose",
    "CasePatch",
    "CaseRemark",
    "CaseTransfer",
    "ChainStep",
    "ClearanceListPage",
    "ClearanceOut",
    "ClearanceRequestCreate",
    "ClearanceRespond",
    "ClockOut",
    "FeatureRow",
    "InstitutionActionDetail",
    "InstitutionActionOut",
    "InstitutionActionPage",
    "InstitutionCreate",
    "InstitutionMatchDecision",
    "InstitutionMatchResult",
    "LinkCaseBrief",
    "LinkDecision",
    "LinkDetail",
    "LinkListItem",
    "LinkListPage",
    "LinkRevert",
    "LinkVersionOut",
    "NotificationList",
    "NotificationOut",
    "OpenMatter",
    "PanelClock",
    "PanelInstitution",
    "PanelSummary",
    "PreActionPanel",
    "PreActionRequest",
    "ReadAllResult",
    "ReviewCandidate",
    "ReviewItem",
    "ReviewQueue",
    "ThreadMessageCreate",
    "ThreadMessageOut",
    "ThreadOut",
    "ThreadPatch",
]
