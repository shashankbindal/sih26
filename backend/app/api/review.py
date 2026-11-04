"""Institution-match review queue (FR-36) and the decision endpoint that triggers stage B."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.cases import get_case_or_404
from app.deps import CurrentUser, DbSession
from app.schemas.cases import InstitutionRef
from app.schemas.intake import CreatedLink
from app.schemas.workflows import InstitutionMatchDecision, InstitutionMatchResult, ReviewQueue
from app.services import case_views, institution_match
from app.services.intake import brief

router = APIRouter(tags=["review"])


@router.get("/review/institution-matches", response_model=ReviewQueue)
def institution_matches(
    db: DbSession,
    user: CurrentUser,
    include_unresolved: bool = False,
    limit: int = Query(100, ge=1, le=500),
) -> ReviewQueue:
    return institution_match.review_queue(db, user, include_unresolved=include_unresolved, limit=limit)


@router.post("/cases/{case_id}/institution-match", response_model=InstitutionMatchResult)
def decide_institution_match(
    case_id: uuid.UUID, body: InstitutionMatchDecision, db: DbSession, user: CurrentUser
) -> InstitutionMatchResult:
    case = get_case_or_404(db, case_id)
    alias, outcome = institution_match.decide_match(
        db,
        case,
        user,
        decision=body.decision,
        institution_id=body.institution_id,
        reason=body.reason,
        new_institution=body.new_institution,
    )
    db.commit()
    inst = case.institution
    return InstitutionMatchResult(
        case=case_views.build_case_detail(db, case, user),
        decision=body.decision,
        institution=InstitutionRef(
            id=inst.id, permanent_id=inst.permanent_id, name=inst.name, district=inst.district,
            state=inst.state, ro_code=inst.ro_code,
        )
        if inst is not None
        else None,
        alias_added=alias,
        links=[
            CreatedLink(
                link_id=link.id,
                other_case=brief(other),
                relation=link.relation,
                status=link.status,
                score=float(link.score),
                reasons=list(link.reasons or []),
                suggested_next_action=s.suggested_next_action,
                lead_bureau=s.lead_bureau,  # type: ignore[arg-type]
            )
            for link, other, s in outcome.links
        ],
    )
