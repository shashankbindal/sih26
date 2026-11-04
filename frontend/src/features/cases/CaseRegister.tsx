import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Download, Search } from 'lucide-react';
import { api, ApiError, errorMessage } from '@/api/client';
import { useAuth } from '@/auth';
import { BureauTag, StatusTag } from '@/components/domain';
import { Button, DataTable, Input, Select, Tabs, useToast, type Column, type TabItem } from '@/components/ui';
import {
  BUREAUS,
  BUREAU_LABEL,
  CASE_STATUS_LABEL,
  CATEGORY_LABEL,
  CHANNEL_LABEL,
  CLOCK_STATE_LABEL,
  PENDING_STEP_LABEL,
  type Bureau,
  type CaseCategory,
  type CaseStatus,
  type ClockState,
  type PendingStep,
  type SourceChannel,
} from '@/lib/constants';
import { ICON } from '@/lib/icons';
import { ageShort, formatDate, formatNumber, formatTime } from '@/lib/format';
import { FilterChip, ToggleChip } from './FilterChip';
import { CaseQuickView } from './CaseQuickView';
import { EXPORT_LIMIT, exportCasesCsv } from './exportCsv';
import {
  PAGE_SIZE,
  activeFilterCount,
  activeView,
  applyView,
  parseFilters,
  toApiParams,
  toSearchParams,
  type CaseFilters,
  type ViewId,
} from './filters';
import { AlertsCell, ClockPills, MaybeHindi, RO_OPTIONS, roName, type CaseListPage, type CaseSummary } from './shared';

const opts = <T extends string>(labels: Record<T, string>) => (Object.keys(labels) as T[]).map((value) => ({ value, label: labels[value] }));

const STATUS_OPTIONS = opts<CaseStatus>(CASE_STATUS_LABEL);
const BUREAU_OPTIONS = BUREAUS.filter((b) => b !== 'ADMIN').map((b) => ({ value: b, label: BUREAU_LABEL[b] }));
const CATEGORY_OPTIONS = opts<CaseCategory>(CATEGORY_LABEL);
const CHANNEL_OPTIONS = opts<SourceChannel>(CHANNEL_LABEL);
const CLOCK_OPTIONS = opts<ClockState>(CLOCK_STATE_LABEL);
const RO_CHIP_OPTIONS = RO_OPTIONS.map((r) => ({ value: r.value, label: `${r.label} (${r.value})` }));

const cellText = 'block max-w-full truncate';

