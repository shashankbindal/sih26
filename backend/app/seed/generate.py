"""Synthetic seed generator for Lok Sutra.

    python -m app.seed.generate --reset      truncate everything and regenerate (target < 60 s)
    python -m app.seed.generate --if-empty   seed only when there are no institutions yet
    python -m app.seed.generate --check      assert scenarios A-F and data invariants (PASS/FAIL)

RNG seed 26264. All case dates are relative to ANCHOR = now() at seed time. All data is synthetic.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import insert, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.db import Base, SessionLocal
from app.models.cases import Case, CaseSourceRef, InstitutionMatchCandidate
from app.models.clocks import CaseClock
from app.models.complainants import Complainant
from app.models.institutions import Institution, InstitutionAlias
from app.models.links import CaseLink, CoordinationThread
from app.models.passport import PassportEntry
from app.models.preaction import ClearanceRequest, InstitutionAction
from app.models.system import Notification, PolicyConfig
from app.models.users import RegionalOffice, User
from app.seed import inst_gen, textgen
from app.seed.cases_gen import CASE_SEED, Builder, Dataset
from app.seed.finalize import finalize
from app.seed.scenarios import write_demo_inputs
from app.services.auth import hash_password
from app.services.clocks import ClockPolicy, ensure_default_policy_config, load_policy
from app.services.passport import GENESIS_HASH, compute_hash, json_safe, truncate_ms

DEMO_PASSWORD = "Demo@2026"


# ------------------------------------------------------------------ users

def build_users(rng: random.Random, password_hash: str) -> list[dict[str, Any]]:
    out = []
    for o in textgen.load_json("person_names.json")["officers"]:
        out.append({"id": uuid.UUID(int=rng.getrandbits(128), version=4), "email": o["email"], "name": o["name"],
                    "designation": o["designation"], "role": o["role"], "bureau": o["bureau"],
                    "ro_code": o["ro_code"], "password_hash": password_hash, "is_active": True})
    return out


# ------------------------------------------------------------------ passport sealing

def seal(events: list[dict[str, Any]], *, case_id: uuid.UUID | None, institution_id: uuid.UUID | None,
         anchor: datetime, chain_key: str | None = None) -> list[dict[str, Any]]:
    evs = list(events)
    while len(evs) > 8 and any(e.get("opt") for e in evs):
        evs.remove(next(e for e in evs if e.get("opt")))
    evs.sort(key=lambda e: e["ts"])
    rows: list[dict[str, Any]] = []
    prev, last = GENESIS_HASH, None
    cap = truncate_ms(anchor - timedelta(minutes=1))
    for seq, e in enumerate(evs, start=1):
        ts = min(truncate_ms(e["ts"]), cap)
        if last is not None and ts < last:
            ts = last
        last = ts
        payload = json_safe(e["payload"])
        if case_id is None:
            payload["chain_key"] = chain_key
        h = compute_hash(prev, case_id=case_id, institution_id=institution_id, seq=seq, event=e["event"],
                         actor_id=e["actor_id"], actor_bureau=e["actor_bureau"], payload=payload,
                         attachment_name=None, created_at=ts)
        rows.append({"case_id": case_id, "institution_id": institution_id, "seq": seq, "event": e["event"],
                     "actor_id": e["actor_id"], "actor_bureau": e["actor_bureau"], "payload": payload,
                     "attachment_name": None, "created_at": ts, "prev_hash": prev, "hash": h})
        prev = h
    return rows


# ------------------------------------------------------------------ links + notifications

EXPECTED_REL = {"dup": "DUPLICATE", "related": "RELATED", "conflict": "CONFLICTING"}


def _ev(ts: datetime, event: str, user: dict[str, Any] | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {"ts": ts, "event": event, "actor_id": user["id"] if user else None,
            "actor_bureau": user["bureau"] if user else None, "payload": payload, "opt": False}


def build_links_and_notifications(ds: Dataset, bd: Builder, rng: random.Random) -> dict[str, Any]:
    from app.services.caselink import CaseRecord, TfidfCharSimilarity, Thresholds
    from app.services.caselink.relationship import score_pair
    from app.services.caselink_runtime import parse_hearing_at
    from app.services.normalise import mask_pii

    anchor = ds.anchor
    cid_of = {id(s): cid for cid, s in ds.specs.items()}
    case_by_id = {c["id"]: c for c in ds.cases}
    comp_party = {cid: ds.persons[cid]["party_hash"] for cid in ds.persons}
    recs: dict[uuid.UUID, Any] = {}
    for c in ds.cases:
        cid = c["id"]
        recs[cid] = CaseRecord(
            id=cid, institution_id=c["institution_id"], owner_bureau=c["owner_bureau"], category=c["category"],
            status=c["status"], received_at=c["received_at"], pending_step=c["pending_step"],
            pending_action=c["pending_action"], party_hash=comp_party[cid], source_refs=(c["source_ref"],),
            subject=c["subject"],
            description=mask_pii(c["description"], known_names=(ds.persons[cid]["name"] or "",)),
            description_norm=c["description_norm"], display_id=c["display_id"], source_channel=c["source_channel"],
            disposed_at=c["disposed_at"], pending_since=c["pending_since"],
            hearing_at=parse_hearing_at(c["pending_action"]),
            institution_permanent_id=bd.inst_by_id[c["institution_id"]]["permanent_id"] if c["institution_id"] else None)
    sim = TfidfCharSimilarity([r.similarity_text() for r in recs.values()])
    th = Thresholds()
    links: list[dict[str, Any]] = []
    threads: list[dict[str, Any]] = []
    notifs: list[dict[str, Any]] = []
    stats = {"pairs": 0, "linked": 0, "engine_disagree": []}
    heads = bd.heads
    for p in bd.pair_log:
        kind = p["kind"]
        if kind not in EXPECTED_REL:
            continue
        stats["pairs"] += 1
        sa, sb = p["a"], p["b"]
        ca, cb = case_by_id[cid_of[id(sa)]], case_by_id[cid_of[id(sb)]]
        scenario = bool(sa.key)
        if ca["institution_id"] is None or cb["institution_id"] is None:
            continue
        new_c, old_c = (ca, cb) if ca["received_at"] >= cb["received_at"] else (cb, ca)
        sug = score_pair(recs[new_c["id"]], recs[old_c["id"]], sim, th, anchor)
        want = EXPECTED_REL[kind]
        both_closed = ca["status"] in ("DISPOSED", "CLOSED_NO_ACTION") and cb["status"] in ("DISPOSED", "CLOSED_NO_ACTION")
        if sug.relation != want:
            stats["engine_disagree"].append((p["gid"], want, sug.relation))
            if not scenario:
                continue
        if both_closed:
            continue
        a_id, b_id = sorted((ca["id"], cb["id"]))
        suggested_at = max(new_c["received_at"], *(c["pending_since"] for c in (ca, cb) if c["pending_since"]
                                                    and kind == "conflict"), new_c["received_at"]) + timedelta(minutes=3)
        suggested_at = min(suggested_at, anchor - timedelta(hours=1))
        status, decided_by, decided_at, reason = "SUGGESTED", None, None, None
        if not scenario and suggested_at < anchor - timedelta(hours=6):
            status = rng.choices(["SUGGESTED", "CONFIRMED", "REJECTED", "DEFERRED"],
                                 [.50, .30, .08 if kind == "related" else 0.0, .12])[0]
        owner_new = new_c["owner_officer_id"]
        decider = next((u for u in bd.users if u["id"] == owner_new), None) or heads.get(new_c["owner_bureau"])
        if status != "SUGGESTED" and decider:
            decided_by = decider["id"]
            decided_at = min(suggested_at + timedelta(hours=rng.uniform(2, 48)), anchor - timedelta(minutes=10))
            reason = {"CONFIRMED": "Reviewed both files; the link is correct.",
                      "REJECTED": "Different complaint on review; not linked.",
                      "DEFERRED": "Revisit after the institution's reply is received."}[status]
        link_id = uuid.UUID(int=rng.getrandbits(128), version=4)
        features = json_safe(sug.features)
        features["suggested_next_action"] = sug.suggested_next_action  # same keys as services/links.py
        features["lead_bureau"] = sug.lead_bureau
        links.append({
            "id": link_id, "case_a_id": a_id, "case_b_id": b_id, "relation": want if scenario else sug.relation,
            "score": Decimal(str(round(sug.score, 3))), "features": features, "reasons": list(sug.reasons),
            "status": status, "version": 1, "decided_by": decided_by, "decided_at": decided_at,
            "decision_reason": reason, "created_at": suggested_at,
        })
        threads.append({"id": uuid.UUID(int=rng.getrandbits(128), version=4), "link_id": link_id,
                        "lead_bureau": sug.lead_bureau, "shared_next_action": sug.suggested_next_action,
                        "status": "OPEN"})
        stats["linked"] += 1
        pl = {"link_id": str(link_id), "relation": want, "score": float(round(sug.score, 3))}
        for c, o in ((ca, cb), (cb, ca)):
            ds.events[c["id"]].append(_ev(suggested_at, "LINK_SUGGESTED", None,
                                          {**pl, "other_display_id": o["display_id"]}))
            if status in ("CONFIRMED", "REJECTED") and decider:
                ds.events[c["id"]].append(_ev(decided_at, f"LINK_{status}", decider,
                                              {**pl, "other_display_id": o["display_id"], "remark": reason}))
            elif status == "DEFERRED" and decider:
                ds.events[c["id"]].append(_ev(decided_at, "REMARK", decider,
                                              {"remark": f"Link with {o['display_id']} deferred", "link_id": str(link_id)}))
        if status == "SUGGESTED":
            owners = []
            if want == "RELATED":
                kindn, title = "COORDINATION_REQUIRED", f"Coordination required: {ca['display_id']} and {cb['display_id']}"
                owners = [ca, cb]
            elif want == "CONFLICTING":
                kindn, title = "PRIORITY_REVIEW", f"Priority review: {ca['display_id']} and {cb['display_id']}"
                owners = [ca, cb]
            else:
                kindn, title = "REVIEW_SUGGESTED", f"Review suggested: possible duplicate {new_c['display_id']}"
                owners = [new_c, old_c]
            seen: set[Any] = set()
            recipients: list[tuple[uuid.UUID | None, str | None]] = []
            for c in owners:
                recipients.append((c["owner_officer_id"], c["owner_bureau"] if c["owner_officer_id"] is None else None))
                if want == "CONFLICTING" and c["owner_bureau"] in heads:
                    recipients.append((heads[c["owner_bureau"]]["id"], None))
            for uid, bur in recipients:
                if (uid, bur) in seen:
                    continue
                seen.add((uid, bur))
                notifs.append({
                    "id": uuid.UUID(int=rng.getrandbits(128), version=4), "user_id": uid, "bureau": bur,
                    "kind": kindn, "title": title, "body": sug.suggested_next_action,
                    "link_path": f"/coordination?link={link_id}", "case_id": new_c["id"],
                    "institution_id": new_c["institution_id"], "read_at": None, "created_at": suggested_at})
    return {"links": links, "threads": threads, "notifications": notifs, "stats": stats}


def build_sla_notifications(ds: Dataset, bd: Builder, rng: random.Random) -> list[dict[str, Any]]:
    anchor = ds.anchor
    case_by_id = {c["id"]: c for c in ds.cases}
    out: list[dict[str, Any]] = []
    breached = [(k["case_id"], k) for k in ds.clocks if k["state"] == "BREACHED"
                and case_by_id[k["case_id"]]["status"] not in ("DISPOSED", "CLOSED_NO_ACTION")]
    amber = [k for k in ds.clocks if k["state"] == "AMBER"
             and case_by_id[k["case_id"]]["status"] not in ("DISPOSED", "CLOSED_NO_ACTION")]
    breached.sort(key=lambda kc: kc[1]["due_at"], reverse=True)
    for _cid, k in breached[:24]:
        c = case_by_id[k["case_id"]]
        eff = k["due_at"] + timedelta(seconds=k["paused_total_seconds"])
        recips = [(c["owner_officer_id"], None if c["owner_officer_id"] else c["owner_bureau"])]
        if c["owner_bureau"] in bd.heads:
            recips.append((bd.heads[c["owner_bureau"]]["id"], None))
        for uid, bur in recips:
            out.append({"id": uuid.UUID(int=rng.getrandbits(128), version=4), "user_id": uid, "bureau": bur,
                        "kind": "SLA_BREACH", "title": f"Clock breached on {c['display_id']}",
                        "body": f"{k['clock']} deadline passed",
                        "link_path": f"/cases/{c['id']}", "case_id": c["id"], "institution_id": c["institution_id"],
                        "read_at": None if (anchor - eff).days < 5 else eff + timedelta(days=1),
                        "created_at": eff + timedelta(minutes=30)})
    for k in amber[:14]:
        c = case_by_id[k["case_id"]]
        out.append({"id": uuid.UUID(int=rng.getrandbits(128), version=4), "user_id": c["owner_officer_id"],
                    "bureau": None if c["owner_officer_id"] else c["owner_bureau"], "kind": "SLA_AMBER",
                    "title": f"Clock turning amber on {c['display_id']}", "body": f"{k['clock']} nearing its deadline",
                    "link_path": f"/cases/{c['id']}", "case_id": c["id"], "institution_id": c["institution_id"],
                    "read_at": None, "created_at": anchor - timedelta(hours=rng.uniform(1, 36))})
    for c in ds.cases:
        if c["institution_match_status"] == "NEEDS_REVIEW":
            out.append({"id": uuid.UUID(int=rng.getrandbits(128), version=4), "user_id": None, "bureau": "PGRC",
                        "kind": "REVIEW_QUEUE", "title": f"Institution match needs review: {c['display_id']}",
                        "body": None, "link_path": "/review", "case_id": c["id"], "institution_id": None,
                        "read_at": None, "created_at": c["received_at"] + timedelta(minutes=2)})
    return out


# ------------------------------------------------------------------ historical institution actions

def build_actions(ds: Dataset, bd: Builder) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(CASE_SEED + 1)
    anchor = ds.anchor
    by_inst: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for c in ds.cases:
        if c["institution_id"]:
            by_inst.setdefault(c["institution_id"], []).append(c)
    keyed = {i["id"] for i in bd.b.institutions if i["key"]}
    pool = [i for i in bd.b.institutions if i["id"] not in keyed and i["approval_status"] == "APPROVED"
            and by_inst.get(i["id"])]
    closure = [i for i in bd.b.institutions if i["approval_status"] == "CLOSURE_APPLIED" and by_inst.get(i["id"])
               and i["id"] not in keyed]
    rng.shuffle(pool)
    u = bd.by_email
    appr, rb, pg = u["approval.officer@demo.loksutra.in"], u["rb.officer@demo.loksutra.in"], u["pgrc.officer@demo.loksutra.in"]
    vig = u["vigilance.officer@demo.loksutra.in"]
    plan = [
        ("SECURITY_DEPOSIT_RELEASE", appr, 60, "PROCEEDED", True, "CLEARED", pool[0]),
        ("SECURITY_DEPOSIT_RELEASE", appr, 35, "PROCEEDED", True, "CLEARED_WITH_REMARKS", pool[1]),
        ("ISSUE_NOC", appr, 20, "ACKNOWLEDGED", False, None, pool[2]),
        ("SHOW_CAUSE", rb, 45, "PROCEEDED", False, None, pool[3]),
        ("CLOSURE_APPROVAL", appr, 12, "ON_HOLD", False, None, closure[0] if closure else pool[4]),
        ("INSPECTION_ORDER", rb, 10, "WITHDRAWN", False, None, pool[5]),
    ]
    actions, clearances, passport, notifs = [], [], [], []
    for atype, who, days_ago, status, chain, resp, inst in plan:
        aid = uuid.UUID(int=rng.getrandbits(128), version=4)
        created = anchor - timedelta(days=days_ago)
        matters = [c for c in by_inst[inst["id"]]
                   if c["received_at"] <= created and (c["disposed_at"] is None or c["disposed_at"] > created)]
        snap = {"generated_at": created.isoformat(), "action_type": atype,
                "open_matters": [{"case_id": str(c["id"]), "display_id": c["display_id"],
                                  "owner_bureau": c["owner_bureau"], "category": c["category"],
                                  "status": c["status"]} for c in matters]}
        n_open = len(matters)
        ack_at = created + timedelta(minutes=rng.randint(5, 40))
        remark = {"PROCEEDED": f"Proceeded with {n_open} open matters acknowledged",
                  "ACKNOWLEDGED": f"Acknowledged {n_open} open matters; NOC to follow",
                  "ON_HOLD": "Held pending resolution of students' dues",
                  "WITHDRAWN": "Inspection order withdrawn after review"}[status]
        actions.append({"id": aid, "institution_id": inst["id"], "action_type": atype, "initiated_by": who["id"],
                        "initiated_bureau": who["bureau"], "status": status, "snapshot": snap,
                        "open_matter_count": n_open, "acknowledged_at": ack_at if status != "CHECK_SHOWN" else None,
                        "ack_remark": remark, "created_at": created})
        key = f"action:{aid}"
        evs: list[dict[str, Any]] = []
        if chain:
            steps = [("PGRC", pg, 1), ("VIGILANCE", vig, 2), ("APPROVAL", appr, 3)]
            t = created + timedelta(minutes=45)
            for bureau, responder, order in steps:
                req_at, resp_at = t, t + timedelta(hours=rng.uniform(5, 40))
                rtext = ("Cleared; student dues settled." if bureau == "PGRC" and resp == "CLEARED_WITH_REMARKS"
                         else "Cleared." if bureau != "APPROVAL" else "NOC issued.")
                response = resp if bureau == "PGRC" else "CLEARED"
                clearances.append({"id": uuid.UUID(int=rng.getrandbits(128), version=4), "institution_action_id": aid,
                                   "institution_id": inst["id"], "target_bureau": bureau, "step_order": order,
                                   "requested_by": who["id"], "requested_at": req_at, "response": response,
                                   "responded_by": responder["id"], "responded_at": resp_at, "remarks": rtext})
                evs.append(_ev(req_at, "CLEARANCE_REQUESTED", who, {"target_bureau": bureau, "step_order": order,
                                                                    "action_type": atype}))
                evs.append(_ev(resp_at, "CLEARANCE_RESPONDED", responder, {"target_bureau": bureau, "response": response,
                                                                           "remarks": rtext}))
                notifs.append({"id": uuid.UUID(int=rng.getrandbits(128), version=4), "user_id": responder["id"],
                               "bureau": None, "kind": "CLEARANCE_REQUEST",
                               "title": f"Clearance requested: {atype.replace('_', ' ').title()}", "body": None,
                               "link_path": "/clearances", "case_id": None, "institution_id": inst["id"],
                               "read_at": resp_at, "created_at": req_at})
                notifs.append({"id": uuid.UUID(int=rng.getrandbits(128), version=4), "user_id": who["id"],
                               "bureau": None, "kind": "CLEARANCE_RESPONSE",
                               "title": f"{bureau.title()} responded: {response.replace('_', ' ').lower()}", "body": rtext,
                               "link_path": "/clearances", "case_id": None, "institution_id": inst["id"],
                               "read_at": resp_at + timedelta(hours=2), "created_at": resp_at})
                t = resp_at + timedelta(minutes=30)
            ack_at = t
            actions[-1]["acknowledged_at"] = ack_at
        evs.append(_ev(ack_at, "PREACTION_ACKNOWLEDGED", who,
                       {"action_type": atype, "status": status, "open_matters": n_open, "remark": remark}))
        passport.extend(seal(evs, case_id=None, institution_id=inst["id"], anchor=anchor, chain_key=key))
    return {"actions": actions, "clearances": clearances, "passport": passport, "notifications": notifs}


# ------------------------------------------------------------------ assembly

class Seeded:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.stats: dict[str, Any] = {}


def build_all(anchor: datetime, policy: ClockPolicy, password_hash: str) -> tuple[Seeded, Builder, Dataset]:
    bundle = inst_gen.build()
    urng = random.Random(inst_gen.SEED + 7)
    users = build_users(urng, password_hash)
    bd = Builder(anchor, bundle, users, policy)
    bd.add_scenarios()
    bd.add_pairs()
    bd.add_background()
    bd.pick_review_cases()
    bd.assign_institutions()
    ds = finalize(bd)
    ds.cases.sort(key=lambda c: (c["received_at"], str(c["id"])))
    year = anchor.astimezone(UTC).year
    for i, c in enumerate(ds.cases, start=1):
        c["display_id"] = f"LS-{year}-{i:06d}"
    lrng = random.Random(CASE_SEED + 2)
    lk = build_links_and_notifications(ds, bd, lrng)
    notifs = lk["notifications"] + build_sla_notifications(ds, bd, lrng)
    act = build_actions(ds, bd)
    notifs += act["notifications"]
    passport: list[dict[str, Any]] = []
    for c in ds.cases:
        passport.extend(seal(ds.events[c["id"]], case_id=c["id"], institution_id=c["institution_id"], anchor=anchor))
    passport.extend(act["passport"])
    sd = Seeded()
    t = sd.tables
    t["regional_offices"] = [{"code": r["code"], "name": r["name"], "city": r["city"], "lat": r["lat"], "lng": r["lng"],
                              "states": r["states"]} for r in bundle.ros]
    t["users"] = users
    t["institutions"] = [{k: v for k, v in i.items() if k in INST_COLS} for i in bundle.institutions]
    t["institution_aliases"] = bundle.aliases
    t["complainants"] = ds.complainants
    t["cases"] = ds.cases
    t["case_source_refs"] = ds.source_refs
    t["case_clocks"] = ds.clocks
    t["institution_match_candidates"] = ds.candidates
    t["case_links"] = lk["links"]
    t["coordination_threads"] = lk["threads"]
    t["institution_actions"] = act["actions"]
    t["clearance_requests"] = act["clearances"]
    t["passport_entries"] = passport
    t["notifications"] = notifs
    sd.stats = {**lk["stats"], "bundle": bundle}
    return sd, bd, ds


INST_COLS = {"id", "permanent_id", "name", "name_norm", "inst_type", "address", "district", "state", "pincode",
             "ro_code", "email_domain", "phone", "approval_status", "established_year"}

WRITE_ORDER = [
    ("regional_offices", RegionalOffice), ("users", User), ("institutions", Institution),
    ("institution_aliases", InstitutionAlias), ("complainants", Complainant), ("cases", Case),
    ("case_source_refs", CaseSourceRef), ("case_clocks", CaseClock),
    ("institution_match_candidates", InstitutionMatchCandidate), ("case_links", CaseLink), ("coordination_threads", CoordinationThread),
    ("institution_actions", InstitutionAction), ("clearance_requests", ClearanceRequest),
    ("passport_entries", PassportEntry), ("notifications", Notification),
]


def _bulk(session: Session, model: type, rows: list[dict[str, Any]], chunk: int = 1000) -> None:
    for i in range(0, len(rows), chunk):
        session.execute(insert(model.__table__), rows[i:i + chunk])


def reset(*, verbose: bool = True) -> dict[str, Any]:
    t0 = time.perf_counter()
    anchor = datetime.now(UTC).replace(microsecond=0)
    pw_hash = hash_password(DEMO_PASSWORD)
    with SessionLocal() as session:
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        session.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
        session.execute(text("ALTER SEQUENCE display_id_seq RESTART WITH 1"))
        ensure_default_policy_config(session)
        session.add(PolicyConfig(key="seeded_at", value={"at": anchor.isoformat()}))
        session.flush()
        policy = load_policy(session)
        sd, _bd, _ds = build_all(anchor, policy, pw_hash)
        for name, model in WRITE_ORDER:
            _bulk(session, model, sd.tables[name])
        n_cases = len(sd.tables["cases"])
        session.execute(text("SELECT setval('display_id_seq', :n)"), {"n": n_cases})
        session.commit()
    write_demo_inputs()
    secs = time.perf_counter() - t0
    counts = {k: len(v) for k, v in sd.tables.items()}
    if verbose:
        print(f"seeded in {secs:.1f}s at {anchor.isoformat()}")
        for k, v in counts.items():
            print(f"  {k:32s} {v}")
        dis = sd.stats["engine_disagree"]
        by_kind: dict[str, int] = {}
        for gid, _want, _got in dis:
            by_kind[gid[0]] = by_kind.get(gid[0], 0) + 1
        print(f"  INFO ground-truth pairs the engine labels differently (not inserted as links): "
              f"{len(dis)} {by_kind}")
    return {"seconds": secs, "counts": counts, "anchor": anchor.isoformat()}


def seed_if_empty() -> bool:
    with SessionLocal() as session:
        n = session.execute(text("SELECT count(*) FROM institutions")).scalar_one()
    if n:
        print("database already seeded; nothing to do")
        return False
    reset()
    return True


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m app.seed.generate")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--reset", action="store_true")
    g.add_argument("--if-empty", action="store_true")
    g.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.reset:
        reset()
        return 0
    if args.if_empty:
        seed_if_empty()
        return 0
    from app.seed.check import run_check

    return 0 if run_check() else 1


if __name__ == "__main__":
    sys.exit(main())
