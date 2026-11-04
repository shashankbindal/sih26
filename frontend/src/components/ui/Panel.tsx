import type { ReactNode } from 'react';
import { cx } from '@/lib/cx';

export interface PanelProps {
  title?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  /** Pad the body (default true). Use false for tables that go edge to edge. */
  padded?: boolean;
  className?: string;
  bodyClassName?: string;
  id?: string;
}

/** White, 1px line, radius 4, 40px header row with 13px/600 title and right-side actions. No shadow. */
export function Panel({ title, actions, children, padded = true, className, bodyClassName, id }: PanelProps) {
  return (
    <section id={id} className={cx('rounded border border-line bg-surface', className)}>
      {(title || actions) && (
        <header className="flex h-10 items-center justify-between gap-3 border-b border-line px-3">
          <h2 className="text-sm font-semibold text-ink-900">{title}</h2>
          {actions && <div className="flex items-center gap-2 text-sm">{actions}</div>}
        </header>
      )}
      <div className={cx(padded && 'p-3', bodyClassName)}>{children}</div>
    </section>
  );
}
