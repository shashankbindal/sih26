import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Info } from 'lucide-react';
import { Button, EmptyState, Skeleton, Tooltip } from '@/components/ui';
import { errorMessage } from '@/api/client';
import { cx } from '@/lib/cx';
import { ICON } from '@/lib/icons';

export type Tint = 'navy' | 'amber' | 'info' | 'neutral' | 'saffron' | 'ok' | 'red';
const TINT: Record<Tint, string> = {
  navy: 'bg-navy-50',
  amber: 'bg-amber-bg',
  info: 'bg-info-bg',
  neutral: 'bg-neutral-bg',
  saffron: 'bg-saffron-bg',
  ok: 'bg-ok-bg',
  red: 'bg-red-bg',
};

export interface ChartPanelProps {
  /** Short title that states the takeaway. */
  title: string;
  /** One sentence stating the takeaway, shown above the chart. */
  takeaway?: ReactNode;
  /** One line explaining what the panel shows (tooltip on the info button). */
  help: string;
  /** Header band colour (a solid tint, never a gradient). */
  tint?: Tint;
  /** "View cases" click-through carrying the dashboard filters. */
  to?: string;
  linkLabel?: string;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  empty?: boolean;
  emptyMessage?: string;
  height: number;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}

/** Panel shell for every dashboard widget: tinted header band, help tooltip, skeleton, error and empty states. */
export function ChartPanel({
  title,
  help,
  takeaway,
  tint = 'navy',
  to,
  linkLabel = 'View cases',
  loading,
  error,
  onRetry,
  empty,
  emptyMessage = 'No cases match the current filters.',
  height,
  children,
  className,
  padded = true,
}: ChartPanelProps) {
  let body: ReactNode;
  if (loading) {
    body = (
      <div className="flex flex-col gap-3" style={{ height }} role="status" aria-label="Loading chart">
        <Skeleton width="38%" height={14} />
        <Skeleton height={height - 40} />
      </div>
    );
  } else if (error) {
    body = (
      <div style={{ minHeight: height }}>
        <EmptyState
          tone="error"
          message={`Could not load this panel. ${errorMessage(error)}`}
          action={
            onRetry && (
              <Button variant="secondary" onClick={onRetry}>
                Retry
              </Button>
            )
          }
        />
      </div>
    );
  } else if (empty) {
    body = (
      <div style={{ minHeight: height }}>
        <EmptyState message={emptyMessage} />
      </div>
    );
  } else {
    body = children;
  }
  return (
    <section className={cx('flex flex-col overflow-hidden rounded border border-line bg-surface', className)}>
      <header className={cx('flex min-h-[44px] items-center justify-between gap-3 border-b border-line px-4 py-2', TINT[tint])}>
        <h2 className="flex items-center gap-1.5 text-base font-semibold text-ink-900">
          {title}
          <Tooltip content={help}>
            <button type="button" aria-label="What this shows" className="focus-ring inline-flex h-5 w-5 items-center justify-center rounded text-ink-500 hover:text-ink-900">
              <Info {...ICON} size={15} />
            </button>
          </Tooltip>
        </h2>
        {to && (
          <Link to={to} className="whitespace-nowrap text-sm font-medium">
            {linkLabel}
          </Link>
        )}
      </header>
      <div className={cx('flex-1', padded && 'p-4')}>
        {takeaway && !loading && !error && !empty && <p className="mb-3 text-base font-medium text-ink-900">{takeaway}</p>}
        {body}
      </div>
    </section>
  );
}
