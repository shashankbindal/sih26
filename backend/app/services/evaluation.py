"""CaseLink evaluation on labelled synthetic data.

Ground truth is `cases.is_seed_label` ({true_institution_id, dup_group, related_group,
conflict_group}).  Everything is measured by running the real engine in `app.services.caselink`;
nothing here is hard-coded or fabricated, and every number carries its N.

Method notes (also returned in the payload):
* Stage A: each labelled case whose true institution is in the evaluated split is resolved against
  the full register.  Aliases of held-out institutions are withheld so the matcher is not helped by
  lookups that were never part of its tuning data.
* Stage B: pairs of cases on the same TRUE institution (isolates stage B from stage A mistakes) are
  scored as of the arrival time of the newer case.  Cases later disposed are treated as still open at
  that moment, as they were in production.
* Truth for a pair: same dup_group -> DUPLICATE, else same conflict_group -> CONFLICTING, else same
  related_group -> RELATED, else UNRELATED (same precedence as the engine).
"""

from __future__ import annotations

import random
import re
import threading
import time
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.cases import Case, CaseSourceRef
from app.models.complainants import Complainant
from app.models.institutions import Institution, InstitutionAlias
from app.models.system import PolicyConfig
from app.services import normalise
from app.services.caselink import (
    AliasRecord,
    CaseRecord,
    InstitutionIndex,
    InstitutionRecord,
    QueryRecord,
    TfidfCharSimilarity,
    Thresholds,
    resolve_institution,
    score_pair,
)

SPLIT_SEED = 26264
RELATIONS = ("UNRELATED", "DUPLICATE", "RELATED", "CONFLICTING")
CACHE_TTL_SECONDS = 600
TARGET_MATCH_RECALL = 0.95
TARGET_ALERT_PRECISION = 0.80
REVIEW_TOP_K = 3
_DEV = re.compile(r"[ऀ-ॿ]")

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def _f1(p: float | None, r: float | None) -> float | None:
    if p is None or r is None or (p + r) == 0:
        return None if p is None or r is None else 0.0
    return round(2 * p * r / (p + r), 4)


# ------------------------------------------------------------------------------------- split
def load_split(
    session: Session, institutions: list[Institution], scenario_ids: set[Any], cases: list[Case]
) -> tuple[dict[str, str], str]:
    """{institution_id: 'train'|'heldout'}.  Prefers the split the seed generator wrote into each
    case's is_seed_label (`split`), then policy_config.eval_split, then a deterministic derivation."""
    from_labels: dict[str, str] = {}
    for c in cases:
        lab = c.is_seed_label or {}
        if lab.get("split") in ("train", "heldout") and lab.get("true_institution_id"):
            from_labels[str(lab["true_institution_id"])] = lab["split"]
    if from_labels:
        return {str(i.id): from_labels.get(str(i.id), "train") for i in institutions}, "seed labels (is_seed_label.split)"
    row = session.get(PolicyConfig, "eval_split")
    if row is not None and isinstance(row.value, dict):
        v = row.value
        if isinstance(v.get("heldout"), list):
            held = {str(x) for x in v["heldout"]}
            return {str(i.id): ("heldout" if str(i.id) in held else "train") for i in institutions}, "policy_config.eval_split"
        if all(isinstance(x, str) for x in v.values()):
            return {str(i.id): v.get(str(i.id), "train") for i in institutions}, "policy_config.eval_split"
    # deterministic fallback mirroring the seed spec: 70/30 by institution, seed 26264, demo institutions in train
    demo = {str(i) for i in scenario_ids}
    rest = sorted(str(i.id) for i in institutions if str(i.id) not in demo)
    random.Random(SPLIT_SEED).shuffle(rest)
    n_train = round(0.7 * len(institutions)) - len(demo)
    split = {i: "train" for i in demo}
    for k, iid in enumerate(rest):
        split[iid] = "train" if k < n_train else "heldout"
    return split, "derived (70/30 by institution, seed 26264, scenario institutions in train)"


