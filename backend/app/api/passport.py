from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.errors import ApiError
from app.models.cases import Case
from app.models.users import User
from app.schemas.passport import PassportEntryOut, PassportOut, VerifyOut
from app.services import passport

router = APIRouter(prefix="/cases", tags=["passport"])


def _ensure_case(db: DbSession, case_id: uuid.UUID) -> None:
    if db.get(Case, case_id) is None:
        raise ApiError(404, "NOT_FOUND", "Case not found")


@router.get("/{case_id}/passport", response_model=PassportOut)
def get_passport(case_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> PassportOut:
    _ensure_case(db, case_id)
    entries = passport.list_entries(db, case_id=case_id)
    actor_ids = {e.actor_id for e in entries if e.actor_id}
    names = (
        {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(actor_ids)))}
        if actor_ids
        else {}
    )
    return PassportOut(
        case_id=case_id,
        entries=[
            PassportEntryOut(
                seq=e.seq,
                event=e.event,
                actor_id=e.actor_id,
                actor_name=names.get(e.actor_id, "System") if e.actor_id else "System",
                actor_bureau=e.actor_bureau,
                payload=e.payload,
                attachment_name=e.attachment_name,
                created_at=e.created_at,
                hash=e.hash,
                hash_short=e.hash[:8],
                prev_hash=e.prev_hash,
            )
            for e in entries
        ],
    )


@router.get("/{case_id}/passport/verify", response_model=VerifyOut)
def verify_passport(case_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> VerifyOut:
    _ensure_case(db, case_id)
    return VerifyOut(**passport.verify_chain(db, case_id=case_id))
