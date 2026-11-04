import { useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { Schemas } from '@/api/types';
import { useApiMutation, useApiQuery } from '@/api/hooks';
import { BureauTag, ClockPill, LinkStatusTag, MaskedValue, ReasonList, RelationBadge, ScoreMeter, StatusTag } from '@/components/domain';
import { Badge, Button, EmptyState, Field, Modal, Panel, Select, Skeleton, Textarea, useToast } from '@/components/ui';
import {
  CATEGORY_LABEL,
  CHANNEL_LABEL,
  PENDING_STEP_LABEL,
  type Bureau,
  type CaseCategory,
  type CaseStatus,
  type LinkStatus,
  type PendingStep,
  type RelationType,
  type SourceChannel,
} from '@/lib/constants';
import { formatDate, formatDateTime, formatScore } from '@/lib/format';
import { InlineError, LinkDecisionModal, MaybeHindi, PageHeader, errText, type LinkDecisionKind } from '@/features/intake/shared';

type LinkDetail = Schemas['LinkDetail'];
type CaseDetail = Schemas['CaseDetail'];
type Thread = Schemas['ThreadOut'];

interface Row {
  label: string;
  a: ReactNode;
  b: ReactNode;
  /** String forms used to decide whether the row differs. */
  ka: string;
  kb: string;
  tall?: boolean;
}

function clocksNode(c: CaseDetail): ReactNode {
  if (!c.clocks.length) return <span className="text-ink-300">{'–'}</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {c.clocks.map((k) => (
        <ClockPill key={k.clock} label={k.label} state={k.state} clock={k.clock} clause={k.rule} />
      ))}
    </span>
  );
}

function buildRows(a: CaseDetail, b: CaseDetail): Row[] {
  const text = (v: string | null | undefined) => v ?? '';
  const pend = (c: CaseDetail) => (c.pending_step === 'NONE' ? (c.pending_action ?? 'None') : PENDING_STEP_LABEL[c.pending_step as PendingStep] + (c.pending_action ? ` · ${c.pending_action}` : ''));
  const complainant = (c: CaseDetail): ReactNode =>
    c.masked_fields.some((f) => f.startsWith('complainant')) || c.masked ? <MaskedValue ownerBureau={c.owner_bureau} /> : <span>{c.complainant.name ?? '–'}</span>;
  const desc = (c: CaseDetail): ReactNode =>
    c.description ? <MaybeHindi text={c.description} /> : c.masked ? <MaskedValue ownerBureau={c.owner_bureau} /> : <span className="text-ink-300">{'–'}</span>;
  return [
    { label: 'Case', a: <Link to={`/cases/${a.id}`} className="font-mono tnum">{a.display_id}</Link>, b: <Link to={`/cases/${b.id}`} className="font-mono tnum">{b.display_id}</Link>, ka: '', kb: '' },
    { label: 'Owner bureau', a: <BureauTag bureau={a.owner_bureau as Bureau} />, b: <BureauTag bureau={b.owner_bureau as Bureau} />, ka: a.owner_bureau, kb: b.owner_bureau },
    { label: 'Owner officer', a: text(a.owner_officer?.name) || '–', b: text(b.owner_officer?.name) || '–', ka: text(a.owner_officer?.name), kb: text(b.owner_officer?.name) },
    { label: 'Institution', a: a.institution?.name ?? '–', b: b.institution?.name ?? '–', ka: text(a.institution?.id), kb: text(b.institution?.id) },
    { label: 'Category', a: CATEGORY_LABEL[a.category as CaseCategory], b: CATEGORY_LABEL[b.category as CaseCategory], ka: a.category, kb: b.category },
    { label: 'Channel', a: CHANNEL_LABEL[a.source_channel as SourceChannel], b: CHANNEL_LABEL[b.source_channel as SourceChannel], ka: a.source_channel, kb: b.source_channel },
    { label: 'Received', a: <span className="tnum">{formatDate(a.received_at)}</span>, b: <span className="tnum">{formatDate(b.received_at)}</span>, ka: formatDate(a.received_at), kb: formatDate(b.received_at) },
    { label: 'Status', a: <StatusTag status={a.status as CaseStatus} />, b: <StatusTag status={b.status as CaseStatus} />, ka: a.status, kb: b.status },
    { label: 'Pending step', a: pend(a), b: pend(b), ka: pend(a), kb: pend(b) },
    { label: 'Clocks', a: clocksNode(a), b: clocksNode(b), ka: a.clocks.map((c) => c.clock + c.state).join(), kb: b.clocks.map((c) => c.clock + c.state).join() },
    { label: 'Complainant', a: complainant(a), b: complainant(b), ka: a.masked ? 'masked' : text(a.complainant.name), kb: b.masked ? 'masked' : text(b.complainant.name) },
    { label: 'Subject', a: <MaybeHindi text={a.subject} />, b: <MaybeHindi text={b.subject} />, ka: a.subject, kb: b.subject, tall: true },
    { label: 'Description', a: desc(a), b: desc(b), ka: a.description ? 'text:' + a.description : (a.masked ? 'masked' : ''), kb: b.description ? 'text:' + b.description : (b.masked ? 'masked' : ''), tall: true },
  ];
}

