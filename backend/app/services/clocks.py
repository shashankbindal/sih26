"""Policy clocks. Three separate clocks; never one "SLA".

Public helpers:
    ensure_default_policy_config(session)        insert missing policy_config keys
    load_policy(session) -> ClockPolicy          durations, labels, clause text, amber ratio
    compute_state(clock, now, policy=None)       pure; returns ClockStatus
    start_clocks_for_case(session, case, ...)    create applicable case_clocks rows
    sync_clocks_for_case(session, case, now)     pause/resume/met transitions after a change
    clock_views(session, clocks, now)            ClockStatus list for API output
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cases import Case
from app.models.clocks import CaseClock
from app.models.enums import (
    CaseCategory,
    CaseStatus,
    ClockState,
    ClockType,
    PendingStep,
    SourceChannel,
)
from app.models.system import PolicyConfig

REFUND_CATEGORIES = (CaseCategory.FEE_REFUND, CaseCategory.CERTIFICATE_WITHHELD)
REFUND_STEPS = (PendingStep.INSTITUTION_ATR, PendingStep.REFUND_FOLLOWUP)

DEFAULT_CONFIG: dict[str, Any] = {
    "thresholds": {"inst_auto": 0.92, "inst_review": 0.75, "dup": 0.85, "related": 0.60},
    "clocks": {
        "CPGRAMS_21D": {
            "duration_hours": 504,
            "short_label": "21-day",
            "long_label": "CPGRAMS 21-day redress",
            "rule": "DARPG comprehensive guidelines, Aug 2024 (redress within 21 days)",
        },
        "CSS_72H": {
            "duration_hours": 72,
            "short_label": "72-hour",
            "long_label": "CSS 72-hour first reply",
            "rule": "AICTE Centralized Support System (reply within 72 hours)",
        },
        "INST_REFUND_7D": {
            "duration_hours": 168,
            "short_label": "Inst. 7-day",
            "long_label": "Institution's 7-day refund duty",
            "rule": None,  # filled from clause_labels.refund
            "clause_key": "refund",
        },
    },
    "clause_labels": {
        "refund": "APH 2024-27 cl. 6.45",
        "deposit": "APH 2024-27 · Security-deposit release procedure",
    },
    "lead_bureau_rules": {
        "FEE_REFUND": "PGRC",
        "CERTIFICATE_WITHHELD": "PGRC",
        "FACULTY_SHORTAGE": "RB",
        "INFRASTRUCTURE": "RB",
        "FAKE_APPROVAL_CLAIM": "VIGILANCE",
        "RAGGING": "PGRC",
    },
    "amber_ratio": 0.7,
}


def ensure_default_policy_config(session: Session) -> None:
    """Insert any missing policy_config keys with the documented defaults (flush only)."""
    existing = set(session.scalars(select(PolicyConfig.key)))
    for key, value in DEFAULT_CONFIG.items():
        if key not in existing:
            session.add(PolicyConfig(key=key, value=value))
    session.flush()


@dataclass(frozen=True)
class ClockPolicy:
    amber_ratio: float = 0.7
    clocks: dict[str, dict[str, Any]] = field(default_factory=lambda: DEFAULT_CONFIG["clocks"])
    clause_labels: dict[str, str] = field(default_factory=lambda: DEFAULT_CONFIG["clause_labels"])

    def duration(self, clock: ClockType | str) -> timedelta:
        key = ClockType(clock).value
        return timedelta(hours=float(self.clocks[key]["duration_hours"]))

    def short_label(self, clock: ClockType | str) -> str:
        return str(self.clocks[ClockType(clock).value]["short_label"])

    def long_label(self, clock: ClockType | str) -> str:
        cfg = self.clocks[ClockType(clock).value]
        return str(cfg.get("long_label") or cfg["short_label"])

    def rule(self, clock: ClockType | str) -> str:
        cfg = self.clocks[ClockType(clock).value]
        clause_key = cfg.get("clause_key")
        if clause_key and clause_key in self.clause_labels:
            return str(self.clause_labels[clause_key])
        return str(cfg.get("rule") or "")


DEFAULT_POLICY = ClockPolicy()


def load_policy(session: Session) -> ClockPolicy:
    """Read clocks/clause_labels/amber_ratio from policy_config (defaults for missing keys)."""
    rows = {r.key: r.value for r in session.scalars(select(PolicyConfig))}
    clocks = {**DEFAULT_CONFIG["clocks"]}
    for k, v in (rows.get("clocks") or {}).items():
        clocks[k] = {**clocks.get(k, {}), **v}
    clause_labels = {**DEFAULT_CONFIG["clause_labels"], **(rows.get("clause_labels") or {})}
    ratio = rows.get("amber_ratio", DEFAULT_CONFIG["amber_ratio"])
    if isinstance(ratio, dict):
        ratio = ratio.get("value", DEFAULT_CONFIG["amber_ratio"])
    return ClockPolicy(amber_ratio=float(ratio), clocks=clocks, clause_labels=clause_labels)


class ClockLike(Protocol):
    clock: Any
    started_at: datetime
    due_at: datetime
    paused_total_seconds: int | None
    paused_at: datetime | None
    met_at: datetime | None


@dataclass(frozen=True)
class ClockStatus:
    clock: ClockType
    state: ClockState
    started_at: datetime
    due_at: datetime  # effective due (base due + all pause time)
    elapsed_ratio: float
    seconds_left: float  # negative when overdue
    label: str  # "21-day · 6 days left"
    short_label: str  # "21-day"
    long_label: str  # "CPGRAMS 21-day redress"
    rule: str  # clause / rule source shown in the tooltip
    met_at: datetime | None = None
    paused_at: datetime | None = None

    @property
    def overdue_seconds(self) -> float:
        return max(0.0, -self.seconds_left) if self.state == ClockState.BREACHED else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "clock": self.clock.value,
            "state": self.state.value,
            "started_at": self.started_at,
            "due_at": self.due_at,
            "elapsed_ratio": round(self.elapsed_ratio, 4),
            "label": self.label,
            "short_label": self.short_label,
            "long_label": self.long_label,
            "rule": self.rule,
            "met_at": self.met_at,
            "paused_at": self.paused_at,
            "overdue_seconds": int(self.overdue_seconds),
        }


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _span(seconds: float, *, overdue: bool = False) -> str:
    """Human span. Days when >= 24 h, otherwise hours (min 1).
    Time left rounds up (never promise more time than there is); overdue rounds down."""
    seconds = abs(seconds)
    rnd = math.floor if overdue else math.ceil
    eps = 1e-6
    if seconds >= 86400:
        n = max(1, rnd(seconds / 86400 + (eps if overdue else -eps)))
        return f"{n} day" + ("" if n == 1 else "s")
    n = max(1, rnd(seconds / 3600 + (eps if overdue else -eps)))
    return f"{n} h"


def compute_state(clock: ClockLike, now: datetime, policy: ClockPolicy | None = None) -> ClockStatus:
    """Pure function: derive state and label of a clock at `now`.

    effective_due = due_at (= started_at + duration) + paused_total_seconds (+ the running pause).
    PAUSED while paused_at is set and the clock is not MET. MET if met_at is set.
    AMBER when active elapsed >= amber_ratio of the duration; BREACHED when now > effective_due.
    """
    policy = policy or DEFAULT_POLICY
    ctype = ClockType(getattr(clock.clock, "value", clock.clock))
    now = _utc(now)
    started = _utc(clock.started_at)
    base_due = _utc(clock.due_at)
    duration = (base_due - started).total_seconds()
    paused_total = float(clock.paused_total_seconds or 0)
    running_pause = 0.0
    if clock.paused_at is not None and clock.met_at is None:
        running_pause = max(0.0, (now - _utc(clock.paused_at)).total_seconds())
    total_paused = paused_total + running_pause
    effective_due = base_due + timedelta(seconds=total_paused)
    short = policy.short_label(ctype)

    def build(state: ClockState, left: float, ratio: float, text_: str) -> ClockStatus:
        return ClockStatus(
            clock=ctype,
            state=state,
            started_at=started,
            due_at=effective_due,
            elapsed_ratio=ratio,
            seconds_left=left,
            label=f"{short} · {text_}",
            short_label=short,
            long_label=policy.long_label(ctype),
            rule=policy.rule(ctype),
            met_at=_utc(clock.met_at) if clock.met_at else None,
            paused_at=_utc(clock.paused_at) if clock.paused_at else None,
        )

    if clock.met_at is not None:
        met = _utc(clock.met_at)
        late = (met - effective_due).total_seconds()
        text_ = "met" if late <= 0 else f"met late ({_span(late, overdue=True)})"
        return build(ClockState.MET, (effective_due - met).total_seconds(), 1.0, text_)

    active_elapsed = max(0.0, (now - started).total_seconds() - total_paused)
    ratio = active_elapsed / duration if duration > 0 else 1.0
    left = (effective_due - now).total_seconds()

    if clock.paused_at is not None:
        return build(ClockState.PAUSED, left, ratio, "paused")
    if left < 0:
        return build(ClockState.BREACHED, left, ratio, f"overdue {_span(left, overdue=True)}")
    state = ClockState.AMBER if ratio >= policy.amber_ratio else ClockState.ON_TRACK
    return build(state, left, ratio, f"{_span(left)} left")


def clock_views(
    session: Session, clocks: list[CaseClock], now: datetime | None = None
) -> list[ClockStatus]:
    policy = load_policy(session)
    now = now or datetime.now(UTC)
    return [compute_state(c, now, policy) for c in clocks]


def _make_clock(
    session: Session, case: Case, ctype: ClockType, started_at: datetime, policy: ClockPolicy
) -> CaseClock:
    row = CaseClock(
        case_id=case.id,
        clock=ctype,
        started_at=started_at,
        due_at=started_at + policy.duration(ctype),
        paused_total_seconds=0,
        state=ClockState.ON_TRACK,
    )
    session.add(row)
    return row


def start_clocks_for_case(
    session: Session,
    case: Case,
    *,
    now: datetime | None = None,
    policy: ClockPolicy | None = None,
    linked_cpgrams_duplicate: bool = False,
) -> list[CaseClock]:
    """Create the clocks that apply to `case` (idempotent). Returns the rows created.

    CPGRAMS_21D  channel CPGRAMS, or `linked_cpgrams_duplicate` (DUPLICATE of a CPGRAMS case)
    CSS_72H      channel CSS
    INST_REFUND_7D  category FEE_REFUND/CERTIFICATE_WITHHELD and pending_step INSTITUTION_ATR or
                 REFUND_FOLLOWUP; starts at pending_since (date AICTE forwarded), else `now`.
    """
    policy = policy or load_policy(session)
    now = now or datetime.now(UTC)
    existing = {
        c.clock for c in session.scalars(select(CaseClock).where(CaseClock.case_id == case.id))
    }
    created: list[CaseClock] = []
    if (
        case.source_channel == SourceChannel.CPGRAMS or linked_cpgrams_duplicate
    ) and ClockType.CPGRAMS_21D not in existing:
        created.append(_make_clock(session, case, ClockType.CPGRAMS_21D, case.received_at, policy))
    if case.source_channel == SourceChannel.CSS and ClockType.CSS_72H not in existing:
        created.append(_make_clock(session, case, ClockType.CSS_72H, case.received_at, policy))
    if (
        case.category in REFUND_CATEGORIES
        and case.pending_step in REFUND_STEPS
        and ClockType.INST_REFUND_7D not in existing
    ):
        created.append(
            _make_clock(session, case, ClockType.INST_REFUND_7D, case.pending_since or now, policy)
        )
    session.flush()
    return created


def sync_clocks_for_case(
    session: Session, case: Case, now: datetime | None = None, policy: ClockPolicy | None = None
) -> list[CaseClock]:
    """Apply transitions after a case change; call after status/pending_step edits.

    - CPGRAMS clock pauses while AWAITING_COMPLAINANT and resumes after (pause time accumulates).
    - CPGRAMS clock is MET when the case is DISPOSED.
    - CSS clock is MET at the first status change out of RECEIVED.
    - INST_REFUND clock is MET once pending_step leaves INSTITUTION_ATR/REFUND_FOLLOWUP (ATR in).
    - Starts INST_REFUND_7D if the case newly qualifies.
    Persists the recomputed `state` on each row; returns all clock rows of the case.
    """
    policy = policy or load_policy(session)
    now = now or datetime.now(UTC)
    start_clocks_for_case(session, case, now=now, policy=policy)
    rows = list(session.scalars(select(CaseClock).where(CaseClock.case_id == case.id)))
    for c in rows:
        if c.met_at is None:
            if c.clock == ClockType.CPGRAMS_21D:
                if case.status == CaseStatus.DISPOSED:
                    c.met_at = case.disposed_at or now
                elif case.status == CaseStatus.AWAITING_COMPLAINANT and c.paused_at is None:
                    c.paused_at = now
                elif case.status != CaseStatus.AWAITING_COMPLAINANT and c.paused_at is not None:
                    c.paused_total_seconds = (c.paused_total_seconds or 0) + int(
                        (now - c.paused_at).total_seconds()
                    )
                    c.paused_at = None
            elif c.clock == ClockType.CSS_72H:
                if case.status != CaseStatus.RECEIVED:
                    c.met_at = now
            elif c.clock == ClockType.INST_REFUND_7D and case.pending_step not in REFUND_STEPS:
                c.met_at = now
        c.state = compute_state(c, now, policy).state
    session.flush()
    return rows
