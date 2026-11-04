"""Stage B: same, related or conflicting matter?

Pure functions over ``CaseRecord``.  Nothing here writes, merges or blocks anything: the output
is a list of ``LinkSuggestion`` for an officer to confirm, reject or defer.

Classification is first-match-wins: DUPLICATE > CONFLICTING > RELATED > UNRELATED.

Clarifications of the spec (also listed in the engine report)
-------------------------------------------------------------
* Category family score for two cases both in category OTHER is 0.5, not 1: "OTHER" carries no
  information, so two OTHER cases must not look like the same topic.
* The conflict matrix reads "pending kinds" from ``pending_step``, ``pending_action`` text,
  ``hearing_at`` and ``extra_pending_kinds`` (institution_actions are passed in as pseudo-cases
  by the caller, e.g. ``owner_bureau="APPROVAL", extra_pending_kinds=("DEPOSIT_RELEASE",)``).
* Row 1 of the matrix also fires when the PGRC case is simply awaiting the institution's ATR,
  matching the example reason in B4 ("RB show-cause pending while PGRC awaits institution ATR").
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime

from app.services.caselink import explain
from app.services.caselink.interfaces import TextSimilarity
from app.services.caselink.types import (
    OPEN_EXCLUDED_STATUSES,
    CaseRecord,
    LinkSuggestion,
    Thresholds,
)

FAMILIES: dict[str, frozenset[str]] = {
    "student_dues": frozenset({"FEE_REFUND", "CERTIFICATE_WITHHELD", "ADMISSION"}),
    "regulatory_compliance": frozenset({
        "FACULTY_SHORTAGE", "SCRUTINY_COMMITTEE", "INFRASTRUCTURE", "FAKE_APPROVAL_CLAIM"}),
    "faculty": frozenset({"SERVICE_MATTER", "FACULTY_SHORTAGE"}),
}
LEAD_BY_FAMILY = {"regulatory_compliance": "RB", "student_dues": "PGRC"}
SEVERITY = {"CONFLICTING": 3, "DUPLICATE": 2, "RELATED": 1, "UNRELATED": 0}


# --------------------------------------------------------------------------------------
# Feature helpers
# --------------------------------------------------------------------------------------


def category_score(a: str, b: str) -> float:
    if a == b:
        return 0.5 if a == "OTHER" else 1.0
    return 0.5 if any(a in fam and b in fam for fam in FAMILIES.values()) else 0.0


def category_families(category: str) -> set[str]:
    return {name for name, fam in FAMILIES.items() if category in fam}


def time_score(days: float, th: Thresholds) -> float:
    if days <= th.time_full_days:
        return 1.0
    if days >= th.time_zero_days:
        return 0.0
    return 1.0 - (days - th.time_full_days) / (th.time_zero_days - th.time_full_days)


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def _days_between(a: datetime, b: datetime) -> float:
    return abs((a - b).total_seconds()) / 86400.0


def ref_overlap(a: CaseRecord, b: CaseRecord) -> tuple[str, str | None] | None:
    """Return (ref, channel-of-the-mentioning-case) if the cases share or quote a reference."""
    refs_a = {_squash(r): r for r in a.source_refs if r}
    refs_b = {_squash(r): r for r in b.source_refs if r}
    for k in refs_a.keys() & refs_b.keys():
        return refs_a[k], None
    text_a, text_b = _squash(f"{a.subject} {a.description}"), _squash(f"{b.subject} {b.description}")
    for k, raw in refs_b.items():
        if k and k in text_a:
            return raw, a.source_channel
    for k, raw in refs_a.items():
        if k and k in text_b:
            return raw, b.source_channel
    return None


_STEP_KINDS = {
    "SHOW_CAUSE_REPLY": "SHOW_CAUSE", "INSPECTION": "INSPECTION", "HEARING": "HEARING",
    "REFUND_FOLLOWUP": "REFUND_FOLLOWUP", "INSTITUTION_ATR": "INSTITUTION_ATR",
    "CLEARANCE": "CLEARANCE",
}
_TEXT_KINDS = (
    (re.compile(r"show[\s_\-]*cause"), "SHOW_CAUSE"),
    (re.compile(r"inspection"), "INSPECTION"),
    (re.compile(r"hearing"), "HEARING"),
    (re.compile(r"refund[\s_\-]*follow|negotiation|conciliat"), "REFUND_FOLLOWUP"),
    (re.compile(r"closure"), "CLOSURE_APPROVAL"),
    (re.compile(r"deposit"), "DEPOSIT_RELEASE"),
    (re.compile(r"\bnoc\b"), "NOC"),
)


def pending_kinds(case: CaseRecord) -> set[str]:
    kinds = set(case.extra_pending_kinds)
    if case.pending_step in _STEP_KINDS:
        kinds.add(_STEP_KINDS[case.pending_step])
    text = (case.pending_action or "").lower()
    for pat, kind in _TEXT_KINDS:
        if pat.search(text):
            kinds.add(kind)
    if case.hearing_at is not None:
        kinds.add("HEARING")
    return kinds


def _since(case: CaseRecord, now: datetime) -> str:
    if case.pending_since is None:
        return ""
    return f" ({max(0, int(_days_between(now, case.pending_since)))} days)"


def action_conflict(a: CaseRecord, b: CaseRecord, now: datetime, th: Thresholds) -> str | None:
    """Conflict matrix (B2).  Returns a plain-English reason, or None if no conflict."""
    for x, y in ((a, b), (b, a)):
        kx, ky = pending_kinds(x), pending_kinds(y)
        if (x.owner_bureau == "RB" and "SHOW_CAUSE" in kx and y.owner_bureau == "PGRC"
                and ({"REFUND_FOLLOWUP", "INSTITUTION_ATR"} & ky)):
            what = ("refund follow-up is in progress" if "REFUND_FOLLOWUP" in ky
                    else "awaits the institution's ATR")
            return f"RB show-cause pending while PGRC {what}{_since(y, now)}"
        if (x.owner_bureau == "APPROVAL" and ({"DEPOSIT_RELEASE", "NOC"} & kx)
                and y.owner_bureau in ("PGRC", "VIGILANCE")):
            return (f"Approval Bureau is processing a deposit release / NOC while "
                    f"{y.owner_bureau} has an open matter")
        if ("CLOSURE_APPROVAL" in kx and y.owner_bureau == "PGRC"
                and y.category in ("FEE_REFUND", "CERTIFICATE_WITHHELD")):
            return "Closure approval in progress while students' dues are unresolved at PGRC"
    if ({a.owner_bureau, b.owner_bureau} == {"RB", "RO"}
            and "INSPECTION" in pending_kinds(a) and "INSPECTION" in pending_kinds(b)):
        return "Two inspections of the same institution are scheduled (RB and Regional Office)"
    if (
        {a.owner_bureau, b.owner_bureau} == {"RB", "PGRC"} and a.hearing_at and b.hearing_at
        and _days_between(a.hearing_at, b.hearing_at) <= th.hearing_window_days
    ):
        return "RB and PGRC hearings fall within 7 days of each other"
    return None


def _lead_bureau(a: CaseRecord, b: CaseRecord) -> str:
    cats = {a.category, b.category}
    if "RAGGING" in cats:
        return "PGRC"
    common = category_families(a.category) & category_families(b.category)
    for fam in ("regulatory_compliance", "student_dues"):
        if fam in common:
            return LEAD_BY_FAMILY[fam]
    fa, fb = category_families(a.category), category_families(b.category)
    if "regulatory_compliance" in (fa | fb) and "student_dues" not in (fa | fb):
        return "RB"
    if "student_dues" in (fa | fb) and "regulatory_compliance" not in (fa | fb):
        return "PGRC"
    return (a if a.received_at <= b.received_at else b).owner_bureau


def _next_action(relation: str, a: CaseRecord, b: CaseRecord, conflict: str | None) -> str | None:
    older, newer = (a, b) if a.received_at <= b.received_at else (b, a)
    if relation == "DUPLICATE":
        return f"Treat {older.label} as lead; reply to complainant once, referencing both IDs."
    if relation == "CONFLICTING":
        if conflict and "show-cause" in conflict:
            return ("Hold issue of further letters until bureau heads agree a single "
                    "communication.")
        return ("Bureau heads to agree the order of the two pending actions before either "
                "bureau proceeds.")
    if relation == "RELATED":
        bureaus = {a.owner_bureau, b.owner_bureau}
        if bureaus == {"PGRC", "RB"}:
            return "PGRC to share ATR status with RB before RB's next letter to the institution."
        if a.owner_bureau == b.owner_bureau:
            return (f"Handle {older.label} and {newer.label} together and send the institution "
                    "one combined letter.")
        return (f"{older.owner_bureau} and {newer.owner_bureau} to share status and agree one "
                "point of contact before the next letter to the institution.")
    return None


# --------------------------------------------------------------------------------------
# Pair scoring
# --------------------------------------------------------------------------------------


def semantic_similarity(a: CaseRecord, b: CaseRecord, similarity: TextSimilarity,
                        th: Thresholds) -> float:
    """TF-IDF char n-gram cosine of the case texts, lifted by topic agreement.

    A one-line query ("status of fee refund") and a long Hinglish letter share few character
    n-grams even though they are plainly about the same thing, so the cosine of the two topic
    signatures (canonical keywords of the dominant category, language independent) counts for
    ``topic_weight`` of its value when that is higher than the plain text cosine.
    """
    full = similarity.similarity(a.similarity_text(), b.similarity_text())
    ta, tb = a.topic_text(), b.topic_text()
    topic = similarity.similarity(ta, tb) if ta and tb else 0.0
    return max(0.0, min(1.0, max(full, th.topic_weight * topic)))


def score_pair(new: CaseRecord, other: CaseRecord, similarity: TextSimilarity,
               th: Thresholds, now: datetime) -> LinkSuggestion:
    ref = ref_overlap(new, other)
    s_ref = 1.0 if ref else 0.0
    s_party = 1.0 if (new.party_hash and new.party_hash == other.party_hash) else 0.0
    s_sem = semantic_similarity(new, other, similarity, th)
    s_cat = category_score(new.category, other.category)
    days = _days_between(new.received_at, other.received_at)
    s_time = time_score(days, th)
    diff_bureau = new.owner_bureau != other.owner_bureau
    conflict = action_conflict(new, other, now, th)

    overlap = (th.w_semantic * s_sem + th.w_category * s_cat + th.w_time * s_time
               + th.w_party * s_party)
    if s_ref:
        overlap = max(overlap, th.ref_floor)

    if (s_ref or (overlap >= th.dup and s_party)
            or (overlap >= th.dup_strict and new.category == other.category
                and days <= th.dup_days)):
        relation = "DUPLICATE"
    elif conflict and (overlap >= th.conflict_overlap or s_cat >= th.conflict_category):
        relation = "CONFLICTING"
    elif overlap >= th.related and (diff_bureau or s_cat >= th.related_category):
        relation = "RELATED"
    else:
        relation = "UNRELATED"

    reasons: list[str] = []
    if relation == "UNRELATED":
        reasons.append("Same institution · unrelated issue")
        reasons.append(explain.text_similarity(s_sem))
        if s_cat == 0:
            reasons.append(f"Different subjects ({explain.category_word(new.category)} and "
                           f"{explain.category_word(other.category)})")
    else:
        if ref:
            reasons.append(explain.ref_shared(ref[0]) if ref[1] is None
                           else explain.ref_mentioned(ref[0], ref[1].upper() if ref[1] else None))
        if conflict:
            reasons.append(explain.action_conflict(conflict))
        reasons.append(explain.same_institution(new.institution_permanent_id
                                                or other.institution_permanent_id))
        if s_cat == 1.0:
            reasons.append(explain.same_category(new.category))
        elif s_cat > 0:
            reasons.append(explain.related_category(new.category, other.category))
        reasons.append(explain.text_similarity(s_sem))
        if s_party:
            reasons.append(explain.same_complainant())
        reasons.append(explain.days_apart(int(round(days))))
        if diff_bureau:
            reasons.append(explain.different_bureaus(new.owner_bureau, other.owner_bureau))

    features = {
        "s_ref": s_ref, "s_party": s_party, "s_semantic": round(s_sem, 3),
        "s_category": s_cat, "s_time": round(s_time, 3), "diff_bureau": diff_bureau,
        "action_conflict": conflict is not None, "overlap": round(overlap, 3),
        "days_apart": round(days, 1),
    }
    return LinkSuggestion(
        case_id=new.id, other_id=other.id, relation=relation, score=round(overlap, 3),
        features=features, reasons=reasons,
        suggested_next_action=_next_action(relation, new, other, conflict),
        lead_bureau=_lead_bureau(new, other) if relation != "UNRELATED" else None,
    )


def is_candidate(case: CaseRecord, now: datetime, th: Thresholds) -> bool:
    """Open, or disposed within the look-back window (B, first paragraph)."""
    if case.status not in OPEN_EXCLUDED_STATUSES:
        return True
    if case.status == "DISPOSED" and case.disposed_at is not None:
        return _days_between(now, case.disposed_at) <= th.disposed_lookback_days
    return False


def is_open(case: CaseRecord) -> bool:
    return case.status not in OPEN_EXCLUDED_STATUSES


def _ensure_fitted(similarity: TextSimilarity, texts: list[str]) -> None:
    if not getattr(similarity, "is_fitted", True):
        similarity.fit(texts)


def detect(
    new: CaseRecord,
    others: Sequence[CaseRecord],
    similarity: TextSimilarity,
    thresholds: Thresholds | None = None,
    now: datetime | None = None,
    *,
    include_unrelated: bool = True,
) -> list[LinkSuggestion]:
    """Relate ``new`` to every other case on the same institution.  Advisory only."""
    th = thresholds or Thresholds()
    now = now or new.received_at
    pool = [
        o for o in others
        if o.id != new.id
        and (new.institution_id is None or o.institution_id is None
             or o.institution_id == new.institution_id)
        and is_candidate(o, now, th)
    ]
    if not pool:
        return []
    _ensure_fitted(similarity, [new.similarity_text(), *(o.similarity_text() for o in pool)])
    out = [score_pair(new, o, similarity, th, now) for o in pool]
    if not include_unrelated:
        out = [s for s in out if s.relation != "UNRELATED"]
    out.sort(key=lambda s: (-SEVERITY[s.relation], -s.score))
    return out


detect_relationships = detect
