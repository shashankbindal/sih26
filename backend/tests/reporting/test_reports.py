from __future__ import annotations

import csv
import io
from datetime import timedelta

from app.services.dashboard import IST
from tests.conftest import auth_headers
from tests.reporting._world import NOW, build_world

API = "/api/v1"


def _month(dt):
    d = dt.astimezone(IST)
    return f"{d.year:04d}-{d.month:02d}"


def test_pendency_current_month_matches_dashboard(db, client):
    w = build_world(db)
    h = auth_headers(client, w["admin"])
    for group_by in ("bureau", "region", "institution", "category"):
        r = client.get(f"{API}/reports/pendency", params={"month": _month(NOW), "group_by": group_by}, headers=h)
        assert r.status_code == 200, r.text
        rep = r.json()
        assert [c["label"] for c in rep["columns"][1:]] == [
            "Opening pending", "Received", "Disposed", "Closing pending", "Overdue", "Avg days to dispose",
        ]
        t = rep["totals"]
        assert t["closing_pending"] == 7  # equals dashboard pending: period contains now
        assert t["overdue"] == 2
        assert t["opening_pending"] + t["received"] - t["disposed"] == t["closing_pending"]
        assert sum(x["closing_pending"] for x in rep["rows"]) == t["closing_pending"]
        for row in rep["rows"]:
            assert row["opening_pending"] + row["received"] - row["disposed"] == row["closing_pending"]


def test_pendency_past_month_disposed_and_avg_days(db, client):
    w = build_world(db)
    h = auth_headers(client, w["admin"])
    rep = client.get(
        f"{API}/reports/pendency", params={"month": _month(NOW - timedelta(days=10)), "group_by": "bureau"}, headers=h
    ).json()
    pgrc = next(r for r in rep["rows"] if r["group_key"] == "PGRC")
    assert pgrc["disposed"] >= 1
    if _month(NOW - timedelta(days=60)) != _month(NOW - timedelta(days=10)):
        assert pgrc["avg_days_to_dispose"] == 30.0


def test_quarterly_and_validation(db, client):
    w = build_world(db)
    h = auth_headers(client, w["admin"])
    d = NOW.astimezone(IST)
    q = f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    r = client.get(f"{API}/reports/pendency", params={"period": "quarterly", "quarter": q}, headers=h)
    assert r.status_code == 200 and r.json()["period_type"] == "quarterly"
    assert client.get(f"{API}/reports/pendency", params={"month": "2026-13"}, headers=h).status_code == 422
    assert client.get(f"{API}/reports/pendency", params={"group_by": "nope"}, headers=h).status_code == 422
    assert client.get(f"{API}/reports/pendency").status_code == 401


def test_csv_has_bom_and_pdf_is_pdf(db, client):
    w = build_world(db)
    h = auth_headers(client, w["admin"])
    p = {"month": _month(NOW), "group_by": "institution"}
    c = client.get(f"{API}/reports/pendency", params={**p, "format": "csv"}, headers=h)
    assert c.status_code == 200 and c.content.startswith(b"\xef\xbb\xbf")
    assert "attachment" in c.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(c.content.decode("utf-8-sig"))))
    assert rows[0] == ["Institution", "Opening pending", "Received", "Disposed", "Closing pending", "Overdue", "Avg days to dispose"]
    assert rows[-1][0] == "Total"
    pdf = client.get(f"{API}/reports/pendency", params={**p, "format": "pdf"}, headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) > 1500
    assert pdf.headers["content-type"] == "application/pdf"


def test_digest_preview_html_no_pii(db, client):
    w = build_world(db)
    h = auth_headers(client, w["head"])
    r = client.get(f"{API}/reports/digest-preview", params={"bureau": "PGRC"}, headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "<table" in body and "stylesheet" not in body and "<script" not in body
    assert "Overdue by policy" in body and "asha" not in body.lower()
    assert client.get(f"{API}/reports/digest-preview?bureau=RB", headers=h).status_code == 200
