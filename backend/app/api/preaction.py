"""Pre-Action Check (FR-16..FR-20): panel, acknowledgement, action list/detail and action Passport."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.errors import ApiError
from app.models.enums import Bureau, InstActionType
from app.models.institutions import Institution
from app.schemas.passport import VerifyOut
from app.schemas.workflows import (
    AcknowledgeRequest,
    AcknowledgeResult,
    ActionPassport,
    InstitutionActionDetail,
    InstitutionActionPage,
    PreActionPanel,
    PreActionRequest,
)
from app.services import institution_actions as svc
from app.services import passport

router = APIRouter(tags=["pre-action"])


@router.post("/institutions/{institution_id}/pre-action-check", response_model=PreActionPanel, status_code=201)
def pre_action_check(
    institution_id: uuid.UUID, body: PreActionRequest, db: DbSession, user: CurrentUser
) -> PreActionPanel:
    svc.require_pre_action_role(user)
    inst = db.get(Institution, institution_id)
    if inst is None:
        raise ApiError(404, "NOT_FOUND", "Institution not found")
    panel = svc.start_check(db, user, inst, body.action_type)
    db.commit()
    return panel


@router.post("/institution-actions/{action_id}/acknowledge", response_model=AcknowledgeResult)
def acknowledge(
    action_id: uuid.UUID, body: AcknowledgeRequest, db: DbSession, user: CurrentUser
) -> AcknowledgeResult:
    action, entry = svc.acknowledge(
        db, user, action_id, remark=body.remark, proceed=body.proceed, acknowledged=body.acknowledged
    )
    db.commit()
    names = svc.users_by_id(db, {entry.actor_id})
    return AcknowledgeResult(action=svc.action_out(db, action), passport_entry=svc.entry_out(entry, names))


@router.get("/institution-actions", response_model=InstitutionActionPage)
def list_actions(
    db: DbSession,
    _user: CurrentUser,
    institution_id: uuid.UUID | None = None,
    bureau: Bureau | None = None,
    status: str | None = Query(None, pattern="^(CHECK_SHOWN|ACKNOWLEDGED|PROCEEDED|ON_HOLD|WITHDRAWN)$"),
    action_type: InstActionType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> InstitutionActionPage:
    items, total = svc.list_actions(
        db, institution_id=institution_id, bureau=bureau, status=status, action_type=action_type,
        page=page, page_size=page_size,
    )
    return InstitutionActionPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/institution-actions/{action_id}", response_model=InstitutionActionDetail)
def get_action(action_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> InstitutionActionDetail:
    return svc.action_detail(db, svc.get_action(db, action_id))


@router.get("/institution-actions/{action_id}/passport", response_model=ActionPassport)
def action_passport(action_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> ActionPassport:
    svc.get_action(db, action_id)
    return svc.action_passport(db, action_id)


@router.get("/institution-actions/{action_id}/passport/verify", response_model=VerifyOut)
def verify_action_passport(action_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> VerifyOut:
    svc.get_action(db, action_id)
    return VerifyOut(**passport.verify_chain(db, chain_key=svc.chain_key(action_id)))
