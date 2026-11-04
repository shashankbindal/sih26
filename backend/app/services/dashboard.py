"""Oversight dashboard aggregates.

Everything here is aggregate-only: no complainant data is read.  Clock state is computed on read
with `services.clocks.compute_state`.  Filters use the same semantics as `GET /cases`
(`from`/`to` bound `received_at`; `ro_code` matches owner RO or the institution's RO), so the
numbers reconcile with the case register for identical filters.

Definitions:
    pending       open statuses (anything not DISPOSED / CLOSED_NO_ACTION)
    under_process UNDER_PROCESS, AWAITING_ATR, AWAITING_COMPLAINANT
    disposed      DISPOSED + CLOSED_NO_ACTION          (total = pending + disposed)
    overdue       open case with any clock BREACHED and not MET, with a per-clock breakdown
    open_alerts   active non-UNRELATED links whose two cases are both open and at least one is in scope
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.errors import ApiError
from app.models.cases import Case
from app.models.clocks import CaseClock
from app.models.enums import (
    CLOSED_STATUSES,
    OPEN_STATUSES,
    Bureau,
    CaseCategory,
    CaseStatus,
    ClockState,
    ClockType,
    LinkStatus,
    RelationType,
    Role,
)
from app.models.institutions import Institution
from app.models.links import CaseLink
from app.models.users import RegionalOffice, User
from app.services import clocks as clocks_svc

IST = ZoneInfo("Asia/Kolkata")
UNDER_PROCESS_STATUSES = (CaseStatus.UNDER_PROCESS, CaseStatus.AWAITING_ATR, CaseStatus.AWAITING_COMPLAINANT)
ACTIVE_LINK_STATUSES = (LinkStatus.SUGGESTED, LinkStatus.CONFIRMED, LinkStatus.DEFERRED)
BUREAU_ORDER = (Bureau.PGRC, Bureau.RB, Bureau.APPROVAL, Bureau.VIGILANCE, Bureau.RO)
AGEING_BUCKETS = ("0-21", "22-60", "61-180", "180+")


def parse_bound(value: str | None, *, end: bool) -> datetime | None:
    """ISO datetime, or a bare date (IST day start, or IST day end when `end`)."""
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip()
    try:
        if len(raw) == 10:
            d = date.fromisoformat(raw)
            t = time(23, 59, 59, 999999) if end else time(0, 0)
            return datetime.combine(d, t, tzinfo=IST).astimezone(UTC)
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(422, "VALIDATION_ERROR", f"Invalid date: {raw[:40]}") from None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


@dataclass(frozen=True)
class Filters:
    start: datetime | None = None
    end: datetime | None = None
    bureau: tuple[Bureau, ...] = ()
    ro_code: tuple[str, ...] = ()
    category: tuple[CaseCategory, ...] = ()
    status: tuple[CaseStatus, ...] = ()
    ro_forced: bool = False

    def conditions(self, *, dates: bool = True, status: bool = True) -> list[Any]:
        conds: list[Any] = []
        if dates and self.start:
            conds.append(Case.received_at >= self.start)
        if dates and self.end:
            conds.append(Case.received_at <= self.end)
        if self.bureau:
            conds.append(Case.owner_bureau.in_(self.bureau))
        if self.ro_code:
            conds.append(
                or_(
                    Case.owner_ro_code.in_(self.ro_code),
                    Case.institution_id.in_(select(Institution.id).where(Institution.ro_code.in_(self.ro_code))),
                )
            )
        if self.category:
            conds.append(Case.category.in_(self.category))
        if status and self.status:
            conds.append(Case.status.in_(self.status))
        return conds

    def echo(self) -> dict[str, Any]:
        return {
            "from": self.start.isoformat() if self.start else None,
            "to": self.end.isoformat() if self.end else None,
            "bureau": [b.value for b in self.bureau],
            "ro_code": list(self.ro_code),
            "category": [c.value for c in self.category],
            "status": [s.value for s in self.status],
            "ro_forced": self.ro_forced,
        }


def build_filters(
    user: User,
    *,
    start: str | None = None,
    end: str | None = None,
    bureau: list[Bureau] | None = None,
    ro_code: list[str] | None = None,
    category: list[CaseCategory] | None = None,
    status: list[CaseStatus] | None = None,
) -> Filters:
    """RO officers are always scoped to their own region (the UI chip is removable by heads/mgmt only)."""
    ros = tuple(ro_code or ())
    forced = False
    if user.role == Role.RO_OFFICER and user.ro_code:
        ros, forced = (user.ro_code,), True
    return Filters(
        start=parse_bound(start, end=False),
        end=parse_bound(end, end=True),
        bureau=tuple(bureau or ()),
        ro_code=ros,
        category=tuple(category or ()),
        status=tuple(status or ()),
        ro_forced=forced,
    )


# ---------------------------------------------------------------------------------------- clocks
@dataclass(frozen=True)
class ClockRow:
    case_id: uuid.UUID
    clock: ClockType
    state: ClockState
    is_open: bool


def clock_rows(session: Session, f: Filters, now: datetime) -> list[ClockRow]:
    """Live clock state for every clock of every in-scope case (one query, pure compute)."""
    policy = clocks_svc.load_policy(session)
    q = select(CaseClock, Case.status).join(Case, Case.id == CaseClock.case_id).where(*f.conditions())
    out: list[ClockRow] = []
    for clk, status in session.execute(q).all():
        st = clocks_svc.compute_state(clk, now, policy).state
        out.append(ClockRow(clk.case_id, ClockType(clk.clock), st, status in OPEN_STATUSES))
    return out


def breached_open_cases(rows: list[ClockRow]) -> set[uuid.UUID]:
    return {r.case_id for r in rows if r.is_open and r.state == ClockState.BREACHED}


# ------------------------------------------------------------------------------------------ KPIs
def open_alert_conditions(ca: Any, cb: Any) -> list[Any]:
    """Predicate for an "open coordination alert": an active, non-UNRELATED link whose two cases (aliased
    as `ca`, `cb`) are both open. Shared by the dashboard KPI and `GET /links?both_open=true` so they cannot drift."""
    return [
        ca.status.in_(OPEN_STATUSES),
        cb.status.in_(OPEN_STATUSES),
        CaseLink.relation != RelationType.UNRELATED,
        CaseLink.status.in_(ACTIVE_LINK_STATUSES),
    ]


def _open_alert_count(session: Session, f: Filters) -> int:
    ca, cb = aliased(Case), aliased(Case)
    scope = select(Case.id).where(*f.conditions())
    stmt = (
        select(func.count(CaseLink.id))
        .join(ca, ca.id == CaseLink.case_a_id)
        .join(cb, cb.id == CaseLink.case_b_id)
        .where(
            *open_alert_conditions(ca, cb),
            or_(CaseLink.case_a_id.in_(scope), CaseLink.case_b_id.in_(scope)),
        )
    )
    return int(session.scalar(stmt) or 0)


def _kpi_counts(session: Session, f: Filters, now: datetime) -> dict[str, Any]:
    by_status = dict(
        session.execute(select(Case.status, func.count()).where(*f.conditions()).group_by(Case.status)).all()
    )

    def n(statuses: tuple[CaseStatus, ...]) -> int:
        return sum(int(by_status.get(s, 0)) for s in statuses)

    rows = clock_rows(session, f, now)
    per_clock: dict[str, int] = {c.value: 0 for c in ClockType}
    seen: set[tuple[uuid.UUID, ClockType]] = set()
    for r in rows:
        if r.is_open and r.state == ClockState.BREACHED and (r.case_id, r.clock) not in seen:
            seen.add((r.case_id, r.clock))
            per_clock[r.clock.value] += 1
    return {
        "total": sum(int(v) for v in by_status.values()),
        "pending": n(OPEN_STATUSES),
        "under_process": n(UNDER_PROCESS_STATUSES),
        "disposed": n(CLOSED_STATUSES),
        "transferred": n((CaseStatus.TRANSFERRED,)),
        "escalated": n((CaseStatus.ESCALATED,)),
        "overdue": len(breached_open_cases(rows)),
        "overdue_by_clock": per_clock,
        "open_alerts": _open_alert_count(session, f),
    }


DELTA_KEYS = ("total", "pending", "under_process", "disposed", "transferred", "escalated", "overdue", "open_alerts")


def kpis(session: Session, f: Filters, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    cur = _kpi_counts(session, f, now)
    deltas: dict[str, Any] | None = None
    if f.start is not None:
        end = f.end or now
        span = end - f.start
        prev = replace(f, start=f.start - span, end=f.start - timedelta(microseconds=1))
        before = _kpi_counts(session, prev, now)
        deltas = {
            "previous_period": {"from": prev.start.isoformat(), "to": prev.end.isoformat()},  # type: ignore[union-attr]
            "vs_prev_period": {
                k: {
                    "previous": before[k],
                    "change": cur[k] - before[k],
                    "pct": round(100.0 * (cur[k] - before[k]) / before[k], 1) if before[k] else None,
                }
                for k in DELTA_KEYS
            },
        }
    return {
        **cur,
        "definitions": {
            "pending": [s.value for s in OPEN_STATUSES],
            "under_process": [s.value for s in UNDER_PROCESS_STATUSES],
            "disposed": [s.value for s in CLOSED_STATUSES],
            "transferred": [CaseStatus.TRANSFERRED.value],
            "escalated": [CaseStatus.ESCALATED.value],
        },
        "deltas": deltas,
        "filters": f.echo(),
        "as_of": now.isoformat(),
    }


# --------------------------------------------------------------------------------- breakdowns
def by_bureau(session: Session, f: Filters) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Case.owner_bureau, Case.status, func.count()).where(*f.conditions()).group_by(Case.owner_bureau, Case.status)
    ).all()
    table: dict[Bureau, dict[str, int]] = defaultdict(lambda: {s.value: 0 for s in CaseStatus})
    for b, s, c in rows:
        table[b][s.value] = int(c)
    out = []
    for b in [*BUREAU_ORDER, *(x for x in table if x not in BUREAU_ORDER)]:
        counts = table.get(b, {s.value: 0 for s in CaseStatus})
        out.append(
            {
                "bureau": b.value,
                **counts,
                "open": sum(v for k, v in counts.items() if CaseStatus(k) in OPEN_STATUSES),
                "total": sum(counts.values()),
            }
        )
    return out


def by_category(session: Session, f: Filters) -> list[dict[str, Any]]:
    is_open = Case.status.in_(OPEN_STATUSES)
    rows = session.execute(
        select(
            Case.category,
            func.count().filter(is_open),
            func.count().filter(Case.status.in_(CLOSED_STATUSES)),
        )
        .where(*f.conditions())
        .group_by(Case.category)
    ).all()
    out = [{"category": c.value, "open": int(o), "disposed": int(d)} for c, o, d in rows]
    out.sort(key=lambda r: (-r["open"], r["category"]))
    return out


def ageing(session: Session, f: Filters, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    r = Case.received_at
    c0, c1, c2 = now - timedelta(days=22), now - timedelta(days=61), now - timedelta(days=181)
    row = session.execute(
        select(
            func.count().filter(r > c0),
            func.count().filter(and_(r <= c0, r > c1)),
            func.count().filter(and_(r <= c1, r > c2)),
            func.count().filter(r <= c2),
        ).where(*f.conditions(), Case.status.in_(OPEN_STATUSES))
    ).one()
    return [{"bucket": b, "count": int(v)} for b, v in zip(AGEING_BUCKETS, row, strict=True)]


def _period_floor(dt: datetime, granularity: str) -> datetime:
    local = dt.astimezone(IST)
    if granularity == "week":
        local = local - timedelta(days=local.weekday())
        return local.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def _next_period(p: datetime, granularity: str) -> datetime:
    if granularity == "week":
        return p + timedelta(days=7)
    return p.replace(year=p.year + 1, month=1) if p.month == 12 else p.replace(month=p.month + 1)


def trend(session: Session, f: Filters, granularity: str = "month") -> list[dict[str, Any]]:
    g = "week" if granularity == "week" else "month"
    local = lambda col: func.timezone("Asia/Kolkata", col)  # noqa: E731
    recv_p = func.date_trunc(g, local(Case.received_at))
    received = dict(
        session.execute(select(recv_p, func.count()).where(*f.conditions()).group_by(recv_p)).all()
    )
    closed_at = func.coalesce(Case.disposed_at, Case.updated_at)
    disp_conds = f.conditions(dates=False)
    if f.start:
        disp_conds.append(closed_at >= f.start)
    if f.end:
        disp_conds.append(closed_at <= f.end)
    disp_p = func.date_trunc(g, local(closed_at))
    disposed = dict(
        session.execute(
            select(disp_p, func.count()).where(*disp_conds, Case.status.in_(CLOSED_STATUSES)).group_by(disp_p)
        ).all()
    )
    keys = sorted({*received, *disposed})
    if not keys:
        return []
    out = []
    p = keys[0]
    while p <= keys[-1]:
        out.append(
            {
                "period": p.strftime("%Y-%m") if g == "month" else p.strftime("%Y-%m-%d"),
                "received": int(received.get(p, 0)),
                "disposed": int(disposed.get(p, 0)),
            }
        )
        p = _next_period(p, g)
    return out


def _open_case_rows(session: Session, f: Filters, *cols: Any) -> list[Any]:
    return list(session.execute(select(Case.id, *cols).where(*f.conditions(), Case.status.in_(OPEN_STATUSES))).all())


def by_region(session: Session, f: Filters, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    region = func.coalesce(Case.owner_ro_code, Institution.ro_code)
    rows = list(
        session.execute(
            select(Case.id, region)
            .outerjoin(Institution, Institution.id == Case.institution_id)
            .where(*f.conditions(), Case.status.in_(OPEN_STATUSES))
        ).all()
    )
    breached = breached_open_cases(clock_rows(session, f, now))
    open_n: dict[str | None, int] = defaultdict(int)
    ovd_n: dict[str | None, int] = defaultdict(int)
    for cid, ro in rows:
        open_n[ro] += 1
        if cid in breached:
            ovd_n[ro] += 1
    ros = session.scalars(select(RegionalOffice).order_by(RegionalOffice.code)).all()
    wanted = set(f.ro_code)
    out = [
        {
            "ro_code": ro.code,
            "name": ro.name,
            "city": ro.city,
            "lat": float(ro.lat) if ro.lat is not None else None,
            "lng": float(ro.lng) if ro.lng is not None else None,
            "open": open_n.get(ro.code, 0),
            "overdue": ovd_n.get(ro.code, 0),
        }
        for ro in ros
        if not wanted or ro.code in wanted
    ]
    return out


def top_institutions(session: Session, f: Filters, limit: int = 10, now: datetime | None = None) -> list[dict[str, Any]]:
    """Institutions with the most open matters (a neutral count, not a ranking of merit or risk)."""
    now = now or datetime.now(UTC)
    rows = [
        (cid, iid)
        for cid, iid in _open_case_rows(session, f, Case.institution_id)
        if iid is not None
    ]
    breached = breached_open_cases(clock_rows(session, f, now))
    open_n: dict[uuid.UUID, int] = defaultdict(int)
    ovd_n: dict[uuid.UUID, int] = defaultdict(int)
    for cid, iid in rows:
        open_n[iid] += 1
        if cid in breached:
            ovd_n[iid] += 1
    insts = {
        i.id: i
        for i in session.scalars(select(Institution).where(Institution.id.in_(list(open_n) or [uuid.uuid4()])))
    }
    ranked = sorted(open_n, key=lambda i: (-open_n[i], -ovd_n[i], insts[i].name))[: max(1, limit)]
    alerts: dict[uuid.UUID, int] = defaultdict(int)
    if ranked:
        ca, cb = aliased(Case), aliased(Case)
        for iid, c in session.execute(
            select(ca.institution_id, func.count(CaseLink.id))
            .join(ca, ca.id == CaseLink.case_a_id)
            .join(cb, cb.id == CaseLink.case_b_id)
            .where(
                ca.institution_id.in_(ranked),
                ca.status.in_(OPEN_STATUSES),
                cb.status.in_(OPEN_STATUSES),
                CaseLink.relation != RelationType.UNRELATED,
                CaseLink.status.in_(ACTIVE_LINK_STATUSES),
            )
            .group_by(ca.institution_id)
        ):
            alerts[iid] = int(c)
    return [
        {
            "institution_id": str(i),
            "name": insts[i].name,
            "permanent_id": insts[i].permanent_id,
            "district": insts[i].district,
            "ro_code": insts[i].ro_code,
            "open": open_n[i],
            "overdue": ovd_n[i],
            "open_alerts": alerts.get(i, 0),
        }
        for i in ranked
    ]


def clocks_summary(session: Session, f: Filters, now: datetime | None = None) -> dict[str, Any]:
    """The three clocks, counted separately.  Closed cases only contribute MET clocks."""
    now = now or datetime.now(UTC)
    policy = clocks_svc.load_policy(session)
    out: dict[str, dict[str, Any]] = {
        c.value: {
            "on_track": 0,
            "amber": 0,
            "breached": 0,
            "paused": 0,
            "met": 0,
            "total": 0,
            "label": policy.short_label(c),
            "rule": policy.rule(c),
        }
        for c in ClockType
    }
    key = {
        ClockState.ON_TRACK: "on_track",
        ClockState.AMBER: "amber",
        ClockState.BREACHED: "breached",
        ClockState.PAUSED: "paused",
        ClockState.MET: "met",
    }
    for r in clock_rows(session, f, now):
        if not r.is_open and r.state != ClockState.MET:
            continue
        b = out[r.clock.value]
        b[key[r.state]] += 1
        b["total"] += 1
    return out

