"""Python enums mirroring the PostgreSQL enum types in the data model section 1."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy.dialects.postgresql import ENUM


class Bureau(StrEnum):
    PGRC = "PGRC"
    RB = "RB"
    APPROVAL = "APPROVAL"
    VIGILANCE = "VIGILANCE"
    RO = "RO"
    ADMIN = "ADMIN"


class Role(StrEnum):
    PGRC_OFFICER = "PGRC_OFFICER"
    RB_OFFICER = "RB_OFFICER"
    APPROVAL_OFFICER = "APPROVAL_OFFICER"
    VIGILANCE_OFFICER = "VIGILANCE_OFFICER"
    RO_OFFICER = "RO_OFFICER"
    BUREAU_HEAD = "BUREAU_HEAD"
    SENIOR_MGMT = "SENIOR_MGMT"
    ADMIN = "ADMIN"


class SourceChannel(StrEnum):
    CSS = "CSS"
    CPGRAMS = "CPGRAMS"
    EMAIL = "EMAIL"
    RO_REGISTER = "RO_REGISTER"
    BUREAU_FILE = "BUREAU_FILE"
    CSV_IMPORT = "CSV_IMPORT"


class CaseStatus(StrEnum):
    RECEIVED = "RECEIVED"
    UNDER_PROCESS = "UNDER_PROCESS"
    AWAITING_ATR = "AWAITING_ATR"
    AWAITING_COMPLAINANT = "AWAITING_COMPLAINANT"
    TRANSFERRED = "TRANSFERRED"
    ESCALATED = "ESCALATED"
    DISPOSED = "DISPOSED"
    CLOSED_NO_ACTION = "CLOSED_NO_ACTION"
    REOPENED = "REOPENED"


class CaseCategory(StrEnum):
    FEE_REFUND = "FEE_REFUND"
    CERTIFICATE_WITHHELD = "CERTIFICATE_WITHHELD"
    FACULTY_SHORTAGE = "FACULTY_SHORTAGE"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    RAGGING = "RAGGING"
    FAKE_APPROVAL_CLAIM = "FAKE_APPROVAL_CLAIM"
    SCHOLARSHIP = "SCHOLARSHIP"
    ADMISSION = "ADMISSION"
    SERVICE_MATTER = "SERVICE_MATTER"
    SCRUTINY_COMMITTEE = "SCRUTINY_COMMITTEE"
    OTHER = "OTHER"


class RelationType(StrEnum):
    UNRELATED = "UNRELATED"
    DUPLICATE = "DUPLICATE"
    RELATED = "RELATED"
    CONFLICTING = "CONFLICTING"


class LinkStatus(StrEnum):
    SUGGESTED = "SUGGESTED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    SUPERSEDED = "SUPERSEDED"


class MatchStatus(StrEnum):
    EXACT = "EXACT"
    AUTO_SUGGESTED = "AUTO_SUGGESTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNRESOLVED = "UNRESOLVED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class ClockType(StrEnum):
    CPGRAMS_21D = "CPGRAMS_21D"
    CSS_72H = "CSS_72H"
    INST_REFUND_7D = "INST_REFUND_7D"


class ClockState(StrEnum):
    ON_TRACK = "ON_TRACK"
    AMBER = "AMBER"
    BREACHED = "BREACHED"
    PAUSED = "PAUSED"
    MET = "MET"


class InstActionType(StrEnum):
    ISSUE_NOC = "ISSUE_NOC"
    SECURITY_DEPOSIT_RELEASE = "SECURITY_DEPOSIT_RELEASE"
    SHOW_CAUSE = "SHOW_CAUSE"
    CLOSURE_APPROVAL = "CLOSURE_APPROVAL"
    EXTENSION_OF_APPROVAL = "EXTENSION_OF_APPROVAL"
    INSPECTION_ORDER = "INSPECTION_ORDER"


class ClearanceResponse(StrEnum):
    PENDING = "PENDING"
    CLEARED = "CLEARED"
    NOT_CLEARED = "NOT_CLEARED"
    CLEARED_WITH_REMARKS = "CLEARED_WITH_REMARKS"


class PendingStep(StrEnum):
    NONE = "NONE"
    INSTITUTION_ATR = "INSTITUTION_ATR"
    COMPLAINANT_REPLY = "COMPLAINANT_REPLY"
    HEARING = "HEARING"
    INSPECTION = "INSPECTION"
    SHOW_CAUSE_REPLY = "SHOW_CAUSE_REPLY"
    CLEARANCE = "CLEARANCE"
    REFUND_FOLLOWUP = "REFUND_FOLLOWUP"


# name of PG type -> python enum
PG_ENUMS: dict[str, type[StrEnum]] = {
    "bureau": Bureau,
    "role": Role,
    "source_channel": SourceChannel,
    "case_status": CaseStatus,
    "case_category": CaseCategory,
    "relation_type": RelationType,
    "link_status": LinkStatus,
    "match_status": MatchStatus,
    "clock_type": ClockType,
    "clock_state": ClockState,
    "inst_action_type": InstActionType,
    "clearance_response": ClearanceResponse,
    "pending_step": PendingStep,
}


def pg_enum(py_enum: type[StrEnum], name: str) -> ENUM:
    """PG enum column type. Types are created explicitly in the Alembic migration."""
    return ENUM(py_enum, name=name, create_type=False, values_callable=lambda e: [m.value for m in e])


BureauT = pg_enum(Bureau, "bureau")
RoleT = pg_enum(Role, "role")
SourceChannelT = pg_enum(SourceChannel, "source_channel")
CaseStatusT = pg_enum(CaseStatus, "case_status")
CaseCategoryT = pg_enum(CaseCategory, "case_category")
RelationTypeT = pg_enum(RelationType, "relation_type")
LinkStatusT = pg_enum(LinkStatus, "link_status")
MatchStatusT = pg_enum(MatchStatus, "match_status")
ClockTypeT = pg_enum(ClockType, "clock_type")
ClockStateT = pg_enum(ClockState, "clock_state")
InstActionTypeT = pg_enum(InstActionType, "inst_action_type")
ClearanceResponseT = pg_enum(ClearanceResponse, "clearance_response")
PendingStepT = pg_enum(PendingStep, "pending_step")

OPEN_STATUSES = (
    CaseStatus.RECEIVED,
    CaseStatus.UNDER_PROCESS,
    CaseStatus.AWAITING_ATR,
    CaseStatus.AWAITING_COMPLAINANT,
    CaseStatus.TRANSFERRED,
    CaseStatus.ESCALATED,
    CaseStatus.REOPENED,
)
CLOSED_STATUSES = (CaseStatus.DISPOSED, CaseStatus.CLOSED_NO_ACTION)
