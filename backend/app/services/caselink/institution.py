"""Stage A: is this the same institution?

Order of evidence: exact Permanent ID (field, then free text) -> exact confirmed alias ->
in-memory blocking (RapidFuzz instead of pg_trgm) -> Fellegi-Sunter style weighted scoring.

Prior calibration (read this before changing numbers)
-----------------------------------------------------
The spec prior is ``log2(1/N)``.  That is right for an unblocked comparison against all N
institutions, but candidates here are pre-filtered by district / pincode / name similarity, so
the realistic pool is a few dozen.  With N = 200 the raw prior is -7.6 bits, which puts a
medium name match + same district (+3.3 +4.2) at 0.48 and even "strong name + district" at
only 0.97.  We therefore use ``prior = -log2(min(N, prior_pool_cap))`` with
``prior_pool_cap = 32`` (-5.0 bits for any realistic N).  Resulting behaviour, checked in
``tests/engine/test_institution.py``:

* strong name (+8.4) + same district (+4.2)               -> 0.99+   AUTO_SUGGESTED
* medium name (+3.3) + same district, no distinctive word -> ~0.85   NEEDS_REVIEW
* strong name, district missing                            -> ~0.91   NEEDS_REVIEW
* strong name + different district (-3.2)                  -> ~0.50   UNRESOLVED
  (a shared rare word can still lift this above 0.92; an AUTO result whose district
  contradicts the register is therefore downgraded to NEEDS_REVIEW)
* shared rare word ("shrinath", +6.3) lifts a medium name + district to 0.99+

Scores are capped at 0.999 (only EXACT reports 1.000).  The near-twin rule works on the
capped probabilities, so two saturated candidates in one district always go to review.

Other deliberate deviations from the spec table
-----------------------------------------------
* Name comparison strips stop words and the district / city words from both sides (an official
  name "..., Kanpur" would otherwise never match a query that omitted the city) and compares
  spelling-folded tokens (``sh -> s`` etc.) so "Shree" and "Shri" are equal.
* ``name_similarity = max(JW, token_set, 0.95 * partial_ratio, 0.92 * core_similarity)`` where
  core similarity compares only non-generic words (drops "college", "institute",
  "engineering", ...).  Without it "Shrinath Engineering College" scores only ~0.8 against
  "Shrinath Institute of Engineering and Technology", the worked example for Hindi institution matching.
* "Distinctive token" is absent -> weight 0 (the spec lists only the present level).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import jellyfish
from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

from app.services.caselink import explain
from app.services.caselink.types import (
    AliasRecord,
    Candidate,
    Id,
    InstitutionRecord,
    QueryRecord,
    Resolution,
    Thresholds,
)
from app.services.normalise import (
    NormalisedName,
    clean_permanent_id,
    district_forms,
    extract_district,
    extract_permanent_id,
    extract_pincode,
    fold_key,
    normalise_name,
)

MAX_PROBABILITY = 0.999

# (m, u) per comparison level; weight = log2(m / u)
FS_PARAMS: dict[str, tuple[float, float]] = {
    "name_strong": (0.70, 0.002),
    "name_medium": (0.20, 0.02),
    "name_weak": (0.07, 0.10),
    "name_none": (0.03, 0.878),
    "district_equal": (0.90, 0.05),
    "district_different": (0.10, 0.95),
    "pincode_equal": (0.85, 0.003),
    "pincode_different": (0.15, 0.997),
    "email_equal": (0.60, 0.0005),
    "distinctive_present": (0.80, 0.01),
}
WEIGHTS: dict[str, float] = {k: math.log2(m / u) for k, (m, u) in FS_PARAMS.items()}

GENERIC_WORDS = frozenset({
    "college", "institute", "engineering", "technology", "management", "pharmacy", "polytechnic",
    "university", "school", "studies", "sciences", "science", "education", "research", "academy",
    "technical", "institution", "applications", "computer", "mca", "mba", "group", "campus",
    "foundation", "trust", "society", "centre", "center", "saint", "government",
})
NON_DISTINCTIVE = frozenset({"sri"})   # folded form of "shri": too common to be distinctive
CORE_FACTOR = 0.92
FREE_EMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com", "rediffmail.com",
    "live.com", "icloud.com", "proton.me", "protonmail.com",
})


# --------------------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------------------


@dataclass
class _Entry:
    inst: InstitutionRecord
    nn: NormalisedName
    tokens: tuple[str, ...]          # comparison tokens (location words removed)
    folded: tuple[str, ...]
    core: tuple[str, ...]            # folded non-generic tokens
    cmp_str: str
    district_norm: str


class InstitutionIndex:
    """Pre-computed lookups over the institution register; build once, reuse per request."""

    def __init__(self, institutions: Sequence[InstitutionRecord], aliases: Sequence[AliasRecord]):
        self.institutions = list(institutions)
        self.n = len(self.institutions)
        self.entries: dict[Id, _Entry] = {}
        self.by_pid: dict[str, InstitutionRecord] = {}
        self.districts: list[str] = sorted({i.district for i in self.institutions if i.district})
        self._location_tokens: set[str] = set()
        for d in self.districts:
            for form in district_forms(d):
                self._location_tokens.update(form.split())
        self._location_tokens -= {"nagar", "urban", "rural", "city", "district", "dist"}
        self.by_pincode: dict[str, list[Id]] = {}
        self.by_district: dict[str, list[Id]] = {}
        for inst in self.institutions:
            nn = normalise_name(inst.name_norm or inst.name)
            own = {t for f in district_forms(inst.district or "") for t in f.split()}
            tokens = tuple(t for t in nn.tokens if t not in own) or nn.tokens
            folded = tuple(fold_key(t) for t in tokens)
            core = tuple(f for t, f in zip(tokens, folded, strict=True) if t not in GENERIC_WORDS)
            self.entries[inst.id] = _Entry(
                inst, nn, tokens, folded, core, " ".join(folded),
                " ".join(normalise_name(inst.district or "").tokens),
            )
            if inst.permanent_id:
                self.by_pid[inst.permanent_id.replace(" ", "")] = inst
            if inst.pincode:
                self.by_pincode.setdefault(inst.pincode, []).append(inst.id)
            if inst.district:
                self.by_district.setdefault(inst.district, []).append(inst.id)
        self.df: Counter[str] = Counter()
        for e in self.entries.values():
            self.df.update(set(e.folded))
        self.aliases = list(aliases)
        self.alias_by_key: dict[str, list[AliasRecord]] = {}
        for a in self.aliases:
            if a.institution_id in self.entries:
                key = normalise_name(a.alias_norm).key
                if key:
                    self.alias_by_key.setdefault(key, []).append(a)
        self._choice_keys: list[str] = []
        self._choice_owner: list[Id] = []
        for e in self.entries.values():
            self._choice_keys.append(e.cmp_str)
            self._choice_owner.append(e.inst.id)
        for a in self.aliases:
            if a.institution_id in self.entries:
                nn = normalise_name(a.alias_norm)
                toks = tuple(t for t in nn.tokens if t not in self._location_tokens) or nn.tokens
                self._choice_keys.append(" ".join(fold_key(t) for t in toks))
                self._choice_owner.append(a.institution_id)

    def query_tokens(self, nn: NormalisedName, district: str | None) -> tuple[str, ...]:
        strip = set(self._location_tokens)
        if district:
            for f in district_forms(district):
                strip.update(f.split())
        kept = tuple(t for t in nn.tokens if t not in strip and not t.isdigit())
        return kept or nn.tokens


# --------------------------------------------------------------------------------------
# Query context and scoring
# --------------------------------------------------------------------------------------


@dataclass
class _Ctx:
    nn: NormalisedName
    tokens: tuple[str, ...]
    folded: tuple[str, ...]
    core: tuple[str, ...]
    cmp_str: str
    display: str
    district: str | None
    pincode: str | None
    email_domain: str | None
    pid: str | None
    pid_in_text: bool
    extracted: dict[str, str | None] = field(default_factory=dict)


def _build_ctx(query: QueryRecord, index: InstitutionIndex) -> _Ctx:
    nn = normalise_name(query.institution_text)
    district = query.district or extract_district(query.institution_text, index.districts)
    if not district:
        district = extract_district(query.text, index.districts)
    pincode = query.pincode or extract_pincode(query.institution_text) or extract_pincode(query.text)
    pid = clean_permanent_id(query.permanent_id_raw)
    in_text = False
    if pid is None:
        pid = extract_permanent_id(query.institution_text) or extract_permanent_id(query.text)
        in_text = pid is not None
    email = (query.email_domain or "").lower().strip() or None
    if email in FREE_EMAIL_DOMAINS:
        email = None
    tokens = index.query_tokens(nn, district)
    folded = tuple(fold_key(t) for t in tokens)
    core = tuple(f for t, f in zip(tokens, folded, strict=True) if t not in GENERIC_WORDS)
    return _Ctx(
        nn, tokens, folded, core, " ".join(folded), " ".join(tokens), district, pincode, email,
        pid, in_text,
        {"permanent_id": pid, "district": district, "pincode": pincode},
    )


@dataclass
class NameSim:
    effective: float
    full: float
    core: float
    jw: float
    token_set: float
    partial: float


def name_similarity(q_folded: str, q_core: Sequence[str], c_folded: str, c_core: Sequence[str]
                    ) -> NameSim:
    if not q_folded or not c_folded:
        return NameSim(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    jw = jellyfish.jaro_winkler_similarity(q_folded, c_folded)
    ts = fuzz.token_set_ratio(q_folded, c_folded) / 100
    partial = 0.0
    if min(len(q_folded), len(c_folded)) >= 8:
        partial = fuzz.partial_ratio(q_folded, c_folded) / 100 * 0.95
    full = max(jw, ts, partial)
    core = 0.0
    if q_core and c_core:
        qc, cc = " ".join(q_core), " ".join(c_core)
        core = max(jellyfish.jaro_winkler_similarity(qc, cc), fuzz.token_set_ratio(qc, cc) / 100)
    return NameSim(max(full, CORE_FACTOR * core), full, core, jw, ts, partial)


def _name_level(sim: float, th: Thresholds) -> str:
    if sim >= th.name_strong:
        return "name_strong"
    if sim >= th.name_medium:
        return "name_medium"
    if sim >= th.name_weak:
        return "name_weak"
    return "name_none"


def _distinctive(entry: _Entry, ctx: _Ctx, index: InstitutionIndex, th: Thresholds) -> str | None:
    """Rarest (IDF top-1) non-generic token of the candidate, if it is rare and in the query."""
    pool = tuple(t for t in entry.core if t not in NON_DISTINCTIVE) or ()
    if not pool:
        return None
    rarest = min(pool, key=lambda t: (index.df[t], -len(t)))
    if index.df[rarest] > th.distinctive_max_df:
        return None
    if rarest in ctx.folded:
        return rarest
    if len(rarest) >= 5 and any(len(q) >= 5 and fuzz.ratio(q, rarest) >= 88 for q in ctx.folded):
        return rarest
    return None


def _prior(n: int, th: Thresholds) -> float:
    return -math.log2(max(2, min(n, th.prior_pool_cap)))


def _probability(match_weight: float) -> float:
    if match_weight > 40:
        return MAX_PROBABILITY
    p = 1.0 / (1.0 + 2.0 ** (-match_weight))
    return min(p, MAX_PROBABILITY)


def _score(ctx: _Ctx, entry: _Entry, index: InstitutionIndex, th: Thresholds) -> Candidate:
    inst = entry.inst
    sim = name_similarity(ctx.cmp_str, ctx.core, entry.cmp_str, entry.core)
    level = _name_level(sim.effective, th)
    weights: dict[str, float] = {"name": WEIGHTS[level]}
    scored: list[tuple[float, str]] = []
    features: dict[str, Any] = {
        "name_similarity": round(sim.effective, 3), "name_full": round(sim.full, 3),
        "name_core": round(sim.core, 3), "name_level": level.removeprefix("name_"),
    }

    cand_district = entry.district_norm
    q_district_norm = " ".join(normalise_name(ctx.district or "").tokens)
    if ctx.district and cand_district:
        if q_district_norm == cand_district:
            weights["district"] = WEIGHTS["district_equal"]
            features["district"] = "equal"
            scored.append((weights["district"], explain.same_district(inst.district or "")))
        else:
            weights["district"] = WEIGHTS["district_different"]
            features["district"] = "different"
            scored.append((-weights["district"] + 0.5,
                           explain.different_district(ctx.district, inst.district or "")))
    else:
        features["district"] = "missing"

    if ctx.pincode and inst.pincode:
        if ctx.pincode == inst.pincode:
            weights["pincode"] = WEIGHTS["pincode_equal"]
            features["pincode"] = "equal"
            scored.append((weights["pincode"], explain.same_pincode(ctx.pincode)))
        else:
            weights["pincode"] = WEIGHTS["pincode_different"]
            features["pincode"] = "different"
            scored.append((-weights["pincode"] + 0.5,
                           explain.different_pincode(ctx.pincode, inst.pincode)))
    else:
        features["pincode"] = "missing"

    if ctx.email_domain and inst.email_domain and ctx.email_domain == inst.email_domain.lower():
        weights["email_domain"] = WEIGHTS["email_equal"]
        features["email_domain"] = "equal"
        scored.append((weights["email_domain"], explain.same_email_domain(ctx.email_domain)))
    else:
        features["email_domain"] = "missing"

    token = _distinctive(entry, ctx, index, th)
    features["distinctive_token"] = token
    if token:
        weights["distinctive"] = WEIGHTS["distinctive_present"]
        shown = next((t for t in ctx.tokens if fold_key(t) == token), token)
        scored.append((weights["distinctive"], explain.distinctive_word(shown)))

    # name reasons
    cand_latin = {fold_key(t) for t in entry.tokens}
    for dev, latin in ctx.nn.translations:
        parts = [fold_key(p) for p in latin.split()]
        if any(p in cand_latin for p in parts) and sim.effective >= th.name_medium:
            scored.append((50.0, explain.transliteration(dev, latin)))
            break
    if level in ("name_strong", "name_medium"):
        scored.append((weights["name"], explain.name_similarity(
            sim.effective, ctx.display, entry.nn.text)))
    elif level == "name_none":
        scored.append((-weights["name"] + 0.5, explain.weak_name()))

    prior = _prior(index.n, th)
    mw = prior + sum(weights.values())
    score = _probability(mw)
    features.update({
        "weights": {k: round(v, 2) for k, v in weights.items()}, "prior": round(prior, 2),
        "match_weight": round(mw, 2),
    })
    return Candidate(
        institution_id=inst.id, institution=inst, score=round(score, 3), matched_via="fuzzy",
        features=features, reasons=explain.pick_reasons(scored),
    )


def score_candidate(query: QueryRecord, inst: InstitutionRecord, index: InstitutionIndex,
                    thresholds: Thresholds | None = None) -> Candidate:
    """Score one query against one institution (used by ``FellegiSunterScorer``)."""
    th = thresholds or Thresholds()
    return _score(_build_ctx(query, index), index.entries[inst.id], index, th)


# --------------------------------------------------------------------------------------
# Blocking
# --------------------------------------------------------------------------------------


def _block(ctx: _Ctx, index: InstitutionIndex, th: Thresholds) -> list[Id]:
    chosen: dict[Id, None] = {}
    if ctx.pincode:
        for i in index.by_pincode.get(ctx.pincode, []):
            chosen[i] = None
    if ctx.district:
        for i in index.by_district.get(ctx.district, []):
            chosen[i] = None
    if ctx.cmp_str:
        hits = process.extract(
            ctx.cmp_str, index._choice_keys, scorer=fuzz.WRatio, limit=th.block_top_names * 2,
            score_cutoff=th.block_fuzzy_cutoff,
        )
        seen_owner: dict[Id, None] = {}
        for _, _, pos in hits:
            seen_owner[index._choice_owner[pos]] = None
            if len(seen_owner) >= th.block_top_names:
                break
        for i in seen_owner:
            chosen[i] = None
    ids = list(chosen)
    if len(ids) > th.block_cap:
        # keep the best by cheap name similarity
        ids.sort(key=lambda i: -fuzz.WRatio(ctx.cmp_str, index.entries[i].cmp_str))
        ids = ids[: th.block_cap]
    return ids


# --------------------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------------------


def _exact_candidate(inst: InstitutionRecord, via: str, reasons: list[str],
                     features: dict[str, Any] | None = None) -> Candidate:
    return Candidate(inst.id, inst, 1.0, matched_via=via, features=features or {}, reasons=reasons)


def _fuzzy(ctx: _Ctx, index: InstitutionIndex, th: Thresholds) -> list[Candidate]:
    cands = [_score(ctx, index.entries[i], index, th) for i in _block(ctx, index, th)]
    cands.sort(key=lambda c: (-c.score, -c.features["match_weight"], c.institution.name))
    return cands


def _rank(cands: list[Candidate], th: Thresholds) -> list[Candidate]:
    top = cands[: th.max_candidates]
    for i, c in enumerate(top, start=1):
        c.rank = i
    return top


def resolve(
    query: QueryRecord,
    institutions: Sequence[InstitutionRecord] | InstitutionIndex,
    aliases: Sequence[AliasRecord] = (),
    thresholds: Thresholds | None = None,
) -> Resolution:
    """Resolve a complaint's institution text to a register entry.  Advisory only."""
    th = thresholds or Thresholds()
    index = institutions if isinstance(institutions, InstitutionIndex) else InstitutionIndex(
        institutions, aliases)
    ctx = _build_ctx(query, index)
    has_name = bool(ctx.nn.tokens)

    # ---- A1.1 / A1.2 exact Permanent ID ------------------------------------------------
    holder = index.by_pid.get(ctx.pid) if ctx.pid else None
    fuzzy: list[Candidate] | None = None
    if holder is not None:
        pid_reason = explain.permanent_id_found(ctx.pid or "", ctx.pid_in_text)
        if not has_name:
            cand = _exact_candidate(holder, "permanent_id_in_text" if ctx.pid_in_text
                                    else "permanent_id", [pid_reason])
            return Resolution("EXACT", cand, _rank([cand], th), ctx.nn, ctx.extracted)
        entry = index.entries[holder.id]
        sim = name_similarity(ctx.cmp_str, ctx.core, entry.cmp_str, entry.core)
        # name agreement uses the distinctive (non-generic) words when both sides have them,
        # otherwise "Devbhoomi College of Engineering" would agree with any "... Engineering"
        agreement = sim.core if (ctx.core and entry.core) else sim.effective
        if agreement >= th.id_name_floor:
            reasons = [pid_reason]
            if sim.effective >= th.name_medium:
                reasons.append(explain.name_similarity(sim.effective, ctx.display, entry.nn.text))
            cand = _exact_candidate(holder, "permanent_id_in_text" if ctx.pid_in_text
                                    else "permanent_id", reasons,
                                    {"name_similarity": round(sim.effective, 3)})
            return Resolution("EXACT", cand, _rank([cand], th), ctx.nn, ctx.extracted)
        # ID exists but the name disagrees: downgrade (A1 last paragraph)
        fuzzy = _fuzzy(ctx, index, th)
        scored = _score(ctx, entry, index, th)
        scored.matched_via = "permanent_id"
        scored.reasons = [explain.permanent_id_name_differs(), *scored.reasons][: explain.MAX_REASONS]
        others = [c for c in fuzzy if c.institution_id != holder.id]
        return Resolution("NEEDS_REVIEW", scored, _rank([scored, *others], th), ctx.nn,
                          ctx.extracted)

    # ---- A1.3 exact confirmed alias --------------------------------------------------
    if has_name:
        hits = index.alias_by_key.get(ctx.nn.key, [])
        owners = {a.institution_id for a in hits}
        if len(owners) == 1:
            alias = hits[0]
            inst = index.entries[alias.institution_id].inst
            reasons = [explain.known_alias(alias.confirmed_by, alias.confirmed_at)]
            top = _exact_candidate(inst, "alias", reasons, {"alias": alias.alias_raw or alias.alias_norm})
            fuzzy = _fuzzy(ctx, index, th)
            rest = [c for c in fuzzy if c.institution_id != inst.id]
            return Resolution("EXACT", top, _rank([top, *rest], th), ctx.nn, ctx.extracted)

    # ---- A2-A4 fuzzy -----------------------------------------------------------------
    cands = fuzzy if fuzzy is not None else _fuzzy(ctx, index, th)
    # A near-miss Permanent ID makes its institution a candidate even if blocking missed it
    near_pid: InstitutionRecord | None = None
    if ctx.pid and holder is None:
        close = [(Levenshtein.distance(ctx.pid, p), i) for p, i in index.by_pid.items()]
        close = [c for c in close if c[0] <= 1]
        if close:
            near_pid = min(close, key=lambda c: c[0])[1]
            if not any(c.institution_id == near_pid.id for c in cands):
                cands.append(_score(ctx, index.entries[near_pid.id], index, th))
                cands.sort(key=lambda c: (-c.score, -c.features["match_weight"], c.institution.name))
    cands = _rank(cands, th)

    if not cands:
        return Resolution("UNRESOLVED", None, [], ctx.nn, ctx.extracted)

    top = cands[0]
    if top.score >= th.inst_auto:
        status = "AUTO_SUGGESTED"
    elif top.score >= th.inst_review:
        status = "NEEDS_REVIEW"
    else:
        status = "UNRESOLVED"

    if status != "UNRESOLVED" and len(cands) > 1:
        second = cands[1]
        if second.score >= th.inst_review and (top.score - second.score) <= th.near_twin_gap:
            status = "NEEDS_REVIEW"
            where = top.institution.district or ctx.district
            top.reasons = [explain.two_similar(where), *top.reasons][: explain.MAX_REASONS]

    if status == "AUTO_SUGGESTED" and top.features.get("district") == "different":
        # a stated district that contradicts the register must be confirmed by an officer
        status = "NEEDS_REVIEW"

    if ctx.pid and holder is None and status != "UNRESOLVED":
        # A Permanent ID was supplied but is not in the register: never auto-suggest.
        status = "NEEDS_REVIEW"
        near_txt = near_pid.permanent_id if near_pid else None
        top.reasons = [explain.permanent_id_not_found(ctx.pid, near_txt), *top.reasons][
            : explain.MAX_REASONS]

    selected = top if status != "UNRESOLVED" else None
    return Resolution(status, selected, cands, ctx.nn, ctx.extracted)


# Names used by the other modules / package root
resolve_institution = resolve
