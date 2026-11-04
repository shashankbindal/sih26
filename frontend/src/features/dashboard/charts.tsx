import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { useNavigate } from 'react-router-dom';
import { registerLoksutraTheme } from '@/lib/echartsTheme';
import { BUREAUS, BUREAU_LABEL, CATEGORY_LABEL, OPEN_STATUSES, type Bureau, type CaseCategory, type CaseStatus } from '@/lib/constants';
import { formatNumber } from '@/lib/format';
import type { AgeingRow, BureauRow, CategoryRow, TrendRow } from './api';
import { casesLink, type DashFilters } from './filters';
import { PLAIN_STATUS } from './plain';

function tok(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

const FONT = 13;

function Chart({ option, height, onClick }: { option: object; height: number; onClick?: (p: { seriesName?: string; name?: string }) => void }) {
  const theme = registerLoksutraTheme();
  // Motion stays at or under 150 ms (the design system section 1).
  const motion = { animationDuration: 150, animationDurationUpdate: 150 };
  return <ReactECharts option={{ ...motion, ...option }} theme={theme} style={{ height, width: '100%' }} opts={{ renderer: 'svg' }} notMerge onEvents={onClick ? { click: onClick } : undefined} />;
}

/* ------------------------------------------------------------------ */
/* Open cases by bureau: bureau colour on the axis, status as tints    */
/* ------------------------------------------------------------------ */

// Series order validated for adjacent-pair separation (dataviz validator, colour-blind and normal vision).
// Saffron is reserved for coordination UI so it is not used for statuses.
const STATUS_ORDER: CaseStatus[] = ['RECEIVED', 'UNDER_PROCESS', 'AWAITING_ATR', 'REOPENED', 'AWAITING_COMPLAINANT', 'ESCALATED'];
const STATUS_COLOR: Record<string, { fill: string; text: string }> = {
  RECEIVED: { fill: '--chart-3', text: '--ink-900' },
  UNDER_PROCESS: { fill: '--chart-2', text: '--surface' },
  AWAITING_ATR: { fill: '--chart-1', text: '--surface' },
  REOPENED: { fill: '--amber', text: '--surface' },
  AWAITING_COMPLAINANT: { fill: '--chart-6', text: '--ink-900' },
  ESCALATED: { fill: '--chart-7', text: '--surface' },
};
const FALLBACK: Record<string, string> = {
  '--chart-1': '#12325e',
  '--chart-2': '#3c7ab5',
  '--chart-3': '#7fa8cf',
  '--chart-6': '#8a97a8',
  '--chart-7': '#a4262c',
  '--amber': '#9a5b00',
  '--ink-900': '#0b1b33',
  '--surface': '#ffffff',
};
const sc = (v: string) => tok(v, FALLBACK[v] ?? '#000000');

export function bureauName(b: string): string {
  return BUREAU_LABEL[b as Bureau] ?? b;
}

export function bureauTotals(rows: BureauRow[]): { bureau: string; total: number; by: Record<string, number> }[] {
  return rows
    .map((r) => {
      const by: Record<string, number> = {};
      let total = 0;
      for (const s of OPEN_STATUSES) {
        const n = Number(r[s] ?? 0);
        by[s] = n;
        total += n;
      }
      return { bureau: r.bureau, total, by };
    })
    .sort((a, b) => b.total - a.total);
}

export function BureauStatusChart({ rows, filters, height }: { rows: BureauRow[]; filters: DashFilters; height: number }) {
  const navigate = useNavigate();
  const data = useMemo(() => bureauTotals(rows), [rows]);
  const option = useMemo(() => {
    const ordered = [...data].reverse(); // category axis draws bottom-up; biggest bureau on top
    const maxTotal = Math.max(1, ...data.map((d) => d.total));
    const minLabel = Math.max(1, Math.ceil(maxTotal * 0.05)); // hide numbers on segments too narrow to hold one
    const used = STATUS_ORDER.filter((s) => data.some((d) => d.by[s] > 0));
    // Fixed bureau colour as a small square in front of each bureau name.
    const rich: Record<string, object> = {};
    for (const b of BUREAUS) rich[`b_${b}`] = { color: tok(`--bureau-${b.toLowerCase()}`, '#12325e'), fontSize: 15, padding: [0, 4, 0, 0] };
    return {
      textStyle: { fontSize: FONT },
      grid: { left: 8, right: 36, top: 70, bottom: 30, containLabel: true },
      legend: { top: 0, left: 0, data: used.map((s) => PLAIN_STATUS[s]), itemGap: 14, itemWidth: 12, itemHeight: 12, textStyle: { fontSize: 12, color: tok('--ink-700', '#22344f') } },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: { seriesName: string; value: number; axisValueLabel: string }[]) => {
          const lines = params.filter((p) => p.value > 0).map((p) => `${p.seriesName}: <b>${formatNumber(p.value)}</b>`);
          const total = params.reduce((a, p) => a + p.value, 0);
          return `<b>${(params[0]?.axisValueLabel ?? '').replace(/^.*\}/, '')}</b>: ${formatNumber(total)} open<br/>${lines.join('<br/>')}`;
        },
      },
      xAxis: { type: 'value', name: 'Open cases', nameLocation: 'middle', nameGap: 24, minInterval: 1, axisLabel: { fontSize: 12 }, nameTextStyle: { fontSize: 12 } },
      yAxis: {
        type: 'category',
        data: ordered.map((d) => bureauName(d.bureau)),
        axisLabel: {
          fontSize: 14,
          fontWeight: 600,
          color: tok('--ink-900', '#0b1b33'),
          rich,
          formatter: (name: string) => {
            const b = ordered.find((d) => bureauName(d.bureau) === name)?.bureau ?? '';
            return `{b_${b}|■}${name}`;
          },
        },
      },
      series: used.map((s) => ({
        name: PLAIN_STATUS[s],
        type: 'bar',
        stack: 'open',
        barMaxWidth: 36,
        itemStyle: { color: sc(STATUS_COLOR[s].fill), borderColor: tok('--surface', '#ffffff'), borderWidth: 1 },
        label: { show: true, color: sc(STATUS_COLOR[s].text), fontSize: 13, fontWeight: 600, formatter: (p: { value: number }) => (p.value >= minLabel ? String(p.value) : '') },
        data: ordered.map((d) => d.by[s]),
      })),
    };
  }, [data]);
  const statusByLabel = Object.fromEntries(Object.entries(PLAIN_STATUS).map(([k, v]) => [v, k]));
  const bureauByLabel = Object.fromEntries(data.map((d) => [bureauName(d.bureau), d.bureau]));
  return (
    <Chart
      option={option}
      height={height}
      onClick={(p) => {
        const st = p.seriesName ? statusByLabel[p.seriesName] : undefined;
        const bu = p.name ? bureauByLabel[p.name.replace(/^.*\}/, '')] : undefined;
        if (st && bu) navigate(casesLink(filters, { bureau: bu, status: st }));
      }}
    />
  );
}

