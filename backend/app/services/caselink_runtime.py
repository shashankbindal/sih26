"""Glue between the database and the in-memory CaseLink engine.

* one `TfidfCharSimilarity` per process (lazy fit on first use, refit after imports / sweeps);
* a cached `InstitutionIndex`, rebuilt only when institutions or aliases change;
* helpers turning `Case` rows into engine `CaseRecord`s (PII-masked descriptions only).

The engine never touches the DB; this module never decides anything: it only prepares inputs.
"""

from __future__ import annotations

import re
import threading
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models.cases import Case, CaseSourceRef
from app.models.complainants import Complainant
from app.models.enums import OPEN_STATUSES, CaseStatus
from app.models.institutions import Institution, InstitutionAlias
from app.models.system import PolicyConfig
from app.models.users import User
from app.services.caselink import (
    AliasRecord,
    CaseRecord,
    InstitutionIndex,
    InstitutionRecord,
    TextSimilarity,
    TfidfCharSimilarity,
    Thresholds,
)
from app.services.normalise import mask_pii

MIN_CORPUS_FOR_SINGLETON = 8

_lock = threading.RLock()
_similarity = TfidfCharSimilarity()
_index_key: tuple[Any, ...] | None = None
_index: InstitutionIndex | None = None


def reset_runtime() -> None:
    """Forget the fitted similarity model and the institution index (tests, demo reset)."""
    global _similarity, _index_key, _index
    with _lock:
        _similarity = TfidfCharSimilarity()
        _index_key = None
        _index = None


# ------------------------------------------------------------------ thresholds
def load_thresholds(session: Session) -> Thresholds:
    row = session.get(PolicyConfig, "thresholds")
    cfg = row.value if row is not None and isinstance(row.value, dict) else None
    return Thresholds.from_policy(cfg)


# ------------------------------------------------------------------ institution index
def _institution_records(session: Session) -> list[InstitutionRecord]:
    rows = session.scalars(select(Institution).order_by(Institution.permanent_id)).all()
    return [
        InstitutionRecord(
            id=i.id,
            name=i.name,
            permanent_id=i.permanent_id,
            name_norm=i.name_norm,
            district=i.district,
            state=i.state,
            pincode=(i.pincode or "").strip() or None,
            email_domain=i.email_domain,
            inst_type=i.inst_type,
            ro_code=i.ro_code,
        )
        for i in rows
    ]


