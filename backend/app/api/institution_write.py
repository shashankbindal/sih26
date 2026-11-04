"""Institution writes: create (from an unresolved case) and aliases. Reads live in institutions.py."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.cases import get_case_or_404
from app.deps import CurrentUser, DbSession
from app.errors import ApiError
from app.models.enums import MatchStatus
from app.models.institutions import Institution
from app.schemas.institutions import InstitutionDetail
from app.schemas.workflows import AliasCreate, InstitutionCreate
from app.services import institution_match, institution_views, passport
from app.services.case_actions import require_editor

router = APIRouter(prefix="/institutions", tags=["institutions"])


@router.post("", response_model=InstitutionDetail, status_code=201)
def create_institution(body: InstitutionCreate, db: DbSession, user: CurrentUser) -> InstitutionDetail:
    inst = institution_match.create_institution(db, user, body)
    if body.from_case_id is not None:
        case = get_case_or_404(db, body.from_case_id)
        require_editor(case, user)
        if case.institution_id is not None:
            raise ApiError(409, "ALREADY_DECIDED", "The case already has an institution; use the review endpoint")
        case.institution_id = inst.id
        case.institution = inst
        case.institution_match_status = MatchStatus.CONFIRMED
        case.institution_match_score = 1.000
        db.flush()
        institution_match.add_alias(db, inst, case.institution_text_raw or "", user)
        passport.append_entry(
            db, event="INSTITUTION_CONFIRMED", case_id=case.id, institution_id=inst.id, actor=user,
            payload={"institution": inst.name, "permanent_id": inst.permanent_id,
                     "created_new_institution": True, "reason": "Created from unresolved case"},
        )
    db.commit()
    return institution_views.institution_detail(db, inst)


@router.post("/{institution_id}/aliases", response_model=InstitutionDetail, status_code=201)
def add_alias(institution_id: uuid.UUID, body: AliasCreate, db: DbSession, user: CurrentUser) -> InstitutionDetail:
    from app.models.enums import Role

    if user.role == Role.SENIOR_MGMT:
        raise ApiError(403, "FORBIDDEN", "Senior management cannot edit aliases")
    inst = db.get(Institution, institution_id)
    if inst is None:
        raise ApiError(404, "NOT_FOUND", "Institution not found")
    source = "ADMIN" if user.role == Role.ADMIN else "CONFIRMED_MATCH"
    institution_match.add_alias(db, inst, body.alias_raw, user, source=source, strict=True)
    institution_match._audit(db, user, "POST", f"/institutions/{inst.id}/aliases", "institution_alias", inst.id,
                             "Alias added")
    db.commit()
    db.refresh(inst)
    return institution_views.institution_detail(db, inst)
