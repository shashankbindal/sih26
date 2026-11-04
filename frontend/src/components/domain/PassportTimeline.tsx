import { cx } from '@/lib/cx';
import { formatDateTime, shortHash } from '@/lib/format';
import { BureauTag } from './BureauTag';
import type { Bureau } from '@/lib/constants';
import { Button } from '@/components/ui/Button';

export interface PassportEntry {
  seq: number;
  event: string;
  actor_name?: string | null;
  bureau?: Bureau | null;
  at: string;
  remark?: string | null;
  /** Short or full hash; shown as a3f9…c21e. */
  hash: string;
  prev_hash?: string | null;
}

export interface ChainVerification {
  ok: boolean;
  count: number;
  first_bad_seq?: number | null;
  checked_at?: string | null;
}

export interface PassportTimelineProps {
  entries: PassportEntry[];
  verification?: ChainVerification | null;
  onVerify?: () => void;
  verifying?: boolean;
  className?: string;
}

/** Hash-chained Case Passport: vertical rule, 8px squares, mono short hash, chain-verified bar with break highlighting. */
export function PassportTimeline({ entries, verification, onVerify, verifying, className }: PassportTimelineProps) {
  const bad = verification && !verification.ok ? (verification.first_bad_seq ?? null) : null;
  return (
    <div className={className}>
      <div
        className={cx(
          'mb-3 flex min-h-9 items-center justify-between gap-3 rounded border px-3 text-sm',
          !verification && 'border-line bg-paper text-ink-500',
          verification?.ok && 'border-ok bg-ok-bg text-ok',
          verification && !verification.ok && 'border-red bg-red-bg text-red',
        )}
        role="status"
      >
        <span className="font-medium">
          {!verification && `Chain not yet verified · ${entries.length} entries`}
          {verification?.ok && (
            <>
              <span aria-hidden className="mr-1.5 font-sans">{'✓'}</span>
              Chain verified {'·'} {verification.count} entries
            </>
          )}
          {verification && !verification.ok && (
            <>
              <span aria-hidden className="mr-1.5 font-sans">{'✗'}</span>
              Chain broken at entry {bad ?? '?'} {'·'} {verification.count} entries checked
            </>
          )}
        </span>
        <span className="flex items-center gap-3">
          {verification?.checked_at && <span className="text-xs text-ink-500">Checked {formatDateTime(verification.checked_at)}</span>}
          {onVerify && (
            <Button variant="secondary" className="!h-7 !px-2" onClick={onVerify} loading={verifying}>
              Verify chain
            </Button>
          )}
        </span>
      </div>

      <ol className="relative m-0 list-none p-0">
        <span aria-hidden className="absolute bottom-2 left-[3px] top-2 w-px bg-line" />
        {entries.map((e) => {
          const broken = bad !== null && e.seq >= bad;
          return (
            <li key={e.seq} className="relative pb-4 pl-6 last:pb-0">
              <span aria-hidden className={cx('absolute left-0 top-[5px] h-2 w-2', broken ? 'bg-red' : 'bg-navy')} />
              <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                <span className={cx('text-sm font-semibold', broken ? 'text-red' : 'text-ink-900')}>{e.event}</span>
                <span className="font-mono text-xs tnum text-ink-500" title={e.hash}>
                  {shortHash(e.hash)}
                </span>
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-ink-500">
                {e.actor_name && <span>{e.actor_name}</span>}
                {e.bureau && <BureauTag bureau={e.bureau} />}
                <span className="tnum">{formatDateTime(e.at)}</span>
              </div>
              {e.remark && <div className="mt-1 text-sm text-ink-700">{e.remark}</div>}
              {broken && e.seq === bad && <div className="mt-1 text-xs font-medium text-red">Hash does not match the previous entry.</div>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
