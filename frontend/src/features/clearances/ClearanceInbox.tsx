import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { Schemas } from '@/api/types';
import { useApiMutation, useApiQuery } from '@/api/hooks';
import { BureauTag, ClearanceTag } from '@/components/domain';
import { Badge, Button, DataTable, Drawer, EmptyState, Field, Select, Skeleton, Tabs, Textarea, useToast, type Column } from '@/components/ui';
import {
  CASE_STATUS_LABEL,
  CATEGORY_LABEL,
  INST_ACTION_LABEL,
  PENDING_STEP_LABEL,
  type Bureau,
  type CaseCategory,
  type CaseStatus,
  type ClearanceResponse,
  type InstActionType,
  type PendingStep,
  type Tone,
} from '@/lib/constants';
import { formatDateTime } from '@/lib/format';
import { InlineError, PageHeader, errText } from '@/features/intake/shared';

type Clearance = Schemas['ClearanceOut'];
type ClearancePage = Schemas['ClearanceListPage'];
type ActionDetail = Schemas['InstitutionActionDetail'];
type Matter = Schemas['OpenMatter'];

const RESPONDED: ClearanceResponse[] = ['CLEARED', 'NOT_CLEARED', 'CLEARED_WITH_REMARKS'];
const REL_TONE: Record<Matter['relevance'], Tone> = { HIGH: 'red', MEDIUM: 'amber', LOW: 'neutral' };
const REL_LABEL: Record<Matter['relevance'], string> = { HIGH: 'High', MEDIUM: 'Medium', LOW: 'Low' };

