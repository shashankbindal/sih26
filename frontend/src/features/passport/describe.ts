import {
  BUREAU_LABEL,
  CASE_STATUS_LABEL,
  CATEGORY_LABEL,
  CHANNEL_LABEL,
  CLOCK_NAME,
  INST_ACTION_LABEL,
  PENDING_STEP_LABEL,
  type Bureau,
  type CaseCategory,
  type CaseStatus,
  type ClockType,
  type InstActionType,
  type PendingStep,
  type SourceChannel,
} from '@/lib/constants';
import { RELATION_LABEL } from '@/components/domain/RelationBadge';
import type { RelationType } from '@/lib/constants';

// Turns a Passport entry (event code + payload) into officer-readable text. No UUIDs, no raw enum names.

type Payload = Record<string, unknown>;
export interface Described {
  label: string;
  summary: string | null;
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const isUuid = (v: unknown): boolean => typeof v === 'string' && UUID.test(v);

const humanise = (s: string): string => {
  const t = s.replace(/_/g, ' ').toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
};
const lower = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);

const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() && !isUuid(v) ? v.trim() : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

const bureau = (v: unknown): string | null => {
  const s = str(v);
  return s ? (BUREAU_LABEL[s as Bureau] ?? humanise(s)) : null;
};
const status = (v: unknown): string | null => {
  const s = str(v);
  return s ? (CASE_STATUS_LABEL[s as CaseStatus] ?? humanise(s)) : null;
};
const step = (v: unknown): string | null => {
  const s = str(v);
  return s ? (PENDING_STEP_LABEL[s as PendingStep] ?? humanise(s)) : null;
};
const category = (v: unknown): string | null => {
  const s = str(v);
  return s ? (CATEGORY_LABEL[s as CaseCategory] ?? humanise(s)) : null;
};
const action = (v: unknown): string | null => {
  const s = str(v);
  return s ? (INST_ACTION_LABEL[s as InstActionType] ?? humanise(s)) : null;
};

/** {from, to} change object, or null. */
function change(v: unknown): { from: unknown; to: unknown } | null {
  if (v && typeof v === 'object' && !Array.isArray(v) && 'to' in v) return v as { from: unknown; to: unknown };
  return null;
}

const sentence = (parts: Array<string | null | undefined | false>): string | null => {
  const out = parts.filter((p): p is string => !!p).map((p) => p.trim()).filter(Boolean);
  return out.length ? out.join(' ') : null;
};
const stop = (s: string) => (/[.!?]$/.test(s) ? s : `${s}.`);
const withRemark = (base: string | null, remark: unknown, label = 'Remark'): string | null => {
  const r = str(remark);
  return sentence([base ? stop(base) : null, r ? `${label}: ${stop(r)}` : null]);
};

const EVENT_LABEL: Record<string, string> = {
  RECEIVED: 'Received',
  ASSIGNED: 'Assigned',
  STATUS_CHANGED: 'Status changed',
  REOPENED: 'Reopened',
  REMARK: 'Remark added',
  ATR_RECEIVED: 'ATR received',
  TRANSFERRED: 'Transferred',
  DISPOSED: 'Disposed',
  ESCALATED: 'Escalated',
  LINK_SUGGESTED: 'Link suggested',
  LINK_CONFIRMED: 'Link confirmed',
  LINK_REJECTED: 'Link rejected',
  LINK_DEFERRED: 'Link deferred',
  LINK_SUPERSEDED: 'Link superseded',
  LINK_REVERTED: 'Link reverted',
  INSTITUTION_CONFIRMED: 'Institution confirmed',
  INSTITUTION_REJECTED: 'Institution match rejected',
  PII_REVEALED: 'Complainant details revealed',
  PREACTION_CHECK_SHOWN: 'Pre-Action Check shown',
  PREACTION_ACKNOWLEDGED: 'Pre-Action Check acknowledged',
  CLEARANCE_REQUESTED: 'Clearance requested',
  CLEARANCE_RESPONDED: 'Clearance responded',
};

const LINK_VERB: Record<string, string> = {
  LINK_SUGGESTED: 'Suggested',
  LINK_CONFIRMED: 'Confirmed',
  LINK_REJECTED: 'Rejected',
  LINK_DEFERRED: 'Deferred',
  LINK_SUPERSEDED: 'Superseded',
  LINK_REVERTED: 'Reverted',
};

const RESPONSE_LABEL: Record<string, string> = {
  CLEARED: 'Cleared',
  NOT_CLEARED: 'Not cleared',
  CLEARED_WITH_REMARKS: 'Cleared with remarks',
};

