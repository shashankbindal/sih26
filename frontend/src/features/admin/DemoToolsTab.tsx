import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Button, Field, Input, Modal, Panel, Skeleton, useToast } from '@/components/ui';
import { api, errorMessage } from '@/api/client';
import { useApiMutation, useApiQuery } from '@/api/hooks';
import { formatDateTime, formatNumber } from '@/lib/format';

interface DemoTools {
  demo_mode: boolean;
  seeded_at: string | null;
  counts: { institutions: number; cases: number; users: number };
  scheduler?: unknown;
}
interface SweepResult {
  pairs_checked: number;
  new_links: number;
  superseded: number;
}
interface TamperResult {
  case_id: string;
  display_id: string;
  seq: number;
  event: string;
  entries: number;
  verify?: { ok?: boolean; count?: number; first_bad_seq?: number | null };
}
interface CaseHit {
  id: string;
  display_id: string;
}

function Row({ children }: { children: React.ReactNode }) {
  return <div className="flex items-start justify-between gap-6 border-b border-line-soft py-3 last:border-0">{children}</div>;
}

export function DemoToolsTab() {
  const q = useApiQuery<DemoTools>(['admin', 'demo-tools'], '/admin/demo-tools');
  const qc = useQueryClient();
  const { toast } = useToast();
  const [confirmReset, setConfirmReset] = useState(false);
  const [sweep, setSweep] = useState<SweepResult | null>(null);
  const [caseRef, setCaseRef] = useState('');
  const [confirmTamper, setConfirmTamper] = useState<CaseHit | null>(null);
  const [tamper, setTamper] = useState<TamperResult | null>(null);

  const demo = q.data?.demo_mode ?? false;

  const reset = useApiMutation(() => api.post<{ seconds?: number }>('/admin/reset-demo'), {
    onSuccess: (r) => {
      setConfirmReset(false);
      setSweep(null);
      setTamper(null);
      void qc.invalidateQueries();
      toast(`Demo data reset${r?.seconds ? ` in ${formatNumber(r.seconds, 1)} s` : ''}.`, 'ok');
    },
    onError: (e) => {
      setConfirmReset(false);
      toast(`Reset failed. ${errorMessage(e)}`, 'red');
    },
  });

  const runSweep = useApiMutation(() => api.post<SweepResult>('/admin/sweep'), {
    invalidate: [['dash'], ['links']],
    onSuccess: (r) => {
      setSweep(r);
      toast('Relationship sweep finished.', 'ok');
    },
    onError: (e) => toast(`Sweep failed. ${errorMessage(e)}`, 'red'),
  });

  const lookup = useApiMutation(
    async (ref: string) => {
      const res = await api.get<{ items: CaseHit[] }>('/cases', { params: { q: ref, page_size: 10 } });
      const hit = res.items.find((c) => c.display_id.toLowerCase() === ref.trim().toLowerCase()) ?? (res.items.length === 1 ? res.items[0] : undefined);
      if (!hit) throw new Error('No single case matches that ID. Enter the full case ID, for example LS-2026-000204.');
      return hit;
    },
    { onSuccess: (hit) => setConfirmTamper(hit), onError: (e) => toast(errorMessage(e), 'red') },
  );

  const runTamper = useApiMutation((c: CaseHit) => api.post<TamperResult>('/admin/tamper-demo', { case_id: c.id }), {
    onSuccess: (r) => {
      setConfirmTamper(null);
      setTamper(r);
      toast('One Passport entry was altered. Verify the chain on the case.', 'amber');
    },
    onError: (e) => {
      setConfirmTamper(null);
      toast(`Tamper demo failed. ${errorMessage(e)}`, 'red');
    },
  });

  return (
    <div className="flex flex-col gap-4">
      <Panel title="Demo tools">
        {q.isLoading && <Skeleton height={120} />}
        {q.error && <p className="text-sm text-red">Could not load demo status. {q.error.message}</p>}
        {q.data && (
          <div>
            <Row>
              <div>
                <div className="text-sm font-medium text-ink-900">Last seeded</div>
                <div className="text-xs text-ink-500">
                  {q.data.counts.institutions} institutions, {q.data.counts.cases} cases, {q.data.counts.users} users. Seed 26264, dates relative to the seed time.
                </div>
              </div>
              <div className="tnum text-sm text-ink-900">{q.data.seeded_at ? formatDateTime(q.data.seeded_at) : 'Not seeded'}</div>
            </Row>
            <Row>
              <div>
                <div className="text-sm font-medium text-ink-900">Reset demo data</div>
                <div className="text-xs text-ink-500">Deletes all cases, links and Passport entries and re-seeds the synthetic data deterministically. Takes up to a minute.{!demo && ' Available in demo mode only.'}</div>
              </div>
              <Button variant="danger" disabled={!demo} onClick={() => setConfirmReset(true)}>
                Reset demo data
              </Button>
            </Row>
            <Row>
              <div>
                <div className="text-sm font-medium text-ink-900">Run relationship sweep</div>
                <div className="text-xs text-ink-500">Re-checks every open case pair on each institution. New links are suggestions; nothing is merged or changed on its own.</div>
                {sweep && (
                  <div className="mt-1 text-xs text-ink-700 tnum" role="status">
                    Checked {formatNumber(sweep.pairs_checked)} pairs. New links: {formatNumber(sweep.new_links)}. Superseded: {formatNumber(sweep.superseded)}.
                  </div>
                )}
              </div>
              <Button loading={runSweep.isPending} onClick={() => runSweep.mutate(undefined)}>
                Run sweep now
              </Button>
            </Row>
            <Row>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-ink-900">Tamper demo on case</div>
                <div className="text-xs text-ink-500">Alters one Passport entry directly in the database so that Verify chain flags the exact entry.{!demo && ' Available in demo mode only.'}</div>
                {tamper && (
                  <div className="mt-2 text-xs text-ink-700" role="status">
                    <span className="mono">{tamper.display_id}</span>: entry {tamper.seq} ({tamper.event}) of {tamper.entries} altered.{' '}
                    {tamper.verify && (tamper.verify.ok ? 'The chain still verifies.' : `Verification now fails at entry ${tamper.verify.first_bad_seq}.`)}{' '}
                    <Link to={`/cases/${tamper.case_id}`}>Open the case</Link>
                  </div>
                )}
              </div>
              <form
                className="flex items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (caseRef.trim()) lookup.mutate(caseRef.trim());
                }}
              >
                <Field label="Case ID">
                  <Input mono placeholder="LS-2026-000204" className="w-48" value={caseRef} disabled={!demo} onChange={(e) => setCaseRef(e.target.value)} />
                </Field>
                <Button type="submit" disabled={!demo || !caseRef.trim()} loading={lookup.isPending}>
                  Tamper
                </Button>
              </form>
            </Row>
          </div>
        )}
      </Panel>

      <Modal
        open={confirmReset}
        onClose={() => !reset.isPending && setConfirmReset(false)}
        title="Reset demo data"
        footer={
          <>
            <Button onClick={() => setConfirmReset(false)} disabled={reset.isPending}>
              Cancel
            </Button>
            <Button variant="danger" loading={reset.isPending} onClick={() => reset.mutate(undefined)}>
              Reset demo data
            </Button>
          </>
        }
      >
        <p>All cases, links, clearances and Passport entries will be deleted and the synthetic data regenerated. Any decisions taken during the demo are lost.</p>
        {reset.isPending && <p className="mt-2 text-ink-500">Re-seeding. This takes up to a minute.</p>}
      </Modal>

      <Modal
        open={!!confirmTamper}
        onClose={() => setConfirmTamper(null)}
        title="Tamper demo"
        footer={
          <>
            <Button onClick={() => setConfirmTamper(null)}>Cancel</Button>
            <Button variant="danger" loading={runTamper.isPending} onClick={() => confirmTamper && runTamper.mutate(confirmTamper)}>
              Alter one entry
            </Button>
          </>
        }
      >
        <p>
          One Passport entry on <span className="mono">{confirmTamper?.display_id}</span> will be altered directly. The chain will then fail verification. This is for the demonstration only.
        </p>
      </Modal>
    </div>
  );
}
