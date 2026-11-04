"""Name and text normalisation shared by the CaseLink engine and the classifier.

Public API
----------
``normalise_name(s) -> NormalisedName(text, tokens, key, translations, has_devanagari)``
``normalise_text(s) -> str``                   complaint text for similarity / classification
``mask_pii(s, known_names=()) -> str``         [EMAIL] [PHONE] [ID] [NAME]
``detect_language(s) -> 'en' | 'hi' | 'hinglish'``
``extract_pincode(s) -> str | None``
``extract_permanent_id(s) -> str | None``      ``1-`` + 7..11 digits, spaces tolerated
``extract_district(text, districts) -> str | None``
``transliterate_word(word) -> str``            single Devanagari word -> Latin, schwa deleted

Pure functions, no database access.  Spec: the CaseLink design section 0.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache

from indic_transliteration import sanscript

from app.services import data_loader
from app.services.data_loader import clean_key

STOP_TOKENS = frozenset({"the", "of", "and", "for"})

_DEV_RANGE = "ऀ-ॿ"
_DEV_RE = re.compile(f"[{_DEV_RANGE}]")
_SCRIPT_SPLIT = re.compile(f"[{_DEV_RANGE}]+|[^{_DEV_RANGE}\\s]+")
_PUNCT_RE = re.compile(f"[^\\w\\s{_DEV_RANGE}]|_")
_DANDA_RE = re.compile("[।॥]")
_DOTTED_ABBR_RE = re.compile(r"\b(?:[A-Za-z]\.){2,}")
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"))

# --------------------------------------------------------------------------------------
# Devanagari -> Latin
# --------------------------------------------------------------------------------------

_ITRANS_UNIT = re.compile(
    r"R\^i|R\^I|RRi|RRI|LLi|LLI|j~n|~N|~n|ai|au|kh|gh|chh|Ch|ch|jh|Th|Dh|th|dh|ph|bh|Sh|sh|."
)
_VOWEL_UNITS = frozenset({"a", "A", "i", "I", "u", "U", "e", "E", "o", "O", "ai", "au",
                          "RRi", "RRI", "R^i", "R^I", "LLi", "LLI"})
_PRE_TRANSLIT = str.maketrans({
    "ॉ": "ो",  # ॉ -> ो
    "ॅ": "े",  # ॅ -> े
    "ऑ": "ओ",  # ऑ -> ओ
    "ऍ": "ए",  # ऍ -> ए
})


def _schwa_delete(itrans: str) -> str:
    """Hindi schwa deletion on case-sensitive ITRANS (long vowels are upper case).

    (a) drop a word-final inherent ``a`` after a consonant (word keeps another vowel);
    (b) drop a medial ``a`` in the pattern vowel-consonant-a-consonant-vowel, scanning right to
    left so that ``sarakArI -> sarkArI`` and ``jabalapura -> jabalpur``.
    """
    units = _ITRANS_UNIT.findall(itrans)
    if not units or any(not u.isascii() for u in units):
        return itrans
    vowel_count = sum(1 for u in units if u in _VOWEL_UNITS)
    if len(units) > 1 and units[-1] == "a" and units[-2] not in _VOWEL_UNITS and vowel_count > 1:
        units.pop()
    i = len(units) - 1
    while i >= 2:
        if (
            units[i] == "a"
            and i + 2 < len(units)
            and units[i - 2] in _VOWEL_UNITS
            and units[i - 1] not in _VOWEL_UNITS
            and units[i + 1] not in _VOWEL_UNITS
            and units[i + 2] in _VOWEL_UNITS
        ):
            del units[i]
        i -= 1
    return "".join(units)


def _itrans_cleanup(s: str) -> str:
    for src, dst in (
        ("R^i", "ri"), ("R^I", "ri"), ("RRi", "ri"), ("RRI", "ri"), ("LLi", "li"), ("LLI", "li"),
        ("j~n", "gy"), ("~N", "n"), ("~n", "n"), (".n", "n"), (".N", "n"), (".h", ""),
        ("Ch", "chh"), ("Sh", "sh"), ("M", "n"), ("H", "h"),
    ):
        s = s.replace(src, dst)
    s = s.lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    for src, dst in (("aa", "a"), ("ii", "i"), ("uu", "u")):
        s = s.replace(src, dst)
    return s


@lru_cache(maxsize=4096)
def transliterate_word(word: str) -> str:
    """Transliterate one Devanagari word to lower-case Latin with schwa deletion."""
    word = clean_key(word).translate(_PRE_TRANSLIT)
    raw = sanscript.transliterate(word, sanscript.DEVANAGARI, sanscript.ITRANS)
    return _itrans_cleanup(_schwa_delete(raw))


# --------------------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalisedName:
    text: str                                   # display form, stop words kept
    tokens: tuple[str, ...]                     # comparison tokens (stop words dropped)
    key: str                                    # folded comparison key
    translations: tuple[tuple[str, str], ...] = ()   # (devanagari word, latin word)
    has_devanagari: bool = False


def _prep(s: str | None) -> str:
    s = unicodedata.normalize("NFKC", s or "").translate(_ZERO_WIDTH)
    return _DANDA_RE.sub(" ", s)


def _words(s: str) -> list[str]:
    """Split into script-homogeneous words after removing punctuation."""
    s = _DOTTED_ABBR_RE.sub(lambda m: m.group(0).replace(".", ""), s)
    s = s.replace("&", " and ").replace("'", "").replace("’", "")
    s = _PUNCT_RE.sub(" ", s)
    return _SCRIPT_SPLIT.findall(s)


def fold_key(token: str) -> str:
    """Spelling-variant folding used only inside the comparison key."""
    t = token.lower()
    for src, dst in (("sh", "s"), ("ph", "f"), ("ck", "k"), ("ee", "i"), ("oo", "u"),
                     ("aa", "a"), ("ii", "i"), ("w", "v")):
        t = t.replace(src, dst)
    return re.sub(r"(.)\1+", r"\1", t)


def _devanagari_to_latin(word: str, *, text_mode: bool) -> tuple[list[str], bool]:
    """Return (latin words, via_map)."""
    mapped = data_loader.hi_map().get(clean_key(word))
    if mapped is None and text_mode:
        mapped = data_loader.hinglish_lexicon().get(clean_key(word))
    if mapped is not None:
        return mapped.split(), True
    latin = transliterate_word(word)
    if text_mode:
        latin = latin.replace("ph", "f")
    return ([latin] if latin else []), False


@lru_cache(maxsize=8192)
def normalise_name(s: str | None) -> NormalisedName:
    """Spec section 0: NFKC, Hindi word map, transliterate, abbreviations, stop tokens."""
    abbr = data_loader.abbreviations()
    first_only = data_loader.first_token_abbreviations()
    translations: list[tuple[str, str]] = []
    out: list[str] = []
    has_dev = False
    for word in _words(_prep(s)):
        if _DEV_RE.search(word):
            has_dev = True
            latin, _ = _devanagari_to_latin(word, text_mode=False)
            if latin:
                translations.append((word, " ".join(latin)))
            out.extend(latin)
        else:
            out.append(word.lower())
    expanded: list[str] = []
    for i, tok in enumerate(out):
        if i == 0 and tok in first_only:
            expanded.extend(first_only[tok].split())
        elif tok in abbr:
            expanded.extend(abbr[tok].split())
        else:
            expanded.append(tok)
    text = " ".join(expanded)
    tokens = tuple(t for t in expanded if t not in STOP_TOKENS)
    key = " ".join(fold_key(t) for t in tokens)
    return NormalisedName(text, tokens, key, tuple(translations), has_dev)


# --------------------------------------------------------------------------------------
# Free text
# --------------------------------------------------------------------------------------

_NUM_COMMA_RE = re.compile(r"(?<=\d),(?=\d)")


@lru_cache(maxsize=1)
def _phrase_rules() -> tuple[tuple[re.Pattern[str], str], ...]:
    rules = []
    for k, v in sorted(data_loader.hinglish_lexicon().items(), key=lambda kv: -len(kv[0])):
        if " " in k and not _DEV_RE.search(k):
            rules.append((re.compile(rf"\b{re.escape(k)}\b"), v))
    return tuple(rules)


@lru_cache(maxsize=4096)
def normalise_text(s: str | None) -> str:
    """Normalise a complaint description or subject for similarity and classification."""
    s = _prep(s).replace("₹", " rs ")
    s = _NUM_COMMA_RE.sub("", s)
    lexicon = data_loader.hinglish_lexicon()
    toks: list[str] = []
    for word in _words(s):
        if _DEV_RE.search(word):
            latin, via_map = _devanagari_to_latin(word, text_mode=True)
            if via_map:
                toks.extend(latin)
            else:
                toks.extend(lexicon.get(t, t) for t in latin)
        else:
            toks.append(word.lower())
    # pass 1: multi-word phrases on the raw words ("wapas liya"); pass 2 below, after the word
    # map, catches phrases that only appear once words are canonical ("wapas nahi" -> "refund nahi")
    text = " ".join(toks)
    for pat, repl in _phrase_rules():
        text = pat.sub(repl, text)
    toks = [lexicon.get(t, t) for t in text.split()]
    text = " ".join(toks)
    for pat, repl in _phrase_rules():
        text = pat.sub(repl, text)
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------------------
# PII masking
# --------------------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_AADHAAR_RE = re.compile(r"(?<!\d)[2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4}(?!\d)")
_PHONE_RE = re.compile(r"(?<!\d)(?:(?:\+|00)?91[\-\s]?)?[6-9]\d{4}[\s\-]?\d{5}(?!\d)")


def mask_pii(s: str | None, known_names: Iterable[str] = ()) -> str:
    """Replace emails, Indian mobiles, Aadhaar-like numbers and known names with tokens."""
    out = s or ""
    out = _EMAIL_RE.sub("[EMAIL]", out)
    out = _AADHAAR_RE.sub("[ID]", out)
    out = _PHONE_RE.sub("[PHONE]", out)
    for name in known_names:
        name = (name or "").strip()
        if len(name) >= 2:
            out = re.sub(re.escape(name), "[NAME]", out, flags=re.IGNORECASE)
    return out


# --------------------------------------------------------------------------------------
# Language
# --------------------------------------------------------------------------------------

_HINGLISH_MARKERS = frozenset({
    "hai", "hain", "nahi", "nahin", "nhi", "mila", "mili", "mile", "maine", "mujhe", "mera",
    "meri", "mere", "kiya", "kiye", "kar", "karo", "kare", "rahe", "raha", "rahi", "abhi",
    "tak", "wapas", "vapas", "bolta", "bolte", "kehta", "kehte", "diya", "diye", "dena",
    "tab", "agar", "lekin", "aur", "bhi", "saal", "paisa", "paise", "ki", "ka", "ke", "ko",
    "se", "par", "hum", "humne", "unhone", "kyun", "kyon", "milega", "milegi", "chahiye",
    "kripya", "sahab", "sir", "fees", "college", "wala", "wale", "jaldi", "pareshan",
})
_HINGLISH_STRONG = _HINGLISH_MARKERS - {"sir", "college", "fees", "kar", "se", "par", "tab",
                                       "agar", "hum", "dena", "ki", "ka", "ke", "ko", "aur"}


def detect_language(s: str | None) -> str:
    """'en', 'hi' (Devanagari) or 'hinglish' (Romanised Hindi or mixed script)."""
    s = _prep(s)
    dev = len(_DEV_RE.findall(s))
    lat = len(re.findall(r"[A-Za-z]", s))
    if dev + lat == 0:
        return "en"
    ratio = dev / (dev + lat)
    if ratio >= 0.9:
        return "hi"
    if ratio >= 0.1:
        return "hinglish"
    words = re.findall(r"[a-z]+", s.lower())
    if not words:
        return "en"
    strong = sum(1 for w in words if w in _HINGLISH_STRONG)
    weak = sum(1 for w in words if w in _HINGLISH_MARKERS)
    if strong >= 2 or weak / len(words) >= 0.2:
        return "hinglish"
    return "en"


# --------------------------------------------------------------------------------------
# Extractors
# --------------------------------------------------------------------------------------

_PIN_RE = re.compile(r"(?<![\d\-/])(?<!rs )(?<!rs\.)[1-9]\d{5}(?![\d\-/])", re.IGNORECASE)
_PID_RE = re.compile(r"(?<![\d\w])1\s*[\-–—]\s*((?:\d\s?){7,13})(?!\d)")
_PID_FULL = re.compile(r"^1-\d{7,11}$")


def extract_pincode(s: str | None) -> str | None:
    m = _PIN_RE.search(_prep(s))
    return m.group(0) if m else None


def clean_permanent_id(raw: str | None) -> str | None:
    """Return the ID without spaces when it matches ``^1-\\d{7,11}$``, else None."""
    if not raw:
        return None
    cand = re.sub(r"\s+", "", raw).replace("–", "-").replace("—", "-")
    return cand if _PID_FULL.match(cand) else None


def extract_permanent_id(s: str | None) -> str | None:
    """Find an AICTE Permanent ID (``1-`` + 7..11 digits) in free text."""
    text = _prep(s)
    for m in _PID_RE.finditer(text):
        digits = re.sub(r"\s", "", m.group(1))
        if len(digits) > 11:
            digits = digits[:10]
        cand = f"1-{digits}"
        if _PID_FULL.match(cand):
            return cand
    return None


_DISTRICT_SUFFIX = frozenset({"nagar", "urban", "rural", "city", "district", "dist"})


def district_forms(district: str) -> set[str]:
    """Normalised alternative spellings of a district: full name and the name without suffix."""
    tokens = list(normalise_name(district).tokens)
    forms = {" ".join(tokens)}
    core = [t for t in tokens if t not in _DISTRICT_SUFFIX]
    if core:
        forms.add(" ".join(core))
    return {f for f in forms if f}


def extract_district(text: str | None, districts: Sequence[str]) -> str | None:
    """Return the entry of ``districts`` named in ``text`` (longest form wins), else None."""
    if not text or not districts:
        return None
    haystack = f" {normalise_text(text)} "
    best: tuple[int, str] | None = None
    for d in districts:
        for form in district_forms(d):
            if f" {form} " in haystack and (best is None or len(form) > best[0]):
                best = (len(form), d)
    return best[1] if best else None