# ---------------------------------------------------------------------------------- failures
def _stage_a_reasons(
    case: Case, res: Any, truth_inst: Institution, by_id: dict[str, Institution], pids: set[str]
) -> list[str]:
    reasons: list[str] = []
    raw = case.institution_text_raw or ""
    if _DEV.search(raw):
        reasons.append("Institution written in Devanagari")
    if len(raw.split()) <= 2:
        reasons.append("Very short institution text")
    if not case.permanent_id_raw:
        reasons.append("No Permanent ID in the complaint")
    elif case.permanent_id_raw.strip() not in pids:
        reasons.append("Permanent ID quoted does not exist (typo)")
    if len((case.description or "").split()) < 12:
        reasons.append("Very short complaint text")
    top = res.candidates[0] if res.candidates else None
    if top is not None and str(top.institution_id) != str(truth_inst.id):
        other = by_id.get(str(top.institution_id))
        if other is not None and other.district and other.district == truth_inst.district:
            reasons.append(f"Two institutions in {truth_inst.district} have similar names ({other.name} vs {truth_inst.name})")
        else:
            reasons.append("A different register entry scored higher than the correct one")
    elif top is None:
        reasons.append("No candidate found in the register")
    return reasons[:5]


def _stage_b_reasons(truth: str, pred: str, s: Any, th: Thresholds) -> list[str]:
    f = s.features or {}
    cat = f.get("s_category")
    parts = [
        f"text similarity {float(f.get('s_semantic', 0.0)):.2f}",
        "same category" if cat == 1 else "related category family" if cat == 0.5 else "different categories",
        f"{float(f.get('days_apart', 0.0)):.0f} days apart",
        "different bureaus" if f.get("diff_bureau") else "same bureau",
    ]
    if f.get("action_conflict"):
        parts.append("pending actions interact")
    if f.get("s_party") == 1:
        parts.append("same complainant")
    base = f"Labelled {truth}, engine said {pred} (overlap {s.score:.2f}): " + ", ".join(parts)
    if truth == "UNRELATED":
        base += f". Related threshold is {th.related:.2f}"
    return [base]


# ------------------------------------------------------------------------------------- main
def _case_record(case: Case, comp_name: str | None, party_hash: str | None, refs: tuple[str, ...], inst_id: Any, perm: str | None) -> CaseRecord:
    desc = normalise.mask_pii(case.description or "", known_names=(comp_name,) if comp_name else ())
    return CaseRecord(
        id=str(case.id),
        institution_id=str(inst_id),
        owner_bureau=case.owner_bureau.value,
        category=case.category.value,
        status=case.status.value,
        received_at=case.received_at,
        pending_step=case.pending_step.value,
        pending_action=case.pending_action,
        party_hash=party_hash,
        source_refs=refs,
        subject=case.subject or "",
        description=desc,
        description_norm=case.description_norm or normalise.normalise_text(case.description or ""),
        display_id=case.display_id,
        source_channel=case.source_channel.value,
        disposed_at=case.disposed_at,
        pending_since=case.pending_since,
        institution_permanent_id=perm,
    )


def _truth_relation(a: dict[str, Any], b: dict[str, Any]) -> str:
    for key, name in (("dup_group", "DUPLICATE"), ("conflict_group", "CONFLICTING"), ("related_group", "RELATED")):
        ga, gb = a.get(key), b.get(key)
        if ga not in (None, "") and ga == gb:
            return name
    return "UNRELATED"


def _as_of(rec: CaseRecord, when: datetime) -> CaseRecord:
    """Present a case as it looked when `when` arrived: still open if it was disposed later."""
    if rec.status in ("DISPOSED", "CLOSED_NO_ACTION") and (rec.disposed_at is None or rec.disposed_at > when):
        return replace(rec, status="UNDER_PROCESS", disposed_at=None)
    return rec