def _alias_records(session: Session) -> list[AliasRecord]:
    rows = session.scalars(select(InstitutionAlias).order_by(InstitutionAlias.created_at)).all()
    user_ids = {a.created_by for a in rows if a.created_by}
    names = (
        {u.id: u.name for u in session.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    )
    return [
        AliasRecord(
            institution_id=a.institution_id,
            alias_norm=a.alias_norm,
            alias_raw=a.alias_raw,
            source=a.source,
            confirmed_by=names.get(a.created_by) if a.created_by else None,
            confirmed_at=a.created_at if a.source == "CONFIRMED_MATCH" else None,
        )
        for a in rows
    ]


def _fingerprint(session: Session) -> tuple[Any, ...]:
    n_inst, max_inst = session.execute(
        select(func.count(Institution.id), func.max(cast(Institution.id, String)))
    ).one()
    n_alias, max_alias_at, max_alias = session.execute(
        select(
            func.count(InstitutionAlias.id),
            func.max(InstitutionAlias.created_at),
            func.max(cast(InstitutionAlias.id, String)),
        )
    ).one()
    return (n_inst, max_inst, n_alias, max_alias_at, max_alias)


def get_index(session: Session) -> InstitutionIndex:
    """Cached institution index; rebuilt when institutions or aliases were added."""
    global _index_key, _index
    key = _fingerprint(session)
    with _lock:
        if _index is None or key != _index_key:
            _index = InstitutionIndex(_institution_records(session), _alias_records(session))
            _index_key = key
        return _index


def invalidate_index() -> None:
    global _index_key
    with _lock:
        _index_key = None


# ------------------------------------------------------------------ similarity
def _corpus(session: Session) -> list[str]:
    rows = session.execute(select(Case.id, Case.subject, Case.description_norm)).all()
    out: list[str] = []
    for cid, subject, norm in rows:
        rec = CaseRecord(
            id=cid, institution_id=None, owner_bureau="PGRC", category="OTHER", status="RECEIVED",
            received_at=datetime.now(UTC), subject=subject or "", description_norm=norm or "",
        )
        out.append(rec.similarity_text())
    return out


def refit_similarity(session: Session) -> int:
    """Refit the process-wide TF-IDF model on every case text. Call after imports and sweeps."""
    global _similarity
    corpus = _corpus(session)
    with _lock:
        if len(corpus) >= MIN_CORPUS_FOR_SINGLETON:
            fresh = TfidfCharSimilarity()
            fresh.fit(corpus)
            _similarity = fresh
        else:
            _similarity = TfidfCharSimilarity()
    return len(corpus)


def get_similarity(session: Session) -> TextSimilarity:
    """The shared model (lazily fitted on the whole corpus). With a tiny corpus a throw-away,
    unfitted instance is returned so `detect()` fits on the pair pool itself."""
    with _lock:
        if _similarity.is_fitted:
            return _similarity
    refit_similarity(session)
    with _lock:
        if _similarity.is_fitted:
            return _similarity
    return TfidfCharSimilarity()


# ------------------------------------------------------------------ case records
def load_case_records(session: Session, cases: Sequence[Case]) -> list[CaseRecord]:
    """Engine records for `cases`. Descriptions are PII-masked (emails/phones/ids) so source
    reference strings stay searchable; the complainant is only touched through `party_hash`."""
    if not cases:
        return []
    ids = [c.id for c in cases]
    refs: dict[uuid.UUID, list[str]] = defaultdict(list)
    for ref in session.scalars(select(CaseSourceRef).where(CaseSourceRef.case_id.in_(ids))):
        refs[ref.case_id].append(ref.ref)
    comp_ids = {c.complainant_id for c in cases}
    hashes = dict(
        session.execute(
            select(Complainant.id, Complainant.party_hash).where(Complainant.id.in_(comp_ids))
        ).all()
    )
    return [
        record_from_case(c, refs=refs.get(c.id, []), party_hash=hashes.get(c.complainant_id)) for c in cases
    ]


_HEARING_RE = re.compile(r"hearing[^\d]{0,60}?(\d{1,2})[\s\-]+([A-Za-z]{3,9})\.?,?[\s\-]+(\d{4})", re.IGNORECASE)


def parse_hearing_at(pending_action: str | None) -> datetime | None:
    """The DB has no hearing column: hearing dates live in pending_action text, e.g.
    "Hearing scheduled 05 Nov 2026". Returns midday IST as UTC, or None."""
    if not pending_action:
        return None
    m = _HEARING_RE.search(pending_action)
    if not m:
        return None
    try:
        day = datetime.strptime(f"{int(m.group(1))} {m.group(2)[:3].title()} {m.group(3)}", "%d %b %Y")
    except ValueError:
        return None
    return day.replace(hour=6, minute=30, tzinfo=UTC)  # 12:00 IST


def record_from_case(case: Case, *, refs: Sequence[str] = (), party_hash: str | None = None) -> CaseRecord:
    all_refs = tuple(dict.fromkeys([*(r for r in refs if r), *([case.source_ref] if case.source_ref else [])]))
    inst = case.institution
    return CaseRecord(
        id=case.id,
        institution_id=case.institution_id,
        owner_bureau=case.owner_bureau.value,
        category=case.category.value,
        status=case.status.value,
        received_at=case.received_at,
        pending_step=case.pending_step.value,
        pending_action=case.pending_action,
        party_hash=party_hash,
        source_refs=all_refs,
        subject=case.subject or "",
        description=mask_pii(case.description),
        description_norm=case.description_norm or "",
        display_id=case.display_id,
        source_channel=case.source_channel.value,
        hearing_at=parse_hearing_at(case.pending_action),
        disposed_at=case.disposed_at,
        pending_since=case.pending_since,
        institution_permanent_id=inst.permanent_id if inst is not None else None,
    )


def pool_cases(session: Session, institution_id: uuid.UUID, *, exclude: uuid.UUID | None = None,
               now: datetime | None = None, lookback_days: float = 90.0) -> list[Case]:
    """Other cases on the institution that are open, or disposed within `lookback_days` (stage B)."""
    now = now or datetime.now(UTC)
    q = select(Case).where(
        Case.institution_id == institution_id,
        or_(
            Case.status.in_(OPEN_STATUSES),
            (Case.status == CaseStatus.DISPOSED) & (Case.disposed_at >= now - timedelta(days=lookback_days)),
        ),
    )
    if exclude is not None:
        q = q.where(Case.id != exclude)
    return list(session.scalars(q.order_by(Case.received_at)).unique().all())
