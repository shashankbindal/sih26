"""Sweep (section C), similarity implementations and performance."""

from __future__ import annotations

import time
from dataclasses import replace

import pytest
from engine_fixtures import (
    ANCHOR,
    HERO_INSTITUTION_TEXT,
    SHRINATH,
    case,
    filler_institutions,
    register,
    scenario_a_cases,
    scenario_c_cases,
)

from app.services.caselink import (
    ExistingLink,
    InstitutionIndex,
    QueryRecord,
    SanscriptTransliterator,
    TextSimilarity,
    TfidfCharSimilarity,
    Thresholds,
    Transliterator,
    resolve_institution,
    sweep_relationships,
)


def test_sweep_finds_new_links_and_skips_unrelated() -> None:
    rb, pgrc = scenario_c_cases()
    a = scenario_a_cases()
    result = sweep_relationships(
        {"inst-devbhoomi": [rb, pgrc], SHRINATH: list(a.values())}, TfidfCharSimilarity(),
        Thresholds(), ANCHOR)
    kinds = {(x.case_id, x.other_id): x.suggestion.relation for x in result.new if x.suggestion}
    assert kinds[("C-PGRC", "C-RB")] == "CONFLICTING"
    assert kinds[("A-EMAIL-1", "A-PGRC-2")] == "DUPLICATE"
    assert all(x.suggestion.relation != "UNRELATED" for x in result.new if x.suggestion)
    assert result.institutions_scanned == 2 and result.pairs_scanned > 2


def test_sweep_never_touches_decided_links_but_escalates_to_conflicting() -> None:
    rb, pgrc = scenario_c_cases()
    sim = TfidfCharSimilarity()
    base = {"d": [rb, pgrc]}
    confirmed_same = ExistingLink("C-PGRC", "C-RB", "CONFLICTING", "CONFIRMED", id="l1")
    assert sweep_relationships(base, sim, now=ANCHOR, existing_links=[confirmed_same]).actions == []

    confirmed_related = ExistingLink("C-RB", "C-PGRC", "RELATED", "REJECTED", id="l2")
    res = sweep_relationships(base, sim, now=ANCHOR, existing_links=[confirmed_related])
    assert [a.kind for a in res.actions] == ["ESCALATE"]
    assert res.actions[0].supersedes_link_id is None   # decided link is left as it is


def test_sweep_supersedes_changed_suggestions_only() -> None:
    rb, pgrc = scenario_c_cases()
    sim = TfidfCharSimilarity()
    old = ExistingLink("C-PGRC", "C-RB", "RELATED", "SUGGESTED", id="l3")
    res = sweep_relationships({"d": [rb, pgrc]}, sim, now=ANCHOR, existing_links=[old])
    assert [a.kind for a in res.actions] == ["SUPERSEDE"]
    assert res.actions[0].supersedes_link_id == "l3"
    assert res.actions[0].suggestion.relation == "CONFLICTING"

    stale = ExistingLink("C-PGRC", "C-RB", "DUPLICATE", "SUGGESTED", id="l4")
    unrelated_now = replace(pgrc, pending_step="NONE", pending_action=None, hearing_at=None,
                            category="SCHOLARSHIP", description_norm="scholarship not credited",
                            subject="scholarship")
    res2 = sweep_relationships({"d": [rb, unrelated_now]}, sim, now=ANCHOR,
                               existing_links=[stale])
    assert res2.actions[0].kind == "SUPERSEDE" and res2.actions[0].suggestion is None

    same = ExistingLink("C-PGRC", "C-RB", "CONFLICTING", "SUGGESTED", id="l5")
    res3 = sweep_relationships({"d": [rb, pgrc]}, sim, now=ANCHOR, existing_links=[same])
    assert res3.actions == [] and res3.unchanged == 1


def test_sweep_ignores_closed_cases_and_single_case_institutions() -> None:
    rb, pgrc = scenario_c_cases()
    closed = replace(pgrc, status="DISPOSED", disposed_at=ANCHOR)
    res = sweep_relationships({"d": [rb, closed], "e": [rb]}, TfidfCharSimilarity(), now=ANCHOR)
    assert res.actions == [] and res.institutions_scanned == 0


def test_tfidf_similarity_basics() -> None:
    sim = TfidfCharSimilarity()
    assert not sim.is_fitted
    assert sim.similarity("fee refund pending", "fee refund pending") == pytest.approx(1.0)
    assert sim.similarity("", "x") == 0.0
    sim.fit(["fee refund pending", "lab has no computers", "faculty salary unpaid"])
    assert sim.is_fitted
    assert sim.similarity("fee refund pending", "fee refund not paid") > sim.similarity(
        "fee refund pending", "lab has no computers")
    sim.refit(["something else entirely", "fee refund"])
    assert 0.0 <= sim.similarity("fee refund", "refund fee") <= 1.0


def test_protocol_conformance() -> None:
    assert isinstance(TfidfCharSimilarity(), TextSimilarity)
    assert isinstance(SanscriptTransliterator(), Transliterator)
    assert SanscriptTransliterator().to_latin("कानपुर Kanpur") == "kanpur kanpur"


def test_detect_fits_unfitted_similarity_lazily() -> None:
    from app.services.caselink import detect_relationships

    sim = TfidfCharSimilarity()
    a = scenario_a_cases()
    detect_relationships(a["A-EMAIL-1"], [a["A-PGRC-2"]], sim, now=ANCHOR)
    assert sim.is_fitted


def test_resolve_under_300ms_against_200_institutions() -> None:
    insts, aliases = register(194)          # 6 scripted + 194 fillers = 200
    assert len(insts) == 200
    assert len(filler_institutions(194)) == 194
    queries = [
        QueryRecord(HERO_INSTITUTION_TEXT, None, "फीस वापस"),
        QueryRecord("Govt Engg Collage Kanpur"),
        QueryRecord("Shri Ram Engg College Lucknow"),
        QueryRecord("Gyanodaya Inst of Tech & Mgmt Bhopal 462001"),
        QueryRecord("Unknown Academy of Arts Pune"),
    ]
    worst = 0.0
    for q in queries:                        # includes index build and cold normalisation caches
        t = time.perf_counter()
        resolve_institution(q, insts, aliases, Thresholds())
        worst = max(worst, time.perf_counter() - t)
    assert worst < 0.3, f"slowest resolve took {worst * 1000:.0f} ms"

    index = InstitutionIndex(insts, aliases)
    t = time.perf_counter()
    for _ in range(20):
        resolve_institution(queries[0], index, (), Thresholds())
    assert (time.perf_counter() - t) / 20 < 0.05


def test_detect_scales_to_many_cases() -> None:
    from app.services.caselink import detect_relationships

    others = [case(f"c{i}", SHRINATH, "PGRC", "FEE_REFUND", received=i % 60,
                   description=f"fee refund pending case number {i} college not refunding")
              for i in range(150)]
    new = scenario_a_cases()["A-PGRC-1"]
    t = time.perf_counter()
    out = detect_relationships(new, others, TfidfCharSimilarity(), now=ANCHOR)
    assert len(out) == 150 and time.perf_counter() - t < 2.0