def compute(session: Session, split: str = "heldout") -> dict[str, Any]:
    started = time.perf_counter()
    now = datetime.now(UTC)
    policy_row = session.get(PolicyConfig, "thresholds")
    th = Thresholds.from_policy(policy_row.value if policy_row and isinstance(policy_row.value, dict) else None)

    institutions = list(session.scalars(select(Institution)))
    by_id = {str(i.id): i for i in institutions}
    cases = list(session.scalars(select(Case).where(Case.is_seed_label.is_not(None))))
    if not institutions or not cases:
        raise ApiError(
            409,
            "NO_GROUND_TRUTH",
            "No labelled synthetic data found. Run `python -m app.seed.generate --reset` first.",
        )
    scenario_inst = {
        (c.is_seed_label or {}).get("true_institution_id") or str(c.institution_id)
        for c in cases
        if (c.is_seed_label or {}).get("scenario_key")
    }
    split_map, split_source = load_split(session, institutions, {i for i in scenario_inst if i in by_id}, cases)
    wanted = {"heldout": {"heldout"}, "train": {"train"}, "all": {"heldout", "train"}}[split]
    eval_ids = {i for i, s in split_map.items() if s in wanted}

    labelled: list[tuple[Case, str]] = []
    unlabelled = 0
    for c in cases:
        tid = (c.is_seed_label or {}).get("true_institution_id")
        if not tid:
            unlabelled += 1
            continue
        if str(tid) in eval_ids:
            labelled.append((c, str(tid)))

    # ---- stage A -------------------------------------------------------------------------
    withheld = {i for i, s in split_map.items() if s == "heldout"} if split != "train" else set()
    alias_rows = list(session.scalars(select(InstitutionAlias).where(InstitutionAlias.source == "SEED")))
    aliases = [
        AliasRecord(str(a.institution_id), a.alias_norm, a.alias_raw, a.source)
        for a in alias_rows
        if str(a.institution_id) not in withheld
    ]
    inst_records = [
        InstitutionRecord(
            id=str(i.id), name=i.name, permanent_id=i.permanent_id, name_norm=i.name_norm, district=i.district,
            state=i.state, pincode=i.pincode, email_domain=i.email_domain, inst_type=i.inst_type, ro_code=i.ro_code,
        )
        for i in institutions
    ]
    index = InstitutionIndex(inst_records, aliases)
    pids = {i.permanent_id for i in institutions}

    band_n: Counter[str] = Counter()
    band_correct: Counter[str] = Counter()
    band_true_in_k: Counter[str] = Counter()
    hits_at_auto_review = 0
    top1_hits = 0
    failures: list[dict[str, Any]] = []
    for c, tid in labelled:
        q = QueryRecord(
            institution_text=c.institution_text_raw or "",
            permanent_id_raw=c.permanent_id_raw,
            text=f"{c.subject or ''} {c.description or ''}".strip(),
        )
        res = resolve_institution(q, index, thresholds=th)
        status = res.status
        band_n[status] += 1
        cand_ids = [str(x.institution_id) for x in res.candidates]
        top1 = cand_ids[0] if cand_ids else None
        sel = str(res.selected_id) if res.selected_id is not None else None
        in_k = tid in cand_ids[:REVIEW_TOP_K]
        if top1 == tid:
            top1_hits += 1
        if status in ("EXACT", "AUTO_SUGGESTED"):
            ok = sel == tid
            band_correct[status] += ok
            if ok:
                hits_at_auto_review += 1
            else:
                failures.append(
                    {
                        "severity": 100 + res.score,
                        "stage": "A", "kind": "WRONG_AUTO_MATCH",
                        "case": c.display_id, "other_case": None,
                        "institution": by_id[tid].name,
                        "expected": by_id[tid].name, "predicted": by_id[sel].name if sel in by_id else None,
                        "score": round(res.score, 3),
                        "reasons": _stage_a_reasons(c, res, by_id[tid], by_id, pids),
                    }
                )
        elif status == "NEEDS_REVIEW":
            band_correct[status] += top1 == tid
            band_true_in_k[status] += in_k
            if in_k:
                hits_at_auto_review += 1
            else:
                failures.append(
                    {
                        "severity": 80 + (res.score if res.selected else 0),
                        "stage": "A", "kind": "TRUE_INSTITUTION_NOT_SHOWN",
                        "case": c.display_id, "other_case": None, "institution": by_id[tid].name,
                        "expected": by_id[tid].name, "predicted": by_id[top1].name if top1 in by_id else None,
                        "score": round(res.score, 3),
                        "reasons": _stage_a_reasons(c, res, by_id[tid], by_id, pids),
                    }
                )
        else:
            band_true_in_k[status] += in_k
            failures.append(
                {
                    "severity": 70, "stage": "A", "kind": "NO_CONFIDENT_MATCH",
                    "case": c.display_id, "other_case": None, "institution": by_id[tid].name,
                    "expected": by_id[tid].name, "predicted": None, "score": round(res.score, 3),
                    "reasons": _stage_a_reasons(c, res, by_id[tid], by_id, pids),
                }
            )
    n_a = len(labelled)
    auto_n = band_n["EXACT"] + band_n["AUTO_SUGGESTED"]
    auto_ok = band_correct["EXACT"] + band_correct["AUTO_SUGGESTED"]

    def band_row(name: str, n: int, correct: int) -> dict[str, Any]:
        p, r = _ratio(correct, n), _ratio(correct, n_a)
        return {"band": name, "n_in_band": n, "correct": correct, "n_total": n_a, "precision": p, "recall": r, "f1": _f1(p, r)}

    review_n = band_n["NEEDS_REVIEW"]
    stage_a = {
        "n": n_a,
        "n_unlabelled_excluded": unlabelled,
        "bands": [
            band_row("EXACT", band_n["EXACT"], band_correct["EXACT"]),
            band_row("AUTO_SUGGESTED", band_n["AUTO_SUGGESTED"], band_correct["AUTO_SUGGESTED"]),
            band_row("AUTO (EXACT + AUTO_SUGGESTED)", auto_n, auto_ok),
            band_row("NEEDS_REVIEW (top-1)", review_n, band_correct["NEEDS_REVIEW"]),
        ],
        "needs_review_true_in_top3": {"hits": band_true_in_k["NEEDS_REVIEW"], "n": review_n, "value": _ratio(band_true_in_k["NEEDS_REVIEW"], review_n)},
        "unresolved": {"n": band_n["UNRESOLVED"], "true_in_candidates": band_true_in_k["UNRESOLVED"]},
        "recall_at_auto_review": {"value": _ratio(hits_at_auto_review, n_a), "hits": hits_at_auto_review, "n": n_a, "review_top_k": REVIEW_TOP_K},
        "top1_accuracy": {"value": _ratio(top1_hits, n_a), "hits": top1_hits, "n": n_a},
        "wrong_auto": {"n": auto_n - auto_ok, "of": auto_n},
    }

    # ---- stage B -------------------------------------------------------------------------
    comp_ids = [cs.complainant_id for cs, _ in labelled]
    comp = (
        {c.id: (c.name, c.party_hash) for c in session.scalars(select(Complainant).where(Complainant.id.in_(comp_ids)))}
        if comp_ids
        else {}
    )
    refs: dict[Any, list[str]] = defaultdict(list)
    ids = [cs.id for cs, _ in labelled]
    if ids:
        for r in session.scalars(select(CaseSourceRef).where(CaseSourceRef.case_id.in_(ids))):
            refs[r.case_id].append(r.ref)
    records: dict[str, CaseRecord] = {}
    labels: dict[str, dict[str, Any]] = {}
    by_inst: dict[str, list[str]] = defaultdict(list)
    for c, tid in labelled:
        name, ph = comp.get(c.complainant_id, (None, None))
        rs = tuple(dict.fromkeys([*(refs.get(c.id, [])), *([c.source_ref] if c.source_ref else [])]))
        rec = _case_record(c, name, ph, rs, tid, by_id[tid].permanent_id)
        records[rec.id] = rec
        labels[rec.id] = c.is_seed_label or {}
        by_inst[tid].append(rec.id)
    sim = TfidfCharSimilarity()
    sim.fit([r.similarity_text() for r in records.values()] or ["x"])

    confusion: dict[tuple[str, str], int] = Counter()
    n_pairs = 0
    for tid, rec_ids in by_inst.items():
        recs = sorted((records[i] for i in rec_ids), key=lambda r: (r.received_at, r.id))
        for i, newer in enumerate(recs):
            for older in recs[:i]:
                when = newer.received_at
                a, b = _as_of(newer, when), _as_of(older, when)
                s = score_pair(a, b, sim, th, when)
                truth = _truth_relation(labels[newer.id], labels[older.id])
                n_pairs += 1
                confusion[(truth, s.relation)] += 1
                if truth != s.relation:
                    miss = {"CONFLICTING": 90, "DUPLICATE": 70, "RELATED": 50}.get(truth, 0)
                    sev = (miss + s.score * 10) if s.relation == "UNRELATED" else (
                        (60 if truth == "UNRELATED" else 40) + s.score * 10
                    )
                    kind = (
                        "FALSE_ALERT" if truth == "UNRELATED"
                        else f"MISSED_{truth}" if s.relation == "UNRELATED"
                        else f"WRONG_RELATION_{truth}_AS_{s.relation}"
                    )
                    failures.append(
                        {
                            "severity": sev, "stage": "B", "kind": kind,
                            "case": newer.display_id, "other_case": older.display_id,
                            "institution": by_id[tid].name, "expected": truth, "predicted": s.relation,
                            "score": round(s.score, 3),
                            "reasons": _stage_b_reasons(truth, s.relation, s, th),
                        }
                    )
    matrix = [[int(confusion.get((t, p), 0)) for p in RELATIONS] for t in RELATIONS]
    classes = []
    for k, rel in enumerate(RELATIONS):
        tp = matrix[k][k]
        n_true = sum(matrix[k])
        n_pred = sum(matrix[r][k] for r in range(4))
        classes.append(
            {"relation": rel, "n_true": n_true, "n_predicted": n_pred, "true_positives": tp,
             "precision": _ratio(tp, n_pred), "recall": _ratio(tp, n_true)}
        )
    alerts = sum(matrix[t][p] for t in range(4) for p in range(1, 4))
    true_alerts = sum(matrix[t][p] for t in range(1, 4) for p in range(1, 4))
    strict_alerts = sum(matrix[k][k] for k in range(1, 4))
    stage_b = {
        "n_pairs": n_pairs,
        "n_cases": len(records),
        "labels": list(RELATIONS),
        "confusion_matrix": matrix,
        "classes": classes,
        "alert_precision": {
            "value": _ratio(true_alerts, alerts), "true_alerts": true_alerts, "alerts": alerts,
            "strict_value": _ratio(strict_alerts, alerts),
        },
    }

    # ---- targets -------------------------------------------------------------------------
    rec_v = stage_a["recall_at_auto_review"]["value"]
    ap_v = stage_b["alert_precision"]["value"]

    def target(name: str, goal: float, measured: float | None, n: int, what: str) -> dict[str, Any]:
        if measured is None:
            return {"name": name, "target": goal, "measured": None, "n": n, "passed": None, "text": f"NOT MEASURED: no {what} in this split"}
        ok = measured >= goal
        return {
            "name": name, "target": goal, "measured": measured, "n": n, "passed": ok,
            "text": f"{'PASS' if ok else 'NOT MET'}: {measured * 100:.1f}% measured on N={n} {what} (target ≥ {goal * 100:.0f}%)",
        }

    targets = [
        target("Institution match recall (auto + review)", TARGET_MATCH_RECALL, rec_v, n_a, "labelled complaints"),
        target("Coordination alert precision", TARGET_ALERT_PRECISION, ap_v, alerts, "alerts raised"),
    ]
    failures.sort(key=lambda f: -f["severity"])
    top = [{k: v for k, v in f.items() if k != "severity"} for f in failures[:10]]
    return {
        "split": split,
        "split_source": split_source,
        "evaluated_institutions": len(eval_ids),
        "generated_at": now,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "cached": False,
        "thresholds_used": {k: v for k, v in asdict(th).items() if k in ("inst_auto", "inst_review", "near_twin_gap", "dup", "dup_strict", "related", "conflict_overlap")},
        "stage_a": stage_a,
        "stage_b": stage_b,
        "targets": targets,
        "failure_cases": top,
        "failure_total": len(failures),
        "notes": [
            "Aliases of held-out institutions are withheld in stage A.",
            "Stage B pairs use the true institution and are scored as of the newer case's arrival.",
            "Synthetic data only; numbers describe this synthetic set, not production performance.",
        ],
    }


def run(session: Session, split: str = "heldout", refresh: bool = False) -> dict[str, Any]:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(split)
        if hit and not refresh and now - hit[0] < CACHE_TTL_SECONDS:
            return {**hit[1], "cached": True}
        result = compute(session, split)
        _cache[split] = (now, result)
        return result


def clear_cache() -> None:
    with _lock:
        _cache.clear()

