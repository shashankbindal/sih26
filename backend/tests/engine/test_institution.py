"""Stage A: institution resolution (the CaseLink design section A and F)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from engine_fixtures import (
    ANCHOR,
    DEVBHOOMI,
    GEC_KANPUR,
    HERO_INSTITUTION_TEXT,
    HERO_SUBJECT,
    HERO_TEXT,
    SHRI_RAM_COE,
    SHRI_RAM_IOT,
    SHRINATH,
    register,
)

from app.services.caselink import (
    AliasRecord,
    FellegiSunterScorer,
    InstitutionIndex,
    InstitutionRecord,
    InstitutionScorer,
    QueryRecord,
    Thresholds,
    resolve_institution,
)
from app.services.normalise import normalise_name


@pytest.fixture(scope="module")
def reg() -> tuple[list[InstitutionRecord], list[AliasRecord]]:
    return register(40)


def resolve(reg, q: QueryRecord, **kw):  # noqa: ANN001, ANN201
    return resolve_institution(q, reg[0], reg[1], Thresholds(), **kw)


def test_govt_engg_collage_kanpur(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord("Govt Engg Collage Kanpur"))
    assert r.selected is not None and r.selected_id == GEC_KANPUR
    assert r.score >= 0.75
    assert r.status in ("AUTO_SUGGESTED", "NEEDS_REVIEW")
    assert any("Kanpur Nagar" in x for x in r.reasons)


def test_scenario_a_hindi_input_resolves_to_shrinath(reg) -> None:  # noqa: ANN001
    q = QueryRecord(HERO_INSTITUTION_TEXT, None, f"{HERO_SUBJECT} {HERO_TEXT}")
    r = resolve(reg, q)
    assert r.selected_id == SHRINATH
    assert r.status == "AUTO_SUGGESTED"
    assert r.score >= 0.92
    joined = " | ".join(r.reasons)
    assert "transliteration" in joined and "श्रीनाथ" in joined
    assert "Kanpur" in joined
    assert len(r.reasons) <= 5
    assert 1 <= len(r.candidates) <= 5
    assert r.candidates[0].features["distinctive_token"] == "srinath"


def test_scenario_a_hindi_name_without_text_still_clears_review_band(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord(HERO_INSTITUTION_TEXT))
    assert r.selected_id == SHRINATH and r.score >= 0.75


def test_scenario_e_near_twin_needs_review_then_alias_makes_it_exact(reg) -> None:  # noqa: ANN001
    q = QueryRecord("Shri Ram Engg College Lucknow")
    r = resolve(reg, q)
    assert r.status == "NEEDS_REVIEW"
    assert any("Two similar institutions in Lucknow" in x for x in r.reasons)
    top2 = {c.institution_id for c in r.candidates[:2]}
    assert top2 == {SHRI_RAM_COE, SHRI_RAM_IOT}
    assert r.candidates[0].score - r.candidates[1].score <= 0.03

    # officer confirms the College of Engineering -> alias saved (source CONFIRMED_MATCH)
    alias = AliasRecord(SHRI_RAM_COE, r.normalised_query.text, q.institution_text,
                        "CONFIRMED_MATCH", "Officer Singh", ANCHOR)
    again = resolve_institution(q, reg[0], [*reg[1], alias], Thresholds())
    assert again.status == "EXACT" and again.score == 1.0
    assert again.selected_id == SHRI_RAM_COE
    assert again.reasons == ["Known alias confirmed earlier by Officer Singh on 01 Nov 2026"]
    assert again.candidates[0].matched_via == "alias"


def test_near_twin_distinct_names_never_auto(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord("Shri Ram Institute of Technology Lucknow"))
    assert r.status != "AUTO_SUGGESTED" or r.selected_id == SHRI_RAM_IOT
    assert {c.institution_id for c in r.candidates[:2]} >= {SHRI_RAM_IOT}


def test_exact_permanent_id_field(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord("anything", "1-4463974255"))
    assert r.status == "EXACT" and r.score == 1.0 and r.selected_id == SHRINATH
    assert r.candidates[0].matched_via == "permanent_id"


def test_exact_permanent_id_with_spaces(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord("", " 1-44639 74255 "))
    assert r.status == "EXACT" and r.selected_id == SHRINATH


def test_permanent_id_found_in_free_text(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord("", None, "College ID 1-4463974255, they refuse refund"))
    assert r.status == "EXACT" and r.selected_id == SHRINATH
    assert r.reasons[0] == "Permanent ID 1-4463974255 found in complaint"
    assert r.candidates[0].matched_via == "permanent_id_in_text"


def test_permanent_id_present_but_name_differs_is_downgraded(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord("Devbhoomi College of Engineering Dehradun", "1-4463974255"))
    assert r.status == "NEEDS_REVIEW"
    assert r.reasons[0] == "Permanent ID matches but name differs — check for typo in ID"
    assert r.selected_id == SHRINATH
    assert DEVBHOOMI in {c.institution_id for c in r.candidates}


def test_wrong_permanent_id_digit_with_correct_name_needs_review(reg) -> None:  # noqa: ANN001
    q = QueryRecord("Shrinath Institute of Engineering and Technology Kanpur", "1-4463974256")
    r = resolve(reg, q)
    assert r.status == "NEEDS_REVIEW"
    assert r.selected_id == SHRINATH
    assert "typo" in r.reasons[0] and "1-4463974255" in r.reasons[0]


def test_unknown_permanent_id_without_near_match_still_needs_review(reg) -> None:  # noqa: ANN001
    q = QueryRecord("Shrinath Institute of Engineering and Technology Kanpur", "1-9999999999")
    r = resolve(reg, q)
    assert r.status == "NEEDS_REVIEW" and "not in the register" in r.reasons[0]


def test_confirmed_alias_from_seed_is_exact(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord("SIET Kanpur"))
    assert r.status == "EXACT" and r.selected_id == SHRINATH


def test_unresolved_when_nothing_similar(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord("Zzyzx Unknown Academy Pune"))
    assert r.status == "UNRESOLVED" and r.selected is None


def test_empty_query_unresolved(reg) -> None:  # noqa: ANN001
    assert resolve(reg, QueryRecord("")).status == "UNRESOLVED"


def test_pincode_in_text_blocks_and_boosts(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord("Shrinath college", None, "pincode 208017"))
    assert r.selected_id == SHRINATH
    assert any("Same pincode: 208017" in x for x in r.candidates[0].reasons)


def test_different_district_is_a_negative_reason(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord("Shrinath Institute of Engineering and Technology Lucknow"))
    top = next(c for c in r.candidates if c.institution_id == SHRINATH)
    assert any(x.startswith("Different district (Lucknow vs Kanpur Nagar)") for x in top.reasons)
    assert r.status != "AUTO_SUGGESTED"


def test_candidates_are_capped_and_carry_features(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord("Government college Kanpur"))
    assert len(r.candidates) <= 5
    for i, c in enumerate(r.candidates, start=1):
        assert c.rank == i and 0.0 <= c.score <= 1.0
        assert {"name_similarity", "weights", "match_weight", "district"} <= set(c.features)
    scores = [c.score for c in r.candidates]
    assert scores == sorted(scores, reverse=True)


def test_email_domain_evidence(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord("Shrinath", email_domain="siet-kanpur.example.in"))
    assert r.selected_id == SHRINATH
    assert any("email domain" in x for x in r.candidates[0].reasons)
    r2 = resolve(reg, QueryRecord("Shrinath", email_domain="gmail.com"))
    assert r2.candidates[0].features["email_domain"] == "missing"


def test_band_calibration_with_generic_name() -> None:
    """Documented calibration (institution.py docstring): name + district -> AUTO, name alone ->
    review, name + wrong district -> unresolved.  Uses a name with no distinctive word."""
    insts, aliases = register(40)
    insts = [*insts, InstitutionRecord("inst-generic", "Technical Institute of Sciences",
                                       "1-4499000001", name_norm="technical institute of sciences",
                                       district="Nagpur", state="Maharashtra", pincode="440009")]
    index = InstitutionIndex(insts, aliases)
    th = Thresholds()
    both = resolve_institution(QueryRecord("Technical Institute of Sciences Nagpur"), index, (), th)
    assert both.status == "AUTO_SUGGESTED" and both.selected_id == "inst-generic"
    name_only = resolve_institution(QueryRecord("Technical Institute of Sciences"), index, (), th)
    assert name_only.status == "NEEDS_REVIEW" and 0.75 <= name_only.score < 0.92
    wrong = resolve_institution(QueryRecord("Technical Institute of Sciences Pune"), index, (), th)
    assert wrong.status == "UNRESOLVED"


def test_thresholds_are_injectable(reg) -> None:  # noqa: ANN001
    strict = replace(Thresholds(), inst_auto=0.9999, inst_review=0.9999)
    q = QueryRecord(HERO_INSTITUTION_TEXT)
    r = resolve_institution(q, reg[0], reg[1], strict)
    assert r.status == "UNRESOLVED"
    assert Thresholds.from_policy({"inst_auto": 0.8, "unknown": 1}).inst_auto == 0.8


def test_scorer_protocol_wrapper(reg) -> None:  # noqa: ANN001
    index = InstitutionIndex(*reg)
    scorer = FellegiSunterScorer(index, Thresholds())
    assert isinstance(scorer, InstitutionScorer)
    shrinath = next(i for i in reg[0] if i.id == SHRINATH)
    res = scorer.score(QueryRecord(HERO_INSTITUTION_TEXT), shrinath)
    assert res.score >= 0.92 and res.reasons


def test_normalised_query_is_returned(reg) -> None:  # noqa: ANN001
    r = resolve(reg, QueryRecord(HERO_INSTITUTION_TEXT))
    assert r.normalised_query == normalise_name(HERO_INSTITUTION_TEXT)
    assert r.extracted["district"] == "Kanpur Nagar"
