import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { api, ApiError, errorMessage } from '@/api/client';
import type { Schemas } from '@/api/types';
import { Badge, Button, DataTable, Input, type Column, type SortState } from '@/components/ui';
import { formatNumber } from '@/lib/format';
import { ICON } from '@/lib/icons';
import { FilterChip, ToggleChip } from '../cases/FilterChip';
import { MaybeHindi, RO_OPTIONS, roName } from '../cases/shared';
import { APPROVAL_LABEL, APPROVAL_TONE, INSTITUTION_TYPES } from './refData';

type Item = Schemas['InstitutionListItem'];
type Page = Schemas['InstitutionListPage'];

const PAGE_SIZE = 25;

interface Filters {
  q: string;
  ro_code: string;
  state: string;
  type: string;
  approval_status: string;
  has_open_alerts: boolean;
  sort: string;
  page: number;
}

function parse(sp: URLSearchParams): Filters {
  const page = Number(sp.get('page') ?? '1');
  return {
    q: sp.get('q') ?? '',
    ro_code: sp.get('ro_code') ?? '',
    state: sp.get('state') ?? '',
    type: sp.get('type') ?? '',
    approval_status: sp.get('approval_status') ?? '',
    has_open_alerts: ['true', '1'].includes(sp.get('has_open_alerts') ?? ''),
    sort: sp.get('sort') ?? '',
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

function serialise(f: Filters): URLSearchParams {
  const sp = new URLSearchParams();
  (['q', 'ro_code', 'state', 'type', 'approval_status', 'sort'] as const).forEach((k) => f[k] && sp.set(k, f[k]));
  if (f.has_open_alerts) sp.set('has_open_alerts', 'true');
  if (f.page > 1) sp.set('page', String(f.page));
  return sp;
}

export function InstitutionList() {
  const navigate = useNavigate();
  const [sp, setSp] = useSearchParams();
  const f = useMemo(() => parse(sp), [sp]);
  const [qText, setQText] = useState(f.q);
  useEffect(() => setQText(f.q), [f.q]);
  useEffect(() => {
    if (qText === f.q) return;
    const t = window.setTimeout(() => setSp(serialise({ ...f, q: qText.trim(), page: 1 })), 300);
    return () => window.clearTimeout(t);
  }, [qText, f, setSp]);
  const update = (patch: Partial<Filters>) => setSp(serialise({ ...f, page: 1, ...patch }));

  const list = useQuery<Page, ApiError>({
    queryKey: ['institutions', 'list', f],
    queryFn: ({ signal }) =>
      api.get<Page>('/institutions', {
        signal,
        params: {
          page: f.page,
          page_size: PAGE_SIZE,
          q: f.q || undefined,
          ro_code: f.ro_code || undefined,
          state: f.state || undefined,
          type: f.type || undefined,
          approval_status: f.approval_status || undefined,
          has_open_alerts: f.has_open_alerts || undefined,
          sort: f.sort || undefined,
        },
      }),
    placeholderData: keepPreviousData,
  });

  // States for the filter come from the institution set itself (about 200 rows, fetched once).
  const all = useQuery<Page, ApiError>({
    queryKey: ['institutions', 'options'],
    queryFn: ({ signal }) => api.get<Page>('/institutions', { params: { page: 1, page_size: 200 }, signal }),
    staleTime: Infinity,
  });
  const stateOptions = useMemo(
    () =>
      [...new Set((all.data?.items ?? []).map((i) => i.state).filter((s): s is string => !!s))].sort().map((s) => ({ value: s, label: s })),
    [all.data],
  );

  const sort: SortState | null = f.sort === 'open_cases_desc' ? { key: 'open', dir: 'desc' } : f.sort === 'name' ? { key: 'name', dir: 'asc' } : null;
  const hasFilters = !!(f.q || f.ro_code || f.state || f.type || f.approval_status || f.has_open_alerts);

  const columns: Column<Item>[] = [
    { key: 'permanent_id', header: 'Permanent ID', mono: true, width: 130, render: (i) => i.permanent_id },
    {
      key: 'name',
      header: 'Name',
      sortable: true,
      render: (i) => (
        <span className="block min-w-[200px] max-w-[290px] truncate font-medium text-ink-900" title={i.name}>
          <MaybeHindi text={i.name} />
        </span>
      ),
    },
    { key: 'place', header: 'District, State', render: (i) => <span className="block max-w-[170px] truncate text-xs text-ink-700">{[i.district, i.state].filter(Boolean).join(', ') || '–'}</span> },
    { key: 'ro', header: 'RO', width: 120, render: (i) => <span className="text-xs">{roName(i.ro_code) ?? '–'}</span> },
    { key: 'type', header: 'Type', width: 104, render: (i) => <span className="text-xs">{i.inst_type ?? '–'}</span> },
    { key: 'approval', header: 'Approval status', width: 136, render: (i) => <Badge tone={APPROVAL_TONE[i.approval_status] ?? 'neutral'}>{APPROVAL_LABEL[i.approval_status] ?? i.approval_status}</Badge> },
    { key: 'open', header: 'Open', numeric: true, sortable: true, width: 64, render: (i) => (i.open_cases ? formatNumber(i.open_cases) : <span className="text-ink-300">0</span>) },
    {
      key: 'overdue',
      header: 'Overdue',
      numeric: true,
      width: 76,
      render: (i) => (i.overdue ? <span className="font-medium text-red">{formatNumber(i.overdue)}</span> : <span className="text-ink-300">0</span>),
    },
    {
      key: 'alerts',
      header: 'Alerts',
      numeric: true,
      width: 64,
      render: (i) =>
        i.open_alerts ? (
          <span className="inline-flex items-center justify-end gap-1.5">
            <span aria-hidden className="inline-block h-2 w-2 bg-saffron" />
            <span className="font-medium">{formatNumber(i.open_alerts)}</span>
          </span>
        ) : (
          <span className="text-ink-300">0</span>
        ),
    },
  ];

  return (
    <div>
      <div className="mb-3 flex items-baseline gap-3">
        <h1 className="text-xl font-semibold text-ink-900">Institutions</h1>
        <span className="text-sm text-ink-500 tnum">{list.data ? `${formatNumber(list.data.total)} ${list.data.total === 1 ? 'institution' : 'institutions'}` : ''}</span>
      </div>

      <section className="mb-3 flex flex-wrap items-center gap-2 rounded border border-line bg-surface px-3 py-2.5" aria-label="Filters">
        <div className="relative">
          <Search {...ICON} size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-300" />
          <Input
            type="search"
            aria-label="Search institutions"
            placeholder="Name (English or Hindi), Permanent ID, district"
            value={qText}
            onChange={(e) => setQText(e.target.value)}
            className="!h-7 w-[320px] !pl-8 text-xs"
          />
        </div>
        <FilterChip single label="RO" options={RO_OPTIONS.map((r) => ({ value: r.value, label: `${r.label} (${r.value})` }))} value={f.ro_code ? [f.ro_code] : []} onChange={(v) => update({ ro_code: v[0] ?? '' })} />
        <FilterChip single label="State" options={stateOptions} value={f.state ? [f.state] : []} onChange={(v) => update({ state: v[0] ?? '' })} />
        <FilterChip single label="Type" options={INSTITUTION_TYPES.map((t) => ({ value: t, label: t }))} value={f.type ? [f.type] : []} onChange={(v) => update({ type: v[0] ?? '' })} />
        <FilterChip
          single
          label="Status"
          options={Object.entries(APPROVAL_LABEL).map(([value, label]) => ({ value, label }))}
          value={f.approval_status ? [f.approval_status] : []}
          onChange={(v) => update({ approval_status: v[0] ?? '' })}
        />
        <ToggleChip label="Has open alerts" pressed={f.has_open_alerts} coordination onChange={(v) => update({ has_open_alerts: v })} />
        {hasFilters && (
          <button type="button" className="focus-ring text-xs text-navy hover:underline" style={{ background: 'none', border: 0 }} onClick={() => setSp(new URLSearchParams())}>
            Reset
          </button>
        )}
      </section>

      <DataTable<Item>
        caption="Institutions"
        className="[&_td]:!px-1.5 [&_th]:!px-1.5"
        columns={columns}
        rows={list.data?.items}
        rowKey={(i) => i.id}
        loading={list.isLoading}
        errorMessage={list.isError && !list.data ? `The institution list could not be loaded. ${errorMessage(list.error)}` : undefined}
        emptyMessage={hasFilters ? 'No institution matches the current search and filters.' : 'No institutions loaded.'}
        emptyAction={hasFilters ? <Button variant="tertiary" onClick={() => setSp(new URLSearchParams())}>Reset filters</Button> : undefined}
        onRowClick={(i) => navigate(`/institutions/${i.id}`)}
        sort={sort}
        onSortChange={(s) => update({ sort: !s ? '' : s.key === 'open' ? 'open_cases_desc' : s.key === 'name' ? 'name' : '' })}
        pagination={{ page: f.page, pageSize: PAGE_SIZE, total: list.data?.total ?? 0, onPageChange: (p) => setSp(serialise({ ...f, page: p })) }}
      />
    </div>
  );
}
