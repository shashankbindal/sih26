from __future__ import annotations

from sqlalchemy import select

from app.models.enums import Bureau, Role
from app.models.system import PiiRevealLog
from app.services import passport, privacy
from tests.conftest import auth_headers, make_case, make_institution, make_user


def _setup(db):
    inst = make_institution(db, ro_code="KNP")
    owner = make_user(db, Role.PGRC_OFFICER, Bureau.PGRC)
    case = make_case(db, inst, Bureau.PGRC, owner_officer=owner)
    users = {
        "owner": owner,
        "pgrc_head": make_user(db, Role.BUREAU_HEAD, Bureau.PGRC),
        "rb": make_user(db, Role.RB_OFFICER, Bureau.RB),
        "mgmt": make_user(db, Role.SENIOR_MGMT, Bureau.ADMIN),
        "admin": make_user(db, Role.ADMIN, Bureau.ADMIN),
        "ro_same": make_user(db, Role.RO_OFFICER, Bureau.RO, ro_code="KNP"),
        "ro_other": make_user(db, Role.RO_OFFICER, Bureau.RO, ro_code="BPL"),
    }
    return case, users


def test_matrix_service(db):
    case, u = _setup(db)
    full = {"owner", "pgrc_head", "admin", "ro_same"}  # ro_same: case is in its region
    for key, user in u.items():
        m = privacy.mask_case(case, user)
        if key in full:
            assert m.masked is False and m.complainant["name"] == case.complainant.name, key
            assert m.description == case.description
        elif key == "mgmt":
            assert m.complainant["name"] is None and m.masked is True
            assert m.masked_fields == ["complainant.name", "complainant.email", "complainant.phone"]
            assert m.description == case.description  # all fields except complainant identity
        else:
            assert m.complainant["name"] is None and m.complainant["email"] is None
            assert "complainant.phone" in m.masked_fields and "description" in m.masked_fields
            assert m.description is None
        assert m.complainant["party_type"] == "STUDENT"


def test_ro_sees_ro_owned_case_of_own_region_only(db):
    inst = make_institution(db, ro_code="CHD")
    bpl = make_user(db, Role.RO_OFFICER, Bureau.RO, ro_code="BPL")
    chd = make_user(db, Role.RO_OFFICER, Bureau.RO, ro_code="CHD")
    case = make_case(db, inst, Bureau.RO, owner_ro_code="CHD")
    assert privacy.mask_case(case, chd).masked is False
    assert privacy.mask_case(case, bpl).masked is True


def test_api_detail_masked_flags(client, db):
    case, u = _setup(db)
    r = client.get(f"/api/v1/cases/{case.id}", headers=auth_headers(client, u["rb"])).json()
    assert r["masked"] is True and r["complainant"]["name"] is None
    assert "complainant.name" in r["masked_fields"]
    assert r["owner_bureau"] == "PGRC" and r["display_id"].startswith("LS-")
    r = client.get(f"/api/v1/cases/{case.id}", headers=auth_headers(client, u["owner"])).json()
    assert r["masked"] is False and r["complainant"]["name"] == case.complainant.name
    r = client.get(f"/api/v1/cases/{case.id}", headers=auth_headers(client, u["ro_other"])).json()
    assert r["masked"] is True


def test_reveal_flow_logs_and_unmasks(client, db):
    case, u = _setup(db)
    h = auth_headers(client, u["rb"])
    short = client.post(f"/api/v1/cases/{case.id}/reveal-pii", json={"reason": "too short"}, headers=h)
    assert short.status_code == 422 and short.json()["error"]["code"] == "VALIDATION_ERROR"
    r = client.post(f"/api/v1/cases/{case.id}/reveal-pii", json={"reason": "Need to call about refund"}, headers=h)
    assert r.status_code == 200
    assert r.json()["complainant"]["name"] == case.complainant.name and r.json()["masked"] is False
    db.expire_all()
    assert db.scalars(select(PiiRevealLog).where(PiiRevealLog.case_id == case.id)).all()[0].user_id == u["rb"].id
    entries = passport.list_entries(db, case_id=case.id)
    assert entries[-1].event == "PII_REVEALED" and entries[-1].actor_id == u["rb"].id
    assert passport.verify_chain(db, case_id=case.id)["ok"] is True
    # later reads by the same user stay unmasked; other users are unaffected
    assert client.get(f"/api/v1/cases/{case.id}", headers=h).json()["masked"] is False
    assert client.get(f"/api/v1/cases/{case.id}", headers=auth_headers(client, u["ro_other"])).json()["masked"] is True


def test_reveal_forbidden_for_senior_mgmt(client, db):
    case, u = _setup(db)
    r = client.post(
        f"/api/v1/cases/{case.id}/reveal-pii",
        json={"reason": "Management curiosity about case"},
        headers=auth_headers(client, u["mgmt"]),
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "PII_FORBIDDEN"
    db.expire_all()
    assert db.scalars(select(PiiRevealLog)).all() == []


def test_reveal_by_owner_is_noop(client, db):
    case, u = _setup(db)
    r = client.post(
        f"/api/v1/cases/{case.id}/reveal-pii",
        json={"reason": "Owner reading own case"},
        headers=auth_headers(client, u["owner"]),
    )
    assert r.status_code == 200 and r.json()["masked"] is False
    assert passport.list_entries(db, case_id=case.id) == []
