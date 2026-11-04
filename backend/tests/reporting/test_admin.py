from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from app.config import get_settings
from app.models.enums import Bureau, CaseCategory, CaseStatus, PendingStep, Role, SourceChannel
from app.models.passport import PassportEntry
from app.models.system import AuditLog, Notification
from app.scheduler import evaluate_clocks
from app.services import passport
from tests.conftest import auth_headers, make_case, make_institution, make_user
from tests.reporting._world import NOW, build_world

API = "/api/v1"


def test_public_config_readable_by_any_user_but_admin_keys_are_not(db, client):
    w = build_world(db)
    h = auth_headers(client, w["me"])
    for key in ("thresholds", "clocks", "clause_labels", "amber_ratio"):
        r = client.get(f"{API}/admin/config/{key}", headers=h)
        assert r.status_code == 200, (key, r.text)
        assert r.json()["key"] == key
    assert client.get(f"{API}/admin/config/lead_bureau_rules", headers=h).status_code == 403
    assert client.get(f"{API}/admin/config/nope", headers=h).status_code == 404
    pub = client.get(f"{API}/config/public", headers=h)
    assert pub.status_code == 200
    body = pub.json()
    assert set(body) == {"thresholds", "clocks", "clause_labels", "amber_ratio"}
    assert body["thresholds"]["inst_auto"] == 0.92
    assert body["clause_labels"]["refund"] == "APH 2024-27 cl. 6.45"
    assert client.get(f"{API}/config/public").status_code == 401
    admin = auth_headers(client, w["admin"])
    assert client.get(f"{API}/admin/config/lead_bureau_rules", headers=admin).status_code == 200
    # everything else stays admin-only
    for method, path in (("get", "/admin/users"), ("get", "/admin/demo-tools"), ("post", "/admin/sweep")):
        assert getattr(client, method)(f"{API}{path}", headers=h).status_code == 403


def test_put_config_validates_and_audits(db, client):
    w = build_world(db)
    me, admin = auth_headers(client, w["me"]), auth_headers(client, w["admin"])
    url = f"{API}/admin/config"
    assert client.put(f"{url}/thresholds", json={"value": {"inst_auto": 0.9}}, headers=me).status_code == 403
    r = client.put(f"{url}/thresholds", json={"value": {"inst_auto": 0.9}}, headers=admin)
    assert r.status_code == 200
    assert r.json()["value"]["inst_auto"] == 0.9 and r.json()["value"]["inst_review"] == 0.75
    bad = client.put(f"{url}/thresholds", json={"value": {"inst_review": 0.95}}, headers=admin)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_CONFIG"
    assert client.put(f"{url}/thresholds", json={"value": {"bogus": 1}}, headers=admin).status_code == 422
    assert client.put(f"{url}/amber_ratio", json={"value": 1.5}, headers=admin).status_code == 422
    assert client.put(f"{url}/amber_ratio", json={"value": 0.8}, headers=admin).status_code == 200
    r = client.put(f"{url}/clocks", json={"value": {"CSS_72H": {"duration_hours": 48}}}, headers=admin)
    assert r.status_code == 200
    assert r.json()["value"]["CSS_72H"]["duration_hours"] == 48
    assert r.json()["value"]["CSS_72H"]["short_label"] == "72-hour"
    assert client.put(f"{url}/clocks", json={"value": {"XX": {}}}, headers=admin).status_code == 422
    assert client.put(f"{url}/lead_bureau_rules", json={"value": {"FEE_REFUND": "NOPE"}}, headers=admin).status_code == 422
    assert client.put(f"{url}/lead_bureau_rules", json={"value": {"FEE_REFUND": "RB"}}, headers=admin).status_code == 200
    db.expire_all()
    rows = db.scalars(select(AuditLog).where(AuditLog.entity == "policy_config")).all()
    assert {r.entity_id for r in rows} == {"thresholds", "amber_ratio", "clocks", "lead_bureau_rules"}
    assert any("inst_auto" in (r.summary or "") for r in rows)


def test_tamper_demo_breaks_chain_mid_way(db, client):
    w = build_world(db)
    inst = w["knp"]
    case = make_case(db, inst, Bureau.PGRC)
    for i in range(5):
        passport.append_entry(
            db, event="REMARK", case_id=case.id, institution_id=inst.id, actor=w["me"], payload={"n": i}
        )
    db.commit()
    assert passport.verify_chain(db, case_id=case.id)["ok"] is True
    admin = auth_headers(client, w["admin"])
    r = client.post(f"{API}/admin/tamper-demo", json={"case_id": str(case.id)}, headers=admin)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["seq"] == 3 and out["verify"]["ok"] is False and out["verify"]["first_bad_seq"] == 3
    db.expire_all()
    assert passport.verify_chain(db, case_id=case.id)["first_bad_seq"] == 3
    assert db.scalar(select(AuditLog.id).where(AuditLog.path.like("%tamper-demo"))) is not None
    entries = db.scalars(select(PassportEntry).where(PassportEntry.case_id == case.id)).all()
    assert len([e for e in entries if "altered_after_the_fact" in e.payload]) == 1
    no_chain = client.post(
        f"{API}/admin/tamper-demo", json={"case_id": str(w["cases"]["css_amber"].id)}, headers=admin
    )
    assert no_chain.status_code == 409


