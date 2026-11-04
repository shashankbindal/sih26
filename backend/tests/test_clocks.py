from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.models.clocks import CaseClock
from app.models.enums import (
    Bureau,
    CaseCategory,
    CaseStatus,
    ClockState,
    ClockType,
    PendingStep,
    SourceChannel,
)
from app.services import clocks
from tests.conftest import make_case, make_institution

IST = timezone(timedelta(hours=5, minutes=30))


def clock(ctype, started, hours, **kw) -> CaseClock:
    return CaseClock(
        clock=ctype,
        started_at=started,
        due_at=started + timedelta(hours=hours),
        paused_total_seconds=kw.pop("paused_total_seconds", 0),
        **kw,
    )


def test_cpgrams_amber_at_71_percent():
    started = datetime(2026, 10, 1, 10, 0, tzinfo=IST)
    c = clock(ClockType.CPGRAMS_21D, started, 504)
    s = clocks.compute_state(c, datetime(2026, 10, 16, 10, 0, tzinfo=IST))
    assert s.state == ClockState.AMBER
    assert round(s.elapsed_ratio, 2) == 0.71
    assert s.label == "21-day · 6 days left"


def test_on_track_below_70_percent():
    started = datetime(2026, 10, 1, 10, 0, tzinfo=IST)
    s = clocks.compute_state(clock(ClockType.CPGRAMS_21D, started, 504), datetime(2026, 10, 10, 10, 0, tzinfo=IST))
    assert s.state == ClockState.ON_TRACK and s.label == "21-day · 12 days left"


def test_amber_boundary_exactly_70_percent():
    started = datetime(2026, 1, 1, tzinfo=UTC)
    now = started + timedelta(hours=504 * 0.7)
    assert clocks.compute_state(clock(ClockType.CPGRAMS_21D, started, 504), now).state == ClockState.AMBER
    just_before = now - timedelta(minutes=1)
    assert (
        clocks.compute_state(clock(ClockType.CPGRAMS_21D, started, 504), just_before).state == ClockState.ON_TRACK
    )


def test_breached_label_and_overdue():
    started = datetime(2026, 10, 1, 10, 0, tzinfo=IST)
    s = clocks.compute_state(clock(ClockType.CPGRAMS_21D, started, 504), datetime(2026, 10, 26, 10, 0, tzinfo=IST))
    assert s.state == ClockState.BREACHED and s.label == "21-day · overdue 4 days"
    assert s.overdue_seconds == 4 * 86400


def test_pause_shifts_due_by_three_days():
    started = datetime(2026, 10, 1, 10, 0, tzinfo=IST)
    c = clock(ClockType.CPGRAMS_21D, started, 504, paused_total_seconds=3 * 86400)
    now = datetime(2026, 10, 24, 10, 0, tzinfo=IST)  # past 22 Oct base due, before 25 Oct shifted due
    s = clocks.compute_state(c, now)
    assert s.due_at == datetime(2026, 10, 25, 10, 0, tzinfo=IST)
    assert s.state != ClockState.BREACHED and s.label.endswith("1 day left")
    base = clock(ClockType.CPGRAMS_21D, started, 504)
    assert clocks.compute_state(base, now).state == ClockState.BREACHED


def test_paused_state_and_running_pause_extends_due():
    started = datetime(2026, 10, 1, 10, 0, tzinfo=IST)
    c = clock(ClockType.CPGRAMS_21D, started, 504, paused_at=datetime(2026, 10, 10, 10, 0, tzinfo=IST))
    s = clocks.compute_state(c, datetime(2026, 10, 30, 10, 0, tzinfo=IST))
    assert s.state == ClockState.PAUSED and s.label == "21-day · paused"
    # 20 days paused so far -> due moved from 22 Oct to 11 Nov
    assert s.due_at == datetime(2026, 11, 11, 10, 0, tzinfo=IST)


def test_css_met_with_first_reply_at_70_hours():
    started = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
    c = clock(ClockType.CSS_72H, started, 72, met_at=started + timedelta(hours=70))
    s = clocks.compute_state(c, started + timedelta(days=10))
    assert s.state == ClockState.MET and s.label == "72-hour · met"


def test_css_hours_labels():
    started = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
    c = clock(ClockType.CSS_72H, started, 72)
    assert clocks.compute_state(c, started + timedelta(hours=60)).label == "72-hour · 12 h left"
    assert clocks.compute_state(c, started + timedelta(hours=77)).label == "72-hour · overdue 5 h"


