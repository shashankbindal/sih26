from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import Notification, PassportEntry, PolicyConfig
from tests.conftest import auth_headers
from tests.workflows._world import DEMO_A, build_world

API = "/api/v1"


def _setup(client, db):
    w = build_world(db)
    client.post(f"{API}/cases", json=DEMO_A, headers=auth_headers(client, w.users["pgrc"]))  # live case (Scenario A)
    return w


def test_scenario_b_panel_clearances_ack_and_hold(client, db):
    w = _setup(client, db)
    u = w.users
    inst = w.inst["A"]
    ap = auth_headers(client, u["approval"])
    pg = auth_headers(client, u["pgrc"])
    vg = auth_headers(client, u["vig"])
    rb = auth_headers(client, u["rb"])

    # role gate: PGRC officer cannot start a Pre-Action Check (may view)
    assert client.post(f"{API}/institutions/{inst.id}/pre-action-check", json={"action_type": "SECURITY_DEPOSIT_RELEASE"}, headers=pg).status_code == 403

    r = client.post(f"{API}/institutions/{inst.id}/pre-action-check", json={"action_type": "SECURITY_DEPOSIT_RELEASE"}, headers=ap)
    assert r.status_code == 201, r.text
    panel = r.json()
    aid = panel["institution_action_id"]
    assert panel["summary"]["total_open"] == 5  # 4 seeded-style matters + the case just created
    assert panel["summary"]["by_bureau"] == {"PGRC": 3, "RB": 1, "RO": 1}
    assert panel["summary"]["overdue"] >= 1
    assert panel["advisory"] == "Advisory only. The competent authority decides."
    assert panel["rule_note"].startswith("APH 2024-27 · Security-deposit release procedure")
    pg1 = next(m for m in panel["open_matters"] if m["display_id"] == w.cases["PGRC-1"].display_id)
    assert pg1["relevance"] == "HIGH" and pg1["pending_days"] == 11 and pg1["pending_step"] == "INSTITUTION_ATR"
    assert "7-day" in pg1["why"] and "overdue" in pg1["why"]
    assert any(c["clock"] == "INST_REFUND_7D" and c["state"] == "BREACHED" and "overdue 4 days" in c["label"] for c in pg1["clocks"])
    rb1 = next(m for m in panel["open_matters"] if m["owner_bureau"] == "RB")
    assert rb1["relevance"] in ("MEDIUM", "LOW") and panel["open_matters"][0]["relevance"] == "HIGH"
    order = [m["relevance"] for m in panel["open_matters"]]
    assert order == sorted(order, key=["HIGH", "MEDIUM", "LOW"].index)
    assert [(s["bureau"], s["state"]) for s in panel["clearance_chain"]] == [
        ("PGRC", "NOT_REQUESTED"), ("VIGILANCE", "NOT_REQUESTED"), ("APPROVAL", "PENDING_PREVIOUS"),
    ]
    assert panel["clearance_chain"][2]["label"] == "Approval Bureau NOC"

    # request PGRC clearance; duplicate pending request refused; appears in PGRC inbox only
    r = client.post(f"{API}/institution-actions/{aid}/clearances", json={"target_bureau": "PGRC", "remark": "Please confirm no dues"}, headers=ap)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["step_order"] == 1 and r.json()["request_remark"] == "Please confirm no dues"
    assert client.post(f"{API}/institution-actions/{aid}/clearances", json={"target_bureau": "PGRC"}, headers=ap).status_code == 409
    inbox = client.get(f"{API}/clearances?inbox=me", headers=pg).json()
    assert inbox["total"] == 1
    item = inbox["items"][0]
    assert item["snapshot_summary"]["total_open"] == 5 and item["requested_by"]["name"] == "Sandeep Kulkarni"
    assert client.get(f"{API}/clearances?inbox=me", headers=vg).json()["total"] == 0
    assert client.get(f"{API}/clearances?inbox=me&status=CLEARED", headers=pg).json()["total"] == 0
    n = db.scalar(select(Notification).where(Notification.kind == "CLEARANCE_REQUEST"))
    assert n.bureau.value == "PGRC" and n.user_id is None
    # only the target bureau may respond
    assert client.post(f"{API}/clearances/{cid}/respond", json={"response": "CLEARED", "remarks": "ok"}, headers=rb).status_code == 403
    assert client.post(f"{API}/clearances/{cid}/respond", json={"response": "NOT_CLEARED"}, headers=pg).status_code == 422
    r = client.post(f"{API}/clearances/{cid}/respond", json={"response": "CLEARED_WITH_REMARKS", "remarks": "Refund pending; proceed after ATR"}, headers=pg)
    assert r.status_code == 200 and r.json()["response"] == "CLEARED_WITH_REMARKS"
    assert client.post(f"{API}/clearances/{cid}/respond", json={"response": "CLEARED", "remarks": "x"}, headers=pg).status_code == 409
    resp = db.scalar(select(Notification).where(Notification.kind == "CLEARANCE_RESPONSE"))
    assert resp.user_id == u["approval"].id and resp.link_path == "/clearances"

    detail = client.get(f"{API}/institution-actions/{aid}", headers=rb).json()
    assert detail["clearance_chain"][0]["state"] == "CLEARED_WITH_REMARKS"
    assert detail["clearance_chain"][2]["state"] == "PENDING_PREVIOUS"
    assert detail["panel"]["summary"]["total_open"] == 5

    # vigilance step then Approval NOC becomes available
    r = client.post(f"{API}/institution-actions/{aid}/clearances", json={"target_bureau": "VIGILANCE"}, headers=ap)
    client.post(f"{API}/clearances/{r.json()['id']}/respond", json={"response": "CLEARED", "remarks": "No vigilance matter"}, headers=vg)
    chain = client.get(f"{API}/institution-actions/{aid}", headers=ap).json()["clearance_chain"]
    assert [s["state"] for s in chain] == ["CLEARED_WITH_REMARKS", "CLEARED", "NOT_REQUESTED"]

    # acknowledgement: required only to proceed
    r = client.post(f"{API}/institution-actions/{aid}/acknowledge", json={"proceed": True, "acknowledged": False}, headers=ap)
    assert r.status_code == 422
    assert client.post(f"{API}/institution-actions/{aid}/acknowledge", json={"proceed": True, "remark": "x"}, headers=rb).status_code == 403
    r = client.post(f"{API}/institution-actions/{aid}/acknowledge", json={"proceed": True, "remark": "Seen all five"}, headers=ap)
    assert r.status_code == 200, r.text
    assert r.json()["action"]["status"] == "PROCEEDED"
    pe = r.json()["passport_entry"]
    assert pe["event"] == "PREACTION_ACKNOWLEDGED"
    assert pe["payload"]["summary"] == "Proceeded with 5 open matters acknowledged"
    assert client.post(f"{API}/institution-actions/{aid}/acknowledge", json={"proceed": False}, headers=ap).status_code == 409

    p = client.get(f"{API}/institution-actions/{aid}/passport", headers=ap).json()
    assert [e["event"] for e in p["entries"]] == [
        "PREACTION_CHECK_SHOWN", "CLEARANCE_REQUESTED", "CLEARANCE_RESPONDED",
        "CLEARANCE_REQUESTED", "CLEARANCE_RESPONDED", "PREACTION_ACKNOWLEDGED",
    ]
    v = client.get(f"{API}/institution-actions/{aid}/passport/verify", headers=ap).json()
    assert v["ok"] is True and v["count"] == 6
    # action chains never mix into case chains
    assert all(e.case_id is not None for e in db.scalars(select(PassportEntry).where(PassportEntry.case_id.is_not(None))))

    # hold needs no acknowledgement and never depends on open matters
    r = client.post(f"{API}/institutions/{inst.id}/pre-action-check", json={"action_type": "SHOW_CAUSE"}, headers=ap)
    aid2 = r.json()["institution_action_id"]
    assert r.json()["clearance_chain"] == []
    r = client.post(f"{API}/institution-actions/{aid2}/acknowledge", json={"proceed": False, "acknowledged": False, "remark": "Waiting for PGRC"}, headers=ap)
    assert r.status_code == 200 and r.json()["action"]["status"] == "ON_HOLD"
    assert "on hold" in r.json()["passport_entry"]["payload"]["summary"].lower()

    # listing + filters
    lst = client.get(f"{API}/institution-actions?institution_id={inst.id}", headers=pg).json()
    assert lst["total"] == 2
    assert client.get(f"{API}/institution-actions?status=ON_HOLD", headers=pg).json()["total"] == 1
    assert client.get(f"{API}/institution-actions?bureau=APPROVAL&institution_id={inst.id}", headers=pg).json()["total"] == 2


def test_rule_note_comes_from_policy_config(client, db):
    w = _setup(client, db)
    row = db.get(PolicyConfig, "clause_labels")
    row.value = {"refund": "REFUND-LABEL-X", "deposit": "DEPOSIT-LABEL-Y"}
    db.commit()
    ap = auth_headers(client, w.users["approval"])
    r = client.post(f"{API}/institutions/{w.inst['A'].id}/pre-action-check", json={"action_type": "SECURITY_DEPOSIT_RELEASE"}, headers=ap)
    assert r.json()["rule_note"].startswith("DEPOSIT-LABEL-Y")
    r = client.post(f"{API}/institutions/{w.inst['A'].id}/pre-action-check", json={"action_type": "CLOSURE_APPROVAL"}, headers=ap)
    assert r.json()["rule_note"].startswith("REFUND-LABEL-X")
    # engine/clock text also follows the config
    case = client.get(f"{API}/cases/{w.cases['PGRC-1'].id}", headers=auth_headers(client, w.users["pgrc2"])).json()
    assert any("REFUND-LABEL-X" in a for a in case["suggested_actions"])
    assert uuid.UUID(r.json()["institution_action_id"])
