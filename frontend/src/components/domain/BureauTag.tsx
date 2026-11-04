import { BUREAU_COLOR_VAR, BUREAU_LABEL, type Bureau } from '@/lib/constants';
import { cx } from '@/lib/cx';

export interface BureauTagProps {
  bureau: Bureau;
  /** Regional office code, shown as "RO (KNP)". */
  roCode?: string | null;
  className?: string;
}

/** Fixed bureau colours everywhere (swatch + text). Saffron is never a bureau colour. */
export function BureauTag({ bureau, roCode, className }: BureauTagProps) {
  return (
    <span className={cx('inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium text-ink-900', className)}>
      <span aria-hidden className="inline-block h-2.5 w-2.5" style={{ background: BUREAU_COLOR_VAR[bureau] }} />
      {BUREAU_LABEL[bureau]}
      {roCode ? ` (${roCode})` : ''}
    </span>
  );
}
