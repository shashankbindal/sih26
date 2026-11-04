import { useApiQuery } from '@/api/hooks';
import { dashParams, type DashFilters } from './filters';

// Shapes follow the API specification "Dashboard". Fields are optional where the spec is loose.
export interface Kpis {
  total: number;
  pending: number;
  under_process: number;
  disposed: number;
  transferred: number;
  escalated: number;
  overdue: number;
  open_alerts: number;
  overdue_by_clock?: Record<string, number>;
  /** Status lists behind each count (from the backend, not hard-coded here). */
  definitions?: Record<string, string[]>;
  deltas?: { vs_prev_period?: Record<string, { previous: number; change: number; pct: number | null }> } | null;
  as_of?: string;
}

export type BureauRow = { bureau: string } & Record<string, number | string>;
export interface CategoryRow {
  category: string;
  open: number;
  disposed: number;
}
export interface AgeingRow {
  bucket: string;
  count: number;
}
export interface TrendRow {
  period: string;
  received: number;
  disposed: number;
}
export interface RegionRow {
  ro_code: string;
  name: string;
  city?: string | null;
  lat: number | null;
  lng: number | null;
  open: number;
  overdue: number;
}
export interface TopInstitutionRow {
  institution_id: string;
  name: string;
  permanent_id?: string;
  district?: string | null;
  open: number;
  overdue: number;
  open_alerts: number;
}
export interface ClockCounts {
  on_track: number;
  amber: number;
  breached: number;
  paused?: number;
  met: number;
  total?: number;
  /** Short label and rule text from policy_config. */
  label?: string;
  rule?: string;
}
export type ClocksResponse = Record<'CPGRAMS_21D' | 'CSS_72H' | 'INST_REFUND_7D', ClockCounts>;

const REFRESH_MS = 60_000;

/** One dashboard widget query: global filters, 60 s auto refresh. */
export function useDash<T>(name: string, path: string, f: DashFilters, extra: Record<string, string | number> = {}) {
  return useApiQuery<T>(['dash', name], `/dashboard/${path}`, {
    params: { ...dashParams(f), ...extra },
    refetchInterval: REFRESH_MS,
  });
}

/** Region options come from an unfiltered query so the select does not shrink when a region is chosen. */
export function useRegionOptions() {
  return useApiQuery<RegionRow[]>(['dash', 'region-options'], '/dashboard/by-region', { staleTime: 300_000 });
}

export function deltaOf(deltas: Kpis['deltas'], key: string): number | null {
  const v = deltas?.vs_prev_period?.[key];
  // No comparison when the previous period had none of this measure (a change from zero says nothing).
  return v && typeof v.change === 'number' && v.previous > 0 ? v.change : null;
}

export interface PublicClock {
  duration_hours?: number;
  short_label?: string;
  long_label?: string | null;
  rule?: string | null;
  clause_key?: string | null;
}
export interface PublicConfig {
  clocks?: Record<string, PublicClock>;
  clause_labels?: Record<string, string>;
  amber_ratio?: number;
}

/** Clock names, durations and clause labels come from policy_config via /config/public, never from literals. */
export function usePublicConfig() {
  return useApiQuery<PublicConfig>(['policy', 'public'], '/config/public', { staleTime: 300_000 });
}

/** Active, non-unrelated links whose two cases are both open: the single definition of an "open alert". */
export const ACTIVE_LINK_STATUSES = ['SUGGESTED', 'CONFIRMED', 'DEFERRED'];

/** Count of open alerts for the given relations (GET /links?both_open=true, page_size 1 so only `total` is used). */
export function useAlertCount(relations: string[], f: DashFilters) {
  return useApiQuery<{ total: number }>(['links', 'dash-count', relations.join(',')], '/links', {
    params: { relation: relations, status: ACTIVE_LINK_STATUSES, both_open: true, bureau: f.bureau || undefined, page_size: 1 },
    refetchInterval: REFRESH_MS,
  });
}

/** Clearance requests waiting for the signed-in user's bureau. Disabled for roles without the inbox. */
export function useClearancesWaiting(enabled: boolean) {
  return useApiQuery<{ total: number }>(['clearances', 'dash-count'], '/clearances', {
    params: { inbox: 'me', status: ['PENDING'], page_size: 1 },
    enabled,
    refetchInterval: REFRESH_MS,
  });
}

/** Complaints whose institution still needs an officer to confirm the match. */
export function useMatchesToConfirm(enabled: boolean) {
  return useApiQuery<{ total: number }>(['review', 'dash-count'], '/review/institution-matches', {
    params: { limit: 1 },
    enabled,
    refetchInterval: REFRESH_MS,
  });
}
