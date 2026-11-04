// URL <-> filter state for the case register. Dashboard click-throughs arrive as query params
// (/cases?overdue=true&bureau=PGRC&ro_code=KNP), so every filter lives in the URL.

export type SortKey = 'received_at_desc' | 'due_asc';

export interface CaseFilters {
  q: string;
  status: string[];
  bureau: string[];
  ro_code: string[];
  category: string[];
  channel: string[];
  clock_state: string[];
  has_alert: boolean;
  owner_me: boolean;
  overdue: boolean;
  /** RO officers default to their own region; scope=all opts out. */
  scope_all: boolean;
  institution_id: string;
  received_from: string;
  received_to: string;
  sort: SortKey;
  page: number;
}

export const PAGE_SIZE = 25;

const LIST_KEYS = ['status', 'bureau', 'ro_code', 'category', 'channel', 'clock_state'] as const;

const list = (sp: URLSearchParams, key: string): string[] =>
  sp
    .getAll(key)
    .flatMap((v) => v.split(','))
    .map((v) => v.trim())
    .filter(Boolean);
const flag = (sp: URLSearchParams, key: string): boolean => ['true', '1', 'me'].includes((sp.get(key) ?? '').toLowerCase());

export function parseFilters(sp: URLSearchParams): CaseFilters {
  const page = Number(sp.get('page') ?? '1');
  return {
    q: sp.get('q') ?? '',
    status: list(sp, 'status'),
    bureau: list(sp, 'bureau'),
    ro_code: list(sp, 'ro_code'),
    category: list(sp, 'category'),
    channel: list(sp, 'channel'),
    clock_state: list(sp, 'clock_state'),
    has_alert: flag(sp, 'has_alert'),
    owner_me: flag(sp, 'owner'),
    overdue: flag(sp, 'overdue'),
    scope_all: (sp.get('scope') ?? '').toLowerCase() === 'all',
    institution_id: sp.get('institution_id') ?? '',
    received_from: sp.get('received_from') ?? '',
    received_to: sp.get('received_to') ?? '',
    sort: sp.get('sort') === 'due_asc' ? 'due_asc' : 'received_at_desc',
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

/** Serialise back to the URL (omits defaults so URLs stay short and shareable). */
export function toSearchParams(f: CaseFilters): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.q) sp.set('q', f.q);
  for (const k of LIST_KEYS) f[k].forEach((v) => sp.append(k, v));
  if (f.has_alert) sp.set('has_alert', 'true');
  if (f.owner_me) sp.set('owner', 'me');
  if (f.overdue) sp.set('overdue', 'true');
  if (f.scope_all) sp.set('scope', 'all');
  if (f.institution_id) sp.set('institution_id', f.institution_id);
  if (f.received_from) sp.set('received_from', f.received_from);
  if (f.received_to) sp.set('received_to', f.received_to);
  if (f.sort !== 'received_at_desc') sp.set('sort', f.sort);
  if (f.page > 1) sp.set('page', String(f.page));
  return sp;
}

type ApiParams = Record<string, string | number | boolean | ReadonlyArray<string> | undefined>;

/** Query parameters for GET /cases (the API specification). */
export function toApiParams(f: CaseFilters, page = f.page, pageSize = PAGE_SIZE): ApiParams {
  const p: ApiParams = { page, page_size: pageSize, sort: f.sort };
  if (f.q) p.q = f.q;
  for (const k of LIST_KEYS) if (f[k].length) p[k] = f[k];
  if (f.has_alert) p.has_alert = true;
  if (f.owner_me) p.owner = 'me';
  if (f.overdue) p.overdue = true;
  if (f.scope_all) p.scope = 'all';
  if (f.institution_id) p.institution_id = f.institution_id;
  if (f.received_from) p.received_from = f.received_from;
  if (f.received_to) p.received_to = f.received_to;
  return p;
}

export const EMPTY_FILTERS: CaseFilters = parseFilters(new URLSearchParams());

export type ViewId = 'mine' | 'bureau' | 'overdue' | 'alerts' | 'all';

/** Saved views are presets that replace the filter set. */
export function applyView(view: ViewId, userBureau: string | undefined): CaseFilters {
  const base = { ...EMPTY_FILTERS };
  switch (view) {
    case 'mine':
      return { ...base, owner_me: true };
    case 'bureau':
      return { ...base, bureau: userBureau ? [userBureau] : [] };
    case 'overdue':
      return { ...base, overdue: true };
    case 'alerts':
      return { ...base, has_alert: true };
    default:
      return base;
  }
}

/** Which saved view matches the current filters exactly (ignoring sort/page); null for a custom filter set. */
export function activeView(f: CaseFilters, userBureau: string | undefined): ViewId | null {
  const key = (x: CaseFilters) => toSearchParams({ ...x, sort: 'received_at_desc', page: 1 }).toString();
  const cur = key(f);
  for (const v of ['mine', 'bureau', 'overdue', 'alerts', 'all'] as ViewId[]) {
    if (v === 'bureau' && !userBureau) continue;
    if (cur === key(applyView(v, userBureau))) return v;
  }
  return null;
}

/** Number of active filters excluding search/sort/page (for the "Reset" affordance). */
export function activeFilterCount(f: CaseFilters): number {
  return (
    LIST_KEYS.reduce((n, k) => n + f[k].length, 0) +
    Number(f.has_alert) +
    Number(f.owner_me) +
    Number(f.overdue) +
    Number(!!f.institution_id) +
    Number(!!(f.received_from || f.received_to))
  );
}
