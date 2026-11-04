"""Every state-changing call must append a Passport entry or an audit_log row (project audit rule), and chains must verify."""

from __future__ import annotations

import uuid

import pytest

from tests.api.helpers import audit_count, case_payload, find_institution, passport_count, verify

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(scope="module")
def fresh_case(u) -> dict:
    """A new RB-owned case (so the RB officer may write) on Shrinath."""
    p = case_payload("A", tag="audit")
    p["owner_bureau"] = "PGRC"
    r = u["pgrc.officer"].post("/cases", json=p)
    assert r.status_code == 201, r.text
    return r.json()["case"]


def test_remark_patch_atr_transfer_dispose_each_add_one_passport_entry(u, fresh_case):
    pg, rb = u["pgrc.officer"], u["rb.officer"]
    cid = fresh_case["id"]
    n = passport_count(pg, cid)

    r = pg.post(f"/cases/{cid}/remarks", json={"remark": "QA: called the institution registrar", "attachment_name": "note.pdf"})
    assert r.status_code == 201, r.text
    n += 1
    assert passport_count(pg, cid) == n

    r = pg.patch(f"/cases/{cid}", json={"status": "UNDER_PROCESS", "remark": "QA: taking up"})
    assert r.status_code == 200, r.text
    n += 1
    assert passport_count(pg, cid) == n

    r = pg.patch(f"/cases/{cid}", json={"pending_step": "INSTITUTION_ATR", "status": "AWAITING_ATR"})
    assert r.status_code == 200, r.text
    assert passport_count(pg, cid) > n
    n = passport_count(pg, cid)

    r = pg.post(f"/cases/{cid}/atr-received", json={"remark": "QA: ATR received"})
    assert r.status_code in (200, 201), r.text
    assert passport_count(pg, cid) == n + 1
    n += 1

    r = pg.post(f"/cases/{cid}/transfer", json={"to_bureau": "RB", "remark": "QA: belongs to RB scrutiny"})
    assert r.status_code in (200, 201), r.text
    assert passport_count(pg, cid) == n + 1
    n += 1
    assert r.json()["owner_bureau"] == "RB" if "owner_bureau" in r.json() else True

    r = rb.post(f"/cases/{cid}/dispose", json={"remark": "QA: disposed after review"})
    assert r.status_code in (200, 201), r.text
    assert passport_count(rb, cid) == n + 1
    assert rb.get(f"/cases/{cid}").json()["status"] in ("DISPOSED", "CLOSED_NO_ACTION")

    v = verify(rb, cid)
    assert v["ok"] is True and v["first_bad_seq"] is None and v["count"] == passport_count(rb, cid)


def test_post_cases_chain_verifies(u):
    p = u["pgrc.officer"]
    r = p.post("/cases", json=case_payload("A", tag="chain"))
    cid = r.json()["case"]["id"]
    v = verify(p, cid)
    assert v["ok"] and v["count"] >= 2


def test_failed_write_adds_no_entry(u, fresh_case):
    pg = u["pgrc.officer"]
    r = pg.post("/cases", json=case_payload("A", tag="fail", category="NOT_A_CATEGORY"))
    assert r.status_code == 422
    n = passport_count(u["admin"], fresh_case["id"])
    assert u["approval.officer"].post(f"/cases/{fresh_case['id']}/remarks", json={"remark": "forbidden probe write"}).status_code == 403
    assert passport_count(u["admin"], fresh_case["id"]) == n


def test_link_decision_revert_and_thread_are_logged(u):
    """Confirm / Reject / Defer + revert write Passport entries (and audit_log rows)."""
    pg = u["pgrc.officer"]
    r = pg.post("/cases", json=case_payload("A", tag="linkdec"))
    body = r.json()
    cid = body["case"]["id"]
    assert body["links"], "scenario A should yield links"
    link = body["links"][0]
    lid = link["link_id"]
    n = passport_count(pg, cid)
    a0 = audit_count()
    d = pg.post(f"/links/{lid}/decision", json={"decision": "CONFIRM", "reason": "QA confirm: same fee matter"})
    assert d.status_code in (200, 201), d.text
    n1 = passport_count(pg, cid)
    a1 = audit_count()
    assert n1 > n or (a0 is not None and a1 > a0), "link decision left no trace"
    assert pg.post(f"/links/{lid}/decision", json={"decision": "REJECT", "reason": "short"}).status_code in (200, 201, 422)
    rv = pg.post(f"/links/{lid}/revert", json={"reason": "QA revert to previous state"})
    assert rv.status_code in (200, 201), rv.text
    assert passport_count(pg, cid) > n1 or (a1 is not None and audit_count() > a1)
    m = pg.post(f"/links/{lid}/thread/messages", json={"body": "QA note on thread"})
    assert m.status_code in (200, 201), m.text
    assert verify(pg, cid)["ok"]


def test_link_decision_requires_reason(u):
    pg = u["pgrc.officer"]
    r = pg.post("/cases", json=case_payload("A", tag="linkreason"))
    lid = r.json()["links"][0]["link_id"]
    assert pg.post(f"/links/{lid}/decision", json={"decision": "CONFIRM", "reason": ""}).status_code == 422
    assert pg.post(f"/links/{lid}/decision", json={"decision": "MERGE", "reason": "advisory engine: no merge verb"}).status_code == 422


