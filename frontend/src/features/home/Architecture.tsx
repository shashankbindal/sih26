import { Section, SectionHeader } from './parts';

const V = (n: string) => `var(--${n})`;

interface Block {
  title: string;
  sub?: string[];
  fill: string;
  stroke: string;
}

const BLOCKS: Block[] = [
  { title: 'Complaint sources', sub: ['Portals, email,', 'regional registers'], fill: 'paper', stroke: 'ink-300' },
  { title: 'The matching step', fill: 'saffron-bg', stroke: 'saffron' },
  { title: 'Database and API', fill: 'navy-50', stroke: 'navy' },
  { title: 'Web app for teams', fill: 'surface', stroke: 'navy' },
];

const DESC =
  'Four steps from left to right. Complaint sources such as the complaint portals, email and regional office registers feed the matching step. The matching step feeds the database and API. The database and API serve the web app used by AICTE teams.';

/** One simple diagram, drawn twice: a row from 1024px up, a column below that so text never drops under 12px. */
function Diagram({ vertical, uid }: { vertical?: boolean; uid: string }) {
  const bw = vertical ? 300 : 200;
  const bh = vertical ? 84 : 110;
  const gap = vertical ? 44 : 66.7;
  const w = vertical ? bw : 4 * bw + 3 * gap;
  const h = vertical ? 4 * bh + 3 * gap : bh;
  const marker = `${uid}-arrow`;
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      role="img"
      aria-labelledby={`${uid}-title ${uid}-desc`}
      className={vertical ? 'mx-auto block h-auto w-full max-w-[320px]' : 'block h-auto w-full'}
      style={{ fontFamily: 'var(--font-sans)' }}
    >
      <title id={`${uid}-title`}>How Lok Sutra is built: sources, matching step, database and API, web app</title>
      <desc id={`${uid}-desc`}>{DESC}</desc>
      <defs>
        <marker id={marker} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto">
          <path d="M0 0L10 5L0 10Z" fill={V('ink-500')} />
        </marker>
      </defs>
      {BLOCKS.map((b, i) => {
        const x = vertical ? 0 : i * (bw + gap);
        const y = vertical ? i * (bh + gap) : 0;
        const mid = x + bw / 2;
        const lines = b.sub ?? [];
        const top = y + bh / 2 - lines.length * 10 + 4;
        return (
          <g key={b.title}>
            <rect x={x} y={y} width={bw} height={bh} rx={4} fill={V(b.fill)} stroke={V(b.stroke)} strokeWidth={1.5} />
            <text x={mid} y={top} textAnchor="middle" fontSize={16} fontWeight={600} fill={V('ink-900')}>
              {b.title}
            </text>
            {lines.map((l, k) => (
              <text key={l} x={mid} y={top + 24 + k * 20} textAnchor="middle" fontSize={14} fill={V('ink-700')}>
                {l}
              </text>
            ))}
            {i < BLOCKS.length - 1 && (
              <path
                d={vertical ? `M${mid} ${y + bh + 4}V${y + bh + gap - 4}` : `M${x + bw + 6} ${bh / 2}H${x + bw + gap - 6}`}
                stroke={V('ink-500')}
                strokeWidth={2}
                fill="none"
                markerEnd={`url(#${marker})`}
              />
            )}
          </g>
        );
      })}
    </svg>
  );
}

export function Architecture() {
  return (
    <Section id="architecture">
      <SectionHeader id="architecture" title="How it is built" hi="संरचना" />
      <div className="hidden lg:block">
        <Diagram uid="arch" />
      </div>
      <div className="lg:hidden">
        <Diagram vertical uid="archm" />
      </div>
    </Section>
  );
}
