import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Schemas } from '@/api/types';
import { BureauTag, RelationBadge, StatusTag } from '@/components/domain';
import { EmptyState } from '@/components/ui';
import {
  BUREAUS,
  BUREAU_COLOR_VAR,
  CATEGORY_LABEL,
  OPEN_STATUSES,
  PENDING_STEP_LABEL,
  type Bureau,
  type CaseCategory,
  type CaseStatus,
  type PendingStep,
  type RelationType,
} from '@/lib/constants';
import { ageShort } from '@/lib/format';
import { cx } from '@/lib/cx';
import { ClockPills } from '../cases/shared';

type TimelineItem = Schemas['TimelineItem'];
type InstitutionLink = Schemas['InstitutionLinkOut'];

const LANES: Bureau[] = BUREAUS.filter((b) => b !== 'ADMIN');
const STRENGTH: Record<string, number> = { CONFLICTING: 3, RELATED: 2, DUPLICATE: 1 };
const ACTIVE = new Set(['SUGGESTED', 'CONFIRMED', 'DEFERRED']);

const KIND_COLOR: Record<string, string> = {
  CONFLICTING: 'var(--red)',
  RELATED: 'var(--saffron)',
  DUPLICATE: 'var(--info)',
};

interface Group {
  ids: Set<string>;
}

/** Active, non-UNRELATED links between open cases, grouped into connected sets (union-find). */
function buildLinkModel(openIds: Set<string>, links: InstitutionLink[]) {
  const active = links.filter((l) => l.relation !== 'UNRELATED' && ACTIVE.has(l.status) && openIds.has(l.case_a.id) && openIds.has(l.case_b.id));
  const parent = new Map<string, string>();
  const find = (x: string): string => {
    let r = x;
    while (parent.get(r) !== r) r = parent.get(r) ?? r;
    parent.set(x, r);
    return r;
  };
  for (const l of active) {
    for (const id of [l.case_a.id, l.case_b.id]) if (!parent.has(id)) parent.set(id, id);
    parent.set(find(l.case_a.id), find(l.case_b.id));
  }
  const groups = new Map<string, Group>();
  for (const id of parent.keys()) {
    const r = find(id);
    if (!groups.has(r)) groups.set(r, { ids: new Set() });
    groups.get(r)!.ids.add(id);
  }
  const groupOf = new Map<string, Group>();
  groups.forEach((g) => g.ids.forEach((id) => groupOf.set(id, g)));
  const kind = new Map<string, string>();
  for (const l of active) {
    for (const id of [l.case_a.id, l.case_b.id]) {
      if ((STRENGTH[l.relation] ?? 0) > (STRENGTH[kind.get(id) ?? ''] ?? 0)) kind.set(id, l.relation);
    }
  }
  return { active, groupOf, kind };
}

interface Segment {
  key: string;
  d: string;
  color: string;
  dash?: string;
  a: string;
  b: string;
  group?: Group;
}

