"""Stage B: duplicate / conflicting / related / unrelated (the CaseLink design section B and F)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from engine_fixtures import (
    ANCHOR,
    SHRINATH,
    case,
    days_ago,
    hero_new_case,
    scenario_a_cases,
    scenario_c_cases,
    scenario_d_cases,
)

from app.services.caselink import (
    CaseRecord,
    TfidfCharSimilarity,
    Thresholds,
    detect_relationships,
)
from app.services.caselink.relationship import (
    category_score,
    pending_kinds,
    score_pair,
    time_score,
)

TH = Thresholds()


def run(new: CaseRecord, others: list[CaseRecord], **kw):  # noqa: ANN201
    return {s.other_id: s for s in detect_relationships(new, others, TfidfCharSimilarity(), TH,
                                                        ANCHOR, **kw)}


# ---- Scenario A ---------------------------------------------------------------------------


def test_scenario_a_links() -> None:
    cases = scenario_a_cases()
    links = run(hero_new_case(), list(cases.values()))

    pgrc1 = links["A-PGRC-1"]
    assert pgrc1.relation == "RELATED"                      # same category, different party
    assert pgrc1.features["s_party"] == 0 and pgrc1.features["s_category"] == 1
    assert "Both about fee refund" in pgrc1.reasons

    ro1 = links["A-RO-1"]
    assert ro1.relation == "RELATED" and ro1.features["diff_bureau"] is True
    assert "Different bureaus: PGRC and RO" in ro1.reasons
    assert ro1.suggested_next_action and ro1.lead_bureau == "PGRC"

    rb1 = links["A-RB-1"]
    assert rb1.relation == "UNRELATED"
    assert rb1.suggested_next_action is None and rb1.lead_bureau is None

    assert not any(s.relation in ("DUPLICATE", "CONFLICTING") for s in links.values())


def test_scenario_a_disposed_history_lookback() -> None:
    links = run(hero_new_case(), list(scenario_a_cases().values()))
    assert "A-H-1" not in links          # ragging disposed 190 days ago: outside 90-day window
    assert "A-H-3" not in links          # CLOSED_NO_ACTION is excluded
    assert "A-H-2" not in links          # disposed 120 days ago
    recent = replace(scenario_a_cases()["A-H-2"], disposed_at=days_ago(30))
    assert "A-H-2" in run(hero_new_case(), [recent])


def test_results_sorted_by_severity_then_score() -> None:
    out = detect_relationships(hero_new_case(), list(scenario_a_cases().values()),
                               TfidfCharSimilarity(), TH, ANCHOR)
    order = {"CONFLICTING": 3, "DUPLICATE": 2, "RELATED": 1, "UNRELATED": 0}
    keys = [(-order[s.relation], -s.score) for s in out]
    assert keys == sorted(keys)
    only_alerts = detect_relationships(hero_new_case(), list(scenario_a_cases().values()),
                                       TfidfCharSimilarity(), TH, ANCHOR, include_unrelated=False)
    assert {s.relation for s in only_alerts} == {"RELATED"}


def test_other_institution_and_self_are_ignored() -> None:
    cases = scenario_a_cases()
    other_inst = replace(cases["A-PGRC-1"], id="X", institution_id="inst-other")
    new = hero_new_case()
    assert run(new, [other_inst, new]) == {}


# ---- Scenario F: duplicate across channels ---------------------------------------------------


def test_scenario_f_cpgrams_ref_quoted_in_email_is_duplicate() -> None:
    cases = scenario_a_cases()
    link = run(cases["A-EMAIL-1"], [cases["A-PGRC-2"]])["A-PGRC-2"]
    assert link.relation == "DUPLICATE"
    assert link.features["s_ref"] == 1 and link.score >= 0.95
    assert "CPGRAMS ref DHIGH/E/2026/0034517 mentioned in email" in link.reasons
    assert link.suggested_next_action == (
        "Treat A-PGRC-2 as lead; reply to complainant once, referencing both IDs.")


def test_shared_source_ref_is_duplicate() -> None:
    a = case("a", SHRINATH, "PGRC", "FEE_REFUND", received=5, source_refs=("CSS-2026-1",))
    b = case("b", SHRINATH, "RO", "OTHER", received=1, source_refs=("css-2026-1",))
    assert run(a, [b])["b"].relation == "DUPLICATE"


def test_same_party_high_overlap_is_duplicate() -> None:
    text = "College is not refunding my fee after I withdrew admission, refund pending."
    a = case("a", SHRINATH, "PGRC", "FEE_REFUND", received=10, description=text,
             party_hash="same")
    b = case("b", SHRINATH, "RO", "FEE_REFUND", received=3, description=text, party_hash="same")
    link = run(b, [a])["a"]
    assert link.relation == "DUPLICATE" and "Same complainant" in " ".join(link.reasons)


def test_never_merges_only_suggests() -> None:
    cases = scenario_a_cases()
    link = run(cases["A-EMAIL-1"], [cases["A-PGRC-2"]])["A-PGRC-2"]
    assert isinstance(link.reasons, list) and link.relation == "DUPLICATE"
    assert not hasattr(link, "merged") and cases["A-PGRC-2"].status == "UNDER_PROCESS"


# ---- Scenario C: conflicting -------------------------------------------------------------


def test_scenario_c_show_cause_vs_refund_followup_is_conflicting() -> None:
    rb, pgrc = scenario_c_cases()
    link = run(pgrc, [rb])["C-RB"]
    assert link.relation == "CONFLICTING"
    assert link.features["action_conflict"] is True
    assert any(r.startswith("RB show-cause pending while PGRC") for r in link.reasons)
    assert link.suggested_next_action == (
        "Hold issue of further letters until bureau heads agree a single communication.")
    assert link.lead_bureau == "RB"
    # symmetric
    assert run(rb, [pgrc])["C-PGRC"].relation == "CONFLICTING"


def test_rb_show_cause_vs_pgrc_fee_refund_awaiting_atr_is_conflicting() -> None:
    rb = case("rb", SHRINATH, "RB", "FEE_REFUND", received=4,
              subject="Show-cause for not refunding student fees",
              description="Show-cause notice to the institution for not refunding fees to students "
                          "who withdrew admission.",
              pending_step="SHOW_CAUSE_REPLY", pending_action="SHOW_CAUSE issued")
    pgrc = case("pgrc", SHRINATH, "PGRC", "FEE_REFUND", received=16, status="AWAITING_ATR",
                subject="Fee refund", description="The college has not refunded my fee after I "
                                                  "withdrew my admission.",
                pending_step="INSTITUTION_ATR", pending_since=days_ago(11))
    link = run(rb, [pgrc])["pgrc"]
    assert link.relation == "CONFLICTING"
    assert "RB show-cause pending while PGRC awaits the institution's ATR (11 days)" in link.reasons


def test_conflict_needs_topic_overlap() -> None:
    rb = case("rb", SHRINATH, "RB", "FAKE_APPROVAL_CLAIM", received=4,
              description="Institute advertises approval it does not have.",
              pending_step="SHOW_CAUSE_REPLY")
    pgrc = case("pgrc", SHRINATH, "PGRC", "SCHOLARSHIP", received=5,
                description="Scholarship not credited.", pending_step="REFUND_FOLLOWUP")
    assert run(rb, [pgrc])["pgrc"].relation == "UNRELATED"


def test_two_inspections_conflict() -> None:
    rb = case("rb", SHRINATH, "RB", "INFRASTRUCTURE", received=5,
              description="Laboratory and library facilities inadequate.",
              pending_step="INSPECTION")
    ro = case("ro", SHRINATH, "RO", "INFRASTRUCTURE", received=2,
              description="Laboratory and library facilities inadequate.",
              pending_action="INSPECTION scheduled 5 Nov")
    link = run(ro, [rb])["rb"]
    assert link.relation == "CONFLICTING" and "Two inspections" in link.reasons[0]


def test_deposit_release_vs_open_pgrc_matter() -> None:
    action = case("act", SHRINATH, "APPROVAL", "FEE_REFUND", received=0.1, status="RECEIVED",
                  description="Security deposit release for refund of student fees.",
                  extra_pending_kinds=("DEPOSIT_RELEASE",))
    pgrc = scenario_a_cases()["A-PGRC-1"]
    assert run(action, [pgrc])["A-PGRC-1"].relation == "CONFLICTING"


def test_closure_approval_vs_unresolved_student_dues() -> None:
    closure = case("cl", SHRINATH, "APPROVAL", "FEE_REFUND", received=1, status="RECEIVED",
                   description="Closure of institution; student fee refund dues.",
                   pending_action="CLOSURE_APPROVAL in progress")
    pgrc = scenario_a_cases()["A-PGRC-1"]
    assert run(closure, [pgrc])["A-PGRC-1"].relation == "CONFLICTING"


def test_hearings_within_seven_days_conflict() -> None:
    rb = case("rb", SHRINATH, "RB", "FACULTY_SHORTAGE", received=10,
              description="No faculty.", hearing_at=ANCHOR + timedelta(days=3))
    pgrc = case("pg", SHRINATH, "PGRC", "SERVICE_MATTER", received=10,
                description="Faculty unpaid.", hearing_at=ANCHOR + timedelta(days=5))
    assert run(rb, [pgrc])["pg"].relation == "CONFLICTING"
    far = replace(pgrc, hearing_at=ANCHOR + timedelta(days=30))
    assert run(rb, [far])["pg"].relation != "CONFLICTING"


# ---- Scenario D: negative example -------------------------------------------------------------


def test_scenario_d_scholarship_vs_lab_is_unrelated() -> None:
    pgrc, ro = scenario_d_cases()
    link = run(ro, [pgrc])["D-PGRC"]
    assert link.relation == "UNRELATED"
    assert link.features["s_category"] == 0 and link.features["days_apart"] == 8.0
    assert link.reasons[0] == "Same institution · unrelated issue"
    assert run(pgrc, [ro])["D-RO"].relation == "UNRELATED"


def test_scholarship_vs_lab_ten_days_apart() -> None:
    a = case("a", SHRINATH, "PGRC", "SCHOLARSHIP", received=14,
             description="Post matric scholarship not credited.")
    b = case("b", SHRINATH, "RO", "INFRASTRUCTURE", received=4,
             description="Computer lab has only 20 working systems.")
    assert run(b, [a])["a"].relation == "UNRELATED"


# ---- feature maths ---------------------------------------------------------------------------


def test_time_score_curve() -> None:
    assert time_score(0, TH) == 1.0 and time_score(30, TH) == 1.0
    assert time_score(105, TH) == pytest.approx(0.5)
    assert time_score(180, TH) == 0.0 and time_score(400, TH) == 0.0


def test_category_families() -> None:
    assert category_score("FEE_REFUND", "FEE_REFUND") == 1.0
    assert category_score("FEE_REFUND", "CERTIFICATE_WITHHELD") == 0.5
    assert category_score("FACULTY_SHORTAGE", "SERVICE_MATTER") == 0.5
    assert category_score("FACULTY_SHORTAGE", "INFRASTRUCTURE") == 0.5
    assert category_score("RAGGING", "SCHOLARSHIP") == 0.0
    assert category_score("RAGGING", "RAGGING") == 1.0
    assert category_score("FEE_REFUND", "SCRUTINY_COMMITTEE") == 0.0
    assert category_score("OTHER", "OTHER") == 0.5


def test_overlap_formula_and_ref_floor() -> None:
    a = scenario_a_cases()["A-PGRC-1"]
    b = scenario_a_cases()["A-RO-1"]
    sim = TfidfCharSimilarity()
    s = score_pair(a, b, sim, TH, ANCHOR)
    f = s.features
    expected = (0.45 * f["s_semantic"] + 0.25 * f["s_category"] + 0.15 * f["s_time"]
                + 0.15 * f["s_party"])
    assert s.score == pytest.approx(expected, abs=0.002)


def test_pending_kinds_parsing() -> None:
    c = case("x", SHRINATH, "RB", "OTHER", received=1, pending_step="SHOW_CAUSE_REPLY",
             pending_action="Show-cause issued 29 Oct; inspection planned")
    assert {"SHOW_CAUSE", "INSPECTION"} <= pending_kinds(c)
    assert pending_kinds(case("y", SHRINATH, "RB", "OTHER", received=1)) == set()


def test_lead_bureau_rules() -> None:
    regulatory_a = case("a", SHRINATH, "PGRC", "FACULTY_SHORTAGE", received=5,
                        description="Faculty shortage in departments.")
    regulatory_b = case("b", SHRINATH, "RB", "INFRASTRUCTURE", received=3,
                        description="Faculty shortage and lab infrastructure poor in departments.")
    ragging_a = case("r1", SHRINATH, "RB", "RAGGING", received=5,
                     description="Ragging of freshers in hostel by seniors.")
    ragging_b = case("r2", SHRINATH, "RO", "RAGGING", received=3,
                     description="Ragging of freshers in hostel by seniors.")
    assert run(regulatory_b, [regulatory_a])["a"].lead_bureau in ("RB", None)
    link = run(ragging_b, [ragging_a])["r1"]
    assert link.relation in ("RELATED", "DUPLICATE") and link.lead_bureau == "PGRC"


def test_thresholds_injectable_changes_outcome() -> None:
    cases = scenario_a_cases()
    strict = replace(TH, related=0.95)
    out = detect_relationships(hero_new_case(), [cases["A-PGRC-1"]], TfidfCharSimilarity(),
                               strict, ANCHOR)
    assert out[0].relation == "UNRELATED"
