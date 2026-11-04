import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useApiQuery } from '@/api/hooks';
import { ApiError, errorMessage } from '@/api/client';
import { useAuth } from '@/auth';
import { BureauTag, StatusTag } from '@/components/domain';
import { Button, EmptyState, Panel, Skeleton, Tabs } from '@/components/ui';
import { CHANNEL_LABEL, type Bureau, type CaseStatus, type SourceChannel } from '@/lib/constants';
import { formatDateTime } from '@/lib/format';
import { ICON } from '@/lib/icons';
import { PassportPanel } from '../passport/PassportPanel';
import { CaseActionModal, canWorkCase, type ActionKind } from './CaseActions';
import { InstitutionSnapshot } from './InstitutionSnapshot';
import { LinkedCasesTab } from './LinkedCasesTab';
import { SummaryTab } from './SummaryTab';
import { ClockPills, type CaseDetail } from './shared';

const ATR_STEPS = ['INSTITUTION_ATR', 'REFUND_FOLLOWUP', 'SHOW_CAUSE_REPLY'];

function SourceRecordsTab({ c }: { c: CaseDetail }) {
  return (
    <Panel title="Source records" padded={false}>
      <p className="m-0 border-b border-line-soft px-3 py-2 text-xs text-ink-500">Original references are kept as received; they are never overwritten by a link or an institution match.</p>
      {c.source_refs.length === 0 ? (
        <EmptyState message="No source reference numbers were recorded for this case." />
      ) : (
        <table className="ls-table">
          <thead>
            <tr>
              <th scope="col">Channel</th>
              <th scope="col">Reference</th>
            </tr>
          </thead>
          <tbody>
            {c.source_refs.map((r) => (
              <tr key={`${r.channel}-${r.ref}`}>
                <td>{CHANNEL_LABEL[r.channel as SourceChannel] ?? r.channel}</td>
                <td className="id">{r.ref}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

export function CaseDetailPage() {
  const { id = '' } = useParams();
  const { user } = useAuth();
  const [sp, setSp] = useSearchParams();
  const tab = sp.get('tab') ?? 'summary';
  const [action, setAction] = useState<ActionKind | null>(null);
  const q = useApiQuery<CaseDetail>(['case', id], `/cases/${id}`);
  const c = q.data;

  if (q.isLoading) {
    return (
      <div role="status" aria-label="Loading case">
        <Skeleton width={220} height={24} />
        <div className="mt-4 grid grid-cols-3 gap-4">
          <div className="col-span-2 flex flex-col gap-3">
            <Skeleton height={140} />
            <Skeleton height={100} />
          </div>
          <Skeleton height={240} />
        </div>
      </div>
    );
  }
  if (q.isError || !c) {
    const notFound = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div>
        <Link to="/cases" className="text-sm">
          Back to case register
        </Link>
        <div className="mt-3 rounded border border-line bg-surface">
          <EmptyState tone="error" message={notFound ? 'This case does not exist or is outside your scope.' : `The case could not be loaded. ${errorMessage(q.error)}`} />
        </div>
      </div>
    );
  }

  const may = canWorkCase(user, c);
  const open = !['DISPOSED', 'CLOSED_NO_ACTION'].includes(c.status);
  const atrApplicable = c.status === 'AWAITING_ATR' || ATR_STEPS.includes(c.pending_step);

  const tabs = [
    { id: 'summary', label: 'Summary' },
    { id: 'passport', label: 'Case Passport' },
    { id: 'links', label: 'Linked cases', count: c.links.length },
    { id: 'sources', label: 'Source records', count: c.source_refs.length },
  ];

  return (
    <div>
      <Link to="/cases" className="mb-2 inline-flex items-center gap-1 text-xs text-ink-500 hover:text-navy">
        <ArrowLeft {...ICON} size={12} />
        Case register
      </Link>

      <header className="rounded border border-line bg-surface px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="font-mono text-xl font-semibold tnum text-ink-900">{c.display_id}</h1>
              <StatusTag status={c.status as CaseStatus} />
              {c.clocks.length > 0 && <ClockPills clocks={c.clocks} />}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-700">
              <span className="inline-flex items-center gap-2">
                <span className="text-xs text-ink-500">Owner</span>
                <BureauTag bureau={c.owner_bureau as Bureau} roCode={c.owner_ro_code} />
                {c.owner_officer ? (
                  <span>
                    {c.owner_officer.name}
                    {c.owner_officer.designation && <span className="text-ink-500">, {c.owner_officer.designation}</span>}
                  </span>
                ) : (
                  <span className="text-ink-500">unassigned</span>
                )}
              </span>
              <span className="text-xs text-ink-500">
                Received <span className="tnum text-ink-700">{formatDateTime(c.received_at)}</span> via {CHANNEL_LABEL[c.source_channel as SourceChannel] ?? c.source_channel}
                {c.source_ref && (
                  <>
                    {' · '}
                    <span className="font-mono tnum text-ink-700">{c.source_ref}</span>
                  </>
                )}
              </span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {may && open ? (
              <>
                <Button onClick={() => setAction('status')}>Update status</Button>
                <Button onClick={() => setAction('transfer')}>Transfer</Button>
                <Button onClick={() => setAction('remark')}>Add remark</Button>
                <Button onClick={() => setAction('atr')} disabled={!atrApplicable} title={atrApplicable ? undefined : 'No ATR is pending on this case'}>
                  Mark ATR received
                </Button>
                <Button variant="primary" onClick={() => setAction('dispose')}>
                  Dispose
                </Button>
              </>
            ) : may ? (
              <Button onClick={() => setAction('remark')}>Add remark</Button>
            ) : (
              <span className="text-xs text-ink-500">Read-only for your role: this case is owned by {c.owner_bureau}.</span>
            )}
          </div>
        </div>
      </header>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]">
        <div className="min-w-0">
          <Tabs
            ariaLabel="Case sections"
            tabs={tabs}
            value={tab}
            onChange={(t) => setSp(t === 'summary' ? {} : { tab: t }, { replace: true })}
            className="mb-3"
          />
          {tab === 'summary' && <SummaryTab caseData={c} />}
          {tab === 'passport' && (
            <Panel title="Case Passport">
              <PassportPanel path={`/cases/${c.id}/passport`} queryKey={['case', c.id]} />
            </Panel>
          )}
          {tab === 'links' && <LinkedCasesTab caseData={c} />}
          {tab === 'sources' && <SourceRecordsTab c={c} />}
        </div>
        <aside className="min-w-0 xl:mt-[45px]">
          <InstitutionSnapshot institutionId={c.institution?.id} currentCaseId={c.id} />
        </aside>
      </div>

      <CaseActionModal kind={action} caseData={c} onClose={() => setAction(null)} />
    </div>
  );
}
