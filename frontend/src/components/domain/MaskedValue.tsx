import type { Bureau } from '@/lib/constants';
import { BUREAU_LABEL } from '@/lib/constants';

export interface MaskedValueProps {
  /** Bureau that owns the case, e.g. PGRC. */
  ownerBureau: Bureau | string;
  onRequestAccess?: () => void;
  className?: string;
}

/** Complainant PII hidden for non-owning bureaus and SENIOR_MGMT. */
export function MaskedValue({ ownerBureau, onRequestAccess, className }: MaskedValueProps) {
  const owner = ownerBureau in BUREAU_LABEL ? BUREAU_LABEL[ownerBureau as Bureau] : ownerBureau;
  return (
    <span className={className}>
      <span className="font-mono text-ink-500" title="Masked by privacy policy">
        {'••••'}
      </span>{' '}
      <span className="text-ink-500">(hidden {'—'} owned by {owner})</span>
      {onRequestAccess && (
        <>
          {' '}
          <button type="button" onClick={onRequestAccess} className="focus-ring text-navy underline-offset-2 hover:underline" style={{ background: 'none', border: 0, padding: 0, font: 'inherit' }}>
            Request access
          </button>
        </>
      )}
    </span>
  );
}
