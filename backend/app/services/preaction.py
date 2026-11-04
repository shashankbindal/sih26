"""Pre-Action Check panel (FR-16..FR-20, the API specification "Pre-Action Check").

Builds the list of open matters on an institution across bureaus, ranks them by relevance to the
action about to be taken, and renders the clearance chain. Advisory only: the panel never blocks
anything and the clause text comes from `policy_config.clause_labels`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.cases import Case
from app.models.enums import (
    OPEN_STATUSES,
    Bureau,
    CaseCategory,
    ClearanceResponse,
    ClockState,
    InstActionType,
    LinkStatus,
    PendingStep,
    RelationType,
    Role,
)
from app.models.institutions import Institution
from app.models.links import CaseLink
from app.models.preaction import ClearanceRequest, InstitutionAction
from app.schemas.workflows import (
    ChainStep,
    OpenMatter,
    PanelClock,
    PanelInstitution,
    PanelSummary,
    PreActionPanel,
)
from app.services import case_views
from app.services import clocks as clocks_svc

PRE_ACTION_ROLES = (Role.APPROVAL_OFFICER, Role.RB_OFFICER, Role.BUREAU_HEAD, Role.ADMIN)
ADVISORY = "Advisory only. The competent authority decides."

ACTION_LABELS: dict[InstActionType, str] = {
    InstActionType.ISSUE_NOC: "Issue NOC",
    InstActionType.SECURITY_DEPOSIT_RELEASE: "Security-deposit release",
    InstActionType.SHOW_CAUSE: "Show-cause",
    InstActionType.CLOSURE_APPROVAL: "Closure approval",
    InstActionType.EXTENSION_OF_APPROVAL: "Extension of approval",
    InstActionType.INSPECTION_ORDER: "Inspection order",
}

# SECURITY_DEPOSIT_RELEASE chain: PGRC -> Vigilance -> Approval Bureau NOC (APH procedure)
DEPOSIT_CHAIN: tuple[tuple[int, Bureau], ...] = (
    (1, Bureau.PGRC),
    (2, Bureau.VIGILANCE),
    (3, Bureau.APPROVAL),
)
STEP_LABELS: dict[Bureau, str] = {
    Bureau.PGRC: "PGRC clearance",
    Bureau.VIGILANCE: "Vigilance clearance",
    Bureau.APPROVAL: "Approval Bureau NOC",
    Bureau.RB: "Regulation Bureau clearance",
    Bureau.RO: "Regional Office clearance",
    Bureau.ADMIN: "Admin clearance",
}
CLEARED_STATES = (ClearanceResponse.CLEARED, ClearanceResponse.CLEARED_WITH_REMARKS)

STUDENT_DUES = frozenset({CaseCategory.FEE_REFUND, CaseCategory.CERTIFICATE_WITHHELD, CaseCategory.ADMISSION})
REGULATORY = frozenset(
    {
        CaseCategory.FACULTY_SHORTAGE,
        CaseCategory.SCRUTINY_COMMITTEE,
        CaseCategory.INFRASTRUCTURE,
        CaseCategory.FAKE_APPROVAL_CLAIM,
    }
)
REFUND_STEPS = (PendingStep.INSTITUTION_ATR, PendingStep.REFUND_FOLLOWUP)
LEVELS = ("LOW", "MEDIUM", "HIGH")


def rule_note(session: Session, action_type: InstActionType) -> str:
    """Clause text always comes from policy_config.clause_labels."""
    labels = clocks_svc.load_policy(session).clause_labels
    if action_type == InstActionType.SECURITY_DEPOSIT_RELEASE:
        return f"{labels.get('deposit', '')}: PGRC and Vigilance clearance, then Approval Bureau NOC.".lstrip(": ")
    if action_type == InstActionType.CLOSURE_APPROVAL:
        return (
            f"{labels.get('refund', '')}: institution's refund and certificate-return duty. "
            "Check unresolved student dues before closure."
        ).lstrip(": ")
    if action_type == InstActionType.SHOW_CAUSE:
        return "Check that no other bureau is already acting on this institution, and agree one communication."
    if action_type in (InstActionType.ISSUE_NOC, InstActionType.EXTENSION_OF_APPROVAL):
        return "Review open compliance and student-dues matters across bureaus before approving."
    return "Check for inspections already scheduled by another bureau or regional office."


# ---------------------------------------------------------------------- chain
def _state_of(req: ClearanceRequest | None) -> str:
    if req is None:
        return "NOT_REQUESTED"
    return req.response.value


def build_chain(session: Session, action: InstitutionAction) -> list[ChainStep]:
    reqs = list(
        session.scalars(
            select(ClearanceRequest)
            .where(ClearanceRequest.institution_action_id == action.id)
            .order_by(ClearanceRequest.requested_at, ClearanceRequest.step_order)
        )
    )
    latest: dict[Bureau, ClearanceRequest] = {}
    for r in reqs:
        latest[r.target_bureau] = r

    def step(order: int, bureau: Bureau, state: str, req: ClearanceRequest | None) -> ChainStep:
        return ChainStep(
            step_order=order,
            bureau=bureau,
            state=state,  # type: ignore[arg-type]
            label=STEP_LABELS.get(bureau),
            clearance_id=req.id if req else None,
            responded_at=req.responded_at if req else None,
            remarks=req.remarks if req else None,
        )

    steps: list[ChainStep] = []
    if action.action_type == InstActionType.SECURITY_DEPOSIT_RELEASE:
        for order, bureau in DEPOSIT_CHAIN:
            req = latest.get(bureau)
            state = _state_of(req)
            if req is None and order == 3:
                prior_ok = all(
                    latest.get(b) is not None and latest[b].response in CLEARED_STATES
                    for o, b in DEPOSIT_CHAIN
                    if o < 3
                )
                state = "NOT_REQUESTED" if prior_ok else "PENDING_PREVIOUS"
            steps.append(step(order, bureau, state, req))
        for r in reqs:  # ad-hoc requests to bureaus outside the fixed chain (kept visible)
            if r.target_bureau not in {b for _, b in DEPOSIT_CHAIN} and latest[r.target_bureau] is r:
                steps.append(step(r.step_order, r.target_bureau, _state_of(r), r))
    else:
        for bureau, r in sorted(latest.items(), key=lambda kv: kv[1].step_order):
            steps.append(step(r.step_order, bureau, _state_of(r), r))
    return steps


def step_order_for(session: Session, action: InstitutionAction, target: Bureau) -> int:
    if action.action_type == InstActionType.SECURITY_DEPOSIT_RELEASE:
        for order, bureau in DEPOSIT_CHAIN:
            if bureau == target:
                return order
    existing = session.scalars(
        select(ClearanceRequest.step_order).where(ClearanceRequest.institution_action_id == action.id)
    ).all()
    floor = 3 if action.action_type == InstActionType.SECURITY_DEPOSIT_RELEASE else 0
    return max([floor, *existing]) + 1


# ---------------------------------------------------------------------- open matters
def _conflicting_links(session: Session, case_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[CaseLink]]:
    out: dict[uuid.UUID, list[CaseLink]] = {i: [] for i in case_ids}
    if not case_ids:
        return out
    q = select(CaseLink).where(
        or_(CaseLink.case_a_id.in_(case_ids), CaseLink.case_b_id.in_(case_ids)),
        CaseLink.relation == RelationType.CONFLICTING,
        CaseLink.status.in_((LinkStatus.SUGGESTED, LinkStatus.CONFIRMED, LinkStatus.DEFERRED)),
    )
    for link in session.scalars(q):
        for cid in (link.case_a_id, link.case_b_id):
            if cid in out:
                out[cid].append(link)
    return out


def _base_level(action: InstActionType, case: Case) -> tuple[int, str | None]:
    """(0 LOW / 1 MEDIUM / 2 HIGH, why) before conflicting / overdue adjustments."""
    dues = case.category in STUDENT_DUES
    if action == InstActionType.SECURITY_DEPOSIT_RELEASE and dues:
        return 2, "Student dues unresolved - relevant to deposit release"
    if action == InstActionType.CLOSURE_APPROVAL and dues:
        return 2, "Student dues unresolved - relevant before closure"
    if action == InstActionType.SHOW_CAUSE and case.pending_step in REFUND_STEPS:
        return 2, "A conciliatory refund process is in progress - a show-cause now would cross it"
    if action == InstActionType.INSPECTION_ORDER and (
        case.pending_step == PendingStep.INSPECTION or "inspection" in (case.pending_action or "").lower()
    ):
        return 2, "An inspection is already scheduled on this institution"
    if action in (InstActionType.ISSUE_NOC, InstActionType.EXTENSION_OF_APPROVAL) and case.category in REGULATORY:
        return 2, "Open compliance matter - relevant before approval"
    if case.category in REGULATORY or dues:
        return 1, "Open matter in another bureau on the same institution"
    return 0, "Open matter on the same institution"


def build_open_matters(
    session: Session, institution: Institution, action_type: InstActionType, initiating_bureau: Bureau,
    now: datetime | None = None,
) -> list[OpenMatter]:
    now = now or datetime.now(UTC)
    policy = clocks_svc.load_policy(session)
    cases = list(
        session.scalars(
            select(Case)
            .where(Case.institution_id == institution.id, Case.status.in_(OPEN_STATUSES))
            .order_by(Case.received_at)
        ).unique()
    )
    conflicts = _conflicting_links(session, [c.id for c in cases])
    summaries = {s.id: s for s in case_views.summarize_cases(session, cases, now)}
    matters: list[tuple[tuple[Any, ...], OpenMatter]] = []
    names = {c.id: c.display_id for c in cases}
    for c in cases:
        summary = summaries[c.id]
        clocks = [PanelClock(clock=ck.clock.value, state=ck.state.value, label=ck.label) for ck in summary.clocks]
        breached = [ck for ck in summary.clocks if ck.state == ClockState.BREACHED]
        level, why = _base_level(action_type, c)
        links = conflicts.get(c.id, [])
        conflicting = bool(links)
        if conflicting:
            level = 2
            other_ids = {i for lk in links for i in (lk.case_a_id, lk.case_b_id) if i != c.id}
            others = ", ".join(sorted(names.get(i, "another case") for i in other_ids))
            why = f"Priority review: conflicting action with {others}"
        if breached:
            level = min(2, level + 1)
            bits = [
                f"{policy.long_label(ck.clock)} {ck.label.split(' · ', 1)[1]}"
                for ck in breached
                if " · " in ck.label
            ]
            if bits:
                why = f"{why}; {'; '.join(bits)}"
        since = c.pending_since or c.received_at
        pending_days = max(0, int((now - since).total_seconds() // 86400))
        om = OpenMatter(
            case_id=c.id,
            display_id=c.display_id,
            owner_bureau=c.owner_bureau,
            owner_officer=c.owner_officer.name if c.owner_officer else None,
            category=c.category,
            status=c.status,
            pending_step=c.pending_step,
            pending_days=pending_days,
            clocks=clocks,
            relevance=LEVELS[level],  # type: ignore[arg-type]
            why=why or "Open matter",
            conflicting=conflicting,
            link_ids=[lk.id for lk in links],
        )
        key = (-level, not conflicting, not breached, -pending_days, c.display_id)
        matters.append((key, om))
    matters.sort(key=lambda t: t[0])
    return [m for _, m in matters]


def summarise(matters: list[OpenMatter]) -> PanelSummary:
    by_bureau: dict[str, int] = {}
    for m in matters:
        by_bureau[m.owner_bureau.value] = by_bureau.get(m.owner_bureau.value, 0) + 1
    conflict_links = {lid for m in matters for lid in m.link_ids}
    return PanelSummary(
        total_open=len(matters),
        by_bureau=by_bureau,
        overdue=sum(1 for m in matters if any(c.state == ClockState.BREACHED.value for c in m.clocks)),
        conflicting=len(conflict_links),
    )


def build_panel(
    session: Session, action: InstitutionAction, institution: Institution, now: datetime | None = None
) -> PreActionPanel:
    matters = build_open_matters(session, institution, action.action_type, action.initiated_bureau, now)
    return PreActionPanel(
        institution_action_id=action.id,
        action_type=action.action_type,
        institution=PanelInstitution(id=institution.id, name=institution.name, permanent_id=institution.permanent_id),
        rule_note=rule_note(session, action.action_type),
        open_matters=matters,
        summary=summarise(matters),
        clearance_chain=build_chain(session, action),
        advisory=ADVISORY,
    )
