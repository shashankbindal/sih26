from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CHAR, BigInteger, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import Bureau, BureauT


class PassportEntry(Base):
    """Hash-chained, append-only. Write ONLY via services/passport.append_entry."""

    __tablename__ = "passport_entries"
    __table_args__ = (
        Index("uq_passport_case_seq", "case_id", "seq", unique=True, postgresql_where=text("case_id IS NOT NULL")),
        Index(
            "uq_passport_chain_key_seq",
            text("(payload->>'chain_key')"),
            "seq",
            unique=True,
            postgresql_where=text("case_id IS NULL"),
        ),
        Index("ix_passport_institution", "institution_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"))
    institution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institutions.id"))
    seq: Mapped[int] = mapped_column(Integer)
    event: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_bureau: Mapped[Bureau | None] = mapped_column(BureauT)
    payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    attachment_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    prev_hash: Mapped[str] = mapped_column(CHAR(64))
    hash: Mapped[str] = mapped_column(CHAR(64))
