"""In-app notifications.

Services only flush; routers commit. Bodies never contain complainant data: only display IDs,
bureaus, categories and engine reasons.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.cases import Case
from app.models.enums import Bureau, Role
from app.models.system import Notification
from app.models.users import User
from app.schemas.workflows import NotificationList, NotificationOut

KINDS = (
    "COORDINATION_REQUIRED",
    "PRIORITY_REVIEW",
    "REVIEW_SUGGESTED",
    "CLEARANCE_REQUEST",
    "CLEARANCE_RESPONSE",
    "SLA_AMBER",
    "SLA_BREACH",
    "REVIEW_QUEUE",
)

OFFICER_ROLES = (
    Role.PGRC_OFFICER,
    Role.RB_OFFICER,
    Role.APPROVAL_OFFICER,
    Role.VIGILANCE_OFFICER,
    Role.RO_OFFICER,
)


def notify(
    session: Session,
    *,
    kind: str,
    title: str,
    body: str | None = None,
    user_id: uuid.UUID | None = None,
    bureau: Bureau | None = None,
    link_path: str | None = None,
    case_id: uuid.UUID | None = None,
    institution_id: uuid.UUID | None = None,
) -> Notification:
    """Create one notification addressed to a user, or (user_id None) to a whole bureau."""
    if kind not in KINDS:
        raise ValueError(f"unknown notification kind {kind}")
    if user_id is None and bureau is None:
        raise ValueError("notification needs a user or a bureau")
    n = Notification(
        user_id=user_id,
        bureau=bureau if user_id is None else None,
        kind=kind,
        title=title[:300],
        body=body[:1000] if body else None,
        link_path=link_path,
        case_id=case_id,
        institution_id=institution_id,
    )
    session.add(n)
    session.flush()
    return n


def bureau_heads(session: Session, bureau: Bureau) -> list[User]:
    return list(
        session.scalars(
            select(User)
            .where(User.role == Role.BUREAU_HEAD, User.bureau == bureau, User.is_active.is_(True))
            .order_by(User.name)
        )
    )


def owner_recipients(case: Case) -> tuple[uuid.UUID | None, Bureau]:
    """(owner officer id or None, owner bureau): falls back to the bureau when unassigned."""
    return case.owner_officer_id, case.owner_bureau


def notify_owner(
    session: Session,
    case: Case,
    *,
    kind: str,
    title: str,
    body: str | None,
    link_path: str | None,
    exclude_user_ids: Iterable[uuid.UUID] = (),
    seen: set[uuid.UUID | str] | None = None,
) -> Notification | None:
    """Notify the owner officer of `case` (or its bureau if unassigned). `seen` de-duplicates."""
    seen = seen if seen is not None else set()
    officer_id, bureau = owner_recipients(case)
    key: uuid.UUID | str = officer_id if officer_id else f"bureau:{bureau.value}"
    if key in seen or (officer_id and officer_id in set(exclude_user_ids)):
        return None
    seen.add(key)
    return notify(
        session,
        kind=kind,
        title=title,
        body=body,
        user_id=officer_id,
        bureau=None if officer_id else bureau,
        link_path=link_path,
        case_id=case.id,
        institution_id=case.institution_id,
    )


def notify_heads(
    session: Session,
    case: Case,
    *,
    kind: str,
    title: str,
    body: str | None,
    link_path: str | None,
    seen: set[uuid.UUID | str] | None = None,
) -> list[Notification]:
    seen = seen if seen is not None else set()
    out: list[Notification] = []
    for head in bureau_heads(session, case.owner_bureau):
        if head.id in seen:
            continue
        seen.add(head.id)
        out.append(
            notify(
                session,
                kind=kind,
                title=title,
                body=body,
                user_id=head.id,
                link_path=link_path,
                case_id=case.id,
                institution_id=case.institution_id,
            )
        )
    return out


# ------------------------------------------------------------------ read side
def _visible(user: User):
    return or_(
        Notification.user_id == user.id,
        (Notification.user_id.is_(None)) & (Notification.bureau == user.bureau),
    )


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        kind=n.kind,
        title=n.title,
        body=n.body,
        link_path=n.link_path,
        case_id=n.case_id,
        institution_id=n.institution_id,
        user_id=n.user_id,
        bureau=n.bureau,
        read_at=n.read_at,
        created_at=n.created_at,
    )


def list_notifications(
    session: Session, user: User, *, unread: bool = False, limit: int = 50, kinds: Sequence[str] | None = None
) -> NotificationList:
    base = select(Notification).where(_visible(user))
    if kinds:
        base = base.where(Notification.kind.in_(kinds))
    if unread:
        base = base.where(Notification.read_at.is_(None))
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.scalars(base.order_by(Notification.created_at.desc(), Notification.id).limit(limit)).all()
    unread_count = (
        session.scalar(
            select(func.count()).select_from(Notification).where(_visible(user), Notification.read_at.is_(None))
        )
        or 0
    )
    return NotificationList(items=[_out(n) for n in rows], total=int(total), unread_count=int(unread_count))


def mark_read(session: Session, user: User, notification_id: uuid.UUID) -> NotificationOut:
    n = session.scalar(select(Notification).where(Notification.id == notification_id, _visible(user)))
    if n is None:
        raise ApiError(404, "NOT_FOUND", "Notification not found")
    if n.read_at is None:
        n.read_at = datetime.now(UTC)
        session.flush()
    return _out(n)


def mark_all_read(session: Session, user: User) -> int:
    res = session.execute(
        update(Notification)
        .where(_visible(user), Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    session.flush()
    return int(res.rowcount or 0)
