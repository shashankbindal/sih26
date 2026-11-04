"""Case write actions: PATCH, transfer, remarks, dispose.

Every change writes a hash-chained Passport entry; clocks are re-synced afterwards
(CPGRAMS pause/met, CSS first reply, institution 7-day ATR). Callers commit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.cases import Case
from app.models.enums import (
    CLOSED_STATUSES,
    Bureau,
    CaseStatus,
    PendingStep,
    Role,
)
from app.models.users import User
from app.schemas.workflows import CasePatch, CaseTransfer
from app.services import clocks as clocks_svc
from app.services import passport, privacy
from app.services.intake import pick_owner_officer

REFUND_STEPS = clocks_svc.REFUND_STEPS


def require_editor(case: Case, user: User) -> None:
    """Edit / transfer / dispose: owner-bureau officers, BUREAU_HEAD of the owner bureau, ADMIN
    (RO officers for their region). Everyone else, including SENIOR_MGMT, gets 403."""
    if user.role == Role.SENIOR_MGMT or not privacy.is_owner(case, user):
        raise ApiError(
            403,
            "FORBIDDEN",
            "Only the owning bureau's officers, its bureau head or an admin can change this case",
            {"owner_bureau": case.owner_bureau.value},
        )


def _fmt(v: Any) -> Any:
    return getattr(v, "value", v)


def _validate_officer(session: Session, officer_id: uuid.UUID, bureau: Bureau, ro_code: str | None) -> User:
    officer = session.get(User, officer_id)
    if officer is None or not officer.is_active:
        raise ApiError(422, "VALIDATION_ERROR", "Officer not found or inactive")
    if officer.bureau != bureau:
        raise ApiError(
            422, "VALIDATION_ERROR", f"Officer belongs to {officer.bureau.value}, not {bureau.value}"
        )
    if bureau == Bureau.RO and ro_code and officer.ro_code and officer.ro_code != ro_code:
        raise ApiError(422, "VALIDATION_ERROR", "Officer belongs to a different regional office")
    return officer


def patch_case(session: Session, case: Case, user: User, body: CasePatch, now: datetime | None = None) -> list[str]:
    """Apply the fields present in `body`. Returns the names of changed fields."""
    require_editor(case, user)
    now = now or datetime.now(UTC)
    fields = body.model_fields_set
    changes: dict[str, dict[str, Any]] = {}
    closed = case.status in CLOSED_STATUSES

    new_status = body.status if "status" in fields else None
    wants_other = body.atr_received or any(
        f in fields for f in ("pending_step", "pending_action", "category", "owner_officer_id")
    )
    if closed and not (new_status == CaseStatus.REOPENED and not wants_other):
        raise ApiError(409, "CASE_CLOSED", "A closed case can only be reopened (status REOPENED)")
    if new_status == CaseStatus.REOPENED and not closed:
        raise ApiError(422, "VALIDATION_ERROR", "Only a disposed or closed case can be reopened")

    old_step = case.pending_step
    event = "STATUS_CHANGED"
    if new_status is not None and new_status != case.status:
        changes["status"] = {"from": case.status.value, "to": new_status.value}
        if new_status in CLOSED_STATUSES:
            case.disposed_at = now
            event = "DISPOSED" if new_status == CaseStatus.DISPOSED else "STATUS_CHANGED"
        elif new_status == CaseStatus.REOPENED:
            case.disposed_at = None
            event = "REOPENED"
        elif new_status == CaseStatus.ESCALATED:
            event = "ESCALATED"
        case.status = new_status

    atr = False
    if body.atr_received and case.pending_step in REFUND_STEPS:
        atr = True
    new_step = body.pending_step if "pending_step" in fields and body.pending_step is not None else None
    if atr and new_step is None:
        new_step = PendingStep.NONE
    if new_step is not None and new_step != case.pending_step:
        changes["pending_step"] = {"from": case.pending_step.value, "to": new_step.value}
        case.pending_step = new_step
        case.pending_since = None if new_step == PendingStep.NONE else now
    if atr and case.status == CaseStatus.AWAITING_ATR and "status" not in changes:
        changes["status"] = {"from": case.status.value, "to": CaseStatus.UNDER_PROCESS.value}
        case.status = CaseStatus.UNDER_PROCESS
    atr = atr or (old_step == PendingStep.INSTITUTION_ATR and case.pending_step not in REFUND_STEPS)

    if "pending_action" in fields:
        new_action = (body.pending_action or "").strip() or None
        if new_action != case.pending_action:
            changes["pending_action"] = {"from": case.pending_action, "to": new_action}
            case.pending_action = new_action
    if "category" in fields and body.category is not None and body.category != case.category:
        changes["category"] = {"from": case.category.value, "to": body.category.value}
        case.category = body.category

    assigned: dict[str, Any] | None = None
    if "owner_officer_id" in fields and body.owner_officer_id != case.owner_officer_id:
        if body.owner_officer_id is None:
            raise ApiError(422, "VALIDATION_ERROR", "owner_officer_id cannot be cleared")
        new_owner = _validate_officer(session, body.owner_officer_id, case.owner_bureau, case.owner_ro_code)
        assigned = {
            "from": case.owner_officer.name if case.owner_officer else None,
            "to": new_owner.name,
            "to_bureau": case.owner_bureau.value,
        }
        case.owner_officer_id = new_owner.id
        session.flush()
        session.refresh(case, ["owner_officer"])

    remark = (body.remark or "").strip() or None
    if not changes and assigned is None and not atr and remark is None:
        return []
    session.flush()
    clocks_svc.sync_clocks_for_case(session, case, now)

    if changes:
        passport.append_entry(
            session, event=event, case_id=case.id, institution_id=case.institution_id, actor=user,
            payload={**changes, **({"remark": remark} if remark else {})},
        )
    elif remark and not atr and assigned is None:
        passport.append_entry(
            session, event="REMARK", case_id=case.id, institution_id=case.institution_id, actor=user,
            payload={"remark": remark},
        )
    if atr:
        passport.append_entry(
            session, event="ATR_RECEIVED", case_id=case.id, institution_id=case.institution_id, actor=user,
            payload={"pending_step_from": old_step.value, **({"remark": remark} if remark else {})},
        )
    if assigned is not None:
        passport.append_entry(
            session, event="ASSIGNED", case_id=case.id, institution_id=case.institution_id, actor=user,
            payload=assigned,
        )
    names = list(changes)
    if atr:
        names.append("atr_received")
    if assigned is not None:
        names.append("owner_officer")
    return names


def transfer_case(session: Session, case: Case, user: User, body: CaseTransfer, now: datetime | None = None) -> None:
    require_editor(case, user)
    now = now or datetime.now(UTC)
    if case.status in CLOSED_STATUSES:
        raise ApiError(409, "CASE_CLOSED", "A closed case cannot be transferred; reopen it first")
    if body.to_bureau == Bureau.ADMIN:
        raise ApiError(422, "VALIDATION_ERROR", "Cases can only be transferred to an operating bureau")
    same_bureau = body.to_bureau == case.owner_bureau
    if same_bureau and body.to_officer_id is None and not (body.to_bureau == Bureau.RO and body.to_ro_code):
        raise ApiError(422, "VALIDATION_ERROR", "Case is already owned by this bureau; pick a different officer")
    ro = (body.to_ro_code or "").strip() or None
    from_officer = case.owner_officer.name if case.owner_officer else None
    from_bureau = case.owner_bureau
    if body.to_officer_id is not None:
        new_owner: User | None = _validate_officer(session, body.to_officer_id, body.to_bureau, ro)
    else:
        new_owner = pick_owner_officer(session, body.to_bureau, ro, None)
    if body.to_bureau == Bureau.RO:
        ro = ro or (new_owner.ro_code if new_owner else None) or (
            case.institution.ro_code if case.institution is not None else None
        )
    else:
        ro = None
    case.owner_bureau = body.to_bureau
    case.owner_ro_code = ro
    case.owner_officer_id = new_owner.id if new_owner else None
    case.status = CaseStatus.TRANSFERRED
    session.flush()
    session.refresh(case, ["owner_officer"])
    clocks_svc.sync_clocks_for_case(session, case, now)
    passport.append_entry(
        session, event="TRANSFERRED", case_id=case.id, institution_id=case.institution_id, actor=user,
        payload={
            "from": from_bureau.value,
            "to": body.to_bureau.value,
            "from_officer": from_officer,
            "to_officer": new_owner.name if new_owner else None,
            "to_ro_code": ro,
            "remark": body.remark.strip(),
        },
    )


def atr_received(session: Session, case: Case, user: User, remark: str | None, now: datetime | None = None) -> None:
    """Institution's Action Taken Report is in: pending step cleared, INST_REFUND_7D marked MET,
    Passport ATR_RECEIVED."""
    require_editor(case, user)
    if case.status in CLOSED_STATUSES:
        raise ApiError(409, "CASE_CLOSED", "Case is already closed")
    now = now or datetime.now(UTC)
    old_step, old_status = case.pending_step, case.status
    if case.pending_step in REFUND_STEPS:
        case.pending_step = PendingStep.NONE
        case.pending_since = None
    if case.status == CaseStatus.AWAITING_ATR:
        case.status = CaseStatus.UNDER_PROCESS
    session.flush()
    clocks_svc.sync_clocks_for_case(session, case, now)
    passport.append_entry(
        session, event="ATR_RECEIVED", case_id=case.id, institution_id=case.institution_id, actor=user,
        payload={
            "pending_step_from": old_step.value,
            "status": {"from": old_status.value, "to": case.status.value},
            **({"remark": remark.strip()} if remark and remark.strip() else {}),
        },
    )


def add_remark(session: Session, case: Case, user: User, remark: str, attachment_name: str | None) -> None:
    require_editor(case, user)
    passport.append_entry(
        session, event="REMARK", case_id=case.id, institution_id=case.institution_id, actor=user,
        payload={"remark": remark.strip()}, attachment_name=attachment_name,
    )


def dispose_case(session: Session, case: Case, user: User, remark: str, now: datetime | None = None) -> None:
    """DISPOSED: sets disposed_at and marks the CPGRAMS clock MET (label 'met late' if after due)."""
    require_editor(case, user)
    if case.status in CLOSED_STATUSES:
        raise ApiError(409, "CASE_CLOSED", "Case is already closed")
    now = now or datetime.now(UTC)
    old = case.status
    case.status = CaseStatus.DISPOSED
    case.disposed_at = now
    session.flush()
    clocks_svc.sync_clocks_for_case(session, case, now)
    passport.append_entry(
        session, event="DISPOSED", case_id=case.id, institution_id=case.institution_id, actor=user,
        payload={"status": {"from": old.value, "to": CaseStatus.DISPOSED.value}, "remark": remark.strip()},
    )


__all__ = [
    "add_remark",
    "atr_received",
    "dispose_case",
    "patch_case",
    "require_editor",
    "transfer_case",
]
