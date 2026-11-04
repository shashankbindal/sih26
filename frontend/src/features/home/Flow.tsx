import { cx } from '@/lib/cx';
import { Section, SectionHeader } from './parts';
import { FLOW } from './content';

/** Four steps in a row. Saffron marks only the step that links bureaus. */
export function Flow() {
  return (
    <Section id="flow" tone="surface">
      <SectionHeader id="flow" title="How it works" hi="यह कैसे काम करता है" />
      <ol className="m-0 grid list-none gap-x-8 gap-y-7 p-0 sm:grid-cols-2 lg:grid-cols-4">
        {FLOW.map((s, i) => (
          <li key={s.title} className="relative">
            <span
              aria-hidden
              className={cx('inline-flex h-7 w-7 items-center justify-center rounded-sm font-mono text-sm font-semibold', s.link ? 'bg-saffron text-ink-900' : 'bg-navy text-surface')}
            >
              {i + 1}
            </span>
            {i < FLOW.length - 1 && (
              <span aria-hidden className="absolute left-10 right-0 top-[13px] hidden h-px bg-line lg:block">
                <svg width="8" height="9" viewBox="0 0 8 9" className="absolute -top-1 right-[-2px]" focusable="false">
                  <path d="M0 0L8 4.5L0 9Z" fill="var(--ink-300)" />
                </svg>
              </span>
            )}
            <h3 className="m-0 mt-3 text-[17px] font-semibold text-ink-900">
              <span className="sr-only">Step {i + 1}: </span>
              {s.title}
            </h3>
            <p className="m-0 mt-1.5 text-[16px] leading-relaxed text-ink-700">{s.line}</p>
          </li>
        ))}
      </ol>
    </Section>
  );
}
