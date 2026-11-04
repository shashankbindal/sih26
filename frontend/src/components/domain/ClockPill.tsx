import { cx } from '@/lib/cx';
import { CLOCK_NAME, CLOCK_STATE_LABEL, CLOCK_STATE_TONE, type ClockState, type ClockType, type Tone } from '@/lib/constants';
import { Tooltip } from '@/components/ui/Tooltip';

const tone: Record<Tone, { pill: string; dot: string }> = {
  ok: { pill: 'bg-ok-bg text-ok', dot: 'bg-ok' },
  amber: { pill: 'bg-amber-bg text-amber', dot: 'bg-amber' },
  red: { pill: 'bg-red-bg text-red', dot: 'bg-red' },
  info: { pill: 'bg-info-bg text-info', dot: 'bg-info' },
  neutral: { pill: 'bg-neutral-bg text-neutral', dot: 'bg-ink-300' },
};

export interface ClockPillProps {
  /** Text from the API, e.g. "21-day · 6d left" or "Inst. 7-day · overdue 4 days". */
  label: string;
  state: ClockState;
  /** Clause label from policy_config clause_labels, shown in the tooltip. */
  clause?: string | null;
  /** Which of the three separate clocks this is (named in the tooltip; never "SLA"). */
  clock?: ClockType;
  className?: string;
}

/** Mono label, colour by state, tooltip with the clock name, state and rule label. */
export function ClockPill({ label, state, clause, clock, className }: ClockPillProps) {
  const t = tone[CLOCK_STATE_TONE[state]];
  const tip = (
    <span className="block">
      {clock && <span className="block font-medium">{CLOCK_NAME[clock]}</span>}
      <span className="block">{CLOCK_STATE_LABEL[state]}</span>
      {clause && <span className="block text-ink-300">{clause}</span>}
    </span>
  );
  return (
    <Tooltip content={tip}>
      <span className={cx('inline-flex h-5 cursor-default items-center gap-1.5 whitespace-nowrap rounded-sm px-1.5 font-mono text-xs leading-none tnum', t.pill, className)} tabIndex={0} aria-label={`${label}, ${CLOCK_STATE_LABEL[state]}`}>
        <span aria-hidden className={cx('inline-block h-1.5 w-1.5', t.dot)} />
        {label}
      </span>
    </Tooltip>
  );
}
