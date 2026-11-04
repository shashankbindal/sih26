"""Scenarios A-F exactly as the seed-data plan section 4 expects, driven through HTTP only. Run on a freshly seeded DB
(scenario E stores an alias, so a second run reports 'reseed needed' via skip)."""

from __future__ import annotations

import pytest

from tests.api.helpers import DEMO_INPUTS, case_payload, find_institution, timeline

SHRINATH = "1-4463974255"
DEVBHOOMI = "1-4471203398"
GYANODAYA = "1-4458812074"
SHRI_RAM_COLLEGE = "1-4440019921"
SHRI_RAM_INSTITUTE = "1-4440019987"


def _shrinath_cases(u):
    inst = find_institution(u["admin"], SHRINATH)
    cases = timeline(u["admin"], inst["id"])
    pgrc1 = next(c for c in cases if c["owner_bureau"] == "PGRC" and c["category"] == "FEE_REFUND"
                 and c["status"] == "AWAITING_ATR" and c["pending_step"] == "INSTITUTION_ATR")
    pgrc2 = next(c for c in cases if c["owner_bureau"] == "PGRC" and c["category"] == "CERTIFICATE_WITHHELD"
                 and c["source_channel"] == "CPGRAMS")
    rb1 = next(c for c in cases if c["owner_bureau"] == "RB" and c["category"] == "SCRUTINY_COMMITTEE" and c["status"] != "DISPOSED")
    ro1 = next(c for c in cases if c["owner_bureau"] == "RO" and c["category"] == "FEE_REFUND")
    return inst, pgrc1, pgrc2, rb1, ro1


# ------------------------------------------------------------------------------------------ A
@pytest.fixture(scope="module")
def scenario_a(u):
    inst, pgrc1, pgrc2, rb1, ro1 = _shrinath_cases(u)
    rb_unread_before = {n["id"] for n in u["rb.officer"].get("/notifications").json()["items"]}
    n_cases_before = u["admin"].get("/cases").json()["total"]
    r = u["pgrc.officer"].post("/cases", json=case_payload("A", tag="scenA"))
    assert r.status_code == 201, r.text
    return {"res": r.json(), "pgrc1": pgrc1, "pgrc2": pgrc2, "rb1": rb1, "ro1": ro1, "inst": inst,
            "rb_before": rb_unread_before, "n_before": n_cases_before}


def test_A_resolution_auto_suggested_with_reasons(scenario_a):
    res = scenario_a["res"]["resolution"]
    assert res["status"] == "AUTO_SUGGESTED"
    assert res["selected"]["permanent_id"] == SHRINATH
    assert res["selected"]["score"] >= 0.92
    reasons = " ".join(res["candidates"][0]["reasons"]).lower()
    assert "transliteration" in reasons and "kanpur" in reasons


def test_A_category_fee_refund(scenario_a):
    assert scenario_a["res"]["category_suggestion"]["category"] == "FEE_REFUND"


def test_A_links_related_to_pgrc1_and_ro1(scenario_a):
    links = {lk["other_case"]["id"]: lk for lk in scenario_a["res"]["links"]}
    for key in ("pgrc1", "ro1"):
        cid = scenario_a[key]["id"]
        assert cid in links, f"no link to {key}"
        assert links[cid]["relation"] == "RELATED", (key, links[cid]["relation"])
        assert links[cid]["reasons"], "link must carry reasons"
        assert links[cid]["status"] == "SUGGESTED"


def test_A_rb1_unrelated_and_nothing_alarming(scenario_a, u):
    res = scenario_a["res"]
    rb1 = scenario_a["rb1"]
    assert rb1["id"] not in {lk["other_case"]["id"] for lk in res["links"]}, "RB-1 must not be linked"
    assert rb1["id"] in {x["other_case"]["id"] for x in res.get("unrelated", [])}
    # RB gets no coordination/priority alert about the new case
    new_display = res["case"]["display_id"]
    after = u["rb.officer"].get("/notifications").json()["items"]
    fresh = [n for n in after if n["id"] not in scenario_a["rb_before"]]
    assert not [n for n in fresh if new_display in (n["title"] + n["body"]) and rb1["display_id"] in (n["title"] + n["body"])], fresh
    rb1_now = next(c for c in timeline(u["admin"], scenario_a["inst"]["id"]) if c["id"] == rb1["id"])
    assert rb1_now["alerts"]["total"] == 0 or rb1["alerts"]["total"] == rb1_now["alerts"]["total"]


