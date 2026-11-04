import { Fragment, useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { Schemas } from '@/api/types';
import { useApiMutation, useApiQuery } from '@/api/hooks';
import { BureauTag, ClearanceTag, ClockPill, PassportTimeline, RelationBadge, type ChainVerification } from '@/components/domain';
import { Badge, Button, Checkbox, EmptyState, Field, Panel, Skeleton, Textarea, useToast } from '@/components/ui';
import {
  CASE_STATUS_LABEL,
  CATEGORY_LABEL,
  INST_ACTION_LABEL,
  PENDING_STEP_LABEL,
  type Bureau,
  type CaseCategory,
  type CaseStatus,
  type ClearanceResponse,
  type ClockState,
  type ClockType,
  type InstActionType,
  type PendingStep,
  type Tone,
} from '@/lib/constants';
import { formatDateTime, shortHash } from '@/lib/format';
import { InlineError, PageHeader, errText, toTimelineEntries } from '@/features/intake/shared';

type PreActionPanel = Schemas['PreActionPanel'];
type OpenMatter = Schemas['OpenMatter'];
type ChainStep = Schemas['ChainStep'];
type ActionDetail = Schemas['InstitutionActionDetail'];
type AckResult = Schemas['AcknowledgeResult'];
type ClearanceOut = Schemas['ClearanceOut'];

const isActionType = (s: string | null): s is InstActionType => !!s && s in INST_ACTION_LABEL;

/* One check per (institution, action) per mount: React StrictMode runs effects twice in development. */
const inflight = new Map<string, Promise<PreActionPanel>>();

function StartCheck({ institutionId, action }: { institutionId: string; action: string | null }) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const valid = isActionType(action);

  useEffect(() => {
    if (!valid) return;
    const key = `${institutionId}:${action}`;
    let p = inflight.get(key);
    if (!p) {
      p = api.post<PreActionPanel>(`/institutions/${institutionId}/pre-action-check`, { action_type: action });
      inflight.set(key, p);
      const clear = () => window.setTimeout(() => inflight.delete(key), 4000);
      p.then(clear, clear);
    }
    let live = true;
    p.then((panel) => {
      if (live) navigate(`/institutions/${institutionId}/pre-action/${panel.institution_action_id}`, { replace: true });
    }).catch((e: unknown) => {
      if (live) setError(errText(e));
    });
    return () => {
      live = false;
    };
  }, [institutionId, action, valid, navigate]);

  if (!valid) {
    return (
      <div>
        <PageHeader title="Pre-Action Check" />
        <InlineError>Choose an action from the Actions menu on the institution page.</InlineError>
        <p className="mt-3 text-sm">
          <Link to={`/institutions/${institutionId}`}>Back to the institution</Link>
        </p>
      </div>
    );
  }
  return (
    <div>
      <PageHeader title={`Pre-Action Check · ${INST_ACTION_LABEL[action]}`} subtitle="Collecting open matters across bureaus." />
      {error ? (
        <>
          <InlineError>{error}</InlineError>
          <p className="mt-3 text-sm">
            <Link to={`/institutions/${institutionId}`}>Back to the institution</Link>
          </p>
        </>
      ) : (
        <div className="flex flex-col gap-3" role="status" aria-label="Preparing the Pre-Action Check">
          <Skeleton height={56} />
          <Skeleton height={160} />
          <Skeleton height={96} />
        </div>
      )}
    </div>
  );
}

const RELEVANCE: Record<OpenMatter['relevance'], { label: string; tone: Tone }> = {
  HIGH: { label: 'High', tone: 'red' },
  MEDIUM: { label: 'Medium', tone: 'amber' },
  LOW: { label: 'Low', tone: 'neutral' },
};
const ORDER: OpenMatter['relevance'][] = ['HIGH', 'MEDIUM', 'LOW'];

function pendingText(m: OpenMatter): string {
  const step = m.pending_step as PendingStep;
  const status = CASE_STATUS_LABEL[m.status as CaseStatus];
  if (step === 'NONE') return status;
  return `${PENDING_STEP_LABEL[step]} · ${m.pending_days} ${m.pending_days === 1 ? 'day' : 'days'}`;
}

function summaryLine(s: PreActionPanel['summary'] | undefined, fallbackTotal: number): string {
  if (!s) return `${fallbackTotal} open ${fallbackTotal === 1 ? 'matter' : 'matters'} on this institution`;
  const by = Object.entries(s.by_bureau)
    .filter(([, n]) => n > 0)
    .map(([b, n]) => `${b} ${n}`)
    .join(' · ');
  const parts = [`${s.total_open} open ${s.total_open === 1 ? 'matter' : 'matters'} on this institution`];
  if (by) parts[0] += ` (${by})`;
  parts.push(`${s.overdue} overdue`);
  if (s.conflicting > 0) parts.push(`${s.conflicting} conflicting`);
  return parts.join(' · ');
}

