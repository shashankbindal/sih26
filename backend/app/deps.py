"""FastAPI dependencies: current user, role guards.

    from app.deps import get_current_user, require_roles, CurrentUser, DbSession
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError
from app.models.enums import Role
from app.models.users import User
from app.services.auth import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if creds is None or not creds.credentials:
        raise ApiError(401, "UNAUTHORIZED", "Authentication required")
    claims = decode_access_token(creds.credentials)
    if not claims or "sub" not in claims:
        raise ApiError(401, "UNAUTHORIZED", "Invalid or expired token")
    try:
        uid = uuid.UUID(str(claims["sub"]))
    except ValueError:
        raise ApiError(401, "UNAUTHORIZED", "Invalid token subject") from None
    user = db.get(User, uid)
    if user is None or not user.is_active:
        raise ApiError(401, "UNAUTHORIZED", "User not found or inactive")
    return user


def require_roles(*roles: Role | str):
    """Dependency factory: `Depends(require_roles(Role.ADMIN, Role.BUREAU_HEAD))`."""
    allowed = {Role(r) for r in roles}

    def _guard(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise ApiError(
                403,
                "FORBIDDEN",
                "Your role is not permitted to perform this action",
                {"required_roles": sorted(r.value for r in allowed)},
            )
        return user

    return _guard


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
