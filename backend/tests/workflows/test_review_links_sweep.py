from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import CaseLink, Institution, InstitutionAlias, Notification
from app.models.enums import Bureau, CaseCategory, PendingStep, SourceChannel
from app.services import passport
from app.services.caselink_runtime import parse_hearing_at
from app.services.links import run_sweep
from tests.conftest import auth_headers, make_institution
from tests.workflows._world import DEMO_A, add_case, build_world

API = "/api/v1"


# ---------------------------------------------------------------- Scenario E
def test_scenario_e_review_confirm_alias_then_exact(client, db):
    w = build_world(db)
    for name, pid, pin in (
        ("Shri Ram College of Engineering, Lucknow", "1-4440019921", "226010"),
        ("Shri Ram Institute of Technology, Lucknow", "1-4440019987", "226021"),
    ):
        make_institution(db, name, ro_code="KNP", district="Lucknow", state="Uttar Pradesh", permanent_id=pid, pincode=pin)
    h = auth_headers(client, w.users["pgrc"])
    payload = {
        "source_channel": "CSS",
        "institution_text_raw": "Shri Ram Engg College Lucknow",
        "complainant": {"name": "Q", "email": "q@mailbox.example", "party_type": "STUDENT"},
        "subject": "Fee refund",
        "description": "Fees not refunded after withdrawal of admission.",
        "owner_bureau": "PGRC",
    }
    r = client.post(f"{API}/cases", json=payload, headers=h)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["resolution"]["status"] == "NEEDS_REVIEW"
    assert len(j["resolution"]["candidates"]) >= 2
    assert any("Two similar institutions in Lucknow" in x for x in j["resolution"]["candidates"][0]["reasons"])
    assert j["links"] == [] and j["case"]["institution"] is None
    assert db.scalar(select(Notification).where(Notification.kind == "REVIEW_QUEUE")) is not None

    q = client.get(f"{API}/review/institution-matches", headers=h).json()
    assert q["total"] == 1
    item = q["items"][0]
    assert item["institution_text_raw"] == "Shri Ram Engg College Lucknow"
    assert item["normalised_text"] and len(item["candidates"]) >= 2

    case_id = j["case"]["id"]
    pick = next(c for c in item["candidates"] if c["permanent_id"] == "1-4440019921")
    assert client.post(f"{API}/cases/{case_id}/institution-match", json={"decision": "CONFIRM", "institution_id": pick["institution_id"], "reason": "x"}, headers=auth_headers(client, w.users["rb"])).status_code in (403, 422)
    r = client.post(
        f"{API}/cases/{case_id}/institution-match",
        json={"decision": "CONFIRM", "institution_id": pick["institution_id"], "reason": "College of Engineering is the right one"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["institution"]["permanent_id"] == "1-4440019921"
    assert out["alias_added"] == "Shri Ram Engg College Lucknow"
    assert out["case"]["institution_match_status"] == "CONFIRMED"
    alias = db.scalar(select(InstitutionAlias).where(InstitutionAlias.source == "CONFIRMED_MATCH"))
    assert alias is not None and alias.created_by == w.users["pgrc"].id
    events = [e.event for e in passport.list_entries(db, case_id=uuid.UUID(case_id))]
    assert "INSTITUTION_CONFIRMED" in events
    assert client.get(f"{API}/review/institution-matches", headers=h).json()["total"] == 0
    # deciding again is refused
    assert client.post(f"{API}/cases/{case_id}/institution-match", json={"decision": "REJECT", "reason": "oops"}, headers=h).status_code == 409

    # same text again resolves EXACT through alias memory
    r = client.post(f"{API}/cases", json=payload, headers=h)
    j2 = r.json()
    assert j2["resolution"]["status"] == "EXACT"
    assert j2["resolution"]["selected"]["permanent_id"] == "1-4440019921"
    assert any("earlier" in x.lower() or "alias" in x.lower() for x in j2["resolution"]["candidates"][0]["reasons"])
    # the second case sits on the same institution as the first: stage B ran and found the pair
    assert any(ln["other_case"]["id"] == case_id for ln in j2["links"] + [{"other_case": {"id": u["other_case"]["id"]}} for u in j2["unrelated"]])


def test_review_create_new_and_reject(client, db):
    w = build_world(db)
    h = auth_headers(client, w.users["pgrc"])
    base = {
        "source_channel": "EMAIL",
        "complainant": {"party_type": "ANONYMOUS"},
        "subject": "Unknown college complaint",
        "description": "Faculty not paid for four months.",
        "owner_bureau": "PGRC",
    }
    a = client.post(f"{API}/cases", json={**base, "institution_text_raw": "Zzyzx Vidyapeeth Nowhereville"}, headers=h).json()
    assert a["resolution"]["status"] == "UNRESOLVED"
    r = client.post(
        f"{API}/cases/{a['case']['id']}/institution-match",
        json={"decision": "CREATE_NEW", "reason": "Not in register", "new_institution": {"name": "Zzyzx Vidyapeeth", "district": "Kanpur Nagar", "state": "Uttar Pradesh", "ro_code": "KNP"}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    inst = r.json()["institution"]
    assert inst["name"] == "Zzyzx Vidyapeeth"
    assert db.scalar(select(Institution).where(Institution.name == "Zzyzx Vidyapeeth")) is not None
    b = client.post(f"{API}/cases", json={**base, "institution_text_raw": "Qwxv Mahavidyalaya Faraway"}, headers=h).json()
    r = client.post(f"{API}/cases/{b['case']['id']}/institution-match", json={"decision": "REJECT", "reason": "None of the candidates"}, headers=h)
    assert r.status_code == 200 and r.json()["case"]["institution_match_status"] == "REJECTED"


# ---------------------------------------------------------------- links
def _demo(client, w):
    h = auth_headers(client, w.users["pgrc"])
    j = client.post(f"{API}/cases", json=DEMO_A, headers=h).json()
    return h, j


def test_link_decision_versions_revert_permissions_and_compare_masking(client, db):
    w = build_world(db)
    h, j = _demo(client, w)
    link = next(ln for ln in j["links"] if ln["other_case"]["display_id"] == w.cases["PGRC-1"].display_id)
    lid = link["link_id"]
    rb = auth_headers(client, w.users["rb"])
    # RB officer sees the compare view, but PGRC complainant PII is masked
    d = client.get(f"{API}/links/{lid}", headers=rb).json()
    for side in ("case_a", "case_b"):
        assert d[side]["masked"] is True
        assert d[side]["complainant"]["name"] is None and d[side]["complainant"]["phone"] is None
    assert d["can_decide"] is False
    assert d["suggested_next_action"] and d["reasons"] and d["feature_rows"]
    assert d["thread"]["lead_bureau"] == "PGRC"
    # owner sees PII on their own case
    dd = client.get(f"{API}/links/{lid}", headers=h).json()
    own = next(s for s in (dd["case_a"], dd["case_b"]) if s["id"] == j["case"]["id"])
    assert own["complainant"]["name"] == "Demo Complainant" and dd["can_decide"] is True
    # RB cannot decide; short reason refused
    assert client.post(f"{API}/links/{lid}/decision", json={"decision": "CONFIRM", "reason": "fine ok"}, headers=rb).status_code == 403
    assert client.post(f"{API}/links/{lid}/decision", json={"decision": "CONFIRM", "reason": ""}, headers=h).status_code == 422
    # inbox: needs my decision
    inbox = client.get(f"{API}/links?needs_my_decision=true", headers=h).json()
    assert lid in [i["id"] for i in inbox["items"]]
    assert inbox["items"][0]["relation"] in ("CONFLICTING", "DUPLICATE", "RELATED")

    r = client.post(f"{API}/links/{lid}/decision", json={"decision": "CONFIRM", "reason": "Same refund matter"}, headers=h)
    assert r.status_code == 200, r.text
    v2 = r.json()
    assert v2["status"] == "CONFIRMED" and v2["version"] == 2 and v2["decided_by_name"] == "Ritu Sharma"
    assert [x["version"] for x in v2["history"]] == [1, 2] and v2["history"][-1]["current"]
    assert lid not in [i["id"] for i in client.get(f"{API}/links?needs_my_decision=true", headers=h).json()["items"]]
    for cid in (j["case"]["id"], str(w.cases["PGRC-1"].id)):
        evs = [e.event for e in passport.list_entries(db, case_id=uuid.UUID(cid))]
        assert "LINK_CONFIRMED" in evs
        assert passport.verify_chain(db, case_id=uuid.UUID(cid))["ok"]

    r = client.post(f"{API}/links/{lid}/decision", json={"decision": "REJECT", "reason": "Actually different"}, headers=h)
    assert r.json()["status"] == "REJECTED" and r.json()["version"] == 3
    # revert restores the previous version's status (CONFIRMED) as a new version
    r = client.post(f"{API}/links/{lid}/revert", json={"reason": "Rejected by mistake"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CONFIRMED" and r.json()["version"] == 4
    assert "LINK_REVERTED" in [e.event for e in passport.list_entries(db, case_id=uuid.UUID(j["case"]["id"]))]
    # defer
    r = client.post(f"{API}/links/{lid}/decision", json={"decision": "DEFER", "reason": "Wait for ATR"}, headers=h)
    assert r.json()["status"] == "DEFERRED"
    # filters
    assert client.get(f"{API}/links?status=DEFERRED&relation=RELATED", headers=h).json()["total"] >= 1
    assert client.get(f"{API}/links?bureau=RB", headers=h).json()["total"] == 0
    # thread (P1): participants only
    assert client.post(f"{API}/links/{lid}/thread/messages", json={"body": "hello"}, headers=rb).status_code == 403
    r = client.post(f"{API}/links/{lid}/thread/messages", json={"body": "PGRC will share the ATR status"}, headers=h)
    assert r.status_code == 201 and r.json()["messages"][0]["author_name"] == "Ritu Sharma"
    r = client.patch(f"{API}/links/{lid}/thread", json={"lead_bureau": "RB", "shared_next_action": "RB waits for PGRC ATR"}, headers=h)
    assert r.status_code == 200 and r.json()["lead_bureau"] == "RB"


def test_link_to_ro_case_between_bureaus_is_decidable_by_both(client, db):
    w = build_world(db)
    h, j = _demo(client, w)
    link = next(ln for ln in j["links"] if ln["other_case"]["display_id"] == w.cases["RO-1"].display_id)
    ro = auth_headers(client, w.users["ro_knp"])
    r = client.post(f"{API}/links/{link['link_id']}/decision", json={"decision": "CONFIRM", "reason": "Same refund query"}, headers=ro)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- sweep + scenarios C, D
def test_scenario_c_conflicting_notifies_heads_via_sweep(client, db):
    w = build_world(db)
    u = w.users
    dev = make_institution(db, "Devbhoomi College of Engineering", ro_code="CHD", district="Dehradun", state="Uttarakhand", permanent_id="1-4471203398", pincode="248001", name_norm="devbhoomi college of engineering")
    rb = add_case(db, dev, Bureau.RB, u["rb"], category=CaseCategory.FACULTY_SHORTAGE, subject="Faculty shortage in departments",
                  description="The department has only 3 regular faculty against the approved intake of 120. Show-cause issued.",
                  channel=SourceChannel.BUREAU_FILE, received_days_ago=20, pending_action="Show-cause issued 3 days ago, reply due in 12 days",
                  pending_step=PendingStep.SHOW_CAUSE_REPLY)
    pg = add_case(db, dev, Bureau.PGRC, u["pgrc"], category=CaseCategory.SERVICE_MATTER, subject="Faculty salary unpaid",
                  description="Faculty salary has not been paid for 4 months, refund and settlement negotiation under way.",
                  received_days_ago=8, pending_step=PendingStep.REFUND_FOLLOWUP, pending_since_days_ago=5,
                  pending_action="Negotiation; hearing scheduled")
    db.commit()
    res = run_sweep(db, u["admin"])
    db.commit()
    assert res["new_links"] >= 1 and res["pairs_checked"] >= 1
    link = db.scalar(select(CaseLink).where(CaseLink.case_a_id.in_([rb.id, pg.id]), CaseLink.case_b_id.in_([rb.id, pg.id])))
    assert link is not None and link.relation.value == "CONFLICTING" and link.status.value == "SUGGESTED"
    assert "Hold issue of further letters" in link.features["suggested_next_action"]
    notes = db.scalars(select(Notification).where(Notification.kind == "PRIORITY_REVIEW")).all()
    recipients = {n.user_id for n in notes}
    assert {u["rb"].id, u["pgrc"].id, u["rb_head"].id, u["pgrc_head"].id} <= recipients
    # second sweep changes nothing
    again = run_sweep(db, u["admin"])
    assert again["new_links"] == 0 and again["superseded"] == 0
    # CONFIRMED / REJECTED decisions are never touched by a sweep
    hd = auth_headers(client, u["pgrc_head"])
    assert client.post(f"{API}/links/{link.id}/decision", json={"decision": "REJECT", "reason": "Agreed one letter already"}, headers=hd).status_code == 200
    db.expire_all()
    run_sweep(db, u["admin"])
    db.commit()
    db.expire_all()
    assert db.get(CaseLink, link.id).status.value == "REJECTED"


def test_scenario_d_no_alert_for_unrelated_issues(client, db):
    w = build_world(db)
    u = w.users
    g = make_institution(db, "Gyanodaya Institute of Technology & Management", ro_code="BPL", district="Bhopal", state="Madhya Pradesh", permanent_id="1-4458812074", pincode="462003", name_norm="gyanodaya institute of technology and management")
    add_case(db, g, Bureau.PGRC, u["pgrc"], category=CaseCategory.SCHOLARSHIP, subject="Post-matric scholarship not credited",
             description="My post matric scholarship amount has not been credited to my account for two semesters.", received_days_ago=12)
    add_case(db, g, Bureau.RO, u["ro_bpl"], category=CaseCategory.INFRASTRUCTURE, subject="Computer lab inadequate",
             description="The computer lab has only 20 working systems for 120 students.", channel=SourceChannel.RO_REGISTER,
             received_days_ago=4, ro_code="BPL")
    db.commit()
    before = db.scalar(select(Notification.id).limit(1))
    assert run_sweep(db, u["admin"])["new_links"] == 0
    db.commit()
    assert db.scalars(select(CaseLink).where(CaseLink.relation != "UNRELATED")).all() == []
    assert before is None and db.scalars(select(Notification)).all() == []


def test_parse_hearing_at():
    d = parse_hearing_at("Hearing scheduled 05 Nov 2026")
    assert d is not None and (d.year, d.month, d.day) == (2026, 11, 5)
    assert parse_hearing_at("Show-cause issued 20 Oct") is None
    assert parse_hearing_at(None) is None

