// Labels and display names only. Thresholds, clock durations and clause labels
// come from policy_config via the API and must never be hard-coded here.

export type Bureau = 'PGRC' | 'RB' | 'APPROVAL' | 'VIGILANCE' | 'RO' | 'ADMIN';
export const BUREAUS: Bureau[] = ['PGRC', 'RB', 'APPROVAL', 'VIGILANCE', 'RO', 'ADMIN'];
export const BUREAU_LABEL: Record<Bureau, string> = {
  PGRC: 'PGRC',
  RB: 'RB',
  APPROVAL: 'Approval',
  VIGILANCE: 'Vigilance',
  RO: 'RO',
  ADMIN: 'Admin',
};
export const BUREAU_FULL_NAME: Record<Bureau, string> = {
  PGRC: 'Public Grievance Redressal Cell',
  RB: 'Regulation Bureau',
  APPROVAL: 'Approval Bureau',
  VIGILANCE: 'Vigilance',
  RO: 'Regional Office',
  ADMIN: 'Administration',
};
// Fixed bureau colours (CSS variables from tokens.css).
export const BUREAU_COLOR_VAR: Record<Bureau, string> = {
  PGRC: 'var(--bureau-pgrc)',
  RB: 'var(--bureau-rb)',
  APPROVAL: 'var(--bureau-approval)',
  VIGILANCE: 'var(--bureau-vigilance)',
  RO: 'var(--bureau-ro)',
  ADMIN: 'var(--bureau-admin)',
};

export type Role =
  | 'PGRC_OFFICER'
  | 'RB_OFFICER'
  | 'APPROVAL_OFFICER'
  | 'VIGILANCE_OFFICER'
  | 'RO_OFFICER'
  | 'BUREAU_HEAD'
  | 'SENIOR_MGMT'
  | 'ADMIN';
export const ROLE_LABEL: Record<Role, string> = {
  PGRC_OFFICER: 'PGRC officer',
  RB_OFFICER: 'RB officer',
  APPROVAL_OFFICER: 'Approval officer',
  VIGILANCE_OFFICER: 'Vigilance officer',
  RO_OFFICER: 'RO officer',
  BUREAU_HEAD: 'Bureau head',
  SENIOR_MGMT: 'Senior management',
  ADMIN: 'Administrator',
};
export const OFFICER_ROLES: Role[] = [
  'PGRC_OFFICER',
  'RB_OFFICER',
  'APPROVAL_OFFICER',
  'VIGILANCE_OFFICER',
  'RO_OFFICER',
  'BUREAU_HEAD',
  'ADMIN',
];

export type CaseStatus =
  | 'RECEIVED'
  | 'UNDER_PROCESS'
  | 'AWAITING_ATR'
  | 'AWAITING_COMPLAINANT'
  | 'TRANSFERRED'
  | 'ESCALATED'
  | 'DISPOSED'
  | 'CLOSED_NO_ACTION'
  | 'REOPENED';
export const CASE_STATUS_LABEL: Record<CaseStatus, string> = {
  RECEIVED: 'Received',
  UNDER_PROCESS: 'Under process',
  AWAITING_ATR: 'Awaiting ATR',
  AWAITING_COMPLAINANT: 'Awaiting complainant',
  TRANSFERRED: 'Transferred',
  ESCALATED: 'Escalated',
  DISPOSED: 'Disposed',
  CLOSED_NO_ACTION: 'Closed, no action',
  REOPENED: 'Reopened',
};
export type Tone = 'ok' | 'amber' | 'red' | 'info' | 'neutral';
export const CASE_STATUS_TONE: Record<CaseStatus, Tone> = {
  RECEIVED: 'info',
  UNDER_PROCESS: 'info',
  AWAITING_ATR: 'amber',
  AWAITING_COMPLAINANT: 'amber',
  TRANSFERRED: 'neutral',
  ESCALATED: 'red',
  DISPOSED: 'ok',
  CLOSED_NO_ACTION: 'neutral',
  REOPENED: 'amber',
};
export const OPEN_STATUSES: CaseStatus[] = [
  'RECEIVED',
  'UNDER_PROCESS',
  'AWAITING_ATR',
  'AWAITING_COMPLAINANT',
  'ESCALATED',
  'REOPENED',
];

export type CaseCategory =
  | 'FEE_REFUND'
  | 'CERTIFICATE_WITHHELD'
  | 'FACULTY_SHORTAGE'
  | 'INFRASTRUCTURE'
  | 'RAGGING'
  | 'FAKE_APPROVAL_CLAIM'
  | 'SCHOLARSHIP'
  | 'ADMISSION'
  | 'SERVICE_MATTER'
  | 'SCRUTINY_COMMITTEE'
  | 'OTHER';
export const CATEGORY_LABEL: Record<CaseCategory, string> = {
  FEE_REFUND: 'Fee refund',
  CERTIFICATE_WITHHELD: 'Certificate withheld',
  FACULTY_SHORTAGE: 'Faculty shortage',
  INFRASTRUCTURE: 'Infrastructure',
  RAGGING: 'Ragging',
  FAKE_APPROVAL_CLAIM: 'Fake approval claim',
  SCHOLARSHIP: 'Scholarship',
  ADMISSION: 'Admission',
  SERVICE_MATTER: 'Service matter',
  SCRUTINY_COMMITTEE: 'Scrutiny committee',
  OTHER: 'Other',
};

export type SourceChannel = 'CSS' | 'CPGRAMS' | 'EMAIL' | 'RO_REGISTER' | 'BUREAU_FILE' | 'CSV_IMPORT';
export const CHANNEL_LABEL: Record<SourceChannel, string> = {
  CSS: 'CSS',
  CPGRAMS: 'CPGRAMS',
  EMAIL: 'Email',
  RO_REGISTER: 'RO register',
  BUREAU_FILE: 'Bureau file',
  CSV_IMPORT: 'CSV import',
};

