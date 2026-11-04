from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import Bureau, BureauT, Role, RoleT


class RegionalOffice(Base):
    __tablename__ = "regional_offices"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[float | None] = mapped_column(Numeric(9, 6))
    states: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    name: Mapped[str] = mapped_column(Text)
    designation: Mapped[str | None] = mapped_column(Text)
    role: Mapped[Role] = mapped_column(RoleT)
    bureau: Mapped[Bureau] = mapped_column(BureauT)
    ro_code: Mapped[str | None] = mapped_column(ForeignKey("regional_offices.code"))
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
