import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useIsFetching, useQueryClient } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { Button, DataTable, Tabs, type Column } from '@/components/ui';
import { useAuth } from '@/auth';
import { ApiError } from '@/api/client';
import { BUREAU_LABEL, CATEGORY_LABEL, OPEN_STATUSES, type CaseCategory } from '@/lib/constants';
import { formatNumber, formatTime } from '@/lib/format';
import { AttentionRow, type AttentionItem } from './AttentionRow';
import { ChartPanel } from './ChartPanel';
import { ClocksPanelBody, clockTitle } from './ClocksPanel';
import { CoordinationAlertsTable } from './CoordinationAlerts';
import { FilterBar } from './FilterBar';
import { RegionPanelBody, type LocatedRegion } from './RegionPanel';
import { AgeingChart, BureauStatusChart, CategoryChart, TrendChart, ageingLabel, bureauName, bureauTotals, categoryName, periodLabel } from './charts';
import {
  useAlertCount,
  useClearancesWaiting,
  useDash,
  useMatchesToConfirm,
  usePublicConfig,
  type AgeingRow,
  type BureauRow,
  type CategoryRow,
  type ClocksResponse,
  type Kpis,
  type RegionRow,
  type TopInstitutionRow,
  type TrendRow,
} from './api';
import { HELP } from './plain';
import { RANGE_OPTIONS, casesLink, useDashboardFilters, type DashFilters } from './filters';

const PANEL_H = 250;

type TabId = 'overview' | 'trends' | 'institutions' | 'alerts';

