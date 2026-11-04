from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import (
    Bureau,
    BureauT,
    ClearanceResponse,
    ClearanceResponseT,
    InstActionType,
    InstActionTypeT,
)


class InstitutionAction(Base):
    __tablename__ = "institution_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    action_type: Mapped[InstActionType] = mapped_column(InstActionTypeT)
    initiated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    initiated_bureau: Mapped[Bureau] = mapped_column(BureauT)
    # CHECK_SHOWN | ACKNOWLEDGED | PROCEEDED | ON_HOLD | WITHDRAWN
    status: Mapped[str] = mapped_column(Text, server_default=text("'CHECK_SHOWN'"))
    snapshot: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    open_matter_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ack_remark: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClearanceRequest(Base):
    __tablename__ = "clearance_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    institution_action_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institution_actions.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"))
    target_bureau: Mapped[Bureau] = mapped_column(BureauT)
    step_order: Mapped[int] = mapped_column(Integer)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    response: Mapped[ClearanceResponse] = mapped_column(
        ClearanceResponseT, server_default=text("'PENDING'")
    )
    responded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remarks: Mapped[str | None] = mapped_column(Text)
