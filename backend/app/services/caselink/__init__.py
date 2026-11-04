"""CaseLink engine: institution resolution (stage A) and relationship detection (stage B).

Pure Python over in-memory dataclasses; never touches the database.  Advisory only: nothing here
merges, blocks or cancels anything.  Callers persist the results and write Passport entries.

Import everything from here::

    from app.services.caselink import (
        resolve_institution, detect_relationships, sweep_relationships, classify_case,
        QueryRecord, InstitutionRecord, AliasRecord, CaseRecord, Thresholds,
        TfidfCharSimilarity,
    )

Public API
----------
Stage A
    ``resolve_institution(query: QueryRecord, institutions: Sequence[InstitutionRecord] |
    InstitutionIndex, aliases: Sequence[AliasRecord] = (), thresholds: Thresholds | None = None)
    -> Resolution``
    Pass an ``InstitutionIndex(institutions, aliases)`` instead of a list to reuse the
    pre-computed lookups across requests.

    ``QueryRecord(institution_text, permanent_id_raw=None, text="", pincode=None, district=None,
    email_domain=None)``  ``text`` is subject + description (mined for ID / pincode / district).

    ``InstitutionRecord(id, name, permanent_id=None, name_norm=None, district=None, state=None,
    pincode=None, email_domain=None, inst_type=None, ro_code=None)``

    ``AliasRecord(institution_id, alias_norm, alias_raw="", source="SEED", confirmed_by=None,
    confirmed_at=None)``

    ``Resolution(status, selected, candidates, normalised_query, extracted)``
        ``status``      EXACT | AUTO_SUGGESTED | NEEDS_REVIEW | UNRESOLVED
        ``selected``    Candidate | None  (None when UNRESOLVED; pre-select it in the UI only
                        for EXACT / AUTO_SUGGESTED)
        ``candidates``  up to 5 Candidate, best first
        ``.score`` / ``.reasons`` / ``.selected_id`` are shortcuts for the selected candidate.
    ``Candidate(institution_id, institution, score, rank, matched_via, features, reasons)``
        ``score`` 0..1 (3 decimals), ``matched_via`` permanent_id | permanent_id_in_text |
        alias | fuzzy; ``reasons`` at most 5 plain-English strings.

Stage B
    ``detect_relationships(new: CaseRecord, others: Sequence[CaseRecord], similarity:
    TextSimilarity, thresholds: Thresholds | None = None, now: datetime | None = None, *,
    include_unrelated: bool = True) -> list[LinkSuggestion]``
    ``others`` is filtered to the same institution, excluding closed cases (disposed ones are
    kept for 90 days).  Persist only ``relation != "UNRELATED"``.

    ``CaseRecord(id, institution_id, owner_bureau, category, status, received_at,
    pending_step="NONE", pending_action=None, party_hash=None, source_refs=(), subject="",
    description="", description_norm="", display_id=None, source_channel=None,
    hearing_at=None, disposed_at=None, pending_since=None, extra_pending_kinds=(),
    institution_permanent_id=None)``

    ``LinkSuggestion(case_id, other_id, relation, score, features, reasons,
    suggested_next_action, lead_bureau)``  relation in DUPLICATE | CONFLICTING | RELATED |
    UNRELATED; ``features`` holds s_ref, s_party, s_semantic, s_category, s_time, diff_bureau,
    action_conflict, overlap, days_apart.

Sweep
    ``sweep_relationships(cases_by_institution: Mapping[Id, Sequence[CaseRecord]], similarity,
    thresholds=None, now=None, existing_links: Sequence[ExistingLink] = ()) -> SweepResult``
    ``SweepResult.actions`` is a list of ``SweepAction(kind NEW | SUPERSEDE | ESCALATE,
    case_id, other_id, suggestion, supersedes_link_id, previous_relation)``.  The caller
    inserts / supersedes links; CONFIRMED and REJECTED decisions are never modified.

Text similarity
    ``TfidfCharSimilarity(corpus=None)`` with ``fit(corpus)`` / ``refit(corpus)`` /
    ``similarity(a, b)`` / ``is_fitted``.  Keep one instance per process; refit after imports.
    Build ``CaseRecord.description_norm`` with ``normalise.normalise_text``.

Thresholds
    ``Thresholds()`` defaults match the CaseLink design; ``Thresholds.from_policy(dict)``
    reads ``policy_config.thresholds`` (unknown keys ignored).

Related modules (outside this package)
    ``app.services.normalise``: normalise_name, normalise_text, mask_pii, detect_language,
    extract_pincode, extract_permanent_id, extract_district.
    ``app.services.classify``: classify(subject, description) -> CategorySuggestion.
"""

from app.services.caselink.institution import (
    InstitutionIndex,
    resolve,
    resolve_institution,
    score_candidate,
)
from app.services.caselink.interfaces import (
    FellegiSunterScorer,
    InstitutionScorer,
    SanscriptTransliterator,
    ScoreResult,
    TextSimilarity,
    TfidfCharSimilarity,
    Transliterator,
)
from app.services.caselink.relationship import detect, detect_relationships, score_pair
from app.services.caselink.sweep import ExistingLink, SweepAction, SweepResult, sweep
from app.services.caselink.types import (
    AliasRecord,
    Candidate,
    CaseRecord,
    InstitutionRecord,
    LinkSuggestion,
    QueryRecord,
    Resolution,
    Thresholds,
)

sweep_relationships = sweep


def classify_case(subject: str, description: str):  # noqa: ANN201 - re-export convenience
    from app.services.classify import classify

    return classify(subject, description)


__all__ = [
    "AliasRecord", "CaseRecord", "Candidate", "ExistingLink", "FellegiSunterScorer",
    "InstitutionIndex", "InstitutionRecord", "InstitutionScorer", "LinkSuggestion",
    "QueryRecord", "Resolution", "SanscriptTransliterator", "ScoreResult", "SweepAction",
    "SweepResult", "TextSimilarity", "TfidfCharSimilarity", "Thresholds", "Transliterator",
    "classify_case", "detect", "detect_relationships", "resolve", "resolve_institution",
    "score_candidate", "score_pair", "sweep", "sweep_relationships",
]