function describeChanges(p: Payload): string[] {
  const out: string[] = [];
  // Flat shape written by older records: {from, to, pending_step}.
  if (str(p.to) && !change(p.status)) {
    out.push(`Status changed${status(p.from) ? ` from ${status(p.from)}` : ''} to ${status(p.to)}.`);
    if (str(p.pending_step)) out.push(`Pending step: ${step(p.pending_step)}.`);
  }
  const s = change(p.status);
  if (s) out.push(`Status changed${status(s.from) ? ` from ${status(s.from)}` : ''} to ${status(s.to)}.`);
  const ps = change(p.pending_step);
  if (ps) out.push(`Pending step changed${step(ps.from) ? ` from ${step(ps.from)}` : ''} to ${step(ps.to)}.`);
  const c = change(p.category);
  if (c) out.push(`Category changed${category(c.from) ? ` from ${category(c.from)}` : ''} to ${category(c.to)}.`);
  const pa = change(p.pending_action);
  if (pa) out.push(str(pa.to) ? `Pending action set to "${str(pa.to)}".` : 'Pending action cleared.');
  return out;
}

/** Fallback for unknown events: key: value pairs, skipping ids and nested objects. */
function generic(p: Payload): string | null {
  const bits: string[] = [];
  for (const [k, v] of Object.entries(p)) {
    if (k === 'remark' || k === 'reason' || k.endsWith('_id') || k === 'id') continue;
    if (typeof v === 'string' && !isUuid(v) && v.length <= 80) bits.push(`${humanise(k)}: ${/^[A-Z0-9_]+$/.test(v) ? humanise(v) : v}`);
    else if (typeof v === 'number' || typeof v === 'boolean') bits.push(`${humanise(k)}: ${String(v)}`);
    else {
      const ch = change(v);
      if (ch && (str(ch.to) || str(ch.from))) bits.push(`${humanise(k)}: ${str(ch.from) ? `${humanise(String(ch.from))} to ` : ''}${humanise(String(ch.to ?? ''))}`);
    }
  }
  const base = bits.length ? `${bits.slice(0, 4).join('; ')}.` : null;
  return withRemark(base, p.remark ?? p.reason);
}

