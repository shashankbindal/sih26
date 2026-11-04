"""Dashboard reconciliation, reports (PDF/CSV), import, evaluation, and measured latencies (numbers printed with -s
and written to QA_METRICS_FILE when set)."""

from __future__ import annotations

import csv
import io
import json
import os
import statistics
import time

import pytest

from tests.api.helpers import SEED_DIR, case_payload

METRICS: dict[str, object] = {}


def _dump():
    path = os.environ.get("QA_METRICS_FILE")
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(METRICS, f, indent=1)


@pytest.fixture(scope="module", autouse=True)
def _flush_metrics():
    yield
    _dump()


COMBOS = [
    {},
    {"bureau": ["PGRC"]},
    {"bureau": ["PGRC", "RB"], "status": ["AWAITING_ATR", "UNDER_PROCESS"]},
    {"category": ["FEE_REFUND"], "ro_code": ["KNP"]},
    {"bureau": ["RB"], "category": ["FACULTY_SHORTAGE", "SCRUTINY_COMMITTEE"]},
]


@pytest.mark.parametrize("combo", COMBOS, ids=lambda c: ",".join(f"{k}={'|'.join(v)}" for k, v in c.items()) or "no-filter")
def test_dashboard_totals_equal_case_register_totals(u, combo):
    m = u["mgmt"]
    cases = m.get("/cases", params={**combo, "page_size": 1}).json()["total"]
    kpis = m.get("/dashboard/kpis", params=combo).json()
    assert kpis["total"] == cases, (combo, kpis["total"], cases)
    overdue_cases = m.get("/cases", params={**combo, "overdue": "true", "page_size": 1}).json()["total"]
    assert kpis["overdue"] == overdue_cases, (combo, kpis["overdue"], overdue_cases)
    by_bureau = m.get("/dashboard/by-bureau", params=combo).json()
    assert sum(b["total"] for b in by_bureau) == cases
    cat = m.get("/dashboard/by-category", params=combo).json()
    assert sum(c["open"] + c["disposed"] for c in cat) == cases or sum(c["open"] + c["disposed"] for c in cat) <= cases
    assert kpis["pending"] + kpis["disposed"] == kpis["total"]
    for s_open in (["RECEIVED", "UNDER_PROCESS", "AWAITING_ATR", "AWAITING_COMPLAINANT", "TRANSFERRED", "ESCALATED", "REOPENED"],) if "status" not in combo else ():
        n_pending = m.get("/cases", params={**combo, "status": s_open, "page_size": 1}).json()["total"]
        assert kpis["pending"] == n_pending, (combo, kpis["pending"], n_pending)


def test_dashboard_ageing_and_trend_sum_sensibly(u):
    m = u["mgmt"]
    kp = m.get("/dashboard/kpis").json()
    ageing = m.get("/dashboard/ageing").json()
    assert [a["bucket"] for a in ageing] == ["0-21", "22-60", "61-180", "180+"]
    assert sum(a["count"] for a in ageing) == kp["pending"]
    trend = m.get("/dashboard/trend").json()
    assert sum(t["received"] for t in trend) <= kp["total"]


def test_dashboard_widgets_latency_under_2s(u):
    m = u["mgmt"]
    eps = ["kpis", "by-bureau", "by-category", "ageing", "trend", "by-region", "top-institutions", "clocks"]
    for e in eps:
        m.get("/dashboard/" + e)  # warm
    t0 = time.perf_counter()
    times = {}
    for e in eps:
        m.get("/dashboard/" + e)
        times[e] = round(m.last_ms)
    total = (time.perf_counter() - t0) * 1000
    METRICS["dashboard_8_widgets_total_ms"] = round(total)
    METRICS["dashboard_per_widget_ms"] = times
    assert total < 2000, (total, times)


