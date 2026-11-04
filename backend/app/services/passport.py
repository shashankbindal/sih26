"""Case Passport: hash-chained, append-only event log.

Public helpers:
    compute_hash(prev_hash, *, case_id, institution_id, seq, event, actor_id, actor_bureau,
                 payload, attachment_name, created_at) -> str
    append_entry(session, *, event, case_id=None, institution_id=None, chain_key=None,
                 actor=None, actor_id=None, actor_bureau=None, payload=None,
                 attachment_name=None, created_at=None) -> PassportEntry
    verify_chain(session, *, case_id=None, chain_key=None) -> dict
    list_entries(session, *, case_id=None, chain_key=None) -> list[PassportEntry]

Chains: one per case (`case_id`), and one per institution action (`case_id=None`,
`chain_key="action:<institution_action_id>"`, stored in payload.chain_key).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.enums import Bureau
from app.models.passport import PassportEntry
from app.models.users import User

GENESIS_HASH = "0" * 64


def iso_ms(dt: datetime) -> str:
    """ISO 8601 UTC with millisecond precision, e.g. 2026-11-01T09:42:11.123Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def truncate_ms(dt: datetime) -> datetime:
    """Truncate to millisecond precision so the stored value equals the hashed value."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=(dt.microsecond // 1000) * 1000)


def _s(value: Any) -> str | None:
    return None if value is None else str(value)


def json_safe(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Round-trip through JSON so what we hash is exactly what jsonb stores and returns."""
    return json.loads(json.dumps(payload or {}, default=str, ensure_ascii=False))


def canonical_json(
    *,
    case_id: Any,
    institution_id: Any,
    seq: int,
    event: str,
    actor_id: Any,
    actor_bureau: Any,
    payload: dict[str, Any],
    attachment_name: str | None,
    created_at: datetime,
) -> str:
    return json.dumps(
        {
            "case_id": _s(case_id),
            "institution_id": _s(institution_id),
            "seq": int(seq),
            "event": event,
            "actor_id": _s(actor_id),
            "actor_bureau": _s(getattr(actor_bureau, "value", actor_bureau)),
            "payload": payload,
            "attachment_name": attachment_name,
            "created_at": iso_ms(created_at),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def compute_hash(
    prev_hash: str,
    *,
    case_id: Any,
    institution_id: Any,
    seq: int,
    event: str,
    actor_id: Any,
    actor_bureau: Any,
    payload: dict[str, Any],
    attachment_name: str | None,
    created_at: datetime,
) -> str:
    canonical = canonical_json(
        case_id=case_id,
        institution_id=institution_id,
        seq=seq,
        event=event,
        actor_id=actor_id,
        actor_bureau=actor_bureau,
        payload=json_safe(payload),
        attachment_name=attachment_name,
        created_at=created_at,
    )
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


def _chain_filter(case_id: uuid.UUID | None, chain_key: str | None):
    if case_id is not None:
        return PassportEntry.case_id == case_id
    if chain_key is not None:
        return (PassportEntry.case_id.is_(None)) & (PassportEntry.payload["chain_key"].astext == chain_key)
    raise ValueError("either case_id or chain_key is required")


def append_entry(
    session: Session,
    *,
    event: str,
    case_id: uuid.UUID | None = None,
    institution_id: uuid.UUID | None = None,
    chain_key: str | None = None,
    actor: User | None = None,
    actor_id: uuid.UUID | None = None,
    actor_bureau: Bureau | str | None = None,
    payload: dict[str, Any] | None = None,
    attachment_name: str | None = None,
    created_at: datetime | None = None,
) -> PassportEntry:
    """Append one entry to a chain. Flushes, never commits (caller owns the transaction).

    Locks the chain tail (SELECT ... FOR UPDATE plus a transaction advisory lock so the very
    first insert of a chain is serialised too). `actor=None` and `actor_id=None` means SYSTEM.
    `created_at` may be passed by the seed generator for backdated history; it must be
    non-decreasing within a chain (not enforced).
    """
    if case_id is None and chain_key is None:
        raise ValueError("append_entry needs case_id or chain_key")
    if actor is not None:
        actor_id = actor_id or actor.id
        actor_bureau = actor_bureau or actor.bureau
    body = json_safe(payload)
    if case_id is None:
        body["chain_key"] = chain_key
    lock_key = str(case_id) if case_id is not None else str(chain_key)
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": lock_key})

    tail = session.execute(
        select(PassportEntry.seq, PassportEntry.hash)
        .where(_chain_filter(case_id, chain_key))
        .order_by(PassportEntry.seq.desc())
        .limit(1)
        .with_for_update()
    ).first()
    seq = (tail.seq + 1) if tail else 1
    prev_hash = tail.hash if tail else GENESIS_HASH

    ts = truncate_ms(created_at or datetime.now(UTC))
    bureau_val = getattr(actor_bureau, "value", actor_bureau)
    digest = compute_hash(
        prev_hash,
        case_id=case_id,
        institution_id=institution_id,
        seq=seq,
        event=event,
        actor_id=actor_id,
        actor_bureau=bureau_val,
        payload=body,
        attachment_name=attachment_name,
        created_at=ts,
    )
    entry = PassportEntry(
        case_id=case_id,
        institution_id=institution_id,
        seq=seq,
        event=event,
        actor_id=actor_id,
        actor_bureau=Bureau(bureau_val) if bureau_val else None,
        payload=body,
        attachment_name=attachment_name,
        created_at=ts,
        prev_hash=prev_hash,
        hash=digest,
    )
    session.add(entry)
    session.flush()
    return entry


def list_entries(
    session: Session, *, case_id: uuid.UUID | None = None, chain_key: str | None = None
) -> list[PassportEntry]:
    return list(
        session.scalars(
            select(PassportEntry).where(_chain_filter(case_id, chain_key)).order_by(PassportEntry.seq)
        )
    )


def verify_chain(
    session: Session, *, case_id: uuid.UUID | None = None, chain_key: str | None = None
) -> dict[str, Any]:
    """Walk the chain in seq order; return {ok, count, first_bad_seq, checked_at}.

    A chain is bad at the first entry whose seq is not contiguous, whose prev_hash does not
    equal the previous entry's hash, or whose recomputed hash differs from the stored one.
    """
    entries = list_entries(session, case_id=case_id, chain_key=chain_key)
    first_bad: int | None = None
    prev = GENESIS_HASH
    for expected_seq, e in enumerate(entries, start=1):
        recomputed = compute_hash(
            e.prev_hash,
            case_id=e.case_id,
            institution_id=e.institution_id,
            seq=e.seq,
            event=e.event,
            actor_id=e.actor_id,
            actor_bureau=e.actor_bureau,
            payload=e.payload,
            attachment_name=e.attachment_name,
            created_at=e.created_at,
        )
        if e.seq != expected_seq or e.prev_hash != prev or recomputed != e.hash:
            first_bad = e.seq
            break
        prev = e.hash
    return {
        "ok": first_bad is None,
        "count": len(entries),
        "first_bad_seq": first_bad,
        "checked_at": datetime.now(UTC),
    }