function CompareTable({ a, b }: { a: CaseDetail; b: CaseDetail }) {
  const rows = buildRows(a, b);
  return (
    <div className="overflow-auto">
      <table className="ls-table" style={{ tableLayout: 'fixed' }}>
        <caption className="sr-only">Side-by-side comparison of the two cases. Rows that differ are shaded.</caption>
        <thead>
          <tr>
            <th scope="col" style={{ width: 130 }}>Field</th>
            <th scope="col">Case A</th>
            <th scope="col">Case B</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const diff = r.ka !== r.kb;
            const shade = diff ? { background: 'var(--paper)' } : undefined;
            return (
              <tr key={r.label} style={{ height: 'auto' }}>
                <th scope="row" className="!font-medium !normal-case !tracking-normal text-ink-500" style={{ background: 'var(--surface)', textAlign: 'left', paddingLeft: 12, paddingRight: 8, boxShadow: diff ? 'inset 2px 0 0 var(--navy)' : undefined }}>
                  {r.label}
                  {diff && <span className="sr-only"> (differs)</span>}
                </th>
                <td className="whitespace-normal align-top" style={shade}>
                  <div className="py-1.5">{r.a}</div>
                </td>
                <td className="whitespace-normal align-top" style={shade}>
                  <div className="py-1.5">{r.b}</div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function formatFeature(v: Schemas['FeatureRow']['value']): string {
  if (v === null || v === undefined) return '–';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return String(v);
}

function RevertModal({ linkId, onClose, onDone }: { linkId: string; onClose: () => void; onDone: () => void }) {
  const { toast } = useToast();
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const rev = useApiMutation<LinkDetail, void>(() => api.post<LinkDetail>(`/links/${linkId}/revert`, { reason: reason.trim() }), {
    onSuccess: () => {
      toast('Reverted to the previous version.', 'ok');
      onDone();
      onClose();
    },
    onError: (e) => setError(errText(e)),
  });
  return (
    <Modal
      open
      onClose={rev.isPending ? () => undefined : onClose}
      title="Revert to previous version"
      footer={
        <>
          <Button onClick={onClose} disabled={rev.isPending}>Cancel</Button>
          <Button variant="primary" loading={rev.isPending} disabled={reason.trim().length < 3} onClick={() => rev.mutate()}>
            Revert
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label="Reason" required hint="Required (at least 3 characters).">
          <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
        </Field>
        {error && <InlineError>{error}</InlineError>}
      </div>
    </Modal>
  );
}

function ThreadPanel({ link, onChanged }: { link: LinkDetail; onChanged: () => void }) {
  const { toast } = useToast();
  const t: Thread | null | undefined = link.thread;
  const [body, setBody] = useState('');
  const [error, setError] = useState<string | null>(null);
  const post = useApiMutation<Thread, string>((b) => api.post<Thread>(`/links/${link.id}/thread/messages`, { body: b }), {
    onSuccess: () => {
      setBody('');
      setError(null);
      onChanged();
    },
    onError: (e) => setError(errText(e)),
  });
  const [lead, setLead] = useState<string>(t?.lead_bureau ?? link.lead_bureau ?? '');
  const [next, setNext] = useState<string>(t?.shared_next_action ?? link.suggested_next_action ?? '');
  const patch = useApiMutation<Thread, void>(() => api.patch<Thread>(`/links/${link.id}/thread`, { lead_bureau: lead || null, shared_next_action: next.trim() || null }), {
    onSuccess: () => {
      toast('Shared next action saved.', 'ok');
      setError(null);
      onChanged();
    },
    onError: (e) => setError(errText(e)),
  });
  return (
    <Panel title="Coordination thread">
      <div className="flex flex-col gap-4">
        <div className="grid gap-3" style={{ gridTemplateColumns: '180px minmax(0, 1fr)' }}>
          <Field label="Lead bureau">
            <Select value={lead} onChange={(e) => setLead(e.target.value)}>
              <option value="">Not set</option>
              {(['PGRC', 'RB', 'APPROVAL', 'VIGILANCE', 'RO'] as Bureau[]).map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </Select>
          </Field>
          <Field label="Shared next action">
            <Textarea rows={2} value={next} onChange={(e) => setNext(e.target.value)} />
          </Field>
        </div>
        <div>
          <Button loading={patch.isPending} onClick={() => patch.mutate()}>Save shared action</Button>
        </div>
        <div>
          <div className="label-caps mb-1.5 text-ink-500">Notes</div>
          {(t?.messages ?? []).length === 0 ? (
            <p className="m-0 text-sm text-ink-500">No notes yet.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {t!.messages.map((m) => (
                <li key={m.id} className="rounded border border-line-soft px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-ink-500">
                    <span className="font-medium text-ink-900">{m.author_name}</span>
                    {m.author_bureau && <BureauTag bureau={m.author_bureau as Bureau} />}
                    <span className="tnum">{formatDateTime(m.created_at)}</span>
                  </div>
                  <p className="m-0 mt-1 text-sm text-ink-700">{m.body}</p>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-2 flex items-start gap-2">
            <Textarea rows={2} value={body} onChange={(e) => setBody(e.target.value)} aria-label="Add a note visible to both bureaus" placeholder="Add a note visible to both bureaus" />
            <Button disabled={!body.trim()} loading={post.isPending} onClick={() => post.mutate(body.trim())}>Add note</Button>
          </div>
        </div>
        {error && <InlineError>{error}</InlineError>}
      </div>
    </Panel>
  );
}

export default function LinkCompare() {
  const { linkId = '' } = useParams();
  const qc = useQueryClient();
  const q = useApiQuery<LinkDetail>(['link', linkId], `/links/${linkId}`);
  const [deciding, setDeciding] = useState<LinkDecisionKind | null>(null);
  const [reverting, setReverting] = useState(false);
  const refresh = () => {
    for (const k of ['link', 'links', 'count', 'case', 'cases']) void qc.invalidateQueries({ queryKey: [k] });
  };

  if (q.isLoading) {
    return (
      <div className="flex flex-col gap-3" role="status" aria-label="Loading link">
        <Skeleton height={64} />
        <Skeleton height={140} />
        <Skeleton height={320} />
      </div>
    );
  }
  if (q.isError || !q.data) {
    return (
      <div>
        <PageHeader title="Link compare" />
        <InlineError>{q.error ? errText(q.error) : 'The link could not be loaded.'}</InlineError>
        <p className="mt-3 text-sm"><Link to="/coordination">Back to the coordination inbox</Link></p>
      </div>
    );
  }

  const l = q.data;
  const final = l.status === 'SUPERSEDED';
  const canRevert = l.can_decide && l.history.length > 1 && !final;
  const label = `${l.case_a.display_id} / ${l.case_b.display_id}`;

  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            <span>Link compare</span>
            <RelationBadge relation={l.relation as RelationType} />
            <LinkStatusTag status={l.status as LinkStatus} />
            <span className="font-mono text-xs font-normal tnum text-ink-500">v{l.version}</span>
          </span>
        }
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {l.institution && (
              <span>
                <Link to={`/institutions/${l.institution.id}`}>{l.institution.name}</Link>{' '}
                <span className="font-mono text-xs tnum">{l.institution.permanent_id}</span>
              </span>
            )}
            <Link to="/coordination">Coordination inbox</Link>
          </span>
        }
      />

      <div className="grid items-start gap-3" style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)' }}>
        <Panel title="Why these cases are linked">
          <div className="mb-3 flex items-center gap-3 border-b border-line-soft pb-3">
            <span className="label-caps text-ink-500">Link score</span>
            <ScoreMeter score={l.score} width={180} />
          </div>
          {l.reasons.length ? <ReasonList reasons={l.reasons} numbered /> : <EmptyState message="No reasons were recorded." />}
        </Panel>
        <Panel title="Feature scores" padded={false}>
          <table className="ls-table compact">
            <caption className="sr-only">Features used by the relationship check</caption>
            <thead>
              <tr>
                <th scope="col">Feature</th>
                <th scope="col" className="num" style={{ textAlign: 'right', width: 90 }}>Value</th>
              </tr>
            </thead>
            <tbody>
              {l.feature_rows.map((f) => (
                <tr key={f.key}>
                  <td>{f.label}</td>
                  <td className="num id">{formatFeature(f.value)}</td>
                </tr>
              ))}
              <tr>
                <td className="font-medium">Overall score</td>
                <td className="num id font-semibold">{formatScore(l.score)}</td>
              </tr>
            </tbody>
          </table>
        </Panel>
      </div>

      <Panel title="Case A and Case B" padded={false}>
        <CompareTable a={l.case_a} b={l.case_b} />
      </Panel>

      <div className="grid items-start gap-3" style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)' }}>
        <Panel title="Suggested shared next action">
          <p className="m-0 text-sm text-ink-900">{l.suggested_next_action ?? 'No shared action suggested.'}</p>
          <p className="m-0 mt-2 flex items-center gap-2 text-sm text-ink-700">
            Lead bureau suggestion: {l.lead_bureau ? <BureauTag bureau={l.lead_bureau as Bureau} /> : <span className="text-ink-500">none</span>}
            <span className="text-xs text-ink-500">Advisory. The bureaus agree the lead.</span>
          </p>
        </Panel>
        <Panel title="Decision">
          {l.decided_at && (
            <p className="m-0 mb-2 text-sm text-ink-700">
              {l.decided_by_name ?? 'An officer'} decided on {formatDateTime(l.decided_at)}
              {l.decision_reason ? `: ${l.decision_reason}` : ''}
            </p>
          )}
          {l.can_decide && !final ? (
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="primary" disabled={l.status === 'CONFIRMED'} onClick={() => setDeciding('CONFIRM')}>Confirm link</Button>
              <Button disabled={l.status === 'REJECTED'} onClick={() => setDeciding('REJECT')}>Reject link</Button>
              <Button disabled={l.status === 'DEFERRED'} onClick={() => setDeciding('DEFER')}>Defer</Button>
              {canRevert && <Button variant="tertiary" onClick={() => setReverting(true)}>Revert to previous version</Button>}
            </div>
          ) : (
            <p className="m-0 text-sm text-ink-500">
              {final ? 'This version has been superseded.' : 'Only the owners of the two cases, bureau heads and administrators can decide this link.'}
            </p>
          )}
          <p className="m-0 mt-2 text-xs text-ink-500">Every decision needs a reason and is kept as a new version. Cases are never merged.</p>
        </Panel>
      </div>

      <Panel title="Version history" padded={false}>
        <table className="ls-table compact">
          <caption className="sr-only">Versions of this link</caption>
          <thead>
            <tr>
              <th scope="col" style={{ width: 60 }}>Version</th>
              <th scope="col" style={{ width: 170 }}>Relation</th>
              <th scope="col" style={{ width: 110 }}>Status</th>
              <th scope="col" className="num" style={{ textAlign: 'right', width: 70 }}>Score</th>
              <th scope="col" style={{ width: 160 }}>Decided by</th>
              <th scope="col" style={{ width: 170 }}>Decided at</th>
              <th scope="col">Reason</th>
            </tr>
          </thead>
          <tbody>
            {l.history.map((h) => (
              <tr key={h.version}>
                <td className="id">v{h.version}{h.current && <Badge tone="info" className="ml-2">Current</Badge>}</td>
                <td><RelationBadge relation={h.relation as RelationType} /></td>
                <td><LinkStatusTag status={h.status as LinkStatus} /></td>
                <td className="num id">{formatScore(h.score)}</td>
                <td>{h.decided_by_name ?? <span className="text-ink-300">{'–'}</span>}</td>
                <td className="tnum">{h.decided_at ? formatDateTime(h.decided_at) : <span className="text-ink-300">{'–'}</span>}</td>
                <td className="whitespace-normal text-ink-700">{h.decision_reason ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <ThreadPanel key={`${l.id}-${l.version}`} link={l} onChanged={refresh} />

      {deciding && <LinkDecisionModal linkId={l.id} label={label} decision={deciding} onClose={() => setDeciding(null)} onDone={refresh} />}
      {reverting && <RevertModal linkId={l.id} onClose={() => setReverting(false)} onDone={refresh} />}
    </div>
  );
}