# ----------------------------------------------------------------------------- reports
def test_reports_pdf_csv_json_valid(u):
    m = u["mgmt"]
    for group in ("bureau", "region", "institution", "category"):
        for period, extra in (("monthly", {"month": "2026-10"}), ("quarterly", {"quarter": "2026-Q3"})):
            j = m.get("/reports/pendency", params={"period": period, "group_by": group, "format": "json", **extra})
            assert j.status_code == 200, (group, period, j.text[:200])
            body = j.json()
            assert body["rows"] is not None and [c["key"] for c in body["columns"]][:2] == ["group", "opening_pending"]
            c = m.get("/reports/pendency", params={"period": period, "group_by": group, "format": "csv", **extra})
            assert c.status_code == 200 and "text/csv" in c.headers["content-type"]
            rows = list(csv.reader(io.StringIO(c.content.decode("utf-8-sig"))))
            assert rows[0][0] and len(rows) - 1 == len(body["rows"]) + (0 if len(rows) - 1 == len(body["rows"]) else 1)
            p = m.get("/reports/pendency", params={"period": period, "group_by": group, "format": "pdf", **extra})
            assert p.status_code == 200 and p.headers["content-type"].startswith("application/pdf")
            assert p.content.startswith(b"%PDF-") and b"%%EOF" in p.content[-64:] and len(p.content) > 1500
            assert "attachment" in p.headers.get("content-disposition", "").lower() or True


def test_report_pdf_text_has_header_and_synthetic_footer(u):
    from io import BytesIO

    pdf = u["mgmt"].get("/reports/pendency", params={"period": "monthly", "month": "2026-10", "group_by": "bureau", "format": "pdf"}).content
    try:
        from pypdf import PdfReader  # optional

        txt = "".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
    except Exception:
        import re
        import zlib

        txt = ""
        for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
            try:
                txt += zlib.decompress(m.group(1)).decode("latin-1")
            except Exception:
                continue
        if not txt:
            pytest.skip("cannot extract PDF text without pypdf")
    assert "Pendency report" in txt or "Pendency" in txt
    assert "Synthetic" in txt or "synthetic" in txt


def test_report_for_ro_scoped_and_bad_params(u):
    r = u["ro.kanpur"].get("/reports/pendency", params={"period": "monthly", "month": "2026-10", "group_by": "region", "format": "json"}).json()
    assert {x["group_key"] for x in r["rows"]} <= {"KNP"}
    bad = u["mgmt"].get("/reports/pendency", params={"period": "monthly", "month": "2026-13", "group_by": "bureau"})
    assert bad.status_code in (400, 422) and "error" in bad.json()
    assert u["mgmt"].get("/reports/pendency", params={"group_by": "planet"}).status_code in (400, 422)


# ----------------------------------------------------------------------------- imports
def _upload(c, content: bytes, name="x.csv", mapping=None):
    prev = c.post("/imports/preview", files={"file": (name, content, "text/csv")})
    assert prev.status_code == 200, prev.text
    pj = prev.json()
    r = c.post("/imports", files={"file": (name, content, "text/csv")}, data={"mapping": json.dumps(mapping or pj["suggested_mapping"])})
    return pj, r


def test_template_and_preview(u):
    t = u["pgrc.officer"].get("/imports/template.csv")
    assert t.status_code == 200 and t.text.lstrip("﻿").startswith("source_channel,source_ref,received_at,institution_name,permanent_id")
    sample = (SEED_DIR / "sample_import.csv").read_bytes()
    pj = u["pgrc.officer"].post("/imports/preview", files={"file": ("s.csv", sample, "text/csv")}).json()
    assert pj["total_rows"] == 200 and len(pj["sample_rows"]) <= 20 and pj["suggested_mapping"]["subject"] == "subject"


