from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.errors import ApiError
from app.models.system import AuditLog
from app.models.users import User
from app.schemas.auth import DemoUser, LoginRequest, LoginResponse, UserOut
from app.services.auth import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@lru_cache
def _dummy_hash() -> str:
    """Verified against when the email is unknown, so timing does not reveal valid accounts."""
    return hash_password("not-a-real-password")


@router.get("/demo-users", response_model=list[DemoUser])
def demo_users(db: DbSession) -> list[DemoUser]:
    if not get_settings().demo_mode:
        raise ApiError(404, "NOT_FOUND", "Not found")
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.bureau, User.email))
    return [
        DemoUser(
            email=u.email,
            name=u.name,
            role=u.role,
            bureau=u.bureau,
            ro_code=u.ro_code,
            designation=u.designation,
        )
        for u in users
    ]


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: DbSession) -> LoginResponse:
    user = db.scalar(select(User).where(User.email == body.email.strip()))
    ok = verify_password(body.password, user.password_hash if user else _dummy_hash())
    if user is None or not user.is_active or not ok:
        raise ApiError(401, "INVALID_CREDENTIALS", "Invalid email or password")
    db.add(
        AuditLog(
            user_id=user.id,
            method="POST",
            path=request.url.path,
            entity="user",
            entity_id=str(user.id),
            summary="login",
        )
    )
    db.commit()
    token = create_access_token(str(user.id), user.role.value, user.bureau.value)
    return LoginResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
