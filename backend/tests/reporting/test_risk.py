from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.models.clocks import CaseClock
from app.models.enums import Bureau, CaseCategory, CaseStatus, ClockState, Role, SourceChannel
from app.services import risk
from tests.conftest import auth_headers, make_case, make_institution, make_user
from tests.reporting._world import NOW

API = "/api/v1"


def _history(db, inst, n=60):
    for i in range(n):
        late = i % 2 == 0
        cat = CaseCategory.FEE_REFUND if late else CaseCategory.SCHOLARSHIP
        c = make_case(
            db, inst, Bureau.PGRC, channel=SourceChannel.CPGRAMS, category=cat, status=CaseStatus.DISPOSED,
            received_at=NOW - timedelta(days=100 + i), start_clocks=True,
        )
        clk = db.scalar(select(CaseClock).where(CaseClock.case_id == c.id))
        clk.met_at = clk.started_at + timedelta(days=30 if late else 10)
        clk.state = ClockState.MET
    db.commit()


def test_risk_levels_and_factors(db, client):
    risk.reset_model()
    inst = make_institution(db, "Risk College")
    user = make_user(db, Role.PGRC_OFFICER, Bureau.PGRC)
    _history(db, inst)
    h = auth_headers(client, user)
    risky = make_case(
        db, inst, Bureau.PGRC, channel=SourceChannel.CPGRAMS, category=CaseCategory.FEE_REFUND,
        received_at=NOW - timedelta(days=3), start_clocks=True,
    )
    safe = make_case(
        db, inst, Bureau.PGRC, channel=SourceChannel.CPGRAMS, category=CaseCategory.SCHOLARSHIP,
        received_at=NOW - timedelta(days=3), start_clocks=True,
    )
    r = client.get(f"{API}/cases/{risky.id}/risk", headers=h)
    assert r.status_code == 200, r.text
    hi, lo = r.json(), client.get(f"{API}/cases/{safe.id}/risk", headers=h).json()
    assert hi["trained_on"] == 60 and hi["probability"] > lo["probability"]
    assert hi["level"] in ("Medium", "High") and lo["level"] == "Low"
    assert any("Category" in f["factor"] and f["effect"] == "raises" for f in hi["factors"])
    risk.reset_model()


def test_risk_edge_cases(db, client):
    risk.reset_model()
    inst = make_institution(db, "Edge College")
    user = make_user(db, Role.PGRC_OFFICER, Bureau.PGRC)
    h = auth_headers(client, user)
    no_clock = make_case(db, inst, Bureau.RB, channel=SourceChannel.EMAIL, category=CaseCategory.OTHER)
    assert client.get(f"{API}/cases/{no_clock.id}/risk", headers=h).json()["level"] == "Not applicable"
    closed = make_case(db, inst, Bureau.PGRC, status=CaseStatus.DISPOSED)
    assert client.get(f"{API}/cases/{closed.id}/risk", headers=h).json()["level"] == "Closed"
    few = make_case(
        db, inst, Bureau.PGRC, channel=SourceChannel.CPGRAMS, received_at=NOW - timedelta(days=30), start_clocks=True
    )
    out = client.get(f"{API}/cases/{few.id}/risk", headers=h).json()
    assert out["level"] == "High" and out["probability"] is None and "not enough" in out["note"].lower()
    assert client.get(f"{API}/cases/00000000-0000-0000-0000-000000000000/risk", headers=h).status_code == 404
    risk.reset_model()
