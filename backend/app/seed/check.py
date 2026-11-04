"""`python -m app.seed.generate --check`: scenario A-F expectations and data invariants."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.cases import Case, CaseSourceRef
from app.models.clocks import CaseClock
from app.models.complainants import Complainant
from app.models.institutions import Institution, InstitutionAlias
from app.models.links import CaseLink, CoordinationThread
from app.models.preaction import ClearanceRequest, InstitutionAction
from app.models.system import PolicyConfig
from app.seed import inst_gen
from app.seed.scenarios import DEMO_INPUTS
from app.services.caselink_runtime import load_case_records
from app.services.clocks import compute_state, load_policy
from app.services.passport import verify_chain

RESULTS: list[bool] = []


def rec(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    return bool(ok)


def _digest(pairs: list[tuple[str, str]]) -> str:
    h = hashlib.sha256()
    for pid, name in sorted(pairs):
        h.update(f"{pid}|{name}\n".encode())
    return h.hexdigest()


def _scn(session: Session) -> dict[str, Case]:
    rows = session.scalars(select(Case).where(Case.is_seed_label["scenario_key"].astext.isnot(None))).all()
    return {c.is_seed_label["scenario_key"]: c for c in rows}


def run_check() -> bool:
    import sys

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")  # noqa: C901 - one long, flat list of assertions
    RESULTS.clear()
    with SessionLocal() as s:
        seeded = s.get(PolicyConfig, "seeded_at")
        if seeded is None:
            print("FAIL  database is not seeded (run --reset first)")
            return False
        anchor = datetime.fromisoformat(seeded.value["at"])
        policy = load_policy(s)
        scn = _scn(s)

        # ---------------- volumes
        n_inst = s.scalar(select(func.count()).select_from(Institution))
        n_alias = s.scalar(select(func.count()).select_from(InstitutionAlias))
        n_cases = s.scalar(select(func.count()).select_from(Case))
        n_users = s.scalar(text("select count(*) from users"))
        n_ro = s.scalar(text("select count(*) from regional_offices"))
        n_act = s.scalar(select(func.count()).select_from(InstitutionAction))
        rec("volumes: 10 ROs, 200 institutions, 350 aliases, 12 users, 600 cases, 6 actions",
            (n_ro, n_inst, n_alias, n_users, n_cases, n_act) == (10, 200, 350, 12, 600, 6),
            f"{n_ro}/{n_inst}/{n_alias}/{n_users}/{n_cases}/{n_act}")
        mix = dict(s.execute(text("select owner_bureau::text, count(*) from cases group by 1")).all())
        rec("bureau mix PGRC 270 / RB 150 / RO 120 / APPROVAL 30 / VIGILANCE 30",
            mix == {"PGRC": 270, "RB": 150, "RO": 120, "APPROVAL": 30, "VIGILANCE": 30}, str(mix))
        smix = dict(s.execute(text("select status::text, count(*) from cases group by 1")).all())
        rec("status mix matches the seed-data plan section 2",
            smix == {"DISPOSED": 270, "UNDER_PROCESS": 120, "AWAITING_ATR": 72, "RECEIVED": 48, "TRANSFERRED": 30,
                     "ESCALATED": 24, "AWAITING_COMPLAINANT": 18, "CLOSED_NO_ACTION": 18}, str(smix))
        n_closed = s.scalar(text("select count(*) from institutions where approval_status in ('CLOSED','CLOSURE_APPLIED')"))
        rec("about 5 percent institutions closed / closure applied", 8 <= n_closed <= 12, str(n_closed))
        full = s.execute(text("select count(*) from case_links")).scalar()
        rec("seeded case_links present (coordination inbox populated)", (full or 0) >= 10, f"{full} links")
        clause = s.get(PolicyConfig, "clause_labels").value
        rec("clause_labels exact", clause == {"refund": "APH 2024-27 cl. 6.45",
                                              "deposit": "APH 2024-27 · Security-deposit release procedure"})

        # ---------------- determinism / real names / PII hash
        db_pairs = [(i.permanent_id, i.name) for i in s.scalars(select(Institution))]
        a, b = inst_gen.build(), inst_gen.build()
        da = _digest([(i["permanent_id"], i["name"]) for i in a.institutions])
        rec("determinism: DB institutions == regenerated == regenerated again",
            _digest(db_pairs) == da == _digest([(i["permanent_id"], i["name"]) for i in b.institutions]), da[:12])
        rec("no real-name collisions (blocklist)", not inst_gen.check_real_names([n for _, n in db_pairs]))
        rec("institution names unique", len({n for _, n in db_pairs}) == 200)
        bad = 0
        for comp in s.scalars(select(Complainant)):
            if comp.party_hash:
                digits = "".join(ch for ch in (comp.phone or "") if ch.isdigit())
                exp = hashlib.sha256(f"{(comp.email or '').lower()}|{digits}".encode()).hexdigest()
                bad += exp != comp.party_hash
        rec("complainant party_hash = sha256(lower(email)|digits(phone))", bad == 0)

        # ---------------- passport chains
        bad_cases = []
        for cid in s.scalars(select(Case.id)):
            v = verify_chain(s, case_id=cid)
            if not v["ok"] or not (2 <= v["count"] <= 8):
                bad_cases.append((str(cid), v["count"], v["first_bad_seq"]))
        rec("every case Passport chain verifies and has 2-8 entries", not bad_cases, str(bad_cases[:3]))
        bad_act = []
        for aid in s.scalars(select(InstitutionAction.id)):
            v = verify_chain(s, chain_key=f"action:{aid}")
            if not v["ok"] or v["count"] < 1:
                bad_act.append(str(aid))
        rec("every institution-action Passport chain verifies", not bad_act)
        full_chain = s.scalar(text(
            "select count(*) from (select institution_action_id from clearance_requests "
            "where response in ('CLEARED','CLEARED_WITH_REMARKS') group by 1 having count(*)=3) t"))
        rec("2 historical actions with complete clearance chains", full_chain == 2, str(full_chain))

        # ---------------- clock invariants
        rows = s.execute(select(CaseClock, Case.status).join(Case, Case.id == CaseClock.case_id)
                         .where(CaseClock.clock == "CPGRAMS_21D")).all()
        open_cp = [(c, st) for c, st in rows if st.value not in ("DISPOSED", "CLOSED_NO_ACTION")]
        states = [compute_state(c, anchor, policy).state.value for c, _ in open_cp]
        br, am = states.count("BREACHED") / len(states), states.count("AMBER") / len(states)
        rec("about 12 percent of open CPGRAMS cases breached", 0.08 <= br <= 0.16, f"{br:.1%} of {len(states)}")
        rec("about 15 percent of open CPGRAMS cases amber", 0.11 <= am <= 0.20, f"{am:.1%} of {len(states)}")

        # ---------------- Scenario A (seed state)
        shri = s.scalar(select(Institution).where(Institution.permanent_id == "1-4463974255"))
        aliases = sorted(x.alias_raw for x in s.scalars(select(InstitutionAlias).where(InstitutionAlias.institution_id == shri.id)))
        p1, p2, rb1, ro1 = scn["A-PGRC-1"], scn["A-PGRC-2"], scn["A-RB-1"], scn["A-RO-1"]
        ok = (shri.name == "Shrinath Institute of Engineering & Technology" and shri.district == "Kanpur Nagar"
              and shri.state == "Uttar Pradesh" and shri.pincode == "208017" and shri.ro_code == "KNP"
              and aliases == ["SIET Kanpur", "Shrinath Engg College"])
        rec("A: Shrinath institution, aliases, RO KNP", ok, str(aliases))
        ck = {c.clock.value: c for c in s.scalars(select(CaseClock).where(CaseClock.case_id == p1.id))}
        st1 = compute_state(ck["INST_REFUND_7D"], anchor, policy)
        rec("A: PGRC-1 INST_REFUND_7D breached by 4 days (pending_since = ANCHOR-11d)",
            st1.state.value == "BREACHED" and abs((p1.pending_since - (anchor - timedelta(days=11))).total_seconds()) < 2
            and st1.label.endswith("overdue 4 days") and p1.status.value == "AWAITING_ATR"
            and p1.pending_step.value == "INSTITUTION_ATR" and abs((p1.received_at - (anchor - timedelta(days=16))).total_seconds()) < 2,
            st1.label)
        ck2 = {c.clock.value: c for c in s.scalars(select(CaseClock).where(CaseClock.case_id == p2.id))}
        st2 = compute_state(ck2["CPGRAMS_21D"], anchor, policy)
        rec("A: PGRC-2 CPGRAMS_21D on track, 12 days left",
            st2.state.value == "ON_TRACK" and st2.label.endswith("12 days left") and p2.status.value == "UNDER_PROCESS",
            st2.label)
        hist = [scn[k] for k in ("A-HIST-1", "A-HIST-2", "A-HIST-3")]
        rec("A: RB-1 scrutiny / RO-1 received / 3 disposed history cases (RAGGING disposed 200 d ago)",
            rb1.category.value == "SCRUTINY_COMMITTEE" and rb1.pending_action == "Scrutiny committee review scheduled"
            and ro1.status.value == "RECEIVED" and ro1.owner_ro_code == "KNP"
            and all(h.status.value == "DISPOSED" for h in hist) and hist[0].category.value == "RAGGING"
            and abs((hist[0].disposed_at - (anchor - timedelta(days=200))).total_seconds()) < 2)

        # ---------------- Scenario B preconditions
        open_matters = s.scalar(text(
            "select count(*) from cases where institution_id=:i and status not in ('DISPOSED','CLOSED_NO_ACTION')"),
            {"i": shri.id})
        has_actions = s.scalar(select(func.count()).select_from(InstitutionAction)
                               .where(InstitutionAction.institution_id == shri.id))
        n_clear = s.scalar(select(func.count()).select_from(ClearanceRequest).where(ClearanceRequest.institution_id == shri.id))
        rec("B: Shrinath has 5 open seeded matters (+ the live one), no prior actions / clearances",
            open_matters == 5 and has_actions == 0 and n_clear == 0, f"open={open_matters}")

        # ---------------- Scenario C/D/E/F (seed state)
        dev = s.scalar(select(Institution).where(Institution.permanent_id == "1-4471203398"))
        crb, cpg = scn["C-RB"], scn["C-PGRC"]
        ok = (dev.name == "Devbhoomi College of Engineering" and dev.district == "Dehradun" and dev.ro_code == "CHD"
              and "show-cause" in crb.pending_action.lower() and crb.pending_step.value == "SHOW_CAUSE_REPLY"
              and abs((crb.pending_since - (anchor - timedelta(days=3))).total_seconds()) < 2
              and cpg.category.value == "SERVICE_MATTER" and cpg.pending_step.value == "REFUND_FOLLOWUP"
              and "hearing scheduled" in cpg.pending_action.lower())
        rec("C: Devbhoomi institution, RB show-cause 3 d ago, PGRC negotiation + hearing", ok)
        pair = lambda x, y: s.scalars(select(CaseLink).where(  # noqa: E731
            CaseLink.case_a_id.in_([x.id, y.id]), CaseLink.case_b_id.in_([x.id, y.id]))).all()
        lc = pair(crb, cpg)
        bad_links = []
        for ln in s.scalars(select(CaseLink)):
            th_ = s.scalar(select(CoordinationThread).where(CoordinationThread.link_id == ln.id))
            f = ln.features or {}
            if not (f.get("suggested_next_action") and f.get("lead_bureau") and th_ is not None
                    and th_.shared_next_action == f["suggested_next_action"]
                    and th_.lead_bureau is not None and th_.lead_bureau.value == f["lead_bureau"]):
                bad_links.append(str(ln.id)[:8])
        rec("every seeded link has suggested_next_action, lead_bureau and a coordination thread",
            not bad_links, str(bad_links[:5]))
        rec("C: CONFLICTING SUGGESTED link seeded", len(lc) == 1 and lc[0].relation.value == "CONFLICTING"
            and lc[0].status.value == "SUGGESTED" and len(lc[0].reasons) > 0, str([(x.relation.value, x.status.value) for x in lc]))
        gy = s.scalar(select(Institution).where(Institution.permanent_id == "1-4458812074"))
        dp, dr = scn["D-PGRC"], scn["D-RO"]
        lf0 = lc[0] if lc else None
        rec("C: link next action is the hold-letters text and lead bureau RB",
            lf0 is not None and (lf0.features or {}).get("suggested_next_action") ==
            "Hold issue of further letters until bureau heads agree a single communication."
            and (lf0.features or {}).get("lead_bureau") == "RB", str((lf0.features or {}).get("lead_bureau")))
        rec("D: Gyanodaya + scholarship (12 d) + RO lab infrastructure (4 d) and NO link row",
            gy.district == "Bhopal" and gy.ro_code == "BPL" and dp.category.value == "SCHOLARSHIP"
            and dr.category.value == "INFRASTRUCTURE" and len(pair(dp, dr)) == 0)
        e1 = s.scalar(select(Institution).where(Institution.permanent_id == "1-4440019921"))
        e2 = s.scalar(select(Institution).where(Institution.permanent_id == "1-4440019987"))
        rec("E: Shri Ram twins, same district, exact names and IDs",
            e1.name == "Shri Ram College of Engineering, Lucknow" and e2.name == "Shri Ram Institute of Technology, Lucknow"
            and e1.district == e2.district == "Lucknow")
        em = scn["A-EMAIL-DUP"]
        lf = pair(em, p2)
        ref_row = s.scalar(select(CaseSourceRef).where(CaseSourceRef.ref == "DHIGH/E/2026/0034517"))
        nf = (lf[0].features or {}) if lf else {}
        rec("F: DUPLICATE next action uses the duplicate template (treat older case as lead)",
            nf.get("suggested_next_action", "").startswith("Treat ") and "reply to complainant once" in
            nf.get("suggested_next_action", ""), str(nf.get("suggested_next_action")))
        rec("F: EMAIL case quotes DHIGH/E/2026/0034517; DUPLICATE SUGGESTED link seeded (not decided)",
            em.source_channel.value == "EMAIL" and "DHIGH/E/2026/0034517" in em.description and ref_row is not None
            and ref_row.case_id == p2.id and len(lf) == 1 and lf[0].relation.value == "DUPLICATE"
            and lf[0].status.value == "SUGGESTED" and lf[0].decided_by is None)

        # ---------------- engine-dependent checks
        try:
            _engine_checks(s, scn, anchor, shri, e1, e2)
        except Exception as exc:  # noqa: BLE001
            rec("engine checks could not run", False, f"{type(exc).__name__}: {exc}")

        # ---------------- demo inputs file
        from app.seed.scenarios import DATA_DIR
        try:
            on_disk = json.loads((DATA_DIR / "demo_inputs.json").read_text(encoding="utf-8"))
            rec("demo_inputs.json matches scenarios.DEMO_INPUTS", on_disk == json.loads(json.dumps(DEMO_INPUTS)))
        except FileNotFoundError:
            rec("demo_inputs.json present", False)
    ok_all = all(RESULTS)
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed" + ("" if ok_all else "  -- FAILURES ABOVE"))
    return ok_all


def _engine_checks(s: Session, scn: dict[str, Case], anchor: datetime, shri: Institution, e1: Institution,
                   e2: Institution) -> None:
    from app.services.caselink import (
        AliasRecord,
        CaseRecord,
        InstitutionIndex,
        InstitutionRecord,
        QueryRecord,
        TfidfCharSimilarity,
        Thresholds,
        detect_relationships,
        resolve_institution,
    )
    from app.services.caselink.relationship import score_pair
    from app.services.classify import classify
    from app.services.normalise import normalise_name, normalise_text

    th = Thresholds()
    insts = [InstitutionRecord(id=i.id, name=i.name, permanent_id=i.permanent_id, name_norm=i.name_norm,
                               district=i.district, state=i.state, pincode=i.pincode, email_domain=i.email_domain,
                               inst_type=i.inst_type, ro_code=i.ro_code) for i in s.scalars(select(Institution))]
    alias_recs = [AliasRecord(institution_id=a.institution_id, alias_norm=a.alias_norm, alias_raw=a.alias_raw,
                              source=a.source) for a in s.scalars(select(InstitutionAlias))]
    index = InstitutionIndex(insts, alias_recs)

    # --- Scenario A live input
    live = DEMO_INPUTS["A"]["payload"]
    q = QueryRecord(institution_text=live["institution_text_raw"], permanent_id_raw=None,
                    text=f"{live['subject']} {live['description']}")
    res = resolve_institution(q, index, thresholds=th)
    reasons = " | ".join(res.reasons)
    rec("A (engine): Hindi input resolves to Shrinath, score >= 0.92, AUTO_SUGGESTED",
        res.selected_id == shri.id and res.score >= 0.92 and res.status == "AUTO_SUGGESTED",
        f"{res.status} {res.score:.3f}")
    rec("A (engine): reasons mention Hindi to English transliteration and district Kanpur",
        ("ransliterat" in reasons) and ("Kanpur" in reasons), reasons[:160])
    cat = classify(live["subject"], live["description"])
    rec("A (engine): category suggestion FEE_REFUND", cat.category == "FEE_REFUND", f"{cat.category} {cat.confidence}")

    all_cases = list(s.scalars(select(Case)))
    all_recs = {r.id: r for r in load_case_records(s, all_cases)}  # production path (parses hearing_at)
    sim = TfidfCharSimilarity([r.similarity_text() for r in all_recs.values()])
    new = CaseRecord(id="live-A", institution_id=shri.id, owner_bureau="PGRC", category=cat.category, status="RECEIVED",
                     received_at=anchor, party_hash="live", subject=live["subject"], description=live["description"],
                     description_norm=normalise_text(live["description"]), display_id="LS-LIVE", source_channel="CSS",
                     institution_permanent_id=shri.permanent_id)
    others = [r for r in all_recs.values() if r.institution_id == shri.id]
    sugg = {x.other_id: x for x in detect_relationships(new, others, sim, th, now=anchor)}
    key_of = {c.id: k for k, c in scn.items()}
    got = {key_of.get(i, str(i)): x.relation for i, x in sugg.items()}
    rec("A (engine): links PGRC-1 RELATED, RO-1 RELATED, RB-1 UNRELATED",
        (got.get("A-PGRC-1"), got.get("A-RO-1"), got.get("A-RB-1")) == ("RELATED", "RELATED", "UNRELATED"),
        f"PGRC-1={got.get('A-PGRC-1')} RO-1={got.get('A-RO-1')} RB-1={got.get('A-RB-1')}  "
        f"(info: PGRC-2={got.get('A-PGRC-2')} EMAIL-DUP={got.get('A-EMAIL-DUP')})")

    # --- Scenario E
    qe = DEMO_INPUTS["E"]["payload"]
    re_ = resolve_institution(QueryRecord(institution_text=qe["institution_text_raw"], text=f"{qe['subject']} {qe['description']}"),
                              index, thresholds=th)
    top2 = {c.institution_id for c in re_.candidates[:2]}
    all_reasons = " ".join(r for c in re_.candidates[:2] for r in c.reasons) + " " + " ".join(re_.reasons)
    rec("E (engine): 'Shri Ram Engg College Lucknow' -> NEEDS_REVIEW, both twins listed, 'Two similar institutions in Lucknow'",
        re_.status == "NEEDS_REVIEW" and top2 == {e1.id, e2.id} and "Two similar institutions in Lucknow" in all_reasons,
        f"{re_.status} " + ", ".join(f"{c.institution.name[:22]}={c.score:.3f}" for c in re_.candidates[:2]))
    alias_new = AliasRecord(institution_id=e1.id, alias_norm=normalise_name(qe["institution_text_raw"]).text,
                            alias_raw=qe["institution_text_raw"], source="CONFIRMED_MATCH", confirmed_by="Officer",
                            confirmed_at=anchor)
    re2 = resolve_institution(QueryRecord(institution_text=qe["institution_text_raw"], text=""),
                              InstitutionIndex(insts, [*alias_recs, alias_new]), thresholds=th)
    rec("E (engine): after confirming one, same text resolves EXACT via alias",
        re2.status == "EXACT" and re2.selected_id == e1.id, re2.status)

    # --- Scenarios C, D, F on the seeded pairs
    def rel(x: str, y: str) -> str:
        a, b = all_recs[scn[x].id], all_recs[scn[y].id]
        new_, old_ = (a, b) if a.received_at >= b.received_at else (b, a)
        return score_pair(new_, old_, sim, th, anchor).relation

    rc, rd, rf = rel("C-RB", "C-PGRC"), rel("D-PGRC", "D-RO"), rel("A-EMAIL-DUP", "A-PGRC-2")
    rec("C (engine): RB show-cause vs PGRC negotiation/hearing -> CONFLICTING", rc == "CONFLICTING", rc)
    rec("D (engine): scholarship vs computer-lab infrastructure -> UNRELATED", rd == "UNRELATED", rd)
    rec("F (engine): EMAIL quoting CPGRAMS ref -> DUPLICATE", rf == "DUPLICATE", rf)

    # --- informational: seeded ground-truth labels vs engine (a measurement, not an assertion)
    groups: dict[tuple[str, str], list[Case]] = {}
    for c in all_cases:
        lab = c.is_seed_label or {}
        for kind in ("dup_group", "related_group", "conflict_group", "negative_group"):
            if lab.get(kind):
                groups.setdefault((kind, lab[kind]), []).append(c)
    want = {"dup_group": "DUPLICATE", "related_group": "RELATED", "conflict_group": "CONFLICTING",
            "negative_group": "UNRELATED"}
    tally: dict[str, list[int]] = {k: [0, 0] for k in want}
    misses: list[str] = []
    for (kind, gid), cs in groups.items():
        if len(cs) != 2:
            continue
        a_, b_ = all_recs[cs[0].id], all_recs[cs[1].id]
        n_, o_ = (a_, b_) if a_.received_at >= b_.received_at else (b_, a_)
        got = score_pair(n_, o_, sim, th, anchor).relation
        tally[kind][1] += 1
        if got == want[kind]:
            tally[kind][0] += 1
        else:
            misses.append(f"{gid}:{got}")
    print("INFO  seeded ground-truth pairs the engine agrees with: "
          + ", ".join(f"{want[k]} {v[0]}/{v[1]}" for k, v in tally.items())
          + (f"  | differing: {' '.join(misses)}" if misses else ""))
