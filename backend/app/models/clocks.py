from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import ClockState, ClockStateT, ClockType, ClockTypeT


class CaseClock(Base):
    """One row per (case, clock). `due_at` is the base due (started_at + duration);
    effective due adds `paused_total_seconds` (see services/clocks.py)."""

    __tablename__ = "case_clocks"
    __table_args__ = (UniqueConstraint("case_id", "clock", name="uq_case_clocks_case_clock"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    clock: Mapped[ClockType] = mapped_column(ClockTypeT)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paused_total_seconds: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    met_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[ClockState] = mapped_column(ClockStateT, server_default=text("'ON_TRACK'"))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
