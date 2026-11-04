import { useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { useAuth } from '@/auth';
import { InstitutionCard, MaskedValue, MatchStatusTag, ScoreMeter } from '@/components/domain';
import { Button, Field, Modal, Panel, Textarea, useToast } from '@/components/ui';
import {
  CATEGORY_LABEL,
  PENDING_STEP_LABEL,
  type Bureau,
  type CaseCategory,
  type MatchStatus,
  type PendingStep,
} from '@/lib/constants';
import { ageShort, formatDateTime, formatScore } from '@/lib/format';
import { APPROVAL_LABEL } from '../institutions/refData';
import { MaybeHindi, describeActionError, roName, type CaseDetail } from './shared';

function Facts({ children }: { children: ReactNode }) {
  return <dl className="m-0 divide-y divide-line-soft">{children}</dl>;
}
function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[150px_1fr] gap-3 py-2 text-sm">
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd className="m-0 min-w-0 text-ink-900">{children}</dd>
    </div>
  );
}

/** Reason capture for a logged PII reveal (min 10 chars, the API specification). */
export function RevealModal({ caseData, onClose }: { caseData: CaseDetail; onClose: () => void }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ok = reason.trim().length >= 10;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const fresh = await api.post<CaseDetail>(`/cases/${caseData.id}/reveal-pii`, { reason: reason.trim() });
      qc.setQueryData(['case', caseData.id, {}], fresh);
      await qc.invalidateQueries({ queryKey: ['passport'] });
      toast('Access granted and logged in the Case Passport.', 'ok');
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
      title="Request access to complainant details"
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void submit()} loading={busy} disabled={!ok}>
            Reveal and log
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="m-0 text-sm text-ink-700">
          This case is owned by {caseData.owner_bureau}. Revealing complainant identity is logged against your name with the reason below.
        </p>
        <Field label="Reason" required hint={`At least 10 characters (${reason.trim().length} entered).`}>
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

