from __future__ import annotations

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.schemas.search import SearchResult
from app.services import institution_views

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResult)
def search(
    db: DbSession, _user: CurrentUser, q: str = Query("", max_length=200)
) -> SearchResult:
    return institution_views.search(db, q)
