"""Clearance requests: request, inbox, respond (FR-19)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.models.enums import ClearanceResponse
from app.schemas.workflows import (
    ClearanceListPage,
    ClearanceOut,
    ClearanceRequestCreate,
    ClearanceRespond,
)
from app.services import institution_actions as svc

router = APIRouter(tags=["clearances"])


@router.post("/institution-actions/{action_id}/clearances", response_model=ClearanceOut, status_code=201)
def request_clearance(
    action_id: uuid.UUID, body: ClearanceRequestCreate, db: DbSession, user: CurrentUser
) -> ClearanceOut:
    req = svc.request_clearance(db, user, action_id, body.target_bureau, body.remark)
    db.commit()
    return svc.get_clearance(db, req.id)


@router.get("/clearances", response_model=ClearanceListPage)
def list_clearances(
    db: DbSession,
    user: CurrentUser,
    inbox: str = Query("me", pattern="^(me|sent|all)$"),
    status: list[ClearanceResponse] | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> ClearanceListPage:
    items, total = svc.list_clearances(db, user, inbox=inbox, statuses=status, page=page, page_size=page_size)
    return ClearanceListPage(items=items, total=total)


@router.get("/clearances/{clearance_id}", response_model=ClearanceOut)
def get_clearance(clearance_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> ClearanceOut:
    return svc.get_clearance(db, clearance_id)


@router.post("/clearances/{clearance_id}/respond", response_model=ClearanceOut)
def respond(clearance_id: uuid.UUID, body: ClearanceRespond, db: DbSession, user: CurrentUser) -> ClearanceOut:
    svc.respond_clearance(db, user, clearance_id, body.response, body.remarks)
    db.commit()
    return svc.get_clearance(db, clearance_id)
