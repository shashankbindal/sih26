import type { Tone } from '@/lib/constants';

// Display labels for institution enums (the data model institutions.inst_type / approval_status).
export const INSTITUTION_TYPES = ['Engineering', 'Management', 'Pharmacy', 'Polytechnic', 'MCA'] as const;

export const APPROVAL_LABEL: Record<string, string> = {
  APPROVED: 'Approved',
  CLOSURE_APPLIED: 'Closure applied',
  CLOSED: 'Closed',
  NO_ADMISSION_YEAR: 'No admission year',
};

export const APPROVAL_TONE: Record<string, Tone> = {
  APPROVED: 'ok',
  CLOSURE_APPLIED: 'amber',
  CLOSED: 'neutral',
  NO_ADMISSION_YEAR: 'amber',
};