def test_refund_breached_by_five_days():
    started = datetime(2026, 10, 20, 10, 0, tzinfo=IST)
    s = clocks.compute_state(clock(ClockType.INST_REFUND_7D, started, 168), datetime(2026, 11, 1, 10, 0, tzinfo=IST))
    assert s.state == ClockState.BREACHED and s.label == "Inst. 7-day · overdue 5 days"
    assert s.rule == "APH 2024-27 cl. 6.45" and s.long_label == "Institution's 7-day refund duty"


def test_met_late_is_still_met():
    started = datetime(2026, 10, 1, tzinfo=UTC)
    c = clock(ClockType.CPGRAMS_21D, started, 504, met_at=started + timedelta(days=24))
    s = clocks.compute_state(c, started + timedelta(days=30))
    assert s.state == ClockState.MET and "met late" in s.label


def test_policy_config_drives_labels_and_ratio(db):
    from app.models.system import PolicyConfig

    db.get(PolicyConfig, "clause_labels").value = {"refund": "Test clause 9.9"}
    db.get(PolicyConfig, "amber_ratio").value = 0.5
    db.commit()
    policy = clocks.load_policy(db)
    assert policy.amber_ratio == 0.5
    assert policy.rule(ClockType.INST_REFUND_7D) == "Test clause 9.9"
    assert policy.clause_labels["deposit"].startswith("APH 2024-27")  # default kept
    started = datetime(2026, 1, 1, tzinfo=UTC)
    s = clocks.compute_state(clock(ClockType.CPGRAMS_21D, started, 504), started + timedelta(days=11), policy)
    assert s.state == ClockState.AMBER


def test_start_clocks_for_case_rules(db):
    inst = make_institution(db)
    now = datetime(2026, 11, 1, tzinfo=UTC)
    cp = make_case(db, inst, channel=SourceChannel.CPGRAMS, category=CaseCategory.OTHER, received_at=now - timedelta(days=3))
    css = make_case(db, inst, channel=SourceChannel.CSS, category=CaseCategory.OTHER, received_at=now - timedelta(days=1))
    ref = make_case(
        db,
        inst,
        channel=SourceChannel.EMAIL,
        category=CaseCategory.FEE_REFUND,
        pending_step=PendingStep.INSTITUTION_ATR,
        pending_since=now - timedelta(days=12),
    )
    none = make_case(db, inst, channel=SourceChannel.EMAIL, category=CaseCategory.RAGGING)
    assert [c.clock for c in clocks.start_clocks_for_case(db, cp, now=now)] == [ClockType.CPGRAMS_21D]
    assert [c.clock for c in clocks.start_clocks_for_case(db, css, now=now)] == [ClockType.CSS_72H]
    created = clocks.start_clocks_for_case(db, ref, now=now)
    assert [c.clock for c in created] == [ClockType.INST_REFUND_7D]
    assert created[0].due_at == ref.pending_since + timedelta(days=7)
    assert clocks.start_clocks_for_case(db, none, now=now) == []
    assert clocks.start_clocks_for_case(db, cp, now=now) == []  # idempotent
    dup = clocks.start_clocks_for_case(db, none, now=now, linked_cpgrams_duplicate=True)
    assert [c.clock for c in dup] == [ClockType.CPGRAMS_21D]


def test_sync_pause_resume_and_met(db):
    inst = make_institution(db)
    t0 = datetime(2026, 10, 1, tzinfo=UTC)
    case = make_case(db, inst, Bureau.PGRC, channel=SourceChannel.CPGRAMS, received_at=t0, category=CaseCategory.OTHER)
    clocks.start_clocks_for_case(db, case, now=t0)
    case.status = CaseStatus.AWAITING_COMPLAINANT
    rows = clocks.sync_clocks_for_case(db, case, t0 + timedelta(days=2))
    assert rows[0].state == ClockState.PAUSED and rows[0].paused_at is not None
    case.status = CaseStatus.UNDER_PROCESS
    rows = clocks.sync_clocks_for_case(db, case, t0 + timedelta(days=5))
    assert rows[0].paused_at is None and rows[0].paused_total_seconds == 3 * 86400
    case.status = CaseStatus.DISPOSED
    case.disposed_at = t0 + timedelta(days=9)
    rows = clocks.sync_clocks_for_case(db, case, t0 + timedelta(days=9))
    assert rows[0].state == ClockState.MET and rows[0].met_at == case.disposed_at
