import type { CaseStatus } from '@/lib/constants';

// Plain-English wording for the dashboard. Labels only: the values the API uses stay as they are.
export const PLAIN_STATUS: Record<CaseStatus, string> = {
  RECEIVED: 'Just received',
  UNDER_PROCESS: 'Being worked on',
  AWAITING_ATR: "Waiting for institution's report",
  AWAITING_COMPLAINANT: 'Waiting for complainant',
  TRANSFERRED: 'Sent to another bureau',
  ESCALATED: 'Escalated to senior',
  DISPOSED: 'Closed',
  CLOSED_NO_ACTION: 'Closed, no action',
  REOPENED: 'Reopened',
};

export const HELP = {
  bureau: 'Cases that are still open, grouped by the bureau handling them. The colours inside each bar show where those cases stand.',
  deadlines: 'Three separate deadline rules. Each bar counts cases against one rule, and one case can be on more than one rule.',
  ageing: 'Open cases grouped by how long ago they were received.',
  region: 'Open cases by Regional Office. A bigger bubble means more open cases; its colour shows how many of them are past a deadline.',
  trend: 'How many cases arrived and how many were closed in each month.',
  category: 'Open cases grouped by the kind of complaint.',
  institutions: 'Institutions with the most open cases. This is a count of cases, not a judgement on the institution.',
  alerts: 'Two or more cases on the same institution that different bureaus may need to handle together. These are suggestions for officers to review.',
} as const;
