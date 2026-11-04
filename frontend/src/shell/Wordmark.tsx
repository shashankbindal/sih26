/** Text wordmark only: no emblem, no logo (State Emblem use is restricted). */
export function Wordmark({ tone = 'dark' }: { tone?: 'dark' | 'light' }) {
  const main = tone === 'dark' ? 'text-surface' : 'text-ink-900';
  const sub = tone === 'dark' ? 'text-on-dark' : 'text-ink-500';
  return (
    <div className="leading-tight">
      <div className="flex items-baseline gap-2">
        <span className={`text-md font-semibold ${main}`}>Lok Sutra</span>
        <span lang="hi" className={`text-sm ${sub}`}>
          लोक सूत्र
        </span>
      </div>
      <div className={`mt-0.5 text-2xs ${sub}`}>AICTE {'·'} Complaint Coordination</div>
    </div>
  );
}
