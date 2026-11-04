import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { cx } from '@/lib/cx';
import { formatNumber } from '@/lib/format';
import { Skeleton } from './Skeleton';

export interface KpiItem {
  key: string;
  label: string;
  value: number | string | null | undefined;
  /** e.g. 4 or -2 vs previous period; rendered as text with sign and arrow. */
  delta?: number | null;
  /** When lower is better (e.g. overdue), a rise is shown red. Default: rise is neutral-good. */
  deltaGoodWhen?: 'up' | 'down';
  /** Click-through to a filtered list. */
  to?: string;
  onClick?: () => void;
  /** Coordination KPIs use the saffron marker. */
  coordination?: boolean;
  /** Native tooltip text (additive; used for the per-clock overdue breakdown). */
  title?: string;
}

export interface KpiStripProps {
  items: KpiItem[];
  loading?: boolean;
  className?: string;
  footnote?: ReactNode;
}

function Delta({ delta, goodWhen }: { delta: number; goodWhen?: 'up' | 'down' }) {
  const up = delta > 0;
  const flat = delta === 0;
  const good = flat ? null : goodWhen ? (goodWhen === 'up') === up : null;
  const colour = good === null ? 'text-ink-500' : good ? 'text-ok' : 'text-red';
  const sign = up ? '+' : delta < 0 ? '−' : '';
  return (
    <span className={cx('tnum whitespace-nowrap text-xs', colour)} title="Change versus the previous period of the same length">
      {flat ? '–' : up ? '▲' : '▼'} {sign}
      {formatNumber(Math.abs(delta))}
    </span>
  );
}

/** One panel divided into cells by 1px vertical rules; 28px numbers; never a grid of tiles. */
export function KpiStrip({ items, loading, className, footnote }: KpiStripProps) {
  return (
    <section className={cx('rounded border border-line bg-surface', className)} aria-label="Key figures">
      <div className="flex overflow-x-auto">
        {items.map((it, i) => {
          const inner = (
            <>
              <div className={cx('min-h-[32px] text-xs leading-tight text-ink-500', it.coordination && 'pr-2.5')}>
                {it.coordination && <span aria-hidden className="absolute right-2.5 top-3.5 inline-block h-2 w-2 bg-saffron" />}
                {it.label}
              </div>
              <div className="mt-1 text-kpi font-semibold tnum text-ink-900">
                {loading ? <Skeleton width={48} height={28} /> : typeof it.value === 'number' ? formatNumber(it.value) : (it.value ?? '–')}
              </div>
              <div className="mt-0.5 h-4">
                {!loading && it.delta !== undefined && it.delta !== null && <Delta delta={it.delta} goodWhen={it.deltaGoodWhen} />}
              </div>
            </>
          );
          const cell = cx('relative min-w-[104px] flex-1 px-2 py-3 text-left', i > 0 && 'border-l border-line');
          if (it.to)
            return (
              <Link key={it.key} to={it.to} title={it.title} className={cx(cell, 'text-ink-900 hover:bg-navy-50 hover:no-underline focus-ring')}>
                {inner}
              </Link>
            );
          if (it.onClick)
            return (
              <button key={it.key} type="button" onClick={it.onClick} title={it.title} className={cx(cell, 'hover:bg-navy-50 focus-ring')}>
                {inner}
              </button>
            );
          return (
            <div key={it.key} title={it.title} className={cell}>
              {inner}
            </div>
          );
        })}
      </div>
      {footnote && <div className="border-t border-line px-4 py-1.5 text-xs text-ink-500">{footnote}</div>}
    </section>
  );
}
