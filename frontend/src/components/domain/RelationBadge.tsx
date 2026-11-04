import { cx } from '@/lib/cx';
import type { RelationType } from '@/lib/constants';

const spec: Record<RelationType, { label: string; cls: string }> = {
  DUPLICATE: { label: 'Review suggested', cls: 'bg-info-bg text-info border border-transparent' },
  // Saffron is reserved for coordination UI: outline + saffron-bg.
  RELATED: { label: 'Coordination required', cls: 'bg-saffron-bg text-amber border border-saffron' },
  CONFLICTING: { label: 'Priority review', cls: 'bg-red-bg text-red border border-transparent' },
  UNRELATED: { label: 'Unrelated', cls: 'bg-neutral-bg text-neutral border border-transparent' },
};

export const RELATION_LABEL: Record<RelationType, string> = {
  DUPLICATE: spec.DUPLICATE.label,
  RELATED: spec.RELATED.label,
  CONFLICTING: spec.CONFLICTING.label,
  UNRELATED: spec.UNRELATED.label,
};

export interface RelationBadgeProps {
  relation: RelationType;
  className?: string;
}

/** Advisory language only: "Review suggested", "Coordination required", "Priority review". */
export function RelationBadge({ relation, className }: RelationBadgeProps) {
  const s = spec[relation];
  return (
    <span className={cx('inline-flex h-5 items-center whitespace-nowrap rounded-sm px-1.5 text-xs font-medium leading-none', s.cls, className)}>
      {s.label}
    </span>
  );
}
