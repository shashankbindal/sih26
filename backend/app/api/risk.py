"""P2: advisory breach-risk score for a case (no PII in the response)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from app.deps import CurrentUser, DbSession
from app.schemas.reporting import RiskOut
from app.services import risk as svc

router = APIRouter(prefix="/cases", tags=["risk"])


@router.get("/{case_id}/risk", response_model=RiskOut)
def case_risk(case_id: uuid.UUID, db: DbSession, _user: CurrentUser) -> dict[str, Any]:
    case = svc.get_case_or_404(db, case_id)
    return svc.assess(db, case)