export type RelationType = 'UNRELATED' | 'DUPLICATE' | 'RELATED' | 'CONFLICTING';
export type LinkStatus = 'SUGGESTED' | 'CONFIRMED' | 'REJECTED' | 'DEFERRED' | 'SUPERSEDED';
export const LINK_STATUS_LABEL: Record<LinkStatus, string> = {
  SUGGESTED: 'Suggested',
  CONFIRMED: 'Confirmed',
  REJECTED: 'Rejected',
  DEFERRED: 'Deferred',
  SUPERSEDED: 'Superseded',
};

export type MatchStatus = 'EXACT' | 'AUTO_SUGGESTED' | 'NEEDS_REVIEW' | 'UNRESOLVED' | 'CONFIRMED' | 'REJECTED';
export const MATCH_STATUS_LABEL: Record<MatchStatus, string> = {
  EXACT: 'Exact match',
  AUTO_SUGGESTED: 'Auto-suggested',
  NEEDS_REVIEW: 'Needs review',
  UNRESOLVED: 'Unresolved',
  CONFIRMED: 'Confirmed',
  REJECTED: 'Rejected',
};
export const MATCH_STATUS_TONE: Record<MatchStatus, Tone> = {
  EXACT: 'ok',
  AUTO_SUGGESTED: 'info',
  NEEDS_REVIEW: 'amber',
  UNRESOLVED: 'red',
  CONFIRMED: 'ok',
  REJECTED: 'neutral',
};

export type ClockType = 'CPGRAMS_21D' | 'CSS_72H' | 'INST_REFUND_7D';
export type ClockState = 'ON_TRACK' | 'AMBER' | 'BREACHED' | 'PAUSED' | 'MET';
// Three separate clocks; never one "SLA". Names carry no durations; the API supplies
// the per-clock label text ("21-day · 6d left") and clause label.
export const CLOCK_NAME: Record<ClockType, string> = {
  CPGRAMS_21D: 'CPGRAMS clock',
  CSS_72H: 'CSS clock',
  INST_REFUND_7D: 'Institution refund clock',
};
export const CLOCK_STATE_LABEL: Record<ClockState, string> = {
  ON_TRACK: 'On track',
  AMBER: 'Due soon',
  BREACHED: 'Overdue',
  PAUSED: 'Paused',
  MET: 'Met',
};
export const CLOCK_STATE_TONE: Record<ClockState, Tone> = {
  ON_TRACK: 'ok',
  AMBER: 'amber',
  BREACHED: 'red',
  PAUSED: 'neutral',
  MET: 'ok',
};

export type PendingStep =
  | 'NONE'
  | 'INSTITUTION_ATR'
  | 'COMPLAINANT_REPLY'
  | 'HEARING'
  | 'INSPECTION'
  | 'SHOW_CAUSE_REPLY'
  | 'CLEARANCE'
  | 'REFUND_FOLLOWUP';
export const PENDING_STEP_LABEL: Record<PendingStep, string> = {
  NONE: 'None',
  INSTITUTION_ATR: 'Institution ATR',
  COMPLAINANT_REPLY: 'Complainant reply',
  HEARING: 'Hearing',
  INSPECTION: 'Inspection',
  SHOW_CAUSE_REPLY: 'Show-cause reply',
  CLEARANCE: 'Clearance',
  REFUND_FOLLOWUP: 'Refund follow-up',
};

export type InstActionType =
  | 'ISSUE_NOC'
  | 'SECURITY_DEPOSIT_RELEASE'
  | 'SHOW_CAUSE'
  | 'CLOSURE_APPROVAL'
  | 'EXTENSION_OF_APPROVAL'
  | 'INSPECTION_ORDER';
export const INST_ACTION_LABEL: Record<InstActionType, string> = {
  ISSUE_NOC: 'Issue NOC',
  SECURITY_DEPOSIT_RELEASE: 'Security-deposit release',
  SHOW_CAUSE: 'Show-cause',
  CLOSURE_APPROVAL: 'Closure approval',
  EXTENSION_OF_APPROVAL: 'Extension of approval',
  INSPECTION_ORDER: 'Inspection order',
};

export type ClearanceResponse = 'PENDING' | 'CLEARED' | 'NOT_CLEARED' | 'CLEARED_WITH_REMARKS';
export const CLEARANCE_RESPONSE_LABEL: Record<ClearanceResponse, string> = {
  PENDING: 'Pending',
  CLEARED: 'Cleared',
  NOT_CLEARED: 'Not cleared',
  CLEARED_WITH_REMARKS: 'Cleared with remarks',
};

export type NotificationKind =
  | 'COORDINATION_REQUIRED'
  | 'PRIORITY_REVIEW'
  | 'REVIEW_SUGGESTED'
  | 'CLEARANCE_REQUEST'
  | 'CLEARANCE_RESPONSE'
  | 'SLA_AMBER'
  | 'SLA_BREACH'
  | 'REVIEW_QUEUE';
export const NOTIFICATION_KIND_LABEL: Record<NotificationKind, string> = {
  COORDINATION_REQUIRED: 'Coordination',
  PRIORITY_REVIEW: 'Priority review',
  REVIEW_SUGGESTED: 'Review suggested',
  CLEARANCE_REQUEST: 'Clearance request',
  CLEARANCE_RESPONSE: 'Clearance response',
  SLA_AMBER: 'Clock due soon',
  SLA_BREACH: 'Clock overdue',
  REVIEW_QUEUE: 'Review queue',
};
