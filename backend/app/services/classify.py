"""Complaint category suggestion (advisory; the officer confirms the category).

``classify(subject, description) -> CategorySuggestion(category, confidence, keywords)``

1. Keyword + Hinglish dictionary classifier over every ``case_category`` value.  Input may be
   Devanagari, romanised Hindi or English: Latin keywords are matched against
   ``normalise_text`` output (so "fees wapas" is seen as "fee refund") and Devanagari keywords
   against the raw text.  Subject hits count 1.5x.
2. If there is hardly any keyword evidence, fall back to a TF-IDF nearest-centroid model trained
   at first use from the keyword lists and short template complaints (scikit-learn only).

Keyword lists come from ``seed/data/hinglish.json`` (``category_keywords``) merged with the
built-ins in ``data_loader``.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from app.services import data_loader
from app.services.data_loader import CATEGORIES
from app.services.normalise import normalise_text

SUBJECT_BOOST = 1.5
MIN_KEYWORD_EVIDENCE = 1.0
_DEV = re.compile(r"[ऀ-ॿ]")


@dataclass(frozen=True)
class CategorySuggestion:
    category: str
    confidence: float
    keywords: list[str] = field(default_factory=list)
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    method: str = "keywords"        # keywords | tfidf | none


@dataclass(frozen=True)
class _Kw:
    text: str                       # normalised keyword (Latin) or raw (Devanagari)
    weight: float
    pattern: re.Pattern[str] | None  # None for Devanagari (substring match)


@lru_cache(maxsize=1)
def _compiled() -> dict[str, tuple[_Kw, ...]]:
    out: dict[str, tuple[_Kw, ...]] = {}
    for cat, kws in data_loader.category_keywords().items():
        best: dict[str, _Kw] = {}
        for raw, weight in kws:
            if _DEV.search(raw):
                kw = unicodedata.normalize("NFKC", raw)
                cand = _Kw(kw, weight, None)
            else:
                kw = normalise_text(raw)
                if not kw:
                    continue
                pat = re.compile(rf"(?<![a-z0-9]){re.escape(kw)}(?:s|es|ed|ing|d)?(?![a-z0-9])")
                cand = _Kw(kw, weight, pat)
            old = best.get(cand.text)
            if old is None or cand.weight > old.weight:
                best[cand.text] = cand
        out[cat] = tuple(best.values())
    return out


def _count(kw: _Kw, norm: str, raw: str) -> int:
    if kw.pattern is None:
        return raw.count(kw.text)
    return len(kw.pattern.findall(norm))


def _score(norm: str, raw: str, boost: float) -> tuple[dict[str, float], dict[str, list[str]]]:
    scores: dict[str, float] = {}
    hits: dict[str, list[str]] = {}
    for cat, kws in _compiled().items():
        total = 0.0
        for kw in kws:
            n = _count(kw, norm, raw)
            if n:
                total += kw.weight * boost * (1.0 + 0.5 * math.log(n))
                hits.setdefault(cat, []).append(kw.text)
        if total:
            scores[cat] = total
    return scores, hits


@lru_cache(maxsize=1)
def _fallback_model() -> tuple[TfidfVectorizer, np.ndarray, tuple[str, ...]]:
    docs: list[str] = []
    labels: list[str] = []
    for cat in CATEGORIES:
        for tpl in data_loader.complaint_templates().get(cat, []):
            docs.append(normalise_text(tpl))
            labels.append(cat)
        kws = [k.text for k in _compiled().get(cat, ()) if k.pattern is not None]
        if kws:
            docs.append(" ".join(kws))
            labels.append(cat)
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
    matrix = vec.fit_transform(docs)
    cats = tuple(dict.fromkeys(labels))
    centroids = []
    for cat in cats:
        idx = [i for i, lab in enumerate(labels) if lab == cat]
        c = np.asarray(matrix[idx].mean(axis=0)).ravel()
        norm = np.linalg.norm(c)
        centroids.append(c / norm if norm else c)
    return vec, np.vstack(centroids), cats


def _tfidf_guess(norm: str) -> tuple[str, float, list[tuple[str, float]]]:
    vec, centroids, cats = _fallback_model()
    v = vec.transform([norm]).toarray().ravel()
    n = np.linalg.norm(v)
    if not n:
        return "OTHER", 0.0, []
    sims = centroids @ (v / n)
    order = np.argsort(-sims)
    ranked = [(cats[i], float(sims[i])) for i in order]
    return ranked[0][0], ranked[0][1], ranked[1:4]


def classify(subject: str | None, description: str | None) -> CategorySuggestion:
    """Suggest a ``case_category`` for a complaint written in Hindi, Hinglish or English."""
    subject, description = subject or "", description or ""
    raw_s = unicodedata.normalize("NFKC", subject).lower()
    raw_d = unicodedata.normalize("NFKC", description).lower()
    s_scores, s_hits = _score(normalise_text(subject), raw_s, SUBJECT_BOOST)
    d_scores, d_hits = _score(normalise_text(description), raw_d, 1.0)

    scores: dict[str, float] = {}
    hits: dict[str, list[str]] = {}
    for src_scores, src_hits in ((s_scores, s_hits), (d_scores, d_hits)):
        for cat, val in src_scores.items():
            scores[cat] = scores.get(cat, 0.0) + val
            for kw in src_hits.get(cat, []):
                if kw not in hits.setdefault(cat, []):
                    hits[cat].append(kw)

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if ranked and ranked[0][1] >= MIN_KEYWORD_EVIDENCE:
        top_cat, top = ranked[0]
        total = sum(v for _, v in ranked)
        confidence = (top / total) * (1.0 - math.exp(-top / 2.0))
        return CategorySuggestion(
            top_cat, round(min(confidence, 0.99), 2),
            sorted(hits.get(top_cat, []), key=len, reverse=True)[:8],
            [(c, round(v / total, 2)) for c, v in ranked[1:4]], "keywords",
        )

    norm = normalise_text(f"{subject} {description}")
    cat, sim, alts = _tfidf_guess(norm)
    if sim < 0.12:
        return CategorySuggestion("OTHER", 0.2, [], [], "none")
    weak = [k for c, _ in ranked[:1] for k in hits.get(c, [])]
    return CategorySuggestion(cat, round(min(sim, 0.5), 2), weak,
                              [(c, round(s, 2)) for c, s in alts], "tfidf")


@lru_cache(maxsize=8192)
def topic_signature(norm_text: str) -> str:
    """Canonical keywords of the dominant category found in already-normalised text.

    Appended to the text used for similarity so that "fees wapas nahi mili" (Hinglish) and
    "status of fee refund" (English) share vocabulary even though the surface words differ.
    """
    scores, hits = _score(norm_text, "", 1.0)
    if not scores:
        return ""
    top_cat = max(scores, key=lambda c: scores[c])
    return " ".join(sorted(hits.get(top_cat, []), key=len, reverse=True)[:6])
