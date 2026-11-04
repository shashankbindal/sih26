import type { ReactNode } from 'react';
import { cx } from '@/lib/cx';
import type { Tone } from '@/lib/constants';

const toneClass: Record<Tone, string> = {
  ok: 'bg-ok-bg text-ok',
  amber: 'bg-amber-bg text-amber',
  red: 'bg-red-bg text-red',
  info: 'bg-info-bg text-info',
  neutral: 'bg-neutral-bg text-neutral',
};

export interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  title?: string;
}

/** 20px tall, 11-12px/500, radius 3, tinted background + darker text. Text is always present. */
export function Badge({ tone = 'neutral', children, className, title }: BadgeProps) {
  return (
    <span
      title={title}
      className={cx(
        'inline-flex h-5 items-center whitespace-nowrap rounded-sm px-1.5 text-xs font-medium leading-none',
        toneClass[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Small coloured status square used in toasts and legends. */
export function StatusSquare({ tone = 'neutral', className }: { tone?: Tone; className?: string }) {
  const bg: Record<Tone, string> = {
    ok: 'bg-ok',
    amber: 'bg-amber',
    red: 'bg-red',
    info: 'bg-info',
    neutral: 'bg-ink-300',
  };
  return <span aria-hidden className={cx('inline-block h-2 w-2 shrink-0', bg[tone], className)} />;
}
