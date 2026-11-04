"""Complainant privacy: data scoping by owning bureau, region and role; complainant identity is masked for other bureaus.

Every case response must pass through `mask_case` (or build_case_detail, which calls it).

Rules
- ADMIN and the owning bureau (BUREAU_HEAD included) see everything.
- RO_OFFICER sees everything only for cases owned by their RO or in their region.
- SENIOR_MGMT sees all case fields except complainant identity, and can never reveal it.
- Everyone else sees masked complainant (name/email/phone -> null) and a masked description,
  unless they have a logged reveal for that case (pii_reveal_log) via `reveal_pii`.
Never log complainant fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.cases import Case
from app.models.complainants import Complainant
from app.models.enums import Bureau, Role
from app.models.system import PiiRevealLog
from app.models.users import User
from app.services import passport

COMPLAINANT_FIELDS = ("name", "email", "phone")


def is_owner(case: Case, user: User) -> bool:
    """True when the user's scope owns the case (full visibility without a reveal)."""
    if user.role == Role.ADMIN:
        return True
    if user.role == Role.RO_OFFICER:
        if not user.ro_code:
            return False
        inst_ro = case.institution.ro_code if case.institution is not None else None
        return user.ro_code in (case.owner_ro_code, inst_ro)
    return user.bureau == case.owner_bureau and case.owner_bureau != Bureau.ADMIN


def has_revealed(session: Session, case_id: Any, user_id: Any) -> bool:
    return (
        session.scalar(
            select(PiiRevealLog.id)
            .where(PiiRevealLog.case_id == case_id, PiiRevealLog.user_id == user_id)
            .limit(1)
        )
        is not None
    )


@dataclass
class MaskedCase:
    """Privacy-governed part of a case payload."""

    complainant: dict[str, Any]
    description: str | None
    masked: bool
    masked_fields: list[str] = field(default_factory=list)


def can_see_complainant(case: Case, user: User, revealed: bool = False) -> bool:
    if user.role == Role.SENIOR_MGMT:
        return False
    return is_owner(case, user) or revealed


def can_see_description(case: Case, user: User, revealed: bool = False) -> bool:
    if user.role == Role.SENIOR_MGMT:
        return True
    return is_owner(case, user) or revealed


def mask_complainant(complainant: Complainant | None, visible: bool) -> dict[str, Any]:
    """Complainant sub-object. party_type is not identity and is always shown."""
    if complainant is None:
        return {"name": None, "email": None, "phone": None, "party_type": None}
    out: dict[str, Any] = {"party_type": complainant.party_type}
    for f in COMPLAINANT_FIELDS:
        out[f] = getattr(complainant, f) if visible else None
    return out


def mask_case(case: Case, user: User, *, revealed: bool = False) -> MaskedCase:
    """Return the complainant object and description as `user` may see them."""
    show_c = can_see_complainant(case, user, revealed)
    show_d = can_see_description(case, user, revealed)
    masked_fields: list[str] = []
    if not show_c:
        masked_fields += [f"complainant.{f}" for f in COMPLAINANT_FIELDS]
    if not show_d:
        masked_fields.append("description")
    return MaskedCase(
        complainant=mask_complainant(case.complainant, show_c),
        description=case.description if show_d else None,
        masked=bool(masked_fields),
        masked_fields=masked_fields,
    )


def reveal_pii(session: Session, case: Case, user: User, reason: str) -> bool:
    """Reveal flow. Returns True if a reveal was logged, False if the user already owns the case.

    Raises 403 for SENIOR_MGMT. Writes pii_reveal_log + a PII_REVEALED Passport entry.
    The caller commits and then re-renders the case with revealed=True.
    """
    if user.role == Role.SENIOR_MGMT:
        raise ApiError(403, "PII_FORBIDDEN", "Senior management cannot view complainant identity")
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise ApiError(422, "REASON_TOO_SHORT", "A reason of at least 10 characters is required")
    if is_owner(case, user):
        return False
    session.add(PiiRevealLog(case_id=case.id, user_id=user.id, reason=reason))
    passport.append_entry(
        session,
        event="PII_REVEALED",
        case_id=case.id,
        institution_id=case.institution_id,
        actor=user,
        payload={"reason": reason, "revealed_fields": [f"complainant.{f}" for f in COMPLAINANT_FIELDS]},
    )
    session.flush()
    return True
