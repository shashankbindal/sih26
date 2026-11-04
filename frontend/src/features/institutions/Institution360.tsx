import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { useApiQuery } from '@/api/hooks';
import { ApiError, errorMessage } from '@/api/client';
import { useAuth } from '@/auth';
import type { Schemas } from '@/api/types';
import { BureauTag, RelationBadge, StatusTag } from '@/components/domain';
import { Badge, Button, DataTable, DropdownMenu, EmptyState, KpiStrip, Panel, Skeleton, type Column, type KpiItem } from '@/components/ui';
import {
  BUREAUS,
  BUREAU_LABEL,
  CATEGORY_LABEL,
  INST_ACTION_LABEL,
  OPEN_STATUSES,
  PENDING_STEP_LABEL,
  type Bureau,
  type CaseCategory,
  type CaseStatus,
  type InstActionType,
  type PendingStep,
  type RelationType,
  type Role,
} from '@/lib/constants';
import { ageShort, formatDate, formatDateTime } from '@/lib/format';
import { ICON } from '@/lib/icons';
import { ClockPills, MaybeHindi, hasDevanagari, roName } from '../cases/shared';
import { APPROVAL_LABEL, APPROVAL_TONE } from './refData';
import { Swimlanes } from './Swimlanes';

type Detail = Schemas['InstitutionDetail'];
type Timeline = Schemas['InstitutionTimeline'];
type TimelineItem = Schemas['TimelineItem'];
type LinkOut = Schemas['InstitutionLinkOut'];

/** the API specification role table: Pre-Action Check may be started by Approval and RB officers, bureau heads and ADMIN. */
const PRE_ACTION_ROLES: Role[] = ['APPROVAL_OFFICER', 'RB_OFFICER', 'BUREAU_HEAD', 'ADMIN'];
const ACTION_ORDER: InstActionType[] = ['ISSUE_NOC', 'SECURITY_DEPOSIT_RELEASE', 'SHOW_CAUSE', 'CLOSURE_APPROVAL', 'EXTENSION_OF_APPROVAL', 'INSPECTION_ORDER'];

const SOURCE_LABEL: Record<string, string> = { SEED: 'register', OFFICIAL: 'register' };
const humanise = (s: string) => s.charAt(0) + s.slice(1).toLowerCase().replace(/_/g, ' ');

/* ------------------------------ timeline ------------------------------ */

