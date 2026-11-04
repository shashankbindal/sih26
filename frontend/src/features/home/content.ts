// Static copy for the public Home page. Nothing here comes from the API.
// Plain words first; an acronym is shown in brackets only where it first appears on the page.

export const PROBLEMS = [
  {
    lead: 'Parallel or conflicting actions.',
    line: 'The rules and regulation team (RB) issues a show-cause notice while the complaint cell is negotiating a refund with the same college.',
  },
  { lead: 'Nobody can say who is handling it.', line: 'One college appears under different names and reference numbers.' },
  { lead: 'Deadlines are missed.', line: 'Three different clocks run on one case, and nobody tracks them together.' },
];

export const FLOW = [
  {
    title: 'Complaint arrives',
    line: 'From AICTE’s complaint portal, the government’s public grievance portal, email or a register, in English or Hindi.',
    link: false,
  },
  {
    title: 'Right college found',
    line: 'The matching step reads the Hindi name in English letters and compares name, district and pincode. The officer confirms.',
    link: false,
  },
  { title: 'Related cases linked', line: 'Other teams working on the same college are shown and told. It advises; the officer decides.', link: true },
  {
    title: 'Check before acting',
    line: 'Pre-Action Check: a check before anyone acts on a college, such as a permission letter (NOC). Each case keeps a history nobody can quietly change.',
    link: false,
  },
];

export interface Chip {
  name: string;
  /** Saffron only for the two parts that coordinate between teams. */
  coordination?: boolean;
}

export interface Quadrant {
  key: string;
  caption: string;
  sub: string;
  tone: 'start' | 'plan' | 'later';
  chips: Chip[];
}

// Rows: impact (high first). Columns: feasibility (harder first). Qualitative team judgement only.
export const QUADRANTS: Quadrant[] = [
  {
    key: 'hard-high',
    caption: 'Plan next',
    sub: 'High impact, harder',
    tone: 'plan',
    chips: [{ name: 'Matching step (CaseLink)', coordination: true }, { name: 'Pre-Action Check', coordination: true }, { name: 'Policy clocks' }],
  },
  { key: 'easy-high', caption: 'Start here', sub: 'High impact, easier', tone: 'start', chips: [{ name: 'Institution 360' }] },
  { key: 'hard-low', caption: 'Later', sub: 'Lower impact, harder', tone: 'later', chips: [] },
  {
    key: 'easy-low',
    caption: 'Plan next',
    sub: 'Lower impact, easier',
    tone: 'plan',
    chips: [{ name: 'Oversight dashboard' }, { name: 'Case history (Case Passport)' }],
  },
];

export const WORDS: ReadonlyArray<readonly [string, string]> = [
  ['PGRC', 'the complaint cell'],
  ['RB', 'the rules and regulation team'],
  ['ATR', 'the college’s reply report'],
  ['NOC', 'a permission letter'],
  ['Institution resolution', 'finds the right college'],
  ['Transliteration', 'reads the Hindi name in English letters'],
  ['CaseLink / matching engine', 'the matching step'],
  ['Pre-Action Check', 'a check before anyone acts on a college'],
  ['Clearance', 'a go-ahead from another team'],
  ['Case Passport / hash chain', 'a history of each case that nobody can quietly change'],
  ['Advisory, not a veto', 'it advises; the officer decides'],
  ['CSS', 'AICTE’s complaint portal'],
  ['CPGRAMS', 'the government’s public grievance portal'],
];
