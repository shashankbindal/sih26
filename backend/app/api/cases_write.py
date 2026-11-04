"""Case write endpoints: create, patch, transfer, remarks, dispose.

Routers only validate, check the role table and call services; they commit.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.cases import get_case_or_404
from app.deps import CurrentUser, DbSession, require_roles
from app.models.enums import Role
from app.models.users import User
from app.schemas.cases import CaseDetail
from app.schemas.intake import CaseCreate, CaseCreateResult
from app.schemas.workflows import AtrReceived, CaseDispose, CasePatch, CaseRemark, CaseTransfer
from app.services import case_actions, case_views, intake

router = APIRouter(prefix="/cases", tags=["cases"])

# Create case: all officers, ADMIN (SENIOR_MGMT is read-only).
CREATORS = (
    Role.PGRC_OFFICER,
    Role.RB_OFFICER,
    Role.APPROVAL_OFFICER,
    Role.VIGILANCE_OFFICER,
    Role.RO_OFFICER,
    Role.BUREAU_HEAD,
    Role.ADMIN,
)


@router.post("", response_model=CaseCreateResult, status_code=201)
def create_case(
    body: CaseCreate, db: DbSession, user: User = Depends(require_roles(*CREATORS))
) -> CaseCreateResult:
    result = intake.create_case(db, body, user)
    db.commit()
    return result


@router.patch("/{case_id}", response_model=CaseDetail)
def patch_case(case_id: uuid.UUID, body: CasePatch, db: DbSession, user: CurrentUser) -> CaseDetail:
    case = get_case_or_404(db, case_id)
    case_actions.patch_case(db, case, user, body)
    db.commit()
    return case_views.build_case_detail(db, case, user)


@router.post("/{case_id}/transfer", response_model=CaseDetail)
def transfer_case(case_id: uuid.UUID, body: CaseTransfer, db: DbSession, user: CurrentUser) -> CaseDetail:
    case = get_case_or_404(db, case_id)
    case_actions.transfer_case(db, case, user, body)
    db.commit()
    return case_views.build_case_detail(db, case, user)


@router.post("/{case_id}/remarks", response_model=CaseDetail, status_code=201)
def add_remark(case_id: uuid.UUID, body: CaseRemark, db: DbSession, user: CurrentUser) -> CaseDetail:
    case = get_case_or_404(db, case_id)
    case_actions.add_remark(db, case, user, body.remark, body.attachment_name)
    db.commit()
    return case_views.build_case_detail(db, case, user)


@router.post("/{case_id}/dispose", response_model=CaseDetail)
def dispose_case(case_id: uuid.UUID, body: CaseDispose, db: DbSession, user: CurrentUser) -> CaseDetail:
    case = get_case_or_404(db, case_id)
    case_actions.dispose_case(db, case, user, body.remark)
    db.commit()
    return case_views.build_case_detail(db, case, user)


@router.post("/{case_id}/atr-received", response_model=CaseDetail)
def atr_received(
    case_id: uuid.UUID, db: DbSession, user: CurrentUser, body: AtrReceived | None = None
) -> CaseDetail:
    """Mark the institution's ATR received: ATR_RECEIVED Passport event, INST_REFUND_7D clock MET."""
    case = get_case_or_404(db, case_id)
    case_actions.atr_received(db, case, user, body.remark if body else None)
    db.commit()
    return case_views.build_case_detail(db, case, user)
