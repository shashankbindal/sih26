"""Text generation for the seed: complaint bodies, institution-name noise, complainants.

All randomness comes from the `random.Random` instance passed in; nothing here reads the clock.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import datetime, timedelta
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"

MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_HI = ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर",
             "अक्टूबर", "नवंबर", "दिसंबर"]


@cache
def load_json(name: str) -> Any:
    with open(DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def indian_amount(n: int) -> str:
    s = str(int(n))
    if len(s) <= 3:
        return "₹" + s
    head, tail = s[:-3], s[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return "₹" + ",".join([*parts, tail])


def choose_lang(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.75:
        return "en"
    return "hi" if r < 0.85 else "hinglish"


# ---------------------------------------------------------------- complaint text

def draw_slots(rng: random.Random, category: str, ref_dt: datetime) -> dict[str, Any]:
    slots = load_json("complaint_templates.json")["slots"]
    lo, hi = slots["n"]["overrides"].get(category, [slots["n"]["min"], slots["n"]["max"]])
    d = ref_dt - timedelta(days=rng.randint(3, 40))
    return {
        "day": d.day,
        "mon": d.month - 1,
        "amount": indian_amount(rng.choice(slots["amount"]["choices"])),
        "semester_i": rng.randrange(len(slots["semester"]["en"])),
        "course_i": rng.randrange(len(slots["course"]["en"])),
        "dept_i": rng.randrange(len(slots["dept"]["en"])),
        "n": rng.randint(lo, hi),
        "intake": rng.choice(slots["intake"]["choices"]),
        "year": rng.choice(slots["year"]["choices"]),
    }


_SLOT_RE = re.compile(r"\{(\w+)\}")


def fill(template: str, s: dict[str, Any], lang: str) -> str:
    slots = load_json("complaint_templates.json")["slots"]
    key = "hi" if lang == "hi" else "en"

    def repl(m: re.Match[str]) -> str:
        k = m.group(1)
        if k == "date":
            return f"{s['day']} {(MONTHS_HI if lang == 'hi' else MONTHS_EN)[s['mon']]}"
        if k in ("semester", "course", "dept"):
            return str(slots[k][key][s[k + "_i"]])
        if k in s:
            return str(s[k])
        return m.group(0)

    return _SLOT_RE.sub(repl, template)


def make_text(rng: random.Random, category: str, lang: str, slots: dict[str, Any], *,
              short: bool = False, exclude: tuple[int, ...] = (), idx: int | None = None
              ) -> tuple[str, int]:
    t = load_json("complaint_templates.json")["templates"][category]
    pool = t["short"][lang] if short else t[lang]
    if idx is None:
        choices = [i for i in range(len(pool)) if i not in exclude] or list(range(len(pool)))
        idx = rng.choice(choices)
    return fill(pool[idx % len(pool)], slots, lang), idx


def make_subject(rng: random.Random, category: str, lang: str, slots: dict[str, Any]) -> str:
    return make_text(rng, category, lang, slots, short=True)[0]


def reference_line(rng: random.Random, lang: str, ref: str) -> str:
    pool = load_json("complaint_templates.json")["reference_prefixes"][lang]
    return rng.choice(pool).replace("{ref}", ref)


# ---------------------------------------------------------------- complainants

def party_hash(email: str | None, phone: str | None) -> str | None:
    if not email and not phone:
        return None
    digits = "".join(c for c in (phone or "") if c.isdigit())
    return hashlib.sha256(f"{(email or '').lower()}|{digits}".encode()).hexdigest()


def make_person(rng: random.Random, party_type: str) -> dict[str, Any]:
    pn = load_json("person_names.json")
    first, last = rng.choice(pn["first_names"]), rng.choice(pn["surnames"])
    if party_type == "ANONYMOUS":
        return {"name": None, "email": None, "phone": None, "party_hash": None,
                "party_type": "ANONYMOUS"}
    name = f"{first} {last}"
    if party_type == "FACULTY" and rng.random() < 0.3:
        name = "Dr. " + name
    email = f"{first}.{last}{rng.randint(10, 99)}@{rng.choice(['mailbox', 'inbox', 'webmail'])}.example".lower()
    phone = str(rng.choice("6789")) + "".join(rng.choice("0123456789") for _ in range(9))
    return {"name": name, "email": email, "phone": phone,
            "party_hash": party_hash(email, phone), "party_type": party_type}


# ---------------------------------------------------------------- institution names

@lru_cache(maxsize=1)
def city_devanagari() -> dict[str, str]:
    inv: dict[str, str] = {}
    for dev, latin in load_json("hi_map.json")["cities"].items():
        inv.setdefault(latin, dev)
    return inv


def devanagari_full(inst: dict[str, Any]) -> str:
    dv = load_json("name_parts.json")["devanagari"]
    words: list[str] = []
    if inst["prefix"]:
        words.append(dv.get(inst["prefix"], inst["prefix"]))
    words.append(dv.get(inst["token"], inst["token"]))
    words.extend(dv.get(w, w) for w in inst["type_phrase"].split())
    return " ".join(words)


def initialism(inst: dict[str, Any], rng: random.Random | None = None, with_city: bool = False) -> str | None:
    stop = {"of", "and", "&", "the", "for"}
    words = [inst["token"], *inst["type_phrase"].split()]
    letters = "".join(w[0].upper() for w in words if w.lower() not in stop)
    if len(letters) < 3:
        return None
    return f"{letters} {inst['city']}" if with_city else letters


def _abbreviate_words(rng: random.Random, name: str) -> str:
    noise = load_json("abbreviations.json")["noise"]
    out: list[str] = []
    for w in name.replace(",", " ").split():
        lw = w.lower()
        if lw in noise["word_abbreviations"] and rng.random() < 0.8:
            out.append(rng.choice(noise["word_abbreviations"][lw]))
        elif lw == "of" and rng.random() < 0.4:
            continue
        elif w == "&" and rng.random() < 0.5:
            out.append(rng.choice(noise["separators"]["and_variants"]))
        else:
            out.append(w)
    return " ".join(out)


def _misspell(rng: random.Random, name: str) -> str:
    noise = load_json("abbreviations.json")["noise"]["misspellings"]
    words = name.split()
    idxs = [i for i, w in enumerate(words) if w.lower() in noise]
    if not idxs:
        return name
    i = rng.choice(idxs)
    words[i] = rng.choice(noise[words[i].lower()])
    return " ".join(words)


def partial_name(inst: dict[str, Any], rng: random.Random) -> str:
    tp = inst["type_phrase"].lower()
    generic = {"engineering": "Engg College", "management": "Management Institute",
               "pharmacy": "Pharmacy College", "polytechnic": "Polytechnic",
               "mca": "Institute"}
    key = ("engineering" if "engineering" in tp or "technology" in tp
           else "management" if "management" in tp
           else "pharmacy" if "pharmacy" in tp
           else "polytechnic" if "polytechnic" in tp else "mca")
    pre = (inst["prefix"] + " ") if inst["prefix"] and rng.random() < 0.5 else ""
    return f"{pre}{inst['token']} {generic[key]}"


def noisy_name(inst: dict[str, Any], rng: random.Random) -> tuple[str, bool]:
    """Abbreviated/misspelt institution name. Returns (text, includes_city)."""
    r = rng.random()
    if r < 0.25:
        ini = initialism(inst, rng, with_city=True)
        if ini:
            return ini, True
    if r < 0.50:
        return _abbreviate_words(rng, base_name(inst)), False
    if r < 0.70:
        return _misspell(rng, base_name(inst)), False
    if r < 0.90:
        return partial_name(inst, rng), False
    return base_name(inst).lower(), False


def base_name(inst: dict[str, Any]) -> str:
    return " ".join(p for p in (inst["prefix"], inst["token"], inst["type_phrase"]) if p)


def institution_text(inst: dict[str, Any], rng: random.Random) -> tuple[str, str]:
    """Free-text institution field as typed by a complainant/officer. Returns (text, style)."""
    r = rng.random()
    city, district, pin = inst["city"], inst["district"], inst["pincode"]
    if r < 0.10 and city.lower() in city_devanagari():
        dev = devanagari_full(inst) if rng.random() < 0.4 else (
            load_json("name_parts.json")["devanagari"][inst["token"]] + " इंजीनियरिंग कॉलेज")
        txt = f"{dev} {city_devanagari()[city.lower()]}"
        return (f"{txt} {pin}" if rng.random() < 0.3 else txt), "devanagari"
    if r < 0.35:
        name, has_city = noisy_name(inst, rng)
        style = "abbr"
    else:
        name, has_city = base_name(inst), False
        style = "official"
    s = rng.random()
    loc = ("city" if s < 0.20 else "district" if s < 0.50 else "pincode" if s < 0.70 else "both")
    parts = [name]
    if loc == "city" and not has_city:
        parts.append(city)
    elif loc == "district":
        parts.append(district)
    elif loc == "pincode":
        parts.append(pin)
    elif loc == "both":
        parts.extend([district, pin])
    return ", ".join(parts), style


def corrupt_pid(rng: random.Random, pid: str) -> str:
    digits = list(pid[2:])
    i = rng.randrange(len(digits))
    digits[i] = str((int(digits[i]) + rng.randint(1, 9)) % 10)
    return "1-" + "".join(digits)
