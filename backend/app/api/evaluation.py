"""Evaluation of the CaseLink engine on labelled synthetic data (aggregate metrics, no PII)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.services import evaluation as svc

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/run")
def run_evaluation(
    db: DbSession,
    _user: CurrentUser,
    split: str = Query("heldout", pattern="^(heldout|train|all)$"),
    refresh: bool = Query(False, description="Ignore the 10-minute cache and re-run"),
) -> dict[str, Any]:
    return svc.run(db, split, refresh)