function Snapshot({ actionId }: { actionId: string }) {
  const q = useApiQuery<ActionDetail>(['preaction', actionId], `/institution-actions/${actionId}`);
  if (q.isLoading) return <Skeleton height={120} />;
  if (q.isError || !q.data) return <InlineError>{q.error ? errText(q.error) : 'The Pre-Action snapshot could not be loaded.'}</InlineError>;
  const snap = q.data.panel as unknown as Partial<Schemas['PreActionPanel']>;
  const matters = snap.open_matters ?? [];
  return (
    <div className="flex flex-col gap-2">
      {snap.rule_note && <p className="m-0 text-sm text-ink-700">Rule: {snap.rule_note}</p>}
      <p className="m-0 text-xs text-ink-500">{snap.advisory ?? 'Advisory only. The competent authority decides.'}</p>
      {matters.length === 0 ? (
        <EmptyState message="No open matters were listed when the check was shown." />
      ) : (
        <ul className="m-0 list-none rounded border border-line p-0">
          {matters.map((m) => (
            <li key={m.case_id} className="border-b border-line-soft px-3 py-2 last:border-b-0">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                <Badge tone={REL_TONE[m.relevance]}>{REL_LABEL[m.relevance]}</Badge>
                <Link to={`/cases/${m.case_id}`} className="font-mono tnum">
                  {m.display_id}
                </Link>
                <BureauTag bureau={m.owner_bureau as Bureau} />
                <span className="text-ink-700">{CATEGORY_LABEL[m.category as CaseCategory]}</span>
              </div>
              <div className="mt-1 text-xs text-ink-500">
                {CASE_STATUS_LABEL[m.status as CaseStatus]}
                {m.pending_step !== 'NONE' && ` · ${PENDING_STEP_LABEL[m.pending_step as PendingStep]} ${m.pending_days} d`}
                {m.clocks.length > 0 && ` · ${m.clocks.map((c) => c.label).join(' · ')}`}
              </div>
              <div className="mt-0.5 text-xs text-ink-700">{m.why}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RespondForm({ item, onDone }: { item: Clearance; onDone: () => void }) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const [response, setResponse] = useState<'CLEARED' | 'NOT_CLEARED' | 'CLEARED_WITH_REMARKS'>('CLEARED');
  const [remarks, setRemarks] = useState('');
  const [error, setError] = useState<string | null>(null);
  const needsRemarks = response !== 'CLEARED';
  const missing = needsRemarks && remarks.trim().length < 3;
  const send = useApiMutation<Clearance, void>(() => api.post<Clearance>(`/clearances/${item.id}/respond`, { response, remarks: remarks.trim() || null }), {
    onSuccess: () => {
      setError(null);
      toast('Response sent to the requesting bureau.', 'ok');
      for (const k of ['clearances', 'preaction', 'count']) void qc.invalidateQueries({ queryKey: [k] });
      onDone();
    },
    onError: (e) => setError(errText(e)),
  });
  return (
    <div className="flex flex-col gap-3">
      <Field label="Response" required>
        <Select value={response} onChange={(e) => setResponse(e.target.value as typeof response)}>
          <option value="CLEARED">Cleared</option>
          <option value="NOT_CLEARED">Not cleared</option>
          <option value="CLEARED_WITH_REMARKS">Cleared with remarks</option>
        </Select>
      </Field>
      <Field label="Remarks" required={needsRemarks} hint={needsRemarks ? 'Required for this response.' : 'Optional.'} error={needsRemarks && missing && remarks.length > 0 ? 'Enter at least 3 characters.' : undefined}>
        <Textarea rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
      </Field>
      {error && <InlineError>{error}</InlineError>}
      <div>
        <Button variant="primary" disabled={missing} loading={send.isPending} onClick={() => send.mutate()}>
          Send response
        </Button>
      </div>
    </div>
  );
}

function Detail({ item, onClose }: { item: Clearance; onClose: () => void }) {
  const pending = item.response === 'PENDING';
  return (
    <Drawer
      open
      onClose={onClose}
      width={640}
      title={`${INST_ACTION_LABEL[item.action_type as InstActionType]} · ${item.step_label}`}
      subtitle={
        <span>
          {item.institution.name} · <span className="font-mono tnum">{item.institution.permanent_id}</span>
        </span>
      }
    >
      <div className="flex flex-col gap-5">
        <section>
          <div className="label-caps mb-1.5 text-ink-500">Request</div>
          <dl className="m-0 grid gap-x-4 gap-y-1.5 text-sm" style={{ gridTemplateColumns: '120px minmax(0, 1fr)' }}>
            <dt className="text-ink-500">Requested</dt>
            <dd className="m-0 tnum">{formatDateTime(item.requested_at)}</dd>
            <dt className="text-ink-500">Requested by</dt>
            <dd className="m-0 flex items-center gap-2">
              {item.requested_by.name}
              {item.requested_by.bureau && <BureauTag bureau={item.requested_by.bureau as Bureau} />}
            </dd>
            <dt className="text-ink-500">Open matters</dt>
            <dd className="m-0 tnum">{item.open_matter_count}</dd>
            <dt className="text-ink-500">Status</dt>
            <dd className="m-0">
              <ClearanceTag response={item.response as ClearanceResponse} />
            </dd>
            {item.request_remark && (
              <>
                <dt className="text-ink-500">Remark</dt>
                <dd className="m-0">{item.request_remark}</dd>
              </>
            )}
          </dl>
        </section>

        <section>
          <div className="label-caps mb-1.5 text-ink-500">{pending ? 'Your response' : 'Response'}</div>
          {pending ? (
            <RespondForm item={item} onDone={onClose} />
          ) : (
            <div className="text-sm">
              <div className="flex items-center gap-2">
                <ClearanceTag response={item.response as ClearanceResponse} />
                {item.responded_by && <span className="text-ink-700">{item.responded_by.name}</span>}
                {item.responded_at && <span className="text-xs text-ink-500 tnum">{formatDateTime(item.responded_at)}</span>}
              </div>
              {item.remarks && <p className="m-0 mt-2 text-ink-700">Remarks: {item.remarks}</p>}
            </div>
          )}
        </section>
        <section>
          <div className="label-caps mb-1.5 text-ink-500">Pre-Action snapshot (read-only)</div>
          <Snapshot actionId={item.institution_action_id} />
        </section>

      </div>
    </Drawer>
  );
}

export default function ClearanceInbox() {
  const [tab, setTab] = useState<'pending' | 'responded'>('pending');
  const [open, setOpen] = useState<Clearance | null>(null);
  const pending = useApiQuery<ClearancePage>(['clearances', 'pending'], '/clearances', { params: { inbox: 'me', status: ['PENDING'] }, refetchInterval: 10_000 });
  const responded = useApiQuery<ClearancePage>(['clearances', 'responded'], '/clearances', { params: { inbox: 'me', status: RESPONDED }, refetchInterval: 30_000 });
  const cur = tab === 'pending' ? pending : responded;

  const columns: Column<Clearance>[] = [
    { key: 'requested', header: 'Requested on', width: 160, render: (r) => <span className="tnum">{formatDateTime(r.requested_at)}</span> },
    {
      key: 'inst',
      header: 'Institution',
      render: (r) => (
        <div className="flex flex-col">
          <span className="font-medium text-ink-900">{r.institution.name}</span>
          <span className="font-mono text-xs tnum text-ink-500">{r.institution.permanent_id}</span>
        </div>
      ),
    },
    { key: 'action', header: 'Action type', width: 170, render: (r) => INST_ACTION_LABEL[r.action_type as InstActionType] },
    {
      key: 'by',
      header: 'Requested by',
      width: 170,
      render: (r) => (
        <div className="flex flex-col gap-0.5">
          {r.requested_by.bureau ? <BureauTag bureau={r.requested_by.bureau as Bureau} /> : null}
          <span className="text-xs text-ink-500">{r.requested_by.name}</span>
        </div>
      ),
    },
    { key: 'step', header: 'Step', width: 190, render: (r) => <span><span className="font-mono text-xs tnum text-ink-500">{r.step_order}</span> {r.step_label}</span> },
    { key: 'status', header: 'Status', width: 150, render: (r) => <ClearanceTag response={r.response as ClearanceResponse} /> },
  ];

  return (
    <div>
      <PageHeader title="Clearance inbox" subtitle="Clearance requests addressed to your bureau. A response is visible to the requesting officer within seconds." />
      <Tabs
        ariaLabel="Clearance status"
        className="mb-3"
        tabs={[
          { id: 'pending', label: 'Pending', count: pending.data?.total },
          { id: 'responded', label: 'Responded', count: responded.data?.total },
        ]}
        value={tab}
        onChange={(id) => setTab(id as 'pending' | 'responded')}
      />
      <DataTable
        caption="Clearance requests"
        columns={columns}
        rows={cur.data?.items}
        rowKey={(r) => r.id}
        loading={cur.isLoading}
        errorMessage={cur.isError ? errText(cur.error) : undefined}
        emptyMessage={tab === 'pending' ? 'No clearance requests are waiting for your bureau.' : 'No responded requests yet.'}
        onRowClick={setOpen}
        selectedKey={open?.id ?? null}
      />
      {open && <Detail key={open.id} item={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