function CaseCard({
  c,
  kind,
  highlighted,
  unrelatedHint,
  onHover,
  setRef,
  firstInGroup,
}: {
  c: TimelineItem;
  kind?: string;
  highlighted: boolean;
  unrelatedHint: boolean;
  onHover: (id: string | null) => void;
  setRef: (id: string, el: HTMLElement | null) => void;
  /** First card of its link group in this lane: forced into column 1 so its connector is a short stub from the gutter. */
  firstInGroup?: boolean;
}) {
  const linked = kind === 'RELATED' || kind === 'CONFLICTING' || kind === 'DUPLICATE';
  const leftColor = kind ? KIND_COLOR[kind] : 'var(--line)';
  return (
    <Link
      ref={(el) => setRef(c.id, el)}
      to={`/cases/${c.id}`}
      onMouseEnter={() => onHover(c.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(c.id)}
      onBlur={() => onHover(null)}
      aria-label={`${c.display_id}, ${CATEGORY_LABEL[c.category as CaseCategory] ?? c.category}${kind ? ', linked' : ''}`}
      className={cx(
        'focus-ring relative z-10 block min-h-[96px] w-full rounded-sm border border-line px-2.5 py-2 text-ink-900 hover:no-underline',
        highlighted ? (kind === 'CONFLICTING' ? 'bg-red-bg' : kind === 'DUPLICATE' ? 'bg-info-bg' : 'bg-saffron-bg') : 'bg-surface',
      )}
      style={{ gridColumnStart: firstInGroup ? 1 : undefined, borderLeft: `4px solid ${leftColor}`, outline: highlighted ? `1px solid ${kind ? KIND_COLOR[kind] : 'var(--line)'}` : undefined }}
    >
      <div className={cx(unrelatedHint && 'opacity-30')}>
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-xs font-medium tnum text-navy">{c.display_id}</span>
          <StatusTag status={c.status as CaseStatus} />
        </div>
        <div className="mt-1 truncate text-sm font-medium">{CATEGORY_LABEL[c.category as CaseCategory] ?? c.category}</div>
        <div className="mt-0.5 truncate text-xs text-ink-700" title={c.subject}>
          {c.subject}
        </div>
        <div className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-500">
          <span className="truncate">
            {c.pending_step !== 'NONE' ? PENDING_STEP_LABEL[c.pending_step as PendingStep] : 'No pending step'}
          </span>
          {c.pending_since && c.pending_step !== 'NONE' && <span className="font-mono tnum">{ageShort(c.pending_since)}</span>}
        </div>
        {c.clocks.length > 0 && (
          <div className="mt-1.5">
            <ClockPills clocks={c.clocks} stacked />
          </div>
        )}
        {linked && (
          <div className="mt-1.5">
            <RelationBadge relation={kind as RelationType} />
          </div>
        )}
      </div>
      {unrelatedHint && (
        <span className="absolute inset-x-2 top-1/2 -translate-y-1/2 rounded-sm border border-line bg-paper px-2 py-1 text-center text-xs text-ink-700">
          Same institution {'·'} unrelated issue
        </span>
      )}
    </Link>
  );
}

export interface SwimlanesProps {
  items: TimelineItem[];
  links: InstitutionLink[];
}

const SLOT = 12; // px per connector track in the gutter
const COL_MIN = 236;
const COL_MAX = 340;

/**
 * Open matters by bureau. Linked cards share a coloured bracket and tag. Connectors live in a gutter column to the
 * left of the cards (vertical track per link group, short stubs into column 1) or in the gap between neighbours,
 * so a line never passes behind an unrelated card. Hover highlights the whole group.
 */
export function Swimlanes({ items, links }: SwimlanesProps) {
  const open = useMemo(() => items.filter((c) => OPEN_STATUSES.includes(c.status as CaseStatus)), [items]);
  const openIds = useMemo(() => new Set(open.map((c) => c.id)), [open]);
  const model = useMemo(() => buildLinkModel(openIds, links), [openIds, links]);
  const [hover, setHover] = useState<string | null>(null);

  // Group slots (gutter tracks) in order of first appearance; only groups with 2+ cards get one.
  const slots = useMemo(() => {
    const m = new Map<Group, number>();
    open.forEach((c) => {
      const g = model.groupOf.get(c.id);
      if (g && g.ids.size > 1 && !m.has(g)) m.set(g, m.size);
    });
    return m;
  }, [open, model]);
  const gutter = slots.size ? slots.size * SLOT + 8 : 8;

  const wrap = useRef<HTMLDivElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const els = useRef(new Map<string, HTMLElement>());
  const [segments, setSegments] = useState<Segment[]>([]);
  const setRef = useCallback((id: string, el: HTMLElement | null) => {
    if (el) els.current.set(id, el);
    else els.current.delete(id);
  }, []);

  // Lane contents: group members contiguous, one group after another; first member of each group starts a row.
  const lanes = useMemo(
    () =>
      LANES.map((b) => {
        const cases = open.filter((c) => c.owner_bureau === b);
        const slotOf = (c: TimelineItem) => {
          const g = model.groupOf.get(c.id);
          return g && slots.has(g) ? (slots.get(g) as number) : 999;
        };
        const sorted = [...cases].sort((x, y) => slotOf(x) - slotOf(y));
        const seen = new Set<number>();
        return {
          bureau: b,
          cards: sorted.map((c) => {
            const sl = slotOf(c);
            const first = sl !== 999 && !seen.has(sl);
            if (sl !== 999) seen.add(sl);
            return { c, first };
          }),
        };
      }),
    [open, model, slots],
  );

  const measure = useCallback(() => {
    const host = wrap.current;
    const gut = gutterRef.current;
    if (!host || !gut) return;
    const hr = host.getBoundingClientRect();
    const gx0 = gut.getBoundingClientRect().left - hr.left;
    type R = { l: number; r: number; t: number; b: number; cy: number };
    const rects = new Map<string, R>();
    open.forEach((c) => {
      const e = els.current.get(c.id);
      if (!e) return;
      const r = e.getBoundingClientRect();
      rects.set(c.id, { l: r.left - hr.left, r: r.right - hr.left, t: r.top - hr.top, b: r.bottom - hr.top, cy: (r.top + r.bottom) / 2 - hr.top });
    });
    if (rects.size === 0) return;
    const col1 = Math.min(...[...rects.values()].map((r) => r.l));
    const next: Segment[] = [];

    // Strongest relation among a group's links decides the track colour.
    const groupKind = new Map<Group, string>();
    model.active.forEach((l) => {
      const g = model.groupOf.get(l.case_a.id);
      if (g && (STRENGTH[l.relation] ?? 0) > (STRENGTH[groupKind.get(g) ?? ''] ?? 0)) groupKind.set(g, l.relation);
    });
    const colorOf = (g: Group) => KIND_COLOR[groupKind.get(g) ?? 'RELATED'] ?? 'var(--saffron)';
    const dashOf = (g: Group) => (groupKind.get(g) === 'DUPLICATE' ? '4 3' : undefined);

    slots.forEach((slot, g) => {
      const members = [...g.ids].map((id) => ({ id, r: rects.get(id) })).filter((m): m is { id: string; r: R } => !!m.r);
      const edge = members.filter((m) => Math.abs(m.r.l - col1) < 3);
      if (edge.length < 2) return;
      const x = gx0 + slot * SLOT + SLOT / 2 + 2;
      const ys = edge.map((m) => m.r.cy);
      next.push({ key: `v${slot}`, d: `M ${x} ${Math.min(...ys)} V ${Math.max(...ys)}`, color: colorOf(g), dash: dashOf(g), a: '', b: '', group: g });
      edge.forEach((m) => next.push({ key: `s${m.id}`, d: `M ${x} ${m.r.cy} H ${m.r.l}`, color: colorOf(g), dash: dashOf(g), a: m.id, b: m.id, group: g }));
    });

    // Inside a lane: short line across the empty gap between two adjacent cards of one group.
    model.groupOf.forEach((g, id) => {
      const r = rects.get(id);
      if (!r || Math.abs(r.l - col1) < 3) return;
      let left: { id: string; r: R } | null = null;
      g.ids.forEach((oid) => {
        const o = rects.get(oid);
        if (!o || oid === id || Math.abs(o.t - r.t) > 8 || o.r > r.l) return;
        if (!left || o.r > left.r.r) left = { id: oid, r: o };
      });
      if (!left) return;
      const l = left as { id: string; r: R };
      next.push({ key: `n${id}`, d: `M ${l.r.r} ${r.cy} H ${r.l}`, color: colorOf(g), dash: dashOf(g), a: l.id, b: id, group: g });
    });
    setSegments(next);
  }, [open, model, slots]);

  useLayoutEffect(() => {
    measure();
    const host = wrap.current;
    if (!host || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => measure());
    ro.observe(host);
    return () => ro.disconnect();
  }, [measure]);

  if (open.length === 0) return <EmptyState message="No open matters on this institution." />;

  const hoverGroup = hover ? model.groupOf.get(hover) : undefined;

  return (
    <div ref={wrap} className="relative">
      <svg aria-hidden className="pointer-events-none absolute inset-0 z-20 h-full w-full overflow-visible">
        {segments.map((s) => {
          const on = !!hoverGroup && hoverGroup === s.group;
          return <path key={s.key} d={s.d} fill="none" stroke={s.color} strokeWidth={on ? 2.25 : 1.5} strokeDasharray={s.dash} opacity={hoverGroup && !on ? 0.3 : 1} />;
        })}
      </svg>
      {lanes.map((lane, idx) => (
        <div key={lane.bureau} className="relative z-10 grid border-b border-line-soft last:border-b-0" style={{ gridTemplateColumns: `116px ${gutter}px minmax(0, 1fr)` }}>
          <div className="flex items-start border-r border-line-soft py-3 pr-2" style={{ borderLeft: `3px solid ${BUREAU_COLOR_VAR[lane.bureau]}`, paddingLeft: 9 }}>
            <div>
              <BureauTag bureau={lane.bureau} />
              <div className="mt-0.5 font-mono text-xs tnum text-ink-500">{lane.cards.length} open</div>
            </div>
          </div>
          <div ref={idx === 0 ? gutterRef : undefined} aria-hidden />
          <div className="grid items-stretch gap-x-4 gap-y-3 py-3 pr-3" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${COL_MIN}px, ${COL_MAX}px))` }}>
            {lane.cards.length === 0 ? (
              <span className="col-span-full py-1 text-xs text-ink-300">No open matters</span>
            ) : (
              lane.cards.map(({ c, first }) => {
                const inGroup = !!hoverGroup && hoverGroup.ids.has(c.id);
                return (
                  <CaseCard
                    key={c.id}
                    c={c}
                    kind={model.kind.get(c.id)}
                    highlighted={inGroup && hoverGroup!.ids.size > 1}
                    unrelatedHint={!!hover && hover !== c.id && !inGroup}
                    onHover={setHover}
                    setRef={setRef}
                    firstInGroup={first}
                  />
                );
              })
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
