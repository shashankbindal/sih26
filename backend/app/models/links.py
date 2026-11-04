from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import Bureau, BureauT, LinkStatus, LinkStatusT, RelationType, RelationTypeT


class CaseLink(Base):
    __tablename__ = "case_links"
    __table_args__ = (
        UniqueConstraint("case_a_id", "case_b_id", "version", name="uq_case_links_pair_version"),
        CheckConstraint("case_a_id < case_b_id", name="pair_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    case_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    case_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    relation: Mapped[RelationType] = mapped_column(RelationTypeT)
    score: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    features: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    status: Mapped[LinkStatus] = mapped_column(LinkStatusT, server_default=text("'SUGGESTED'"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaseLinkHistory(Base):
    """Immutable copy of every previous version of a link."""

    __tablename__ = "case_link_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    link_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_links.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    relation: Mapped[RelationType] = mapped_column(RelationTypeT)
    score: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    features: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    status: Mapped[LinkStatus] = mapped_column(LinkStatusT)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CoordinationThread(Base):
    __tablename__ = "coordination_threads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    link_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_links.id", ondelete="CASCADE"), index=True)
    lead_bureau: Mapped[Bureau | None] = mapped_column(BureauT)
    shared_next_action: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'OPEN'"))


class CoordinationMessage(Base):
    __tablename__ = "coordination_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("coordination_threads.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
