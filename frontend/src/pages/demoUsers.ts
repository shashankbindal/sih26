import { BUREAU_COLOR_VAR, BUREAU_LABEL, ROLE_LABEL, type Bureau, type Role } from '@/lib/constants';

export interface DemoUser {
  email: string;
  name: string;
  role: Role;
  bureau: Bureau;
  ro_code?: string | null;
}

export const DEMO_PASSWORD = 'Demo@2026';

// Built-in copy of the seed-data plan section 5, used when /auth/demo-users is unreachable.
export const FALLBACK_USERS: DemoUser[] = [
  { email: 'pgrc.officer@demo.loksutra.in', name: 'Ritu Sharma', role: 'PGRC_OFFICER', bureau: 'PGRC' },
  { email: 'pgrc.head@demo.loksutra.in', name: 'Dr. Anil Verma', role: 'BUREAU_HEAD', bureau: 'PGRC' },
  { email: 'rb.officer@demo.loksutra.in', name: 'Karthik Iyer', role: 'RB_OFFICER', bureau: 'RB' },
  { email: 'rb.head@demo.loksutra.in', name: 'Meenakshi Rao', role: 'BUREAU_HEAD', bureau: 'RB' },
  { email: 'approval.officer@demo.loksutra.in', name: 'Sandeep Kulkarni', role: 'APPROVAL_OFFICER', bureau: 'APPROVAL' },
  { email: 'vigilance.officer@demo.loksutra.in', name: 'Farhan Qureshi', role: 'VIGILANCE_OFFICER', bureau: 'VIGILANCE' },
  { email: 'ro.kanpur@demo.loksutra.in', name: 'Pooja Mishra', role: 'RO_OFFICER', bureau: 'RO', ro_code: 'KNP' },
  { email: 'ro.bhopal@demo.loksutra.in', name: 'Vivek Chouhan', role: 'RO_OFFICER', bureau: 'RO', ro_code: 'BPL' },
  { email: 'ro.chandigarh@demo.loksutra.in', name: 'Harpreet Gill', role: 'RO_OFFICER', bureau: 'RO', ro_code: 'CHD' },
  { email: 'mgmt@demo.loksutra.in', name: 'Office of Member Secretary', role: 'SENIOR_MGMT', bureau: 'ADMIN' },
  { email: 'admin@demo.loksutra.in', name: 'System Admin (PGRC)', role: 'ADMIN', bureau: 'ADMIN' },
  { email: 'pgrc.officer2@demo.loksutra.in', name: 'Neha Gupta', role: 'PGRC_OFFICER', bureau: 'PGRC' },
];

/** The four accounts that cover the demo script, shown first under "Start here". */
export const START_HERE_EMAILS = [
  'pgrc.officer@demo.loksutra.in',
  'approval.officer@demo.loksutra.in',
  'mgmt@demo.loksutra.in',
  'admin@demo.loksutra.in',
];

export function unwrapUsers(data: unknown): DemoUser[] {
  const list = Array.isArray(data) ? data : ((data as { items?: unknown[] } | null)?.items ?? []);
  return (list as DemoUser[]).filter((u) => u && typeof u.email === 'string');
}

export function splitUsers(users: DemoUser[]): { start: DemoUser[]; more: DemoUser[] } {
  const start = START_HERE_EMAILS.map((e) => users.find((u) => u.email === e)).filter((u): u is DemoUser => !!u);
  const more = users.filter((u) => !start.includes(u));
  return { start, more };
}

export function roleLabel(u: DemoUser): string {
  const base = ROLE_LABEL[u.role] ?? u.role;
  return u.role === 'RO_OFFICER' && u.ro_code ? `${base} (${u.ro_code})` : base;
}

/** Fixed bureau colour for the left bar; management and admin use the neutral token. */
export function bureauColour(u: DemoUser): string {
  return BUREAU_COLOR_VAR[u.bureau] ?? 'var(--ink-300)';
}

export function bureauName(u: DemoUser): string {
  return BUREAU_LABEL[u.bureau] ?? u.bureau;
}
