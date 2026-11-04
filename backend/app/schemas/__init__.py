"""Pydantic v2 request/response schemas.

`CaseCreate` and `CaseCreateResult` are importable from here:
    from app.schemas import CaseCreate, CaseCreateResult
"""

from __future__ import annotations

from typing import Any

_INTAKE_EXPORTS = ("CaseCreate", "CaseCreateResult")


def __getattr__(name: str) -> Any:  # lazy: avoids import cycles at package import time
    if name in _INTAKE_EXPORTS:
        from app.schemas import intake

        return getattr(intake, name)
    raise AttributeError(f"module 'app.schemas' has no attribute {name!r}")
