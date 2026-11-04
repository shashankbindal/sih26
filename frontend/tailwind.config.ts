import type { Config } from 'tailwindcss';

// Theme maps ONLY to CSS variables in src/styles/tokens.css.
// Colors, radii, shadows and font sizes are replaced (not extended) so default
// palette classes (slate-500, blue-600, rounded-xl, shadow-lg ...) do not exist.
const v = (name: string) => `var(--${name})`;

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      ink: { 900: v('ink-900'), 700: v('ink-700'), 500: v('ink-500'), 300: v('ink-300') },
      line: { DEFAULT: v('line'), soft: v('line-soft') },
      'on-dark': v('on-dark-muted'),
      paper: v('paper'),
      surface: v('surface'),
      navy: { DEFAULT: v('navy'), 50: v('navy-50') },
      ok: { DEFAULT: v('ok'), bg: v('ok-bg') },
      amber: { DEFAULT: v('amber'), bg: v('amber-bg') },
      red: { DEFAULT: v('red'), bg: v('red-bg') },
      info: { DEFAULT: v('info'), bg: v('info-bg') },
      neutral: { DEFAULT: v('neutral'), bg: v('neutral-bg') },
      saffron: { DEFAULT: v('saffron'), bg: v('saffron-bg') },
      bureau: {
        pgrc: v('bureau-pgrc'),
        rb: v('bureau-rb'),
        approval: v('bureau-approval'),
        vigilance: v('bureau-vigilance'),
        ro: v('bureau-ro'),
        admin: v('bureau-admin'),
      },
    },
    borderRadius: { none: '0', sm: v('radius-sm'), DEFAULT: v('radius'), lg: v('radius-lg') },
    boxShadow: { none: 'none', menu: v('shadow-menu'), focus: v('focus') },
    fontFamily: {
      sans: ['IBM Plex Sans', 'Noto Sans Devanagari', 'system-ui', 'sans-serif'],
      mono: ['IBM Plex Mono', 'ui-monospace', 'Consolas', 'monospace'],
    },
    fontSize: {
      '2xs': ['11px', '1.25'],
      xs: ['12px', '1.45'],
      sm: ['13px', '1.45'],
      base: ['14px', '1.45'],
      md: ['16px', '1.25'],
      xl: ['20px', '1.25'],
      kpi: ['28px', '1.1'],
    },
    extend: {
      spacing: { nav: '232px', topbar: '52px', envbar: '24px', row: '36px', ctl: '32px' },
    },
  },
} satisfies Config;
