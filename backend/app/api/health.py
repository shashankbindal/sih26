from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import select, text

from app.config import get_settings
from app.deps import DbSession
from app.models.system import PolicyConfig
from app.schemas.health import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(db: DbSession) -> HealthOut:
    """Liveness + DB check. `seeded_at` comes from policy_config key `seeded_at`
    ({"at": ISO timestamp}, written by the seed generator); null when unseeded."""
    db_state = "ok"
    seeded_at: datetime | None = None
    try:
        db.execute(text("SELECT 1"))
        row = db.scalar(select(PolicyConfig.value).where(PolicyConfig.key == "seeded_at"))
        raw = row.get("at") if isinstance(row, dict) else row
        if isinstance(raw, str):
            seeded_at = datetime.fromisoformat(raw)
    except Exception:  # noqa: BLE001 - health must answer even if the DB is down
        db.rollback()
        db_state = "error"
    return HealthOut(
        status="ok" if db_state == "ok" else "degraded",
        db=db_state,
        version=get_settings().app_version,
        seeded_at=seeded_at,
    )