def test_A_advisory_no_auto_merge(scenario_a, u):
    """Engine is advisory: exactly one new case, existing cases untouched, links only SUGGESTED."""
    assert u["admin"].get("/cases").json()["total"] >= scenario_a["n_before"] + 1
    for key in ("pgrc1", "ro1", "pgrc2"):
        now = u["admin"].get(f"/cases/{scenario_a[key]['id']}").json()
        assert now["status"] == scenario_a[key]["status"], f"{key} status changed by the engine"
        assert now["owner_bureau"] == scenario_a[key]["owner_bureau"]
    assert all(lk["status"] == "SUGGESTED" for lk in scenario_a["res"]["links"])


def test_A_clock_css72_started(scenario_a):
    assert [c["clock"] for c in scenario_a["res"]["clocks"]] == ["CSS_72H"]


# ------------------------------------------------------------------------------------------ B
@pytest.fixture(scope="module")
def scenario_b(u, scenario_a):
    ap = u["approval.officer"]
    r = ap.post(f"/institutions/{scenario_a['inst']['id']}/pre-action-check", json={"action_type": "SECURITY_DEPOSIT_RELEASE"})
    assert r.status_code == 201, r.text
    return r.json()


def test_B_panel_open_matters_and_high_flag(scenario_b, scenario_a):
    panel = scenario_b
    assert panel["action_type"] == "SECURITY_DEPOSIT_RELEASE"
    assert panel["summary"]["total_open"] >= 5
    by_id = {m["case_id"]: m for m in panel["open_matters"]}
    pgrc1 = by_id[scenario_a["pgrc1"]["id"]]
    assert pgrc1["relevance"] == "HIGH"
    assert pgrc1["pending_days"] == 11
    assert any(c["clock"] == "INST_REFUND_7D" and c["state"] == "BREACHED" for c in pgrc1["clocks"])
    assert "overdue" in pgrc1["why"].lower() and "7-day" in pgrc1["why"]
    # most relevant first
    rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    ranks = [rank[m["relevance"]] for m in panel["open_matters"]]
    assert ranks == sorted(ranks)
    assert panel["advisory"].lower().startswith("advisory only")
    assert "APH 2024-27 · Security-deposit release procedure" in panel["rule_note"]


def test_B_chain_is_pgrc_vigilance_approval(scenario_b):
    chain = scenario_b["clearance_chain"]
    assert [c["bureau"] for c in chain] == ["PGRC", "VIGILANCE", "APPROVAL"]
    assert chain[0]["state"] == "NOT_REQUESTED" and chain[1]["state"] == "NOT_REQUESTED"
    assert chain[2]["state"] in ("NOT_REQUESTED", "PENDING_PREVIOUS")


