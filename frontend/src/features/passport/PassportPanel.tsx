import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, errorMessage } from '@/api/client';
import { useApiQuery } from '@/api/hooks';
import type { Schemas } from '@/api/types';
import { EmptyState, SkeletonRows } from '@/components/ui';
import { PassportTimeline, type ChainVerification, type PassportEntry } from '@/components/domain';

import { describeEvent } from './describe';

type PassportEntryOut = Schemas['PassportEntryOut'];
type PassportOut = Schemas['PassportOut'];
type VerifyOut = Schemas['VerifyOut'];

export function toTimelineEntries(entries: PassportEntryOut[]): PassportEntry[] {
  return entries.map((e) => {
    const d = describeEvent(e.event, e.payload);
    return {
      seq: e.seq,
      event: d.label,
      actor_name: e.actor_name,
      bureau: e.actor_bureau ?? null,
      at: e.created_at,
      remark: d.summary,
      hash: e.hash,
      prev_hash: e.prev_hash,
    };
  });
}

export interface PassportPanelProps {
  /** e.g. `/cases/{id}/passport` or `/institution-actions/{id}/passport`. */
  path: string;
  /** Defaults to `${path}/verify`. */
  verifyPath?: string;
  /** Query key prefix; changes when the subject changes. */
  queryKey: readonly unknown[];
  newestFirst?: boolean;
}

/** Hash-chained timeline with a Verify chain control. Reusable for case-level and institution-action-level chains. */
export function PassportPanel({ path, verifyPath, queryKey, newestFirst = true }: PassportPanelProps) {
  const qc = useQueryClient();
  const q = useApiQuery<PassportOut>(['passport', ...queryKey], path);
  const [verification, setVerification] = useState<ChainVerification | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  const verify = async () => {
    setVerifying(true);
    setVerifyError(null);
    try {
      const res = await api.get<VerifyOut>(verifyPath ?? `${path}/verify`);
      setVerification({ ok: res.ok, count: res.count, first_bad_seq: res.first_bad_seq, checked_at: res.checked_at });
      void qc.invalidateQueries({ queryKey: ['passport', ...queryKey] });
    } catch (e) {
      setVerifyError(errorMessage(e));
    } finally {
      setVerifying(false);
    }
  };

  if (q.isLoading) return <SkeletonRows rows={5} cols={3} />;
  if (q.isError) return <EmptyState tone="error" message={`The Passport could not be loaded. ${errorMessage(q.error)}`} />;
  const raw = q.data?.entries ?? [];
  if (raw.length === 0) return <EmptyState message="No Passport entries recorded yet." />;
  const ordered = newestFirst ? [...raw].sort((a, b) => b.seq - a.seq) : raw;

  return (
    <div>
      <PassportTimeline entries={toTimelineEntries(ordered)} verification={verification} onVerify={() => void verify()} verifying={verifying} />
      {verifyError && (
        <p role="alert" className="mt-2 text-sm text-red">
          Verification could not run. {verifyError}
        </p>
      )}
    </div>
  );
}