export function SummaryTab({ caseData: c }: { caseData: CaseDetail }) {
  const { user } = useAuth();
  const [norm, setNorm] = useState(false);
  const [reveal, setReveal] = useState(false);
  const descNorm = (c as CaseDetail & { description_norm?: string | null }).description_norm ?? null;
  const descMasked = c.masked_fields.includes('description');
  const complainantMasked = c.masked_fields.includes('complainant.name');
  const canRequest = user?.role !== 'SENIOR_MGMT';
  const request = canRequest ? () => setReveal(true) : undefined;
  const inst = (c.institution_snapshot ?? c.institution ?? null) as Partial<NonNullable<CaseDetail['institution_snapshot']>> & { id: string; name: string; permanent_id: string } | null;
  const showCandidates = c.institution_match_status !== 'EXACT' && c.match_candidates.length > 0;

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title="Complaint"
        actions={
          descNorm ? (
            <div role="group" aria-label="Text version" className="inline-flex overflow-hidden rounded border border-line text-xs">
              {(['Original', 'Normalised text'] as const).map((l, i) => (
                <button
                  key={l}
                  type="button"
                  aria-pressed={norm === (i === 1)}
                  onClick={() => setNorm(i === 1)}
                  className={`focus-ring h-6 px-2 ${norm === (i === 1) ? 'bg-navy-50 font-semibold text-ink-900' : 'bg-surface text-ink-500 hover:bg-paper'}`}
                >
                  {l}
                </button>
              ))}
            </div>
          ) : undefined
        }
      >
        <h3 className="m-0 text-md font-semibold leading-snug text-ink-900">
          <MaybeHindi text={c.subject} />
        </h3>
        <div className="mt-1 text-xs text-ink-500">
          {CATEGORY_LABEL[c.category as CaseCategory] ?? c.category}
          {c.category_suggested && c.category_suggested !== c.category && <span> · suggested: {CATEGORY_LABEL[c.category_suggested as CaseCategory] ?? c.category_suggested}</span>}
          {c.language && <span> · language: {c.language}</span>}
        </div>
        <div className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-ink-900">
          {descMasked ? (
            <MaskedValue ownerBureau={c.owner_bureau as Bureau} onRequestAccess={request} />
          ) : c.description ? (
            <span lang={c.language === 'hi' ? 'hi' : undefined}>{norm && descNorm ? descNorm : c.description}</span>
          ) : (
            <span className="text-ink-500">No description recorded.</span>
          )}
        </div>
        {norm && descNorm && <div className="mt-2 text-xs text-ink-500">Normalised text is what the matching engine reads: transliterated, lower-cased, with personal details masked.</div>}
      </Panel>

      <Panel title="Institution" actions={<MatchStatusTag status={c.institution_match_status as MatchStatus} />}>
        {inst ? (
          <InstitutionCard
            institution={{
              id: inst.id,
              name: inst.name,
              permanent_id: inst.permanent_id,
              district: inst.district,
              state: inst.state,
              pincode: inst.pincode,
              ro_name: roName(inst.ro_code),
              institution_type: inst.inst_type,
              approval_status: inst.approval_status ? (APPROVAL_LABEL[inst.approval_status] ?? inst.approval_status) : undefined,
            }}
            aside={c.institution_match_score !== null && c.institution_match_score !== undefined ? <ScoreMeter score={c.institution_match_score} /> : undefined}
          />
        ) : (
          <p className="m-0 text-sm text-ink-500">No institution has been matched to this case.</p>
        )}
        <Facts>
          <Fact label="Institution as written">
            {c.institution_text_raw ? <MaybeHindi text={c.institution_text_raw} /> : <span className="text-ink-500">–</span>}
          </Fact>
          {c.permanent_id_raw && (
            <Fact label="Permanent ID as written">
              <span className="font-mono tnum">{c.permanent_id_raw}</span>
            </Fact>
          )}
        </Facts>
        {showCandidates && (
          <div className="mt-2 border-t border-line pt-2">
            <h4 className="label-caps mb-1.5">Other candidate institutions</h4>
            <ol className="m-0 list-none p-0">
              {c.match_candidates.slice(0, 3).map((m) => (
                <li key={m.institution_id} className="flex items-center justify-between gap-3 border-b border-line-soft py-1.5 text-sm last:border-b-0">
                  <span className="min-w-0">
                    <span className="block truncate text-ink-900">{m.name}</span>
                    <span className="block font-mono text-xs tnum text-ink-500">{m.permanent_id}</span>
                  </span>
                  <span className="font-mono text-xs tnum text-ink-900">{formatScore(m.score)}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </Panel>

      <Panel title="Pending step">
        <Facts>
          <Fact label="Awaiting">
            {c.pending_step === 'NONE' ? <span className="text-ink-500">Nothing pending</span> : PENDING_STEP_LABEL[c.pending_step as PendingStep] ?? c.pending_step}
          </Fact>
          {c.pending_since && c.pending_step !== 'NONE' && (
            <Fact label="Since">
              <span className="tnum">{formatDateTime(c.pending_since)}</span>
              <span className="text-ink-500"> · </span>
              <span className="font-mono text-xs tnum">{ageShort(c.pending_since)}</span>
            </Fact>
          )}
          {c.pending_action && <Fact label="Pending action">{c.pending_action}</Fact>}
        </Facts>
        {c.suggested_actions.length > 0 && (
          <div className="mt-2 rounded border border-line bg-paper px-3 py-2 text-sm">
            <div className="label-caps mb-1">Suggested next action</div>
            {c.suggested_actions.map((a) => (
              <p key={a} className="m-0 text-ink-900">
                {a}
              </p>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Complainant">
        <Facts>
          <Fact label="Name">{complainantMasked ? <MaskedValue ownerBureau={c.owner_bureau as Bureau} onRequestAccess={request} /> : (c.complainant.name ?? '–')}</Fact>
          <Fact label="Email">{complainantMasked ? <span className="text-ink-500">{'••••'}</span> : (c.complainant.email ?? '–')}</Fact>
          <Fact label="Phone">{complainantMasked ? <span className="text-ink-500">{'••••'}</span> : <span className="tnum">{c.complainant.phone ?? '–'}</span>}</Fact>
          <Fact label="Party type">{c.complainant.party_type ?? '–'}</Fact>
        </Facts>
        {complainantMasked && !canRequest && <p className="m-0 mt-2 text-xs text-ink-500">Complainant identity is not shown to senior management.</p>}
      </Panel>
      {reveal && <RevealModal caseData={c} onClose={() => setReveal(false)} />}
    </div>
  );
}
