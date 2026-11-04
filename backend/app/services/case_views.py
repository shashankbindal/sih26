"""Read-side case serialisation and listing (clocks computed on read, privacy applied).

Public helpers:
    summarize_cases(session, cases, now=None) -> list[CaseSummary]
    build_case_detail(session, case, user, now=None, *, revealed=None) -> CaseDetail
    list_cases(session, user, *, filters..., page, page_size) -> (items, total)
    link_briefs_for_cases(session, case_ids) -> dict[case_id, list[LinkOut]]
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.cases import Case, CaseSourceRef, InstitutionMatchCandidate
from app.models.clocks import CaseClock
from app.models.enums import (
    OPEN_STATUSES,
    Bureau,
    CaseCategory,
    CaseStatus,
    ClockState,
    ClockType,
    LinkStatus,
    RelationType,
    Role,
    SourceChannel,
)
from app.models.institutions import Institution
from app.models.links import CaseLink
from app.models.users import User
from app.schemas.cases import (
    AlertCounts,
    CaseDetail,
    CaseRef,
    CaseSummary,
    ComplainantOut,
    InstitutionRef,
    InstitutionSnapshot,
    LinkOut,
    MatchCandidateOut,
    OwnerOut,
    SourceRefOut,
)
from app.schemas.clocks import ClockOut
from app.services import clocks as clocks_svc
from app.services import privacy

ACTIVE_LINK_STATUSES = (LinkStatus.SUGGESTED, LinkStatus.CONFIRMED, LinkStatus.DEFERRED)
PENDING_LINK_STATUSES = (LinkStatus.SUGGESTED, LinkStatus.DEFERRED)


def _now() -> datetime:
    return datetime.now(UTC)


def _clock_rows(session: Session, case_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[CaseClock]]:
    out: dict[uuid.UUID, list[CaseClock]] = defaultdict(list)
    if not case_ids:
        return out
    for c in session.scalars(select(CaseClock).where(CaseClock.case_id.in_(case_ids))):
        out[c.case_id].append(c)
    return out


def _link_rows(session: Session, case_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[CaseLink]]:
    out: dict[uuid.UUID, list[CaseLink]] = defaultdict(list)
    if not case_ids:
        return out
    q = select(CaseLink).where(
        or_(CaseLink.case_a_id.in_(case_ids), CaseLink.case_b_id.in_(case_ids)),
        CaseLink.relation != RelationType.UNRELATED,
        CaseLink.status.in_(ACTIVE_LINK_STATUSES),
    )
    wanted = set(case_ids)
    for link in session.scalars(q):
        if link.case_a_id in wanted:
            out[link.case_a_id].append(link)
        if link.case_b_id in wanted:
            out[link.case_b_id].append(link)
    return out


def _is_open(case: Case) -> bool:
    return case.status in OPEN_STATUSES


def _alerts(case: Case, statuses: list[Any], links: list[CaseLink]) -> AlertCounts:
    if not _is_open(case):
        return AlertCounts()
    amber = sum(1 for s in statuses if s.state == ClockState.AMBER)
    breached = sum(1 for s in statuses if s.state == ClockState.BREACHED)
    pending = sum(1 for lk in links if lk.status in PENDING_LINK_STATUSES)
    conflicting = sum(1 for lk in links if lk.relation == RelationType.CONFLICTING)
    return AlertCounts(
        clock_amber=amber,
        clock_breached=breached,
        pending_links=pending,
        conflicting=conflicting,
        total=amber + breached + len(links),
    )


_RELATION_ORDER = (RelationType.CONFLICTING, RelationType.DUPLICATE, RelationType.RELATED)


def _link_relations(case: Case, links: list[CaseLink]) -> list[RelationType]:
    if not _is_open(case):
        return []
    present = {lk.relation for lk in links}
    return [r for r in _RELATION_ORDER if r in present]


def _inst_ref(inst: Institution | None) -> InstitutionRef | None:
    if inst is None:
        return None
    return InstitutionRef(
        id=inst.id,
        permanent_id=inst.permanent_id,
        name=inst.name,
        district=inst.district,
        state=inst.state,
        ro_code=inst.ro_code,
    )


def _summary(
    case: Case,
    clock_rows: list[CaseClock],
    link_rows: list[CaseLink],
    policy: clocks_svc.ClockPolicy,
    now: datetime,
) -> CaseSummary:
    statuses = [clocks_svc.compute_state(c, now, policy) for c in clock_rows]
    statuses.sort(key=lambda s: s.due_at)
    overdue = any(s.state == ClockState.BREACHED for s in statuses) and _is_open(case)
    return CaseSummary(
        id=case.id,
        display_id=case.display_id,
        source_channel=case.source_channel,
        source_ref=case.source_ref,
        received_at=case.received_at,
        institution=_inst_ref(case.institution),
        institution_text_raw=case.institution_text_raw,
        institution_match_status=case.institution_match_status,
        category=case.category,
        subject=case.subject,
        owner_bureau=case.owner_bureau,
        owner_ro_code=case.owner_ro_code,
        owner_officer=(
            OwnerOut(
                id=case.owner_officer.id,
                name=case.owner_officer.name,
                designation=case.owner_officer.designation,
            )
            if case.owner_officer
            else None
        ),
        status=case.status,
        pending_step=case.pending_step,
        pending_since=case.pending_since,
        pending_action=case.pending_action,
        disposed_at=case.disposed_at,
        language=case.language,
        clocks=[ClockOut(**s.as_dict()) for s in statuses],
        alerts=_alerts(case, statuses, link_rows),
        link_relations=_link_relations(case, link_rows),
        overdue=overdue,
    )


def summarize_cases(
    session: Session, cases: Sequence[Case], now: datetime | None = None
) -> list[CaseSummary]:
    """Summaries (no complainant or description data, so no masking needed) with live clocks."""
    now = now or _now()
    ids = [c.id for c in cases]
    policy = clocks_svc.load_policy(session)
    clock_map = _clock_rows(session, ids)
    link_map = _link_rows(session, ids)
    return [_summary(c, clock_map.get(c.id, []), link_map.get(c.id, []), policy, now) for c in cases]


def link_briefs_for_cases(
    session: Session, case_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[LinkOut]]:
    """Active non-UNRELATED links per case, each oriented to show the *other* case."""
    link_map = _link_rows(session, case_ids)
    other_ids = {i for lks in link_map.values() for lk in lks for i in (lk.case_a_id, lk.case_b_id)}
    cases = {}
    if other_ids:
        cases = {c.id: c for c in session.scalars(select(Case).where(Case.id.in_(other_ids)))}
    out: dict[uuid.UUID, list[LinkOut]] = {}
    for cid, lks in link_map.items():
        items: list[LinkOut] = []
        for lk in lks:
            other = cases.get(lk.case_b_id if lk.case_a_id == cid else lk.case_a_id)
            if other is None:
                continue
            items.append(
                LinkOut(
                    id=lk.id,
                    relation=lk.relation,
                    status=lk.status,
                    score=float(lk.score),
                    version=lk.version,
                    reasons=list(lk.reasons or []),
                    other_case=CaseRef(
                        id=other.id,
                        display_id=other.display_id,
                        subject=other.subject,
                        owner_bureau=other.owner_bureau,
                        status=other.status,
                    ),
                )
            )
        out[cid] = items
    return out


def _suggested_actions(case: Case, statuses: list[Any], policy: clocks_svc.ClockPolicy) -> list[str]:
    actions: list[str] = []
    for s in statuses:
        if s.clock == ClockType.INST_REFUND_7D and s.state == ClockState.BREACHED:
            actions.append(
                f"Institution has exceeded the 7-day refund duty ({policy.rule(s.clock)}). "
                "Consider reminder / escalation to RB."
            )
    return actions


def build_case_detail(
    session: Session,
    case: Case,
    user: User,
    now: datetime | None = None,
    *,
    revealed: bool | None = None,
) -> CaseDetail:
    """Full privacy-masked CaseDetail. `revealed=None` looks up pii_reveal_log for the user."""
    now = now or _now()
    if revealed is None:
        revealed = privacy.has_revealed(session, case.id, user.id)
    masked = privacy.mask_case(case, user, revealed=revealed)
    policy = clocks_svc.load_policy(session)
    clock_rows = _clock_rows(session, [case.id]).get(case.id, [])
    base = _summary(case, clock_rows, _link_rows(session, [case.id]).get(case.id, []), policy, now)
    live_statuses = [clocks_svc.compute_state(c, now, policy) for c in clock_rows]
    inst = case.institution
    candidates = session.scalars(
        select(InstitutionMatchCandidate)
        .where(InstitutionMatchCandidate.case_id == case.id)
        .order_by(InstitutionMatchCandidate.rank)
    ).all()
    refs = session.scalars(select(CaseSourceRef).where(CaseSourceRef.case_id == case.id)).all()
    return CaseDetail(
        **base.model_dump(),
        description=masked.description,
        # same visibility as `description`: the normalised text is still the complaint body
        description_norm=case.description_norm if privacy.can_see_description(case, user, revealed) else None,
        permanent_id_raw=case.permanent_id_raw,
        institution_match_score=(
            float(case.institution_match_score) if case.institution_match_score is not None else None
        ),
        category_suggested=case.category_suggested,
        created_at=case.created_at,
        updated_at=case.updated_at,
        complainant=ComplainantOut(**masked.complainant),
        masked=masked.masked,
        masked_fields=masked.masked_fields,
        institution_snapshot=(
            InstitutionSnapshot(
                id=inst.id,
                permanent_id=inst.permanent_id,
                name=inst.name,
                district=inst.district,
                state=inst.state,
                ro_code=inst.ro_code,
                inst_type=inst.inst_type,
                address=inst.address,
                pincode=inst.pincode,
                approval_status=inst.approval_status,
            )
            if inst
            else None
        ),
        match_candidates=[
            MatchCandidateOut(
                rank=c.rank,
                institution_id=c.institution_id,
                name=c.institution.name,
                permanent_id=c.institution.permanent_id,
                score=float(c.score),
                reasons=list(c.reasons or []),
                status=c.status,
            )
            for c in candidates
        ],
        source_refs=[SourceRefOut(channel=r.channel, ref=r.ref) for r in refs],
        links=link_briefs_for_cases(session, [case.id]).get(case.id, []),
        suggested_actions=_suggested_actions(case, live_statuses, policy),
    )


def _apply_filters(
    stmt,
    user: User,
    *,
    q: str | None,
    status: Sequence[CaseStatus] | None,
    bureau: Sequence[Bureau] | None,
    ro_code: Sequence[str] | None,
    category: Sequence[CaseCategory] | None,
    channel: Sequence[SourceChannel] | None,
    institution_id: uuid.UUID | None,
    received_from: datetime | None,
    received_to: datetime | None,
    owner_me: bool,
):
    if q:
        q = q.strip()
        stmt = stmt.where(
            or_(
                Case.display_id.icontains(q, autoescape=True),
                Case.source_ref.icontains(q, autoescape=True),
                Case.subject.icontains(q, autoescape=True),
                Case.institution_text_raw.icontains(q, autoescape=True),
                Case.institution_id.in_(
                    select(Institution.id).where(Institution.name.icontains(q, autoescape=True))
                ),
                Case.id.in_(
                    select(CaseSourceRef.case_id).where(CaseSourceRef.ref.icontains(q, autoescape=True))
                ),
            )
        )
    if status:
        stmt = stmt.where(Case.status.in_(status))
    if bureau:
        stmt = stmt.where(Case.owner_bureau.in_(bureau))
    if ro_code:
        stmt = stmt.where(
            or_(
                Case.owner_ro_code.in_(ro_code),
                Case.institution_id.in_(select(Institution.id).where(Institution.ro_code.in_(ro_code))),
            )
        )
    if category:
        stmt = stmt.where(Case.category.in_(category))
    if channel:
        stmt = stmt.where(Case.source_channel.in_(channel))
    if institution_id:
        stmt = stmt.where(Case.institution_id == institution_id)
    if received_from:
        stmt = stmt.where(Case.received_at >= received_from)
    if received_to:
        stmt = stmt.where(Case.received_at <= received_to)
    if owner_me:
        stmt = stmt.where(Case.owner_officer_id == user.id)
    return stmt


def list_cases(
    session: Session,
    user: User,
    *,
    q: str | None = None,
    status: Sequence[CaseStatus] | None = None,
    bureau: Sequence[Bureau] | None = None,
    ro_code: Sequence[str] | None = None,
    category: Sequence[CaseCategory] | None = None,
    channel: Sequence[SourceChannel] | None = None,
    institution_id: uuid.UUID | None = None,
    overdue: bool | None = None,
    clock_state: Sequence[ClockState] | None = None,
    received_from: datetime | None = None,
    received_to: datetime | None = None,
    has_alert: bool | None = None,
    owner_me: bool = False,
    scope_all: bool = False,
    sort: str = "received_at_desc",
    page: int = 1,
    page_size: int = 25,
    now: datetime | None = None,
) -> tuple[list[CaseSummary], int]:
    """Filtered, paginated case list. Filters/sorts that depend on computed clock state
    (overdue, clock_state, has_alert, due_asc) run in Python over the SQL-filtered set."""
    now = now or _now()
    if user.role == Role.RO_OFFICER and user.ro_code and not scope_all:
        ro_code = [user.ro_code]  # RO officers default to their own region; scope=all widens it
    base = _apply_filters(
        select(Case),
        user,
        q=q,
        status=status,
        bureau=bureau,
        ro_code=ro_code,
        category=category,
        channel=channel,
        institution_id=institution_id,
        received_from=received_from,
        received_to=received_to,
        owner_me=owner_me,
    )
    computed = overdue is not None or bool(clock_state) or has_alert is not None or sort == "due_asc"
    if not computed:
        total = session.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
        rows = session.scalars(
            base.order_by(Case.received_at.desc(), Case.display_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).unique().all()
        return summarize_cases(session, rows, now), int(total)

    rows = session.scalars(base.order_by(Case.received_at.desc(), Case.display_id.desc())).unique().all()
    summaries = summarize_cases(session, rows, now)
    if overdue is not None:
        summaries = [s for s in summaries if s.overdue == overdue]
    if clock_state:
        wanted = set(clock_state)
        summaries = [s for s in summaries if any(c.state in wanted for c in s.clocks)]
    if has_alert is not None:
        summaries = [s for s in summaries if (s.alerts.total > 0) == has_alert]
    if sort == "due_asc":
        far = datetime.max.replace(tzinfo=UTC)

        def due_key(s: CaseSummary) -> datetime:
            live = [c.due_at for c in s.clocks if c.state != ClockState.MET]
            return min(live) if live else far

        summaries.sort(key=due_key)
    total = len(summaries)
    start = (page - 1) * page_size
    return summaries[start : start + page_size], total
