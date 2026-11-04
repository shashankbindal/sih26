import { Link } from 'react-router-dom';

interface Try {
  who: string;
  what: string;
  /** Marker colour; PGRC navy would vanish on the navy panel, so it gets a light marker. */
  marker: string;
}

const TRY: Try[] = [
  { who: 'PGRC officer', what: 'enter a Hindi complaint and see related cases', marker: 'var(--surface)' },
  { who: 'Approval officer', what: 'run a Pre-Action Check before a deposit release', marker: 'var(--bureau-approval)' },
  { who: 'Senior management', what: 'see what needs attention', marker: 'var(--on-dark-muted)' },
  { who: 'Admin', what: 'reset the demo data', marker: 'var(--on-dark-muted)' },
];

/** Left navy panel: wordmark, headline, what to try, footer. Secondary text uses --on-dark-muted (>= 4.5:1). */
export function LoginAside() {
  return (
    <aside className="flex shrink-0 flex-col justify-between gap-10 bg-navy px-10 py-10 text-surface min-[901px]:order-first min-[901px]:w-[42%] min-[1536px]:px-20 min-[1536px]:py-14">
      <div>
        <div className="flex items-baseline gap-3">
          <span className="text-md font-semibold">Lok Sutra</span>
          <span lang="hi" className="text-base text-on-dark">
            लोक सूत्र
          </span>
        </div>
        <div className="mt-0.5 text-xs text-on-dark">AICTE {'·'} Complaint Coordination</div>
      </div>

      <div className="max-w-[560px]">
        <h2 className="text-[40px] font-semibold leading-[1.1] min-[1536px]:text-[52px]">
          One institution.
          <br />
          One truth.
        </h2>
        <div lang="hi" className="mt-2 text-md text-on-dark">
          एक संस्थान, एक सत्य
        </div>
        <p className="mt-5 text-base text-surface" style={{ lineHeight: 1.55 }}>
          Lok Sutra gives every AICTE officer one verified view of a college, and tells them when another bureau is already acting on it.
        </p>

        <div className="mt-8 border-t border-ink-500 pt-4">
          <h3 className="text-2xs font-semibold uppercase tracking-[0.04em] text-on-dark">What you can try</h3>
          <ul className="m-0 mt-3 flex list-none flex-col gap-2.5 p-0 text-sm">
            {TRY.map((t) => (
              <li key={t.who} className="flex items-start gap-3">
                <span aria-hidden className="mt-[5px] inline-block h-2.5 w-2.5 shrink-0" style={{ background: t.marker }} />
                <span>
                  <span className="font-semibold text-surface">{t.who}:</span> <span className="text-on-dark">{t.what}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-xs text-on-dark">
        <span>SIH 2026 {'·'} SIH26264 {'·'} Team Neurals Knight</span>
        <Link to="/home" className="focus-ring rounded text-surface underline">
          Back to home
        </Link>
      </div>
    </aside>
  );
}
