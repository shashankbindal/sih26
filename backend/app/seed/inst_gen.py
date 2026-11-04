"""Deterministic generation of regional offices, institutions, aliases and the 70/30 split.

Uses its own RNG (seed 26264) so the institution list never depends on case generation or on
the seed-time clock. Running it twice yields byte-identical output.
"""

from __future__ import annotations

import hashlib
import random
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.seed import textgen
from app.seed.scenarios import SCENARIO_INSTITUTIONS
from app.seed.textgen import load_json
from app.services.normalise import normalise_name

SEED = 26264
N_INSTITUTIONS = 200
N_ALIASES = 350
N_TWIN_PAIRS = 8  # includes the Shri Ram pair (scenario E)
ROADS = ["Civil Lines Road", "Station Road", "Ring Road", "Industrial Area Phase 2", "University Road",
         "Bypass Road", "Sector 5", "Model Town", "Gandhi Marg", "Nehru Nagar", "Tilak Marg", "Mall Road"]


@dataclass
class Bundle:
    ros: list[dict[str, Any]]
    institutions: list[dict[str, Any]]
    aliases: list[dict[str, Any]]
    split: dict[uuid.UUID, str] = field(default_factory=dict)
    by_key: dict[str, dict[str, Any]] = field(default_factory=dict)
    twin_pairs: list[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=list)


def _uuid(rng: random.Random) -> uuid.UUID:
    return uuid.UUID(int=rng.getrandbits(128), version=4)


class RealNameBlocklist:
    def __init__(self) -> None:
        bl = load_json("blocklist_real_names.json")
        self.names = [re.compile(r"\b" + re.escape(n.lower().replace("&", "and")) + r"\b")
                      for n in bl["names"]]
        self.short = {s.upper() for s in bl["short_names"]}

    def hit(self, name: str) -> bool:
        text = " ".join(re.sub(r"[^a-z0-9. ]+", " ", name.lower().replace("&", " and ")).split())
        if any(p.search(text) for p in self.names):
            return True
        return any(tok.upper().strip(".,") in self.short for tok in name.split())


def check_real_names(names: list[str]) -> list[str]:
    bl = RealNameBlocklist()
    return [n for n in names if bl.hit(n)]


def full_name(prefix: str, token: str, type_phrase: str, city: str | None) -> str:
    base = " ".join(p for p in (prefix, token, type_phrase) if p)
    return f"{base}, {city}" if city else base


