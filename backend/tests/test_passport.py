from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.enums import Bureau, Role
from app.services import passport
from tests.conftest import make_case, make_institution, make_user


def _chain(db, n=4):
    inst = make_institution(db)
    officer = make_user(db, Role.PGRC_OFFICER, Bureau.PGRC)
    case = make_case(db, inst, Bureau.PGRC, owner_officer=officer)
    events = ["RECEIVED", "ASSIGNED", "REMARK", "STATUS_CHANGED"]
    for i in range(n):
        passport.append_entry(
            db,
            event=events[i % len(events)],
            case_id=case.id,
            institution_id=inst.id,
            actor=officer,
            payload={"n": i, "remark": "Hindi: फीस वापसी", "score": 0.5},
        )
    db.commit()
    return case, inst, officer


def test_chain_builds_and_verifies(db):
    case, _inst, _o = _chain(db)
    entries = passport.list_entries(db, case_id=case.id)
    assert [e.seq for e in entries] == [1, 2, 3, 4]
    assert entries[0].prev_hash == "0" * 64
    for prev, cur in zip(entries, entries[1:], strict=False):
        assert cur.prev_hash == prev.hash
    res = passport.verify_chain(db, case_id=case.id)
    assert res["ok"] is True and res["count"] == 4 and res["first_bad_seq"] is None
    assert res["checked_at"] is not None


def test_hash_matches_spec_formula(db):
    case, inst, officer = _chain(db, 1)
    e = passport.list_entries(db, case_id=case.id)[0]
    import hashlib
    import json

    canonical = json.dumps(
        {
            "case_id": str(case.id),
            "institution_id": str(inst.id),
            "seq": 1,
            "event": e.event,
            "actor_id": str(officer.id),
            "actor_bureau": "PGRC",
            "payload": e.payload,
            "attachment_name": None,
            "created_at": passport.iso_ms(e.created_at),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert e.hash == hashlib.sha256(("0" * 64 + canonical).encode("utf-8")).hexdigest()
    assert passport.iso_ms(e.created_at).endswith("Z") and len(passport.iso_ms(e.created_at)) == 24


def test_update_blocked_by_trigger(db):
    case, _i, _o = _chain(db)
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE passport_entries SET event = 'X' WHERE case_id = :c AND seq = 2"), {"c": case.id})
    db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM passport_entries WHERE case_id = :c"), {"c": case.id})
    db.rollback()


def test_tamper_detected_with_demo_flag(db):
    case, _i, _o = _chain(db)
    # The trigger honours SET LOCAL loksutra.tamper_demo = 'on' (app layer gates it on DEMO_MODE).
    db.execute(text("SET LOCAL loksutra.tamper_demo = 'on'"))
    db.execute(
        text("UPDATE passport_entries SET payload = jsonb_set(payload, '{n}', '99') WHERE case_id = :c AND seq = 3"),
        {"c": case.id},
    )
    db.commit()
    res = passport.verify_chain(db, case_id=case.id)
    assert res["ok"] is False and res["first_bad_seq"] == 3 and res["count"] == 4
    # the flag was transaction-local: after commit the trigger blocks again
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE passport_entries SET event = 'X' WHERE case_id = :c"), {"c": case.id})
    db.rollback()


def test_deleted_entry_detected(db):
    case, _i, _o = _chain(db)
    db.execute(text("SET LOCAL loksutra.tamper_demo = 'on'"))
    db.execute(text("DELETE FROM passport_entries WHERE case_id = :c AND seq = 2"), {"c": case.id})
    db.commit()
    res = passport.verify_chain(db, case_id=case.id)
    assert res["ok"] is False and res["first_bad_seq"] == 3


def test_action_chain_keyed_by_chain_key(db):
    inst = make_institution(db)
    key = "action:11111111-1111-1111-1111-111111111111"
    other = "action:22222222-2222-2222-2222-222222222222"
    for i in range(3):
        passport.append_entry(db, event="REMARK", chain_key=key, institution_id=inst.id, payload={"i": i})
    passport.append_entry(db, event="REMARK", chain_key=other, institution_id=inst.id)
    db.commit()
    a = passport.list_entries(db, chain_key=key)
    assert [e.seq for e in a] == [1, 2, 3] and a[0].payload["chain_key"] == key
    assert passport.verify_chain(db, chain_key=key)["ok"] is True
    assert passport.verify_chain(db, chain_key=other)["count"] == 1


def test_append_requires_chain(db):
    with pytest.raises(ValueError):
        passport.append_entry(db, event="REMARK")


def test_api_passport_and_verify(client, db):
    case, _i, officer = _chain(db)
    reader = make_user(db, Role.RB_OFFICER, Bureau.RB)
    from tests.conftest import auth_headers

    h = auth_headers(client, reader)
    r = client.get(f"/api/v1/cases/{case.id}/passport", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert len(body["entries"]) == 4
    first = body["entries"][0]
    assert first["actor_name"] == officer.name and first["hash_short"] == first["hash"][:8]
    v = client.get(f"/api/v1/cases/{case.id}/passport/verify", headers=h).json()
    assert v["ok"] is True and v["count"] == 4
    assert client.get(f"/api/v1/cases/{case.id}/passport", headers={}).status_code == 401
