"""Institution-match review (FR-36), alias memory (FR-9) and institution creation.

CONFIRM sets the institution, stores the raw text as an alias (source CONFIRMED_MATCH) so the same
text resolves EXACT next time, writes Passport and then runs stage B. Advisory flow: nothing is
decided without an officer.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.cases import Case, InstitutionMatchCandidate
from app.models.enums import CLOSED_STATUSES, LinkStatus, MatchStatus, Role
from app.models.institutions import Institution, InstitutionAlias
from app.models.links import CaseLink, CaseLinkHistory
from app.models.system import AuditLog
from app.models.users import RegionalOffice, User
from app.schemas.workflows import InstitutionCreate, ReviewCandidate, ReviewItem, ReviewQueue
from app.services import passport, privacy
from app.services.case_actions import require_editor
from app.services.caselink_runtime import invalidate_index
from app.services.links import DetectionOutcome, detect_and_persist
from app.services.normalise import normalise_name

QUEUE_STATUSES = (MatchStatus.NEEDS_REVIEW,)
DECIDABLE = (MatchStatus.NEEDS_REVIEW, MatchStatus.UNRESOLVED, MatchStatus.AUTO_SUGGESTED, MatchStatus.REJECTED)


def _audit(session: Session, user: User, method: str, path: str, entity: str, entity_id: Any, summary: str) -> None:
    session.add(
        AuditLog(user_id=user.id, method=method, path=path, entity=entity, entity_id=str(entity_id), summary=summary[:500])
    )
    session.flush()


# ====================================================================== institutions / aliases
def _generate_permanent_id(session: Session) -> str:
    for _ in range(50):
        pid = "1-44" + "".join(str(secrets.randbelow(10)) for _ in range(9))
        if session.scalar(select(Institution.id).where(Institution.permanent_id == pid)) is None:
            return pid
    raise ApiError(500, "INTERNAL_ERROR", "Could not allocate a Permanent ID")


def create_institution(session: Session, user: User, data: InstitutionCreate) -> Institution:
    """POST /institutions (ADMIN or an officer). A register entry created from an unresolved case."""
    if user.role == Role.SENIOR_MGMT:
        raise ApiError(403, "FORBIDDEN", "Senior management cannot create institutions")
    pid = data.permanent_id or _generate_permanent_id(session)
    if session.scalar(select(Institution.id).where(Institution.permanent_id == pid)) is not None:
        raise ApiError(409, "CONFLICT", "An institution with this Permanent ID already exists")
    if data.ro_code and session.get(RegionalOffice, data.ro_code) is None:
        raise ApiError(422, "VALIDATION_ERROR", "Unknown regional office code")
    inst = Institution(
        permanent_id=pid,
        name=data.name.strip(),
        name_norm=normalise_name(data.name).text,
        inst_type=data.inst_type,
        address=data.address,
        district=data.district,
        state=data.state,
        pincode=data.pincode,
        ro_code=data.ro_code,
        email_domain=(data.email_domain or "").lower() or None,
        phone=data.phone,
        established_year=data.established_year,
        approval_status="APPROVED",
    )
    session.add(inst)
    session.flush()
    invalidate_index()
    _audit(session, user, "POST", "/institutions", "institution", inst.id,
           f"Institution created ({inst.permanent_id}) from an unresolved complaint")
    return inst


def add_alias(
    session: Session, inst: Institution, alias_raw: str, user: User | None, *, source: str = "CONFIRMED_MATCH",
    strict: bool = False,
) -> InstitutionAlias | None:
    """Store `alias_raw` as an alias. Internal callers (strict=False) silently skip empty/duplicate
    aliases; the endpoint (strict=True) answers 422/409."""
    raw = (alias_raw or "").strip()
    norm = normalise_name(raw).text
    if not norm:
        if strict:
            raise ApiError(422, "VALIDATION_ERROR", "Alias has no usable text")
        return None
    own = normalise_name(inst.name).text
    exists = session.scalar(
        select(InstitutionAlias.id).where(
            InstitutionAlias.institution_id == inst.id, InstitutionAlias.alias_norm == norm
        )
    )
    if exists is not None or norm == own:
        if strict:
            raise ApiError(409, "CONFLICT", "This alias already exists for the institution")
        return None
    alias = InstitutionAlias(
        institution_id=inst.id, alias_raw=raw[:300], alias_norm=norm, source=source,
        created_by=user.id if user else None,
    )
    session.add(alias)
    session.flush()
    invalidate_index()
    return alias


# ====================================================================== review queue
def review_queue(
    session: Session, user: User, *, include_unresolved: bool = False, limit: int = 100
) -> ReviewQueue:
    statuses = [MatchStatus.NEEDS_REVIEW]
    if include_unresolved:
        statuses += [MatchStatus.UNRESOLVED, MatchStatus.REJECTED]
    cases = list(
        session.scalars(
            select(Case).where(Case.institution_match_status.in_(statuses)).order_by(Case.received_at)
        ).unique().all()
    )
    if user.role not in (Role.ADMIN, Role.SENIOR_MGMT):
        cases = [c for c in cases if privacy.is_owner(c, user)]
    total = len(cases)
    cases = cases[:limit]
    ids = [c.id for c in cases]
    cand_map: dict[uuid.UUID, list[InstitutionMatchCandidate]] = {i: [] for i in ids}
    if ids:
        for cand in session.scalars(
            select(InstitutionMatchCandidate)
            .where(InstitutionMatchCandidate.case_id.in_(ids), InstitutionMatchCandidate.rank <= 3)
            .order_by(InstitutionMatchCandidate.rank)
        ).unique():
            cand_map[cand.case_id].append(cand)
    items: list[ReviewItem] = []
    for c in cases:
        items.append(
            ReviewItem(
                case_id=c.id,
                display_id=c.display_id,
                subject=c.subject,
                source_channel=c.source_channel.value,
                received_at=c.received_at,
                owner_bureau=c.owner_bureau,
                institution_text_raw=c.institution_text_raw,
                normalised_text=normalise_name(c.institution_text_raw).text if c.institution_text_raw else None,
                permanent_id_raw=c.permanent_id_raw,
                language=c.language,
                match_status=c.institution_match_status,
                top_score=float(c.institution_match_score) if c.institution_match_score is not None else None,
                candidates=[
                    ReviewCandidate(
                        institution_id=k.institution_id,
                        name=k.institution.name,
                        permanent_id=k.institution.permanent_id,
                        district=k.institution.district,
                        state=k.institution.state,
                        rank=k.rank,
                        score=float(k.score),
                        reasons=list(k.reasons or []),
                        features=dict(k.features or {}),
                    )
                    for k in cand_map.get(c.id, [])
                ],
            )
        )
    return ReviewQueue(items=items, total=total)


# ====================================================================== decisions
def _supersede_open_links(session: Session, case: Case, user: User) -> None:
    """The case moves to another institution: its undecided suggestions no longer apply."""
    links = session.scalars(
        select(CaseLink).where(
            (CaseLink.case_a_id == case.id) | (CaseLink.case_b_id == case.id),
            CaseLink.status.in_((LinkStatus.SUGGESTED, LinkStatus.DEFERRED)),
        )
    ).all()
    for link in links:
        session.add(
            CaseLinkHistory(
                link_id=link.id, version=link.version, relation=link.relation, score=link.score,
                features=link.features or {}, reasons=list(link.reasons or []), status=link.status,
                decided_by=link.decided_by, decided_at=link.decided_at, decision_reason=link.decision_reason,
            )
        )
        link.status = LinkStatus.SUPERSEDED
        session.flush()
        other_id = link.case_b_id if link.case_a_id == case.id else link.case_a_id
        for cid, oid in ((case.id, other_id), (other_id, case.id)):
            c = session.get(Case, cid)
            o = session.get(Case, oid)
            if c is None or o is None:
                continue
            passport.append_entry(
                session, event="LINK_SUPERSEDED", case_id=c.id, institution_id=c.institution_id, actor=user,
                payload={"link_id": str(link.id), "other_case": o.display_id,
                         "reason": "institution match changed"},
            )


def _decide_candidates(
    session: Session, case: Case, chosen_id: uuid.UUID | None, user: User, reason: str, now: datetime
) -> None:
    for cand in session.scalars(
        select(InstitutionMatchCandidate).where(InstitutionMatchCandidate.case_id == case.id)
    ).unique():
        confirmed = chosen_id is not None and cand.institution_id == chosen_id
        cand.status = MatchStatus.CONFIRMED if confirmed else MatchStatus.REJECTED
        cand.decided_by = user.id
        cand.decided_at = now
        cand.decision_reason = reason
    session.flush()


def decide_match(
    session: Session,
    case: Case,
    user: User,
    *,
    decision: str,
    institution_id: uuid.UUID | None,
    reason: str,
    new_institution: InstitutionCreate | None,
    now: datetime | None = None,
) -> tuple[str | None, DetectionOutcome]:
    """Apply CONFIRM / REJECT / CREATE_NEW. Returns (alias added, stage-B outcome)."""
    require_editor(case, user)
    now = now or datetime.now(UTC)
    if case.institution_match_status not in DECIDABLE:
        raise ApiError(409, "ALREADY_DECIDED", "The institution for this case is already confirmed")
    if case.status in CLOSED_STATUSES:
        raise ApiError(409, "CASE_CLOSED", "A closed case cannot be re-matched")
    reason = reason.strip()
    if len(reason) < 3:
        raise ApiError(422, "REASON_REQUIRED", "A reason is required")
    previous_status = case.institution_match_status
    previous_inst = case.institution_id
    empty = DetectionOutcome()

    if decision == "REJECT":
        if previous_inst is not None:
            _supersede_open_links(session, case, user)
        _decide_candidates(session, case, None, user, reason, now)
        case.institution_id = None
        case.institution = None
        case.institution_match_status = MatchStatus.REJECTED
        session.flush()
        passport.append_entry(
            session, event="INSTITUTION_REJECTED", case_id=case.id, institution_id=None, actor=user,
            payload={"reason": reason, "previous_status": previous_status.value},
        )
        return None, empty

    created_new = False
    if decision == "CREATE_NEW":
        data = new_institution
        if data is None:
            text = (case.institution_text_raw or "").strip()
            if len(text) < 3:
                raise ApiError(422, "VALIDATION_ERROR", "new_institution is required (no usable institution text)")
            data = InstitutionCreate(name=text, ro_code=case.owner_ro_code)
        inst = create_institution(session, user, data)
        created_new = True
    else:  # CONFIRM
        target = institution_id
        if target is None:
            top = session.scalar(
                select(InstitutionMatchCandidate)
                .where(InstitutionMatchCandidate.case_id == case.id)
                .order_by(InstitutionMatchCandidate.rank)
                .limit(1)
            )
            target = top.institution_id if top else None
        if target is None:
            raise ApiError(422, "VALIDATION_ERROR", "institution_id is required (no candidates to confirm)")
        inst = session.get(Institution, target)
        if inst is None:
            raise ApiError(404, "NOT_FOUND", "Institution not found")

    changed = previous_inst != inst.id
    if changed and previous_inst is not None:
        _supersede_open_links(session, case, user)
    chosen = session.scalar(
        select(InstitutionMatchCandidate).where(
            InstitutionMatchCandidate.case_id == case.id, InstitutionMatchCandidate.institution_id == inst.id
        )
    )
    case.institution_id = inst.id
    case.institution = inst
    case.institution_match_status = MatchStatus.CONFIRMED
    case.institution_match_score = chosen.score if chosen is not None else None
    if case.institution_match_score is None:
        case.institution_match_score = 1.000 if created_new else case.institution_match_score
    _decide_candidates(session, case, inst.id, user, reason, now)
    alias = add_alias(session, inst, case.institution_text_raw or "", user) if case.institution_text_raw else None
    session.flush()
    passport.append_entry(
        session, event="INSTITUTION_CONFIRMED", case_id=case.id, institution_id=inst.id, actor=user,
        payload={
            "institution": inst.name,
            "permanent_id": inst.permanent_id,
            "reason": reason,
            "previous_status": previous_status.value,
            "created_new_institution": created_new,
            "alias_added": alias.alias_raw if alias else None,
        },
    )
    outcome = detect_and_persist(session, case, user, now) if (changed or previous_inst is None) else empty
    return (alias.alias_raw if alias else None), outcome