def test_preaction_and_clearance_chain_logged(u):
    ap = u["approval.officer"]
    inst = find_institution(ap, "1-4463974255")
    a = ap.post(f"/institutions/{inst['id']}/pre-action-check", json={"action_type": "SECURITY_DEPOSIT_RELEASE"})
    assert a.status_code == 201, a.text
    aid = a.json()["institution_action_id"]

    def n():
        e = ap.get(f"/institution-actions/{aid}/passport").json()["entries"]
        return len(e)

    assert n() == 1
    c = ap.post(f"/institution-actions/{aid}/clearances", json={"target_bureau": "PGRC", "remark": "QA clearance"})
    assert c.status_code == 201, c.text
    assert n() == 2
    resp = u["pgrc.officer"].post(f"/clearances/{c.json()['id']}/respond", json={"response": "CLEARED_WITH_REMARKS", "remarks": "QA: dues pending, proceed with care"})
    assert resp.status_code == 200, resp.text
    assert n() == 3
    ack = ap.post(f"/institution-actions/{aid}/acknowledge", json={"remark": "QA ack", "proceed": True})
    assert ack.status_code == 200, ack.text
    assert n() == 4
    ev = ap.get(f"/institution-actions/{aid}/passport").json()["entries"]
    assert [e["event"] for e in ev] == ["PREACTION_CHECK_SHOWN", "CLEARANCE_REQUESTED", "CLEARANCE_RESPONDED", "PREACTION_ACKNOWLEDGED"], [e["event"] for e in ev]
    v = ap.get(f"/institution-actions/{aid}/passport/verify").json()
    assert v["ok"] and v["count"] == 4
    ev_ack = ev[-1]["payload"]
    assert str(ack.json()["action"]["open_matter_count"]) in ack.json()["passport_entry"]["payload"]["summary"]
    assert "Proceeded" in ack.json()["passport_entry"]["payload"]["summary"], ack.json()["passport_entry"]["payload"]
    assert ev_ack["proceed"] is True


def test_double_respond_is_rejected(u):
    ap = u["approval.officer"]
    inst = find_institution(ap, "1-4471203398")
    aid = ap.post(f"/institutions/{inst['id']}/pre-action-check", json={"action_type": "SHOW_CAUSE"}).json()["institution_action_id"]
    cid = ap.post(f"/institution-actions/{aid}/clearances", json={"target_bureau": "PGRC"}).json()["id"]
    pg = u["pgrc.officer"]
    assert pg.post(f"/clearances/{cid}/respond", json={"response": "NOT_CLEARED", "remarks": "QA first"}).status_code == 200
    again = pg.post(f"/clearances/{cid}/respond", json={"response": "CLEARED", "remarks": "QA second"})
    assert again.status_code in (409, 422), again.status_code
    assert pg.post(f"/clearances/{cid}/respond", json={"response": "MAYBE"}).status_code == 422


def test_institution_create_alias_and_config_write_audited(u):
    ad = u["admin"]
    before = audit_count()
    name = f"QA Test Institute {uuid.uuid4().hex[:5]}"
    r = ad.post("/institutions", json={"name": name, "district": "Kanpur Nagar", "state": "Uttar Pradesh", "ro_code": "KNP", "pincode": "208017"})
    assert r.status_code in (200, 201), r.text
    iid = r.json()["id"]
    mid = audit_count()
    a = ad.post(f"/institutions/{iid}/aliases", json={"alias_raw": f"QA Alias {uuid.uuid4().hex[:4]}"})
    assert a.status_code in (200, 201), a.text
    after_alias = audit_count()
    cfg = ad.get("/admin/config/thresholds").json()
    value = cfg.get("value", cfg)
    w = ad.put("/admin/config/thresholds", json={"value": value})
    assert w.status_code == 200, w.text
    after_cfg = audit_count()
    if before is None:
        pytest.skip("audit_log not reachable from the test host")
    assert mid > before, "POST /institutions wrote no audit_log row"
    assert after_alias > mid, "POST /institutions/{id}/aliases wrote no audit_log row"
    assert after_cfg > after_alias, "PUT /admin/config wrote no audit_log row"


def test_sweep_and_login_audited(u):
    before = audit_count()
    r = u["admin"].post("/admin/sweep")
    assert r.status_code == 200, r.text
    assert {"pairs_checked", "new_links", "superseded"} <= set(r.json())
    mid = audit_count()
    from tests.api.helpers import login

    login("pgrc.head")
    end = audit_count()
    if before is None:
        pytest.skip("audit_log not reachable")
    assert mid > before, "sweep wrote no audit_log row"
    assert end > mid, "login wrote no audit_log row"


def test_institution_match_decision_audited(u):
    """Scenario E: confirming an institution match writes audit/passport."""
    pg = u["pgrc.officer"]
    from tests.api.helpers import DEMO_INPUTS

    p = case_payload("E", tag="auditE", institution_text_raw="Sri Ram College Lucknow UP")
    res = pg.post("/cases", json=p).json()
    if res["resolution"]["status"] != "NEEDS_REVIEW":
        pytest.skip("alias for this text already stored by a previous run; reseed to repeat")
    cid = res["case"]["id"]
    cand = res["resolution"]["candidates"][0]
    n = passport_count(pg, cid)
    a0 = audit_count()
    r = pg.post(f"/cases/{cid}/institution-match", json={"decision": "CONFIRM", "institution_id": cand["institution_id"], "reason": "QA confirm exact twin"})
    assert r.status_code in (200, 201), r.text
    assert passport_count(pg, cid) > n or (a0 is not None and audit_count() > a0)
    assert verify(pg, cid)["ok"]
    assert DEMO_INPUTS