function isCurrentMonth(period: string): boolean {
  const d = new Date();
  return period.slice(0, 7) === `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** One plain sentence describing what the numbers cover. */
function summarySentence(f: DashFilters, total: number | undefined, open: number | undefined, regionLabel: string): string {
  const range = (RANGE_OPTIONS.find((r) => r.id === f.range)?.label ?? '').toLowerCase();
  const parts = [range || 'all time', f.bureau ? `${BUREAU_LABEL[f.bureau as keyof typeof BUREAU_LABEL] ?? f.bureau} bureau` : 'all bureaus'];
  if (f.ro) parts.push(`${regionLabel} region`);
  if (f.category) parts.push(`${(CATEGORY_LABEL[f.category as CaseCategory] ?? f.category).toLowerCase()} cases`);
  const head = total === undefined ? 'Loading cases' : `Showing ${formatNumber(total)} cases`;
  return `${head}, ${parts.join(', ')}.${open === undefined ? '' : ` ${formatNumber(open)} are still open.`}`;
}

export default function DashboardPage() {
  const { filters: f, roLocked } = useDashboardFilters();
  const { user } = useAuth();
  const [sp, setSp] = useSearchParams();
  const qc = useQueryClient();
  const fetching = useIsFetching({ queryKey: ['dash'] }) > 0;
  const isWork = user?.role !== 'SENIOR_MGMT'; // senior management has read-only oversight, no inboxes

  const tabRaw = sp.get('tab');
  const tab: TabId = tabRaw === 'trends' || tabRaw === 'institutions' || tabRaw === 'alerts' ? tabRaw : 'overview';
  const setTab = (id: string) =>
    setSp(
      (cur) => {
        const next = new URLSearchParams(cur);
        if (id === 'overview') next.delete('tab');
        else next.set('tab', id);
        return next;
      },
      { replace: true },
    );
  const tabHref = (id: TabId) => {
    const next = new URLSearchParams(sp);
    next.set('tab', id);
    return `/?${next.toString()}`;
  };

  const kpis = useDash<Kpis>('kpis', 'kpis', f);
  const byBureau = useDash<BureauRow[]>('by-bureau', 'by-bureau', f);
  const byCategory = useDash<CategoryRow[]>('by-category', 'by-category', f);
  const ageing = useDash<AgeingRow[]>('ageing', 'ageing', f);
  const trend = useDash<TrendRow[]>('trend', 'trend', f, { granularity: 'month' });
  const byRegion = useDash<RegionRow[]>('by-region', 'by-region', f);
  const top = useDash<TopInstitutionRow[]>('top-institutions', 'top-institutions', f, { limit: 10 });
  const clocks = useDash<ClocksResponse>('clocks', 'clocks', f);
  const pub = usePublicConfig().data;

  // "Open alerts" are links where both cases are open (GET /links?both_open=true), split by how urgent they are.
  const priority = useAlertCount(['CONFLICTING'], f);
  const coordination = useAlertCount(['RELATED', 'DUPLICATE'], f);
  const clearances = useClearancesWaiting(isWork);
  const matches = useMatchesToConfirm(isWork);

  const k = kpis.data;
  const openLink = casesLink(f, { status: OPEN_STATUSES });
  const refreshedAt = kpis.dataUpdatedAt ? new Date(kpis.dataUpdatedAt) : null;
  const alertsTotal = priority.data && coordination.data ? priority.data.total + coordination.data.total : undefined;

  const hidden = (e: unknown) => e instanceof ApiError && (e.status === 403 || e.status === 404);

  const overdueHint = useMemo(() => {
    const by = k?.overdue_by_clock;
    if (!by) return undefined;
    const label = (key: keyof ClocksResponse) => clockTitle(key, pub, clocks.data?.[key]);
    return ['A case counts once if any of its deadlines is past.', ...Object.keys(by).map((key) => `${label(key as keyof ClocksResponse)}: ${formatNumber(by[key] ?? 0)}`)].join('\n');
  }, [k?.overdue_by_clock, clocks.data, pub]);

  const attention: AttentionItem[] = [
    {
      key: 'late',
      label: 'Past deadline',
      hint: 'Open cases that missed at least one deadline',
      zeroHint: 'No case has missed a deadline',
      value: k?.overdue,
      loading: kpis.isLoading,
      to: casesLink(f, { overdue: true, anyStatus: true }),
      title: overdueHint,
      bar: 'var(--red)',
      ink: 'var(--red)',
      bg: 'var(--red-bg)',
    },
    {
      key: 'priority',
      label: 'Priority review',
      hint: 'Two bureaus may be acting against each other',
      zeroHint: 'No conflicting actions found',
      value: priority.data?.total,
      loading: priority.isLoading,
      to: isWork ? '/coordination?relation=CONFLICTING' : tabHref('alerts'),
      bar: 'var(--ink-900)',
      ink: 'var(--ink-900)',
      bg: 'var(--neutral-bg)',
    },
    {
      key: 'coordination',
      label: 'Coordination needed',
      hint: 'Same institution, more than one bureau',
      zeroHint: 'No overlapping cases found',
      value: coordination.data?.total,
      loading: coordination.isLoading,
      to: isWork ? '/coordination' : tabHref('alerts'),
      bar: 'var(--saffron)',
      ink: 'var(--amber)',
      bg: 'var(--saffron-bg)',
    },
  ];
  if (isWork && !hidden(clearances.error))
    attention.push({
      key: 'clearances',
      label: 'Clearances waiting for you',
      hint: 'Requests from other bureaus to answer',
      zeroHint: 'Nothing waiting for you',
      value: clearances.data?.total,
      loading: clearances.isLoading,
      to: '/clearances',
      bar: 'var(--amber)',
      ink: 'var(--amber)',
      bg: 'var(--amber-bg)',
    });
  if (isWork && !hidden(matches.error))
    attention.push({
      key: 'matches',
      label: 'Institution matches to confirm',
      hint: 'Complaints where the college needs your check',
      zeroHint: 'No matches waiting',
      value: matches.data?.total,
      loading: matches.isLoading,
      to: '/review',
      bar: 'var(--info)',
      ink: 'var(--info)',
      bg: 'var(--info-bg)',
    });

  /* summary and takeaways */
  const regionLabel = (byRegion.data ?? []).find((r) => r.ro_code === f.ro)?.city ?? f.ro;
  const bureauRows = useMemo(() => bureauTotals(byBureau.data ?? []), [byBureau.data]);
  const bureauSum = bureauRows.reduce((a, r) => a + r.total, 0);
  const ageSum = (ageing.data ?? []).reduce((a, r) => a + r.count, 0);
  const ageOld = (ageing.data ?? []).filter((r) => r.bucket === '61-180' || r.bucket === '180+').reduce((a, r) => a + r.count, 0);
  const oldest = (ageing.data ?? []).find((r) => r.bucket.endsWith('+'));
  const lastTrend = trend.data && trend.data.length ? trend.data[trend.data.length - 1] : null;
  const catTop = [...(byCategory.data ?? [])].sort((a, b) => b.open - a.open)[0];
  const regionTop = [...(byRegion.data ?? [])].sort((a, b) => b.open - a.open)[0];
  const regionRows = (byRegion.data ?? []).filter((r): r is LocatedRegion => r.lat != null && r.lng != null);

  const counts: { key: string; label: string; value: number | undefined; to: string }[] = [
    { key: 'total', label: 'All cases', value: k?.total, to: casesLink(f, { anyStatus: true }) },
    { key: 'pending', label: 'Still open', value: k?.pending, to: casesLink(f, { status: k?.definitions?.pending ?? OPEN_STATUSES }) },
    { key: 'worked', label: 'Being worked on', value: k?.under_process, to: casesLink(f, { status: k?.definitions?.under_process ?? ['UNDER_PROCESS', 'AWAITING_ATR', 'AWAITING_COMPLAINANT'] }) },
    { key: 'closed', label: 'Closed', value: k?.disposed, to: casesLink(f, { status: k?.definitions?.disposed ?? ['DISPOSED', 'CLOSED_NO_ACTION'] }) },
    { key: 'sent', label: 'Sent to another bureau', value: k?.transferred, to: casesLink(f, { status: 'TRANSFERRED' }) },
    { key: 'esc', label: 'Escalated to senior', value: k?.escalated, to: casesLink(f, { status: 'ESCALATED' }) },
  ];

  const topColumns: Column<TopInstitutionRow>[] = [
    {
      key: 'name',
      header: 'Institution',
      render: (r) => (
        <div className="min-w-0 py-1">
          <Link to={`/institutions/${r.institution_id}`} className="block max-w-[420px] truncate text-base text-ink-900" title={r.name}>
            {r.name}
          </Link>
          {r.permanent_id && <span className="mono text-xs text-ink-500">{r.permanent_id}</span>}
        </div>
      ),
    },
    { key: 'open', header: 'Open cases', numeric: true, render: (r) => <span className="text-base font-semibold">{formatNumber(r.open)}</span> },
    { key: 'overdue', header: 'Past deadline', numeric: true, render: (r) => <span className={r.overdue > 0 ? 'text-base font-semibold text-red' : 'text-base'}>{formatNumber(r.overdue)}</span> },
    { key: 'alerts', header: 'Alerts', numeric: true, render: (r) => <span className="text-base">{formatNumber(r.open_alerts)}</span> },
  ];

  const alertQuery: Record<string, string | string[]> = {};
  if (f.bureau) alertQuery.bureau = f.bureau;

  return (
    <div className="flex flex-col gap-4 text-base">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-ink-900">Oversight dashboard</h1>
        <div className="flex items-center gap-3 text-base text-ink-700">
          <span className="tnum" aria-live="polite">
            {roLocked && <span className="mr-3 text-ink-900">Region fixed to your Regional Office</span>}
            Updated {refreshedAt ? formatTime(refreshedAt) : '–'}
          </span>
          <Button variant="secondary" icon={RefreshCw} loading={fetching} onClick={() => void qc.invalidateQueries({ queryKey: ['dash'] }).then(() => qc.invalidateQueries({ queryKey: ['links'] }))}>
            Refresh
          </Button>
        </div>
      </div>

      <FilterBar />

      <div className="flex flex-col gap-2">
        <h2 className="text-md font-semibold text-ink-900">What needs your attention</h2>
        {kpis.error ? (
          <p className="rounded border border-line bg-surface p-3 text-base text-red">Could not load the figures. {kpis.error.message}</p>
        ) : (
          <AttentionRow items={attention} />
        )}
        <p className="text-base text-ink-700">
          {summarySentence(f, k?.total, k?.pending, regionLabel)}
        </p>
      </div>

      <Tabs
        ariaLabel="Dashboard sections"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: 'overview', label: 'Overview' },
          { id: 'trends', label: 'Trends' },
          { id: 'institutions', label: 'Institutions' },
          { id: 'alerts', label: 'Coordination alerts', count: alertsTotal },
        ]}
        className="[&_button]:!h-10 [&_button]:!text-base"
      />

      {tab === 'overview' && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-x-1 gap-y-1 rounded border border-line bg-surface" aria-label="Case counts">
            {counts.map((c, i) => (
              <Link key={c.key} to={c.to} className={`flex min-w-[130px] flex-1 items-baseline gap-2 px-4 py-2.5 text-ink-900 hover:bg-navy-50 hover:no-underline focus-ring ${i > 0 ? 'border-l border-line' : ''}`}>
                <span className="text-xl font-semibold tnum">{c.value === undefined ? '–' : formatNumber(c.value)}</span>
                <span className="text-sm text-ink-700">{c.label}</span>
              </Link>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <ChartPanel
              title="Open cases by bureau"
              help={HELP.bureau}
              tint="navy"
              takeaway={bureauRows[0] ? `${bureauName(bureauRows[0].bureau)} has the most open cases: ${formatNumber(bureauRows[0].total)} of ${formatNumber(bureauSum)}.` : undefined}
              to={openLink}
              loading={byBureau.isLoading}
              error={byBureau.error}
              onRetry={() => void byBureau.refetch()}
              empty={!!byBureau.data && bureauSum === 0}
              height={PANEL_H + 80}
            >
              <BureauStatusChart rows={byBureau.data ?? []} filters={f} height={PANEL_H + 80} />
            </ChartPanel>

            <ChartPanel
              title="Deadlines at a glance"
              help={HELP.deadlines}
              tint="amber"
              takeaway={k ? `${formatNumber(k.overdue)} open ${k.overdue === 1 ? 'case is' : 'cases are'} past a deadline.` : undefined}
              to={casesLink(f, { clock_state: 'BREACHED', anyStatus: true })}
              linkLabel="View late cases"
              loading={clocks.isLoading}
              error={clocks.error}
              onRetry={() => void clocks.refetch()}
              height={PANEL_H + 80}
            >
              {clocks.data && <ClocksPanelBody data={clocks.data} filters={f} pub={pub} />}
            </ChartPanel>

            <ChartPanel
              title="How old are open cases"
              help={HELP.ageing}
              tint="neutral"
              takeaway={ageSum ? `${formatNumber(ageOld)} of ${formatNumber(ageSum)} open cases are more than 60 days old${oldest && oldest.count > 0 ? `, ${formatNumber(oldest.count)} ${oldest.count === 1 ? 'is' : 'are'} ${ageingLabel(oldest.bucket).toLowerCase()}` : ''}.` : undefined}
              to={openLink}
              loading={ageing.isLoading}
              error={ageing.error}
              onRetry={() => void ageing.refetch()}
              empty={!!ageing.data && ageSum === 0}
              emptyMessage="No open cases match the current filters."
              height={PANEL_H}
            >
              <AgeingChart rows={ageing.data ?? []} height={PANEL_H} />
            </ChartPanel>

            <ChartPanel
              title="Where cases are"
              help={HELP.region}
              tint="info"
              takeaway={regionTop ? `${regionTop.city ?? regionTop.name} has the most open cases (${formatNumber(regionTop.open)}).` : undefined}
              to={openLink}
              loading={byRegion.isLoading}
              error={byRegion.error}
              onRetry={() => void byRegion.refetch()}
              empty={!!byRegion.data && regionRows.length === 0}
              emptyMessage="No Regional Office data for the current filters."
              height={PANEL_H}
            >
              <RegionPanelBody rows={regionRows} filters={f} height={PANEL_H} />
            </ChartPanel>
          </div>
        </div>
      )}

      {tab === 'trends' && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <ChartPanel
            title="Received and closed each month"
            help={HELP.trend}
            tint="info"
            takeaway={lastTrend ? `${periodLabel(lastTrend.period)}${isCurrentMonth(lastTrend.period) ? ' (so far)' : ''}: ${formatNumber(lastTrend.received)} received, ${formatNumber(lastTrend.disposed)} closed.` : undefined}
            to={casesLink(f, { anyStatus: true })}
            loading={trend.isLoading}
            error={trend.error}
            onRetry={() => void trend.refetch()}
            empty={!!trend.data && trend.data.length === 0}
            height={320}
          >
            <TrendChart rows={trend.data ?? []} height={320} />
          </ChartPanel>
          <ChartPanel
            title="Open cases by category"
            help={HELP.category}
            tint="navy"
            takeaway={catTop && catTop.open > 0 ? `${categoryName(catTop.category)} is the biggest category (${formatNumber(catTop.open)} open).` : undefined}
            to={openLink}
            loading={byCategory.isLoading}
            error={byCategory.error}
            onRetry={() => void byCategory.refetch()}
            empty={!!byCategory.data && byCategory.data.every((r) => r.open === 0)}
            emptyMessage="No open cases match the current filters."
            height={360}
          >
            <CategoryChart rows={byCategory.data ?? []} filters={f} height={360} />
          </ChartPanel>
        </div>
      )}

      {tab === 'institutions' && (
        <ChartPanel
          title="Institutions with the most open cases"
          help={HELP.institutions}
          tint="navy"
          to="/institutions?sort=open_cases_desc"
          linkLabel="View institutions"
          loading={false}
          height={200}
          padded={false}
        >
          <DataTable
            caption="Institutions with the most open cases"
            columns={topColumns}
            rows={top.data}
            rowKey={(r) => r.institution_id}
            loading={top.isLoading}
            errorMessage={top.error ? `Could not load institutions. ${top.error.message}` : undefined}
            emptyMessage="No open cases for the current filters."
            className="rounded-none border-0"
          />
        </ChartPanel>
      )}

      {tab === 'alerts' && (
        <ChartPanel
          title="Coordination alerts"
          help={HELP.alerts}
          tint="saffron"
          to={isWork ? '/coordination' : undefined}
          linkLabel="Open coordination inbox"
          loading={false}
          height={200}
          padded={false}
        >
          <CoordinationAlertsTable query={alertQuery} />
        </ChartPanel>
      )}
    </div>
  );
}
