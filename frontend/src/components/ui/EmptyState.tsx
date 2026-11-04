import type { ReactNode } from 'react';
import { cx } from '@/lib/cx';

export interface EmptyStateProps {
  /** One sentence. */
  message: ReactNode;
  /** One action (Button / ButtonLink). */
  action?: ReactNode;
  className?: string;
  tone?: 'default' | 'error';
}

/** One line of text and one action. No illustrations. */
export function EmptyState({ message, action, className, tone = 'default' }: EmptyStateProps) {
  return (
    <div className={cx('flex items-center gap-3 px-3 py-4 text-sm', tone === 'error' ? 'text-red' : 'text-ink-500', className)}>
      <span>{message}</span>
      {action}
    </div>
  );
}
