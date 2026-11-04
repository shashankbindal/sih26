from __future__ import annotations

import time
from datetime import timedelta

from tests.conftest import auth_headers
from tests.reporting._world import NOW, build_world

API = "/api/v1"
FILTER_SETS = [
    {},
    {"bureau": ["PGRC"]},
    {"bureau": ["PGRC", "RB"], "category": ["FEE_REFUND", "FACULTY_SHORTAGE"]},
    {"ro_code": ["KNP"]},
    {"ro_code": ["BPL"], "status": ["RECEIVED", "ESCALATED", "CLOSED_NO_ACTION"]},
    {"received_from": (NOW - timedelta(days=45)).isoformat(), "received_to": (NOW - timedelta(days=1)).isoformat()},
]
CLOSED = {"DISPOSED", "CLOSED_NO_ACTION"}


def _cases(client, h, **params):
    r = client.get(f"{API}/cases", params={**params, "page_size": 200}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _dash_params(p):
    q = dict(p)
    if "received_from" in q:
        q["from"] = q.pop("received_from")
    if "received_to" in q:
        q["to"] = q.pop("received_to")
    return q


def test_kpis_reconcile_with_case_register(db, client):
    w = build_world(db)
    h = auth_headers(client, w["admin"])
    for params in FILTER_SETS:
        k = client.get(f"{API}/dashboard/kpis", params=_dash_params(params), headers=h)
        assert k.status_code == 200, k.text
        k = k.json()
        allc = _cases(client, h, **params)
        items = allc["items"]
        assert k["total"] == allc["total"], params
        assert k["pending"] == sum(i["status"] not in CLOSED for i in items), params
        assert k["disposed"] == sum(i["status"] in CLOSED for i in items), params
        assert k["total"] == k["pending"] + k["disposed"]
        assert k["escalated"] == sum(i["status"] == "ESCALATED" for i in items)
        assert k["transferred"] == sum(i["status"] == "TRANSFERRED" for i in items)
        assert k["under_process"] == sum(
            i["status"] in {"UNDER_PROCESS", "AWAITING_ATR", "AWAITING_COMPLAINANT"} for i in items
        )
        overdue = _cases(client, h, overdue="true", **params)
        assert k["overdue"] == overdue["total"], params
        assert sum(k["overdue_by_clock"].values()) >= k["overdue"]


def test_kpi_values_and_deltas(db, client):
    w = build_world(db)
    h = auth_headers(client, w["admin"])
    k = client.get(f"{API}/dashboard/kpis", headers=h).json()
    assert k["total"] == 9 and k["pending"] == 7 and k["disposed"] == 2
    assert k["overdue"] == 2  # cpgrams 30d + refund 12d
    assert k["overdue_by_clock"]["CPGRAMS_21D"] == 1
    assert k["overdue_by_clock"]["INST_REFUND_7D"] == 1
    assert k["open_alerts"] == 2  # the link to the disposed case is excluded
    assert k["deltas"] is None
    p = {"from": (NOW - timedelta(days=60)).isoformat(), "to": NOW.isoformat()}
    k2 = client.get(f"{API}/dashboard/kpis", params=p, headers=h).json()
    d = k2["deltas"]["vs_prev_period"]["total"]
    assert d["change"] == k2["total"] - d["previous"]
    # previous window is days 120..60 ago: knp_ro_case (100) and closed_no_action (70)
    assert d["previous"] == 2


def test_breakdowns(db, client):
    w = build_world(db)
    h = auth_headers(client, w["admin"])
    bb = {r["bureau"]: r for r in client.get(f"{API}/dashboard/by-bureau", headers=h).json()}
    assert bb["PGRC"]["total"] == 4 and bb["PGRC"]["DISPOSED"] == 1 and bb["PGRC"]["CLOSED_NO_ACTION"] == 1
    assert sum(r["total"] for r in bb.values()) == 9
    cat = client.get(f"{API}/dashboard/by-category", headers=h).json()
    assert sum(r["open"] + r["disposed"] for r in cat) == 9
    ag = {r["bucket"]: r["count"] for r in client.get(f"{API}/dashboard/ageing", headers=h).json()}
    assert list(ag) == ["0-21", "22-60", "61-180", "180+"]
    assert ag == {"0-21": 3, "22-60": 2, "61-180": 1, "180+": 1}
    tr = client.get(f"{API}/dashboard/trend", params={"granularity": "month"}, headers=h).json()
    assert sum(r["received"] for r in tr) == 9 and sum(r["disposed"] for r in tr) == 2
    periods = [r["period"] for r in tr]
    assert periods == sorted(periods) and len(periods) == len(set(periods))
    reg = {r["ro_code"]: r for r in client.get(f"{API}/dashboard/by-region", headers=h).json()}
    assert reg["KNP"]["open"] + reg["BPL"]["open"] == 7
    assert reg["KNP"]["overdue"] == 2
    top = client.get(f"{API}/dashboard/top-institutions", params={"limit": 5}, headers=h).json()
    assert top[0]["name"] == "Shrinath Engineering College" and top[0]["open"] == 5
    assert top[0]["overdue"] == 2 and top[0]["open_alerts"] >= 1
    assert "risk" not in str(top).lower()


def test_clock_summary_separate_clocks(db, client):
    w = build_world(db)
    h = auth_headers(client, w["admin"])
    c = client.get(f"{API}/dashboard/clocks", headers=h).json()
    assert set(c) == {"CPGRAMS_21D", "CSS_72H", "INST_REFUND_7D"}
    assert c["CPGRAMS_21D"]["breached"] == 1
    assert c["INST_REFUND_7D"]["breached"] == 1
    assert c["CSS_72H"]["amber"] == 1
    assert c["CPGRAMS_21D"]["label"] == "21-day"
    assert c["INST_REFUND_7D"]["rule"] == "APH 2024-27 cl. 6.45"


def test_ro_user_scoped_to_region(db, client):
    w = build_world(db)
    h = auth_headers(client, w["ro"])
    k = client.get(f"{API}/dashboard/kpis", params={"ro_code": "BPL"}, headers=h).json()
    assert k["filters"]["ro_code"] == ["KNP"] and k["filters"]["ro_forced"] is True
    admin_k = client.get(
        f"{API}/dashboard/kpis", params={"ro_code": "KNP"}, headers=auth_headers(client, w["admin"])
    ).json()
    assert k["total"] == admin_k["total"]
    regions = client.get(f"{API}/dashboard/by-region", headers=h).json()
    assert [r["ro_code"] for r in regions] == ["KNP"]


def test_requires_auth_and_no_pii(db, client):
    w = build_world(db)
    assert client.get(f"{API}/dashboard/kpis").status_code == 401
    h = auth_headers(client, w["mgmt"])
    for ep in ("kpis", "by-bureau", "by-category", "ageing", "trend", "by-region", "top-institutions", "clocks"):
        r = client.get(f"{API}/dashboard/{ep}", headers=h)
        assert r.status_code == 200
        assert "asha" not in r.text.lower() and "example.test" not in r.text


def test_dashboard_fast_on_larger_data(db, client):
    from tests.conftest import make_case, make_institution

    w = build_world(db)
    insts = [make_institution(db, f"Test College {i}", ro_code="KNP") for i in range(20)]
    for i in range(300):
        make_case(db, insts[i % 20], received_at=NOW - timedelta(days=i % 250), start_clocks=(i % 3 == 0))
    h = auth_headers(client, w["admin"])
    t = time.perf_counter()
    for ep in ("kpis", "by-bureau", "by-category", "ageing", "trend", "by-region", "top-institutions", "clocks"):
        client.get(f"{API}/dashboard/{ep}", headers=h)
    assert time.perf_counter() - t < 8.0  # eight endpoints in total; each is well under 2 s


def test_links_both_open_matches_kpi_open_alerts(db, client):
    """GET /links?both_open=true lists exactly the links the dashboard KPI counts (same shared predicate)."""
    w = build_world(db)
    h = auth_headers(client, w["admin"])
    active = ["SUGGESTED", "CONFIRMED", "DEFERRED"]
    every = client.get(f"{API}/links", params={"status": active, "page_size": 200}, headers=h).json()
    open_only = client.get(f"{API}/links", params={"status": active, "both_open": "true", "page_size": 200}, headers=h).json()
    kpi = client.get(f"{API}/dashboard/kpis", headers=h).json()["open_alerts"]
    assert every["total"] == 3  # includes the link to the disposed case
    assert open_only["total"] == kpi == 2
    assert all(i["case_a"]["status"] != "DISPOSED" and i["case_b"]["status"] != "DISPOSED" for i in open_only["items"])
    # without an explicit status the active set is still the KPI's, because superseded links are never open alerts
    default = client.get(f"{API}/links", params={"both_open": "true"}, headers=h).json()
    assert default["total"] == kpi
