from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.models.enums import Bureau, Role


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    designation: str | None = None
    role: Role
    bureau: Bureau
    ro_code: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DemoUser(BaseModel):
    email: str
    name: str
    role: Role
    bureau: Bureau
    ro_code: str | None = None
    designation: str | None = None
