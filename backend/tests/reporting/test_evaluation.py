from __future__ import annotations

import json
from datetime import timedelta

from app.models.cases import Case
from app.models.enums import Bureau, CaseCategory, Role, SourceChannel
from app.models.institutions import InstitutionAlias
from app.models.system import PolicyConfig
from app.services import evaluation
from tests.conftest import auth_headers, make_case, make_institution, make_user
from tests.reporting._world import NOW

API = "/api/v1"

NAMES = [
    ("Shrinath Institute of Engineering and Technology", "Kanpur Nagar", "208017"),
    ("Devbhoomi College of Engineering", "Dehradun", "248001"),
    ("Gyanodaya Institute of Technology and Management", "Bhopal", "462001"),
    ("Rajarshi College of Pharmacy", "Jaipur", "302001"),
    ("Navchetna Polytechnic", "Pune", "411001"),
    ("Sumeru Institute of Management Studies", "Nagpur", "440001"),
]


def _label(inst, dup=None, rel=None, conf=None):
    return {"true_institution_id": str(inst.id), "dup_group": dup, "related_group": rel, "conflict_group": conf}


def _world(db):
    insts = []
    for name, district, pin in NAMES:
        insts.append(make_institution(db, name, district=district, pincode=pin, name_norm=name.lower()))
    held = insts[:3]
    db.add(PolicyConfig(key="eval_split", value={"heldout": [str(i.id) for i in held]}))
    db.commit()
    for i, inst in enumerate(insts):
        a = make_case(
            db, inst, Bureau.PGRC, category=CaseCategory.FEE_REFUND, channel=SourceChannel.CSS,
            received_at=NOW - timedelta(days=10), subject="Fee refund not given after withdrawal",
        )
        b = make_case(
            db, inst, Bureau.PGRC, category=CaseCategory.FEE_REFUND, channel=SourceChannel.CPGRAMS,
            received_at=NOW - timedelta(days=8), subject="Fee refund not given after withdrawal",
        )
        c = make_case(
            db, inst, Bureau.RO, category=CaseCategory.SCHOLARSHIP, channel=SourceChannel.RO_REGISTER,
            received_at=NOW - timedelta(days=5), subject="Scholarship amount not credited this year",
        )
        for case, text, lab in (
            (a, inst.name, _label(inst, dup=f"d{i}")),
            (b, inst.name.upper(), _label(inst, dup=f"d{i}")),
            (c, inst.name, _label(inst)),
        ):
            row = db.get(Case, case.id)
            row.institution_text_raw = text
            row.is_seed_label = lab
        # same complainant for the duplicate pair
        cb = db.get(Case, b.id)
        ca = db.get(Case, a.id)
        cb.complainant_id = ca.complainant_id
        db.commit()
    return insts


def test_evaluation_metrics_are_internally_consistent(db, client):
    _world(db)
    user = make_user(db, Role.PGRC_OFFICER, Bureau.PGRC)
    h = auth_headers(client, user)
    evaluation.clear_cache()
    r = client.get(f"{API}/evaluation/run", params={"split": "heldout"}, headers=h)
    assert r.status_code == 200, r.text
    ev = r.json()
    a, b = ev["stage_a"], ev["stage_b"]
    assert a["n"] == 9  # 3 held-out institutions x 3 cases
    assert a["recall_at_auto_review"]["n"] == 9 and 0 <= a["recall_at_auto_review"]["hits"] <= 9
    band_total = sum(
        x["n_in_band"] for x in a["bands"] if x["band"] in ("EXACT", "AUTO_SUGGESTED")
    ) + a["bands"][3]["n_in_band"] + a["unresolved"]["n"]
    assert band_total == 9
    assert b["n_pairs"] == 9  # 3 pairs on each of 3 institutions
    assert sum(sum(row) for row in b["confusion_matrix"]) == b["n_pairs"]
    assert b["labels"] == ["UNRELATED", "DUPLICATE", "RELATED", "CONFLICTING"]
    assert sum(c["n_true"] for c in b["classes"]) == b["n_pairs"]
    ap = b["alert_precision"]
    assert ap["alerts"] == sum(b["confusion_matrix"][t][p] for t in range(4) for p in range(1, 4))
    assert len(ev["targets"]) == 2 and all("N=" in t["text"] or t["passed"] is None for t in ev["targets"])
    assert len(ev["failure_cases"]) <= 10
    assert ev["split_source"] == "policy_config.eval_split" and ev["evaluated_institutions"] == 3
    dump = json.dumps(ev)
    assert "Asha" not in dump and "example.test" not in dump
    # duplicates with the same complainant should be found by the engine
    dup_truth = b["classes"][1]
    assert dup_truth["n_true"] == 3 and dup_truth["recall"] is not None and dup_truth["recall"] >= 0.66


def test_cache_and_refresh(db, client):
    _world(db)
    user = make_user(db, Role.BUREAU_HEAD, Bureau.PGRC)
    h = auth_headers(client, user)
    evaluation.clear_cache()
    first = client.get(f"{API}/evaluation/run", headers=h).json()
    second = client.get(f"{API}/evaluation/run", headers=h).json()
    assert first["cached"] is False and second["cached"] is True
    assert client.get(f"{API}/evaluation/run", params={"refresh": "true"}, headers=h).json()["cached"] is False
    allsplit = client.get(f"{API}/evaluation/run", params={"split": "all"}, headers=h).json()
    assert allsplit["stage_a"]["n"] == 18
    assert client.get(f"{API}/evaluation/run", params={"split": "bad"}, headers=h).status_code == 422
    assert client.get(f"{API}/evaluation/run").status_code == 401


def test_no_ground_truth_is_a_409_not_made_up_numbers(db, client):
    user = make_user(db, Role.PGRC_OFFICER, Bureau.PGRC)
    make_institution(db, "Lonely College")
    evaluation.clear_cache()
    r = client.get(f"{API}/evaluation/run", headers=auth_headers(client, user))
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_GROUND_TRUTH"


def test_alias_withholding_for_heldout(db):
    insts = _world(db)
    db.add(InstitutionAlias(institution_id=insts[0].id, alias_raw="SIET", alias_norm="siet", source="SEED"))
    db.commit()
    evaluation.clear_cache()
    ev = evaluation.compute(db, "heldout")
    assert ev["stage_a"]["n"] == 9
