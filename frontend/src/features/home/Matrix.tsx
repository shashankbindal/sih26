import { cx } from '@/lib/cx';
import { Section, SectionHeader } from './parts';
import { QUADRANTS, type Quadrant } from './content';

const TONE: Record<Quadrant['tone'], string> = {
  start: 'bg-ok-bg border-ok',
  plan: 'bg-surface border-line',
  later: 'bg-neutral-bg border-line',
};

/** Two by two: impact down (high first), feasibility across (harder first). Qualitative only. */
export function MatrixSection() {
  return (
    <Section id="matrix" tone="surface">
      <SectionHeader id="matrix" title="Impact and feasibility" hi="प्रभाव और व्यवहार्यता" />
      <div role="group" aria-label="Impact and feasibility matrix" className="grid grid-cols-2 gap-3">
        {QUADRANTS.map((q) => (
          <div key={q.key} className={cx('min-h-[130px] rounded border p-3 sm:p-4', TONE[q.tone])}>
            <div className="text-[16px] font-semibold text-ink-900">{q.caption}</div>
            <div className="mb-3 text-sm text-ink-700">{q.sub}</div>
            {q.chips.length > 0 ? (
              <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
                {q.chips.map((c) => (
                  <li
                    key={c.name}
                    className="rounded-sm border border-line border-l-4 bg-surface px-2 py-1 text-sm leading-tight text-ink-900"
                    style={{ borderLeftColor: c.coordination ? 'var(--saffron)' : 'var(--navy)' }}
                  >
                    {c.name}
                  </li>
                ))}
              </ul>
            ) : (
              <span className="sr-only">Nothing placed here</span>
            )}
          </div>
        ))}
      </div>
      <p className="mt-4 text-sm text-ink-500">
        Team judgement, not measured scores. Impact: fewer parallel actions and missed deadlines. Feasibility: uses data AICTE already has, with little change to the workflow.
        Saffron marks the parts that coordinate between teams.
      </p>
    </Section>
  );
}
