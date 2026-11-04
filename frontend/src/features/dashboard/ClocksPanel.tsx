import { Link } from 'react-router-dom';
import { formatNumber } from '@/lib/format';
import type { ClockCounts, ClocksResponse, PublicConfig } from './api';
import { casesLink, type DashFilters } from './filters';

// Three separate clocks, never one "SLA" (the policy-clock rules). Clock keys, names, durations and rule text
// all come from the API (/dashboard/clocks and policy_config via /config/public); nothing is written here.

type SegKey = 'breached' | 'amber' | 'on_track' | 'met' | 'paused';
const SEGMENTS: { key: SegKey; label: string; color: string; state: string }[] = [
  { key: 'breached', label: 'Past deadline', color: 'var(--red)', state: 'BREACHED' },
  { key: 'amber', label: 'Due soon', color: 'var(--amber)', state: 'AMBER' },
  { key: 'on_track', label: 'On track', color: 'var(--ok)', state: 'ON_TRACK' },
  { key: 'met', label: 'Done in time', color: 'var(--chart-3)', state: 'MET' },
  { key: 'paused', label: 'Paused', color: 'var(--ink-300)', state: 'PAUSED' },
];

const cnt = (c: ClockCounts, k: SegKey): number => c[k] ?? 0;

/** Clock name from policy_config: long label, else short label from the dashboard response, else the key. */
export function clockTitle(key: keyof ClocksResponse, pub: PublicConfig | undefined, counts?: ClockCounts): string {
  return pub?.clocks?.[key]?.long_label || pub?.clocks?.[key]?.short_label || counts?.label || key;
}

/** Rule / clause text for a clock tooltip. */
export function clockRule(key: keyof ClocksResponse, pub: PublicConfig | undefined, counts?: ClockCounts): string | undefined {
  const cfg = pub?.clocks?.[key];
  const clause = cfg?.clause_key ? pub?.clause_labels?.[cfg.clause_key] : undefined;
  return clause || cfg?.rule || counts?.rule || undefined;
}

export function totalOf(c: ClockCounts | undefined): number {
  return c ? (c.total ?? c.on_track + c.amber + c.breached + c.met + (c.paused ?? 0)) : 0;
}

/** Three segmented bars, one per clock: overdue, due soon, on track, met. Text counts under each bar. */
export function ClocksPanelBody({ data, filters, pub }: { data: ClocksResponse; filters: DashFilters; pub?: PublicConfig }) {
  return (
    <div className="flex flex-col gap-6 pt-1">
      {(Object.keys(data) as (keyof ClocksResponse)[]).map((key) => {
        const c = data[key];
        if (!c) return null;
        const label = clockTitle(key, pub, c);
        const total = totalOf(c);
        return (
          <div key={key}>
            <div className="flex items-baseline justify-between">
              <span className="text-base font-semibold text-ink-900" title={clockRule(key, pub, c)}>
                {label}
              </span>
              <span className="tnum text-sm text-ink-500">{formatNumber(total)} cases</span>
            </div>
            {total === 0 ? (
              <p className="mt-2 text-xs text-ink-500">No cases follow this deadline rule in the current filters.</p>
            ) : (
              <>
                <div className="mt-2 flex h-8 gap-0.5" role="img" aria-label={`${label}: ${SEGMENTS.map((s) => `${s.label} ${cnt(c, s.key)}`).join(', ')}`}>
                  {SEGMENTS.map((s) =>
                    cnt(c, s.key) > 0 ? (
                      <div
                        key={s.key}
                        className="flex items-center justify-center overflow-hidden text-sm font-semibold tnum"
                        style={{ width: `${(cnt(c, s.key) / total) * 100}%`, background: s.color, color: s.key === 'met' ? 'var(--ink-900)' : 'var(--surface)', minWidth: 2 }}
                      >
                        {cnt(c, s.key) / total > 0.06 ? cnt(c, s.key) : ''}
                      </div>
                    ) : null,
                  )}
                </div>
                <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm">
                  {SEGMENTS.filter((s) => s.key !== 'paused' || cnt(c, 'paused') > 0).map((s) => (
                    <Link key={s.key} to={casesLink(filters, { clock_state: s.state, anyStatus: true })} className="inline-flex items-center gap-1.5 text-ink-700">
                      <span aria-hidden className="inline-block h-3 w-3" style={{ background: s.color }} />
                      {s.label} <span className="tnum font-medium text-ink-900">{formatNumber(cnt(c, s.key))}</span>
                    </Link>
                  ))}
                </div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
