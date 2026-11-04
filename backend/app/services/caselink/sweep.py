"""Nightly / on-demand sweep.

Re-runs stage B over every pair of live cases on each institution that has at least two.
The function is pure: it returns the actions the caller should persist and never touches
decided links.

Rules (per pair, using the latest existing link for that pair, if any):
* no link, relation != UNRELATED          -> NEW (insert a SUGGESTED link)
* link SUGGESTED/DEFERRED, relation moved -> SUPERSEDE (old link marked SUPERSEDED; a new
  SUGGESTED link is attached unless the pair is now UNRELATED)
* link CONFIRMED/REJECTED                 -> left alone, except an escalation to CONFLICTING,
  which yields ESCALATE (a new SUGGESTED version; the decided link is not modified)
* same relation                           -> unchanged
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from app.services.caselink.interfaces import TextSimilarity
from app.services.caselink.relationship import is_open, score_pair
from app.services.caselink.types import CaseRecord, Id, LinkSuggestion, Thresholds

DECIDED = frozenset({"CONFIRMED", "REJECTED"})
REVISABLE = frozenset({"SUGGESTED", "DEFERRED"})


@dataclass(frozen=True)
class ExistingLink:
    case_a_id: Id
    case_b_id: Id
    relation: str
    status: str                       # SUGGESTED | CONFIRMED | REJECTED | DEFERRED | SUPERSEDED
    id: Id | None = None
    version: int = 1


@dataclass
class SweepAction:
    kind: str                         # NEW | SUPERSEDE | ESCALATE
    case_id: Id
    other_id: Id
    suggestion: LinkSuggestion | None  # None when a SUPERSEDE leaves the pair UNRELATED
    supersedes_link_id: Id | None = None
    previous_relation: str | None = None


@dataclass
class SweepResult:
    actions: list[SweepAction] = field(default_factory=list)
    institutions_scanned: int = 0
    pairs_scanned: int = 0
    unchanged: int = 0

    @property
    def new(self) -> list[SweepAction]:
        return [a for a in self.actions if a.kind == "NEW"]

    @property
    def changed(self) -> list[SweepAction]:
        return [a for a in self.actions if a.kind != "NEW"]


def sweep(
    cases_by_institution: Mapping[Id, Sequence[CaseRecord]],
    similarity: TextSimilarity,
    thresholds: Thresholds | None = None,
    now: datetime | None = None,
    existing_links: Sequence[ExistingLink] = (),
) -> SweepResult:
    th = thresholds or Thresholds()
    result = SweepResult()

    latest: dict[frozenset[Id], ExistingLink] = {}
    for link in existing_links:
        if link.status == "SUPERSEDED":
            continue
        key = frozenset((link.case_a_id, link.case_b_id))
        prev = latest.get(key)
        if prev is None or link.version >= prev.version:
            latest[key] = link

    all_open = [c for cases in cases_by_institution.values() for c in cases if is_open(c)]
    if not getattr(similarity, "is_fitted", True):
        similarity.fit([c.similarity_text() for c in all_open])

    for inst_id, cases in cases_by_institution.items():
        live = sorted((c for c in cases if is_open(c)), key=lambda c: (c.received_at, str(c.id)))
        if len(live) < 2:
            continue
        result.institutions_scanned += 1
        for i, newer in enumerate(live):
            for older in live[:i]:
                result.pairs_scanned += 1
                s = score_pair(newer, older, similarity, th, now or newer.received_at)
                link = latest.get(frozenset((newer.id, older.id)))
                action = _decide(s, link)
                if action is None:
                    result.unchanged += 1
                else:
                    result.actions.append(action)
        _ = inst_id
    return result


def _decide(s: LinkSuggestion, link: ExistingLink | None) -> SweepAction | None:
    if link is None:
        if s.relation == "UNRELATED":
            return None
        return SweepAction("NEW", s.case_id, s.other_id, s)
    if link.relation == s.relation:
        return None
    if link.status in DECIDED:
        if s.relation == "CONFLICTING":
            return SweepAction("ESCALATE", s.case_id, s.other_id, s, None, link.relation)
        return None
    if link.status in REVISABLE:
        keep = None if s.relation == "UNRELATED" else s
        return SweepAction("SUPERSEDE", s.case_id, s.other_id, keep, link.id, link.relation)
    return None
