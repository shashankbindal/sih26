import { useEffect, useMemo, useState } from 'react';
import { Download, FileText } from 'lucide-react';
import { Button, DataTable, Drawer, EmptyState, Field, Input, Panel, Select, Skeleton, Tabs, useToast, type Column } from '@/components/ui';
import { api, errorMessage } from '@/api/client';
import { useApiQuery } from '@/api/hooks';
import { BUREAUS, BUREAU_LABEL, CATEGORY_LABEL, type CaseCategory } from '@/lib/constants';
import { formatDateTime, formatNumber } from '@/lib/format';
import { useRegionOptions } from '@/features/dashboard/api';
import { downloadFile } from './download';
import { useAuth } from '@/auth';

interface ReportColumn {
  key: string;
  label: string;
}
interface ReportRow {
  group: string;
  group_key: string;
  opening_pending: number;
  received: number;
  disposed: number;
  closing_pending: number;
  overdue: number;
  avg_days_to_dispose: number | null;
}
interface PendencyReport {
  title: string;
  organisation: string;
  period_type: string;
  period_label: string;
  group_by: string;
  generated_at: string;
  generated_at_ist: string;
  generated_by: string;
  columns: ReportColumn[];
  rows: ReportRow[];
  totals: ReportRow;
  footer: string;
}

type Period = 'monthly' | 'quarterly';
type GroupBy = 'bureau' | 'region' | 'institution' | 'category';
const GROUP_LABEL: Record<GroupBy, string> = { bureau: 'Bureau', region: 'Region', institution: 'Institution', category: 'Category' };

function previousMonth(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}
function previousQuarter(): { year: number; q: number } {
  const d = new Date();
  const q = Math.floor(d.getMonth() / 3) + 1;
  return q === 1 ? { year: d.getFullYear() - 1, q: 4 } : { year: d.getFullYear(), q: q - 1 };
}

function DigestDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user } = useAuth();
  const [bureau, setBureau] = useState<string>(user && user.bureau !== 'ADMIN' ? user.bureau : 'PGRC');
  // The endpoint returns HTML, so it is fetched as a blob and read as text (api.get would JSON-parse it).
  const html = useHtml(open, bureau);
  return (
    <Drawer open={open} onClose={onClose} title="Weekly digest preview" subtitle="What the head of the selected bureau would receive. Synthetic data." width={640}>
      <div className="mb-3 max-w-[200px]">
        <Field label="Bureau">
          <Select value={bureau} onChange={(e) => setBureau(e.target.value)}>
            {BUREAUS.filter((b) => b !== 'ADMIN').map((b) => (
              <option key={b} value={b}>
                {BUREAU_LABEL[b]}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      {html.loading && <Skeleton height={240} />}
      {html.error && <EmptyState tone="error" message={`Could not load the digest. ${html.error}`} />}
      {html.value && <iframe title="Weekly digest" sandbox="" srcDoc={html.value} className="h-[520px] w-full rounded border border-line bg-surface" />}
    </Drawer>
  );
}

function useHtml(enabled: boolean, bureau: string): { value: string | null; loading: boolean; error: string | null } {
  const [state, setState] = useState<{ value: string | null; loading: boolean; error: string | null }>({ value: null, loading: false, error: null });
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    setState({ value: null, loading: true, error: null });
    api
      .get<Blob>('/reports/digest-preview', { params: { bureau }, blob: true })
      .then((b) => b.text())
      .then((t) => live && setState({ value: t, loading: false, error: null }))
      .catch((e: unknown) => live && setState({ value: null, loading: false, error: errorMessage(e) }));
    return () => {
      live = false;
    };
  }, [enabled, bureau]);
  return state;
}

