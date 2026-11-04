"""Case-level synthetic data: specs (scenario, ground-truth pairs, background), noise, clocks.

Pure in-memory; the database writer lives in generate.py. All dates are relative to `anchor`.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.seed import textgen
from app.seed.inst_gen import Bundle
from app.seed.scenarios import fmt_date, scenario_specs
from app.seed.spec import CaseSpec
from app.services.clocks import ClockPolicy

CASE_SEED = 26264 ^ 0x5EED

BUREAU_QUOTA = {"PGRC": 270, "RB": 150, "RO": 120, "APPROVAL": 30, "VIGILANCE": 30}
STATUS_QUOTA = {"DISPOSED": 270, "UNDER_PROCESS": 120, "AWAITING_ATR": 72, "RECEIVED": 48,
                "TRANSFERRED": 30, "ESCALATED": 24, "AWAITING_COMPLAINANT": 18, "CLOSED_NO_ACTION": 18}
OPEN_ST = {"RECEIVED", "UNDER_PROCESS", "AWAITING_ATR", "AWAITING_COMPLAINANT", "TRANSFERRED",
           "ESCALATED", "REOPENED"}
REFUND_CATS = {"FEE_REFUND", "CERTIFICATE_WITHHELD"}
FAMILIES = [
    {"FEE_REFUND", "CERTIFICATE_WITHHELD", "ADMISSION"},
    {"FACULTY_SHORTAGE", "SCRUTINY_COMMITTEE", "INFRASTRUCTURE", "FAKE_APPROVAL_CLAIM"},
    {"SERVICE_MATTER", "FACULTY_SHORTAGE"},
]

CAT_W: dict[str, dict[str, float]] = {
    "PGRC": {"FEE_REFUND": .25, "CERTIFICATE_WITHHELD": .17, "ADMISSION": .08, "RAGGING": .08,
             "SCHOLARSHIP": .10, "FACULTY_SHORTAGE": .08, "INFRASTRUCTURE": .07, "SERVICE_MATTER": .08,
             "FAKE_APPROVAL_CLAIM": .04, "OTHER": .05},
    "RB": {"FACULTY_SHORTAGE": .25, "INFRASTRUCTURE": .20, "SCRUTINY_COMMITTEE": .25,
           "FAKE_APPROVAL_CLAIM": .10, "ADMISSION": .05, "SERVICE_MATTER": .05, "OTHER": .10},
    "RO": {"FEE_REFUND": .22, "CERTIFICATE_WITHHELD": .14, "SCHOLARSHIP": .12, "INFRASTRUCTURE": .12,
           "ADMISSION": .12, "RAGGING": .06, "FACULTY_SHORTAGE": .08, "SERVICE_MATTER": .06, "OTHER": .08},
    "APPROVAL": {"FAKE_APPROVAL_CLAIM": .35, "SCRUTINY_COMMITTEE": .20, "ADMISSION": .15, "OTHER": .30},
    "VIGILANCE": {"FAKE_APPROVAL_CLAIM": .40, "SERVICE_MATTER": .15, "OTHER": .25, "ADMISSION": .10,
                  "CERTIFICATE_WITHHELD": .10},
}
CHAN_W: dict[str, dict[str, float]] = {
    "PGRC": {"CSS": .40, "CPGRAMS": .45, "EMAIL": .15},
    "RB": {"BUREAU_FILE": .70, "EMAIL": .15, "CPGRAMS": .15},
    "RO": {"RO_REGISTER": .85, "CSS": .10, "EMAIL": .05},
    "APPROVAL": {"BUREAU_FILE": .60, "EMAIL": .20, "CPGRAMS": .20},
    "VIGILANCE": {"EMAIL": .40, "CPGRAMS": .40, "BUREAU_FILE": .20},
}
RO_W = {"KNP": 3.0, "BPL": 3.0, "CHD": 1.5}

REMARKS = ["Called for comments from the institution", "Complainant informed of the process followed",
           "Institution reply examined; further clarification sought", "Matter taken up with the Regional Office",
           "Reminder issued to the institution", "File put up to the bureau head for directions"]
CLOSE_REMARKS = ["Matter not within AICTE jurisdiction; complainant advised accordingly",
                 "Complaint withdrawn by the complainant", "No actionable material in the complaint"]
DISPOSE_REMARKS = ["ATR received and found satisfactory; disposed", "Refund confirmed by the institution; disposed",
                   "Institution complied with the direction; disposed", "Matter resolved; complainant informed"]


def family_clash(c1: str, c2: str) -> bool:
    if c1 == c2:
        return True
    return any(c1 in f and c2 in f for f in FAMILIES)


def wchoice(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), list(weights.values()))[0]


def _uuid(rng: random.Random) -> uuid.UUID:
    return uuid.UUID(int=rng.getrandbits(128), version=4)


@dataclass
class Dataset:
    anchor: datetime
    cases: list[dict[str, Any]] = field(default_factory=list)
    complainants: list[dict[str, Any]] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    clocks: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    specs: dict[uuid.UUID, CaseSpec] = field(default_factory=dict)  # case id -> spec
    persons: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)  # case id -> person
    events: dict[uuid.UUID, list[dict[str, Any]]] = field(default_factory=dict)  # case id -> events
    pair_truth: list[dict[str, Any]] = field(default_factory=list)  # {kind, gid, a, b}
    stats: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------ builder

class Builder:
    def __init__(self, anchor: datetime, bundle: Bundle, users: list[dict[str, Any]], policy: ClockPolicy):
        self.anchor = anchor
        self.b = bundle
        self.rng = random.Random(CASE_SEED)
        self.users = users
        self.policy = policy
        self.by_email = {u["email"]: u for u in users}
        self.officers: dict[str, list[dict[str, Any]]] = {}
        self.heads: dict[str, dict[str, Any]] = {}
        for u in users:
            if u["role"] == "BUREAU_HEAD":
                self.heads[u["bureau"]] = u
            elif u["role"].endswith("_OFFICER"):
                self.officers.setdefault(u["bureau"], []).append(u)
        self.inst_by_id = {i["id"]: i for i in bundle.institutions}
        self.specs: list[CaseSpec] = []
        self.used_refs: set[tuple[str, str]] = set()
        self.persons: dict[str, dict[str, Any]] = {}
        self.assigned: dict[uuid.UUID, list[tuple[datetime, str]]] = {}
        self.pair_log: list[dict[str, Any]] = []
        self.pair_insts: set[uuid.UUID] = set()

    # ---- helpers
    def ago(self, days: float) -> datetime:
        return self.anchor - timedelta(days=days)

    def open_status_for_pair(self) -> str:
        return self.rng.choices(["UNDER_PROCESS", "AWAITING_ATR", "TRANSFERRED", "AWAITING_COMPLAINANT"],
                                [.50, .35, .10, .05])[0]

    def channel(self, bureau: str, allow_cp: bool = True) -> str:
        w = {k: v for k, v in CHAN_W[bureau].items() if allow_cp or k != "CPGRAMS"}
        return wchoice(self.rng, w)

    def derive_pending(self, s: CaseSpec) -> None:
        rng, anchor = self.rng, self.anchor
        age = (anchor - s.received_at).total_seconds()
        off = timedelta(seconds=min(age * 0.5, rng.uniform(0.5, 4) * 86400))
        off = max(off, timedelta(hours=3))
        if s.status == "AWAITING_ATR":
            s.pending_step, s.pending_since = "INSTITUTION_ATR", s.received_at + off
            s.pending_action = "ATR called from institution"
        elif s.status == "AWAITING_COMPLAINANT":
            s.pending_step, s.pending_since = "COMPLAINANT_REPLY", s.received_at + off
            s.pending_action = "Clarification sought from complainant"
        elif s.status == "UNDER_PROCESS":
            if s.bureau == "PGRC" and s.category in REFUND_CATS and rng.random() < 0.25:
                s.pending_step, s.pending_since = "REFUND_FOLLOWUP", s.received_at + off
                s.pending_action = "Refund follow-up with institution in progress"
            elif s.bureau == "PGRC" and rng.random() < 0.06:
                s.pending_step = "HEARING"
                s.pending_since = s.received_at + off
                s.pending_action = f"Hearing scheduled {fmt_date(anchor + timedelta(days=rng.uniform(3, 20)))}"
            elif s.bureau == "RB" and rng.random() < 0.4:
                s.pending_action = ("Scrutiny committee review scheduled" if s.category == "SCRUTINY_COMMITTEE"
                                    else "Institution reply under examination")
            elif s.bureau == "RO" and rng.random() < 0.2:
                s.pending_action = "Verification with institution pending"
        elif s.status == "ESCALATED":
            s.pending_action = "Escalated to bureau head"
        if s.pending_since and s.pending_since > anchor - timedelta(hours=1):
            s.pending_since = anchor - timedelta(hours=1)

    def new_ref(self, channel: str, bureau: str, ro: str | None) -> str:
        rng = self.rng
        while True:
            if channel == "CPGRAMS":
                ref = f"DHIGH/E/2026/{rng.randint(20000, 39999):07d}"
            elif channel == "CSS":
                ref = f"CSS-2026-{rng.randint(60000, 99999)}"
            elif channel == "EMAIL":
                ref = f"EML-2026-{rng.randint(100, 9999):06d}"
            elif channel == "RO_REGISTER":
                ref = f"ROREG/{ro or 'KNP'}/2026/{rng.randint(1, 999):04d}"
            else:
                ref = f"{bureau}/F/2026/{rng.randint(1, 999):04d}"
            if (channel, ref) not in self.used_refs:
                self.used_refs.add((channel, ref))
                return ref

    # ---- scenario cases
    def add_scenarios(self) -> None:
        by_key = self.b.by_key
        self.specs.extend(scenario_specs(self.anchor, by_key))
        for s in self.specs:
            if s.source_ref:
                self.used_refs.add((s.channel, s.source_ref))
        for s in self.specs:
            if s.inst_id:
                self.pair_insts.add(s.inst_id)
        for gid_kind, key_a, key_b in (("dup", "A-PGRC-2", "A-EMAIL-DUP"), ("related", "A-PGRC-1", "A-RO-1"),
                                       ("conflict", "C-RB", "C-PGRC"), ("negative", "D-PGRC", "D-RO")):
            sa = next(s for s in self.specs if s.key == key_a)
            sb = next(s for s in self.specs if s.key == key_b)
            self.pair_log.append({"kind": gid_kind, "gid": sa.groups[gid_kind], "a": sa, "b": sb})

    # ---- ground-truth pairs
    def add_pairs(self) -> None:
        rng = self.rng
        twin_ids = {i for p in self.b.twin_pairs for i in p}
        pool = [i for i in self.b.institutions if i["key"] is None and i["id"] not in twin_ids
                and i["approval_status"] in ("APPROVED", "NO_ADMISSION_YEAR")]
        rng.shuffle(pool)
        it = iter(pool)

        def take() -> dict[str, Any]:
            inst = next(it)
            self.pair_insts.add(inst["id"])
            return inst

        def mk(bureau: str, channel: str, cat: str, inst: dict[str, Any], received: datetime,
               status: str, gkind: str, gid: str, lang: str, party: str, **kw: Any) -> CaseSpec:
            ptype = kw.pop("party_type", "STUDENT")
            s = CaseSpec(bureau=bureau, channel=channel, category=cat, inst_id=inst["id"], received_at=received,
                         status=status, lang=lang, fixed=True, party_key=party, party_type=ptype,
                         groups={gkind: gid}, **kw)
            if bureau == "RO":
                s.ro_code = inst["ro_code"]
            if s.pending_step == "NONE" and not s.pending_action:
                self.derive_pending(s)
            self.specs.append(s)
            return s

        # duplicates: same complainant re-files on another channel within 2-20 days (17 + scenario F)
        for n in range(17):
            gid = f"D-{n + 1:03d}"
            inst = take()
            cat = rng.choices(["FEE_REFUND", "CERTIFICATE_WITHHELD", "ADMISSION", "SCHOLARSHIP", "FACULTY_SHORTAGE",
                               "INFRASTRUCTURE", "RAGGING"], [.28, .22, .1, .1, .1, .1, .1])[0]
            age = rng.uniform(5, 19.5)
            gap = rng.uniform(2, min(18.0, age - 0.4))
            t1, t2 = self.ago(age), self.ago(age - gap)
            lang1 = textgen.choose_lang(rng)
            lang2 = lang1 if rng.random() < 0.7 else textgen.choose_lang(rng)
            slots = textgen.draw_slots(rng, cat, t1)
            party = f"dup-{gid}"
            st1 = self.open_status_for_pair()
            email_mode = n % 3 == 2
            if email_mode:
                ch1, ch2 = "CPGRAMS", "EMAIL"
            elif n % 2 == 0:
                ch1, ch2 = "CSS", "CPGRAMS"
            else:
                ch1, ch2 = "CPGRAMS", "CSS"
            st2 = "RECEIVED" if (age - gap) <= 3 and rng.random() < 0.6 else self.open_status_for_pair()
            s1 = mk("PGRC", ch1, cat, inst, t1, st1, "dup", gid, lang1, party, slots=slots)
            s1.source_ref = self.new_ref(ch1, "PGRC", None)
            s2 = mk("PGRC", ch2, cat, inst, t2, st2, "dup", gid, lang2, party, slots=slots)
            s2.source_ref = self.new_ref(ch2, "PGRC", None)
            t_idx = rng.randrange(6)
            s1.template_idx = t_idx
            if rng.random() < 0.5 and s2.lang == s1.lang:
                s2.template_idx = t_idx  # re-filed by copy-paste: same wording
            else:
                s2.template_idx = (t_idx + rng.randint(1, 5)) % 6
            if email_mode:
                s2.extra["quote_ref"] = s1.source_ref
            self.pair_log.append({"kind": "dup", "gid": gid, "a": s1, "b": s2})

        # related across bureaus (29 + scenario A)
        rel_types = [
            ("FEE_REFUND", "PGRC", "FEE_REFUND", "RO"), ("CERTIFICATE_WITHHELD", "PGRC", "FEE_REFUND", "RO"),
            ("FEE_REFUND", "PGRC", "ADMISSION", "RO"), ("FACULTY_SHORTAGE", "PGRC", "FACULTY_SHORTAGE", "RB"),
            ("FACULTY_SHORTAGE", "RB", "INFRASTRUCTURE", "RO"), ("INFRASTRUCTURE", "PGRC", "INFRASTRUCTURE", "RB"),
            ("SCRUTINY_COMMITTEE", "RB", "FACULTY_SHORTAGE", "PGRC"),
            ("FAKE_APPROVAL_CLAIM", "VIGILANCE", "FAKE_APPROVAL_CLAIM", "PGRC"),
            ("RAGGING", "PGRC", "RAGGING", "RO"), ("SCHOLARSHIP", "PGRC", "SCHOLARSHIP", "RO"),
            ("SERVICE_MATTER", "PGRC", "FACULTY_SHORTAGE", "RB"), ("CERTIFICATE_WITHHELD", "PGRC", "CERTIFICATE_WITHHELD", "RO"),
            ("FEE_REFUND", "PGRC", "FEE_REFUND", "RO"), ("FAKE_APPROVAL_CLAIM", "RB", "FAKE_APPROVAL_CLAIM", "APPROVAL"),
        ]
        for n in range(29):
            gid = f"R-{n + 1:03d}"
            inst = take()
            ca, ba, cb, bb = rel_types[n % len(rel_types)]
            age = rng.uniform(4, 110)
            gap = rng.uniform(1, 55)
            ra, rb = self.ago(age), self.ago(max(0.5, age - gap))
            if rng.random() < 0.5:
                ra, rb = rb, ra
            pa, pb = ra, rb

            def ch(bu: str, when: datetime) -> str:
                return self.channel(bu, allow_cp=(self.anchor - when).days <= 19)

            sa = mk(ba, ch(ba, pa), ca, inst, pa, self.open_status_for_pair(), "related", gid,
                    textgen.choose_lang(rng), f"{gid}-a",
                    party_type="FACULTY" if ca in ("FACULTY_SHORTAGE", "SERVICE_MATTER") else "STUDENT")
            sb = mk(bb, ch(bb, pb), cb, inst, pb, self.open_status_for_pair(), "related", gid,
                    textgen.choose_lang(rng), f"{gid}-b",
                    party_type="FACULTY" if cb in ("FACULTY_SHORTAGE", "SERVICE_MATTER") else "STUDENT")
            for s in (sa, sb):
                s.source_ref = self.new_ref(s.channel, s.bureau, s.ro_code)
                if s.bureau == "RO":
                    s.short = rng.random() < 0.5
            self.pair_log.append({"kind": "related", "gid": gid, "a": sa, "b": sb})

        # conflicting pairs (8 + scenario C): both have pending actions from the conflict matrix
        kinds = ["sc_service", "sc_service", "sc_faculty", "sc_faculty", "inspection", "inspection", "hearing", "hearing"]
        for n, kind in enumerate(kinds):
            gid = f"C-{n + 1:03d}"
            inst = take()
            age = rng.uniform(6, 18)
            rb_rec, pg_rec = self.ago(age + rng.uniform(0, 4)), self.ago(age)
            lang = "en"
            if kind.startswith("sc"):
                issued = self.ago(rng.uniform(2, 6))
                due = issued + timedelta(days=15)
                sa = mk("RB", "BUREAU_FILE", "FACULTY_SHORTAGE", inst, rb_rec, "UNDER_PROCESS", "conflict", gid, lang,
                        f"{gid}-a", party_type="OTHER", pending_step="SHOW_CAUSE_REPLY", pending_since=issued,
                        pending_action=f"Show-cause notice issued {fmt_date(issued)}; reply due {fmt_date(due)}")
                if kind == "sc_service":
                    sb = mk("PGRC", self.channel("PGRC", allow_cp=age <= 19), "SERVICE_MATTER", inst, pg_rec,
                            "UNDER_PROCESS", "conflict", gid, lang, f"{gid}-b", party_type="FACULTY",
                            pending_step="REFUND_FOLLOWUP", pending_since=self.ago(age - 1),
                            pending_action="Negotiation with institution on faculty salary arrears in progress")
                else:
                    sb = mk("PGRC", self.channel("PGRC", allow_cp=age <= 19), "FACULTY_SHORTAGE", inst, pg_rec,
                            "AWAITING_ATR", "conflict", gid, lang, f"{gid}-b", party_type="FACULTY",
                            pending_step="INSTITUTION_ATR", pending_since=self.ago(age - 1),
                            pending_action="ATR called from institution")
            elif kind == "inspection":
                d1 = self.anchor + timedelta(days=rng.randint(4, 20))
                sa = mk("RB", "BUREAU_FILE", "INFRASTRUCTURE", inst, rb_rec, "UNDER_PROCESS", "conflict", gid, lang,
                        f"{gid}-a", party_type="OTHER", pending_step="INSPECTION", pending_since=self.ago(age - 2),
                        pending_action=f"Inspection scheduled {fmt_date(d1)}")
                sb = mk("RO", "RO_REGISTER", "INFRASTRUCTURE", inst, pg_rec, "UNDER_PROCESS", "conflict", gid, lang,
                        f"{gid}-b", pending_step="INSPECTION", pending_since=self.ago(age - 1),
                        pending_action=f"Inspection scheduled {fmt_date(d1 + timedelta(days=2))}")
            else:
                d1 = self.anchor + timedelta(days=rng.randint(3, 12))
                sa = mk("RB", "BUREAU_FILE", "FACULTY_SHORTAGE", inst, rb_rec, "UNDER_PROCESS", "conflict", gid, lang,
                        f"{gid}-a", party_type="OTHER", pending_step="HEARING", pending_since=self.ago(age - 2),
                        pending_action=f"Hearing scheduled {fmt_date(d1)}")
                sb = mk("PGRC", self.channel("PGRC", allow_cp=age <= 19), "SERVICE_MATTER", inst, pg_rec,
                        "UNDER_PROCESS", "conflict", gid, lang, f"{gid}-b", party_type="FACULTY",
                        pending_step="HEARING", pending_since=self.ago(age - 2),
                        pending_action=f"Hearing scheduled {fmt_date(d1 + timedelta(days=rng.randint(-5, 5)))}")
            for s in (sa, sb):
                s.source_ref = self.new_ref(s.channel, s.bureau, s.ro_code)
            self.pair_log.append({"kind": "conflict", "gid": gid, "a": sa, "b": sb})

        # hard negatives (29 + scenario D): same institution, unrelated categories, <= 30 days apart
        neg_cats = [("SCHOLARSHIP", "INFRASTRUCTURE"), ("RAGGING", "FAKE_APPROVAL_CLAIM"), ("FEE_REFUND", "INFRASTRUCTURE"),
                    ("ADMISSION", "FACULTY_SHORTAGE"), ("RAGGING", "SCHOLARSHIP"), ("CERTIFICATE_WITHHELD", "SCRUTINY_COMMITTEE"),
                    ("SERVICE_MATTER", "SCHOLARSHIP"), ("FEE_REFUND", "FAKE_APPROVAL_CLAIM"), ("INFRASTRUCTURE", "RAGGING"),
                    ("ADMISSION", "SCRUTINY_COMMITTEE"), ("FEE_REFUND", "SERVICE_MATTER"), ("SCHOLARSHIP", "FACULTY_SHORTAGE"),
                    ("CERTIFICATE_WITHHELD", "INFRASTRUCTURE")]
        bureaus_for = {"SCHOLARSHIP": ["PGRC", "RO"], "INFRASTRUCTURE": ["RB", "RO", "PGRC"], "RAGGING": ["PGRC", "RO"],
                       "FAKE_APPROVAL_CLAIM": ["RB", "VIGILANCE", "APPROVAL"], "FEE_REFUND": ["PGRC", "RO"],
                       "ADMISSION": ["PGRC", "RO", "APPROVAL"], "FACULTY_SHORTAGE": ["RB", "PGRC"],
                       "CERTIFICATE_WITHHELD": ["PGRC", "RO"], "SCRUTINY_COMMITTEE": ["RB", "APPROVAL"],
                       "SERVICE_MATTER": ["PGRC", "VIGILANCE"]}
        for n in range(29):
            gid = f"N-{n + 1:03d}"
            inst = take()
            ca, cb = neg_cats[n % len(neg_cats)]
            if rng.random() < 0.5:
                ca, cb = cb, ca
            age = rng.uniform(4, 150)
            gap = rng.uniform(0.5, 28)
            ta, tb = self.ago(age), self.ago(max(0.4, age - gap))
            ba, bb = rng.choice(bureaus_for[ca]), rng.choice(bureaus_for[cb])
            sa = mk(ba, self.channel(ba, allow_cp=age <= 19), ca, inst, ta, self.open_status_for_pair(), "negative",
                    gid, textgen.choose_lang(rng), f"{gid}-a")
            sb = mk(bb, self.channel(bb, allow_cp=(age - gap) <= 19), cb, inst, tb, self.open_status_for_pair(),
                    "negative", gid, textgen.choose_lang(rng), f"{gid}-b")
            for s in (sa, sb):
                s.source_ref = self.new_ref(s.channel, s.bureau, s.ro_code)
            self.pair_log.append({"kind": "negative", "gid": gid, "a": sa, "b": sb})

        for s in self.specs:
            if s.inst_id:
                self.assigned.setdefault(s.inst_id, []).append((s.received_at, s.category))

    # ---- background cases
    def add_background(self) -> None:
        rng = self.rng
        used_b: dict[str, int] = {}
        used_s: dict[str, int] = {}
        for s in self.specs:
            used_b[s.bureau] = used_b.get(s.bureau, 0) + 1
            used_s[s.status or ""] = used_s.get(s.status or "", 0) + 1
        pool: list[str] = []
        for st, q in STATUS_QUOTA.items():
            pool += [st] * max(0, q - used_s.get(st, 0))
        rng.shuffle(pool)
        bg: list[CaseSpec] = []
        for bureau, q in BUREAU_QUOTA.items():
            for _ in range(q - used_b.get(bureau, 0)):
                cat = wchoice(rng, CAT_W[bureau])
                s = CaseSpec(bureau=bureau, channel=self.channel(bureau), category=cat, lang=textgen.choose_lang(rng))
                bg.append(s)
        rng.shuffle(bg)
        # pool may be shorter/longer than bg if pair statuses overshot a quota: pad / trim
        while len(pool) < len(bg):
            pool.append("UNDER_PROCESS")
        for s, st in zip(bg, pool, strict=False):
            s.status = st
        # status-driven channel tweaks
        owner_esc = [s for s in bg if s.status == "ESCALATED"]
        fixed = [s for s in self.specs if s.channel == "CPGRAMS" and s.status in OPEN_ST]
        open_cp = [s for s in bg if s.channel == "CPGRAMS" and s.status in OPEN_ST] + fixed
        target_b = round(0.12 * len(open_cp))
        k_esc = round(0.6 * target_b)
        e0 = sum(1 for s in owner_esc if s.channel == "CPGRAMS")
        for s in owner_esc:
            if e0 >= k_esc:
                break
            if s.channel != "CPGRAMS" and s.bureau != "RO":
                s.channel = "CPGRAMS"
                e0 += 1
        open_cp = [s for s in bg if s.channel == "CPGRAMS" and s.status in OPEN_ST] + fixed
        n_open = len(open_cp)
        target_b, target_a = round(0.12 * n_open), round(0.15 * n_open)
        for s in owner_esc:
            if s.channel == "CPGRAMS":
                s.cp_class = "breached"
            else:
                s.escalated_manual = True
        fixed_b = sum(1 for s in fixed if (self.anchor - s.received_at).days > 21)
        fixed_a = sum(1 for s in fixed if 14.7 <= (self.anchor - s.received_at).total_seconds() / 86400 <= 21)
        have_b = sum(1 for s in bg if s.cp_class == "breached") + fixed_b
        elig = [s for s in bg if s.channel == "CPGRAMS" and s.status in ("UNDER_PROCESS", "AWAITING_ATR", "TRANSFERRED")]
        rng.shuffle(elig)
        for s in elig:
            if have_b >= target_b:
                break
            s.cp_class, have_b = "breached", have_b + 1
        have_a = fixed_a
        for s in elig:
            if have_a >= target_a:
                break
            if s.cp_class is None:
                s.cp_class, have_a = "amber", have_a + 1
        # received_at by status / class
        for s in bg:
            s.received_at = self.ago(self.draw_age(s))
            self.derive_pending(s)
            if s.status == "DISPOSED" or s.status == "CLOSED_NO_ACTION":
                self.draw_disposal(s)
        self.specs.extend(bg)
        self.bg = bg

    def draw_age(self, s: CaseSpec) -> float:
        rng = self.rng
        st = s.status
        if s.channel == "CPGRAMS" and st in ("UNDER_PROCESS", "AWAITING_ATR", "TRANSFERRED", "ESCALATED"):
            cls = s.cp_class or "ontrack"
            if cls == "breached":
                return rng.uniform(22.5, 95)
            if cls == "amber":
                return rng.uniform(14.9, 20.4)
            return rng.uniform(1.0, 14.0)
        if st == "RECEIVED":
            return rng.uniform(0.05, 4) if rng.random() < 0.85 else rng.uniform(5, 20)
        if st == "UNDER_PROCESS":
            return min(268.0, 1.5 + rng.expovariate(1 / 45))
        if st == "AWAITING_ATR":
            return rng.uniform(3, 12) if rng.random() < 0.45 else rng.uniform(12, 60)
        if st == "AWAITING_COMPLAINANT":
            return rng.uniform(5, 40 if s.channel == "CPGRAMS" else 60)
        if st == "TRANSFERRED":
            return rng.uniform(3, 60)
        if st == "ESCALATED":
            return rng.uniform(30, 150)
        if st == "CLOSED_NO_ACTION":
            return rng.uniform(15, 268)
        return rng.uniform(12, 268)  # DISPOSED

    def draw_disposal(self, s: CaseSpec) -> None:
        rng = self.rng
        age = (self.anchor - s.received_at).total_seconds() / 86400
        if s.channel == "CPGRAMS":
            days = rng.uniform(3, 19) if rng.random() < 0.88 else rng.uniform(22, 40)
        else:
            days = rng.uniform(3, 120)
        days = min(days, age * 0.9)
        s.disposed_at = s.received_at + timedelta(days=max(days, 1.0))
        if s.channel == "CPGRAMS" and rng.random() < 0.1:
            s.extra["paused_hist"] = rng.randint(2, 5) * 86400
        if s.category in REFUND_CATS and rng.random() < 0.6:
            s.refund_clock_history = True

    # ---- institution assignment with accidental-relation rejection
    def assign_institutions(self) -> None:
        rng = self.rng
        keyed = {i["id"] for i in self.b.institutions if i["key"] is not None}
        insts = [i for i in self.b.institutions if i["id"] not in keyed]
        weights = {i["id"]: rng.lognormvariate(0, 0.8) for i in insts}
        twin_ids = {i for p in self.b.twin_pairs for i in p}
        for s in self.bg:
            if s.inst_id is not None:
                continue
            for _ in range(60):
                ws = []
                for i in insts:
                    w = weights[i["id"]]
                    if s.bureau == "RO":
                        w *= RO_W.get(i["ro_code"], 1.0)
                    if i["id"] in self.pair_insts:
                        w *= 0.3
                    if i["approval_status"] == "CLOSED":
                        w *= 0.3
                    ws.append(w)
                inst = rng.choices(insts, ws)[0]
                clash = any(family_clash(cat, s.category) and abs((t - s.received_at).days) <= 120
                            for t, cat in self.assigned.get(inst["id"], []))
                if not clash:
                    break
            s.inst_id = inst["id"]
            if s.bureau == "RO":
                s.ro_code = inst["ro_code"]
            self.assigned.setdefault(inst["id"], []).append((s.received_at, s.category))
            _ = twin_ids

    def pick_review_cases(self) -> None:
        """10 NEEDS_REVIEW (4 near-twin) + 4 UNRESOLVED cases with the institution left unresolved."""
        rng = self.rng
        cands = [s for s in self.bg if s.bureau == "PGRC" and s.status == "RECEIVED" and not s.fixed
                 and s.channel in ("CSS", "CPGRAMS", "EMAIL")]
        if len(cands) < 14:
            cands += [s for s in self.bg if s.bureau == "PGRC" and s.status in ("UNDER_PROCESS",)
                      and s.channel in ("CSS", "EMAIL") and s not in cands][: 14 - len(cands)]
        rng.shuffle(cands)
        twin_members = [i for p in self.b.twin_pairs[1:] for i in p]
        for k, s in enumerate(cands[:14]):
            s.needs_review = "NEEDS_REVIEW" if k < 10 else "UNRESOLVED"
            if k < 4:
                s.inst_id = rng.choice(twin_members)
                s.extra["twin"] = True
            s.pid_mode = "missing"
            if k >= 10:
                s.short = True
            if s.status != "RECEIVED":
                s.status = "RECEIVED"  # unresolved cases sit in the queue, not in process
                s.pending_step, s.pending_since, s.pending_action = "NONE", None, None
                s.received_at = self.ago(rng.uniform(0.1, 6))
                s.disposed_at = None