/* ------------------------------------------------------------------ */
/* How old are open cases: four discrete severity steps                */
/* ------------------------------------------------------------------ */

export function ageingLabel(bucket: string): string {
  if (/\+$/.test(bucket)) return `Over ${bucket.replace('+', '')} days`;
  return `${bucket.replace('-', '–')} days`;
}

// Green to red in four discrete steps (no gradient). The last step is a darker red for the longest waits.
const AGEING_STEPS = [
  { name: '--ok', fallback: '#1e6b3a' },
  { name: '--amber', fallback: '#9a5b00' },
  { name: '--red', fallback: '#a4262c' },
  { name: '--ageing-oldest', fallback: '#5c1418' },
];

export function AgeingChart({ rows, height }: { rows: AgeingRow[]; height: number }) {
  const option = useMemo(
    () => ({
      textStyle: { fontSize: FONT },
      grid: { left: 8, right: 16, top: 48, bottom: 52, containLabel: true },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (p: { axisValueLabel: string; value: number }[]) => `Received ${p[0].axisValueLabel} ago<br/>Open cases: <b>${formatNumber(p[0].value)}</b>`,
      },
      xAxis: { type: 'category', name: 'Time since received', nameLocation: 'middle', nameGap: 34, nameTextStyle: { fontSize: 12 }, data: rows.map((r) => ageingLabel(r.bucket)), axisLabel: { fontSize: 13, interval: 0 } },
      yAxis: { type: 'value', name: 'Open cases', nameLocation: 'end', nameTextStyle: { align: 'left', fontSize: 12 }, minInterval: 1, axisLabel: { fontSize: 12 } },
      series: [
        {
          name: 'Open cases',
          type: 'bar',
          barMaxWidth: 70,
          label: { show: true, position: 'top', color: tok('--ink-900', '#0b1b33'), fontSize: 14, fontWeight: 600 },
          data: rows.map((r, i) => {
            const s = AGEING_STEPS[Math.min(i, AGEING_STEPS.length - 1)];
            return { value: r.count, itemStyle: { color: tok(s.name, s.fallback) } };
          }),
        },
      ],
    }),
    [rows],
  );
  return <Chart option={option} height={height} />;
}

