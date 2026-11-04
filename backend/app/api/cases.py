"""Case read endpoints. Write endpoints (create/patch/transfer/...) live in other modules."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.errors import ApiError
from app.models.cases import Case
from app.models.enums import Bureau, CaseCategory, CaseStatus, ClockState, SourceChannel
from app.schemas.cases import CaseDetail, CaseListPage, RevealPiiRequest
from app.services import case_views, privacy

router = APIRouter(prefix="/cases", tags=["cases"])


def get_case_or_404(db: DbSession, case_id: uuid.UUID) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise ApiError(404, "NOT_FOUND", "Case not found")
    return case


@router.get("", response_model=CaseListPage)
def list_cases(
    db: DbSession,
    user: CurrentUser,
    q: str | None = Query(None, max_length=200),
    status: list[CaseStatus] | None = Query(None),
    bureau: list[Bureau] | None = Query(None),
    ro_code: list[str] | None = Query(None),
    category: list[CaseCategory] | None = Query(None),
    channel: list[SourceChannel] | None = Query(None),
    institution_id: uuid.UUID | None = None,
    overdue: bool | None = None,
    clock_state: list[ClockState] | None = Query(None),
    received_from: datetime | None = None,
    received_to: datetime | None = None,
    has_alert: bool | None = None,
    owner: str | None = Query(None, pattern="^me$"),
    scope: str | None = Query(None, pattern="^all$"),
    sort: str = Query("received_at_desc", pattern="^(received_at_desc|due_asc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> CaseListPage:
    """Case register. RO_OFFICER users are filtered to their own region (owner_ro_code or
    institution region) by default; pass `scope=all` to see every region. Other roles are
    unaffected. Complainant data stays masked outside owned/own-region cases either way."""
    items, total = case_views.list_cases(
        db,
        user,
        q=q,
        status=status,
        bureau=bureau,
        ro_code=ro_code,
        category=category,
        channel=channel,
        institution_id=institution_id,
        overdue=overdue,
        clock_state=clock_state,
        received_from=received_from,
        received_to=received_to,
        has_alert=has_alert,
        owner_me=owner == "me",
        scope_all=scope == "all",
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return CaseListPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: uuid.UUID, db: DbSession, user: CurrentUser) -> CaseDetail:
    case = get_case_or_404(db, case_id)
    return case_views.build_case_detail(db, case, user)


@router.post("/{case_id}/reveal-pii", response_model=CaseDetail)
def reveal_pii(
    case_id: uuid.UUID, body: RevealPiiRequest, db: DbSession, user: CurrentUser
) -> CaseDetail:
    """Logged reveal of complainant identity (reason >= 10 chars). SENIOR_MGMT is refused."""
    case = get_case_or_404(db, case_id)
    privacy.reveal_pii(db, case, user, body.reason)
    db.commit()
    return case_views.build_case_detail(db, case, user, revealed=True)