function TimelinePanel({ items, loading, error }: { items: TimelineItem[] | undefined; loading: boolean; error?: string }) {
  const [scope, setScope] = useState<'open' | 'all'>('open');
  const [bureau, setBureau] = useState<string>('');
  const rows = useMemo(
    () =>
      (items ?? [])
        .filter((c) => scope === 'all' || OPEN_STATUSES.includes(c.status as CaseStatus))
        .filter((c) => !bureau || c.owner_bureau === bureau),
    [items, scope, bureau],
  );

  const columns: Column<TimelineItem>[] = [
    { key: 'received', header: 'Received', width: 104, render: (c) => <span className="tnum">{formatDate(c.received_at)}</span> },
    {
      key: 'case',
      header: 'Case',
      mono: true,
      width: 124,
      render: (c) => <Link to={`/cases/${c.id}`}>{c.display_id}</Link>,
    },
    { key: 'bureau', header: 'Bureau', width: 100, render: (c) => <BureauTag bureau={c.owner_bureau as Bureau} roCode={c.owner_ro_code} /> },
    { key: 'category', header: 'Category', render: (c) => <span className="text-xs">{CATEGORY_LABEL[c.category as CaseCategory] ?? c.category}</span> },
    { key: 'status', header: 'Status', width: 120, render: (c) => <StatusTag status={c.status as CaseStatus} /> },
    {
      key: 'pending',
      header: 'Pending',
      width: 140,
      render: (c) =>
        c.pending_step === 'NONE' ? (
          <span className="text-ink-300">{'–'}</span>
        ) : (
          <span className="text-xs">
            {PENDING_STEP_LABEL[c.pending_step as PendingStep] ?? c.pending_step}
            {c.pending_since && <span className="font-mono tnum text-ink-500"> {ageShort(c.pending_since)}</span>}
          </span>
        ),
    },
    { key: 'clocks', header: 'Policy clocks', width: 190, render: (c) => <ClockPills clocks={c.clocks} stacked /> },
    {
      key: 'relations',
      header: 'Relations',
      width: 220,
      render: (c) =>
        c.relations.length === 0 ? (
          <span className="text-ink-300">{'–'}</span>
        ) : (
          <span className="flex flex-col items-start gap-1">
            {c.relations.map((l) => (
              <span key={l.id} className="inline-flex items-center gap-1.5">
                <RelationBadge relation={l.relation as RelationType} />
                <Link to={`/cases/${l.other_case.id}`} className="font-mono text-xs tnum">
                  {l.other_case.display_id.slice(-6)}
                </Link>
              </span>
            ))}
          </span>
        ),
    },
  ];

  return (
    <Panel
      title={`Timeline · all bureaus${items ? ` (${rows.length})` : ''}`}
      padded={false}
      actions={
        <>
          <div role="group" aria-label="Scope" className="inline-flex overflow-hidden rounded border border-line text-xs">
            {(['open', 'all'] as const).map((s) => (
              <button
                key={s}
                type="button"
                aria-pressed={scope === s}
                onClick={() => setScope(s)}
                className={`focus-ring h-6 px-2.5 ${scope === s ? 'bg-navy-50 font-semibold text-ink-900' : 'bg-surface text-ink-500 hover:bg-paper'}`}
              >
                {s === 'open' ? 'Open' : 'All'}
              </button>
            ))}
          </div>
          <select
            aria-label="Bureau filter"
            value={bureau}
            onChange={(e) => setBureau(e.target.value)}
            className="focus-ring h-6 rounded border border-line bg-surface px-1.5 text-xs text-ink-900"
          >
            <option value="">All bureaus</option>
            {BUREAUS.filter((b) => b !== 'ADMIN').map((b) => (
              <option key={b} value={b}>
                {BUREAU_LABEL[b]}
              </option>
            ))}
          </select>
        </>
      }
    >
      <DataTable<TimelineItem>
        className="!rounded-none !border-0 [&_td]:!px-2 [&_td]:!py-1 [&_th]:!px-2"
        caption="Timeline of all cases on this institution"
        columns={columns}
        rows={rows}
        rowKey={(c) => c.id}
        loading={loading}
        errorMessage={error}
        emptyMessage={scope === 'open' ? 'No open matters match. Switch to All to see closed cases.' : 'No cases recorded for this institution.'}
        maxHeight={420}
      />
    </Panel>
  );
}

/* --------------------------- actions history --------------------------- */

interface ActionRow {
  id: string;
  action_type: string;
  status: string;
  initiated_bureau?: string | null;
  initiated_by_name?: string | null;
  open_matter_count?: number | null;
  created_at?: string | null;
}