def test_demo_only_tools_refuse_when_demo_mode_off(db, client, monkeypatch):
    w = build_world(db)
    admin = auth_headers(client, w["admin"])
    monkeypatch.setattr(get_settings(), "demo_mode", False)
    assert client.post(f"{API}/admin/reset-demo", headers=admin).status_code == 403
    r = client.post(f"{API}/admin/tamper-demo", json={"case_id": str(w["cases"]["css_amber"].id)}, headers=admin)
    assert r.status_code == 403 and r.json()["error"]["code"] == "DEMO_MODE_DISABLED"


def test_users_and_demo_tools(db, client):
    w = build_world(db)
    admin = auth_headers(client, w["admin"])
    users = client.get(f"{API}/admin/users", headers=admin)
    assert users.status_code == 200 and "password" not in users.text
    assert {u["role"] for u in users.json()} >= {"ADMIN", "PGRC_OFFICER", "RO_OFFICER"}
    d = client.get(f"{API}/admin/demo-tools", headers=admin).json()
    assert d["demo_mode"] is True and d["counts"]["cases"] == 9
    assert d["scheduler"]["enabled"] is False  # never runs under pytest


def test_sweep_endpoint_adapter(db, client):
    w = build_world(db)
    r = client.post(f"{API}/admin/sweep", headers=auth_headers(client, w["admin"]))
    assert r.status_code in (200, 501)
    if r.status_code == 501:
        assert r.json()["error"]["code"] == "NOT_IMPLEMENTED"
    else:
        assert {"pairs_checked", "new_links", "superseded"} <= set(r.json())


def test_scheduler_clock_events_are_idempotent(db):
    inst = make_institution(db, "Clock College")
    officer = make_user(db, Role.PGRC_OFFICER, Bureau.PGRC)
    head = make_user(db, Role.BUREAU_HEAD, Bureau.PGRC)
    cp = make_case(
        db, inst, Bureau.PGRC, owner_officer=officer, channel=SourceChannel.CPGRAMS,
        received_at=NOW - timedelta(days=25), start_clocks=True, category=CaseCategory.SCHOLARSHIP,
    )
    refund = make_case(
        db, inst, Bureau.PGRC, owner_officer=officer, channel=SourceChannel.EMAIL, category=CaseCategory.FEE_REFUND,
        status=CaseStatus.AWAITING_ATR, pending_step=PendingStep.INSTITUTION_ATR,
        pending_since=NOW - timedelta(days=11), received_at=NOW - timedelta(days=14), start_clocks=True,
    )
    css = make_case(
        db, inst, Bureau.PGRC, owner_officer=officer, channel=SourceChannel.CSS,
        received_at=NOW - timedelta(hours=55), start_clocks=True,
    )
    stats = evaluate_clocks(db)
    db.commit()
    assert stats["breached"] == 2 and stats["amber"] == 1 and stats["escalated"] == 2
    db.refresh(cp)
    db.refresh(refund)
    assert cp.status == CaseStatus.ESCALATED  # CPGRAMS clock only
    assert refund.status == CaseStatus.AWAITING_ATR
    notes = db.scalars(select(Notification)).all()
    breach = [n for n in notes if n.kind == "SLA_BREACH" and n.case_id == cp.id]
    assert {n.user_id for n in breach} == {officer.id, head.id}
    assert any(n.kind == "SLA_AMBER" and n.case_id == css.id and n.user_id == officer.id for n in notes)
    esc = db.scalars(
        select(PassportEntry).where(PassportEntry.event == "ESCALATED", PassportEntry.case_id == cp.id)
    ).all()
    assert len(esc) == 1 and esc[0].actor_id is None and esc[0].payload["clock"] == "CPGRAMS_21D"
    assert esc[0].payload["status_to"] == "ESCALATED"
    assert passport.verify_chain(db, case_id=cp.id)["ok"]
    before = db.scalar(select(func.count()).select_from(Notification))
    stats2 = evaluate_clocks(db)
    db.commit()
    assert stats2["changed"] == 0 and stats2["escalated"] == 0
    assert db.scalar(select(func.count()).select_from(Notification)) == before