export default function ReportsPage() {
  const { toast } = useToast();
  const regions = useRegionOptions();
  const [period, setPeriod] = useState<Period>('monthly');
  const [month, setMonth] = useState(previousMonth());
  const pq = previousQuarter();
  const [qYear, setQYear] = useState(pq.year);
  const [qNum, setQNum] = useState(pq.q);
  const [groupBy, setGroupBy] = useState<GroupBy>('bureau');
  const [bureau, setBureau] = useState('');
  const [ro, setRo] = useState('');
  const [category, setCategory] = useState('');
  const [busy, setBusy] = useState<'pdf' | 'csv' | null>(null);
  const [digest, setDigest] = useState(false);

  const params = useMemo(
    () => ({
      period,
      month: period === 'monthly' ? month : undefined,
      quarter: period === 'quarterly' ? `${qYear}-Q${qNum}` : undefined,
      group_by: groupBy,
      bureau: bureau || undefined,
      ro_code: ro || undefined,
      category: category || undefined,
    }),
    [period, month, qYear, qNum, groupBy, bureau, ro, category],
  );
  const valid = period === 'monthly' ? /^\d{4}-\d{2}$/.test(month) : qYear >= 2000 && qYear <= 2100;
  const q = useApiQuery<PendencyReport>(['reports', 'pendency'], '/reports/pendency', { params: { ...params, format: 'json' }, enabled: valid });

  const download = async (format: 'pdf' | 'csv') => {
    setBusy(format);
    try {
      const slug = period === 'monthly' ? month : `${qYear}-Q${qNum}`;
      await downloadFile('/reports/pendency', `pendency_${slug}_${groupBy}.${format}`, { ...params, format });
      toast(`Downloaded ${format.toUpperCase()} report.`, 'ok');
    } catch (e) {
      toast(`Could not download the report. ${errorMessage(e)}`, 'red');
    } finally {
      setBusy(null);
    }
  };

  const r = q.data;
  const columns: Column<ReportRow>[] = useMemo(() => {
    const cols = (r?.columns ?? []).filter((c) => c.key !== 'group'); // the group column is added below
    const first: Column<ReportRow> = {
      key: 'group',
      header: GROUP_LABEL[groupBy],
      render: (row) => <span className={row.group_key === '__total__' ? 'font-semibold' : ''}>{row.group}</span>,
    };
    return [
      first,
      ...cols.map<Column<ReportRow>>((c) => ({
        key: c.key,
        header: c.label,
        numeric: true,
        render: (row) => {
          const v = (row as unknown as Record<string, number | null>)[c.key];
          const text = c.key === 'avg_days_to_dispose' ? (v === null || v === undefined ? '–' : formatNumber(v, 1)) : formatNumber(v ?? 0);
          return <span className={row.group_key === '__total__' ? 'font-semibold' : ''}>{text}</span>;
        },
      })),
    ];
  }, [r?.columns, groupBy]);
  const tableRows = useMemo(() => (r ? [...r.rows, { ...r.totals, group: 'Total', group_key: '__total__' }] : undefined), [r]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-ink-900">Reports</h1>
        <Button variant="secondary" icon={FileText} onClick={() => setDigest(true)}>
          Weekly digest preview
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <Panel title="Pendency report builder">
          <div className="flex flex-col gap-3">
            <Tabs
              ariaLabel="Report period"
              value={period}
              onChange={(id) => setPeriod(id as Period)}
              tabs={[
                { id: 'monthly', label: 'Monthly' },
                { id: 'quarterly', label: 'Quarterly' },
              ]}
            />
            {period === 'monthly' ? (
              <Field label="Month" error={valid ? undefined : 'Pick a month.'}>
                <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
              </Field>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <Field label="Year">
                  <Input type="number" min={2000} max={2100} value={qYear} onChange={(e) => setQYear(Number(e.target.value))} className="tnum" />
                </Field>
                <Field label="Quarter">
                  <Select value={qNum} onChange={(e) => setQNum(Number(e.target.value))}>
                    <option value={1}>Q1 (Jan to Mar)</option>
                    <option value={2}>Q2 (Apr to Jun)</option>
                    <option value={3}>Q3 (Jul to Sep)</option>
                    <option value={4}>Q4 (Oct to Dec)</option>
                  </Select>
                </Field>
              </div>
            )}
            <Field label="Group by">
              <Select value={groupBy} onChange={(e) => setGroupBy(e.target.value as GroupBy)}>
                {(Object.keys(GROUP_LABEL) as GroupBy[]).map((g) => (
                  <option key={g} value={g}>
                    {GROUP_LABEL[g]}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="label-caps pt-1">Filters</div>
            <Field label="Bureau">
              <Select value={bureau} onChange={(e) => setBureau(e.target.value)}>
                <option value="">All bureaus</option>
                {BUREAUS.filter((b) => b !== 'ADMIN').map((b) => (
                  <option key={b} value={b}>
                    {BUREAU_LABEL[b]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Region">
              <Select value={ro} onChange={(e) => setRo(e.target.value)}>
                <option value="">All regions</option>
                {(regions.data ?? []).map((x) => (
                  <option key={x.ro_code} value={x.ro_code}>
                    {x.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Category">
              <Select value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">All categories</option>
                {(Object.keys(CATEGORY_LABEL) as CaseCategory[]).map((c) => (
                  <option key={c} value={c}>
                    {CATEGORY_LABEL[c]}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="flex gap-2 pt-1">
              <Button variant="primary" icon={Download} loading={busy === 'pdf'} disabled={!valid || busy !== null} onClick={() => void download('pdf')}>
                Download PDF
              </Button>
              <Button variant="secondary" icon={Download} loading={busy === 'csv'} disabled={!valid || busy !== null} onClick={() => void download('csv')}>
                Download CSV
              </Button>
            </div>
          </div>
        </Panel>

        <Panel title="Preview (same columns as the PDF)" padded={false}>
          {q.isLoading && (
            <div className="p-3" role="status" aria-label="Loading report">
              <Skeleton width="40%" height={16} />
              <Skeleton className="mt-2" width="60%" />
              <Skeleton className="mt-4" height={180} />
            </div>
          )}
          {q.error && <EmptyState tone="error" message={`Could not build the report. ${q.error.message}`} action={<Button onClick={() => void q.refetch()}>Retry</Button>} />}
          {r && (
            <div>
              <div className="border-b border-line px-4 py-3">
                <div className="label-caps">{r.organisation}</div>
                <h2 className="mt-0.5 text-md font-semibold text-ink-900">{r.title}</h2>
                <div className="mt-0.5 text-sm text-ink-700">
                  {r.period_label} <span className="text-ink-300">·</span> grouped by {GROUP_LABEL[groupBy].toLowerCase()}
                </div>
                <div className="mt-0.5 text-xs text-ink-500">
                  Generated {r.generated_at_ist || formatDateTime(r.generated_at)} by {r.generated_by}
                </div>
              </div>
              <DataTable
                compact
                caption={r.title}
                columns={columns}
                rows={tableRows}
                rowKey={(x) => x.group_key + x.group}
                emptyMessage="No cases in this period for the selected filters."
                maxHeight={440}
                className="rounded-none border-0"
              />
              <div className="border-t border-line px-4 py-2 text-xs text-ink-500">
                {r.footer}
                <div className="mt-0.5">Overdue counts cases still pending at the end of the period that had an overdue clock.</div>
              </div>
            </div>
          )}
        </Panel>
      </div>
      <DigestDrawer open={digest} onClose={() => setDigest(false)} />
    </div>
  );
}
