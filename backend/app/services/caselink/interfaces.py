"""Protocols (production swap points) and their prototype implementations.

Prototype            -> Production
SanscriptTransliterator -> IndicXlitTransliterator
TfidfCharSimilarity     -> LabseSimilarity (pgvector)
FellegiSunterScorer     -> SplinkScorer
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from app.services.normalise import transliterate_word

if TYPE_CHECKING:  # pragma: no cover
    from app.services.caselink.types import InstitutionRecord, QueryRecord


@dataclass
class ScoreResult:
    score: float
    features: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


@runtime_checkable
class Transliterator(Protocol):
    def to_latin(self, text: str) -> str: ...


@runtime_checkable
class TextSimilarity(Protocol):
    def fit(self, corpus: list[str]) -> None: ...

    def similarity(self, a: str, b: str) -> float: ...


@runtime_checkable
class InstitutionScorer(Protocol):
    def score(self, query: QueryRecord, candidate: InstitutionRecord) -> ScoreResult: ...


class SanscriptTransliterator:
    """Devanagari -> Latin via indic_transliteration (ITRANS) with Hindi schwa deletion."""

    def to_latin(self, text: str) -> str:
        from app.services.normalise import _DEV_RE, _words  # local: avoid widening the public API

        out = []
        for word in _words(text):
            out.append(transliterate_word(word) if _DEV_RE.search(word) else word.lower())
        return " ".join(out)


class TfidfCharSimilarity:
    """Cosine similarity of char_wb 3-5 gram TF-IDF vectors (sublinear tf).

    Fit lazily: ``detect()`` fits on the texts it is given when ``is_fitted`` is False;
    ``refit(corpus)`` replaces the model (after imports, nightly sweep).  If ``similarity`` is
    called before any fit, the pair itself is used as a throw-away corpus.
    """

    def __init__(self, corpus: Sequence[str] | None = None) -> None:
        self._vec: TfidfVectorizer | None = None
        self._cache: dict[str, Any] = {}
        if corpus:
            self.fit(list(corpus))

    @property
    def is_fitted(self) -> bool:
        return self._vec is not None

    @staticmethod
    def _new_vectorizer() -> TfidfVectorizer:
        return TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True,
                               lowercase=True, dtype=np.float64)

    def fit(self, corpus: list[str]) -> None:
        docs = [c for c in corpus if c and c.strip()] or ["placeholder"]
        vec = self._new_vectorizer()
        vec.fit(docs)
        self._vec = vec
        self._cache = {}

    refit = fit

    def _vector(self, vec: TfidfVectorizer, text: str, cache: dict[str, Any] | None) -> Any:
        if cache is not None and text in cache:
            return cache[text]
        v = vec.transform([text])
        if cache is not None:
            if len(cache) > 20000:
                cache.clear()
            cache[text] = v
        return v

    def similarity(self, a: str, b: str) -> float:
        if not a.strip() or not b.strip():
            return 0.0
        if self._vec is None:
            vec = self._new_vectorizer()
            vec.fit([a, b])
            cache: dict[str, Any] | None = None
        else:
            vec, cache = self._vec, self._cache
        va, vb = self._vector(vec, a, cache), self._vector(vec, b, cache)
        return float(va.multiply(vb).sum())  # rows are L2-normalised


class FellegiSunterScorer:
    """Wrapper object exposing the stage A scorer behind the ``InstitutionScorer`` protocol.

    The scoring maths lives in ``institution.py`` (it needs the corpus-level index for the
    prior and token rarity), so this class binds an index and delegates.
    """

    def __init__(self, index: Any, thresholds: Any | None = None) -> None:
        self._index = index
        self._thresholds = thresholds

    def score(self, query: QueryRecord, candidate: InstitutionRecord) -> ScoreResult:
        from app.services.caselink.institution import score_candidate

        cand = score_candidate(query, candidate, self._index, self._thresholds)
        return ScoreResult(cand.score, cand.features, cand.reasons)
