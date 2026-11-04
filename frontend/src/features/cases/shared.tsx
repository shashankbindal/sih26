import type { ReactNode } from 'react';
import { ApiError } from '@/api/client';
import type { Schemas } from '@/api/types';
import { ClockPill } from '@/components/domain';
import { RelationBadge } from '@/components/domain/RelationBadge';
import type { RelationType } from '@/lib/constants';

export type CaseSummary = Schemas['CaseSummary'];
export type CaseDetail = Schemas['CaseDetail'];
export type CaseListPage = Schemas['CaseListPage'];
export type ClockOut = Schemas['ClockOut'];
export type LinkOut = Schemas['LinkOut'];

/** Regional Offices (reference data from the data model regional_offices; names are display labels only). */
export const RO_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'KNP', label: 'Kanpur' },
  { value: 'CHD', label: 'Chandigarh' },
  { value: 'MUM', label: 'Mumbai' },
  { value: 'BPL', label: 'Bhopal' },
  { value: 'KOL', label: 'Kolkata' },
  { value: 'GHY', label: 'Guwahati' },
  { value: 'BLR', label: 'Bengaluru' },
  { value: 'HYD', label: 'Hyderabad' },
  { value: 'CHN', label: 'Chennai' },
  { value: 'TVM', label: 'Thiruvananthapuram' },
];
export const roName = (code: string | null | undefined): string | null =>
  code ? (RO_OPTIONS.find((r) => r.value === code)?.label ?? code) : null;

const DEVANAGARI = /[ऀ-ॿ]/;
export const hasDevanagari = (s: string | null | undefined): boolean => !!s && DEVANAGARI.test(s);

/** Wraps Devanagari text with lang="hi". */
export function MaybeHindi({ text, className }: { text: string; className?: string }): ReactNode {
  return hasDevanagari(text) ? (
    <span lang="hi" className={className}>
      {text}
    </span>
  ) : (
    <span className={className}>{text}</span>
  );
}

/** Message for an inline action error. 404/501 on a write path means another service has not shipped it yet. */
export function describeActionError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404 || err.status === 501 || err.status === 405) {
      return 'This action is not available on the server yet. Nothing was changed.';
    }
    if (err.status === 403) return err.message || 'You are not permitted to do this.';
    return err.message || 'The request failed.';
  }
  return err instanceof Error ? err.message : 'The request failed.';
}

/** Clock pills for a case; each is its own clock, never merged into one figure. */
/** Table-width label: "21-day · 6 days left" becomes "21-day · 6d left". */
const compactLabel = (l: string) => l.replace(/\s*days?\b/g, 'd').replace(/\s*hours?\b/g, 'h');

export function ClockPills({ clocks, stacked, compact }: { clocks: ClockOut[]; stacked?: boolean; compact?: boolean }) {
  if (!clocks.length) return <span className="text-ink-300">{'–'}</span>;
  return (
    <span className={stacked ? 'flex flex-col items-start gap-1' : 'flex flex-wrap items-center gap-1'}>
      {clocks.map((c) => (
        <ClockPill key={c.clock} label={compact ? compactLabel(c.label) : c.label} state={c.state} clock={c.clock} clause={c.rule} />
      ))}
    </span>
  );
}

/** Alert count cell: conflicting first (red), other pending links in saffron (coordination), clock flags as text. */
export function AlertsCell({ alerts }: { alerts: CaseSummary['alerts'] }) {
  const otherLinks = Math.max(0, alerts.pending_links - alerts.conflicting);
  // Clock flags are already shown in the clocks column; this column counts coordination links only.
  if (alerts.conflicting === 0 && otherLinks === 0) return <span className="text-ink-300">{'–'}</span>;
  return (
    <span className="flex flex-col items-start gap-1">
      {alerts.conflicting > 0 && (
        <span className="inline-flex items-center gap-1">
          <RelationBadge relation={'CONFLICTING' as RelationType} />
          {alerts.conflicting > 1 && <span className="font-mono text-xs tnum text-ink-500">×{alerts.conflicting}</span>}
        </span>
      )}
      {otherLinks > 0 && (
        <span className="inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-sm border border-saffron bg-saffron-bg px-1.5 text-xs font-medium leading-none text-amber">
          Linked <span className="font-mono tnum">×{otherLinks}</span>
        </span>
      )}
    </span>
  );
}
