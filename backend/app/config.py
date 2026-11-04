"""Application settings (pydantic-settings). Reads env vars and backend/.env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DB_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/loksutra"


def normalise_database_url(url: str) -> str:
    """Rewrite postgres:// and postgresql:// to the psycopg 3 SQLAlchemy dialect."""
    url = url.strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = DEFAULT_DB_URL
    jwt_secret: str = "change-me-dev-secret-at-least-32-characters-long"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    cors_origins: str = "http://localhost:5173"
    demo_mode: bool = False
    tz_display: str = "Asia/Kolkata"
    bcrypt_rounds: int = 12
    app_version: str = "0.1.0"

    @field_validator("database_url")
    @classmethod
    def _fix_url(cls, v: str) -> str:
        return normalise_database_url(v)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
