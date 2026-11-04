import { cx } from '@/lib/cx';

export type Reason = string | { fact: string; detail?: string };

/** Engine reasons arrive as strings ("Same district: Kanpur Nagar"). Split into bold fact + muted detail. */
export function splitReason(r: Reason): { fact: string; detail?: string } {
  if (typeof r !== 'string') return r;
  const m = r.match(/^(.{3,60}?)(?:\s[—–-]\s|:\s)(.+)$/);
  return m ? { fact: m[1], detail: m[2] } : { fact: r };
}

export interface ReasonListProps {
  reasons: Reason[];
  numbered?: boolean;
  /** Show only the first n with a "Show all" control handled by the caller. */
  limit?: number;
  className?: string;
}

/** The visual star of CaseLink: each reason is a short bold fact then muted detail. Give it room. */
export function ReasonList({ reasons, numbered, limit, className }: ReasonListProps) {
  const shown = limit ? reasons.slice(0, limit) : reasons;
  const Tag = numbered ? 'ol' : 'ul';
  return (
    <Tag className={cx('m-0 flex list-none flex-col gap-1.5 p-0 text-sm', className)}>
      {shown.map((r, i) => {
        const { fact, detail } = splitReason(r);
        return (
          <li key={i} className="flex gap-2">
            <span aria-hidden className={cx('shrink-0 text-ink-300', numbered ? 'w-4 text-right font-mono text-xs leading-[1.45rem] tnum' : 'leading-[1.2rem]')}>
              {numbered ? `${i + 1}.` : '•'}
            </span>
            <span>
              <span className="font-semibold text-ink-900">{fact}</span>
              {detail && <span className="text-ink-500">{' — '}{detail}</span>}
            </span>
          </li>
        );
      })}
    </Tag>
  );
}
