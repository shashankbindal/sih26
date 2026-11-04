from __future__ import annotations

import time

from sqlalchemy import func, select

from app.models import AuditLog, Case, Notification, PassportEntry
from app.services import passport
from tests.conftest import auth_headers
from tests.workflows._world import DEMO_A, build_world

API = "/api/v1"


def _post_demo_a(client, db, w):
    h = auth_headers(client, w.users["pgrc"])
    t0 = time.perf_counter()
    r = client.post(f"{API}/cases", json=DEMO_A, headers=h)
    ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 201, r.text
    return r.json(), ms


def test_scenario_a_full_pipeline(client, db):
    w = build_world(db)
    body, ms = _post_demo_a(client, db, w)
    print(f"POST /cases latency {ms:.0f} ms")
    res = body["resolution"]
    assert res["status"] == "AUTO_SUGGESTED"
    assert res["selected"]["permanent_id"] == "1-4463974255"
    assert res["selected"]["score"] >= 0.92
    assert len(res["candidates"]) >= 1 and res["candidates"][0]["reasons"]
    assert any("shrinath" in r.lower() for r in res["candidates"][0]["reasons"])
    assert body["category_suggestion"]["category"] == "FEE_REFUND"
    assert body["case"]["category"] == "FEE_REFUND"

    rel = {ln["other_case"]["display_id"]: ln["relation"] for ln in body["links"]}
    pg1, ro1, rb1 = (w.cases[k].display_id for k in ("PGRC-1", "RO-1", "RB-1"))
    assert rel[pg1] == "RELATED"
    assert rel[ro1] == "RELATED"
    assert rb1 not in rel  # no alert for the scrutiny matter
    assert rb1 in {u["other_case"]["display_id"] for u in body["unrelated"]}
    assert all(ln["suggested_next_action"] for ln in body["links"])

    assert [c["clock"] for c in body["clocks"]] == ["CSS_72H"]
    assert body["clocks"][0]["state"] == "ON_TRACK"

    case_id = body["case"]["id"]
    # Passport chain: RECEIVED, ASSIGNED, LINK_SUGGESTED per link; verifies
    import uuid

    entries = passport.list_entries(db, case_id=uuid.UUID(case_id))
    events = [e.event for e in entries]
    assert events[:2] == ["RECEIVED", "ASSIGNED"]
    assert events.count("LINK_SUGGESTED") == len(body["links"])
    assert passport.verify_chain(db, case_id=uuid.UUID(case_id))["ok"]
    # the other case's chain also records the suggestion
    other = passport.list_entries(db, case_id=w.cases["PGRC-1"].id)
    assert "LINK_SUGGESTED" in [e.event for e in other]
    assert passport.verify_chain(db, case_id=w.cases["PGRC-1"].id)["ok"]

    # notifications: both owner officers of a RELATED pair
    kinds = {
        (n.user_id, n.kind) for n in db.scalars(select(Notification).where(Notification.kind == "COORDINATION_REQUIRED"))
    }
    assert (w.users["pgrc"].id, "COORDINATION_REQUIRED") in kinds
    assert (w.users["pgrc2"].id, "COORDINATION_REQUIRED") in kinds
    assert (w.users["ro_knp"].id, "COORDINATION_REQUIRED") in kinds
    n = db.scalar(select(Notification).where(Notification.user_id == w.users["ro_knp"].id))
    assert n.link_path.startswith("/coordination/")
    # complainant stored with party hash, PII visible to the owner
    assert body["case"]["complainant"]["name"] == "Demo Complainant"
    assert body["case"]["description_norm"]


def test_privacy_masked_for_other_bureau_and_list_link_relations(client, db):
    w = build_world(db)
    body, _ = _post_demo_a(client, db, w)
    rb = auth_headers(client, w.users["rb"])
    r = client.get(f"{API}/cases/{body['case']['id']}", headers=rb)
    assert r.status_code == 200
    d = r.json()
    assert d["masked"] is True
    assert d["complainant"]["name"] is None and d["complainant"]["email"] is None
    assert d["description"] is None and d["description_norm"] is None
    lst = client.get(f"{API}/cases?institution_id={w.inst['A'].id}", headers=rb).json()["items"]
    mine = next(i for i in lst if i["id"] == body["case"]["id"])
    assert mine["link_relations"] == ["RELATED"]


