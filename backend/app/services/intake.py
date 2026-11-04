"""Case intake: the POST /cases pipeline, the dry-run
resolver for the live Resolution panel, classify and paste-email parsing (FR-4).

Public (stable contract used by the importer and the seed generator):
    create_case(session, payload: CaseCreate, user, *, source_import_job_id=None) -> CaseCreateResult
Services flush but never commit; the caller commits. Nothing here merges, blocks or cancels:
the engine only suggests, officers decide.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import UTC, datetime
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models.cases import Case, CaseSourceRef, InstitutionMatchCandidate
from app.models.complainants import Complainant
from app.models.enums import (
    Bureau,
    CaseCategory,
    CaseStatus,
    MatchStatus,
    PendingStep,
    Role,
    SourceChannel,
)
from app.models.institutions import Institution
from app.models.users import User
from app.schemas.cases import CaseRef
from app.schemas.intake import (
    CaseCreate,
    CaseCreateResult,
    CategorySuggestionOut,
    ClassifyResult,
    ComplainantIn,
    CreatedLink,
    DetectedFields,
    OtherCaseBrief,
    ParseEmailResult,
    ResolutionCandidate,
    ResolutionOut,
    ResolutionSelected,
    ResolveRequest,
    ResolveResult,
    ResultClock,
    UnrelatedCheck,
)
from app.services import case_views, notifications, passport
from app.services import clocks as clocks_svc
from app.services.caselink import QueryRecord, Resolution, resolve_institution
from app.services.caselink_runtime import get_index, load_thresholds
from app.services.classify import classify
from app.services.links import detect_and_persist
from app.services.normalise import (
    detect_language,
    extract_permanent_id,
    mask_pii,
    normalise_name,
    normalise_text,
)

log = logging.getLogger("loksutra")

__all__ = ["CaseCreate", "CaseCreateResult", "create_case", "party_hash"]

OFFICER_ROLE_BY_BUREAU: dict[Bureau, Role] = {
    Bureau.PGRC: Role.PGRC_OFFICER,
    Bureau.RB: Role.RB_OFFICER,
    Bureau.APPROVAL: Role.APPROVAL_OFFICER,
    Bureau.VIGILANCE: Role.VIGILANCE_OFFICER,
    Bureau.RO: Role.RO_OFFICER,
}


# ====================================================================== small helpers
def party_hash(email: str | None, phone: str | None) -> str | None:
    """sha256(lower(email)|digits(phone)); same formula as the seed generator. None if no contact."""
    if not email and not phone:
        return None
    digits = "".join(c for c in (phone or "") if c.isdigit())
    return hashlib.sha256(f"{(email or '').lower().strip()}|{digits}".encode()).hexdigest()


def _email_domain(email: str | None) -> str | None:
    if email and "@" in email:
        return email.rsplit("@", 1)[1].lower().strip() or None
    return None


def _clean(s: str | None) -> str | None:
    s = (s or "").strip()
    return s or None


def _json_safe(value: Any) -> Any:
    import json

    return json.loads(json.dumps(value, default=str))


def resolution_out(res: Resolution) -> ResolutionOut:
    selected = None
    if res.selected is not None:
        s = res.selected
        selected = ResolutionSelected(
            institution_id=s.institution.id,  # type: ignore[arg-type]
            name=s.institution.name,
            permanent_id=s.institution.permanent_id or "",
            score=round(float(s.score), 3),
            district=s.institution.district,
            state=s.institution.state,
        )
    return ResolutionOut(
        status=MatchStatus(res.status),
        selected=selected,
        candidates=[
            ResolutionCandidate(
                institution_id=c.institution.id,  # type: ignore[arg-type]
                name=c.institution.name,
                permanent_id=c.institution.permanent_id or "",
                district=c.institution.district,
                state=c.institution.state,
                rank=c.rank,
                score=round(float(c.score), 3),
                matched_via=c.matched_via,
                reasons=list(c.reasons),
                features=_json_safe(c.features),
            )
            for c in res.candidates
        ],
        normalised_query=res.normalised_query.text,
        extracted={k: v for k, v in (res.extracted or {}).items()},
    )


def category_out(subject: str, description: str) -> CategorySuggestionOut:
    s = classify(subject, description)
    return CategorySuggestionOut(
        category=CaseCategory(s.category), confidence=round(float(s.confidence), 3), keywords=list(s.keywords)
    )


def brief(case: Case) -> OtherCaseBrief:
    return OtherCaseBrief(
        id=case.id, display_id=case.display_id, owner_bureau=case.owner_bureau, subject=case.subject,
        status=case.status,
    )


# ====================================================================== owner assignment
def pick_owner_officer(
    session: Session, bureau: Bureau, ro_code: str | None, creator: User | None
) -> User | None:
    """The creator when they are an officer of the owner bureau; otherwise the least-loaded active
    officer of that bureau (RO: of that region), ties by name; bureau head as last resort."""
    role = OFFICER_ROLE_BY_BUREAU.get(bureau)
    if (
        creator is not None
        and role is not None
        and creator.role == role
        and creator.bureau == bureau
        and (bureau != Bureau.RO or not ro_code or creator.ro_code == ro_code)
    ):
        return creator
    if role is None:
        return None
    q = select(User).where(User.role == role, User.bureau == bureau, User.is_active.is_(True))
    if bureau == Bureau.RO and ro_code:
        q = q.where(User.ro_code == ro_code)
    officers = list(session.scalars(q.order_by(User.name)))
    if officers:
        loads = dict(
            session.execute(
                select(Case.owner_officer_id, func.count(Case.id))
                .where(
                    Case.owner_officer_id.in_([o.id for o in officers]),
                    Case.status.notin_((CaseStatus.DISPOSED, CaseStatus.CLOSED_NO_ACTION)),
                )
                .group_by(Case.owner_officer_id)
            ).all()
        )
        return min(officers, key=lambda o: (loads.get(o.id, 0), o.name))
    heads = notifications.bureau_heads(session, bureau)
    return heads[0] if heads else None


# ====================================================================== resolution
def _resolve(session: Session, institution_text: str | None, permanent_id_raw: str | None, text: str,
             email: str | None) -> Resolution:
    query = QueryRecord(
        institution_text=institution_text or "",
        permanent_id_raw=permanent_id_raw,
        text=text,
        email_domain=_email_domain(email),
    )
    return resolve_institution(query, get_index(session), thresholds=load_thresholds(session))


def resolve_dry_run(session: Session, req: ResolveRequest) -> ResolveResult:
    """POST /intake/resolve: nothing is stored."""
    subject, description = req.subject or "", req.description or ""
    res = _resolve(
        session, _clean(req.institution_text_raw), _clean(req.permanent_id_raw),
        f"{subject}\n{description}".strip(), req.complainant_email,
    )
    return ResolveResult(
        resolution=resolution_out(res),
        category_suggestion=category_out(subject, description),
        language=detect_language(f"{subject} {description}"),
        normalised_text=normalise_name(req.institution_text_raw).text if req.institution_text_raw else "",
    )


def classify_text(subject: str, description: str) -> ClassifyResult:
    s = category_out(subject, description)
    return ClassifyResult(category=s.category, confidence=s.confidence, keywords=s.keywords)


def persist_candidates(session: Session, case: Case, res: Resolution) -> None:
    """Top-5 candidates (rank, score, features, reasons). Rank 1 carries the resolution status."""
    session.query(InstitutionMatchCandidate).filter(InstitutionMatchCandidate.case_id == case.id).delete()
    for c in res.candidates[:5]:
        if c.rank == 1:
            status = MatchStatus(res.status)
        else:
            status = MatchStatus.NEEDS_REVIEW if res.status == "NEEDS_REVIEW" else MatchStatus.UNRESOLVED
        session.add(
            InstitutionMatchCandidate(
                case_id=case.id,
                institution_id=c.institution.id,
                rank=c.rank,
                score=round(float(c.score), 3),
                features=_json_safe(c.features),
                reasons=list(c.reasons),
                status=status,
            )
        )
    session.flush()


# ====================================================================== POST /cases
def create_case(
    session: Session,
    payload: CaseCreate,
    user: User,
    *,
    source_import_job_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> CaseCreateResult:
    """Validate -> normalise -> classify -> resolve institution -> relationships -> clocks ->
    Passport -> notifications, and return everything in one result. Caller commits."""
    now = now or datetime.now(UTC)
    received_at = payload.received_at or now
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=UTC)
    subject = payload.subject.strip()
    description = (payload.description or "").strip()
    comp_in = payload.complainant
    owner_bureau = payload.owner_bureau
    if owner_bureau is None:
        owner_bureau = user.bureau if user.bureau in OFFICER_ROLE_BY_BUREAU else Bureau.PGRC
    if owner_bureau == Bureau.ADMIN:
        raise ApiError(422, "VALIDATION_ERROR", "owner_bureau must be an operating bureau")

    # ---- normalise + classify (PII-masked copy feeds similarity and other bureaus) ----------
    masked = mask_pii(description, known_names=[comp_in.name] if comp_in.name else [])
    description_norm = normalise_text(masked)
    language = detect_language(f"{subject} {description}")
    suggestion = category_out(subject, description)
    category = payload.category or suggestion.category

    # ---- stage A ---------------------------------------------------------------------------
    institution: Institution | None = None
    match_status = MatchStatus.UNRESOLVED
    match_score: float | None = None
    res: Resolution | None = None
    if payload.institution_id is not None:
        institution = session.get(Institution, payload.institution_id)
        if institution is None:
            raise ApiError(404, "NOT_FOUND", "Institution not found")
        match_status = MatchStatus.CONFIRMED
    else:
        res = _resolve(
            session, _clean(payload.institution_text_raw), _clean(payload.permanent_id_raw),
            f"{subject}\n{description}".strip(), comp_in.email,
        )
        match_status = MatchStatus(res.status)
        match_score = round(float(res.score), 3) if res.selected is not None else 0.0
        if res.status in ("EXACT", "AUTO_SUGGESTED") and res.selected is not None:
            institution = session.get(Institution, res.selected.institution_id)

    owner_ro = _clean(payload.owner_ro_code)
    if owner_bureau == Bureau.RO and not owner_ro:
        owner_ro = user.ro_code or (institution.ro_code if institution is not None else None)
    owner = pick_owner_officer(session, owner_bureau, owner_ro, user)

    # ---- persist case + complainant -------------------------------------------------------
    complainant = Complainant(
        name=_clean(comp_in.name), email=_clean(comp_in.email), phone=_clean(comp_in.phone),
        party_hash=party_hash(_clean(comp_in.email), _clean(comp_in.phone)), party_type=comp_in.party_type,
    )
    session.add(complainant)
    session.flush()
    case = Case(
        source_channel=payload.source_channel,
        source_ref=_clean(payload.source_ref),
        received_at=received_at,
        institution_text_raw=_clean(payload.institution_text_raw),
        permanent_id_raw=_clean(payload.permanent_id_raw),
        institution_id=institution.id if institution else None,
        institution_match_status=match_status,
        institution_match_score=match_score,
        complainant_id=complainant.id,
        category=category,
        category_suggested=suggestion.category,
        subject=subject,
        description=description or None,
        description_norm=description_norm,
        language=language,
        owner_bureau=owner_bureau,
        owner_ro_code=owner_ro,
        owner_officer_id=owner.id if owner else None,
        status=CaseStatus.RECEIVED,
        pending_step=PendingStep.NONE,
    )
    session.add(case)
    session.flush()
    case.institution = institution
    if case.source_ref:
        taken = session.get(CaseSourceRef, (case.source_channel, case.source_ref))
        if taken is None:
            session.add(CaseSourceRef(channel=case.source_channel, ref=case.source_ref, case_id=case.id))
            session.flush()
    if res is not None:
        persist_candidates(session, case, res)

    # ---- Passport: RECEIVED, ASSIGNED ------------------------------------------------------
    passport.append_entry(
        session, event="RECEIVED", case_id=case.id, institution_id=case.institution_id, actor=user,
        payload={
            "channel": case.source_channel.value,
            "source_ref": case.source_ref,
            "category": category.value,
            "institution_match": match_status.value,
            "institution_match_score": match_score,
            "language": language,
            **({"import_job_id": str(source_import_job_id)} if source_import_job_id else {}),
        },
    )
    passport.append_entry(
        session, event="ASSIGNED", case_id=case.id, institution_id=case.institution_id, actor=user,
        payload={
            "to_bureau": owner_bureau.value,
            "to_officer": owner.name if owner else None,
            "to_ro_code": owner_ro,
        },
    )

    # ---- stage B + notifications ------------------------------------------------------------
    outcome = detect_and_persist(session, case, user, now)
    if match_status == MatchStatus.NEEDS_REVIEW:
        creating = owner_bureau if user.bureau == Bureau.ADMIN else user.bureau
        top = res.selected if res and res.selected else None
        notifications.notify(
            session,
            kind="REVIEW_QUEUE",
            title=f"Institution match needs review: {case.display_id}",
            body=(top.reasons[0] if top and top.reasons else "Institution match needs an officer's confirmation."),
            bureau=creating,
            link_path="/review",
            case_id=case.id,
        )

    # ---- clocks -----------------------------------------------------------------------------
    clocks_svc.start_clocks_for_case(session, case, now=now)
    session.flush()

    detail = case_views.build_case_detail(session, case, user, now)
    links = [
        CreatedLink(
            link_id=link.id,
            other_case=brief(other),
            relation=link.relation,
            status=link.status,
            score=float(link.score),
            reasons=list(link.reasons or []),
            suggested_next_action=s.suggested_next_action,
            lead_bureau=Bureau(s.lead_bureau) if s.lead_bureau else None,
        )
        for link, other, s in outcome.links
    ]
    unrelated = [
        UnrelatedCheck(other_case=brief(other), score=float(s.score), reasons=list(s.reasons))
        for other, s in outcome.unrelated
    ]
    if res is not None:
        resolution = resolution_out(res)
    else:
        resolution = ResolutionOut(
            status=MatchStatus.CONFIRMED,
            selected=ResolutionSelected(
                institution_id=institution.id, name=institution.name,  # type: ignore[union-attr]
                permanent_id=institution.permanent_id, score=1.0,  # type: ignore[union-attr]
                district=institution.district, state=institution.state,  # type: ignore[union-attr]
            ),
            candidates=[],
            normalised_query=normalise_name(payload.institution_text_raw).text if payload.institution_text_raw else "",
        )
    return CaseCreateResult(
        case=detail,
        resolution=resolution,
        category_suggestion=suggestion,
        links=links,
        unrelated=unrelated,
        clocks=[ResultClock(**c.model_dump()) for c in detail.clocks],
    )


def other_case_ref(case: Case) -> CaseRef:
    return CaseRef(
        id=case.id, display_id=case.display_id, subject=case.subject, owner_bureau=case.owner_bureau,
        status=case.status,
    )


# ====================================================================== paste email (FR-4)
_HEADER_RE = re.compile(r"^(subject|from|date|to|cc|reply-to|message-id)\s*:\s*(.*)$", re.IGNORECASE)
_CPGRAMS_RE = re.compile(r"\b[A-Z]{3,8}/[A-Z]/\d{4}/\d{5,8}\b")
_CSS_RE = re.compile(r"\bCSS-\d{4}-\d{3,8}\b", re.IGNORECASE)
_LABELLED_INST_RE = re.compile(
    r"^\s*(?:name of (?:the )?)?(?:institution|institute|college)(?: name)?\s*[:\-]\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_CAP = r"[A-Z][\w&'’-]*\.?"
_INST_EN_RE = re.compile(
    rf"((?:{_CAP}\s+){{1,6}}(?:College|Collage|Institute|University|Polytechnic|Academy|School)\b"
    rf"(?:\s+of\s+(?:(?:[A-Z&][\w&'’-]*|and)\s*){{1,7}})?"
    rf"(?:\s*,?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)?)"
)
_INST_LOWER_RE = re.compile(
    r"\b((?:[\w&'-]+\s+){1,3}(?:college|collage|clg|institute|instt|university|polytechnic)"
    r"(?:\s+of\s+[\w&]+(?:\s+and\s+[\w&]+)?)?(?:\s+[a-z]+)?)\b",
    re.IGNORECASE,
)
_DEV_KEYWORDS = (
    "कॉलेज", "महाविद्यालय", "संस्थान", "विश्वविद्यालय", "इंजीनियरिंग", "पॉलिटेक्निक", "टेक्नोलॉजी",
    "प्रौद्योगिकी", "फार्मेसी", "अभियांत्रिकी",
)
_DEV_RE = re.compile(r"[ऀ-ॿ]")
_LEAD_STOP = {
    "regarding", "complaint", "against", "about", "re", "dear", "from", "sir", "madam", "subject", "fee",
    "fees", "refund", "not", "the", "at", "of", "to", "in", "for", "on", "i", "my", "we", "our", "sub",
    "attn", "respected", "kindly", "request", "please", "hello", "hi", "regards", "thanks", "thank",
}
_TRAIL_STOP = {"i", "and", "or", "the", "is", "was", "has", "have", "for", "that", "who", "which"}


def _dev_institution(text: str) -> str | None:
    for raw_line in re.split(r"[\n।]", text):
        tokens = raw_line.split()
        idx = [i for i, t in enumerate(tokens) if any(k in t for k in _DEV_KEYWORDS)]
        if not idx:
            continue
        first, last = idx[0], idx[-1]
        start = first
        while start > 0 and start > first - 4 and _DEV_RE.search(tokens[start - 1]) and not re.search(
            r"[,;:.।?!]$", tokens[start - 1]
        ):
            start -= 1
        end = last + 1
        if not re.search(r"[,;:.।?!]$", tokens[last]) and end < len(tokens) and _DEV_RE.search(tokens[end]):
            end += 1
        phrase = " ".join(tokens[start:end]).strip(" ,;:.।")
        if phrase:
            return phrase
    return None


def _trim(phrase: str) -> str | None:
    words = phrase.strip().strip(",.;:").split()
    while words and words[0].lower().strip(".,") in _LEAD_STOP:
        words.pop(0)
    while words and words[-1].lower().strip(".,") in _TRAIL_STOP:
        words.pop()
    out = " ".join(words).strip(",.;: ")
    return out or None


def extract_institution_mention(subject: str | None, body: str) -> str | None:
    text = f"{subject or ''}\n{body}"
    m = _LABELLED_INST_RE.search(text)
    if m:
        return _trim(m.group(1))
    if _DEV_RE.search(text):
        found = _dev_institution(text)
        if found:
            return found
    for src in (body, subject or ""):
        for m in _INST_EN_RE.finditer(src):
            got = _trim(m.group(1))
            if got and len(got.split()) >= 2:
                return got
    for src in (body, subject or ""):
        m = _INST_LOWER_RE.search(src)
        if m:
            got = _trim(m.group(1))
            if got:
                return got
    return None


def parse_email(raw_text: str, now: datetime | None = None) -> ParseEmailResult:
    """Extract subject, sender, institution mention, Permanent ID and CPGRAMS/CSS refs from pasted
    email text and return a prefilled CaseCreate. Nothing is stored or resolved here."""
    now = now or datetime.now(UTC)
    lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    headers: dict[str, str] = {}
    i = 0
    while i < len(lines) and _HEADER_RE.match(lines[i].strip()):
        m = _HEADER_RE.match(lines[i].strip())
        headers[m.group(1).lower()] = m.group(2).strip()  # type: ignore[union-attr]
        i += 1
    if headers and i < len(lines) and not lines[i].strip():
        i += 1
    body = "\n".join(lines[i:] if headers else lines).strip()
    subject = _clean(headers.get("subject"))
    if subject:
        subject = re.sub(r"^(re|fwd?)\s*:\s*", "", subject, flags=re.IGNORECASE).strip() or subject
    elif body:
        first = next((ln.strip() for ln in body.split("\n") if ln.strip()), "")
        subject = first[:120] if first else None
    sender_name, sender_email = parseaddr(headers.get("from", ""))
    sender_name, sender_email = _clean(sender_name), _clean(sender_email)
    received_at: datetime | None = None
    if headers.get("date"):
        try:
            received_at = parsedate_to_datetime(headers["date"])
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            received_at = None
    haystack = f"{subject or ''}\n{body}"
    pid = extract_permanent_id(haystack)
    cpgrams = list(dict.fromkeys(_CPGRAMS_RE.findall(haystack)))
    css = list(dict.fromkeys(m.upper() for m in _CSS_RE.findall(haystack)))
    mention = extract_institution_mention(subject, body)
    language = detect_language(haystack)
    suggestion = category_out(subject or "", body)
    prefill = CaseCreate(
        source_channel=SourceChannel.EMAIL,
        source_ref=None,
        received_at=received_at or now,
        institution_text_raw=mention,
        permanent_id_raw=pid,
        complainant=ComplainantIn(
            name=sender_name, email=sender_email, party_type="OTHER" if (sender_name or sender_email) else "ANONYMOUS"
        ),
        category=None,
        subject=(subject or "Complaint received by email")[:500],
        description=body or None,
        owner_bureau=None,
        owner_ro_code=None,
    )
    return ParseEmailResult(
        prefill=prefill,
        detected=DetectedFields(
            subject=subject, sender_name=sender_name, sender_email=sender_email,
            institution_mention=mention, permanent_id=pid, cpgrams_refs=cpgrams, css_refs=css, language=language,
        ),
        category_suggestion=suggestion,
    )
