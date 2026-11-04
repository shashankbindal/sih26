import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { cx } from '@/lib/cx';
import { Badge } from '@/components/ui/Badge';

export interface InstitutionCardData {
  id: string;
  name: string;
  /** 1-4463974255 */
  permanent_id: string;
  district?: string | null;
  state?: string | null;
  pincode?: string | null;
  ro_name?: string | null;
  institution_type?: string | null;
  approval_status?: string | null;
}

export interface InstitutionCardProps {
  institution: InstitutionCardData;
  /** Link the name to the Institution 360 page. */
  linked?: boolean;
  /** Right-aligned slot (ScoreMeter, Change/Confirm buttons). */
  aside?: ReactNode;
  /** Extra lines under the facts (reasons, aliases). */
  children?: ReactNode;
  className?: string;
}

/** Compact institution identity block: name, Permanent ID (mono), place, RO, type, approval status. */
export function InstitutionCard({ institution: i, linked = true, aside, children, className }: InstitutionCardProps) {
  const place = [i.district, i.state].filter(Boolean).join(', ') + (i.pincode ? ` ${i.pincode}` : '');
  return (
    <div className={cx('rounded border border-line bg-surface p-3', className)}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-md font-semibold leading-tight text-ink-900">
            {linked ? <Link to={`/institutions/${i.id}`}>{i.name}</Link> : i.name}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-ink-500">
            <span className="font-mono tnum text-ink-700">{i.permanent_id}</span>
            {place && <span>{'·'} {place}</span>}
            {i.ro_name && <span>{'·'} RO {i.ro_name}</span>}
            {i.institution_type && <span>{'·'} {i.institution_type}</span>}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {i.approval_status && <Badge tone={i.approval_status.toLowerCase() === 'approved' ? 'ok' : 'amber'}>{i.approval_status}</Badge>}
          {aside}
        </div>
      </div>
      {children && <div className="mt-2 border-t border-line-soft pt-2">{children}</div>}
    </div>
  );
}
