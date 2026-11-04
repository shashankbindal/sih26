"""Case links: persistence of engine suggestions, officer decisions, history, threads and the sweep.

Advisory only. Nothing here merges cases or blocks an action; officers decide (FR-13) and every
change writes a Passport entry on both cases (hash-chained) so it is reversible and auditable.

Public:
    persist_suggestion(session, new_case, other_case, suggestion, *, version=1) -> CaseLink
    detect_and_persist(session, case, user, now=None) -> DetectionOutcome
    decide_link(session, link_id, user, decision, reason) -> CaseLink
    revert_link(session, link_id, user, reason) -> CaseLink
    list_links(session, user, ...) -> (items, total)
    link_detail(session, link_id, user) -> LinkDetail
    post_message / patch_thread
    run_sweep(session, user) -> {pairs_checked, new_links, superseded}
    refit_similarity(session) -> int            (re-exported; the importer calls it after imports)
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.errors import ApiError
from app.models.cases import Case
from app.models.enums import (
    OPEN_STATUSES,
    Bureau,
    LinkStatus,
    RelationType,
    Role,
    SourceChannel,
)
from app.models.institutions import Institution
from app.models.links import CaseLink, CaseLinkHistory, CoordinationMessage, CoordinationThread
from app.models.system import AuditLog
from app.models.users import User
from app.schemas.cases import InstitutionRef
from app.schemas.workflows import (
    FeatureRow,
    LinkCaseBrief,
    LinkDetail,
    LinkListItem,
    LinkVersionOut,
    ThreadMessageOut,
    ThreadOut,
)
from app.services import case_views, notifications, passport
from app.services import clocks as clocks_svc
from app.services.caselink import ExistingLink, LinkSuggestion, detect_relationships, sweep_relationships
from app.services.caselink_runtime import (
    get_similarity,
    load_case_records,
    load_thresholds,
    pool_cases,
    refit_similarity,  # noqa: F401 - re-exported: the importer calls links.refit_similarity
)

FEATURE_LABELS: dict[str, str] = {
    "s_semantic": "Text similarity",
    "s_category": "Category match",
    "s_time": "Time proximity",
    "s_party": "Same complainant",
    "s_ref": "Shared reference",
    "action_conflict": "Conflicting pending actions",
    "overlap": "Overall overlap",
    "days_apart": "Days apart",
    "diff_bureau": "Different bureaus",
}
_META_KEYS = ("suggested_next_action", "lead_bureau")
ACTIVE_STATUSES = (LinkStatus.SUGGESTED, LinkStatus.CONFIRMED, LinkStatus.DEFERRED)

EVENT_BY_DECISION = {"CONFIRM": "LINK_CONFIRMED", "REJECT": "LINK_REJECTED", "DEFER": "LINK_DEFERRED"}
STATUS_BY_DECISION = {
    "CONFIRM": LinkStatus.CONFIRMED,
    "REJECT": LinkStatus.REJECTED,
    "DEFER": LinkStatus.DEFERRED,
}
OFFICER_ROLES = notifications.OFFICER_ROLES


# ====================================================================== helpers
def _now() -> datetime:
    return datetime.now(UTC)


def ordered_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (a, b) if a < b else (b, a)


def next_version(session: Session, a: uuid.UUID, b: uuid.UUID) -> int:
    lo, hi = ordered_pair(a, b)
    current = session.scalar(
        select(func.max(CaseLink.version)).where(CaseLink.case_a_id == lo, CaseLink.case_b_id == hi)
    )
    return int(current or 0) + 1


def existing_active_link(session: Session, a: uuid.UUID, b: uuid.UUID) -> CaseLink | None:
    lo, hi = ordered_pair(a, b)
    return session.scalar(
        select(CaseLink)
        .where(
            CaseLink.case_a_id == lo,
            CaseLink.case_b_id == hi,
            CaseLink.status != LinkStatus.SUPERSEDED,
        )
        .order_by(CaseLink.version.desc())
        .limit(1)
    )


def _lead(link: CaseLink) -> Bureau | None:
    val = (link.features or {}).get("lead_bureau")
    try:
        return Bureau(val) if val else None
    except ValueError:
        return None


def _next_action(link: CaseLink) -> str | None:
    return (link.features or {}).get("suggested_next_action")


def _inst_ref(inst: Institution | None) -> InstitutionRef | None:
    if inst is None:
        return None
    return InstitutionRef(
        id=inst.id, permanent_id=inst.permanent_id, name=inst.name, district=inst.district,
        state=inst.state, ro_code=inst.ro_code,
    )


def can_decide(user: User, case_a: Case, case_b: Case) -> bool:
    """Decide link: owner officer of either case, bureau heads of either owner bureau, ADMIN."""
    if user.role == Role.ADMIN:
        return True
    if user.role == Role.SENIOR_MGMT:
        return False
    cases = (case_a, case_b)
    if user.role == Role.BUREAU_HEAD:
        return user.bureau in {c.owner_bureau for c in cases}
    if user.id in {c.owner_officer_id for c in cases if c.owner_officer_id}:
        return True
    return user.role in OFFICER_ROLES and any(
        c.owner_officer_id is None and c.owner_bureau == user.bureau for c in cases
    )


def can_participate(user: User, case_a: Case, case_b: Case) -> bool:
    """Thread access: users of either owner bureau (not senior management), and ADMIN."""
    if user.role == Role.ADMIN:
        return True
    if user.role == Role.SENIOR_MGMT:
        return False
    return user.bureau in {case_a.owner_bureau, case_b.owner_bureau}


def _link_cases(session: Session, link: CaseLink) -> tuple[Case, Case]:
    a = session.get(Case, link.case_a_id)
    b = session.get(Case, link.case_b_id)
    if a is None or b is None:
        raise ApiError(404, "NOT_FOUND", "Linked case not found")
    return a, b


def _get_link(session: Session, link_id: uuid.UUID, *, lock: bool = False) -> CaseLink:
    q = select(CaseLink).where(CaseLink.id == link_id)
    if lock:
        q = q.with_for_update()
    link = session.scalar(q)
    if link is None:
        raise ApiError(404, "NOT_FOUND", "Link not found")
    return link


def _archive(session: Session, link: CaseLink) -> None:
    session.add(
        CaseLinkHistory(
            link_id=link.id,
            version=link.version,
            relation=link.relation,
            score=link.score,
            features=link.features or {},
            reasons=list(link.reasons or []),
            status=link.status,
            decided_by=link.decided_by,
            decided_at=link.decided_at,
            decision_reason=link.decision_reason,
        )
    )
    session.flush()


def _passport_both(
    session: Session, event: str, link: CaseLink, a: Case, b: Case, *, actor: User | None,
    extra: dict[str, Any] | None = None,
) -> None:
    for me, other in ((a, b), (b, a)):
        passport.append_entry(
            session,
            event=event,
            case_id=me.id,
            institution_id=me.institution_id,
            actor=actor,
            payload={
                "link_id": str(link.id),
                "other_case": other.display_id,
                "other_bureau": other.owner_bureau.value,
                "relation": link.relation.value,
                "status": link.status.value,
                "score": float(link.score),
                "version": link.version,
                **(extra or {}),
            },
        )


# ====================================================================== notifications for links
_TITLES = {
    RelationType.DUPLICATE: ("REVIEW_SUGGESTED", "Review suggested: possible duplicate"),
    RelationType.RELATED: ("COORDINATION_REQUIRED", "Coordination required"),
    RelationType.CONFLICTING: ("PRIORITY_REVIEW", "Priority review: conflicting actions"),
}


def notify_for_link(
    session: Session, link: CaseLink, a: Case, b: Case, *, exclude: Sequence[uuid.UUID] = (), prefix: str = ""
) -> int:
    """FR-14. DUPLICATE -> owners (review suggested); RELATED -> both owner officers; CONFLICTING ->
    both owners and both bureau heads. UNRELATED -> nothing. Returns notifications created."""
    spec = _TITLES.get(link.relation)
    if spec is None:
        return 0
    kind, title = spec
    title = f"{prefix}{title}: {a.display_id} and {b.display_id}"
    reasons = list(link.reasons or [])[:2]
    body = " ".join(r.rstrip(".") + "." for r in reasons)
    action = _next_action(link)
    if action:
        body = f"{body} Suggested: {action}"
    path = f"/coordination/{link.id}"
    seen: set[uuid.UUID | str] = set()
    n = 0
    for c in (a, b):
        if notifications.notify_owner(
            session, c, kind=kind, title=title, body=body, link_path=path,
            exclude_user_ids=exclude, seen=seen,
        ):
            n += 1
    if link.relation == RelationType.CONFLICTING:
        for c in (a, b):
            n += len(
                notifications.notify_heads(
                    session, c, kind=kind, title=title, body=body, link_path=path, seen=seen
                )
            )
    return n


# ====================================================================== persistence of suggestions
def persist_suggestion(
    session: Session,
    new_case: Case,
    other_case: Case,
    suggestion: LinkSuggestion,
    *,
    version: int | None = None,
    notify: bool = True,
    extra_payload: dict[str, Any] | None = None,
) -> CaseLink:
    """Insert a SUGGESTED link (+ coordination thread, Passport on both cases, notifications)."""
    lo, hi = ordered_pair(new_case.id, other_case.id)
    features = dict(suggestion.features)
    features["suggested_next_action"] = suggestion.suggested_next_action
    features["lead_bureau"] = suggestion.lead_bureau
    link = CaseLink(
        case_a_id=lo,
        case_b_id=hi,
        relation=RelationType(suggestion.relation),
        score=round(float(suggestion.score), 3),
        features=features,
        reasons=list(suggestion.reasons),
        status=LinkStatus.SUGGESTED,
        version=version or next_version(session, new_case.id, other_case.id),
    )
    session.add(link)
    session.flush()
    lead = None
    if suggestion.lead_bureau:
        try:
            lead = Bureau(suggestion.lead_bureau)
        except ValueError:
            lead = None
    session.add(
        CoordinationThread(link_id=link.id, lead_bureau=lead, shared_next_action=suggestion.suggested_next_action)
    )
    session.flush()
    a, b = (new_case, other_case) if new_case.id == lo else (other_case, new_case)
    _passport_both(session, "LINK_SUGGESTED", link, a, b, actor=None, extra=extra_payload)
    if notify:
        notify_for_link(session, link, a, b)
    return link


@dataclass
class DetectionOutcome:
    links: list[tuple[CaseLink, Case, LinkSuggestion]] = field(default_factory=list)
    unrelated: list[tuple[Case, LinkSuggestion]] = field(default_factory=list)
    pool_size: int = 0


def detect_and_persist(
    session: Session, case: Case, user: User | None, now: datetime | None = None
) -> DetectionOutcome:
    """Stage B for `case` against the other open (or recently disposed) cases of its institution."""
    out = DetectionOutcome()
    if case.institution_id is None:
        return out
    now = now or _now()
    th = load_thresholds(session)
    pool = pool_cases(session, case.institution_id, exclude=case.id, now=now, lookback_days=th.disposed_lookback_days)
    out.pool_size = len(pool)
    if not pool:
        return out
    sim = get_similarity(session)
    records = load_case_records(session, [case, *pool])
    new_rec, others = records[0], records[1:]
    by_id = {c.id: c for c in pool}
    suggestions = detect_relationships(new_rec, others, sim, th, now)
    for s in suggestions:
        other = by_id[s.other_id]  # type: ignore[index]
        if s.relation == "UNRELATED":
            out.unrelated.append((other, s))
            continue
        if existing_active_link(session, case.id, other.id) is not None:
            continue
        link = persist_suggestion(session, case, other, s)
        out.links.append((link, other, s))
    return out


def start_duplicate_clocks(session: Session, link: CaseLink, a: Case, b: Case, now: datetime | None = None) -> None:
    """the policy-clock rules: a case linked as DUPLICATE to a CPGRAMS case also carries the 21-day clock.
    Applied only when an officer CONFIRMS the duplicate (suggestions never change clocks)."""
    if link.relation != RelationType.DUPLICATE:
        return
    for me, other in ((a, b), (b, a)):
        if other.source_channel == SourceChannel.CPGRAMS and me.status in OPEN_STATUSES:
            clocks_svc.start_clocks_for_case(session, me, now=now or _now(), linked_cpgrams_duplicate=True)


# ====================================================================== decisions
def decide_link(session: Session, link_id: uuid.UUID, user: User, decision: str, reason: str) -> CaseLink:
    link = _get_link(session, link_id, lock=True)
    if link.status == LinkStatus.SUPERSEDED:
        raise ApiError(409, "LINK_SUPERSEDED", "This link version was superseded by a newer suggestion")
    a, b = _link_cases(session, link)
    if not can_decide(user, a, b):
        raise ApiError(
            403, "FORBIDDEN", "Only the owner officers, the bureau heads of either case, or an admin can decide a link"
        )
    reason = reason.strip()
    if len(reason) < 3:
        raise ApiError(422, "REASON_REQUIRED", "A reason is required for every link decision")
    previous = link.status
    _archive(session, link)
    link.status = STATUS_BY_DECISION[decision]
    link.version = next_version(session, link.case_a_id, link.case_b_id)
    link.decided_by = user.id
    link.decided_at = _now()
    link.decision_reason = reason
    session.flush()
    _passport_both(
        session, EVENT_BY_DECISION[decision], link, a, b, actor=user,
        extra={"reason": reason, "from_status": previous.value},
    )
    if decision == "CONFIRM":
        start_duplicate_clocks(session, link, a, b)
        notify_for_link(session, link, a, b, exclude=[user.id], prefix="Confirmed - ")
    return link


def revert_link(session: Session, link_id: uuid.UUID, user: User, reason: str) -> CaseLink:
    link = _get_link(session, link_id, lock=True)
    a, b = _link_cases(session, link)
    if not can_decide(user, a, b):
        raise ApiError(403, "FORBIDDEN", "Only the owner officers, bureau heads of either case, or an admin can revert a link")
    reason = reason.strip()
    if len(reason) < 3:
        raise ApiError(422, "REASON_REQUIRED", "A reason is required to revert a link")
    prev = session.scalar(
        select(CaseLinkHistory)
        .where(CaseLinkHistory.link_id == link.id, CaseLinkHistory.status != LinkStatus.SUPERSEDED)
        .order_by(CaseLinkHistory.version.desc())
        .limit(1)
    )
    if prev is None or link.status == LinkStatus.SUPERSEDED:
        raise ApiError(409, "NOTHING_TO_REVERT", "This link has no earlier version to revert to")
    from_status = link.status
    _archive(session, link)
    link.relation = prev.relation
    link.score = prev.score
    link.features = prev.features or {}
    link.reasons = list(prev.reasons or [])
    link.status = prev.status
    link.version = next_version(session, link.case_a_id, link.case_b_id)
    link.decided_by = user.id
    link.decided_at = _now()
    link.decision_reason = f"Reverted: {reason}"
    session.flush()
    _passport_both(
        session, "LINK_REVERTED", link, a, b, actor=user,
        extra={"reason": reason, "from_status": from_status.value, "restored_version": prev.version},
    )
    return link


# ====================================================================== read side
def _brief(case: Case) -> LinkCaseBrief:
    return LinkCaseBrief(
        id=case.id,
        display_id=case.display_id,
        owner_bureau=case.owner_bureau,
        owner_officer_name=case.owner_officer.name if case.owner_officer else None,
        status=case.status,
        category=case.category,
        subject=case.subject,
    )


def list_links(
    session: Session,
    user: User,
    *,
    relation: Sequence[RelationType] | None = None,
    status: Sequence[LinkStatus] | None = None,
    bureau: Bureau | None = None,
    institution_id: uuid.UUID | None = None,
    needs_my_decision: bool = False,
    both_open: bool = False,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[LinkListItem], int]:
    ca, cb = aliased(Case), aliased(Case)
    q = select(CaseLink, ca, cb).join(ca, ca.id == CaseLink.case_a_id).join(cb, cb.id == CaseLink.case_b_id)
    q = q.where(CaseLink.relation != RelationType.UNRELATED)
    if relation:
        q = q.where(CaseLink.relation.in_(relation))
    q = q.where(CaseLink.status.in_(status) if status else CaseLink.status != LinkStatus.SUPERSEDED)
    if both_open:
        # Same predicate as the dashboard 'Open coordination alerts' KPI (active links, both cases open).
        from app.services.dashboard import open_alert_conditions

        q = q.where(*open_alert_conditions(ca, cb))
    if bureau:
        q = q.where(or_(ca.owner_bureau == bureau, cb.owner_bureau == bureau))
    if institution_id:
        q = q.where(or_(ca.institution_id == institution_id, cb.institution_id == institution_id))
    if needs_my_decision:
        q = q.where(CaseLink.status == LinkStatus.SUGGESTED)
    rows = session.execute(q).unique().all()
    rank = {RelationType.CONFLICTING: 0, RelationType.DUPLICATE: 1, RelationType.RELATED: 2}
    items: list[tuple[CaseLink, Case, Case, bool]] = []
    for link, a, b in rows:
        mine = can_decide(user, a, b)
        if needs_my_decision and not mine:
            continue
        items.append((link, a, b, mine))
    items.sort(key=lambda t: (rank.get(t[0].relation, 9), t[0].created_at))
    total = len(items)
    start = (page - 1) * page_size
    out: list[LinkListItem] = []
    for link, a, b, mine in items[start : start + page_size]:
        reasons = list(link.reasons or [])
        out.append(
            LinkListItem(
                id=link.id,
                relation=link.relation,
                status=link.status,
                score=float(link.score),
                version=link.version,
                top_reason=reasons[0] if reasons else None,
                reasons=reasons,
                institution=_inst_ref(a.institution or b.institution),
                case_a=_brief(a),
                case_b=_brief(b),
                suggested_next_action=_next_action(link),
                lead_bureau=_lead(link),
                created_at=link.created_at,
                decided_at=link.decided_at,
                needs_my_decision=mine and link.status == LinkStatus.SUGGESTED,
            )
        )
    return out, total


def _user_names(session: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, User]:
    real = {i for i in ids if i}
    if not real:
        return {}
    return {u.id: u for u in session.scalars(select(User).where(User.id.in_(real)))}


def _thread_out(session: Session, link: CaseLink) -> ThreadOut | None:
    thread = session.scalar(select(CoordinationThread).where(CoordinationThread.link_id == link.id))
    if thread is None:
        return None
    msgs = session.scalars(
        select(CoordinationMessage)
        .where(CoordinationMessage.thread_id == thread.id)
        .order_by(CoordinationMessage.created_at, CoordinationMessage.id)
    ).all()
    users = _user_names(session, {m.author_id for m in msgs})
    return ThreadOut(
        id=thread.id,
        lead_bureau=thread.lead_bureau,
        shared_next_action=thread.shared_next_action,
        status=thread.status,
        messages=[
            ThreadMessageOut(
                id=m.id,
                author_id=m.author_id,
                author_name=users[m.author_id].name if m.author_id in users else "System",
                author_bureau=users[m.author_id].bureau if m.author_id in users else None,
                body=m.body,
                created_at=m.created_at,
            )
            for m in msgs
        ],
    )


def _history(session: Session, link: CaseLink) -> list[LinkVersionOut]:
    rows = session.scalars(
        select(CaseLinkHistory).where(CaseLinkHistory.link_id == link.id).order_by(CaseLinkHistory.version)
    ).all()
    sup = session.scalars(
        select(CaseLink).where(
            CaseLink.case_a_id == link.case_a_id,
            CaseLink.case_b_id == link.case_b_id,
            CaseLink.id != link.id,
            CaseLink.status == LinkStatus.SUPERSEDED,
        )
    ).all()
    users = _user_names(
        session, {r.decided_by for r in rows} | {s.decided_by for s in sup} | {link.decided_by}
    )

    def name(uid: uuid.UUID | None) -> str | None:
        return users[uid].name if uid in users else None

    items = [
        LinkVersionOut(
            version=r.version, relation=r.relation, status=r.status, score=float(r.score),
            reasons=list(r.reasons or []), decided_by_name=name(r.decided_by), decided_at=r.decided_at,
            decision_reason=r.decision_reason, archived_at=r.archived_at,
        )
        for r in rows
    ]
    items += [
        LinkVersionOut(
            version=s.version, relation=s.relation, status=s.status, score=float(s.score),
            reasons=list(s.reasons or []), decided_by_name=name(s.decided_by), decided_at=s.decided_at,
            decision_reason=s.decision_reason, archived_at=s.decided_at or s.created_at,
        )
        for s in sup
    ]
    items.sort(key=lambda v: v.version)
    items.append(
        LinkVersionOut(
            version=link.version, relation=link.relation, status=link.status, score=float(link.score),
            reasons=list(link.reasons or []), decided_by_name=name(link.decided_by),
            decided_at=link.decided_at, decision_reason=link.decision_reason, current=True,
        )
    )
    return items


def _feature_rows(features: dict[str, Any]) -> list[FeatureRow]:
    rows: list[FeatureRow] = []
    for key, label in FEATURE_LABELS.items():
        if key in features:
            val = features[key]
            if isinstance(val, int | float | bool) or val is None:
                rows.append(FeatureRow(key=key, label=label, value=val))
    return rows


def link_detail(session: Session, link_id: uuid.UUID, user: User) -> LinkDetail:
    link = _get_link(session, link_id)
    a, b = _link_cases(session, link)
    feats = {k: v for k, v in (link.features or {}).items() if k not in _META_KEYS}
    users = _user_names(session, {link.decided_by})
    return LinkDetail(
        id=link.id,
        relation=link.relation,
        status=link.status,
        score=float(link.score),
        version=link.version,
        reasons=list(link.reasons or []),
        features=feats,
        feature_rows=_feature_rows(feats),
        suggested_next_action=_next_action(link),
        lead_bureau=_lead(link),
        institution=_inst_ref(a.institution or b.institution),
        case_a=case_views.build_case_detail(session, a, user),
        case_b=case_views.build_case_detail(session, b, user),
        decided_by_name=users[link.decided_by].name if link.decided_by in users else None,
        decided_at=link.decided_at,
        decision_reason=link.decision_reason,
        created_at=link.created_at,
        history=_history(session, link),
        thread=_thread_out(session, link),
        can_decide=can_decide(user, a, b) and link.status != LinkStatus.SUPERSEDED,
    )


# ====================================================================== thread (P1)
def _ensure_thread(session: Session, link: CaseLink) -> CoordinationThread:
    thread = session.scalar(select(CoordinationThread).where(CoordinationThread.link_id == link.id))
    if thread is None:
        thread = CoordinationThread(link_id=link.id, lead_bureau=_lead(link), shared_next_action=_next_action(link))
        session.add(thread)
        session.flush()
    return thread


def _audit(session: Session, user: User, method: str, path: str, entity: str, entity_id: Any, summary: str) -> None:
    session.add(
        AuditLog(user_id=user.id, method=method, path=path, entity=entity, entity_id=str(entity_id), summary=summary[:500])
    )
    session.flush()


def post_message(session: Session, link_id: uuid.UUID, user: User, body: str) -> ThreadOut:
    link = _get_link(session, link_id)
    a, b = _link_cases(session, link)
    if not can_participate(user, a, b):
        raise ApiError(403, "FORBIDDEN", "Only the two owning bureaus can post to this coordination thread")
    thread = _ensure_thread(session, link)
    session.add(CoordinationMessage(thread_id=thread.id, author_id=user.id, body=body.strip()))
    session.flush()
    _audit(session, user, "POST", f"/links/{link.id}/thread/messages", "coordination_thread", thread.id,
           "Coordination message posted")
    return _thread_out(session, link)  # type: ignore[return-value]


def patch_thread(
    session: Session, link_id: uuid.UUID, user: User, *, lead_bureau: Bureau | None,
    shared_next_action: str | None, fields_set: set[str],
) -> ThreadOut:
    link = _get_link(session, link_id)
    a, b = _link_cases(session, link)
    if not can_participate(user, a, b):
        raise ApiError(403, "FORBIDDEN", "Only the two owning bureaus can edit this coordination thread")
    thread = _ensure_thread(session, link)
    changed: dict[str, Any] = {}
    if "lead_bureau" in fields_set and lead_bureau != thread.lead_bureau:
        changed["lead_bureau"] = {"from": thread.lead_bureau.value if thread.lead_bureau else None,
                                  "to": lead_bureau.value if lead_bureau else None}
        thread.lead_bureau = lead_bureau
    if "shared_next_action" in fields_set and shared_next_action != thread.shared_next_action:
        changed["shared_next_action"] = True
        thread.shared_next_action = shared_next_action
    if changed:
        session.flush()
        _passport_both(session, "REMARK", link, a, b, actor=user,
                       extra={"coordination_thread_updated": changed})
    return _thread_out(session, link)  # type: ignore[return-value]


# ====================================================================== sweep
def run_sweep(session: Session, user: User | None) -> dict[str, int]:
    """Nightly / on-demand re-scan of every institution with >= 2 open cases (the CaseLink design C).

    Never modifies CONFIRMED / REJECTED links. NEW inserts a SUGGESTED link, SUPERSEDE marks the old
    suggestion SUPERSEDED and inserts the re-classified one (version + 1), ESCALATE adds a new
    SUGGESTED CONFLICTING version next to a decided link. Caller commits.
    Returns {pairs_checked, new_links (rows inserted), superseded (old rows superseded)}.
    """
    now = _now()
    refit_similarity(session)
    sim = get_similarity(session)
    th = load_thresholds(session)
    cases = list(
        session.scalars(
            select(Case).where(Case.status.in_(OPEN_STATUSES), Case.institution_id.is_not(None))
        ).unique().all()
    )
    by_id = {c.id: c for c in cases}
    records = load_case_records(session, cases)
    by_inst: dict[uuid.UUID, list[Any]] = {}
    for rec in records:
        by_inst.setdefault(rec.institution_id, []).append(rec)  # type: ignore[arg-type]
    existing_rows = session.scalars(
        select(CaseLink).where(
            CaseLink.status != LinkStatus.SUPERSEDED,
            CaseLink.case_a_id.in_(list(by_id)) if by_id else CaseLink.id.is_(None),
        )
    ).all()
    existing = [
        ExistingLink(
            case_a_id=r.case_a_id, case_b_id=r.case_b_id, relation=r.relation.value,
            status=r.status.value, id=r.id, version=r.version,
        )
        for r in existing_rows
    ]
    result = sweep_relationships(by_inst, sim, th, now, existing)
    link_by_id = {r.id: r for r in existing_rows}
    new_links = superseded = 0
    for act in result.actions:
        newer = by_id.get(act.case_id)  # type: ignore[arg-type]
        older = by_id.get(act.other_id)  # type: ignore[arg-type]
        if newer is None or older is None:
            continue
        if act.kind == "SUPERSEDE":
            old = link_by_id.get(act.supersedes_link_id)  # type: ignore[arg-type]
            if old is None or old.status in (LinkStatus.CONFIRMED, LinkStatus.REJECTED):
                continue
            _archive(session, old)
            old.status = LinkStatus.SUPERSEDED
            session.flush()
            a, b = _link_cases(session, old)
            _passport_both(
                session, "LINK_SUPERSEDED", old, a, b, actor=None,
                extra={"previous_relation": act.previous_relation,
                       "new_relation": act.suggestion.relation if act.suggestion else "UNRELATED"},
            )
            superseded += 1
            if act.suggestion is not None:
                persist_suggestion(session, newer, older, act.suggestion,
                                   extra_payload={"reason": "sweep: relation changed"})
                new_links += 1
        elif act.kind in ("NEW", "ESCALATE") and act.suggestion is not None:
            extra = {"reason": "sweep: escalated to CONFLICTING"} if act.kind == "ESCALATE" else {"reason": "sweep"}
            persist_suggestion(session, newer, older, act.suggestion, extra_payload=extra)
            new_links += 1
    if user is not None:
        _audit(session, user, "POST", "/admin/sweep", "sweep", "-",
               f"Relationship sweep: pairs={result.pairs_scanned} new={new_links} superseded={superseded}")
    return {"pairs_checked": int(result.pairs_scanned), "new_links": new_links, "superseded": superseded}

