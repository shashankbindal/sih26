"""Background jobs (APScheduler, in-process, one worker).

* clock evaluation, hourly: persists clock state changes; AMBER -> SLA_AMBER notification to the
  owner; BREACHED -> SLA_BREACH notification to the owner and bureau head(s), Passport ESCALATED
  (actor SYSTEM, payload {clock, overdue_by}); the case status moves to ESCALATED only for the
  CPGRAMS 21-day clock (other clocks just flag).  Idempotent: an event already recorded for the
  same clock is never repeated.
* relationship sweep, 02:00 IST (the CaseLink design section C) via app.services.links.run_sweep.

Disabled under pytest and when SCHEDULER_ENABLED=false.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.errors import ApiError
from app.models.cases import Case
from app.models.clocks import CaseClock
from app.models.enums import OPEN_STATUSES, CaseStatus, ClockState, ClockType, Role
from app.models.passport import PassportEntry
from app.models.system import Notification
from app.models.users import User
from app.services import clocks as clocks_svc
from app.services import passport as passport_svc

log = logging.getLogger("loksutra")
IST = ZoneInfo("Asia/Kolkata")
FIRST_CLOCK_RUN_SECONDS = 120

_scheduler: Any = None


def scheduler_enabled() -> bool:
    if os.environ.get("SCHEDULER_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return False
    return "pytest" not in sys.modules and "PYTEST_CURRENT_TEST" not in os.environ


def scheduler_status() -> dict[str, Any]:
    jobs = []
    if _scheduler is not None:
        jobs = [
            {"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None}
            for j in _scheduler.get_jobs()
        ]
    return {"enabled": scheduler_enabled(), "running": _scheduler is not None, "jobs": jobs}


# ------------------------------------------------------------------------------ clock evaluation
def _already_notified(session: Session, kind: str, case_id: Any, title: str) -> bool:
    return (
        session.scalar(
            select(Notification.id)
            .where(Notification.kind == kind, Notification.case_id == case_id, Notification.title == title)
            .limit(1)
        )
        is not None
    )


def _already_escalated(session: Session, case_id: Any, clock: str) -> bool:
    return (
        session.scalar(
            select(PassportEntry.id)
            .where(
                PassportEntry.case_id == case_id,
                PassportEntry.event == "ESCALATED",
                PassportEntry.payload["clock"].astext == clock,
            )
            .limit(1)
        )
        is not None
    )


def _notify(session: Session, case: Case, kind: str, title: str, body: str, recipients: list[User]) -> int:
    if _already_notified(session, kind, case.id, title):
        return 0
    targets: list[tuple[Any, Any]] = [(u.id, None) for u in recipients]
    if not targets:
        targets = [(None, case.owner_bureau)]  # bureau-addressed when no individual is known
    for user_id, bureau in targets:
        session.add(
            Notification(
                user_id=user_id,
                bureau=bureau,
                kind=kind,
                title=title,
                body=body,
                link_path=f"/cases/{case.id}",
                case_id=case.id,
                institution_id=case.institution_id,
            )
        )
    return len(targets)


def evaluate_clocks(session: Session, now: datetime | None = None) -> dict[str, int]:
    """Persist clock state transitions and fire the events in the policy-clock rules. Flushes only."""
    now = now or datetime.now(UTC)
    policy = clocks_svc.load_policy(session)
    heads: dict[Any, list[User]] = {}
    for u in session.scalars(select(User).where(User.role == Role.BUREAU_HEAD, User.is_active.is_(True))):
        heads.setdefault(u.bureau, []).append(u)
    stats = {"checked": 0, "changed": 0, "amber": 0, "breached": 0, "escalated": 0, "notifications": 0}
    pairs = session.execute(select(CaseClock, Case).join(Case, Case.id == CaseClock.case_id)).unique().all()
    for clk, case in pairs:
        stats["checked"] += 1
        status = clocks_svc.compute_state(clk, now, policy)
        if status.state == clk.state:
            continue
        previous = clk.state
        clk.state = status.state
        stats["changed"] += 1
        if case.status not in OPEN_STATUSES or clk.met_at is not None:
            continue
        ctype = ClockType(clk.clock)
        owner = [case.owner_officer] if case.owner_officer is not None else []
        if status.state == ClockState.AMBER and previous == ClockState.ON_TRACK:
            stats["amber"] += 1
            stats["notifications"] += _notify(
                session,
                case,
                "SLA_AMBER",
                f"{status.short_label} clock in amber: {case.display_id}",
                f"{status.long_label}: {status.label}. Rule: {status.rule}",
                owner,
            )
        elif status.state == ClockState.BREACHED:
            stats["breached"] += 1
            recipients = list(owner)
            for h in heads.get(case.owner_bureau, []):
                if all(h.id != r.id for r in recipients):
                    recipients.append(h)
            stats["notifications"] += _notify(
                session,
                case,
                "SLA_BREACH",
                f"{status.short_label} clock breached: {case.display_id}",
                f"{status.long_label}: {status.label}. Rule: {status.rule}",
                recipients,
            )
            if not _already_escalated(session, case.id, ctype.value):
                payload: dict[str, Any] = {
                    "clock": ctype.value,
                    "overdue_by": status.label.split("overdue ", 1)[-1],
                    "overdue_seconds": int(status.overdue_seconds),
                }
                if ctype == ClockType.CPGRAMS_21D and case.status != CaseStatus.ESCALATED:
                    payload["status_from"] = case.status.value
                    payload["status_to"] = CaseStatus.ESCALATED.value
                    case.status = CaseStatus.ESCALATED
                passport_svc.append_entry(
                    session,
                    event="ESCALATED",
                    case_id=case.id,
                    institution_id=case.institution_id,
                    actor=None,
                    payload=payload,
                    created_at=now,
                )
                clk.escalated_at = now
                stats["escalated"] += 1
    session.flush()
    return stats


def run_clock_job() -> None:
    session = SessionLocal()
    try:
        stats = evaluate_clocks(session)
        session.commit()
        log.info("clock evaluation %s", stats)
    except Exception as exc:  # noqa: BLE001 - a job must never kill the scheduler thread
        session.rollback()
        log.error("clock evaluation failed: %s", type(exc).__name__)
    finally:
        session.close()


def run_sweep_job() -> None:
    from app.services import admin_tools

    session = SessionLocal()
    try:
        result = admin_tools.run_sweep(session, None)
        session.commit()
        log.info("nightly sweep %s", result)
    except ApiError as exc:
        session.rollback()
        log.info("nightly sweep skipped: %s", exc.code)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        log.error("nightly sweep failed: %s", type(exc).__name__)
    finally:
        session.close()


# ------------------------------------------------------------------------------------ lifecycle
def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None or not scheduler_enabled():
        return
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    sched = BackgroundScheduler(timezone=IST, job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 600})
    sched.add_job(
        run_clock_job,
        IntervalTrigger(hours=1),
        id="clock_evaluation",
        next_run_time=datetime.now(IST) + timedelta(seconds=FIRST_CLOCK_RUN_SECONDS),
        replace_existing=True,
    )
    sched.add_job(run_sweep_job, CronTrigger(hour=2, minute=0, timezone=IST), id="nightly_sweep", replace_existing=True)
    sched.start()
    _scheduler = sched
    log.info("scheduler started")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
