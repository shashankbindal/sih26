import type { ReactNode } from 'react';
import { cx } from '@/lib/cx';

export function Container({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx('mx-auto w-full max-w-[1000px] px-4 sm:px-6', className)}>{children}</div>;
}

/** Full-width band with a 1px rule; content is held to about 1000px. */
export function Section({ id, tone = 'paper', children }: { id: string; tone?: 'paper' | 'surface'; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className={cx('scroll-mt-14 border-b border-line py-12 md:py-14', tone === 'surface' ? 'bg-surface' : 'bg-paper')}>
      <Container>{children}</Container>
    </section>
  );
}

export function SectionHeader({ id, title, hi }: { id: string; title: string; hi: string }) {
  return (
    <h2 id={`${id}-h`} className="mb-8 flex flex-wrap items-baseline gap-x-3 text-[24px] font-semibold leading-tight text-ink-900">
      {title}
      <span lang="hi" className="text-[16px] font-medium text-ink-500">
        {hi}
      </span>
    </h2>
  );
}