export function CaseRegister() {
  const { user } = useAuth();
  const { toast } = useToast();
  const [sp, setSp] = useSearchParams();
  const filters = useMemo(() => parseFilters(sp), [sp]);
  const [selected, setSelected] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  // Search box: local text, debounced into the URL.
  const [qText, setQText] = useState(filters.q);
  useEffect(() => setQText(filters.q), [filters.q]);
  useEffect(() => {
    if (qText === filters.q) return;
    const t = window.setTimeout(() => setSp(toSearchParams({ ...filters, q: qText.trim(), page: 1 })), 300);
    return () => window.clearTimeout(t);
  }, [qText, filters, setSp]);

  const update = (patch: Partial<CaseFilters>) => setSp(toSearchParams({ ...filters, page: 1, ...patch }));

  const list = useQuery<CaseListPage, ApiError>({
    queryKey: ['cases', 'list', filters],
    queryFn: ({ signal }) => api.get<CaseListPage>('/cases', { params: toApiParams(filters), signal }),
    placeholderData: keepPreviousData,
  });

  const view = activeView(filters, user?.bureau);
  const viewTabs: TabItem[] = [
    { id: 'mine', label: 'My cases' },
    { id: 'bureau', label: 'My bureau' },
    { id: 'overdue', label: 'Overdue' },
    { id: 'alerts', label: 'With alerts' },
    { id: 'all', label: 'All' },
    ...(view === null ? [{ id: 'custom', label: 'Filtered' }] : []),
  ];

  const nFilters = activeFilterCount(filters);
  const total = list.data?.total;

  const runExport = async () => {
    setExporting(true);
    try {
      const r = await exportCasesCsv(filters);
      toast(r.truncated ? `Exported ${formatNumber(r.rows)} of ${formatNumber(r.total)} cases (limit ${formatNumber(EXPORT_LIMIT)}).` : `Exported ${formatNumber(r.rows)} cases.`, 'ok');
    } catch (e) {
      toast(`Export failed. ${errorMessage(e)}`, 'red');
    } finally {
      setExporting(false);
    }
  };

  const columns: Column<CaseSummary>[] = [
    {
      key: 'display_id',
      header: 'Case ID',
      mono: true,
      width: 124,
      render: (c) => (
        <Link to={`/cases/${c.id}`} onClick={(e) => e.stopPropagation()} className="text-navy">
          {c.display_id}
        </Link>
      ),
    },
    {
      key: 'received',
      header: 'Received',
      width: 90,
      render: (c) => (
        <span className="block whitespace-nowrap leading-tight">
          <span className="tnum">{formatDate(c.received_at)}</span>
          <span className="block text-xs text-ink-500 tnum">{formatTime(c.received_at)}</span>
        </span>
      ),
    },
    { key: 'channel', header: 'Channel', width: 70, render: (c) => <span className="block text-xs leading-tight">{CHANNEL_LABEL[c.source_channel as SourceChannel] ?? c.source_channel}</span> },
    {
      key: 'institution',
      header: 'Institution',
      render: (c) =>
        c.institution ? (
          <span className="block min-w-[130px] max-w-[160px] leading-tight">
            <span className={cellText} title={c.institution.name}>
              <MaybeHindi text={c.institution.name} />
            </span>
            <span className="block font-mono text-xs tnum text-ink-500">{c.institution.permanent_id}</span>
          </span>
        ) : (
          <span className="block max-w-[160px] leading-tight text-ink-500">
            <span className={cellText}>Unresolved</span>
            {c.institution_text_raw && <span className="block truncate text-xs">{c.institution_text_raw}</span>}
          </span>
        ),
    },
    { key: 'category', header: 'Category', width: 90, render: (c) => <span className="block text-xs leading-tight">{CATEGORY_LABEL[c.category as CaseCategory] ?? c.category}</span> },
    {
      key: 'owner',
      header: 'Owner',
      width: 96,
      render: (c) => (
        <span className="block leading-tight">
          <BureauTag bureau={c.owner_bureau as Bureau} roCode={c.owner_ro_code} />
          {c.owner_officer && <span className="block max-w-[82px] truncate text-xs text-ink-500">{c.owner_officer.name}</span>}
        </span>
      ),
    },
    { key: 'status', header: 'Status', width: 104, render: (c) => <StatusTag status={c.status as CaseStatus} /> },
    {
      key: 'pending',
      header: 'Pending step',
      width: 88,
      render: (c) =>
        c.pending_step === 'NONE' ? (
          <span className="text-ink-300">{'–'}</span>
        ) : (
          <span className="block leading-tight">
            <span className="block text-xs">{PENDING_STEP_LABEL[c.pending_step as PendingStep] ?? c.pending_step}</span>
            {c.pending_since && <span className="block font-mono text-xs tnum text-ink-500">{ageShort(c.pending_since)}</span>}
          </span>
        ),
    },
    { key: 'clocks', header: 'Policy clocks', width: 150, render: (c) => <ClockPills clocks={c.clocks} stacked compact /> },
    { key: 'alerts', header: 'Alerts', width: 84, render: (c) => <AlertsCell alerts={c.alerts} /> },
  ];

  const errorNode = list.isError && !list.data ? `The register could not be loaded. ${errorMessage(list.error)}` : undefined;
  const hasFilters = nFilters > 0 || !!filters.q;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-xl font-semibold text-ink-900">Case register</h1>
          <span className="text-sm text-ink-500">
            <span className="tnum">{total === undefined ? '' : `${formatNumber(total)} ${total === 1 ? 'case' : 'cases'}`}</span>
          </span>
        </div>
        <Button icon={Download} onClick={() => void runExport()} loading={exporting} disabled={!total} title={`Exports the current filter, up to ${formatNumber(EXPORT_LIMIT)} rows`}>
          Export CSV
        </Button>
      </div>

      <section className="mb-3 rounded border border-line bg-surface" aria-label="Filters">
        <Tabs
          ariaLabel="Saved views"
          className="px-3"
          tabs={viewTabs}
          value={view ?? 'custom'}
          onChange={(id) => {
            if (id === 'custom') return;
            setSp(toSearchParams(applyView(id as ViewId, user?.bureau)));
          }}
        />
        <div className="flex flex-wrap items-center gap-2 px-3 py-2.5">
          <div className="relative">
            <Search {...ICON} size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-300" />
            <Input
              type="search"
              aria-label="Search cases"
              placeholder="Case ID, reference, institution or text"
              value={qText}
              onChange={(e) => setQText(e.target.value)}
              className="!h-7 w-[230px] !pl-8 text-xs"
            />
          </div>
          <FilterChip label="Status" options={STATUS_OPTIONS} value={filters.status} onChange={(v) => update({ status: v })} />
          <FilterChip label="Bureau" options={BUREAU_OPTIONS} value={filters.bureau} onChange={(v) => update({ bureau: v })} />
          <FilterChip label="Region" options={RO_CHIP_OPTIONS} value={filters.ro_code} onChange={(v) => update({ ro_code: v })} />
          <FilterChip label="Category" options={CATEGORY_OPTIONS} value={filters.category} onChange={(v) => update({ category: v })} />
          <FilterChip label="Channel" options={CHANNEL_OPTIONS} value={filters.channel} onChange={(v) => update({ channel: v })} />
          <FilterChip label="Clock" options={CLOCK_OPTIONS} value={filters.clock_state} onChange={(v) => update({ clock_state: v })} />
          <ToggleChip label="Overdue" pressed={filters.overdue} onChange={(v) => update({ overdue: v })} />
          <ToggleChip label="Has alert" pressed={filters.has_alert} coordination onChange={(v) => update({ has_alert: v })} />
          {user?.role === 'RO_OFFICER' && user.ro_code && (
            <>
              {!filters.scope_all && (
                <span className="inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded border border-line bg-paper px-2 text-xs font-medium text-ink-900" title="RO officers see their own region by default">
                  <span className="text-ink-500">Region:</span>
                  {roName(user.ro_code) ?? user.ro_code} <span className="text-ink-500">(default)</span>
                </span>
              )}
              <ToggleChip label="All regions" pressed={filters.scope_all} onChange={(v) => update({ scope_all: v })} />
            </>
          )}
          <ToggleChip label="Owner: me" pressed={filters.owner_me} onChange={(v) => update({ owner_me: v })} />
          {filters.institution_id && (
            <ToggleChip label="One institution" pressed onChange={() => update({ institution_id: '' })} />
          )}
          {(filters.received_from || filters.received_to) && (
            <ToggleChip
              label={`Received ${filters.received_from ? formatDate(filters.received_from) : '…'} – ${filters.received_to ? formatDate(filters.received_to) : '…'}`}
              pressed
              onChange={() => update({ received_from: '', received_to: '' })}
            />
          )}
          {hasFilters && (
            <button type="button" className="focus-ring text-xs text-navy hover:underline" style={{ background: 'none', border: 0 }} onClick={() => setSp(new URLSearchParams())}>
              Reset
            </button>
          )}
          <label className="ml-auto flex items-center gap-2 text-xs text-ink-500">
            Sort
            <Select aria-label="Sort order" value={filters.sort} onChange={(e) => update({ sort: e.target.value as CaseFilters['sort'] })} className="!h-7 !w-auto text-xs">
              <option value="received_at_desc">Received, newest first</option>
              <option value="due_asc">Due date, earliest first</option>
            </Select>
          </label>
        </div>
      </section>

      <DataTable<CaseSummary>
        caption="Case register"
        className="[&_td]:!px-1.5 [&_td]:!py-1 [&_th]:!px-1.5"
        columns={columns}
        rows={list.data?.items}
        rowKey={(c) => c.id}
        loading={list.isLoading}
        errorMessage={errorNode}
        emptyMessage={hasFilters ? 'No cases match the current filters.' : 'No cases in the register yet.'}
        emptyAction={hasFilters ? <Button variant="tertiary" onClick={() => setSp(new URLSearchParams())}>Reset filters</Button> : undefined}
        onRowClick={(c) => setSelected(c.id)}
        selectedKey={selected}
        pagination={{
          page: filters.page,
          pageSize: PAGE_SIZE,
          total: list.data?.total ?? 0,
          onPageChange: (p) => setSp(toSearchParams({ ...filters, page: p })),
        }}
      />

      <CaseQuickView caseId={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
