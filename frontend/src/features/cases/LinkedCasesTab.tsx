import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { useAuth } from '@/auth';
import { BureauTag, LinkStatusTag, ReasonList, RelationBadge, StatusTag } from '@/components/domain';
import { Button, EmptyState, Field, Modal, Textarea, useToast } from '@/components/ui';
import type { Bureau, CaseStatus, LinkStatus, RelationType } from '@/lib/constants';
import { formatScore } from '@/lib/format';
import { canDecideLink } from './CaseActions';
import { MaybeHindi, describeActionError, type CaseDetail, type LinkOut } from './shared';

type Decision = 'CONFIRM' | 'REJECT' | 'DEFER';
const DECISION_LABEL: Record<Decision, string> = { CONFIRM: 'Confirm link', REJECT: 'Reject link', DEFER: 'Defer' };
const DECISION_VERB: Record<Decision, string> = { CONFIRM: 'Confirm', REJECT: 'Reject', DEFER: 'Defer' };

function DecisionModal({ link, decision, onClose }: { link: LinkOut; decision: Decision; onClose: () => void }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/links/${link.id}/decision`, { decision, reason: reason.trim() });
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['case'] }),
        qc.invalidateQueries({ queryKey: ['cases'] }),
        qc.invalidateQueries({ queryKey: ['institution'] }),
        qc.invalidateQueries({ queryKey: ['passport'] }),
      ]);
      toast(`${DECISION_VERB[decision]}: decision recorded as a new link version.`, 'ok');
      onClose();
    } catch (e) {
      setError(describeActionError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={busy ? () => undefined : onClose}
      title={`${DECISION_LABEL[decision]} · ${link.other_case.display_id}`}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void submit()} loading={busy} disabled={reason.trim().length < 3}>
            {DECISION_LABEL[decision]}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="m-0 text-sm text-ink-700">
          The suggestion is advisory. Your decision and reason are versioned in the link history and can be reverted.
        </p>
        <Field label="Reason" required hint="Required for every decision.">
          <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        {error && (
          <p role="alert" className="m-0 rounded border border-red bg-red-bg px-3 py-2 text-sm text-red">
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}

function LinkBlock({ link, caseData }: { link: LinkOut; caseData: CaseDetail }) {
  const { user } = useAuth();
  const [decision, setDecision] = useState<Decision | null>(null);
  const [all, setAll] = useState(false);
  const may = canDecideLink(user, caseData, link.other_case.owner_bureau);
  const final = link.status === 'REJECTED' || link.status === 'SUPERSEDED';
  const coordination = link.relation === 'RELATED' || link.relation === 'CONFLICTING';
  const reasons = all ? link.reasons : link.reasons.slice(0, 3);

  return (
    <li className="border-b border-line-soft last:border-b-0">
      <div className={`flex gap-3 px-3 py-3 ${coordination ? 'border-l-[3px] ' + (link.relation === 'CONFLICTING' ? 'border-l-red' : 'border-l-saffron') : 'border-l-[3px] border-l-transparent'}`}>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <RelationBadge relation={link.relation as RelationType} />
            <LinkStatusTag status={link.status as LinkStatus} />
            <span className="text-xs text-ink-500">
              Score <span className="font-mono tnum text-ink-900">{formatScore(link.score)}</span>
            </span>
            <span className="font-mono text-xs tnum text-ink-500">v{link.version}</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <Link to={`/cases/${link.other_case.id}`} className="font-mono tnum">
              {link.other_case.display_id}
            </Link>
            <BureauTag bureau={link.other_case.owner_bureau as Bureau} />
            <StatusTag status={link.other_case.status as CaseStatus} />
            <span className="min-w-0 truncate text-ink-700">
              <MaybeHindi text={link.other_case.subject} />
            </span>
          </div>
          {link.reasons.length > 0 && (
            <div className="mt-2.5">
              <ReasonList reasons={reasons} numbered />
              {link.reasons.length > 3 && (
                <button type="button" onClick={() => setAll((v) => !v)} className="focus-ring mt-1.5 text-xs text-navy hover:underline" style={{ background: 'none', border: 0, padding: 0 }}>
                  {all ? 'Show fewer reasons' : `Show all ${link.reasons.length} reasons`}
                </button>
              )}
            </div>
          )}
        </div>
        {may && !final && (
          <div className="flex w-[104px] shrink-0 flex-col gap-1.5">
            <Button variant="primary" className="!h-7" disabled={link.status === 'CONFIRMED'} onClick={() => setDecision('CONFIRM')}>
              Confirm
            </Button>
            <Button className="!h-7" onClick={() => setDecision('REJECT')}>
              Reject
            </Button>
            <Button className="!h-7" disabled={link.status === 'DEFERRED'} onClick={() => setDecision('DEFER')}>
              Defer
            </Button>
          </div>
        )}
      </div>
      {decision && <DecisionModal link={link} decision={decision} onClose={() => setDecision(null)} />}
    </li>
  );
}

/** Links on this case. Engine suggestions are advisory: the officer confirms, rejects or defers with a reason. */
export function LinkedCasesTab({ caseData }: { caseData: CaseDetail }) {
  const links = [...caseData.links].sort((a, b) => b.score - a.score);
  if (links.length === 0) return <EmptyState message="No related, duplicate or conflicting cases found for this case." />;
  return (
    <div className="rounded border border-line bg-surface">
      <ul className="m-0 list-none p-0">
        {links.map((l) => (
          <LinkBlock key={l.id} link={l} caseData={caseData} />
        ))}
      </ul>
    </div>
  );
}
