import { Badge } from '@/components/ui/Badge';
import {
  CASE_STATUS_LABEL,
  CASE_STATUS_TONE,
  LINK_STATUS_LABEL,
  MATCH_STATUS_LABEL,
  MATCH_STATUS_TONE,
  CLEARANCE_RESPONSE_LABEL,
  type CaseStatus,
  type ClearanceResponse,
  type LinkStatus,
  type MatchStatus,
  type Tone,
} from '@/lib/constants';

/** case_status enum -> tinted tag with text ("Awaiting ATR"). */
export function StatusTag({ status, className }: { status: CaseStatus; className?: string }) {
  return (
    <Badge tone={CASE_STATUS_TONE[status]} className={className}>
      {CASE_STATUS_LABEL[status]}
    </Badge>
  );
}

/** match_status enum: Auto-suggested / Needs review / Unresolved ... */
export function MatchStatusTag({ status, className }: { status: MatchStatus; className?: string }) {
  return (
    <Badge tone={MATCH_STATUS_TONE[status]} className={className}>
      {MATCH_STATUS_LABEL[status]}
    </Badge>
  );
}

const linkTone: Record<LinkStatus, Tone> = { SUGGESTED: 'info', CONFIRMED: 'ok', REJECTED: 'neutral', DEFERRED: 'amber', SUPERSEDED: 'neutral' };
export function LinkStatusTag({ status, className }: { status: LinkStatus; className?: string }) {
  return (
    <Badge tone={linkTone[status]} className={className}>
      {LINK_STATUS_LABEL[status]}
    </Badge>
  );
}

const clearanceTone: Record<ClearanceResponse, Tone> = { PENDING: 'amber', CLEARED: 'ok', NOT_CLEARED: 'red', CLEARED_WITH_REMARKS: 'info' };
export function ClearanceTag({ response, className }: { response: ClearanceResponse; className?: string }) {
  return (
    <Badge tone={clearanceTone[response]} className={className}>
      {CLEARANCE_RESPONSE_LABEL[response]}
    </Badge>
  );
}
