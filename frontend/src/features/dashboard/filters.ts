import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '@/auth';

export type RangeId = '30d' | '90d' | '180d' | '365d' | 'all';

export const RANGE_OPTIONS: { id: RangeId; label: string; days: number | null }[] = [
  { id: '30d', label: 'Last 30 days', days: 30 },
  { id: '90d', label: 'Last 90 days', days: 90 },
  { id: '180d', label: 'Last 180 days', days: 180 },
  { id: '365d', label: 'Last 12 months', days: 365 },
  { id: 'all', label: 'All time', days: null },
];

/** Default window, as in the dashboard wireframe ("Last 90 days"). */
export const DEFAULT_RANGE: RangeId = '90d';

export interface DashFilters {
  range: RangeId;
  bureau: string;
  ro: string;
  category: string;
  status: string;
}

const KEYS = ['range', 'bureau', 'ro', 'category', 'status'] as const;

function isRange(v: string | null): v is RangeId {
  return RANGE_OPTIONS.some((r) => r.id === v);
}

/** YYYY-MM-DD, `days` before today. Date-only so query keys stay stable within a day. */
export function fromDate(range: RangeId): string | undefined {
  const opt = RANGE_OPTIONS.find((r) => r.id === range);
  if (!opt || opt.days === null) return undefined;
  const d = new Date();
  d.setDate(d.getDate() - opt.days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export interface UseDashFilters {
  filters: DashFilters;
  /** RO officers are scoped to their own region; the control is locked for them. */
  roLocked: boolean;
  set: (patch: Partial<DashFilters>) => void;
  reset: () => void;
  isDefault: boolean;
}

/** Filter state lives in the URL so views can be shared and links keep the same filters. */
export function useDashboardFilters(): UseDashFilters {
  const { user } = useAuth();
  const [sp, setSp] = useSearchParams();
  const roLocked = user?.role === 'RO_OFFICER' && !!user.ro_code;

  const rangeRaw = sp.get('range');
  const filters: DashFilters = useMemo(
    () => ({
      range: isRange(rangeRaw) ? rangeRaw : DEFAULT_RANGE,
      bureau: sp.get('bureau') ?? '',
      ro: roLocked ? (user?.ro_code ?? '') : (sp.get('ro') ?? ''),
      category: sp.get('category') ?? '',
      status: sp.get('status') ?? '',
    }),
    [sp, rangeRaw, roLocked, user?.ro_code],
  );

  const set = useCallback(
    (patch: Partial<DashFilters>) => {
      setSp(
        (cur) => {
          const next = new URLSearchParams(cur);
          for (const k of KEYS) {
            const v = patch[k];
            if (v === undefined) continue;
            if (v === '' || (k === 'range' && v === DEFAULT_RANGE)) next.delete(k);
            else next.set(k, v);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSp],
  );

  const reset = useCallback(
    () =>
      setSp(
        (cur) => {
          const next = new URLSearchParams();
          const tab = cur.get('tab');
          if (tab) next.set('tab', tab); // filters reset, the open tab stays
          return next;
        },
        { replace: true },
      ),
    [setSp],
  );
  const isDefault = filters.range === DEFAULT_RANGE && !filters.bureau && !filters.category && !filters.status && (roLocked || !filters.ro);

  return { filters, roLocked, set, reset, isDefault };
}

type ParamValue = string | number | boolean | undefined;

/** Query-string params for /dashboard/* endpoints (the API specification: from, bureau[], ro_code[], category[], status[]). */
export function dashParams(f: DashFilters): Record<string, ParamValue> {
  return {
    from: fromDate(f.range),
    bureau: f.bureau || undefined,
    ro_code: f.ro || undefined,
    category: f.category || undefined,
    status: f.status || undefined,
  };
}

export interface LinkOverride {
  /** Replaces the dashboard status filter. */
  status?: string | string[];
  bureau?: string;
  ro_code?: string;
  category?: string;
  clock_state?: string;
  overdue?: boolean;
  has_alert?: boolean;
  /** Drop the dashboard status filter (e.g. for totals). */
  anyStatus?: boolean;
}

/** `/cases?...` carrying the dashboard filters; `over` replaces individual filters. */
export function casesLink(f: DashFilters, over: LinkOverride = {}): string {
  const sp = new URLSearchParams();
  const from = fromDate(f.range);
  if (from) sp.set('received_from', from);
  const bureau = over.bureau ?? f.bureau;
  if (bureau) sp.set('bureau', bureau);
  const ro = over.ro_code ?? f.ro;
  if (ro) sp.set('ro_code', ro);
  const category = over.category ?? f.category;
  if (category) sp.set('category', category);
  const status = over.status ?? (over.anyStatus ? undefined : f.status || undefined);
  if (status) (Array.isArray(status) ? status : [status]).forEach((s) => sp.append('status', s));
  if (over.clock_state) sp.set('clock_state', over.clock_state);
  if (over.overdue) sp.set('overdue', 'true');
  if (over.has_alert) sp.set('has_alert', 'true');
  const q = sp.toString();
  return q ? `/cases?${q}` : '/cases';
}

/** `/coordination?...` with the bureau / region part of the dashboard filters. */
export function coordinationLink(f: DashFilters): string {
  const sp = new URLSearchParams();
  if (f.bureau) sp.set('bureau', f.bureau);
  if (f.ro) sp.set('ro_code', f.ro);
  const q = sp.toString();
  return q ? `/coordination?${q}` : '/coordination';
}
