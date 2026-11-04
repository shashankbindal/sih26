"""In-memory records exchanged with the CaseLink engine (no database coupling)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any

from app.services.normalise import NormalisedName

Id = str | uuid.UUID

RELATIONS = ("UNRELATED", "DUPLICATE", "RELATED", "CONFLICTING")
OPEN_EXCLUDED_STATUSES = frozenset({"DISPOSED", "CLOSED_NO_ACTION"})


# --------------------------------------------------------------------------------------
# Stage A
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class InstitutionRecord:
    id: Id
    name: str
    permanent_id: str | None = None
    name_norm: str | None = None           # optional pre-computed; recomputed when None
    district: str | None = None
    state: str | None = None
    pincode: str | None = None
    email_domain: str | None = None
    inst_type: str | None = None
    ro_code: str | None = None


@dataclass(frozen=True)
class AliasRecord:
    institution_id: Id
    alias_norm: str                         # as stored in institution_aliases.alias_norm
    alias_raw: str = ""
    source: str = "SEED"                    # SEED | CONFIRMED_MATCH | ADMIN
    confirmed_by: str | None = None         # officer display name, for the reason string
    confirmed_at: datetime | None = None


@dataclass(frozen=True)
class QueryRecord:
    """What the intake form knows about the institution a complaint is about."""

    institution_text: str = ""
    permanent_id_raw: str | None = None
    text: str = ""                          # subject + description, mined for ID/pincode/district
    pincode: str | None = None              # structured override
    district: str | None = None             # structured override
    email_domain: str | None = None


@dataclass
class Candidate:
    institution_id: Id
    institution: InstitutionRecord
    score: float                            # probability 0..1 (3 decimals), 1.0 for EXACT
    rank: int = 0
    matched_via: str = "fuzzy"              # permanent_id | permanent_id_in_text | alias | fuzzy
    features: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


@dataclass
class Resolution:
    status: str                             # EXACT | AUTO_SUGGESTED | NEEDS_REVIEW | UNRESOLVED
    selected: Candidate | None
    candidates: list[Candidate]
    normalised_query: NormalisedName
    extracted: dict[str, str | None] = field(default_factory=dict)  # pincode/district/permanent_id

    @property
    def score(self) -> float:
        return self.selected.score if self.selected else 0.0

    @property
    def reasons(self) -> list[str]:
        return list(self.selected.reasons) if self.selected else []

    @property
    def selected_id(self) -> Id | None:
        return self.selected.institution_id if self.selected else None


# --------------------------------------------------------------------------------------
# Stage B
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseRecord:
    id: Id
    institution_id: Id | None
    owner_bureau: str                       # PGRC | RB | APPROVAL | VIGILANCE | RO
    category: str
    status: str
    received_at: datetime
    pending_step: str = "NONE"              # NONE | INSTITUTION_ATR | HEARING | SHOW_CAUSE_REPLY ...
    pending_action: str | None = None       # free text, e.g. "SHOW_CAUSE issued 29 Oct"
    party_hash: str | None = None
    source_refs: tuple[str, ...] = ()       # CPGRAMS / CSS refs
    subject: str = ""
    description: str = ""                   # PII-masked original text (searched for ref strings)
    description_norm: str = ""
    display_id: str | None = None
    source_channel: str | None = None
    hearing_at: datetime | None = None
    disposed_at: datetime | None = None
    pending_since: datetime | None = None
    # Extra pending-action kinds supplied by the caller, e.g. ("DEPOSIT_RELEASE",) for a
    # Pre-Action Check in progress (institution_actions) represented as a pseudo-case.
    extra_pending_kinds: tuple[str, ...] = ()
    institution_permanent_id: str | None = None   # only used in reason strings

    @property
    def label(self) -> str:
        return self.display_id or str(self.id)

    def _base_text(self) -> str:
        from app.services.normalise import normalise_text

        return f"{self.description_norm} {normalise_text(self.subject)}".strip()

    def topic_text(self) -> str:
        """Canonical keywords of the dominant category (see ``classify.topic_signature``)."""
        from app.services.classify import topic_signature

        return topic_signature(self._base_text())

    def similarity_text(self) -> str:
        """description_norm + normalised subject + topic signature."""
        base = self._base_text()
        return f"{base} {self.topic_text()}".strip()


@dataclass
class LinkSuggestion:
    case_id: Id                             # the new / updated case the detection ran for
    other_id: Id
    relation: str                           # DUPLICATE | CONFLICTING | RELATED | UNRELATED
    score: float                            # overlap, 0..1
    features: dict[str, Any]
    reasons: list[str]
    suggested_next_action: str | None = None
    lead_bureau: str | None = None


# --------------------------------------------------------------------------------------
# Thresholds (policy_config.thresholds -> Thresholds.from_policy)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    # stage A bands
    inst_auto: float = 0.92
    inst_review: float = 0.75
    near_twin_gap: float = 0.03
    id_name_floor: float = 0.5
    block_cap: int = 50
    block_top_names: int = 20
    block_fuzzy_cutoff: float = 55.0        # RapidFuzz WRatio cutoff for blocking
    max_candidates: int = 5
    prior_pool_cap: int = 32                # effective pool size for the prior, see institution.py
    distinctive_max_df: int = 3             # token counts as "distinctive" if in <= this many names
    # stage A name-similarity levels
    name_strong: float = 0.95
    name_medium: float = 0.88
    name_weak: float = 0.75
    # stage B
    dup: float = 0.85
    dup_strict: float = 0.90
    dup_days: float = 14.0
    conflict_overlap: float = 0.40
    conflict_category: float = 0.5
    related: float = 0.60
    related_category: float = 0.5
    ref_floor: float = 0.95
    topic_weight: float = 0.75
    w_semantic: float = 0.45
    w_category: float = 0.25
    w_time: float = 0.15
    w_party: float = 0.15
    time_full_days: float = 30.0
    time_zero_days: float = 180.0
    disposed_lookback_days: float = 90.0
    hearing_window_days: float = 7.0

    @classmethod
    def from_policy(cls, cfg: dict[str, Any] | None) -> Thresholds:
        """Build from ``policy_config.thresholds``; unknown keys are ignored."""
        if not cfg:
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in cfg.items() if k in known})