function MattersTable({ matters }: { matters: OpenMatter[] }) {
  if (matters.length === 0) return <EmptyState message="No open matters on this institution." />;
  return (
    <div className="overflow-auto">
      <table className="ls-table">
        <caption className="sr-only">Open matters on this institution, grouped by relevance</caption>
        <thead>
          <tr>
            <th scope="col" style={{ width: 150 }}>Case</th>
            <th scope="col" style={{ width: 150 }}>Owner</th>
            <th scope="col" style={{ width: 150 }}>Category</th>
            <th scope="col" style={{ width: 190 }}>Pending step</th>
            <th scope="col" style={{ width: 190 }}>Clocks</th>
            <th scope="col">Why it matters</th>
          </tr>
        </thead>
        <tbody>
          {ORDER.map((rel) => {
            const rows = matters.filter((m) => m.relevance === rel);
            if (rows.length === 0) return null;
            return (
              <Fragment key={rel}>
                <tr>
                  <td colSpan={6} style={{ background: 'var(--paper)' }}>
                    <span className="flex items-center gap-2">
                      <Badge tone={RELEVANCE[rel].tone}>{RELEVANCE[rel].label}</Badge>
                      <span className="text-xs text-ink-500 tnum">
                        {rows.length} {rows.length === 1 ? 'matter' : 'matters'}
                      </span>
                    </span>
                  </td>
                </tr>
                {rows.map((m) => (
                  <tr key={m.case_id} style={{ height: 'auto' }}>
                    <td className="id">
                      <Link to={`/cases/${m.case_id}`}>{m.display_id}</Link>
                    </td>
                    <td>
                      <div className="flex flex-col gap-0.5">
                        <BureauTag bureau={m.owner_bureau as Bureau} />
                        {m.owner_officer && <span className="text-xs text-ink-500">{m.owner_officer}</span>}
                      </div>
                    </td>
                    <td>{CATEGORY_LABEL[m.category as CaseCategory]}</td>
                    <td>
                      <div className="flex flex-col gap-0.5">
                        <span>{pendingText(m)}</span>
                        {m.pending_step !== 'NONE' && <span className="text-xs text-ink-500">{CASE_STATUS_LABEL[m.status as CaseStatus]}</span>}
                      </div>
                    </td>
                    <td>
                      <div className="flex flex-col items-start gap-1 py-1">
                        {m.clocks.length === 0 && <span className="text-ink-300">{'–'}</span>}
                        {m.clocks.map((c) => (
                          <ClockPill key={c.clock} label={c.label} state={c.state as ClockState} clock={c.clock as ClockType} />
                        ))}
                      </div>
                    </td>
                    <td className="whitespace-normal">
                      <div className="flex flex-col items-start gap-1 py-1">
                        {m.conflicting && <RelationBadge relation="CONFLICTING" />}
                        <span className="text-ink-700">{m.why}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StepState({ step }: { step: ChainStep }) {
  switch (step.state) {
    case 'NOT_REQUESTED':
      return <Badge tone="neutral">Not requested</Badge>;
    case 'PENDING_PREVIOUS':
      return <Badge tone="neutral">After steps 1 and 2</Badge>;
    case 'PENDING':
      return <ClearanceTag response="PENDING" />;
    default:
      return <ClearanceTag response={step.state as ClearanceResponse} />;
  }
}

function ChainPanel({ actionId, chain, locked, onChanged }: { actionId: string; chain: ChainStep[]; locked: boolean; onChanged: () => void }) {
  const { toast } = useToast();
  const [error, setError] = useState<string | null>(null);
  const req = useApiMutation<ClearanceOut, Bureau>((target_bureau) => api.post<ClearanceOut>(`/institution-actions/${actionId}/clearances`, { target_bureau }), {
    onSuccess: (c) => {
      setError(null);
      toast(`Clearance requested from ${c.target_bureau}. It appears in their inbox.`, 'ok');
      onChanged();
    },
    onError: (e) => setError(errText(e)),
  });
  return (
    <Panel title="Clearance chain" actions={<span className="text-xs font-normal text-ink-500">Updates automatically every 10 seconds</span>} padded={false}>
      <ol className="m-0 grid list-none p-0" style={{ gridTemplateColumns: `repeat(${Math.max(1, chain.length)}, minmax(0, 1fr))` }}>
        {chain.map((s) => {
          const label = s.label ?? `${s.bureau === 'PGRC' ? 'PGRC' : s.bureau === 'VIGILANCE' ? 'Vigilance' : s.bureau} clearance`;
          const can = s.state === 'NOT_REQUESTED' && !locked;
          return (
            <li key={s.step_order} className="flex flex-col gap-2 border-r border-line-soft p-3 last:border-r-0">
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-xs tnum text-ink-500">{s.step_order}</span>
                <span className="text-sm font-semibold text-ink-900">{label}</span>
              </div>
              <div className="flex items-center gap-2">
                <StepState step={s} />
                {s.responded_at && <span className="text-xs text-ink-500 tnum">{formatDateTime(s.responded_at)}</span>}
              </div>
              {s.remarks && <p className="m-0 text-xs text-ink-700">Remarks: {s.remarks}</p>}
              {s.state === 'NOT_REQUESTED' || s.state === 'PENDING_PREVIOUS' ? (
                <div>
                  <Button className="!h-7" disabled={!can} loading={req.isPending && req.variables === s.bureau} onClick={() => req.mutate(s.bureau as Bureau)}>
                    Request {s.bureau === 'APPROVAL' ? 'Approval NOC' : `${s.bureau === 'VIGILANCE' ? 'Vigilance' : s.bureau} clearance`}
                  </Button>
                  {s.state === 'PENDING_PREVIOUS' && <div className="mt-1 text-xs text-ink-500">Follows steps 1 and 2 of the chain.</div>}
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
      {error && (
        <div className="border-t border-line p-3">
          <InlineError>{error}</InlineError>
        </div>
      )}
    </Panel>
  );
}

const ACTION_STATUS: Record<string, { label: string; tone: Tone }> = {
  CHECK_SHOWN: { label: 'Check shown', tone: 'info' },
  ACKNOWLEDGED: { label: 'Acknowledged', tone: 'info' },
  PROCEEDED: { label: 'Proceeded', tone: 'ok' },
  ON_HOLD: { label: 'On hold', tone: 'amber' },
  WITHDRAWN: { label: 'Withdrawn', tone: 'neutral' },
};

function AcknowledgePanel({ detail, total, onDone }: { detail: ActionDetail; total: number; onDone: (r: AckResult) => void }) {
  const { toast } = useToast();
  const [seen, setSeen] = useState(false);
  const [remark, setRemark] = useState('');
  const [error, setError] = useState<string | null>(null);
  const decided = detail.status === 'PROCEEDED' || detail.status === 'WITHDRAWN';
  const send = useApiMutation<AckResult, boolean>(
    (proceed) => api.post<AckResult>(`/institution-actions/${detail.id}/acknowledge`, { proceed, acknowledged: seen, remark: remark.trim() || null }),
    {
      onSuccess: (r, proceed) => {
        setError(null);
        toast(proceed ? 'Acknowledged. Proceeding with the action is recorded.' : 'Action put on hold. Recorded in the Passport.', 'ok');
        onDone(r);
      },
      onError: (e) => setError(errText(e)),
    },
  );
  return (
    <Panel title="Acknowledge">
      <div className="flex flex-col gap-3">
        <Checkbox
          checked={seen}
          disabled={decided}
          onChange={(e) => setSeen(e.target.checked)}
          label={`I have seen the ${total} open ${total === 1 ? 'matter' : 'matters'} listed above`}
        />
        <Field label="Remark (optional)" className="max-w-2xl">
          <Textarea rows={2} value={remark} disabled={decided} onChange={(e) => setRemark(e.target.value)} />
        </Field>
        {error && <InlineError>{error}</InlineError>}
        <div className="flex items-center gap-2">
          <Button disabled={decided || !seen} loading={send.isPending && send.variables === false} onClick={() => send.mutate(false)}>
            Put on hold
          </Button>
          <Button variant="primary" disabled={decided || !seen} loading={send.isPending && send.variables === true} onClick={() => send.mutate(true)}>
            Proceed with action
          </Button>
          <span className="text-xs text-ink-500">Open matters never block this step. Your acknowledgement is written to the Passport.</span>
        </div>
      </div>
    </Panel>
  );
}

function ConfirmationPanel({ detail, fresh }: { detail: ActionDetail; fresh: AckResult | null }) {
  const entry =
    fresh?.passport_entry ?? [...detail.passport].reverse().find((e) => e.event === 'PREACTION_ACKNOWLEDGED') ?? null;
  const st = ACTION_STATUS[detail.status] ?? { label: detail.status, tone: 'neutral' as Tone };
  return (
    <Panel title="Recorded" actions={<Badge tone={st.tone}>{st.label}</Badge>}>
      <div className="flex flex-col gap-1.5 text-sm">
        {entry ? (
          <>
            <div>
              <span className="font-semibold text-ink-900">{entry.event}</span>
              <span className="text-ink-500"> · {formatDateTime(entry.created_at)}</span>
              <span className="ml-3 font-mono text-xs tnum text-ink-700" title={entry.hash}>
                {shortHash(entry.hash)}
              </span>
            </div>
            <div className="text-ink-700">
              {typeof entry.payload?.summary === 'string' ? entry.payload.summary : ''}
              {detail.ack_remark ? `. Remark: ${detail.ack_remark}` : ''}
            </div>
          </>
        ) : (
          <span className="text-ink-500">The acknowledgement is recorded in the action chain below.</span>
        )}
        <div>
          <Link to={`/institutions/${detail.institution.id}`}>Back to {detail.institution.name}</Link>
        </div>
      </div>
    </Panel>
  );
}

function ActionPassport({ detail }: { detail: ActionDetail }) {
  const [verification, setVerification] = useState<ChainVerification | null>(null);
  const [error, setError] = useState<string | null>(null);
  const verify = useApiMutation<Schemas['VerifyOut'], void>(() => api.get<Schemas['VerifyOut']>(`/institution-actions/${detail.id}/passport/verify`), {
    onSuccess: (v) => {
      setError(null);
      setVerification({ ok: v.ok, count: v.count, first_bad_seq: v.first_bad_seq, checked_at: v.checked_at });
    },
    onError: (e) => setError(errText(e)),
  });
  return (
    <Panel title="Action passport">
      <PassportTimeline entries={toTimelineEntries(detail.passport)} verification={verification} onVerify={() => verify.mutate()} verifying={verify.isPending} />
      {error && <InlineError>{error}</InlineError>}
    </Panel>
  );
}

function ActionView({ institutionId, actionId }: { institutionId: string; actionId: string }) {
  const qc = useQueryClient();
  const [fresh, setFresh] = useState<AckResult | null>(null);
  const q = useApiQuery<ActionDetail>(['preaction', actionId], `/institution-actions/${actionId}`, { refetchInterval: 10_000 });
  const refresh = () => void qc.invalidateQueries({ queryKey: ['preaction', actionId] });

  if (q.isLoading) {
    return (
      <div className="flex flex-col gap-3" role="status" aria-label="Loading">
        <Skeleton height={56} />
        <Skeleton height={200} />
      </div>
    );
  }
  if (q.isError || !q.data) {
    return (
      <div>
        <PageHeader title="Pre-Action Check" />
        <InlineError>{q.error ? errText(q.error) : 'The check could not be loaded.'}</InlineError>
        <p className="mt-3 text-sm">
          <Link to={`/institutions/${institutionId}`}>Back to the institution</Link>
        </p>
      </div>
    );
  }
  const d = q.data;
  const snap = d.panel as unknown as Partial<PreActionPanel>;
  const matters = snap.open_matters ?? [];
  const total = snap.summary?.total_open ?? d.open_matter_count;
  const locked = d.status === 'PROCEEDED' || d.status === 'WITHDRAWN';
  const decided = d.status === 'PROCEEDED' || d.status === 'ON_HOLD';
  const st = ACTION_STATUS[d.status] ?? { label: d.status, tone: 'neutral' as Tone };
  const label = INST_ACTION_LABEL[d.action_type as InstActionType];

  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        title={`Pre-Action Check · ${label} · ${d.institution.name}`}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-mono tnum">{d.institution.permanent_id}</span>
            <span>Started {formatDateTime(d.created_at)} by {d.initiated_by.name}</span>
            <Badge tone={st.tone}>{st.label}</Badge>
            <Link to={`/institutions/${d.institution.id}`}>Institution 360</Link>
          </span>
        }
      />

      <div className="rounded border border-line border-l-[3px] border-l-navy bg-surface px-3 py-2.5">
        <p className="m-0 text-sm font-semibold text-ink-900">{snap.advisory ?? 'Advisory only. The competent authority decides.'}</p>
        {snap.rule_note && <p className="m-0 mt-1 text-sm text-ink-700">Rule: {snap.rule_note}</p>}
      </div>

      <Panel title={summaryLine(snap.summary, total)} padded={false}>
        <MattersTable matters={matters} />
      </Panel>

      <ChainPanel actionId={d.id} chain={d.clearance_chain} locked={locked} onChanged={refresh} />

      <AcknowledgePanel
        detail={d}
        total={total}
        onDone={(r) => {
          setFresh(r);
          refresh();
        }}
      />

      {decided && <ConfirmationPanel detail={d} fresh={fresh} />}

      <ActionPassport detail={d} />
    </div>
  );
}

export default function PreActionPage() {
  const { id = '', actionId = '' } = useParams();
  const [sp] = useSearchParams();
  if (actionId === 'new') return <StartCheck institutionId={id} action={sp.get('action')} />;
  return <ActionView institutionId={id} actionId={actionId} />;
}
