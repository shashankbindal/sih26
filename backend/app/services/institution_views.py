"""Read-side institution queries: list/detail/timeline/links, per-institution stats, search.

Definitions:
- open case: status not in DISPOSED / CLOSED_NO_ACTION
- overdue: open case with any BREACHED clock (computed on read)
- open_alerts: active (SUGGESTED / CONFIRMED / DEFERRED) non-UNRELATED links between two open
  cases of the institution
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.cases import Case, CaseSourceRef
from app.models.clocks import CaseClock
from app.models.enums import OPEN_STATUSES, ClockState, RelationType
from app.models.institutions import Institution, InstitutionAlias
from app.models.links import CaseLink
from app.models.passport import PassportEntry
from app.schemas.cases import CaseRef
from app.schemas.institutions import (
    AliasOut,
    InstitutionDetail,
    InstitutionLinkOut,
    InstitutionListItem,
    InstitutionSummaryOut,
    TimelineItem,
)
from app.schemas.search import SearchCase, SearchInstitution, SearchResult
from app.services import case_views
from app.services import clocks as clocks_svc


def normalise_query(q: str) -> str:
    """Latin-normalised search text. Uses app.services.normalise.normalise_name when the
    engine module exists (handles Devanagari), else plain lower-casing."""
    q = (q or "").strip()
    try:
        from app.services.normalise import normalise_name  # type: ignore[import-not-found]
    except ImportError:
        return " ".join(q.lower().split())
    try:
        res = normalise_name(q)
        text_ = getattr(res, "text", res)
        return str(text_).strip() or " ".join(q.lower().split())
    except Exception:  # noqa: BLE001 - search must never fail on exotic input
        return " ".join(q.lower().split())


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def institution_stats(
    session: Session, institution_ids: Sequence[uuid.UUID] | None = None, now: datetime | None = None
) -> dict[uuid.UUID, dict[str, Any]]:
    """{institution_id: {open_by_bureau: Counter, open_total, overdue, open_alerts}}."""
    now = now or datetime.now(UTC)
    stmt = select(Case.id, Case.institution_id, Case.owner_bureau).where(
        Case.institution_id.is_not(None), Case.status.in_(OPEN_STATUSES)
    )
    if institution_ids is not None:
        stmt = stmt.where(Case.institution_id.in_(institution_ids))
    rows = session.execute(stmt).all()
    stats: dict[uuid.UUID, dict[str, Any]] = defaultdict(
        lambda: {"open_by_bureau": Counter(), "open_total": 0, "overdue": 0, "open_alerts": 0}
    )
    if not rows:
        return stats
    case_inst = {r.id: r.institution_id for r in rows}
    policy = clocks_svc.load_policy(session)
    breached: set[uuid.UUID] = set()
    for c in session.scalars(select(CaseClock).where(CaseClock.case_id.in_(list(case_inst)))):
        if clocks_svc.compute_state(c, now, policy).state == ClockState.BREACHED:
            breached.add(c.case_id)
    for r in rows:
        st = stats[r.institution_id]
        st["open_by_bureau"][r.owner_bureau] += 1
        st["open_total"] += 1
        if r.id in breached:
            st["overdue"] += 1
    links = session.execute(
        select(CaseLink.case_a_id, CaseLink.case_b_id).where(
            CaseLink.case_a_id.in_(list(case_inst)),
            CaseLink.case_b_id.in_(list(case_inst)),
            CaseLink.relation != RelationType.UNRELATED,
            CaseLink.status.in_(case_views.ACTIVE_LINK_STATUSES),
        )
    ).all()
    for a, _b in links:
        stats[case_inst[a]]["open_alerts"] += 1
    return stats


def _empty_stats() -> dict[str, Any]:
    return {"open_by_bureau": Counter(), "open_total": 0, "overdue": 0, "open_alerts": 0}


def list_institutions(
    session: Session,
    *,
    q: str | None = None,
    ro_code: str | None = None,
    state: str | None = None,
    district: str | None = None,
    inst_type: str | None = None,
    approval_status: str | None = None,
    has_open_alerts: bool | None = None,
    sort: str | None = None,
    page: int = 1,
    page_size: int = 25,
    now: datetime | None = None,
) -> tuple[list[InstitutionListItem], int]:
    score_col = None
    stmt = select(Institution)
    if q and q.strip():
        raw = q.strip()
        nq = normalise_query(raw)
        alias_sim = (
            select(func.coalesce(func.max(func.similarity(InstitutionAlias.alias_norm, nq)), 0.0))
            .where(InstitutionAlias.institution_id == Institution.id)
            .scalar_subquery()
        )
        score_col = func.greatest(func.similarity(Institution.name_norm, nq), alias_sim).label("score")
        tokens = [t for t in nq.split() if t]
        token_match = (
            and_(*[Institution.name_norm.ilike(f"%{_like_escape(t)}%", escape="\\") for t in tokens])
            if tokens
            else None
        )
        conds = [
            score_col >= 0.25,
            Institution.permanent_id.ilike(f"{_like_escape(raw)}%", escape="\\"),
            Institution.name.ilike(f"%{_like_escape(raw)}%", escape="\\"),
        ]
        if token_match is not None:
            conds.append(token_match)
        stmt = select(Institution, score_col).where(or_(*conds))
    if ro_code:
        stmt = stmt.where(Institution.ro_code == ro_code)
    if state:
        stmt = stmt.where(Institution.state.ilike(state))
    if district:
        stmt = stmt.where(Institution.district.ilike(district))
    if inst_type:
        stmt = stmt.where(Institution.inst_type.ilike(inst_type))
    if approval_status:
        stmt = stmt.where(Institution.approval_status == approval_status)

    result = session.execute(stmt).unique().all() if score_col is not None else [
        (i, None) for i in session.scalars(stmt).unique().all()
    ]
    stats = institution_stats(session, now=now)
    items: list[InstitutionListItem] = []
    for inst, score in result:
        st = stats.get(inst.id) or _empty_stats()
        if has_open_alerts is not None and (st["open_alerts"] > 0) != has_open_alerts:
            continue
        items.append(
            InstitutionListItem(
                id=inst.id,
                permanent_id=inst.permanent_id,
                name=inst.name,
                district=inst.district,
                state=inst.state,
                ro_code=inst.ro_code,
                inst_type=inst.inst_type,
                approval_status=inst.approval_status,
                pincode=inst.pincode,
                open_cases=st["open_total"],
                overdue=st["overdue"],
                open_alerts=st["open_alerts"],
                score=round(float(score), 3) if score is not None else None,
            )
        )
    if sort == "open_cases_desc":
        items.sort(key=lambda i: (-i.open_cases, -i.overdue, i.name))
    elif score_col is not None:
        items.sort(key=lambda i: (-(i.score or 0.0), i.name))
    else:
        items.sort(key=lambda i: i.name)
    total = len(items)
    start = (page - 1) * page_size
    return items[start : start + page_size], total


def institution_detail(session: Session, inst: Institution, now: datetime | None = None) -> InstitutionDetail:
    st = institution_stats(session, [inst.id], now).get(inst.id) or _empty_stats()
    last = session.scalar(
        select(func.max(PassportEntry.created_at)).where(PassportEntry.institution_id == inst.id)
    )
    return InstitutionDetail(
        id=inst.id,
        permanent_id=inst.permanent_id,
        name=inst.name,
        district=inst.district,
        state=inst.state,
        ro_code=inst.ro_code,
        inst_type=inst.inst_type,
        address=inst.address,
        pincode=inst.pincode,
        email_domain=inst.email_domain,
        phone=inst.phone,
        approval_status=inst.approval_status,
        established_year=inst.established_year,
        aliases=[
            AliasOut(id=a.id, alias_raw=a.alias_raw, alias_norm=a.alias_norm, source=a.source)
            for a in sorted(inst.aliases, key=lambda a: a.alias_raw)
        ],
        summary=InstitutionSummaryOut(
            open_by_bureau=dict(st["open_by_bureau"]),
            open_total=st["open_total"],
            overdue=st["overdue"],
            open_alerts=st["open_alerts"],
            last_action_at=last,
        ),
    )


def institution_timeline(
    session: Session, inst: Institution, now: datetime | None = None
) -> list[TimelineItem]:
    cases = session.scalars(
        select(Case)
        .where(Case.institution_id == inst.id)
        .order_by(Case.received_at.desc(), Case.display_id.desc())
    ).unique().all()
    summaries = case_views.summarize_cases(session, cases, now)
    relations = case_views.link_briefs_for_cases(session, [c.id for c in cases])
    return [
        TimelineItem(**s.model_dump(), relations=relations.get(s.id, [])) for s in summaries
    ]


def institution_links(session: Session, inst: Institution) -> list[InstitutionLinkOut]:
    ids = list(session.scalars(select(Case.id).where(Case.institution_id == inst.id)))
    if not ids:
        return []
    links = session.scalars(
        select(CaseLink)
        .where(
            or_(CaseLink.case_a_id.in_(ids), CaseLink.case_b_id.in_(ids)),
            CaseLink.relation != RelationType.UNRELATED,
        )
        .order_by(CaseLink.created_at.desc())
    ).all()
    case_ids = {i for lk in links for i in (lk.case_a_id, lk.case_b_id)}
    cases = {c.id: c for c in session.scalars(select(Case).where(Case.id.in_(case_ids)))}

    def ref(cid: uuid.UUID) -> CaseRef:
        c = cases[cid]
        return CaseRef(
            id=c.id,
            display_id=c.display_id,
            subject=c.subject,
            owner_bureau=c.owner_bureau,
            status=c.status,
        )

    return [
        InstitutionLinkOut(
            id=lk.id,
            relation=lk.relation.value,
            status=lk.status.value,
            score=float(lk.score),
            version=lk.version,
            reasons=list(lk.reasons or []),
            features=dict(lk.features or {}),
            case_a=ref(lk.case_a_id),
            case_b=ref(lk.case_b_id),
            decided_at=lk.decided_at,
        )
        for lk in links
        if lk.case_a_id in cases and lk.case_b_id in cases
    ]


def search(session: Session, q: str, limit: int = 8) -> SearchResult:
    raw = (q or "").strip()
    if not raw:
        return SearchResult(institutions=[], cases=[])
    nq = normalise_query(raw)
    like_raw = f"%{_like_escape(raw)}%"

    alias_sim = (
        select(func.coalesce(func.max(func.similarity(InstitutionAlias.alias_norm, nq)), 0.0))
        .where(InstitutionAlias.institution_id == Institution.id)
        .scalar_subquery()
    )
    score = func.greatest(func.similarity(Institution.name_norm, nq), alias_sim)
    tokens = [t for t in nq.split() if t]
    conds = [
        Institution.permanent_id.ilike(f"{_like_escape(raw)}%", escape="\\"),
        score >= 0.25,
    ]
    if tokens:
        conds.append(and_(*[Institution.name_norm.ilike(f"%{_like_escape(t)}%", escape="\\") for t in tokens]))
    pid_exact = Institution.permanent_id == raw
    rows = session.execute(
        select(Institution, score.label("score"))
        .where(or_(*conds))
        .order_by(pid_exact.desc(), score.desc(), Institution.name)
        .limit(limit)
    ).all()
    institutions = [
        SearchInstitution(
            id=i.id,
            permanent_id=i.permanent_id,
            name=i.name,
            district=i.district,
            score=1.0 if i.permanent_id == raw else round(float(s or 0.0), 3),
        )
        for i, s in rows
    ]

    case_rows = session.scalars(
        select(Case)
        .where(
            or_(
                Case.display_id.ilike(like_raw, escape="\\"),
                Case.source_ref.ilike(like_raw, escape="\\"),
                Case.id.in_(
                    select(CaseSourceRef.case_id).where(CaseSourceRef.ref.ilike(like_raw, escape="\\"))
                ),
            )
        )
        .order_by(Case.received_at.desc())
        .limit(limit)
    ).unique().all()
    cases = [
        SearchCase(
            id=c.id,
            display_id=c.display_id,
            subject=c.subject,
            institution_name=c.institution.name if c.institution else None,
            status=c.status,
        )
        for c in case_rows
    ]
    return SearchResult(institutions=institutions, cases=cases)