function ActionsHistory({ institutionId }: { institutionId: string }) {
  const q = useApiQuery<ActionRow[] | { items: ActionRow[] }>(['institution-actions', institutionId], '/institution-actions', { params: { institution_id: institutionId } });
  const rows = Array.isArray(q.data) ? q.data : (q.data?.items ?? []);
  const unavailable = q.error instanceof ApiError && (q.error.status === 404 || q.error.status === 501);

  const columns: Column<ActionRow>[] = [
    { key: 'at', header: 'Started', width: 150, render: (a) => <span className="tnum">{formatDateTime(a.created_at)}</span> },
    { key: 'type', header: 'Action', render: (a) => INST_ACTION_LABEL[a.action_type as InstActionType] ?? humanise(a.action_type) },
    { key: 'status', header: 'Status', width: 130, render: (a) => <Badge tone={a.status === 'PROCEEDED' ? 'ok' : a.status === 'ON_HOLD' ? 'amber' : 'neutral'}>{humanise(a.status)}</Badge> },
    {
      key: 'by',
      header: 'Initiated by',
      width: 170,
      render: (a) => (
        <span className="inline-flex items-center gap-2">
          {a.initiated_bureau && <BureauTag bureau={a.initiated_bureau as Bureau} />}
          {a.initiated_by_name && <span className="text-xs text-ink-700">{a.initiated_by_name}</span>}
        </span>
      ),
    },
    { key: 'n', header: 'Open matters', numeric: true, width: 104, render: (a) => a.open_matter_count ?? '–' },
    { key: 'open', header: '', width: 70, render: (a) => <Link to={`/institutions/${institutionId}/pre-action/${a.id}`}>Open</Link> },
  ];

  return (
    <Panel title="Institution-level actions" padded={false}>
      {unavailable ? (
        <EmptyState message="Institution-level action history is not available from the server yet." />
      ) : (
        <DataTable<ActionRow>
          className="!rounded-none !border-0 [&_td]:!px-3"
          caption="Pre-Action Checks and clearances"
          columns={columns}
          rows={rows}
          rowKey={(a) => a.id}
          loading={q.isLoading}
          errorMessage={q.isError ? `The history could not be loaded. ${errorMessage(q.error)}` : undefined}
          emptyMessage="No Pre-Action Checks or clearances recorded for this institution."
          compact
        />
      )}
    </Panel>
  );
}

/* -------------------------------- page --------------------------------- */

