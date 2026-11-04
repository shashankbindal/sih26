"""Intake schemas: CaseCreate / CaseCreateResult and the dry-run helpers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import (
    Bureau,
    CaseCategory,
    CaseStatus,
    ClockState,
    ClockType,
    LinkStatus,
    MatchStatus,
    RelationType,
    SourceChannel,
)
from app.schemas.cases import CaseDetail
from app.schemas.clocks import ClockOut

PartyType = Literal["STUDENT", "PARENT", "FACULTY", "ANONYMOUS", "OTHER"]


class ComplainantIn(BaseModel):
    name: str | None = Field(None, max_length=200)
    email: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=40)
    party_type: PartyType = "OTHER"


class CaseCreate(BaseModel):
    source_channel: SourceChannel
    source_ref: str | None = Field(None, max_length=200)
    received_at: datetime | None = None
    institution_text_raw: str | None = Field(None, max_length=500)
    permanent_id_raw: str | None = Field(None, max_length=60)
    complainant: ComplainantIn = Field(default_factory=ComplainantIn)
    category: CaseCategory | None = None
    subject: str = Field(min_length=1, max_length=500)
    description: str | None = Field(None, max_length=20000)
    owner_bureau: Bureau | None = None
    owner_ro_code: str | None = Field(None, max_length=10)
    # Optional extension: the officer picked the institution by hand (skips stage A, status CONFIRMED).
    institution_id: uuid.UUID | None = None


class ResolutionSelected(BaseModel):
    institution_id: uuid.UUID
    name: str
    permanent_id: str
    score: float
    district: str | None = None
    state: str | None = None


class ResolutionCandidate(BaseModel):
    institution_id: uuid.UUID
    name: str
    permanent_id: str
    district: str | None = None
    state: str | None = None
    rank: int
    score: float
    matched_via: str | None = None
    reasons: list[str] = []
    features: dict[str, Any] = {}


class ResolutionOut(BaseModel):
    status: MatchStatus
    selected: ResolutionSelected | None = None
    candidates: list[ResolutionCandidate] = []
    normalised_query: str = ""
    extracted: dict[str, str | None] = {}


class CategorySuggestionOut(BaseModel):
    category: CaseCategory
    confidence: float
    keywords: list[str] = []


class OtherCaseBrief(BaseModel):
    id: uuid.UUID
    display_id: str
    owner_bureau: Bureau
    subject: str
    status: CaseStatus


class CreatedLink(BaseModel):
    link_id: uuid.UUID
    other_case: OtherCaseBrief
    relation: RelationType
    status: LinkStatus = LinkStatus.SUGGESTED
    score: float
    reasons: list[str] = []
    suggested_next_action: str | None = None
    lead_bureau: Bureau | None = None


class UnrelatedCheck(BaseModel):
    """Same-institution case that the engine judged UNRELATED (no link stored, no alert)."""

    other_case: OtherCaseBrief
    relation: Literal["UNRELATED"] = "UNRELATED"
    score: float
    reasons: list[str] = []


class ResultClock(ClockOut):
    """ClockOut already carries clock, due_at, state (+ label, rule); kept as its own name for the schema."""


class CaseCreateResult(BaseModel):
    case: CaseDetail
    resolution: ResolutionOut
    category_suggestion: CategorySuggestionOut
    links: list[CreatedLink] = []
    unrelated: list[UnrelatedCheck] = []
    clocks: list[ResultClock] = []


# ------------------------------------------------------------------ dry run / helpers
class ResolveRequest(BaseModel):
    institution_text_raw: str | None = Field(None, max_length=500)
    permanent_id_raw: str | None = Field(None, max_length=60)
    subject: str | None = Field(None, max_length=500)
    description: str | None = Field(None, max_length=20000)
    complainant_email: str | None = Field(None, max_length=200)


class ResolveResult(BaseModel):
    resolution: ResolutionOut
    category_suggestion: CategorySuggestionOut
    language: str
    normalised_text: str = ""


class ClassifyRequest(BaseModel):
    subject: str = Field("", max_length=500)
    description: str = Field("", max_length=20000)


class ClassifyResult(BaseModel):
    category: CaseCategory
    confidence: float
    keywords: list[str] = []


class ParseEmailRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=50000)


class DetectedFields(BaseModel):
    subject: str | None = None
    sender_name: str | None = None
    sender_email: str | None = None
    institution_mention: str | None = None
    permanent_id: str | None = None
    cpgrams_refs: list[str] = []
    css_refs: list[str] = []
    language: str = "en"


class ParseEmailResult(BaseModel):
    prefill: CaseCreate
    detected: DetectedFields
    category_suggestion: CategorySuggestionOut


__all__ = [
    "CaseCreate",
    "CaseCreateResult",
    "CategorySuggestionOut",
    "ClassifyRequest",
    "ClassifyResult",
    "ClockState",
    "ClockType",
    "ComplainantIn",
    "CreatedLink",
    "DetectedFields",
    "OtherCaseBrief",
    "ParseEmailRequest",
    "ParseEmailResult",
    "ResolutionCandidate",
    "ResolutionOut",
    "ResolutionSelected",
    "ResolveRequest",
    "ResolveResult",
    "ResultClock",
    "UnrelatedCheck",
]
