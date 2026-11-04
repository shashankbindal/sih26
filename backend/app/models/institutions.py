from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Institution(Base):
    __tablename__ = "institutions"
    __table_args__ = (
        Index(
            "ix_institutions_name_norm_trgm",
            "name_norm",
            postgresql_using="gin",
            postgresql_ops={"name_norm": "gin_trgm_ops"},
        ),
        Index("ix_institutions_ro_code", "ro_code"),
        Index("ix_institutions_state_district", "state", "district"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    permanent_id: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    name_norm: Mapped[str] = mapped_column(Text)
    inst_type: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    district: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    pincode: Mapped[str | None] = mapped_column(CHAR(6))
    ro_code: Mapped[str | None] = mapped_column(ForeignKey("regional_offices.code"))
    email_domain: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(Text, server_default=text("'APPROVED'"))
    established_year: Mapped[int | None] = mapped_column(Integer)

    aliases: Mapped[list[InstitutionAlias]] = relationship(
        back_populates="institution", cascade="all, delete-orphan"
    )


class InstitutionAlias(Base):
    __tablename__ = "institution_aliases"
    __table_args__ = (
        UniqueConstraint("institution_id", "alias_norm", name="uq_institution_aliases_inst_norm"),
        Index(
            "ix_institution_aliases_alias_norm_trgm",
            "alias_norm",
            postgresql_using="gin",
            postgresql_ops={"alias_norm": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), index=True
    )
    alias_raw: Mapped[str] = mapped_column(Text)
    alias_norm: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, server_default=text("'SEED'"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    institution: Mapped[Institution] = relationship(back_populates="aliases")
