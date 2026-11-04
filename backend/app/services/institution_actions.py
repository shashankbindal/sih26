"""Institution-level actions (Pre-Action Check), acknowledgement, clearances and their Passport chains.

Chains are keyed by `action:<institution_action_id>` (passport service `chain_key`). The check is
advisory: acknowledging is required only to proceed, holding needs none, and open matters never
block anything. Services flush; routers commit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.enums import Bureau, ClearanceResponse, InstActionType, Role
from app.models.institutions import Institution
from app.models.passport import PassportEntry
from app.models.preaction import ClearanceRequest, InstitutionAction
from app.models.users import User
from app.schemas.passport import PassportEntryOut
from app.schemas.workflows import (
    ActionPassport,
    ActorBrief,
    ClearanceOut,
    InstitutionActionDetail,
    InstitutionActionOut,
    PanelInstitution,
    PreActionPanel,
)
from app.services import notifications, passport
from app.services.preaction import (
    ACTION_LABELS,
    PRE_ACTION_ROLES,
    STEP_LABELS,
    build_chain,
    build_panel,
    step_order_for,
)

OFFICER_ROLES = notifications.OFFICER_ROLES


def chain_key(action_id: uuid.UUID) -> str:
    return f"action:{action_id}"


# ---------------------------------------------------------------------- permissions
def require_pre_action_role(user: User) -> None:
    if user.role not in PRE_ACTION_ROLES:
        raise ApiError(
            403,
            "FORBIDDEN",
            "Only Approval and Regulation officers, bureau heads and admins can start a Pre-Action Check",
            {"required_roles": sorted(r.value for r in PRE_ACTION_ROLES)},
        )


def require_action_owner(action: InstitutionAction, user: User) -> None:
    """The initiating bureau (or an admin) acknowledges and requests clearances for the action."""
    require_pre_action_role(user)
    if user.role != Role.ADMIN and user.bureau != action.initiated_bureau:
        raise ApiError(403, "FORBIDDEN", "Only the bureau that started this check can act on it")


def can_respond(user: User, target: Bureau) -> bool:
    return user.bureau == target and (user.role in OFFICER_ROLES or user.role == Role.BUREAU_HEAD)


# ---------------------------------------------------------------------- loading helpers
def get_action(session: Session, action_id: uuid.UUID, *, lock: bool = False) -> InstitutionAction:
    q = select(InstitutionAction).where(InstitutionAction.id == action_id)
    if lock:
        q = q.with_for_update()
    action = session.scalar(q)
    if action is None:
        raise ApiError(404, "NOT_FOUND", "Institution action not found")
    return action


def users_by_id(session: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, User]:
    real = {i for i in ids if i}
    if not real:
        return {}
    return {u.id: u for u in session.scalars(select(User).where(User.id.in_(real)))}


def _actor(users: dict[uuid.UUID, User], uid: uuid.UUID | None) -> ActorBrief | None:
    u = users.get(uid) if uid else None
    return ActorBrief(id=u.id, name=u.name, bureau=u.bureau) if u else None


def entry_out(e: PassportEntry, names: dict[uuid.UUID, User]) -> PassportEntryOut:
    return PassportEntryOut(
        seq=e.seq,
        event=e.event,
        actor_id=e.actor_id,
        actor_name=names[e.actor_id].name if e.actor_id in names else "System",
        actor_bureau=e.actor_bureau,
        payload=e.payload,
        attachment_name=e.attachment_name,
        created_at=e.created_at,
        hash=e.hash,
        hash_short=e.hash[:8],
        prev_hash=e.prev_hash,
    )


def action_passport(session: Session, action_id: uuid.UUID) -> ActionPassport:
    entries = passport.list_entries(session, chain_key=chain_key(action_id))
    names = users_by_id(session, {e.actor_id for e in entries})
    return ActionPassport(institution_action_id=action_id, entries=[entry_out(e, names) for e in entries])


# ---------------------------------------------------------------------- Pre-Action Check
def start_check(
    session: Session, user: User, institution: Institution, action_type: InstActionType, now: datetime | None = None
) -> PreActionPanel:
    """Create the institution_actions row (CHECK_SHOWN + snapshot) and return the panel."""
    require_pre_action_role(user)
    now = now or datetime.now(UTC)
    action = InstitutionAction(
        institution_id=institution.id,
        action_type=action_type,
        initiated_by=user.id,
        initiated_bureau=user.bureau,
        status="CHECK_SHOWN",
        snapshot={},
        open_matter_count=0,
    )
    session.add(action)
    session.flush()
    panel = build_panel(session, action, institution, now)
    action.snapshot = panel.model_dump(mode="json")
    action.open_matter_count = panel.summary.total_open
    session.flush()
    passport.append_entry(
        session,
        event="PREACTION_CHECK_SHOWN",
        institution_id=institution.id,
        chain_key=chain_key(action.id),
        actor=user,
        payload={
            "action_type": action_type.value,
            "institution": institution.name,
            "open_matters": panel.summary.total_open,
            "by_bureau": panel.summary.by_bureau,
            "overdue": panel.summary.overdue,
            "conflicting": panel.summary.conflicting,
        },
    )
    return panel


def acknowledge(
    session: Session, user: User, action_id: uuid.UUID, *, remark: str | None, proceed: bool, acknowledged: bool,
    now: datetime | None = None,
) -> tuple[InstitutionAction, PassportEntry]:
    action = get_action(session, action_id, lock=True)
    require_action_owner(action, user)
    if action.status in ("PROCEEDED", "WITHDRAWN"):
        raise ApiError(409, "ALREADY_DECIDED", f"This check is already {action.status}")
    if proceed and not acknowledged:
        raise ApiError(
            422, "ACK_REQUIRED", "Tick the acknowledgement that you have seen the open matters to proceed"
        )
    now = now or datetime.now(UTC)
    n = action.open_matter_count
    plural = "matter" if n == 1 else "matters"
    summary = (
        f"Proceeded with {n} open {plural} acknowledged" if proceed else f"Placed on hold with {n} open {plural}"
    )
    action.status = "PROCEEDED" if proceed else "ON_HOLD"
    action.acknowledged_at = now
    action.ack_remark = (remark or "").strip() or None
    session.flush()
    entry = passport.append_entry(
        session,
        event="PREACTION_ACKNOWLEDGED",
        institution_id=action.institution_id,
        chain_key=chain_key(action.id),
        actor=user,
        payload={
            "summary": summary,
            "proceed": proceed,
            "open_matters": n,
            "acknowledged": acknowledged,
            "action_type": action.action_type.value,
            "remark": action.ack_remark,
        },
    )
    return action, entry


# ---------------------------------------------------------------------- views
def _institution_brief(inst: Institution) -> PanelInstitution:
    return PanelInstitution(id=inst.id, name=inst.name, permanent_id=inst.permanent_id)


def action_out(session: Session, action: InstitutionAction, users: dict[uuid.UUID, User] | None = None) -> InstitutionActionOut:
    inst = session.get(Institution, action.institution_id)
    users = users if users is not None else users_by_id(session, {action.initiated_by})
    who = _actor(users, action.initiated_by) or ActorBrief(id=action.initiated_by, name="Unknown")
    return InstitutionActionOut(
        id=action.id,
        institution=_institution_brief(inst),  # type: ignore[arg-type]
        action_type=action.action_type,
        status=action.status,
        initiated_by=who,
        initiated_bureau=action.initiated_bureau,
        open_matter_count=action.open_matter_count,
        created_at=action.created_at,
        acknowledged_at=action.acknowledged_at,
        ack_remark=action.ack_remark,
        clearance_chain=build_chain(session, action),
    )


def list_actions(
    session: Session, *, institution_id: uuid.UUID | None, bureau: Bureau | None, status: str | None,
    action_type: InstActionType | None, page: int, page_size: int,
) -> tuple[list[InstitutionActionOut], int]:
    q = select(InstitutionAction)
    if institution_id:
        q = q.where(InstitutionAction.institution_id == institution_id)
    if bureau:
        q = q.where(InstitutionAction.initiated_bureau == bureau)
    if status:
        q = q.where(InstitutionAction.status == status)
    if action_type:
        q = q.where(InstitutionAction.action_type == action_type)
    total = session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = session.scalars(
        q.order_by(InstitutionAction.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    users = users_by_id(session, {r.initiated_by for r in rows})
    return [action_out(session, r, users) for r in rows], int(total)


def _request_remarks(session: Session, action_ids: set[uuid.UUID]) -> dict[str, str | None]:
    """Remark typed when the clearance was requested (kept in the Passport payload)."""
    out: dict[str, str | None] = {}
    for aid in action_ids:
        for e in passport.list_entries(session, chain_key=chain_key(aid)):
            if e.event == "CLEARANCE_REQUESTED":
                out[str(e.payload.get("clearance_id"))] = e.payload.get("remark")
    return out


def clearance_out(
    session: Session, reqs: list[ClearanceRequest], actions: dict[uuid.UUID, InstitutionAction] | None = None
) -> list[ClearanceOut]:
    if not reqs:
        return []
    action_ids = {r.institution_action_id for r in reqs}
    if actions is None:
        actions = {a.id: a for a in session.scalars(select(InstitutionAction).where(InstitutionAction.id.in_(action_ids)))}
    insts = {
        i.id: i
        for i in session.scalars(select(Institution).where(Institution.id.in_({a.institution_id for a in actions.values()})))
    }
    users = users_by_id(session, {r.requested_by for r in reqs} | {r.responded_by for r in reqs})
    remarks = _request_remarks(session, action_ids)
    out: list[ClearanceOut] = []
    for r in reqs:
        a = actions[r.institution_action_id]
        summary = (a.snapshot or {}).get("summary", {}) if isinstance(a.snapshot, dict) else {}
        out.append(
            ClearanceOut(
                id=r.id,
                institution_action_id=a.id,
                institution=_institution_brief(insts[a.institution_id]),
                action_type=a.action_type,
                action_status=a.status,
                target_bureau=r.target_bureau,
                step_order=r.step_order,
                step_label=STEP_LABELS.get(r.target_bureau, r.target_bureau.value),
                requested_by=_actor(users, r.requested_by) or ActorBrief(id=r.requested_by, name="Unknown"),
                requested_at=r.requested_at,
                request_remark=remarks.get(str(r.id)),
                response=r.response,
                responded_by=_actor(users, r.responded_by),
                responded_at=r.responded_at,
                remarks=r.remarks,
                snapshot_summary=summary,
                open_matter_count=a.open_matter_count,
            )
        )
    return out


def action_detail(session: Session, action: InstitutionAction) -> InstitutionActionDetail:
    base = action_out(session, action)
    reqs = list(
        session.scalars(
            select(ClearanceRequest)
            .where(ClearanceRequest.institution_action_id == action.id)
            .order_by(ClearanceRequest.requested_at)
        )
    )
    return InstitutionActionDetail(
        **base.model_dump(),
        panel=action.snapshot if isinstance(action.snapshot, dict) else {},
        clearances=clearance_out(session, reqs, {action.id: action}),
        passport=action_passport(session, action.id).entries,
    )


# ---------------------------------------------------------------------- clearances
def request_clearance(
    session: Session, user: User, action_id: uuid.UUID, target: Bureau, remark: str | None
) -> ClearanceRequest:
    """Advisory chain: allowed regardless of earlier steps. One PENDING request per bureau."""
    action = get_action(session, action_id, lock=True)
    require_action_owner(action, user)
    if target == Bureau.ADMIN:
        raise ApiError(422, "VALIDATION_ERROR", "Clearance can only be requested from an operating bureau")
    pending = session.scalar(
        select(ClearanceRequest.id).where(
            ClearanceRequest.institution_action_id == action.id,
            ClearanceRequest.target_bureau == target,
            ClearanceRequest.response == ClearanceResponse.PENDING,
        )
    )
    if pending is not None:
        raise ApiError(409, "CLEARANCE_ALREADY_PENDING", f"A clearance request to {target.value} is already pending")
    req = ClearanceRequest(
        institution_action_id=action.id,
        institution_id=action.institution_id,
        target_bureau=target,
        step_order=step_order_for(session, action, target),
        requested_by=user.id,
        response=ClearanceResponse.PENDING,
    )
    session.add(req)
    session.flush()
    clean_remark = (remark or "").strip() or None
    inst = session.get(Institution, action.institution_id)
    passport.append_entry(
        session,
        event="CLEARANCE_REQUESTED",
        institution_id=action.institution_id,
        chain_key=chain_key(action.id),
        actor=user,
        payload={
            "clearance_id": str(req.id),
            "target_bureau": target.value,
            "step_order": req.step_order,
            "action_type": action.action_type.value,
            "remark": clean_remark,
        },
    )
    label = ACTION_LABELS[action.action_type]
    notifications.notify(
        session,
        kind="CLEARANCE_REQUEST",
        title=f"Clearance requested: {label} - {inst.name}",  # type: ignore[union-attr]
        body=(
            f"Requested by {user.name} ({user.bureau.value}); {action.open_matter_count} open "
            f"matter{'' if action.open_matter_count == 1 else 's'} on this institution."
            + (f" Remark: {clean_remark}" if clean_remark else "")
        ),
        bureau=target,
        link_path="/clearances",
        institution_id=action.institution_id,
    )
    return req


def respond_clearance(
    session: Session, user: User, clearance_id: uuid.UUID, response: str, remarks: str | None
) -> tuple[ClearanceRequest, InstitutionAction]:
    req = session.scalar(select(ClearanceRequest).where(ClearanceRequest.id == clearance_id).with_for_update())
    if req is None:
        raise ApiError(404, "NOT_FOUND", "Clearance request not found")
    if not can_respond(user, req.target_bureau):
        raise ApiError(
            403, "FORBIDDEN", "Only officers or the head of the target bureau can respond to a clearance request",
            {"target_bureau": req.target_bureau.value},
        )
    if req.response != ClearanceResponse.PENDING:
        raise ApiError(409, "ALREADY_RESPONDED", "This clearance request has already been answered")
    clean = (remarks or "").strip() or None
    if response in ("NOT_CLEARED", "CLEARED_WITH_REMARKS") and not clean:
        raise ApiError(422, "REMARKS_REQUIRED", "Remarks are required for this response")
    action = get_action(session, req.institution_action_id)
    req.response = ClearanceResponse(response)
    req.responded_by = user.id
    req.responded_at = datetime.now(UTC)
    req.remarks = clean
    session.flush()
    inst = session.get(Institution, action.institution_id)
    passport.append_entry(
        session,
        event="CLEARANCE_RESPONDED",
        institution_id=action.institution_id,
        chain_key=chain_key(action.id),
        actor=user,
        payload={
            "clearance_id": str(req.id),
            "target_bureau": req.target_bureau.value,
            "step_order": req.step_order,
            "response": response,
            "remarks": clean,
        },
    )
    notifications.notify(
        session,
        kind="CLEARANCE_RESPONSE",
        title=f"{STEP_LABELS.get(req.target_bureau, req.target_bureau.value)}: {response.replace('_', ' ').lower()}",
        body=f"{ACTION_LABELS[action.action_type]} - {inst.name}." + (f" Remarks: {clean}" if clean else ""),  # type: ignore[union-attr]
        user_id=req.requested_by,
        link_path="/clearances",
        institution_id=action.institution_id,
    )
    return req, action


def list_clearances(
    session: Session, user: User, *, inbox: str, statuses: list[ClearanceResponse] | None, page: int, page_size: int
) -> tuple[list[ClearanceOut], int]:
    q = select(ClearanceRequest)
    if inbox == "me":
        q = q.where(ClearanceRequest.target_bureau == user.bureau)
    elif inbox == "sent":
        q = q.where(
            ClearanceRequest.requested_by.in_(select(User.id).where(User.bureau == user.bureau))
        )
    if statuses:
        q = q.where(ClearanceRequest.response.in_(statuses))
    total = session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = session.scalars(
        q.order_by(ClearanceRequest.requested_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return clearance_out(session, list(rows)), int(total)


def get_clearance(session: Session, clearance_id: uuid.UUID) -> ClearanceOut:
    req = session.get(ClearanceRequest, clearance_id)
    if req is None:
        raise ApiError(404, "NOT_FOUND", "Clearance request not found")
    return clearance_out(session, [req])[0]


__all__ = [
    "acknowledge",
    "action_detail",
    "action_out",
    "action_passport",
    "can_respond",
    "chain_key",
    "get_action",
    "get_clearance",
    "list_actions",
    "list_clearances",
    "request_clearance",
    "respond_clearance",
    "start_check",
]