export function describeEvent(event: string, payload: Payload | null | undefined): Described {
  const p: Payload = payload ?? {};
  const label = EVENT_LABEL[event] ?? humanise(event);

  switch (event) {
    case 'RECEIVED': {
      const ch = str(p.channel);
      const ref = str(p.source_ref);
      const cat = category(p.category);
      return {
        label,
        summary: sentence([
          `Logged via ${ch ? (CHANNEL_LABEL[ch as SourceChannel] ?? humanise(ch)) : 'a source channel'}${ref ? `, reference ${ref}` : ''}.`,
          cat && `Category: ${cat}.`,
        ]),
      };
    }
    case 'ASSIGNED': {
      const to = str(p.to_officer) ?? str(p.to);
      const from = str(p.from) ?? str(p.from_officer);
      const b = bureau(p.to_bureau);
      const ro = str(p.to_ro_code) ?? str(p.owner_ro_code);
      const where = [b, ro && `RO ${ro}`].filter(Boolean).join(' · ');
      const who = to ? `${to}${where ? ` (${where})` : ''}` : where || 'the owner bureau';
      return { label: from ? 'Reassigned' : label, summary: from ? `Reassigned from ${from} to ${who}.` : `Assigned to ${who}.` };
    }
    case 'STATUS_CHANGED':
    case 'REOPENED': {
      const lines = describeChanges(p);
      const base = lines.length ? lines.join(' ') : event === 'REOPENED' ? 'Case reopened.' : null;
      return { label, summary: withRemark(base, p.remark) ?? generic(p) };
    }
    case 'REMARK':
      return { label, summary: str(p.remark) ? stop(str(p.remark) as string) : null };
    case 'ATR_RECEIVED': {
      const from = step(p.pending_step_from);
      const lines = describeChanges(p);
      return {
        label,
        summary: withRemark(sentence(['Action Taken Report received.', from && from !== 'None' ? `Pending step "${from}" cleared.` : null, ...lines]), p.remark),
      };
    }
    case 'TRANSFERRED': {
      const from = bureau(p.from);
      const to = bureau(p.to);
      const officer = str(p.to_officer);
      const ro = str(p.to_ro_code);
      return {
        label,
        summary: withRemark(
          `Transferred${from ? ` from ${from}` : ''} to ${to ?? 'another bureau'}${ro ? ` (RO ${ro})` : ''}${officer ? `, assigned to ${officer}` : ''}`,
          p.remark,
        ),
      };
    }
    case 'DISPOSED': {
      const s = change(p.status);
      return { label, summary: withRemark(s && status(s.from) ? `Disposed; previous status ${status(s.from)}` : 'Case disposed', p.remark, 'Disposal remark') };
    }
    case 'ESCALATED': {
      if (!str(p.clock)) {
        const to = str(p.to);
        return { label, summary: withRemark(`Escalated${to ? ` to ${humanise(to).toLowerCase()}` : ''}`, p.remark) };
      }
      const clock = str(p.clock);
      const name = clock ? (CLOCK_NAME[clock as ClockType] ?? humanise(clock)) : 'A policy clock';
      const by = str(p.overdue_by);
      const to = status(p.status_to);
      return { label, summary: sentence([`${name} is overdue${by ? ` by ${by}` : ''}.`, to && `Case status set to ${to}.`]) };
    }
    case 'LINK_SUGGESTED':
    case 'LINK_CONFIRMED':
    case 'LINK_REJECTED':
    case 'LINK_DEFERRED':
    case 'LINK_SUPERSEDED':
    case 'LINK_REVERTED': {
      const other = str(p.other_case) ?? str(p.other_display_id);
      const rel = str(p.relation);
      const relLabel = rel ? RELATION_LABEL[rel as RelationType] : null;
      const ob = bureau(p.other_bureau);
      const score = num(p.score);
      const details = [ob, relLabel, score !== null ? `score ${score.toFixed(2)}` : null].filter(Boolean).join(' · ');
      const base = `${LINK_VERB[event]} link with ${other ?? 'another case'}${details ? ` (${details})` : ''}`;
      return { label, summary: withRemark(base, p.reason ?? p.remark, 'Reason') };
    }
    case 'INSTITUTION_CONFIRMED': {
      const name = str(p.institution);
      const pid = str(p.permanent_id);
      const alias = str(p.alias_added);
      return {
        label,
        summary: withRemark(
          sentence([
            `Institution confirmed${name ? ` as ${name}` : ''}${pid ? ` (${pid})` : ''}.`,
            p.created_new_institution === true ? 'A new institution record was created.' : null,
            alias ? `Alias added: ${alias}.` : null,
          ]),
          p.reason,
          'Reason',
        ),
      };
    }
    case 'INSTITUTION_REJECTED':
      return { label, summary: withRemark('Suggested institution match rejected', p.reason, 'Reason') };
    case 'PII_REVEALED':
      return { label, summary: withRemark('Complainant name, email and phone were revealed to the actor', p.reason, 'Reason') };
    case 'PREACTION_CHECK_SHOWN': {
      const a = action(p.action_type);
      const n = num(p.open_matters);
      const by = p.by_bureau && typeof p.by_bureau === 'object' ? Object.entries(p.by_bureau as Record<string, unknown>).map(([b, c]) => `${bureau(b)} ${String(c)}`).join(', ') : null;
      const ov = num(p.overdue);
      return {
        label,
        summary: sentence([
          `Pre-Action Check for ${a ? lower(a) : 'an institution action'} shown with ${n ?? 0} open ${n === 1 ? 'matter' : 'matters'}${by ? ` (${by})` : ''}.`,
          ov ? `${ov} overdue.` : null,
        ]),
      };
    }
    case 'PREACTION_ACKNOWLEDGED': {
      const a = action(p.action_type);
      const sum = str(p.summary);
      const st = str(p.status);
      const verb = st === 'PROCEEDED' ? 'Proceeded' : st === 'ON_HOLD' ? 'Placed on hold' : null;
      const base = sum ? `${sum}${a ? ` for ${lower(a)}` : ''}` : verb ? `${verb}${a ? ` with ${lower(a)}` : ''}` : (a ?? null);
      return { label, summary: withRemark(base, p.remark) };
    }
    case 'CLEARANCE_REQUESTED': {
      const to = bureau(p.target_bureau);
      const a = action(p.action_type);
      const n = num(p.step_order);
      return {
        label,
        summary: withRemark(`Clearance requested from ${to ?? 'a bureau'}${a ? ` for ${lower(a)}` : ''}${n !== null ? ` (step ${n})` : ''}`, p.remark),
      };
    }
    case 'CLEARANCE_RESPONDED': {
      const from = bureau(p.target_bureau);
      const r = str(p.response);
      return {
        label,
        summary: withRemark(`${from ?? 'The bureau'} responded: ${r ? (RESPONSE_LABEL[r] ?? humanise(r)).toLowerCase() : 'no response recorded'}`, p.remarks ?? p.remark, 'Remarks'),
      };
    }
    default:
      return { label, summary: generic(p) };
  }
}
