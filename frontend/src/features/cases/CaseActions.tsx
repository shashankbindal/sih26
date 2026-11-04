import { useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { AuthUser } from '@/auth/AuthContext';
import { Button, Field, Modal, Select, Textarea, Input, useToast } from '@/components/ui';
import {
  BUREAUS,
  BUREAU_LABEL,
  CASE_STATUS_LABEL,
  PENDING_STEP_LABEL,
  type Bureau,
  type CaseStatus,
  type PendingStep,
} from '@/lib/constants';
import { describeActionError, type CaseDetail } from './shared';

export type ActionKind = 'status' | 'transfer' | 'remark' | 'atr' | 'dispose';

const OFFICER_ROLES = ['PGRC_OFFICER', 'RB_OFFICER', 'APPROVAL_OFFICER', 'VIGILANCE_OFFICER', 'RO_OFFICER', 'BUREAU_HEAD'];

/** the API specification role table: edit/transfer/dispose = owner-bureau officers, bureau head of the owner bureau, ADMIN. */
export function canWorkCase(user: AuthUser | null, c: Pick<CaseDetail, 'owner_bureau' | 'owner_ro_code'>): boolean {
  if (!user) return false;
  if (user.role === 'ADMIN') return true;
  if (!OFFICER_ROLES.includes(user.role)) return false;
  if (user.bureau !== c.owner_bureau) return false;
  if (user.role === 'RO_OFFICER' && c.owner_ro_code && user.ro_code && user.ro_code !== c.owner_ro_code) return false;
  return true;
}

/** Decide link: owner officer of either case, bureau heads, ADMIN. */
export function canDecideLink(user: AuthUser | null, c: Pick<CaseDetail, 'owner_bureau'>, otherBureau: string): boolean {
  if (!user) return false;
  if (user.role === 'ADMIN' || user.role === 'BUREAU_HEAD') return true;
  return OFFICER_ROLES.includes(user.role) && (user.bureau === c.owner_bureau || user.bureau === otherBureau);
}

const REQUIRED_REMARK = 3;

interface ActionModalProps {
  kind: ActionKind | null;
  caseData: CaseDetail;
  onClose: () => void;
}

const TITLES: Record<ActionKind, string> = {
  status: 'Update status',
  transfer: 'Transfer case',
  remark: 'Add remark',
  atr: 'Mark ATR received',
  dispose: 'Dispose case',
};

const SUBMIT: Record<ActionKind, string> = {
  status: 'Update status',
  transfer: 'Transfer',
  remark: 'Add remark',
  atr: 'Mark ATR received',
  dispose: 'Dispose case',
};

const EDITABLE_STATUSES = (Object.keys(CASE_STATUS_LABEL) as CaseStatus[]).filter((s) => s !== 'DISPOSED' && s !== 'TRANSFERRED');

/** One modal for the five case actions. Every action writes a Passport entry server-side. */
export function CaseActionModal({ kind, caseData, onClose }: ActionModalProps) {
  if (!kind) return null;
  return <Inner key={kind} kind={kind} caseData={caseData} onClose={onClose} />;
}

function Inner({ kind, caseData, onClose }: { kind: ActionKind; caseData: CaseDetail; onClose: () => void }) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [remark, setRemark] = useState('');
  const [status, setStatus] = useState<CaseStatus>(caseData.status as CaseStatus);
  const [step, setStep] = useState<PendingStep>(caseData.pending_step as PendingStep);
  const [pendingAction, setPendingAction] = useState(caseData.pending_action ?? '');
  const transferTargets = BUREAUS.filter((b): b is Bureau => b !== 'ADMIN' && b !== caseData.owner_bureau);
  const [toBureau, setToBureau] = useState<Bureau>(transferTargets[0]);

  const remarkRequired = kind === 'transfer' || kind === 'remark' || kind === 'dispose';
  const remarkOk = !remarkRequired || remark.trim().length >= REQUIRED_REMARK;
  const id = caseData.id;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = remark.trim();
      if (kind === 'status') {
        await api.patch(`/cases/${id}`, { status, pending_step: step, pending_action: pendingAction.trim() || null });
      } else if (kind === 'transfer') {
        await api.post(`/cases/${id}/transfer`, { to_bureau: toBureau, remark: r });
      } else if (kind === 'remark') {
        await api.post(`/cases/${id}/remarks`, { remark: r });
      } else if (kind === 'atr') {
        await api.patch(`/cases/${id}`, { status: 'UNDER_PROCESS', pending_step: 'NONE', pending_action: null, atr_received: true, ...(r ? { remark: r } : {}) });
      } else {
        await api.post(`/cases/${id}/dispose`, { remark: r });
      }
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['case'] }),
        qc.invalidateQueries({ queryKey: ['cases'] }),
        qc.invalidateQueries({ queryKey: ['passport'] }),
        qc.invalidateQueries({ queryKey: ['institution'] }),
      ]);
      toast(`${TITLES[kind]}: recorded in the Case Passport.`, 'ok');
      onClose();
    } catch (e) {
      setError(describeActionError(e));
    } finally {
      setBusy(false);
    }
  };

  let fields: ReactNode;
  switch (kind) {
    case 'status':
      fields = (
        <>
          <Field label="Status">
            <Select value={status} onChange={(e) => setStatus(e.target.value as CaseStatus)}>
              {EDITABLE_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {CASE_STATUS_LABEL[s]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Pending step">
            <Select value={step} onChange={(e) => setStep(e.target.value as PendingStep)}>
              {(Object.keys(PENDING_STEP_LABEL) as PendingStep[]).map((s) => (
                <option key={s} value={s}>
                  {PENDING_STEP_LABEL[s]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Pending action" hint="Optional note on what is awaited, e.g. reminder issued.">
            <Input value={pendingAction} maxLength={200} onChange={(e) => setPendingAction(e.target.value)} />
          </Field>
        </>
      );
      break;
    case 'transfer':
      fields = (
        <>
          <Field label="Transfer to bureau" required>
            <Select value={toBureau} onChange={(e) => setToBureau(e.target.value as Bureau)}>
              {transferTargets.map((b) => (
                <option key={b} value={b}>
                  {BUREAU_LABEL[b]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Remark" required hint="Recorded in the Passport and shown to the receiving bureau.">
            <Textarea rows={3} value={remark} onChange={(e) => setRemark(e.target.value)} />
          </Field>
        </>
      );
      break;
    case 'atr':
      fields = (
        <>
          <p className="m-0 text-sm text-ink-700">
            Records that the Action Taken Report has been received. The case moves to Under process and the pending step is cleared.
          </p>
          <Field label="Remark" hint="Optional.">
            <Textarea rows={3} value={remark} onChange={(e) => setRemark(e.target.value)} />
          </Field>
        </>
      );
      break;
    case 'dispose':
      fields = (
        <>
          <p className="m-0 text-sm text-ink-700">Disposal closes the case. The remark is recorded in the hash-chained Case Passport.</p>
          <Field label="Disposal remark" required>
            <Textarea rows={3} value={remark} onChange={(e) => setRemark(e.target.value)} />
          </Field>
        </>
      );
      break;
    default:
      fields = (
        <Field label="Remark" required>
          <Textarea rows={4} value={remark} onChange={(e) => setRemark(e.target.value)} />
        </Field>
      );
  }

  return (
    <Modal
      open
      onClose={busy ? () => undefined : onClose}
      title={`${TITLES[kind]} · ${caseData.display_id}`}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void submit()} loading={busy} disabled={!remarkOk}>
            {SUBMIT[kind]}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {fields}
        {error && (
          <p role="alert" className="m-0 rounded border border-red bg-red-bg px-3 py-2 text-sm text-red">
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}
