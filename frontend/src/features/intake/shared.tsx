import { useState, type ReactNode } from 'react';
import { ApiError, api } from '@/api/client';
import type { Schemas } from '@/api/types';
import type { PassportEntry } from '@/components/domain';
import { ScoreMeter } from '@/components/domain';
import { Button, Field, Modal, Textarea, useToast } from '@/components/ui';
import type { Bureau } from '@/lib/constants';

export type CaseCreate = Schemas['CaseCreate'];
export type CaseCreateResult = Schemas['CaseCreateResult'];
export type CreatedLink = Schemas['CreatedLink'];
export type ResolutionOut = Schemas['ResolutionOut'];
export type ResolutionCandidate = Schemas['ResolutionCandidate'];
export type ResolveResult = Schemas['ResolveResult'];
export type PassportEntryOut = Schemas['PassportEntryOut'];
export type LinkDetail = Schemas['LinkDetail'];

const DEVANAGARI = /[ऀ-ॿ]/;
export const hasDevanagari = (s: string | null | undefined): boolean => !!s && DEVANAGARI.test(s);

/** Wraps Devanagari text with lang="hi" (the design system section 8). */
export function MaybeHindi({ text, className }: { text: string | null | undefined; className?: string }): ReactNode {
  if (!text) return null;
  return hasDevanagari(text) ? (
    <span lang="hi" className={className}>
      {text}
    </span>
  ) : (
    <span className={className}>{text}</span>
  );
}

/** Message for an inline error. Never includes request bodies (no PII). */
export function errText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return 'The server could not be reached. Nothing was changed.';
    if (err.status === 403) return err.message || 'You are not permitted to do this.';
    if (err.status === 404 || err.status === 405 || err.status === 501) return err.message || 'This action is not available on the server.';
    return err.message || 'The request failed.';
  }
  return err instanceof Error ? err.message : 'The request failed.';
}

/** Regional Offices: display labels for the owner_ro_code field (reference data, the data model regional_offices). */
export const RO_CHOICES: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'KNP', label: 'Kanpur' },
  { value: 'CHD', label: 'Chandigarh' },
  { value: 'MUM', label: 'Mumbai' },
  { value: 'BPL', label: 'Bhopal' },
  { value: 'KOL', label: 'Kolkata' },
  { value: 'GHY', label: 'Guwahati' },
  { value: 'BLR', label: 'Bengaluru' },
  { value: 'HYD', label: 'Hyderabad' },
  { value: 'CHN', label: 'Chennai' },
  { value: 'TVM', label: 'Thiruvananthapuram' },
];

export const OWNER_BUREAUS: Bureau[] = ['PGRC', 'RB', 'APPROVAL', 'VIGILANCE', 'RO'];

/** Passport API rows -> PassportTimeline rows. The remark is the human text carried in the payload. */
export function toTimelineEntries(rows: PassportEntryOut[]): PassportEntry[] {
  return rows.map((e) => {
    const p = e.payload ?? {};
    const str = (x: unknown): string | null => (typeof x === 'string' && x.trim() ? x.trim() : null);
    const summary = str(p.summary) ?? str(p.note);
    const own = str(p.remark);
    const remark = summary && own ? `${summary}. Remark: ${own}` : (summary ?? own);
    return {
      seq: e.seq,
      event: e.event,
      actor_name: e.actor_name,
      bureau: (e.actor_bureau ?? null) as Bureau | null,
      at: e.created_at,
      remark,
      hash: e.hash,
      prev_hash: e.prev_hash,
    };
  });
}

/** Reasons list with "Show all" after the first n. */
export function useShowAll(): [boolean, () => void] {
  const [all, setAll] = useState(false);
  return [all, () => setAll((v) => !v)];
}

export function LinkButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="focus-ring text-xs text-navy hover:underline" style={{ background: 'none', border: 0, padding: 0 }}>
      {children}
    </button>
  );
}

export type LinkDecisionKind = 'CONFIRM' | 'REJECT' | 'DEFER';
const TITLE: Record<LinkDecisionKind, string> = { CONFIRM: 'Confirm link', REJECT: 'Reject link', DEFER: 'Defer decision' };
const DONE: Record<LinkDecisionKind, string> = {
  CONFIRM: 'Link confirmed. Recorded as a new link version.',
  REJECT: 'Link rejected. Recorded as a new link version.',
  DEFER: 'Decision deferred. Recorded as a new link version.',
};

/** Reason capture for POST /links/{id}/decision. The reason is required for every decision. */
export function LinkDecisionModal({
  linkId,
  label,
  decision,
  onClose,
  onDone,
}: {
  linkId: string;
  label: string;
  decision: LinkDecisionKind;
  onClose: () => void;
  onDone: (result: LinkDetail) => void;
}) {
  const { toast } = useToast();
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<LinkDetail>(`/links/${linkId}/decision`, { decision, reason: reason.trim() });
      toast(DONE[decision], 'ok');
      onDone(res);
      onClose();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={busy ? () => undefined : onClose}
      title={`${TITLE[decision]} · ${label}`}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void submit()} loading={busy} disabled={reason.trim().length < 3}>
            {TITLE[decision]}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="m-0 text-sm text-ink-700">The suggestion is advisory. Your decision and reason are versioned in the link history and can be reverted.</p>
        <Field label="Reason" required hint="Required for every decision (at least 3 characters).">
          <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
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

/** Small page header used by the workflow screens. */
export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold text-ink-900">{title}</h1>
        {subtitle && <div className="mt-1 text-sm text-ink-500">{subtitle}</div>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function InlineError({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="m-0 rounded border border-red bg-red-bg px-3 py-2 text-sm text-red">
      {children}
    </p>
  );
}

/** ScoreMeter with the engine's 3-decimal score (a 2-decimal display would round 0.998 up to 1.00). */
export function ScoreBar({ score, width = 160 }: { score: number; width?: number }) {
  return (
    <span className="inline-flex items-start gap-2">
      <ScoreMeter score={score} width={width} hideValue />
      <span className="font-mono text-xs tnum text-ink-900" style={{ lineHeight: '8px' }}>
        {score.toFixed(3)}
      </span>
    </span>
  );
}