/* ------------------------------------------------------------------ */
/* Received vs closed, monthly (two lines, direct end labels)          */
/* ------------------------------------------------------------------ */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function periodLabel(p: string): string {
  const m = /^(\d{4})-(\d{2})/.exec(p);
  if (!m) return p;
  return `${MONTHS[Number(m[2]) - 1]} ${m[1].slice(2)}`;
}

export function TrendChart({ rows, height }: { rows: TrendRow[]; height: number }) {
  const option = useMemo(() => {
    const ink = tok('--ink-900', '#0b1b33');
    const line = (name: string, key: 'received' | 'disposed', color: string, symbol: string) => ({
      name,
      type: 'line',
      symbol,
      symbolSize: 9,
      color,
      itemStyle: { color, borderColor: tok('--surface', '#ffffff'), borderWidth: 1 },
      lineStyle: { width: 3, color },
      endLabel: { show: true, formatter: (p: { value: number }) => `${name} ${formatNumber(p.value)}`, color: ink, fontSize: 13, fontWeight: 600 },
      labelLayout: { moveOverlap: 'shiftY' },
      emphasis: { focus: 'series' },
      data: rows.map((r) => r[key]),
    });
    return {
      textStyle: { fontSize: FONT },
      grid: { left: 8, right: 120, top: 34, bottom: 34, containLabel: true },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', name: 'Month', nameLocation: 'middle', nameGap: 26, nameTextStyle: { fontSize: 12 }, boundaryGap: false, data: rows.map((r) => periodLabel(r.period)), axisLabel: { fontSize: 12 } },
      yAxis: { type: 'value', name: 'Cases per month', nameLocation: 'end', nameTextStyle: { align: 'left', fontSize: 12 }, minInterval: 1, axisLabel: { fontSize: 12 } },
      series: [line('Received', 'received', tok('--chart-2', '#3c7ab5'), 'circle'), line('Closed', 'disposed', tok('--ok', '#1e6b3a'), 'rect')],
    };
  }, [rows]);
  return <Chart option={option} height={height} />;
}

/* ------------------------------------------------------------------ */
/* Open cases by category (horizontal bars)                            */
/* ------------------------------------------------------------------ */

export function categoryName(c: string): string {
  return CATEGORY_LABEL[c as CaseCategory] ?? c;
}

export function CategoryChart({ rows, filters, height }: { rows: CategoryRow[]; filters: DashFilters; height: number }) {
  const navigate = useNavigate();
  const sorted = useMemo(() => [...rows].filter((r) => r.open > 0).sort((a, b) => a.open - b.open), [rows]); // ascending: biggest ends on top
  const option = useMemo(
    () => ({
      textStyle: { fontSize: FONT },
      grid: { left: 8, right: 40, top: 30, bottom: 30, containLabel: true },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (p: { axisValueLabel: string; dataIndex: number }[]) => {
          const r = sorted[p[0].dataIndex];
          return `<b>${p[0].axisValueLabel}</b><br/>Open: <b>${formatNumber(r.open)}</b><br/>Closed: ${formatNumber(r.disposed)}`;
        },
      },
      xAxis: { type: 'value', name: 'Open cases', nameLocation: 'middle', nameGap: 24, nameTextStyle: { fontSize: 12 }, minInterval: 1, axisLabel: { fontSize: 12 } },
      yAxis: { type: 'category', data: sorted.map((r) => categoryName(r.category)), axisLabel: { fontSize: 13, color: tok('--ink-900', '#0b1b33') } },
      series: [
        {
          name: 'Open cases',
          type: 'bar',
          barMaxWidth: 20,
          itemStyle: { color: tok('--chart-2', '#3c7ab5') },
          label: { show: true, position: 'right', color: tok('--ink-900', '#0b1b33'), fontSize: 13, fontWeight: 600 },
          data: sorted.map((r) => r.open),
        },
      ],
    }),
    [sorted],
  );
  return (
    <Chart
      option={option}
      height={height}
      onClick={(p) => {
        const hit = sorted.find((r) => categoryName(r.category) === p.name);
        if (hit) navigate(casesLink(filters, { category: hit.category, status: OPEN_STATUSES }));
      }}
    />
  );
}
