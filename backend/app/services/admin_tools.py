"""Admin / demo tools: relationship sweep adapter, demo reset, passport tamper demo.

The sweep lives in backend-workflows' `app.services.links.run_sweep(session, user)`; it is imported
lazily so this module works before that service exists (the endpoint then answers 501).
"""

from __future__ import annotations

import contextlib
import importlib
import json
import logging
import time
import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError
from app.models.cases import Case
from app.models.institutions import Institution
from app.models.passport import PassportEntry
from app.models.system import AuditLog, PolicyConfig
from app.models.users import User
from app.services import passport as passport_svc

log = logging.getLogger("loksutra")


def require_demo_mode() -> None:
    if not get_settings().demo_mode:
        raise ApiError(403, "DEMO_MODE_DISABLED", "This tool is only available when DEMO_MODE is enabled")


def seeded_at(session: Session) -> str | None:
    row = session.get(PolicyConfig, "seeded_at")
    if row is None or not isinstance(row.value, dict):
        return None
    return row.value.get("at")


def run_sweep(session: Session, user: User | None) -> dict[str, Any]:
    try:
        links = importlib.import_module("app.services.links")
        fn = links.run_sweep
    except (ImportError, AttributeError):
        raise ApiError(
            501,
            "NOT_IMPLEMENTED",
            "The relationship sweep service (app.services.links.run_sweep) is not available yet",
        ) from None
    result = fn(session, user)
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    elif hasattr(result, "__dict__") and not isinstance(result, dict):
        result = dict(vars(result))
    out = {
        "pairs_checked": int(result.get("pairs_checked", 0)),
        "new_links": int(result.get("new_links", 0)),
        "superseded": int(result.get("superseded", 0)),
    }
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            method="POST",
            path="/api/v1/admin/sweep",
            entity="sweep",
            summary=f"Relationship sweep: {json.dumps(out)}",
        )
    )
    return out


def tamper_demo(session: Session, user: User, case_id: uuid.UUID) -> dict[str, Any]:
    """Alter ONE passport payload in the middle of the case's chain so verification fails there."""
    require_demo_mode()
    case = session.get(Case, case_id)
    if case is None:
        raise ApiError(404, "NOT_FOUND", "Case not found")
    entries = session.execute(
        select(PassportEntry.id, PassportEntry.seq, PassportEntry.event)
        .where(PassportEntry.case_id == case_id)
        .order_by(PassportEntry.seq)
    ).all()
    if not entries:
        raise ApiError(409, "NO_PASSPORT", "This case has no Passport entries to alter")
    target = entries[len(entries) // 2]
    session.execute(text("SET LOCAL loksutra.tamper_demo = 'on'"))
    session.execute(
        text("UPDATE passport_entries SET payload = payload || CAST(:extra AS jsonb) WHERE id = :id"),
        {"extra": json.dumps({"altered_after_the_fact": True}), "id": target.id},
    )
    session.add(
        AuditLog(
            user_id=user.id,
            method="POST",
            path="/api/v1/admin/tamper-demo",
            entity="case",
            entity_id=str(case_id),
            summary=f"Tamper demo: altered payload of Passport entry seq {target.seq} ({target.event})",
        )
    )
    session.flush()
    verify = passport_svc.verify_chain(session, case_id=case_id)
    return {
        "case_id": str(case_id),
        "display_id": case.display_id,
        "seq": target.seq,
        "event": target.event,
        "entries": len(entries),
        "verify": verify,
    }


def _load_generate() -> Any:
    try:
        return importlib.import_module("app.seed.generate")
    except ImportError:
        raise ApiError(501, "NOT_IMPLEMENTED", "The seed generator (app.seed.generate) is not available yet") from None


def _reset_runtime_caches() -> None:
    """Drop in-process caches that were built from the data that was just replaced."""
    from app.services import evaluation, risk

    evaluation.clear_cache()
    risk.reset_model()
    with contextlib.suppress(ImportError, AttributeError):
        importlib.import_module("app.services.caselink_runtime").reset_runtime()


def reset_demo(user: User | None) -> dict[str, Any]:
    """Re-seed deterministically in-process (opens its own sessions; caller must have released its own)."""
    require_demo_mode()
    gen = _load_generate()
    started = time.perf_counter()
    gen.reset(verbose=False)
    _reset_runtime_caches()
    elapsed = round(time.perf_counter() - started, 1)
    from app.db import SessionLocal

    with SessionLocal() as s:
        counts = {
            "institutions": s.scalar(select(func.count()).select_from(Institution)) or 0,
            "cases": s.scalar(select(func.count()).select_from(Case)) or 0,
        }
        s.add(
            AuditLog(
                user_id=None,
                method="POST",
                path="/api/v1/admin/reset-demo",
                entity="demo",
                summary=f"Demo data reset in {elapsed}s (requested by admin)",
            )
        )
        s.commit()
        at = seeded_at(s)
    log.info("demo reset complete in %ss", elapsed)
    return {"status": "ok", "seconds": elapsed, "counts": counts, "seeded_at": at}
