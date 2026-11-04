"""Import every model so Base.metadata is complete (Alembic autogenerate relies on this)."""

from app.models.cases import (
    Case,
    CaseSourceRef,
    InstitutionMatchCandidate,
    display_id_seq,
)
from app.models.clocks import CaseClock
from app.models.complainants import Complainant
from app.models.enums import *  # noqa: F403
from app.models.institutions import Institution, InstitutionAlias
from app.models.links import CaseLink, CaseLinkHistory, CoordinationMessage, CoordinationThread
from app.models.passport import PassportEntry
from app.models.preaction import ClearanceRequest, InstitutionAction
from app.models.system import (
    AuditLog,
    ImportJob,
    Notification,
    PiiRevealLog,
    PolicyConfig,
)
from app.models.users import RegionalOffice, User

__all__ = [
    "AuditLog",
    "Case",
    "CaseClock",
    "CaseLink",
    "CaseLinkHistory",
    "CaseSourceRef",
    "ClearanceRequest",
    "Complainant",
    "CoordinationMessage",
    "CoordinationThread",
    "ImportJob",
    "Institution",
    "InstitutionAction",
    "InstitutionAlias",
    "InstitutionMatchCandidate",
    "Notification",
    "PassportEntry",
    "PiiRevealLog",
    "PolicyConfig",
    "RegionalOffice",
    "User",
    "display_id_seq",
]
