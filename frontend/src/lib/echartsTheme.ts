import * as echarts from 'echarts';

// ECharts theme built from tokens.css (the design system section 7). Canvas cannot read
// CSS variables directly, so they are resolved from :root at registration time.
function cssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export const THEME_NAME = 'loksutra';

export function chartPalette(): string[] {
  return [
    cssVar('--chart-1', '#12325e'),
    cssVar('--chart-2', '#3c7ab5'),
    cssVar('--chart-3', '#7fa8cf'),
    cssVar('--chart-4', '#d9822b'),
    cssVar('--chart-5', '#1e6b3a'),
    cssVar('--chart-6', '#8a97a8'),
    cssVar('--chart-7', '#a4262c'),
  ];
}

let registered = false;

/** Idempotent; call before rendering any chart (ReactECharts theme={THEME_NAME}). */
export function registerLoksutraTheme(): string {
  if (registered) return THEME_NAME;
  const ink = cssVar('--ink-900', '#0b1b33');
  const muted = cssVar('--ink-500', '#4a5b73');
  const lineSoft = cssVar('--line-soft', '#e9ecf0');
  const line = cssVar('--line', '#d9dee5');
  const font = cssVar('--font-sans', "'IBM Plex Sans', system-ui, sans-serif");
  const axis = {
    axisLine: { lineStyle: { color: line } },
    axisTick: { show: false },
    axisLabel: { color: muted, fontSize: 12, fontFamily: font },
    splitLine: { lineStyle: { color: lineSoft } },
    nameTextStyle: { color: muted, fontSize: 12, fontFamily: font },
  };
  echarts.registerTheme(THEME_NAME, {
    color: chartPalette(),
    backgroundColor: 'transparent',
    textStyle: { fontFamily: font, fontSize: 12, color: ink },
    title: {
      textStyle: { color: ink, fontSize: 13, fontWeight: 600, fontFamily: font },
      subtextStyle: { color: muted, fontSize: 12, fontFamily: font },
    },
    grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
    categoryAxis: { ...axis, splitLine: { show: false } },
    valueAxis: { ...axis, axisLine: { show: false } },
    timeAxis: axis,
    legend: { textStyle: { color: muted, fontSize: 12, fontFamily: font }, itemWidth: 10, itemHeight: 10, icon: 'rect' },
    tooltip: {
      backgroundColor: cssVar('--surface', '#ffffff'),
      borderColor: line,
      borderWidth: 1,
      textStyle: { color: ink, fontSize: 12, fontFamily: font },
      extraCssText: 'box-shadow:' + cssVar('--shadow-menu', '0 4px 12px rgba(11,27,51,.14)') + ';border-radius:4px;',
    },
    bar: { itemStyle: { borderRadius: 0 }, barMaxWidth: 28 },
    line: { symbol: 'circle', symbolSize: 5, lineStyle: { width: 2 }, smooth: false },
  });
  registered = true;
  return THEME_NAME;
}