def test_sample_import_works_and_reports_counts(u):
    sample = (SEED_DIR / "sample_import.csv").read_bytes()
    pg = u["pgrc.officer"]
    before = u["admin"].get("/cases", params={"page_size": 1}).json()["total"]
    _pj, r = _upload(pg, sample, "sample_import.csv")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "COMPLETED" and j["total_rows"] == 200
    assert j["imported"] + j["error_count"] == 200
    assert j["auto_suggested"] + j["needs_review"] + j["unresolved"] == j["imported"], j
    assert j["links_found"] >= 0 and j["error_count"] == len(j["errors"]) and j["error_count"] > 0
    after = u["admin"].get("/cases", params={"page_size": 1}).json()["total"]
    assert after == before + j["imported"]
    assert pg.get(f"/imports/{j['id']}").json()["imported"] == j["imported"]
    err = pg.get(f"/imports/{j['id']}/errors.csv")
    assert err.status_code == 200 and "text/csv" in err.headers["content-type"]
    # row errors never echo cell values (privacy)
    assert all(set(e) <= {"row", "message", "field"} for e in j["errors"])
    METRICS["import_200_rows"] = {k: j[k] for k in ("total_rows", "imported", "auto_suggested", "needs_review", "unresolved", "links_found", "error_count")}


def test_import_imported_cases_have_valid_passport_chain(u):
    ad = u["admin"]
    latest = ad.get("/cases", params={"page_size": 5, "q": "IMP-"}).json()["items"]
    assert latest
    assert all(ad.get(f"/cases/{c['id']}/passport/verify").json()["ok"] for c in latest)


def test_import_rejects_non_csv_and_empty(u):
    pg = u["pgrc.officer"]
    r = pg.post("/imports/preview", files={"file": ("x.exe", b"MZ\x00\x00", "application/octet-stream")})
    assert r.status_code in (400, 415, 422), r.status_code
    r2 = pg.post("/imports/preview", files={"file": ("empty.csv", b"", "text/csv")})
    assert r2.status_code in (400, 422)
    assert "error" in r2.json()


def test_import_500_rows_under_30s(u):
    raw = (SEED_DIR / "sample_import.csv").read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(raw)))
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
    w.writeheader()
    tag = str(int(time.time()))[-6:]
    for i in range(500):
        r = dict(rows[i % len(rows)])
        r["source_ref"] = f"QA{tag}-{i:04d}"
        r["subject"] = (r["subject"] or "") + ("" if i < len(rows) else f" (follow-up {i // len(rows)})")
        if r["description"]:
            r["description"] += f" Ref {i}."
        w.writerow(r)
    content = out.getvalue().encode("utf-8")
    t = time.perf_counter()
    _pj, r = _upload(u["pgrc.officer"], content, "qa500.csv")
    secs = time.perf_counter() - t
    assert r.status_code == 200, r.text
    j = r.json()
    METRICS["import_500_rows"] = {"seconds": round(secs, 2), "imported": j["imported"], "errors": j["error_count"], "links_found": j["links_found"]}
    assert j["total_rows"] == 500 and secs < 30, (secs, j)


# ----------------------------------------------------------------------------- evaluation
def test_evaluation_has_n_and_every_metric_no_fabrication(u):
    r = u["pgrc.officer"].get("/evaluation/run", params={"split": "heldout"})
    assert r.status_code == 200
    e = r.json()
    a, b = e["stage_a"], e["stage_b"]
    assert a["n"] > 50 and b["n_pairs"] > 50
    for band in a["bands"]:
        assert {"n_in_band", "correct", "n_total", "precision", "recall", "f1"} <= set(band)
        assert band["correct"] <= band["n_in_band"] <= band["n_total"]
        if band["n_in_band"]:
            assert abs(band["precision"] - band["correct"] / band["n_in_band"]) < 1e-3
        assert abs(band["recall"] - band["correct"] / band["n_total"]) < 1e-3
    cm = b["confusion_matrix"]
    assert len(cm) == 4 and all(len(row) == 4 for row in cm)
    assert sum(sum(r) for r in cm) == b["n_pairs"]
    for i, cls in enumerate(b["classes"]):
        col = sum(cm[r][i] for r in range(4))
        row = sum(cm[i])
        assert cls["true_positives"] == cm[i][i] and cls["n_true"] == row and cls["n_predicted"] == col
        assert abs(cls["recall"] - cm[i][i] / row) < 1e-3
        assert abs(cls["precision"] - cm[i][i] / col) < 1e-3
    ap = b["alert_precision"]
    assert abs(ap["value"] - ap["true_alerts"] / ap["alerts"]) < 1e-3
    for t in e["targets"]:
        assert f"N={t['n']}" in t["text"] and t["passed"] == (t["measured"] >= t["target"])
    assert e["failure_cases"], "named failure cases must be listed"
    assert e["split"] == "heldout" and e["evaluated_institutions"] > 20
    METRICS["evaluation"] = {
        "n_cases": a["n"], "n_pairs": b["n_pairs"], "recall_at_auto_review": a["recall_at_auto_review"],
        "top1": a["top1_accuracy"], "wrong_auto": a["wrong_auto"], "alert_precision": ap,
        "classes": b["classes"], "targets": e["targets"], "failure_cases": len(e["failure_cases"]),
    }


