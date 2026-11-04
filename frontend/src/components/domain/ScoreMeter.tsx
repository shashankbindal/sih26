import { usePolicyThresholds } from '@/api/hooks';
import { formatScore } from '@/lib/format';
import { cx } from '@/lib/cx';

export interface ScoreMeterProps {
  /** 0..1 */
  score: number;
  /** Tick positions. When omitted they are read from policy_config (admin thresholds); if unavailable no ticks are drawn. */
  thresholds?: { review: number; auto: number };
  /** Bar width in px (default 120). */
  width?: number;
  className?: string;
  hideValue?: boolean;
  /** Hide the Review / Auto captions under the ticks (candidate lists repeat the meter per row). */
  hideLabels?: boolean;
  /** Decimal places for the value (default 2; pass 3 so 0.998 does not round to 1.00). */
  decimals?: number;
}

/** 120px bar, filled to score, ticks at the Review and Auto thresholds, mono value. */
export function ScoreMeter({ score, thresholds, width = 120, className, hideValue, hideLabels, decimals = 2 }: ScoreMeterProps) {
  const fetched = usePolicyThresholds(!thresholds);
  const review = thresholds?.review ?? fetched?.review;
  const auto = thresholds?.auto ?? fetched?.auto;
  const pct = Math.max(0, Math.min(1, score)) * 100;
  const hasTicks = review !== undefined && auto !== undefined;
  const value = formatScore(score, decimals);
  return (
    <div className={cx('inline-flex flex-col', className)}>
      <div className="flex items-center gap-2">
        <div
          className="relative h-2 shrink-0 bg-line-soft"
          style={{ width }}
          role="meter"
          aria-valuemin={0}
          aria-valuemax={1}
          aria-valuenow={score}
          aria-label={`Match score ${value}`}
        >
          <div className="absolute inset-y-0 left-0 bg-navy" style={{ width: `${pct}%` }} />
          {hasTicks &&
            [review, auto].map((t) => (
              <span key={t} aria-hidden className="absolute -bottom-0.5 -top-0.5 w-px bg-ink-700" style={{ left: `${t * 100}%` }} />
            ))}
        </div>
        {!hideValue && <span className="font-mono text-xs tnum text-ink-900">{value}</span>}
      </div>
      {hasTicks && !hideLabels && (
        // Captions share the bar's width; "Auto" may run past the bar into the (empty) value column, never clipped.
        <div className="relative mt-0.5 h-3 text-2xs leading-none text-ink-500" style={{ width }} aria-hidden>
          <span className="absolute -translate-x-full whitespace-nowrap pr-0.5" style={{ left: `${review * 100}%` }}>
            Review
          </span>
          <span className="absolute whitespace-nowrap pl-0.5" style={{ left: `${auto * 100}%` }}>
            Auto
          </span>
        </div>
      )}
    </div>
  );
}
