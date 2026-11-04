from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.errors import ApiError
from app.models.institutions import Institution
from app.schemas.institutions import (
    InstitutionDetail,
    InstitutionLinkOut,
    InstitutionListPage,
    InstitutionTimeline,
)
from app.services import institution_views

router = APIRouter(prefix="/institutions", tags=["institutions"])


def _get(db: DbSession, institution_id: uuid.UUID) -> Institution:
    inst = db.get(Institution, institution_id)
    if inst is None:
        raise ApiError(404, "NOT_FOUND", "Institution not found")
    return inst


@router.get("", response_model=InstitutionListPage)
def list_institutions(
    db: DbSession,
    _user: CurrentUser,
    q: str | None = Query(None, max_length=200),
    ro_code: str | None = None,
    state: str | None = None,
    district: str | None = None,
    type: str | None = None,
    approval_status: str | None = None,
    has_open_alerts: bool | None = None,
    sort: str | None = Query(None, pattern="^(open_cases_desc|name)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> InstitutionListPage:
    items, total = institution_views.list_institutions(
        db,
        q=q,
        ro_code=ro_code,
        state=state,
        district=district,
        inst_type=type,
        approval_status=approval_status,
        has_open_alerts=has_open_alerts,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return InstitutionListPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{institution_id}", response_model=InstitutionDetail)
def get_institution(institution_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> InstitutionDetail:
    return institution_views.institution_detail(db, _get(db, institution_id))


@router.get("/{institution_id}/timeline", response_model=InstitutionTimeline)
def get_timeline(institution_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> InstitutionTimeline:
    items = institution_views.institution_timeline(db, _get(db, institution_id))
    return InstitutionTimeline(items=items, total=len(items))


@router.get("/{institution_id}/links", response_model=list[InstitutionLinkOut])
def get_links(
    institution_id: uuid.UUID, db: DbSession, _user: CurrentUser
) -> list[InstitutionLinkOut]:
    return institution_views.institution_links(db, _get(db, institution_id))
