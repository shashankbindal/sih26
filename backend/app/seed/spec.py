"""Plain dataclass describing one case before it is finalised and written."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CaseSpec:
    bureau: str
    channel: str
    category: str
    inst_id: uuid.UUID | None = None
    received_at: datetime | None = None
    status: str | None = None
    key: str | None = None  # scenario key, stored in is_seed_label.scenario_key
    lang: str = "en"
    subject: str | None = None
    description: str | None = None
    owner_email: str | None = None
    ro_code: str | None = None
    pending_step: str = "NONE"
    pending_since: datetime | None = None
    pending_action: str | None = None
    disposed_at: datetime | None = None
    party_key: str | None = None  # shared identity between cases of one complainant
    party_type: str = "STUDENT"
    source_ref: str | None = None
    inst_text: str | None = None  # institution_text_raw (None = generate noisy text)
    pid_mode: str | None = None  # exact | missing | wrong | None (draw)
    fixed: bool = False  # scenario case: do not redraw dates/status
    groups: dict[str, str] = field(default_factory=dict)  # dup/related/conflict/negative -> id
    first_reply_hours: float | None = None
    cp_class: str | None = None  # CPGRAMS class: breached | amber | ontrack
    slots: dict[str, Any] | None = None
    template_idx: int | None = None
    short: bool = False
    needs_review: str | None = None  # NEEDS_REVIEW | UNRESOLVED (institution left null)
    refund_clock_history: bool = False
    escalated_manual: bool = False
    link_after: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)
