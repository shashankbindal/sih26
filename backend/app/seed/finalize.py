"""Turn case specs into table rows: complainants, text, institution matching, clocks, passport events."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import jellyfish
from rapidfuzz import fuzz

from app.seed import textgen
from app.seed.cases_gen import (
    CLOSE_REMARKS,
    DISPOSE_REMARKS,
    REFUND_CATS,
    REMARKS,
    Builder,
    Dataset,
)
from app.seed.spec import CaseSpec
from app.services.clocks import compute_state
from app.services.normalise import normalise_name, normalise_text

try:  # engine helpers; the seed still works (with weaker category_suggested) if absent
    from app.services.classify import classify as _classify
except Exception:  # pragma: no cover
    _classify = None  # type: ignore[assignment]


def _uuid(rng: random.Random) -> uuid.UUID:
    return uuid.UUID(int=rng.getrandbits(128), version=4)


def _hours(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600.0


def _cand_features(qtext: str, inst: dict[str, Any]) -> dict[str, Any]:
    qn = normalise_name(qtext)
    nn = inst["name_norm"]
    low = qtext.lower()
    return {
        "name_jw": round(jellyfish.jaro_winkler_similarity(qn.text, nn), 3),
        "token_set": round(fuzz.token_set_ratio(qn.text, nn) / 100, 3),
        "pincode": inst["pincode"] in qtext,
        "district": inst["district"].lower() in low or inst["city"].lower() in low or qn.has_devanagari,
        "translit": bool(qn.has_devanagari),
    }


def _cand_reasons(feat: dict[str, Any], inst: dict[str, Any], qtext: str) -> list[str]:
    r: list[str] = []
    if feat["translit"]:
        r.append("Name matches after Hindi to English transliteration")
    if feat["token_set"] >= 0.85:
        r.append(f"Name similarity {feat['token_set']:.2f}")
    if feat["district"]:
        r.append(f"Same district: {inst['district']}")
    if feat["pincode"]:
        r.append(f"Same pincode: {inst['pincode']}")
    return r[:5] or ["Weak name similarity"]


def finalize(bd: Builder) -> Dataset:
    rng, anchor, policy = bd.rng, bd.anchor, bd.policy
    ds = Dataset(anchor)
    insts = bd.b.institutions
    by_dist: dict[str, list[dict[str, Any]]] = {}
    for i in insts:
        by_dist.setdefault(i["district"], []).append(i)
    ro_users = {u["ro_code"]: u for u in bd.users if u["role"] == "RO_OFFICER"}
    pgrc_officers = [bd.by_email["pgrc.officer@demo.loksutra.in"], bd.by_email["pgrc.officer2@demo.loksutra.in"]]
    persons = bd.persons
    cp_dur = policy.duration("CPGRAMS_21D")

    for s in bd.specs:
        cid = _uuid(rng)
        true_inst = bd.inst_by_id.get(s.inst_id) if s.inst_id else None
        assert true_inst is not None, s
        # ---- complainant
        if s.party_key and s.party_key in persons:
            person = persons[s.party_key]
        else:
            if s.party_key is None:
                ptype = rng.choices(["STUDENT", "PARENT", "FACULTY", "ANONYMOUS", "OTHER"],
                                    [.60, .20, .08, .05, .07])[0]
                if s.category in ("SERVICE_MATTER", "FACULTY_SHORTAGE") and rng.random() < 0.4:
                    ptype = "FACULTY"
                if s.bureau in ("RB", "APPROVAL") and rng.random() < 0.5:
                    ptype = "OTHER"
            else:
                ptype = s.party_type
            person = textgen.make_person(rng, ptype)
            if s.party_key:
                persons[s.party_key] = person
        comp_id = _uuid(rng)
        ds.complainants.append({"id": comp_id, **person})
        ds.persons[cid] = person

        # ---- text
        slots = s.slots or textgen.draw_slots(rng, s.category, s.received_at)
        if s.description is None:
            short = s.short or rng.random() < 0.08
            desc, _ = textgen.make_text(rng, s.category, s.lang, slots, short=short, idx=s.template_idx)
            if s.extra.get("quote_ref"):
                desc = textgen.reference_line(rng, s.lang, s.extra["quote_ref"]) + " " + desc
            elif s.lang == "en" and not s.fixed and person["name"] and rng.random() < 0.08:
                desc += f" Regards, {person['name']}. Mobile {person['phone']}."
        else:
            desc = s.description
        subject = s.subject or textgen.make_subject(rng, s.category, s.lang, slots)
        suggested = s.category
        if _classify is not None:
            try:
                suggested = _classify(subject, desc).category
            except Exception:  # pragma: no cover
                suggested = s.category
        # ---- institution text / permanent id / match status
        style = "official"
        if s.needs_review == "UNRESOLVED":
            city = true_inst["city"]
            itext = rng.choice([f"Engineering college, {city}", f"Technical institute {city}",
                                f"College near {city} bus stand"])
            style = "vague"
        elif s.extra.get("twin"):
            itext = f"{textgen.partial_name(true_inst, rng)}, {true_inst['city']}"
            style = "abbr"
        elif s.inst_text is None:
            itext, style = textgen.institution_text(true_inst, rng)
        else:
            itext = s.inst_text
        pid_mode = s.pid_mode or rng.choices(["missing", "wrong", "exact"], [.30, .03, .67])[0]
        pid_raw = (true_inst["permanent_id"] if pid_mode == "exact"
                   else textgen.corrupt_pid(rng, true_inst["permanent_id"]) if pid_mode == "wrong" else None)
        resolved = s.needs_review is None
        if not resolved:
            status_m = s.needs_review
            score = round(rng.uniform(0.76, 0.91), 3) if status_m == "NEEDS_REVIEW" else round(rng.uniform(0.3, 0.6), 3)
            if s.extra.get("twin"):
                score = round(rng.uniform(0.90, 0.985), 3)
        elif pid_mode == "exact":
            status_m, score = "EXACT", 1.0
        elif pid_mode == "wrong":
            status_m, score = "CONFIRMED", round(rng.uniform(0.80, 0.95), 3)
        elif style in ("abbr", "devanagari") and rng.random() < 0.15:
            status_m, score = "CONFIRMED", round(rng.uniform(0.78, 0.91), 3)
        elif style in ("abbr", "devanagari"):
            status_m, score = "AUTO_SUGGESTED", round(rng.uniform(0.92, 0.985), 3)
        else:
            status_m, score = "AUTO_SUGGESTED", round(rng.uniform(0.93, 0.999), 3)
        # ---- owner
        if s.owner_email:
            owner = bd.by_email[s.owner_email]
        elif s.bureau == "PGRC":
            owner = pgrc_officers[0] if rng.random() < 0.55 else pgrc_officers[1]
        elif s.bureau == "RO":
            owner = ro_users.get(s.ro_code)
        else:
            owner = (bd.officers.get(s.bureau) or [None])[0]
        # ---- timing
        age_h = _hours(s.received_at, anchor)
        fr = s.first_reply_hours
        if fr is None:
            fr = (rng.uniform(1, 68) if rng.random() < 0.88 else rng.uniform(76, 130)) if s.channel == "CSS" \
                else rng.uniform(2, 120)
        if s.status != "RECEIVED":
            fr = max(1.0, min(fr, age_h * 0.5))
            if s.pending_since and s.status in ("AWAITING_ATR", "AWAITING_COMPLAINANT"):
                fr = max(0.5, min(fr, _hours(s.received_at, s.pending_since) - 1))
            if s.disposed_at:
                fr = max(0.5, min(fr, _hours(s.received_at, s.disposed_at) * 0.4))
        tf = s.received_at + timedelta(hours=fr)
        ref = s.source_ref or bd.new_ref(s.channel, s.bureau, s.ro_code)
        s.source_ref = ref
        label = {
            "true_institution_id": str(true_inst["id"]),
            "dup_group": s.groups.get("dup"), "related_group": s.groups.get("related"),
            "conflict_group": s.groups.get("conflict"), "negative_group": s.groups.get("negative"),
            "scenario_key": s.key, "split": bd.b.split[true_inst["id"]],
        }
        last_ts = s.disposed_at or s.pending_since or tf
        case = {
            "id": cid, "source_channel": s.channel, "source_ref": ref, "received_at": s.received_at,
            "institution_text_raw": itext, "permanent_id_raw": pid_raw,
            "institution_id": true_inst["id"] if resolved else None,
            "institution_match_status": status_m, "institution_match_score": score,
            "complainant_id": comp_id, "category": s.category, "category_suggested": suggested,
            "subject": subject, "description": desc, "description_norm": normalise_text(desc),
            "language": s.lang, "owner_bureau": s.bureau, "owner_ro_code": s.ro_code if s.bureau == "RO" else None,
            "owner_officer_id": owner["id"] if owner else None, "status": s.status,
            "pending_step": s.pending_step, "pending_since": s.pending_since, "pending_action": s.pending_action,
            "disposed_at": s.disposed_at, "is_seed_label": label, "created_at": s.received_at,
            "updated_at": min(max(last_ts, s.received_at), anchor),
        }
        ds.cases.append(case)
        ds.specs[cid] = s
        ds.source_refs.append({"case_id": cid, "channel": s.channel, "ref": ref})
        s.extra["tf"] = tf
        s.extra["owner"] = owner
        s.extra["style"] = style
        s.extra["itext"] = itext

        # ---- match candidates
        if status_m in ("AUTO_SUGGESTED", "CONFIRMED", "NEEDS_REVIEW", "UNRESOLVED"):
            _add_candidates(ds, rng, case, true_inst, itext, status_m, score, by_dist, bd, s)

        # ---- clocks
        clocks = _clocks(rng, case, s, policy, anchor, cp_dur, tf)
        ds.clocks.extend(clocks)
        ds.events[cid] = _events(rng, bd, case, s, clocks, owner, tf, anchor)
    return ds


def _add_candidates(ds: Dataset, rng: random.Random, case: dict[str, Any], inst: dict[str, Any], itext: str,
                    status_m: str, score: float, by_dist: dict[str, list[dict[str, Any]]], bd: Builder,
                    s: CaseSpec) -> None:
    others = [i for i in by_dist.get(inst["district"], []) if i["id"] != inst["id"]]
    if s.extra.get("twin"):
        partner = next((b if a == inst["id"] else a for a, b in bd.b.twin_pairs if inst["id"] in (a, b)), None)
        others = [bd.inst_by_id[partner]] + [o for o in others if o["id"] != partner] if partner else others
    ranked = [(inst, score)]
    for k, o in enumerate(sorted(others, key=lambda x: -fuzz.token_set_ratio(itext.lower(), x["name"].lower()))[:2]):
        drop = rng.uniform(0.005, 0.025) if (k == 0 and s.extra.get("twin")) else rng.uniform(0.04, 0.25)
        ranked.append((o, round(max(0.05, score - drop), 3)))
    cstatus = status_m if status_m in ("NEEDS_REVIEW", "UNRESOLVED") else status_m
    for rank, (i, sc) in enumerate(ranked[:3], start=1):
        feat = _cand_features(itext, i)
        ds.candidates.append({
            "id": _uuid(rng), "case_id": case["id"], "institution_id": i["id"], "rank": rank, "score": sc,
            "features": feat, "reasons": _cand_reasons(feat, i, itext),
            "status": cstatus if rank == 1 else ("NEEDS_REVIEW" if status_m == "NEEDS_REVIEW" else "REJECTED"
                                                 if status_m == "CONFIRMED" else "NEEDS_REVIEW"),
            "decided_by": None, "decided_at": None, "decision_reason": None,
        })


def _clocks(rng: random.Random, case: dict[str, Any], s: CaseSpec, policy: Any, anchor: datetime,
            cp_dur: timedelta, tf: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ch, st = case["source_channel"], case["status"]
    closed = st in ("DISPOSED", "CLOSED_NO_ACTION")

    def row(ctype: str, started: datetime, met: datetime | None = None, paused_at: datetime | None = None,
            paused_total: int = 0) -> dict[str, Any]:
        r = {"id": _uuid(rng), "case_id": case["id"], "clock": ctype, "started_at": started,
             "due_at": started + policy.duration(ctype), "paused_total_seconds": paused_total,
             "paused_at": paused_at, "met_at": met, "state": "ON_TRACK", "escalated_at": None}
        obj = SimpleNamespace(**r)
        state = compute_state(obj, anchor, policy).state
        r["state"] = state.value
        return r

    if ch == "CPGRAMS":
        if closed:
            r = row("CPGRAMS_21D", case["received_at"], met=case["disposed_at"],
                    paused_total=int(s.extra.get("paused_hist", 0)))
        elif st == "AWAITING_COMPLAINANT":
            r = row("CPGRAMS_21D", case["received_at"], paused_at=case["pending_since"])
        else:
            r = row("CPGRAMS_21D", case["received_at"])
            if r["state"] == "BREACHED":
                eff_due = r["due_at"] + timedelta(seconds=r["paused_total_seconds"])
                r["escalated_at"] = min(eff_due + timedelta(minutes=rng.randint(5, 55)), anchor - timedelta(minutes=5))
        rows.append(r)
    if ch == "CSS":
        rows.append(row("CSS_72H", case["received_at"], met=tf if st != "RECEIVED" else None))
    if case["category"] in REFUND_CATS:
        if case["pending_step"] in ("INSTITUTION_ATR", "REFUND_FOLLOWUP") and case["pending_since"]:
            rows.append(row("INST_REFUND_7D", case["pending_since"]))
        elif closed and st == "DISPOSED" and s.refund_clock_history and case["disposed_at"]:
            start = min(case["received_at"] + timedelta(days=rng.uniform(1, 3)), case["disposed_at"] - timedelta(hours=2))
            met = min(start + timedelta(days=rng.uniform(1, 9)), case["disposed_at"])
            rows.append(row("INST_REFUND_7D", start, met=met))
    return rows


def _events(rng: random.Random, bd: Builder, case: dict[str, Any], s: CaseSpec, clocks: list[dict[str, Any]],
            owner: dict[str, Any] | None, tf: datetime, anchor: datetime) -> list[dict[str, Any]]:
    ev: list[dict[str, Any]] = []
    rec, st, bureau = case["received_at"], case["status"], case["owner_bureau"]

    def actor(u: dict[str, Any] | None) -> tuple[uuid.UUID | None, str | None]:
        return (u["id"], u["bureau"]) if u else (None, None)

    def add(ts: datetime, event: str, u: dict[str, Any] | None, payload: dict[str, Any], opt: bool = False) -> None:
        aid, ab = actor(u)
        ev.append({"ts": ts, "event": event, "actor_id": aid, "actor_bureau": ab, "payload": payload, "opt": opt})

    intake = None if case["source_channel"] in ("CSS", "CPGRAMS", "CSV_IMPORT") else owner
    add(rec, "RECEIVED", intake, {"channel": case["source_channel"], "source_ref": case["source_ref"]})
    from_b = rng.choice([b for b in ("PGRC", "RB", "RO") if b != bureau])
    first_b = from_b if st == "TRANSFERRED" else bureau
    assigned_to = owner["name"] if (owner and st != "TRANSFERRED") else None
    add(rec + timedelta(minutes=rng.randint(2, 50)), "ASSIGNED", bd.heads.get(first_b),
        {"to_bureau": first_b, "to_officer": assigned_to, "owner_ro_code": case["owner_ro_code"]})
    if st == "RECEIVED":
        return ev
    if st == "TRANSFERRED":
        src = (bd.officers.get(from_b) or [None])[0]
        add(tf, "TRANSFERRED", src, {"from": from_b, "to": bureau, "remark": "Transferred to the bureau concerned"})
    else:
        add(tf, "STATUS_CHANGED", owner, {"from": "RECEIVED", "to": "UNDER_PROCESS" if st != "CLOSED_NO_ACTION" else "UNDER_PROCESS"})
    ps = case["pending_since"]
    if st == "AWAITING_ATR" and ps:
        add(ps, "STATUS_CHANGED", owner, {"from": "UNDER_PROCESS", "to": "AWAITING_ATR", "pending_step": "INSTITUTION_ATR"})
    elif st == "AWAITING_COMPLAINANT" and ps:
        add(ps, "STATUS_CHANGED", owner, {"from": "UNDER_PROCESS", "to": "AWAITING_COMPLAINANT"})
        add(ps + timedelta(minutes=5), "REMARK", owner, {"remark": "Clarification sought from complainant"})
    elif st == "DISPOSED" and case["disposed_at"]:
        d = case["disposed_at"]
        add(tf + (d - tf) * 0.4, "REMARK", owner, {"remark": rng.choice(REMARKS)}, opt=True)
        if case["category"] in ("FEE_REFUND", "CERTIFICATE_WITHHELD", "FACULTY_SHORTAGE", "INFRASTRUCTURE",
                                "SERVICE_MATTER") and rng.random() < 0.7:
            add(d - timedelta(hours=rng.uniform(1, 30)), "ATR_RECEIVED", owner,
                {"remark": "Action taken report received from institution"}, opt=True)
        add(d, "DISPOSED", owner, {"remark": rng.choice(DISPOSE_REMARKS)})
    elif st == "CLOSED_NO_ACTION" and case["disposed_at"]:
        d = case["disposed_at"]
        add(tf + (d - tf) * 0.5, "REMARK", owner, {"remark": rng.choice(CLOSE_REMARKS)}, opt=True)
        add(d, "STATUS_CHANGED", owner, {"from": "UNDER_PROCESS", "to": "CLOSED_NO_ACTION"})
    elif st in ("UNDER_PROCESS", "ESCALATED") and rng.random() < 0.5:
        end = ps or anchor - timedelta(hours=2)
        if end > tf + timedelta(hours=2):
            add(tf + (end - tf) * 0.5, "REMARK", owner, {"remark": rng.choice(REMARKS)}, opt=True)
    cp = next((c for c in clocks if c["clock"] == "CPGRAMS_21D" and c["escalated_at"]), None)
    if cp:
        over = anchor - (cp["due_at"] + timedelta(seconds=cp["paused_total_seconds"]))
        add(cp["escalated_at"], "ESCALATED", None,
            {"clock": "CPGRAMS_21D", "overdue_by": f"{max(0, over.days)} days", "status": "ESCALATED"})
        if st != "ESCALATED":
            back = min(cp["escalated_at"] + timedelta(hours=rng.uniform(2, 24)), anchor - timedelta(minutes=2))
            add(back, "STATUS_CHANGED", owner, {"from": "ESCALATED", "to": st})
    elif st == "ESCALATED":
        age = (anchor - rec) * 0.6
        add(rec + age, "ESCALATED", owner, {"to": "BUREAU_HEAD", "remark": "Escalated for directions of the bureau head"})
    return ev
