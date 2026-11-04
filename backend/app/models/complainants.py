from __future__ import annotations

import uuid

from sqlalchemy import Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Complainant(Base):
    """PII lives only here. Never log these fields; read via services/privacy.py."""

    __tablename__ = "complainants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    party_hash: Mapped[str | None] = mapped_column(Text, index=True)
    party_type: Mapped[str] = mapped_column(Text, server_default=text("'OTHER'"))
