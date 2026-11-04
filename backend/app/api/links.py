"""Coordination inbox and link decisions (FR-13, FR-14, FR-21, FR-22)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.models.enums import Bureau, LinkStatus, RelationType
from app.schemas.workflows import (
    LinkDecision,
    LinkDetail,
    LinkListPage,
    LinkRevert,
    ThreadMessageCreate,
    ThreadOut,
    ThreadPatch,
)
from app.services import links as links_svc

router = APIRouter(prefix="/links", tags=["links"])


@router.get("", response_model=LinkListPage)
def list_links(
    db: DbSession,
    user: CurrentUser,
    relation: list[RelationType] | None = Query(None),
    status: list[LinkStatus] | None = Query(None),
    bureau: Bureau | None = None,
    institution_id: uuid.UUID | None = None,
    needs_my_decision: bool = False,
    both_open: bool = Query(False, description="Only active links whose two cases are both open (the dashboard alert definition)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> LinkListPage:
    items, total = links_svc.list_links(
        db,
        user,
        relation=relation,
        status=status,
        bureau=bureau,
        institution_id=institution_id,
        needs_my_decision=needs_my_decision,
        both_open=both_open,
        page=page,
        page_size=page_size,
    )
    return LinkListPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{link_id}", response_model=LinkDetail)
def get_link(link_id: uuid.UUID, db: DbSession, user: CurrentUser) -> LinkDetail:
    return links_svc.link_detail(db, link_id, user)


@router.post("/{link_id}/decision", response_model=LinkDetail)
def decide(link_id: uuid.UUID, body: LinkDecision, db: DbSession, user: CurrentUser) -> LinkDetail:
    links_svc.decide_link(db, link_id, user, body.decision, body.reason)
    db.commit()
    return links_svc.link_detail(db, link_id, user)


@router.post("/{link_id}/revert", response_model=LinkDetail)
def revert(link_id: uuid.UUID, body: LinkRevert, db: DbSession, user: CurrentUser) -> LinkDetail:
    links_svc.revert_link(db, link_id, user, body.reason)
    db.commit()
    return links_svc.link_detail(db, link_id, user)


@router.post("/{link_id}/thread/messages", response_model=ThreadOut, status_code=201)
def post_message(link_id: uuid.UUID, body: ThreadMessageCreate, db: DbSession, user: CurrentUser) -> ThreadOut:
    out = links_svc.post_message(db, link_id, user, body.body)
    db.commit()
    return out


@router.patch("/{link_id}/thread", response_model=ThreadOut)
def patch_thread(link_id: uuid.UUID, body: ThreadPatch, db: DbSession, user: CurrentUser) -> ThreadOut:
    out = links_svc.patch_thread(
        db,
        link_id,
        user,
        lead_bureau=body.lead_bureau,
        shared_next_action=body.shared_next_action,
        fields_set=set(body.model_fields_set),
    )
    db.commit()
    return out
