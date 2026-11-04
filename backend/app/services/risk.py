"""P2 breach-risk score for open cases (FR-29): Low / Medium / High with top factors.

A small GradientBoostingClassifier trained lazily on the cases already in the database.  Label:
a case with at least one policy clock counts as 1 if any clock was breached (or met late) and 0 if all
its clocks were met on time; open cases still inside their clocks have no outcome yet and are not used.
Features are static intake facts only (category, channel, bureau, pending step, language, text
length, linked matters, institution workload); the clock's own elapsed time is NOT a feature (it
would leak the label), it is reported as a separate, rule-based factor.

Advisory only: the score never changes a case, blocks an action or escalates anything.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.cases import Case
from app.models.clocks import CaseClock
from app.models.enums import (
    OPEN_STATUSES,
    CaseCategory,
    ClockState,
    PendingStep,
    RelationType,
    SourceChannel,
)
from app.models.links import CaseLink
from app.services import clocks as clocks_svc
from app.services.dashboard import ACTIVE_LINK_STATUSES

SEED = 26264
MIN_SAMPLES = 40
RETRAIN_SECONDS = 3600
CATEGORICAL: dict[str, list[str]] = {
    "category": [c.value for c in CaseCategory],
    "channel": [c.value for c in SourceChannel],
    "bureau": ["PGRC", "RB", "APPROVAL", "VIGILANCE", "RO"],
    "pending_step": [p.value for p in PendingStep],
}
NUMERIC = ["links", "inst_open", "text_words"]
GROUP_LABEL = {
    "category": "Category",
    "channel": "Channel",
    "bureau": "Owning bureau",
    "pending_step": "Pending step",
    "links": "Linked matters",
    "inst_open": "Open matters at the institution",
    "text_words": "Length of complaint text",
}

_lock = threading.Lock()
_model: dict[str, Any] = {}


def _columns() -> list[str]:
    cols = [f"{g}={v}" for g, vals in CATEGORICAL.items() for v in vals]
    return cols + NUMERIC


def _vector(f: dict[str, Any]) -> list[float]:
    row = [1.0 if f.get(g) == v else 0.0 for g, vals in CATEGORICAL.items() for v in vals]
    return row + [float(f.get(n, 0)) for n in NUMERIC]


def _features(
    case: Case, links: dict[Any, int], inst_open: dict[Any, int]
) -> dict[str, Any]:
    return {
        "category": case.category.value,
        "channel": case.source_channel.value,
        "bureau": case.owner_bureau.value,
        "pending_step": case.pending_step.value,
        "links": links.get(case.id, 0),
        "inst_open": max(0, inst_open.get(case.institution_id, 0) - (1 if case.status in OPEN_STATUSES else 0)),
        "text_words": len((case.description or "").split()),
    }


def _context(session: Session) -> tuple[dict[Any, int], dict[Any, int]]:
    links: dict[Any, int] = defaultdict(int)
    for a, b in session.execute(
        select(CaseLink.case_a_id, CaseLink.case_b_id).where(
            CaseLink.relation != RelationType.UNRELATED, CaseLink.status.in_(ACTIVE_LINK_STATUSES)
        )
    ):
        links[a] += 1
        links[b] += 1
    inst_open = dict(
        session.execute(
            select(Case.institution_id, func.count()).where(Case.status.in_(OPEN_STATUSES)).group_by(Case.institution_id)
        ).all()
    )
    return links, inst_open


def _is_late(clock: CaseClock, now: datetime, policy: clocks_svc.ClockPolicy) -> bool | None:
    st = clocks_svc.compute_state(clock, now, policy)
    if st.state == ClockState.BREACHED:
        return True
    if st.state == ClockState.MET:
        return st.seconds_left < 0
    return None  # still running: outcome unknown


def train(session: Session, now: datetime | None = None) -> dict[str, Any]:
    from sklearn.ensemble import GradientBoostingClassifier

    now = now or datetime.now(UTC)
    policy = clocks_svc.load_policy(session)
    links, inst_open = _context(session)
    clock_map: dict[Any, list[CaseClock]] = defaultdict(list)
    for c in session.scalars(select(CaseClock)):
        clock_map[c.case_id].append(c)
    xs: list[list[float]] = []
    ys: list[int] = []
    trained_cases = (
        session.scalars(select(Case).where(Case.id.in_(list(clock_map)))).unique() if clock_map else []
    )
    for case in trained_cases:
        outcomes = [_is_late(c, now, policy) for c in clock_map[case.id]]
        if any(o is True for o in outcomes):
            label = 1
        elif all(o is False for o in outcomes):
            label = 0
        else:
            continue  # still running: no outcome yet
        xs.append(_vector(_features(case, links, inst_open)))
        ys.append(label)
    state: dict[str, Any] = {"trained_at": time.monotonic(), "n": len(ys), "model": None, "positives": int(sum(ys))}
    if len(ys) >= MIN_SAMPLES and 0 < sum(ys) < len(ys):
        x = np.array(xs)
        model = GradientBoostingClassifier(n_estimators=60, max_depth=2, learning_rate=0.1, random_state=SEED)
        model.fit(x, np.array(ys))
        state["model"] = model
        state["baseline"] = np.median(x, axis=0)
    return state


def _get_model(session: Session) -> dict[str, Any]:
    with _lock:
        if not _model or time.monotonic() - _model["trained_at"] > RETRAIN_SECONDS:
            _model.clear()
            _model.update(train(session))
        return _model


def _level(p: float) -> str:
    return "Low" if p < 0.34 else "Medium" if p < 0.67 else "High"


def _value_label(group: str, f: dict[str, Any]) -> str:
    v = f.get(group)
    if group in ("channel", "bureau"):
        return f"{GROUP_LABEL[group]}: {str(v).replace('_', ' ')}"
    if group in CATEGORICAL:
        return f"{GROUP_LABEL[group]}: {str(v).replace('_', ' ').capitalize()}"
    if group == "text_words":
        return f"Complaint text length: {v} words"
    return f"{GROUP_LABEL[group]}: {v}"


def assess(session: Session, case: Case, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    base = {"case_id": case.id, "probability": None, "factors": [], "trained_on": 0, "note": None}
    if case.status not in OPEN_STATUSES:
        return {**base, "level": "Closed", "note": "Case is closed; no risk is computed."}
    policy = clocks_svc.load_policy(session)
    clocks = list(session.scalars(select(CaseClock).where(CaseClock.case_id == case.id)))
    if not clocks:
        return {**base, "level": "Not applicable", "note": "No policy clock applies to this case."}
    statuses = [clocks_svc.compute_state(c, now, policy) for c in clocks if c.met_at is None]
    factors: list[dict[str, str]] = []
    breached = [s for s in statuses if s.state == ClockState.BREACHED]
    amber = [s for s in statuses if s.state == ClockState.AMBER]
    for s in breached:
        factors.append({"factor": f"{s.short_label} clock already breached ({s.label})", "effect": "raises"})
    for s in amber:
        factors.append({"factor": f"{s.short_label} clock {round(s.elapsed_ratio * 100)}% elapsed", "effect": "raises"})
    state = _get_model(session)
    n = int(state["n"])
    model = state.get("model")
    if model is None:
        level = "High" if breached else "Unknown"
        note = "Not enough resolved cases with clocks to train the model yet."
        return {**base, "level": level, "factors": factors, "trained_on": n, "note": note}
    links, inst_open = _context(session)
    f = _features(case, links, inst_open)
    vec = np.array([_vector(f)])
    p = float(model.predict_proba(vec)[0][1])
    cols = _columns()
    baseline = state["baseline"]
    contribs: list[tuple[float, str]] = []
    for group in [*CATEGORICAL, *NUMERIC]:
        idx = [i for i, c in enumerate(cols) if c.split("=")[0] == group]
        alt = vec.copy()
        alt[0, idx] = baseline[idx]
        delta = p - float(model.predict_proba(alt)[0][1])
        if abs(delta) >= 0.02:
            contribs.append((delta, group))
    contribs.sort(key=lambda t: -abs(t[0]))
    for delta, group in contribs[:3]:
        factors.append({"factor": _value_label(group, f), "effect": "raises" if delta > 0 else "lowers"})
    level = "High" if breached else _level(p)
    return {
        **base,
        "level": level,
        "probability": round(p, 3),
        "factors": factors[:5],
        "trained_on": n,
        "note": "Advisory estimate from a small model trained on this synthetic dataset.",
    }


def reset_model() -> None:
    with _lock:
        _model.clear()


def get_case_or_404(session: Session, case_id: Any) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise ApiError(404, "NOT_FOUND", "Case not found")
    return case