def build(seed: int = SEED) -> Bundle:
    rng = random.Random(seed)
    parts = load_json("name_parts.json")
    dd = load_json("districts.json")
    districts: list[dict[str, Any]] = dd["districts"]
    dist_by_name = {d["district"]: d for d in districts}
    bl = RealNameBlocklist()
    type_to_inst = parts["type_to_inst_type"]
    reserved_tokens = {s["token"] for s in SCENARIO_INSTITUTIONS}

    used_pids: set[str] = {s["pid"] for s in SCENARIO_INSTITUTIONS}
    used_combo: set[tuple[str, str, str]] = set()
    used_domains: set[str] = set()
    token_use: dict[str, int] = {t: 0 for t in parts["tokens"]}
    token_districts: dict[str, set[str]] = {t: set() for t in parts["tokens"]}
    institutions: list[dict[str, Any]] = []

    def new_pid() -> str:
        while True:
            pid = "1-44" + "".join(rng.choice("0123456789") for _ in range(rng.choice((8, 8, 8, 9))))
            if pid not in used_pids:
                used_pids.add(pid)
                return pid

    def make(prefix: str, token: str, type_phrase: str, district: str, *, pincode: str | None = None,
             pid: str | None = None, city_in_name: bool = False, key: str | None = None,
             inst_type: str | None = None) -> dict[str, Any]:
        d = dist_by_name[district]
        city = d["city"]
        name = full_name(prefix, token, type_phrase, city if city_in_name else None)
        slug = re.sub(r"[^a-z0-9]+", "-", f"{token}-{type_phrase.split()[0]}-{city}".lower()).strip("-")
        domain = f"{slug}.example.in"
        n = 2
        while domain in used_domains:
            domain = f"{slug}-{n}.example.in"
            n += 1
        used_domains.add(domain)
        used_combo.add((prefix.lower(), token.lower(), type_phrase.lower()))
        token_use[token] = token_use.get(token, 0) + 1
        token_districts.setdefault(token, set()).add(district)
        pincode = pincode or rng.choice(d["pincodes"])
        inst = {
            "id": _uuid(rng), "key": key, "permanent_id": pid or new_pid(), "name": name,
            "name_norm": normalise_name(name).text,
            "inst_type": inst_type or type_to_inst.get(type_phrase, "Engineering"),
            "address": f"{rng.randint(1, 240)}, {rng.choice(ROADS)}, {city}, {district}, {d['state']} - {pincode}",
            "district": district, "state": d["state"], "pincode": pincode, "ro_code": d["ro_code"],
            "email_domain": domain,
            "phone": f"0{rng.randint(11, 891)}-{rng.randint(2000000, 9999999)}",
            "approval_status": "APPROVED", "established_year": rng.randint(1996, 2021),
            "city": city, "token": token, "prefix": prefix, "type_phrase": type_phrase,
        }
        institutions.append(inst)
        return inst

    # 1. scenario institutions (exact names / IDs from the seed-data plan section 4)
    for s in SCENARIO_INSTITUTIONS:
        make(s["prefix"], s["token"], s["type_phrase"], s["district"], pincode=s["pincode"], pid=s["pid"],
             city_in_name=s["city_in_name"], key=s["key"], inst_type=s.get("inst_type"))

    # 2. seven more deliberate near-twin pairs: same district, same prefix and token, different type
    twin_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = [(institutions[3], institutions[4])]
    blocked_districts = {s["district"] for s in SCENARIO_INSTITUTIONS}
    twin_districts = [d["district"] for d in districts if d["district"] not in blocked_districts]
    rng.shuffle(twin_districts)
    twin_tokens = [t for t in parts["tokens"] if t not in reserved_tokens]
    rng.shuffle(twin_tokens)
    type_pairs = [
        ("College of Engineering", "Institute of Engineering & Technology"),
        ("Institute of Engineering & Technology", "Institute of Technology & Management"),
        ("College of Engineering", "Institute of Technology & Management"),
    ]
    for i in range(N_TWIN_PAIRS - 1):
        token = twin_tokens[i]
        prefix = rng.choice(["Shri", "Dr.", "Sant", "Maharishi", "Smt.", ""])
        t1, t2 = type_pairs[i % len(type_pairs)]
        dist = twin_districts[i]
        a_ = make(prefix, token, t1, dist, city_in_name=True)
        b_ = make(prefix, token, t2, dist, city_in_name=True)
        twin_pairs.append((a_, b_))
    twin_ids = {x["id"] for p in twin_pairs for x in p}

    # 3. random institutions up to 200
    prefixes = parts["prefixes"]
    weights = [parts["prefix_weights"][p] for p in prefixes]
    free_tokens = [t for t in parts["tokens"] if t not in reserved_tokens]
    while len(institutions) < N_INSTITUTIONS:
        prefix = rng.choices(prefixes, weights)[0]
        low = min(token_use[t] for t in free_tokens)
        token = rng.choice([t for t in free_tokens if token_use[t] <= low + 1])
        type_phrase = rng.choice(parts["type_phrases"])
        dist = rng.choice(districts)["district"]
        if (prefix.lower(), token.lower(), type_phrase.lower()) in used_combo:
            continue
        if dist in token_districts[token]:
            continue
        if any(i["token"] == token and i["district"] == dist for i in institutions):
            continue
        nm = full_name(prefix, token, type_phrase, None)
        if bl.hit(nm):
            continue
        make(prefix, token, type_phrase, dist, city_in_name=rng.random() < 0.35)

    # 4. approval status: ~5% closed / closure applied (+ a few NO_ADMISSION_YEAR)
    candidates = [i for i in institutions if i["key"] is None and i["id"] not in twin_ids]
    rng.shuffle(candidates)
    for i, inst in enumerate(candidates[:13]):
        inst["approval_status"] = (["CLOSURE_APPLIED"] * 6 + ["CLOSED"] * 4 + ["NO_ADMISSION_YEAR"] * 3)[i]

    # 5. aliases (~350) -- globally unique alias_norm, none for the Shri Ram twins
    names_norm = {i["name_norm"] for i in institutions}
    seen_alias: set[str] = set()
    aliases: list[dict[str, Any]] = []
    extra_pool: list[tuple[dict[str, Any], str]] = []

    def add_alias(inst: dict[str, Any], raw: str, *, force: bool = False) -> bool:
        norm = normalise_name(raw).text
        if not norm or norm in seen_alias or norm in names_norm:
            return False
        seen_alias.add(norm)
        aliases.append({"id": _uuid(rng), "institution_id": inst["id"], "alias_raw": raw,
                        "alias_norm": norm, "source": "SEED"})
        return True

    for s in SCENARIO_INSTITUTIONS:
        inst = next(i for i in institutions if i["key"] == s["key"])
        for raw in s["aliases"]:
            add_alias(inst, raw, force=True)
    skip = {i["id"] for i in institutions if i["key"] in {s["key"] for s in SCENARIO_INSTITUTIONS}}
    for inst in institutions:
        if inst["id"] in skip:
            continue
        cands: list[str] = []
        ini = textgen.initialism(inst, rng, with_city=rng.random() < 0.8)
        if ini:
            cands.append(ini)
        cands.append(textgen.partial_name(inst, rng))
        cands.append(f"{inst['token']} {rng.choice(['Technical Institute', 'Engineering College', 'Institute'])}")
        cands.append(textgen.devanagari_full(inst))
        probs = [0.85, 0.6, 0.2, 0.15]
        for raw, p in zip(cands, probs, strict=False):
            if rng.random() < p:
                add_alias(inst, raw)
            else:
                extra_pool.append((inst, raw))
    # trim / top up to exactly N_ALIASES (scenario aliases are never trimmed)
    n_scn = sum(len(s["aliases"]) for s in SCENARIO_INSTITUTIONS)
    while len(aliases) < N_ALIASES and extra_pool:
        inst, raw = extra_pool.pop(rng.randrange(len(extra_pool)))
        add_alias(inst, raw)
    if len(aliases) > N_ALIASES:
        droppable = list(range(n_scn, len(aliases)))
        rng.shuffle(droppable)
        for idx in sorted(droppable[: len(aliases) - N_ALIASES], reverse=True):
            del aliases[idx]

    # 6. split 70/30 by institution, demo institutions always in train
    demo_ids = {i["id"] for i in institutions if i["key"] is not None}
    rest = [i["id"] for i in institutions if i["id"] not in demo_ids]
    rng.shuffle(rest)
    n_train = round(0.7 * len(institutions)) - len(demo_ids)
    split = {i: "train" for i in demo_ids}
    for k, iid in enumerate(rest):
        split[iid] = "train" if k < n_train else "heldout"

    return Bundle(
        ros=[dict(r) for r in dd["regional_offices"]],
        institutions=institutions,
        aliases=aliases,
        split=split,
        by_key={i["key"]: i for i in institutions if i["key"]},
        twin_pairs=[(a["id"], b["id"]) for a, b in twin_pairs],
    )


def names_digest(institutions: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for i in institutions:
        h.update(f"{i['permanent_id']}|{i['name']}\n".encode())
    return h.hexdigest()
