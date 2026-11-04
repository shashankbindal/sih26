import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Skeleton } from '@/components/ui';
import { cx } from '@/lib/cx';
import { formatNumber } from '@/lib/format';

export interface AttentionItem {
  key: string;
  label: string;
  /** One short line saying what the number means. */
  hint: string;
  value: number | undefined;
  loading?: boolean;
  to?: string;
  /** Native tooltip (e.g. per-clock breakdown). */
  title?: string;
  /** Solid accent colour (CSS variable) for the left bar. */
  bar: string;
  /** Text colour for the number; must reach 4.5:1 on its background. */
  ink: string;
  /** Optional solid tint behind the cell. */
  bg?: string;
  /** Shown instead of the hint when the count is zero. */
  zeroHint?: string;
}

function Cell({ it }: { it: AttentionItem }) {
  const zero = it.value === 0;
  const body: ReactNode = (
    <>
      <span aria-hidden className="absolute inset-y-0 left-0 w-1.5" style={{ background: zero ? 'var(--line)' : it.bar }} />
      <span className="block text-[34px] font-semibold leading-none tnum" style={{ color: zero ? 'var(--ink-500)' : it.ink }}>
        {it.loading ? <Skeleton width={56} height={32} /> : it.value === undefined ? '–' : formatNumber(it.value)}
      </span>
      <span className="mt-2 block text-base font-semibold leading-tight text-ink-900">{it.label}</span>
      <span className="mt-1 block text-sm leading-snug text-ink-700">{zero && it.zeroHint ? it.zeroHint : it.hint}</span>
    </>
  );
  const cls = cx('relative block min-h-[124px] rounded border border-line py-3 pl-5 pr-3 text-left', zero || !it.bg ? 'bg-surface' : '');
  const style = zero || !it.bg ? undefined : { background: it.bg };
  if (it.to)
    return (
      <Link to={it.to} title={it.title} className={cx(cls, 'text-ink-900 hover:border-ink-300 hover:no-underline focus-ring')} style={style}>
        {body}
      </Link>
    );
  return (
    <div className={cls} style={style} title={it.title}>
      {body}
    </div>
  );
}

/** "What needs my attention?": a row of large numbers with plain labels and a solid coloured left bar. */
export function AttentionRow({ items }: { items: AttentionItem[] }) {
  return (
    <section aria-label="What needs attention" className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' }}>
      {items.map((it) => (
        <Cell key={it.key} it={it} />
      ))}
    </section>
  );
}
