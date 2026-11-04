"""Hash-chain tamper demo, three separate clocks, no combined 'SLA' label, clause wording from policy_config."""

from __future__ import annotations

import re

from tests.api.helpers import case_payload, find_institution, passport_count, timeline, verify, walk

SLA_RE = re.compile(r"\bSLA\b")


def test_every_non_tampered_chain_verifies(u):
    """All seeded and imported cases (QA tamper-demo cases are excluded: their chains are broken on purpose)."""
    ad = u["admin"]
    items, page = [], 1
    while True:
        body = ad.get("/cases", params={"page_size": 100, "page": page}).json()
        items += body["items"]
        if len(items) >= body["total"] or not body["items"]:
            break
        page += 1
    items = [c for c in items if "-tamper" not in (c["source_ref"] or "")]
    assert len(items) >= 600
    bad = [c["display_id"] for c in items if not verify(ad, c["id"])["ok"]]
    assert not bad, f"chains that do not verify: {bad}"


def test_tamper_demo_flags_exact_seq(u):
    pg, ad = u["pgrc.officer"], u["admin"]
    cid = pg.post("/cases", json=case_payload("A", tag="tamper")).json()["case"]["id"]
    pg.post(f"/cases/{cid}/remarks", json={"remark": "QA remark before tamper"})
    assert verify(ad, cid)["ok"] is True
    n = passport_count(ad, cid)
    r = ad.post("/admin/tamper-demo", json={"case_id": cid})
    assert r.status_code == 200, r.text
    body = r.json()
    seq = body["seq"]
    assert 1 <= seq <= n
    v = verify(ad, cid)
    assert v["ok"] is False
    assert v["first_bad_seq"] == seq, (v, seq)
    assert body["verify"]["first_bad_seq"] == seq


def test_tamper_demo_unknown_case_404(u):
    r = u["admin"].post("/admin/tamper-demo", json={"case_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 404


def test_passport_is_append_only_via_api():
    import httpx

    from tests.api.helpers import BASE

    paths = httpx.get(BASE + "/openapi.json").json()["paths"]
    for p, ops in paths.items():
        if "passport" in p:
            assert set(ops) == {"get"}, f"{p} exposes writes: {set(ops)}"


# ----------------------------------------------------------------------------- clocks
def test_three_separate_clocks_in_payloads(u):
    ad = u["admin"]
    inst = find_institution(ad, "1-4463974255")
    cases = timeline(ad, inst["id"])
    kinds: set[str] = set()
    for c in cases:
        for ck in c["clocks"]:
            kinds.add(ck["clock"])
            assert ck["clock"] in {"CPGRAMS_21D", "CSS_72H", "INST_REFUND_7D"}
            assert ck["state"] in {"ON_TRACK", "AMBER", "BREACHED", "PAUSED", "MET"}
            assert ck["label"] and ck["rule"] or ck["clock"] == "INST_REFUND_7D"
    assert {"CPGRAMS_21D", "INST_REFUND_7D"} <= kinds
    clocks = ad.get("/dashboard/clocks").json()
    assert {"CPGRAMS_21D", "CSS_72H", "INST_REFUND_7D"} <= set(clocks)
    assert clocks["INST_REFUND_7D"]["label"] != clocks["CPGRAMS_21D"]["label"]


def test_scenario_clock_states(u):
    ad = u["admin"]
    inst = find_institution(ad, "1-4463974255")
    cases = timeline(ad, inst["id"])
    pgrc1 = next(c for c in cases if c["category"] == "FEE_REFUND" and c["owner_bureau"] == "PGRC" and c["pending_step"] == "INSTITUTION_ATR")
    refund = next(ck for ck in pgrc1["clocks"] if ck["clock"] == "INST_REFUND_7D")
    assert refund["state"] == "BREACHED" and refund["label"] == "Inst. 7-day · overdue 4 days", refund
    pgrc2 = next(c for c in cases if c["category"] == "CERTIFICATE_WITHHELD" and c["source_channel"] == "CPGRAMS" and c["owner_bureau"] == "PGRC")
    cp = next(ck for ck in pgrc2["clocks"] if ck["clock"] == "CPGRAMS_21D")
    assert cp["state"] == "ON_TRACK" and cp["label"] == "21-day · 12 days left", cp


def test_no_combined_sla_label_in_any_payload(u):
    """'SLA' must never appear as a clock/label value in user-visible API text (the policy-clock rules: three separate clocks)."""
    ad = u["admin"]
    inst = find_institution(ad, "1-4463974255")
    docs = {
        "timeline": ad.get(f"/institutions/{inst['id']}/timeline").json(),
        "cases": ad.get("/cases", params={"page_size": 100}).json(),
        "clocks": ad.get("/dashboard/clocks").json(),
        "kpis": ad.get("/dashboard/kpis").json(),
        "config": ad.get("/config/public").json(),
        "notifications": ad.get("/notifications").json(),
        "digest": ad.get("/reports/digest-preview", params={"bureau": "RB"}).text,
        "pendency": ad.get("/reports/pendency", params={"month": "2026-10"}).json(),
        "openapi_descriptions": None,
    }
    hits = []
    for name, doc in docs.items():
        if doc is None:
            continue
        if isinstance(doc, str):
            if SLA_RE.search(doc):
                hits.append((name, "text"))
            continue
        for k, v in walk(doc):
            if isinstance(v, str) and SLA_RE.search(v):
                hits.append((name, k, v[:80]))
    assert not hits, f"'SLA' appears as a label: {hits[:5]}"


def test_notification_kinds_do_not_use_single_sla(u):
    kinds = set()
    for who in ("pgrc.officer", "rb.head", "pgrc.head", "approval.officer"):
        for n in u[who].get("/notifications").json()["items"]:
            kinds.add(n["kind"])
    sla_kinds = {k for k in kinds if "SLA" in k.upper()}
    # Identifiers named in the policy-clock rules (SLA_AMBER / SLA_BREACH) are internal enum values, not labels; report them.
    assert sla_kinds <= {"SLA_AMBER", "SLA_BREACH"}, sla_kinds


def test_clause_wording_in_policy_config_and_panel(u):
    cfg = u["pgrc.officer"].get("/config/public").json()
    assert cfg["clause_labels"]["refund"] == "APH 2024-27 cl. 6.45"
    assert cfg["clause_labels"]["deposit"] == "APH 2024-27 · Security-deposit release procedure"
    assert cfg["thresholds"]["inst_auto"] == 0.92 and cfg["thresholds"]["inst_review"] == 0.75
    assert cfg["clocks"]["CPGRAMS_21D"]["duration_hours"] == 504
    assert cfg["clocks"]["CSS_72H"]["duration_hours"] == 72
    assert cfg["clocks"]["INST_REFUND_7D"]["duration_hours"] == 168
    inst = find_institution(u["approval.officer"], "1-4463974255")
    panel = u["approval.officer"].post(f"/institutions/{inst['id']}/pre-action-check", json={"action_type": "SECURITY_DEPOSIT_RELEASE"}).json()
    assert cfg["clause_labels"]["deposit"] in panel["rule_note"]
    clocks = u["admin"].get("/dashboard/clocks").json()
    assert clocks["INST_REFUND_7D"]["rule"] == "APH 2024-27 cl. 6.45"


def test_clock_tooltips_carry_rule_label(u):
    inst = find_institution(u["admin"], "1-4463974255")
    for c in timeline(u["admin"], inst["id"]):
        for ck in c["clocks"]:
            assert ck.get("rule") or ck.get("long_label"), ck