export function Institution360() {
  const { id = '' } = useParams();
  const { user } = useAuth();
  const detail = useApiQuery<Detail>(['institution', id], `/institutions/${id}`);
  const timeline = useApiQuery<Timeline>(['institution', id, 'timeline'], `/institutions/${id}/timeline`);
  const links = useApiQuery<LinkOut[]>(['institution', id, 'links'], `/institutions/${id}/links`);
  const i = detail.data;

  if (detail.isLoading) {
    return (
      <div role="status" aria-label="Loading institution">
        <Skeleton width={420} height={24} />
        <Skeleton className="mt-2" width={560} height={14} />
        <Skeleton className="mt-4" height={72} />
        <Skeleton className="mt-4" height={220} />
      </div>
    );
  }
  if (detail.isError || !i) {
    const notFound = detail.error instanceof ApiError && detail.error.status === 404;
    return (
      <div>
        <Link to="/institutions" className="text-sm">
          Back to institutions
        </Link>
        <div className="mt-3 rounded border border-line bg-surface">
          <EmptyState tone="error" message={notFound ? 'This institution does not exist.' : `The institution could not be loaded. ${errorMessage(detail.error)}`} />
        </div>
      </div>
    );
  }

  const s = i.summary;
  const place = [i.district, i.state].filter(Boolean).join(', ') + (i.pincode ? ` ${i.pincode}` : '');
  const base = `/cases?institution_id=${i.id}`;
  const bureauKpis: KpiItem[] = BUREAUS.filter((b) => b !== 'ADMIN' && (s.open_by_bureau[b] ?? 0) > 0).map((b) => ({
    key: b,
    label: BUREAU_LABEL[b],
    value: s.open_by_bureau[b] ?? 0,
    to: `${base}&bureau=${b}`,
  }));
  const kpis: KpiItem[] = [
    { key: 'open', label: 'Open', value: s.open_total, to: base },
    ...bureauKpis,
    { key: 'overdue', label: 'Overdue by policy', value: s.overdue, to: `${base}&overdue=true` },
    { key: 'alerts', label: 'Coordination alerts', value: s.open_alerts, coordination: true, to: `${base}&has_alert=true` },
    { key: 'last', label: s.last_action_at ? `Last action · ${formatDate(s.last_action_at)}` : 'Last action', value: s.last_action_at ? `${ageShort(s.last_action_at)} ago` : 'None' },
  ];

  const canAct = !!user && PRE_ACTION_ROLES.includes(user.role);
  const aliases = i.aliases;

  return (
    <div className="flex flex-col gap-4">
      <header>
        <Link to="/institutions" className="mb-2 inline-block text-xs text-ink-500 hover:text-navy">
          Institutions
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold leading-tight text-ink-900">
              <MaybeHindi text={i.name} />
            </h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-700">
              <span className="font-mono tnum">{i.permanent_id}</span>
              {place && <span className="text-ink-500">{'·'}</span>}
              {place && <span>{place}</span>}
              {i.ro_code && (
                <>
                  <span className="text-ink-500">{'·'}</span>
                  <span>RO {roName(i.ro_code)}</span>
                </>
              )}
              {i.inst_type && (
                <>
                  <span className="text-ink-500">{'·'}</span>
                  <span>{i.inst_type}</span>
                </>
              )}
              <Badge tone={APPROVAL_TONE[i.approval_status] ?? 'neutral'}>{APPROVAL_LABEL[i.approval_status] ?? humanise(i.approval_status)}</Badge>
            </div>
            {i.address && <div className="mt-1 text-xs text-ink-500">{i.address}</div>}
            <div className="mt-1.5 text-sm text-ink-700">
              <span className="text-xs text-ink-500">Also known as: </span>
              {aliases.length === 0 ? (
                <span className="text-ink-500">no aliases recorded</span>
              ) : (
                aliases.map((a, n) => (
                  <span key={a.id}>
                    {n > 0 && <span className="text-ink-300">{' · '}</span>}
                    <span lang={hasDevanagari(a.alias_raw) ? 'hi' : undefined}>{a.alias_raw}</span>
                    <span className="text-xs text-ink-500"> ({SOURCE_LABEL[a.source] ?? humanise(a.source)})</span>
                  </span>
                ))
              )}
            </div>
          </div>
          {canAct && (
            <DropdownMenu
              align="right"
              width={248}
              header={<span className="text-xs text-ink-500">Opens the Pre-Action Check first. Advisory only.</span>}
              items={ACTION_ORDER.map((a) => ({ key: a, label: INST_ACTION_LABEL[a], to: `/institutions/${i.id}/pre-action/new?action=${a}` }))}
              trigger={({ open, toggle }) => (
                <Button variant="primary" aria-haspopup="menu" aria-expanded={open} onClick={toggle}>
                  Actions
                  <ChevronDown {...ICON} />
                </Button>
              )}
            />
          )}
        </div>
      </header>

      <KpiStrip items={kpis} />

      <Panel title="Open matters by bureau" padded={false}>
        {timeline.isLoading || links.isLoading ? (
          <div className="flex flex-col gap-3 p-3" role="status" aria-label="Loading swimlanes">
            <Skeleton height={64} />
            <Skeleton height={64} />
          </div>
        ) : timeline.isError ? (
          <EmptyState tone="error" message={`The matters could not be loaded. ${errorMessage(timeline.error)}`} />
        ) : (
          <>
            <Swimlanes items={timeline.data?.items ?? []} links={links.data ?? []} />
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line px-3 py-2 text-xs text-ink-500">
              <span className="inline-flex items-center gap-1.5">
                <span aria-hidden className="inline-block h-3 w-1" style={{ background: 'var(--saffron)' }} />
                Coordination required
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span aria-hidden className="inline-block h-3 w-1" style={{ background: 'var(--red)' }} />
                Priority review (conflicting)
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span aria-hidden className="inline-block h-3 w-1" style={{ background: 'var(--info)' }} />
                Review suggested (possible duplicate)
              </span>
              <span>Hover a card to highlight the cases linked to it.</span>
            </div>
          </>
        )}
      </Panel>

      <div className="grid items-start gap-4 2xl:grid-cols-[minmax(0,1fr)_460px]">
        <TimelinePanel items={timeline.data?.items} loading={timeline.isLoading} error={timeline.isError ? `The timeline could not be loaded. ${errorMessage(timeline.error)}` : undefined} />

        <ActionsHistory institutionId={i.id} />
      </div>
    </div>
  );
}
