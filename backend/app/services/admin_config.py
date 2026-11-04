"""policy_config read/validate/write used by the admin endpoints.

Keys: thresholds, clocks, clause_labels, lead_bureau_rules, amber_ratio.  Dict-valued keys
(thresholds, clocks, clause_labels) are merged onto the stored value; lead_bureau_rules and
amber_ratio are replaced.  Every change writes an audit_log row (no PII involved).
"""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.enums import Bureau, CaseCategory, ClockType
from app.models.system import AuditLog, PolicyConfig
from app.models.users import User
from app.services import clocks as clocks_svc
from app.services.caselink.types import Thresholds

PUBLIC_KEYS = ("thresholds", "clocks", "clause_labels", "amber_ratio")
ADMIN_KEYS = ("lead_bureau_rules",)
ALL_KEYS = PUBLIC_KEYS + ADMIN_KEYS
THRESHOLD_FIELDS = {f.name for f in fields(Thresholds)}
UNIT_RANGE = {"inst_auto", "inst_review", "dup", "dup_strict", "related", "near_twin_gap"}
ASSIGNABLE_BUREAUS = {b.value for b in Bureau if b != Bureau.ADMIN}


def _bad(message: str, **details: Any) -> ApiError:
    return ApiError(422, "INVALID_CONFIG", message, details)


def _num(v: Any, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise _bad(f"{name} must be a number")
    return float(v)


def _validate_thresholds(new: dict[str, Any], merged: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(new, dict):
        raise _bad("thresholds must be an object")
    for k, v in new.items():
        if k not in THRESHOLD_FIELDS:
            raise _bad(f"Unknown threshold '{k}'", allowed=sorted(THRESHOLD_FIELDS))
        x = _num(v, k)
        if k in UNIT_RANGE and not 0.0 <= x <= 1.0:
            raise _bad(f"{k} must be between 0 and 1")
        if x < 0:
            raise _bad(f"{k} must not be negative")
    if "inst_auto" in merged and "inst_review" in merged and not merged["inst_review"] < merged["inst_auto"]:
        raise _bad("inst_review must be lower than inst_auto")
    if "dup" in merged and "related" in merged and not merged["related"] < merged["dup"]:
        raise _bad("related must be lower than dup")
    return merged


def _validate_clocks(new: dict[str, Any], merged: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(new, dict):
        raise _bad("clocks must be an object keyed by clock type")
    valid = {c.value for c in ClockType}
    for key, cfg in new.items():
        if key not in valid:
            raise _bad(f"Unknown clock '{key}'", allowed=sorted(valid))
        if not isinstance(cfg, dict):
            raise _bad(f"clocks.{key} must be an object")
        for field, val in cfg.items():
            if field == "duration_hours":
                x = _num(val, f"{key}.duration_hours")
                if not 1 <= x <= 24 * 365:
                    raise _bad(f"{key}.duration_hours must be between 1 and 8760")
            elif field in {"short_label", "long_label"}:
                if not isinstance(val, str) or not val.strip() or len(val) > 80:
                    raise _bad(f"{key}.{field} must be a non-empty string (max 80 characters)")
            elif field in {"rule", "clause_key"}:
                if val is not None and (not isinstance(val, str) or len(val) > 300):
                    raise _bad(f"{key}.{field} must be a string (max 300 characters) or null")
            else:
                raise _bad(f"Unknown clock field '{field}'", clock=key)
    return merged


def _validate_clause_labels(new: dict[str, Any], merged: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(new, dict):
        raise _bad("clause_labels must be an object")
    for k, v in new.items():
        if not isinstance(v, str) or not v.strip() or len(v) > 300:
            raise _bad(f"clause_labels.{k} must be a non-empty string (max 300 characters)")
    return merged


def _validate_lead_rules(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _bad("lead_bureau_rules must be an object mapping category to bureau")
    cats = {c.value for c in CaseCategory}
    for k, v in value.items():
        if k not in cats:
            raise _bad(f"Unknown category '{k}'", allowed=sorted(cats))
        if v not in ASSIGNABLE_BUREAUS:
            raise _bad(f"Unknown bureau '{v}' for {k}", allowed=sorted(ASSIGNABLE_BUREAUS))
    return value


def _validate_amber(value: Any) -> float:
    x = _num(value, "amber_ratio")
    if not 0.1 <= x <= 0.99:
        raise _bad("amber_ratio must be between 0.1 and 0.99")
    return x


def get_config(session: Session, key: str) -> tuple[Any, datetime | None, Any]:
    if key not in ALL_KEYS:
        raise ApiError(404, "NOT_FOUND", f"Unknown config key '{key}'", {"allowed": list(ALL_KEYS)})
    row = session.get(PolicyConfig, key)
    if row is None:
        clocks_svc.ensure_default_policy_config(session)
        row = session.get(PolicyConfig, key)
    value = row.value if row else clocks_svc.DEFAULT_CONFIG.get(key)
    return value, (row.updated_at if row else None), (row.updated_by if row else None)


def public_config(session: Session) -> dict[str, Any]:
    clocks_svc.ensure_default_policy_config(session)
    rows = {r.key: r.value for r in session.scalars(select(PolicyConfig).where(PolicyConfig.key.in_(PUBLIC_KEYS)))}
    return {k: rows.get(k, clocks_svc.DEFAULT_CONFIG[k]) for k in PUBLIC_KEYS}


def _summary(key: str, old: Any, new: Any) -> str:
    if isinstance(new, dict) and isinstance(old, dict):
        changed = sorted(k for k in new if old.get(k) != new[k])
        removed = sorted(k for k in old if k not in new)
        parts = [f"{k}: {old.get(k)!r} -> {new[k]!r}" for k in changed][:6]
        if removed:
            parts.append("removed " + ", ".join(removed))
        return f"Config '{key}' changed ({'; '.join(parts) or 'no effective change'})"[:900]
    return f"Config '{key}' changed ({old!r} -> {new!r})"[:900]


def put_config(session: Session, user: User, key: str, value: Any, *, path: str) -> tuple[Any, PolicyConfig]:
    old, _, _ = get_config(session, key)
    if key == "thresholds":
        merged = _validate_thresholds(value, {**(old or {}), **value} if isinstance(value, dict) else {})
    elif key == "clocks":
        merged = {k: dict(v) for k, v in (old or {}).items()}
        if isinstance(value, dict):
            for ck, cfg in value.items():
                merged[ck] = {**merged.get(ck, {}), **(cfg if isinstance(cfg, dict) else {})}
        merged = _validate_clocks(value, merged)
    elif key == "clause_labels":
        merged = _validate_clause_labels(value, {**(old or {}), **value} if isinstance(value, dict) else {})
    elif key == "lead_bureau_rules":
        merged = _validate_lead_rules(value)
    else:
        merged = _validate_amber(value)
    row = session.get(PolicyConfig, key)
    if row is None:
        row = PolicyConfig(key=key, value=merged, updated_by=user.id)
        session.add(row)
    else:
        row.value = merged
        row.updated_by = user.id
    session.add(
        AuditLog(
            user_id=user.id,
            method="PUT",
            path=path,
            entity="policy_config",
            entity_id=key,
            summary=_summary(key, old, merged),
        )
    )
    session.flush()
    session.refresh(row)
    return merged, row
