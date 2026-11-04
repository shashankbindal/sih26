"""Loads the Hindi / Hinglish / abbreviation maps used by the CaseLink engine.

Files live in ``backend/app/seed/data/`` (``hi_map.json``, ``hinglish.json``,
``abbreviations.json``) and are shipped with the seed data.  Every entry the spec lists
inline is also built in below, so a missing or malformed file never blocks the engine; when a
file is present its entries override the built-ins.

The loader is deliberately tolerant about JSON shape.  A map may be flat
(``{"engg": "engineering"}``), sectioned (``{"cities": {...}, "words": {...}}``) or
canonical-to-variants (``{"engineering": ["engg", "engr"]}``).  Keys starting with ``_`` and
the usual metadata keys are ignored.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "seed" / "data"

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"))
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_META_KEYS = {"meta", "comment", "comments", "description", "version", "source", "notes", "note"}

CATEGORIES: tuple[str, ...] = (
    "FEE_REFUND",
    "CERTIFICATE_WITHHELD",
    "FACULTY_SHORTAGE",
    "INFRASTRUCTURE",
    "RAGGING",
    "FAKE_APPROVAL_CLAIM",
    "SCHOLARSHIP",
    "ADMISSION",
    "SERVICE_MATTER",
    "SCRUTINY_COMMITTEE",
    "OTHER",
)


def clean_key(s: str) -> str:
    """NFKC + zero-width strip + trim; used for every map key and lookup."""
    return unicodedata.normalize("NFKC", s or "").translate(_ZERO_WIDTH).strip()


# --------------------------------------------------------------------------------------
# Built-in defaults (everything the spec lists inline, plus a few safe extras)
# --------------------------------------------------------------------------------------

_BUILTIN_HI_MAP: dict[str, str] = {
    "इंजीनियरिंग": "engineering",
    "इंजिनियरिंग": "engineering",
    "इंजीनीयरिंग": "engineering",
    "अभियांत्रिकी": "engineering",
    "कॉलेज": "college",
    "कालेज": "college",
    "महाविद्यालय": "college",
    "संस्थान": "institute",
    "इंस्टीट्यूट": "institute",
    "प्रौद्योगिकी": "technology",
    "टेक्नोलॉजी": "technology",
    "विश्वविद्यालय": "university",
    "प्रबंधन": "management",
    "प्रबन्धन": "management",
    "फार्मेसी": "pharmacy",
    "पॉलिटेक्निक": "polytechnic",
    "पोलिटेक्निक": "polytechnic",
    "सरकारी": "government",
    "राजकीय": "government",
    "श्री": "shri",
    "एवं": "and",
    "और": "and",
    "कानपुर": "kanpur",
    "लखनऊ": "lucknow",
    "भोपाल": "bhopal",
    "इंदौर": "indore",
    "जयपुर": "jaipur",
    "पटना": "patna",
    "नागपुर": "nagpur",
    "पुणे": "pune",
    "देहरादून": "dehradun",
    "दिल्ली": "delhi",
    "मुंबई": "mumbai",
    "वाराणसी": "varanasi",
    "आगरा": "agra",
    "प्रयागराज": "prayagraj",
    "इलाहाबाद": "allahabad",
    "गोरखपुर": "gorakhpur",
    "मेरठ": "meerut",
    "रांची": "ranchi",
    "चंडीगढ़": "chandigarh",
    "ग्वालियर": "gwalior",
    "जबलपुर": "jabalpur",
    "उदयपुर": "udaipur",
    "जोधपुर": "jodhpur",
    "रायपुर": "raipur",
}

_BUILTIN_ABBREVIATIONS: dict[str, str] = {
    "engg": "engineering",
    "engr": "engineering",
    "eng": "engineering",
    "govt": "government",
    "gov": "government",
    "inst": "institute",
    "instt": "institute",
    "tech": "technology",
    "coll": "college",
    "clg": "college",
    "collage": "college",
    "univ": "university",
    "mgmt": "management",
    "pharm": "pharmacy",
    "poly": "polytechnic",
    "coe": "college of engineering",
    "iet": "institute of engineering and technology",
    "sr": "shri",
    "shree": "shri",
    "sri": "shri",
}

_BUILTIN_LEXICON: dict[str, str] = {
    "fees": "fee",
    "fess": "fee",
    "fis": "fee",
    "wapas": "refund",
    "vapas": "refund",
    "vaapas": "refund",
    "wapis": "refund",
    "vapis": "refund",
    "refund nahi": "refund",
    "refund nahin": "refund",
    "refund nhi": "refund",
    "refunded": "refund",
    "refunds": "refund",
    "rifund": "refund",
    "certificates": "certificate",
    "sartifikat": "certificate",
    "marksheet": "certificate",
    "marksheets": "certificate",
    "tc": "certificate",
    "ragging": "ragging",
    "raging": "ragging",
    "faculty": "faculty",
    "faculties": "faculty",
    "teacher": "faculty",
    "teachers": "faculty",
    "professor": "faculty",
    "professors": "faculty",
    "shikshak": "faculty",
    "adhyapak": "faculty",
    "labs": "lab",
    "prayogshala": "lab",
    "scholarships": "scholarship",
    "chhatravritti": "scholarship",
    "chatravritti": "scholarship",
    "salary": "salary",
    "salaries": "salary",
    "vetan": "salary",
    "wetan": "salary",
    "tankhwah": "salary",
    "tankhwa": "salary",
    "tankha": "salary",
    "admissions": "admission",
    "pravesh": "admission",
    # Devanagari words commonly seen in complaints (matched on the raw token)
    "फीस": "fee",
    "फ़ीस": "fee",
    "शुल्क": "fee",
    "वापस": "refund",
    "रिफंड": "refund",
    "प्रमाणपत्र": "certificate",
    "प्रमाण": "certificate",
    "सर्टिफिकेट": "certificate",
    "अंकपत्र": "certificate",
    "मार्कशीट": "certificate",
    "रैगिंग": "ragging",
    "शिक्षक": "faculty",
    "अध्यापक": "faculty",
    "प्राध्यापक": "faculty",
    "फैकल्टी": "faculty",
    "प्रयोगशाला": "lab",
    "लैब": "lab",
    "छात्रवृत्ति": "scholarship",
    "स्कॉलरशिप": "scholarship",
    "वेतन": "salary",
    "तनख्वाह": "salary",
    "सैलरी": "salary",
    "प्रवेश": "admission",
    "दाखिला": "admission",
    "एडमिशन": "admission",
}

# Category keyword lists.  Latin entries match the *normalised* text (Hinglish already folded
# to canonical words, e.g. "fees wapas" -> "fee refund"); Devanagari entries match the raw text.
# Value is (keyword, weight).
_BUILTIN_CATEGORY_KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "FEE_REFUND": [
        ("refund", 2.0), ("fee refund", 2.0), ("fee", 1.0), ("tuition fee", 1.0),
        ("fee return", 2.0), ("money back", 2.0), ("withdraw", 0.8), ("withdrawn", 0.8),
        ("cancel admission", 1.0), ("admission cancelled", 1.0), ("caution money", 1.5),
        ("security deposit", 1.0), ("amount not returned", 2.0), ("fee not returned", 2.0),
        ("फीस", 1.5), ("शुल्क", 1.5), ("वापस", 1.5), ("रिफंड", 2.0), ("पैसे वापस", 2.0),
    ],
    "CERTIFICATE_WITHHELD": [
        ("certificate", 1.5), ("original documents", 2.0), ("original certificate", 2.0),
        ("documents withheld", 2.0), ("not giving certificate", 2.0), ("degree", 1.0),
        ("migration", 1.0), ("transfer certificate", 2.0), ("character certificate", 1.5),
        ("withholding", 1.0), ("withheld", 1.0), ("mark card", 1.0), ("provisional", 0.5),
        ("प्रमाणपत्र", 1.5), ("सर्टिफिकेट", 1.5), ("अंकपत्र", 1.5), ("मार्कशीट", 1.5),
        ("डिग्री", 1.0), ("मूल दस्तावेज", 2.0),
    ],
    "FACULTY_SHORTAGE": [
        ("faculty shortage", 3.0), ("shortage of faculty", 3.0), ("no faculty", 2.5),
        ("faculty not available", 2.5), ("insufficient faculty", 3.0), ("faculty vacancy", 2.5),
        ("vacant posts", 1.5), ("faculty", 1.0), ("shortage", 1.5), ("student teacher ratio", 2.0),
        ("pupil teacher ratio", 2.0), ("teachers absent", 1.5), ("no teachers", 2.5),
        ("classes not held", 1.5), ("classes not conducted", 1.5), ("guest faculty", 1.0),
        ("शिक्षकों की कमी", 3.0), ("फैकल्टी की कमी", 3.0), ("शिक्षक नहीं", 2.0),
        ("कमी", 0.8),
    ],
    "INFRASTRUCTURE": [
        ("infrastructure", 2.5), ("lab", 1.5), ("laboratory", 1.5), ("computers", 1.0),
        ("working systems", 2.0), ("library", 1.2), ("hostel", 1.2), ("building", 1.0),
        ("classroom", 1.2), ("classrooms", 1.2), ("equipment", 1.2), ("playground", 1.0),
        ("toilets", 1.0), ("drinking water", 1.2), ("workshop", 1.0), ("internet", 0.8),
        ("campus", 0.8), ("not working", 0.8), ("facilities", 1.2),
        ("प्रयोगशाला", 1.5), ("लैब", 1.5), ("भवन", 1.2), ("पुस्तकालय", 1.2), ("छात्रावास", 1.2),
        ("कक्षा", 0.8), ("सुविधा", 1.0),
    ],
    "RAGGING": [
        ("ragging", 3.0), ("harassment by seniors", 3.0), ("seniors harass", 3.0),
        ("bullying", 2.0), ("hazing", 3.0), ("anti ragging", 3.0), ("seniors beat", 2.5),
        ("रैगिंग", 3.0), ("सीनियर", 1.0),
    ],
    "FAKE_APPROVAL_CLAIM": [
        ("fake approval", 3.0), ("not approved by aicte", 3.0), ("without approval", 2.5),
        ("fake affiliation", 3.0), ("claims aicte approval", 3.0), ("no aicte approval", 3.0),
        ("approval not valid", 2.5), ("fraud", 1.5), ("fake", 1.2), ("fraudulent", 1.5),
        ("unrecognised", 1.5), ("unrecognized", 1.5), ("approval", 0.8), ("misleading", 1.2),
        ("फर्जी", 2.0), ("नकली मान्यता", 3.0), ("बिना मान्यता", 3.0), ("मान्यता", 1.0),
    ],
    "SCHOLARSHIP": [
        ("scholarship", 3.0), ("post matric", 2.0), ("stipend", 2.0), ("not credited", 1.0),
        ("fee waiver", 1.5), ("tfw", 1.5), ("pragati", 2.0), ("saksham", 2.0),
        ("छात्रवृत्ति", 3.0), ("स्कॉलरशिप", 3.0), ("वजीफा", 2.0),
    ],
    "ADMISSION": [
        ("admission", 1.5), ("counselling", 1.5), ("seat", 1.0), ("seat allotment", 2.0),
        ("management quota", 1.5), ("capitation", 2.0), ("donation", 1.2), ("denied admission", 2.5),
        ("admission denied", 2.5), ("lateral entry", 1.5), ("merit list", 1.5),
        ("प्रवेश", 1.5), ("दाखिला", 1.5), ("काउंसलिंग", 1.5),
    ],
    "SERVICE_MATTER": [
        ("salary", 2.5), ("unpaid salary", 3.0), ("salary not paid", 3.0), ("termination", 2.5),
        ("terminated", 2.5), ("appointment letter", 2.0), ("promotion", 1.5), ("provident fund", 2.0),
        ("pf", 1.0), ("gratuity", 2.0), ("pay scale", 2.0), ("seventh pay", 2.0),
        ("resigned", 1.0), ("relieving letter", 2.0), ("dues of staff", 2.0), ("service book", 2.0),
        ("वेतन", 2.5), ("तनख्वाह", 2.5), ("सैलरी", 2.5), ("बर्खास्त", 2.5), ("नियुक्ति", 1.5),
    ],
    "SCRUTINY_COMMITTEE": [
        ("scrutiny committee", 3.5), ("scrutiny", 2.5), ("committee review", 2.0),
        ("expert committee", 2.0), ("committee", 1.0), ("faculty norms", 1.5),
        ("compliance review", 1.5), ("deficiency report", 2.0), ("norms", 0.8),
        ("जांच समिति", 3.0), ("जाँच समिति", 3.0), ("समिति", 1.0),
    ],
}

# Short complaint-like templates per category for the TF-IDF fallback classifier.
CATEGORY_TEMPLATES: dict[str, list[str]] = {
    "FEE_REFUND": [
        "college is not refunding my fee after i withdrew admission",
        "fees abhi tak wapas nahi mili refund pending",
        "tuition fee and caution money not returned",
    ],
    "CERTIFICATE_WITHHELD": [
        "college is withholding my original certificates and marksheet",
        "transfer certificate not being issued unless dues are paid",
        "degree and documents retained by the institute",
    ],
    "FACULTY_SHORTAGE": [
        "there are not enough teachers and classes are not conducted",
        "faculty shortage in the department no permanent faculty",
        "student teacher ratio is very poor vacant faculty posts",
    ],
    "INFRASTRUCTURE": [
        "computer lab has too few working systems",
        "library hostel and classroom facilities are inadequate",
        "laboratory equipment is missing and building is unsafe",
    ],
    "RAGGING": [
        "senior students are ragging and harassing freshers",
        "ragging incident in hostel complaint to anti ragging cell",
    ],
    "FAKE_APPROVAL_CLAIM": [
        "institute claims aicte approval which it does not have",
        "fake affiliation and misleading advertisement about approval",
    ],
    "SCHOLARSHIP": [
        "post matric scholarship amount not credited to my account",
        "scholarship and stipend pending for two years",
    ],
    "ADMISSION": [
        "i was denied admission despite my rank in the merit list",
        "college demanded capitation donation for seat in management quota",
    ],
    "SERVICE_MATTER": [
        "faculty salary has not been paid for several months",
        "teacher terminated without notice and provident fund dues pending",
    ],
    "SCRUTINY_COMMITTEE": [
        "scrutiny committee review of faculty norms compliance",
        "expert committee to examine deficiency report of the institute",
    ],
    "OTHER": [
        "general query about the institute",
        "request for information and status",
    ],
}


# --------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------


def _read_json(name: str) -> Any:
    path = DATA_DIR / name
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _flatten(obj: Any, skip: frozenset[str] = frozenset()) -> dict[str, str]:
    """Flatten sectioned / canonical-to-variants JSON into ``{variant: canonical}``."""
    out: dict[str, str] = {}
    if not isinstance(obj, Mapping):
        return out
    for k, v in obj.items():
        if not isinstance(k, str) or k.startswith("_") or k in _META_KEYS or k in skip:
            continue
        if isinstance(v, str):
            if _DEVANAGARI.search(v) and not _DEVANAGARI.search(k):
                out[clean_key(v)] = clean_key(k).lower()  # reversed orientation
            else:
                out[clean_key(k)] = clean_key(v)
        elif isinstance(v, Mapping):
            out.update(_flatten(v, skip))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    out[clean_key(item)] = clean_key(k)
    return out


def _merge(base: dict[str, str], extra: Mapping[str, str], *, lower: bool) -> dict[str, str]:
    merged = {clean_key(k): clean_key(v) for k, v in base.items()}
    for k, v in extra.items():
        if k and v:
            merged[k.lower() if lower and not _DEVANAGARI.search(k) else k] = v.lower()
    return merged


@lru_cache(maxsize=1)
def hi_map() -> dict[str, str]:
    """Devanagari word -> Latin word (institution words, cities, general complaint words)."""
    return _merge(_BUILTIN_HI_MAP, _flatten(_read_json("hi_map.json")), lower=False)


def _abbreviation_sources() -> tuple[dict[str, str], set[str]]:
    skip = frozenset({"noise", "first_token_only", "stop_tokens"})
    data = _read_json("abbreviations.json")
    merged = _merge(_BUILTIN_ABBREVIATIONS, _flatten(data, skip), lower=True)
    first_only = {"st"}
    if isinstance(data, Mapping) and isinstance(data.get("first_token_only"), list):
        first_only = {str(x).lower() for x in data["first_token_only"]}
    merged.setdefault("st", "saint")
    return merged, first_only


@lru_cache(maxsize=1)
def abbreviations() -> dict[str, str]:
    """Institution-name abbreviation -> expansion (applied at any token position)."""
    merged, first_only = _abbreviation_sources()
    return {k: v for k, v in merged.items() if k not in first_only}


@lru_cache(maxsize=1)
def first_token_abbreviations() -> dict[str, str]:
    """Abbreviations expanded only when they are the first token (``st`` -> ``saint``)."""
    merged, first_only = _abbreviation_sources()
    return {k: v for k, v in merged.items() if k in first_only}


@lru_cache(maxsize=1)
def hinglish_lexicon() -> dict[str, str]:
    """Hinglish / Devanagari complaint word -> canonical English word."""
    return _merge(
        _BUILTIN_LEXICON,
        _flatten(_read_json("hinglish.json"), skip=frozenset({"category_keywords"})),
        lower=True,
    )


@lru_cache(maxsize=1)
def category_keywords() -> dict[str, list[tuple[str, float]]]:
    """Category -> [(keyword, weight)] merging built-ins with ``hinglish.json`` extras."""
    merged: dict[str, dict[str, float]] = {
        c: {clean_key(k).lower(): w for k, w in kws} for c, kws in _BUILTIN_CATEGORY_KEYWORDS.items()
    }
    data = _read_json("hinglish.json")
    extra = data.get("category_keywords") if isinstance(data, Mapping) else None
    if isinstance(extra, Mapping):
        for cat, kws in extra.items():
            if cat not in CATEGORIES or not isinstance(kws, list):
                continue
            bucket = merged.setdefault(cat, {})
            for item in kws:
                if isinstance(item, str):
                    bucket.setdefault(clean_key(item).lower(), 1.0)
                elif isinstance(item, Mapping) and isinstance(item.get("keyword"), str):
                    w = item.get("weight", 1.0)
                    bucket[clean_key(item["keyword"]).lower()] = float(w)
    return {c: sorted(b.items()) for c, b in merged.items()}


@lru_cache(maxsize=1)
def complaint_templates() -> dict[str, list[str]]:
    """Category -> template complaint strings (slots stripped), built-ins + complaint_templates.json."""
    out = {c: list(v) for c, v in CATEGORY_TEMPLATES.items()}
    data = _read_json("complaint_templates.json")
    templates = data.get("templates") if isinstance(data, Mapping) else None
    if not isinstance(templates, Mapping):
        return out

    def add(cat: str, items: Any) -> None:
        if isinstance(items, list):
            for t in items:
                if isinstance(t, str):
                    out.setdefault(cat, []).append(re.sub(r"\{[a-z_]+\}", " ", t))

    for cat, langs in templates.items():
        if cat not in CATEGORIES or not isinstance(langs, Mapping):
            continue
        for lang, items in langs.items():
            if lang == "short" and isinstance(items, Mapping):
                for sub in items.values():
                    add(cat, sub)
            else:
                add(cat, items)
    return out


def reload() -> None:
    """Drop caches (tests, or after the data files change)."""
    hi_map.cache_clear()
    abbreviations.cache_clear()
    first_token_abbreviations.cache_clear()
    hinglish_lexicon.cache_clear()
    category_keywords.cache_clear()
    complaint_templates.cache_clear()