def test_dry_run_resolve_persists_nothing(client, db):
    w = build_world(db)
    before = db.scalar(select(func.count()).select_from(Case))
    h = auth_headers(client, w.users["pgrc"])
    r = client.post(
        f"{API}/intake/resolve",
        json={"institution_text_raw": "Shrinath Engg College Kanpur", "subject": "refund", "description": "fees wapas nahi"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["resolution"]["selected"]["permanent_id"] == "1-4463974255"
    assert j["category_suggestion"]["category"] == "FEE_REFUND"
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Case)) == before


def test_classify_and_parse_email(client, db):
    w = build_world(db)
    h = auth_headers(client, w.users["pgrc"])
    r = client.post(f"{API}/intake/classify", json={"subject": "Refund", "description": "fee refund not received"}, headers=h)
    assert r.json()["category"] == "FEE_REFUND"
    raw = (
        "From: Asha Verma <asha.verma@mailbox.example>\n"
        "Subject: Fee refund pending - Shrinath Engineering College Kanpur\n"
        "Date: Tue, 27 Oct 2026 10:15:00 +0530\n\n"
        "Respected Sir,\nI am writing about Shrinath Engineering College, Kanpur (Permanent ID 1-4463974255). "
        "I had filed CPGRAMS grievance DHIGH/E/2026/0034517 earlier. My fees have not been refunded.\n"
    )
    r = client.post(f"{API}/intake/parse-email", json={"raw_text": raw}, headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    d = j["detected"]
    assert d["sender_email"] == "asha.verma@mailbox.example"
    assert d["permanent_id"] == "1-4463974255"
    assert d["cpgrams_refs"] == ["DHIGH/E/2026/0034517"]
    assert d["institution_mention"] and "Shrinath" in d["institution_mention"]
    assert j["prefill"]["source_channel"] == "EMAIL"
    assert j["prefill"]["institution_text_raw"] == d["institution_mention"]
    assert j["category_suggestion"]["category"] == "FEE_REFUND"


def test_scenario_f_duplicate_via_quoted_cpgrams_ref(client, db):
    w = build_world(db)
    h = auth_headers(client, w.users["pgrc"])
    payload = {
        "source_channel": "EMAIL",
        "institution_text_raw": "Shrinath Institute of Engineering & Technology, Kanpur",
        "permanent_id_raw": "1-4463974255",
        "complainant": {"name": "Parent X", "email": "parent.x@mailbox.example", "party_type": "PARENT"},
        "subject": "Certificates still not returned",
        "description": "Following up my CPGRAMS grievance DHIGH/E/2026/0034517: the college still holds my son's certificates.",
        "owner_bureau": "PGRC",
    }
    r = client.post(f"{API}/cases", json=payload, headers=h)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["resolution"]["status"] == "EXACT"
    dup = [ln for ln in j["links"] if ln["relation"] == "DUPLICATE"]
    assert len(dup) == 1 and dup[0]["other_case"]["display_id"] == w.cases["PGRC-2"].display_id
    assert any("DHIGH/E/2026/0034517" in x for x in dup[0]["reasons"])
    n = db.scalar(select(Notification).where(Notification.kind == "REVIEW_SUGGESTED"))
    assert n is not None
    # never merged: both cases remain separate, status unchanged
    assert db.get(Case, w.cases["PGRC-2"].id).status.value == "UNDER_PROCESS"
    # confirming the duplicate starts the CPGRAMS 21-day clock on the email case (policy rule)
    assert [c["clock"] for c in j["clocks"]] == []
    link_id = dup[0]["link_id"]
    r = client.post(f"{API}/links/{link_id}/decision", json={"decision": "CONFIRM", "reason": "Same parent, same grievance"}, headers=h)
    assert r.status_code == 200, r.text
    case = client.get(f"{API}/cases/{j['case']['id']}", headers=h).json()
    assert "CPGRAMS_21D" in [c["clock"] for c in case["clocks"]]


def test_case_writes_and_permissions(client, db):
    w = build_world(db)
    pg1 = w.cases["PGRC-1"]
    owner = auth_headers(client, w.users["pgrc2"])
    rb = auth_headers(client, w.users["rb"])
    mgmt = auth_headers(client, w.users["mgmt"])

    # non-owner cannot edit, dispose, transfer, remark, atr
    for path, body, method in (
        (f"/cases/{pg1.id}", {"status": "UNDER_PROCESS"}, "patch"),
        (f"/cases/{pg1.id}/dispose", {"remark": "closing"}, "post"),
        (f"/cases/{pg1.id}/transfer", {"to_bureau": "RB", "remark": "x"}, "post"),
        (f"/cases/{pg1.id}/remarks", {"remark": "x"}, "post"),
        (f"/cases/{pg1.id}/atr-received", {}, "post"),
    ):
        for hdr in (rb, mgmt):
            r = getattr(client, method)(f"{API}{path}", json=body, headers=hdr)
            assert r.status_code == 403, (path, r.text)

    # owner: remark, then ATR received marks INST_REFUND_7D MET
    r = client.post(f"{API}/cases/{pg1.id}/remarks", json={"remark": "Reminder sent to institution", "attachment_name": "letter.pdf"}, headers=owner)
    assert r.status_code == 201, r.text
    before = client.get(f"{API}/cases/{pg1.id}", headers=owner).json()
    assert any(c["clock"] == "INST_REFUND_7D" and c["state"] == "BREACHED" for c in before["clocks"])
    r = client.post(f"{API}/cases/{pg1.id}/atr-received", json={"remark": "ATR received by email"}, headers=owner)
    assert r.status_code == 200, r.text
    after = r.json()
    assert any(c["clock"] == "INST_REFUND_7D" and c["state"] == "MET" for c in after["clocks"])
    assert after["pending_step"] == "NONE" and after["status"] == "UNDER_PROCESS"
    events = [e.event for e in passport.list_entries(db, case_id=pg1.id)]
    assert "REMARK" in events and "ATR_RECEIVED" in events

    # PATCH: category + pending step (starts the refund clock only when it qualifies) + officer
    r = client.patch(f"{API}/cases/{pg1.id}", json={"status": "AWAITING_COMPLAINANT", "pending_action": "Awaiting bank proof"}, headers=owner)
    assert r.status_code == 200 and r.json()["status"] == "AWAITING_COMPLAINANT"
    r = client.patch(f"{API}/cases/{pg1.id}", json={"owner_officer_id": str(w.users["pgrc"].id)}, headers=owner)
    assert r.status_code == 200 and r.json()["owner_officer"]["name"] == "Ritu Sharma"
    r = client.patch(f"{API}/cases/{pg1.id}", json={"owner_officer_id": str(w.users["rb"].id)}, headers=owner)
    assert r.status_code == 422  # officer of another bureau

    # transfer to RB
    r = client.post(f"{API}/cases/{pg1.id}/transfer", json={"to_bureau": "RB", "remark": "Regulatory angle"}, headers=auth_headers(client, w.users["pgrc"]))
    assert r.status_code == 200, r.text
    assert r.json()["owner_bureau"] == "RB" and r.json()["status"] == "TRANSFERRED"
    assert r.json()["owner_officer"]["name"] == "Karthik Iyer"
    # the old owner can no longer edit
    r = client.patch(f"{API}/cases/{pg1.id}", json={"status": "UNDER_PROCESS"}, headers=owner)
    assert r.status_code == 403

    # dispose by the new owner: CPGRAMS clock MET on a CPGRAMS case
    pg2 = w.cases["PGRC-2"]
    r = client.post(f"{API}/cases/{pg2.id}/dispose", json={"remark": "Certificates returned"}, headers=owner)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "DISPOSED" and d["disposed_at"]
    assert any(c["clock"] == "CPGRAMS_21D" and c["state"] == "MET" for c in d["clocks"])
    assert client.post(f"{API}/cases/{pg2.id}/dispose", json={"remark": "again"}, headers=owner).status_code == 409
    # reopen
    r = client.patch(f"{API}/cases/{pg2.id}", json={"status": "REOPENED", "remark": "Parent re-complained"}, headers=owner)
    assert r.status_code == 200 and r.json()["status"] == "REOPENED"
    for case in (pg1, pg2):
        v = passport.verify_chain(db, case_id=case.id)
        assert v["ok"], v
    ev2 = [e.event for e in passport.list_entries(db, case_id=pg2.id)]
    assert "DISPOSED" in ev2 and "REOPENED" in ev2


def test_every_state_change_leaves_passport_or_audit(client, db):
    w = build_world(db)
    h = auth_headers(client, w.users["pgrc2"])
    pg1 = w.cases["PGRC-1"]
    base = db.scalar(select(func.count()).select_from(PassportEntry))
    client.patch(f"{API}/cases/{pg1.id}", json={"category": "CERTIFICATE_WITHHELD"}, headers=h)
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(PassportEntry)) == base + 1
    # institution create writes an audit_log row
    admin = auth_headers(client, w.users["admin"])
    n_audit = db.scalar(select(func.count()).select_from(AuditLog))
    r = client.post(f"{API}/institutions", json={"name": "Trikuta Institute of Technology", "district": "Kanpur Nagar", "state": "Uttar Pradesh", "pincode": "208001", "ro_code": "KNP"}, headers=admin)
    assert r.status_code == 201, r.text
    assert r.json()["permanent_id"].startswith("1-44")
    r2 = client.post(f"{API}/institutions/{r.json()['id']}/aliases", json={"alias_raw": "Trikuta Tech Kanpur"}, headers=admin)
    assert r2.status_code == 201 and any(a["alias_raw"] == "Trikuta Tech Kanpur" for a in r2.json()["aliases"])
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(AuditLog)) >= n_audit + 2
    assert client.post(f"{API}/institutions", json={"name": "Nope Institute"}, headers=auth_headers(client, w.users["mgmt"])).status_code == 403