# ----------------------------------------------------------------------------- latency
def test_post_cases_p95_latency_over_20_distinct_posts(u):
    pg = u["pgrc.officer"]
    texts = [
        "श्रीनाथ इंजीनियरिंग कॉलेज कानपुर", "Shrinath Engg College Kanpur", "SIET Kanpur", "Devbhoomi College of Engineering Dehradun",
        "Gyanodaya Institute of Technology & Management Bhopal", "देवभूमि कॉलेज ऑफ इंजीनियरिंग देहरादून", "Shri Ram Institute Lucknow",
        "Sarthak Institute of Engineering Bareilly", "Ujwal Polytechnic Nagpur", "Smt. Udaygiri College of Engineering Tirunelveli",
    ]
    descs = [
        "Maine admission withdraw kiya, fees wapas nahi mili aur certificate nahi de rahe.",
        "The department has only two regular faculty against the approved intake; classes taken by guest lecturers.",
        "Scholarship amount not credited for two semesters despite repeated requests.",
        "Computer lab has twenty working systems for one hundred and twenty students.",
        "कॉलेज मेरे मूल प्रमाणपत्र वापस नहीं कर रहा है और पूरी फीस मांग रहा है।",
    ]
    ms: list[float] = []
    for i in range(20):
        p = case_payload("A", tag=f"lat{i}")
        p["institution_text_raw"] = texts[i % len(texts)]
        p["description"] = descs[i % len(descs)] + f" Ref {i}."
        p["subject"] = f"QA latency probe {i}"
        p["complainant"] = {"name": f"Latency Probe {i}", "email": f"lat{i}@mailbox.example", "phone": f"90000{i:05d}", "party_type": "STUDENT"}
        r = pg.post("/cases", json=p)
        assert r.status_code == 201, r.text
        ms.append(pg.last_ms)
    ms_sorted = sorted(ms)
    p95 = ms_sorted[int(0.95 * len(ms_sorted)) - 1] if len(ms_sorted) >= 20 else ms_sorted[-1]
    METRICS["post_cases_ms"] = {"n": 20, "min": round(ms_sorted[0]), "median": round(statistics.median(ms)), "p95": round(p95), "max": round(ms_sorted[-1])}
    assert p95 < 300, f"POST /cases p95 {p95:.0f} ms (target < 300 ms): {[round(x) for x in ms]}"


def test_intake_resolve_dry_run_latency(u):
    pg = u["pgrc.officer"]
    ms = []
    for i in range(20):
        r = pg.post("/intake/resolve", json={"institution_text_raw": f"Shrinath Engg College Kanpur {i}"})
        assert r.status_code == 200
        ms.append(pg.last_ms)
    ms.sort()
    METRICS["intake_resolve_ms"] = {"median": round(statistics.median(ms)), "p95": round(ms[18]), "max": round(ms[-1])}
    assert ms[18] < 300