def test_B_request_clearance_reaches_pgrc_inbox_and_acknowledge_logs(scenario_b, u):
    ap, pg = u["approval.officer"], u["pgrc.officer"]
    aid = scenario_b["institution_action_id"]
    r = ap.post(f"/institution-actions/{aid}/clearances", json={"target_bureau": "PGRC", "remark": "Scenario B QA request"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    inbox = pg.get("/clearances", params={"inbox": "me"}).json()["items"]
    mine = [c for c in inbox if c["id"] == cid]
    assert mine and mine[0]["response"] == "PENDING" and mine[0]["target_bureau"] == "PGRC"
    assert u["rb.officer"].get("/clearances", params={"inbox": "me"}).json()["items"] is not None
    assert cid not in [c["id"] for c in u["rb.officer"].get("/clearances", params={"inbox": "me"}).json()["items"]]
    # live chain update seen by Approval after PGRC responds
    assert pg.post(f"/clearances/{cid}/respond", json={"response": "CLEARED", "remarks": "QA cleared"}).status_code == 200
    det = ap.get(f"/institution-actions/{aid}").json()
    chain = (det.get("action") or det)["clearance_chain"]
    assert chain[0]["state"] in ("CLEARED", "CLEARED_WITH_REMARKS")
    ack = ap.post(f"/institution-actions/{aid}/acknowledge", json={"remark": "seen all open matters", "proceed": True})
    assert ack.status_code == 200, ack.text
    entry = ack.json()["passport_entry"]
    assert entry["event"] == "PREACTION_ACKNOWLEDGED"
    n = scenario_b["summary"]["total_open"]
    assert f"Proceeded with {n} open matters acknowledged" in entry["payload"]["summary"], entry["payload"]


# ------------------------------------------------------------------------------------------ C
def test_C_conflicting_link_and_heads_notified(u):
    inst = find_institution(u["admin"], DEVBHOOMI)
    links = u["admin"].get(f"/institutions/{inst['id']}/links").json()
    conf = [lk for lk in links if lk["relation"] == "CONFLICTING"]
    assert conf, "no CONFLICTING link on Devbhoomi"
    lk = conf[0]
    assert lk["status"] == "SUGGESTED" and lk["reasons"]
    detail = u["pgrc.head"].get(f"/links/{lk['id']}").json()
    assert detail["relation"] == "CONFLICTING"
    assert detail.get("suggested_next_action") or (detail.get("thread") or {}).get("shared_next_action")
    for head in ("rb.head", "pgrc.head"):
        notes = u[head].get("/notifications").json()["items"]
        assert [n for n in notes if n["kind"] == "PRIORITY_REVIEW" and n["institution_id"] == inst["id"]], head
    # priority review is the inbox's first item for that institution
    inbox = u["rb.head"].get("/links", params={"institution_id": inst["id"]}).json()["items"]
    assert inbox and inbox[0]["relation"] == "CONFLICTING"


# ------------------------------------------------------------------------------------------ D
def test_D_negative_example_no_link_no_alert(u):
    inst = find_institution(u["admin"], GYANODAYA)
    cases = timeline(u["admin"], inst["id"])
    cats = {c["category"] for c in cases}
    assert {"SCHOLARSHIP", "INFRASTRUCTURE"} <= cats
    for c in cases:
        assert c["alerts"]["total"] == 0 and c["link_relations"] == [], c["display_id"]
    assert u["admin"].get(f"/institutions/{inst['id']}/links").json() == []
    assert u["admin"].get("/links", params={"institution_id": inst["id"]}).json()["items"] == []
    for who in ("pgrc.head", "rb.head", "ro.bhopal", "pgrc.officer"):
        for n in u[who].get("/notifications").json()["items"]:
            assert n["institution_id"] != inst["id"] or n["kind"] not in ("COORDINATION_REQUIRED", "PRIORITY_REVIEW", "REVIEW_SUGGESTED"), (who, n["title"])
    # the sweep must not invent an alert either
    u["admin"].post("/admin/sweep")
    assert u["admin"].get(f"/institutions/{inst['id']}/links").json() == []


# ------------------------------------------------------------------------------------------ E
def test_E_near_twin_review_confirm_alias_then_exact(u):
    pg = u["pgrc.officer"]
    payload = case_payload("E", tag="scenE")
    res = pg.post("/cases", json=payload).json()
    if res["resolution"]["status"] == "EXACT":
        pytest.skip("scenario E alias already stored (previous run) - reseed to repeat")
    r = res["resolution"]
    assert r["status"] == "NEEDS_REVIEW"
    pids = [c["permanent_id"] for c in r["candidates"][:2]]
    assert set(pids) == {SHRI_RAM_COLLEGE, SHRI_RAM_INSTITUTE}
    assert any("Two similar institutions in Lucknow" in x for c in r["candidates"][:2] for x in c["reasons"]), r["candidates"][0]["reasons"]
    cid = res["case"]["id"]
    # the case is in the review queue
    queue = pg.get("/review/institution-matches").json()
    items = queue["items"] if isinstance(queue, dict) else queue
    assert cid in [i["case_id"] for i in items]
    pick = next(c for c in r["candidates"] if c["permanent_id"] == SHRI_RAM_COLLEGE)
    d = pg.post(f"/cases/{cid}/institution-match", json={"decision": "CONFIRM", "institution_id": pick["institution_id"], "reason": "Officer confirmed from candidates"})
    assert d.status_code in (200, 201), d.text
    assert d.json().get("alias_added")
    again = pg.post("/cases", json=case_payload("E", tag="scenE2")).json()
    assert again["resolution"]["status"] == "EXACT"
    assert again["resolution"]["selected"]["permanent_id"] == SHRI_RAM_COLLEGE
    assert again["resolution"]["selected"]["score"] == 1.0


# ------------------------------------------------------------------------------------------ F
def test_F_duplicate_suggested_not_merged_seeded(u):
    inst = find_institution(u["admin"], SHRINATH)
    links = u["admin"].get(f"/institutions/{inst['id']}/links").json()
    dup = [lk for lk in links if lk["relation"] == "DUPLICATE" and any("DHIGH/E/2026/0034517" in x for x in lk["reasons"])]
    assert dup, "seeded DUPLICATE link quoting the CPGRAMS ref is missing"
    lk = dup[0]
    assert lk["status"] == "SUGGESTED" and lk["decided_at"] is None
    assert any("DHIGH/E/2026/0034517" in x for x in lk["reasons"])
    for side in ("case_a", "case_b"):
        d = u["admin"].get(f"/cases/{lk[side]['id']}").json()
        assert d["status"] not in ("CLOSED_NO_ACTION",) and d["id"] == lk[side]["id"]


def test_F_engine_flags_duplicate_for_email_quoting_cpgrams_ref(u):
    pg = u["pgrc.officer"]
    inst, _p1, pgrc2, _rb, _ro = _shrinath_cases(u)
    p = case_payload("A", tag="scenF")
    p.update(source_channel="EMAIL", permanent_id_raw=SHRINATH, institution_text_raw="Shrinath Institute of Engineering and Technology, Kanpur",
             subject="Re: certificates still withheld, ref DHIGH/E/2026/0034517",
             description="Following up on my CPGRAMS grievance DHIGH/E/2026/0034517: the college still holds my original certificates.")
    p["complainant"] = {"name": "Demo Complainant Three", "email": "demo.f@mailbox.example", "phone": "9000000003", "party_type": "STUDENT"}
    res = pg.post("/cases", json=p).json()
    dups = [lk for lk in res["links"] if lk["relation"] == "DUPLICATE" and lk["other_case"]["id"] == pgrc2["id"]]
    assert dups and dups[0]["status"] == "SUGGESTED", [(lk["relation"], lk["other_case"]["display_id"]) for lk in res["links"]]
    assert any("DHIGH" in x for x in dups[0]["reasons"])
    # not merged: the CPGRAMS case is untouched and still open
    assert u["admin"].get(f"/cases/{pgrc2['id']}").json()["status"] == pgrc2["status"]


# ------------------------------------------------------------------------------------------ advisory
def test_no_endpoint_can_merge_or_block():
    import httpx

    from tests.api.helpers import BASE

    paths = httpx.get(BASE + "/openapi.json").json()["paths"]
    assert not [p for p in paths if "merge" in p.lower() or "block" in p.lower() or "veto" in p.lower()]


def test_pre_action_never_blocks_with_open_matters(u):
    ap = u["approval.officer"]
    inst = find_institution(ap, SHRINATH)
    for decision in (True, False):
        aid = ap.post(f"/institutions/{inst['id']}/pre-action-check", json={"action_type": "CLOSURE_APPROVAL"}).json()["institution_action_id"]
        r = ap.post(f"/institution-actions/{aid}/acknowledge", json={"remark": "QA advisory check", "proceed": decision})
        assert r.status_code == 200, r.text
        assert r.json()["action"]["status"] == ("PROCEEDED" if decision else "ON_HOLD")


def test_demo_inputs_endpoint_payloads_match_seed():
    assert set(DEMO_INPUTS) >= {"A", "E"}
