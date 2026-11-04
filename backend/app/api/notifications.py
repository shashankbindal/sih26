"""In-app notifications for the user or the user's bureau."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.schemas.workflows import NotificationList, NotificationOut, ReadAllResult
from app.services import notifications

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationList)
def list_notifications(
    db: DbSession, user: CurrentUser, unread: bool = False, limit: int = Query(50, ge=1, le=200)
) -> NotificationList:
    return notifications.list_notifications(db, user, unread=unread, limit=limit)


@router.post("/read-all", response_model=ReadAllResult)
def read_all(db: DbSession, user: CurrentUser) -> ReadAllResult:
    n = notifications.mark_all_read(db, user)
    db.commit()
    return ReadAllResult(updated=n)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def read_one(notification_id: uuid.UUID, db: DbSession, user: CurrentUser) -> NotificationOut:
    out = notifications.mark_read(db, user, notification_id)
    db.commit()
    return out
