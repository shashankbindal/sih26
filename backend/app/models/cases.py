from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Sequence,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.complainants import Complainant
from app.models.enums import (
    Bureau,
    BureauT,
    CaseCategory,
    CaseCategoryT,
    CaseStatus,
    CaseStatusT,
    MatchStatus,
    MatchStatusT,
    PendingStep,
    PendingStepT,
    SourceChannel,
    SourceChannelT,
)
from app.models.institutions import Institution
from app.models.users import User

display_id_seq = Sequence("display_id_seq", metadata=Base.metadata)

DISPLAY_ID_DEFAULT = text(
    "'LS-' || to_char(now() AT TIME ZONE 'UTC', 'YYYY') || '-' "
    "|| lpad(nextval('display_id_seq')::text, 6, '0')"
)


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        Index("ix_cases_institution_status", "institution_id", "status"),
        Index("ix_cases_owner_bureau_status", "owner_bureau", "status"),
        Index("ix_cases_received_at", "received_at"),
        Index(
            "ix_cases_description_norm_trgm",
            "description_norm",
            postgresql_using="gin",
            postgresql_ops={"description_norm": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    display_id: Mapped[str] = mapped_column(Text, unique=True, server_default=DISPLAY_ID_DEFAULT)
    source_channel: Mapped[SourceChannel] = mapped_column(SourceChannelT)
    source_ref: Mapped[str | None] = mapped_column(Text, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    institution_text_raw: Mapped[str | None] = mapped_column(Text)
    permanent_id_raw: Mapped[str | None] = mapped_column(Text)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institutions.id"))
    institution_match_status: Mapped[MatchStatus] = mapped_column(
        MatchStatusT, server_default=text("'UNRESOLVED'")
    )
    institution_match_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    complainant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("complainants.id"))
    category: Mapped[CaseCategory] = mapped_column(CaseCategoryT, server_default=text("'OTHER'"))
    category_suggested: Mapped[CaseCategory | None] = mapped_column(CaseCategoryT)
    subject: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    description_norm: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(Text)
    owner_bureau: Mapped[Bureau] = mapped_column(BureauT)
    owner_ro_code: Mapped[str | None] = mapped_column(ForeignKey("regional_offices.code"))
    owner_officer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[CaseStatus] = mapped_column(CaseStatusT, server_default=text("'RECEIVED'"))
    pending_step: Mapped[PendingStep] = mapped_column(PendingStepT, server_default=text("'NONE'"))
    pending_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_action: Mapped[str | None] = mapped_column(Text)
    disposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_seed_label: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    institution: Mapped[Institution | None] = relationship(lazy="joined")
    # lazy="select": PII is only loaded when privacy.mask_case decides the viewer may see it
    complainant: Mapped[Complainant] = relationship(lazy="select")
    owner_officer: Mapped[User | None] = relationship(lazy="joined")
    source_refs: Mapped[list[CaseSourceRef]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class CaseSourceRef(Base):
    __tablename__ = "case_source_refs"

    channel: Mapped[SourceChannel] = mapped_column(SourceChannelT, primary_key=True)
    ref: Mapped[str] = mapped_column(Text, primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )

    case: Mapped[Case] = relationship(back_populates="source_refs")


class InstitutionMatchCandidate(Base):
    __tablename__ = "institution_match_candidates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"))
    rank: Mapped[int] = mapped_column()
    score: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    features: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    status: Mapped[MatchStatus] = mapped_column(MatchStatusT, server_default=text("'NEEDS_REVIEW'"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)

    institution: Mapped[Institution] = relationship(lazy="joined")