def test_notifications_read_flow(client, db):
    w = build_world(db)
    _post_demo_a(client, db, w)
    h = auth_headers(client, w.users["pgrc2"])
    r = client.get(f"{API}/notifications?unread=true", headers=h).json()
    assert r["unread_count"] >= 1 and r["items"]
    nid = r["items"][0]["id"]
    assert client.post(f"{API}/notifications/{nid}/read", headers=h).status_code == 200
    r2 = client.get(f"{API}/notifications?unread=true", headers=h).json()
    assert r2["unread_count"] == r["unread_count"] - 1
    assert client.post(f"{API}/notifications/read-all", headers=h).json()["updated"] == r2["unread_count"]
    assert client.get(f"{API}/notifications?unread=true", headers=h).json()["items"] == []
    # someone else's notification is not visible
    other = auth_headers(client, w.users["rb"])
    assert client.post(f"{API}/notifications/{nid}/read", headers=other).status_code == 404


def test_description_norm_follows_description_visibility(client, db):
    """QA D1: the normalised text is the complaint body; it must be hidden exactly like `description`."""
    w = build_world(db)
    h, = (auth_headers(client, w.users["pgrc"]),)
    j = client.post(f"{API}/cases", json=DEMO_A, headers=h).json()
    cid = j["case"]["id"]
    link = next(ln for ln in j["links"] if ln["other_case"]["display_id"] == w.cases["PGRC-1"].display_id)
    rb = auth_headers(client, w.users["rb"])
    mgmt = auth_headers(client, w.users["mgmt"])
    admin = auth_headers(client, w.users["admin"])

    # non-owning bureau: both null, on the case and on both sides of the link compare
    d = client.get(f"{API}/cases/{cid}", headers=rb).json()
    assert d["description"] is None and d["description_norm"] is None
    cmp_ = client.get(f"{API}/links/{link['link_id']}", headers=rb).json()
    for side in ("case_a", "case_b"):
        assert cmp_[side]["description"] is None and cmp_[side]["description_norm"] is None
    # owning PGRC officer and ADMIN see both
    for hdr in (h, admin):
        d = client.get(f"{API}/cases/{cid}", headers=hdr).json()
        assert d["description"] and d["description_norm"]
        cmp_ = client.get(f"{API}/links/{link['link_id']}", headers=hdr).json()
        for side in ("case_a", "case_b"):
            assert cmp_[side]["description"] and cmp_[side]["description_norm"]
    # SENIOR_MGMT sees the description (no identity) and therefore its normalised text
    d = client.get(f"{API}/cases/{cid}", headers=mgmt).json()
    assert d["description"] and d["description_norm"] and d["complainant"]["name"] is None
    # a logged reveal unmasks both together
    r = client.post(f"{API}/cases/{cid}/reveal-pii", json={"reason": "Needed for coordinated reply"}, headers=rb)
    assert r.status_code == 200
    assert r.json()["description"] and r.json()["description_norm"]
    d = client.get(f"{API}/cases/{cid}", headers=rb).json()
    assert d["description"] and d["description_norm"]
