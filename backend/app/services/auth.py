"""Password hashing (bcrypt) and JWT (python-jose, HS256)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings


def _pw_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]  # bcrypt ignores bytes past 72


def hash_password(password: str) -> str:
    rounds = get_settings().bcrypt_rounds
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_pw_bytes(password), password_hash.encode("ascii"))
    except ValueError:
        return False


def create_access_token(user_id: str, role: str, bureau: str, now: datetime | None = None) -> str:
    s = get_settings()
    now = now or datetime.now(UTC)
    claims = {
        "sub": user_id,
        "role": role,
        "bureau": bureau,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=s.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(claims, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except JWTError:
        return None
