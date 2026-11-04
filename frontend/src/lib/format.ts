// Display formatting. Store UTC, show IST; numbers in Indian grouping.
const TZ = 'Asia/Kolkata';

type Input = string | number | Date | null | undefined;
const EMPTY = '–'; // en dash for missing values

function toDate(v: Input): Date | null {
  if (v === null || v === undefined || v === '') return null;
  const d = v instanceof Date ? v : new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

function parts(d: Date, opts: Intl.DateTimeFormatOptions): Record<string, string> {
  const out: Record<string, string> = {};
  for (const p of new Intl.DateTimeFormat('en-GB', { timeZone: TZ, ...opts }).formatToParts(d)) {
    out[p.type] = p.value;
  }
  return out;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// Month names are fixed three-letter forms; Intl en-GB yields "Sept", which we do not want.
function dayMonth(d: Date): { day: string; month: string; year: string } {
  const p = parts(d, { day: '2-digit', month: 'numeric', year: 'numeric' });
  return { day: p.day, month: MONTHS[Number(p.month) - 1], year: p.year };
}

/** 01 Nov 2026 */
export function formatDate(v: Input): string {
  const d = toDate(v);
  if (!d) return EMPTY;
  const p = dayMonth(d);
  return `${p.day} ${p.month} ${p.year}`;
}

/** 15:12 IST */
export function formatTime(v: Input): string {
  const d = toDate(v);
  if (!d) return EMPTY;
  const p = parts(d, { hour: '2-digit', minute: '2-digit', hour12: false });
  return `${p.hour}:${p.minute} IST`;
}

/** 01 Nov 2026, 15:12 IST */
export function formatDateTime(v: Input): string {
  const d = toDate(v);
  if (!d) return EMPTY;
  return `${formatDate(d)}, ${formatTime(d)}`;
}

/** 01 Nov, 15:12 IST (same-year compact form) */
export function formatDateTimeShort(v: Input): string {
  const d = toDate(v);
  if (!d) return EMPTY;
  const p = dayMonth(d);
  return `${p.day} ${p.month}, ${formatTime(d)}`;
}

/** 1,23,456 */
export function formatNumber(n: number | null | undefined, maxFractionDigits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return EMPTY;
  return n.toLocaleString('en-IN', { maximumFractionDigits: maxFractionDigits });
}

/** Rupee amount: Rs 85,000 shown as the rupee sign + Indian grouping. */
export function formatRupee(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return EMPTY;
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}

/** Whole days between now and a date: positive = in the past. */
export function daysSince(v: Input, now: Date = new Date()): number | null {
  const d = toDate(v);
  if (!d) return null;
  return Math.floor((now.getTime() - d.getTime()) / 86_400_000);
}

/** "today", "yesterday", "11 days ago", "in 3 days" */
export function relativeDays(v: Input, now: Date = new Date()): string {
  const n = daysSince(v, now);
  if (n === null) return EMPTY;
  if (n === 0) return 'today';
  if (n === 1) return 'yesterday';
  if (n === -1) return 'tomorrow';
  return n > 0 ? `${n} days ago` : `in ${-n} days`;
}

/** "11d" / "3h" / "12m" style age for dense tables. */
export function ageShort(v: Input, now: Date = new Date()): string {
  const d = toDate(v);
  if (!d) return EMPTY;
  const ms = Math.max(0, now.getTime() - d.getTime());
  const mins = Math.floor(ms / 60_000);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 48) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

/** a3f9c21e... -> a3f9…c21e */
export function shortHash(hash: string | null | undefined, head = 4, tail = 4): string {
  if (!hash) return EMPTY;
  if (hash.length <= head + tail) return hash;
  return `${hash.slice(0, head)}…${hash.slice(-tail)}`;
}

/** 0.8123 -> "0.81" (scores are shown to two decimals, never as a percentage claim). */
export function formatScore(s: number | null | undefined, decimals = 2): string {
  if (s === null || s === undefined || Number.isNaN(s)) return EMPTY;
  return s.toFixed(decimals);
}

export function formatPercent(num: number, den: number): string {
  if (!den) return EMPTY;
  return `${((num / den) * 100).toFixed(0)}%`;
}
