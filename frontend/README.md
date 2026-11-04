# Lok Sutra · frontend

Institution-level complaint coordination for AICTE bureaus and Regional Offices (SIH 2026, SIH26264). React 18 + Vite + TypeScript (strict), React Router, TanStack Query, Tailwind mapped to CSS variables in `src/styles/tokens.css`, ECharts, Leaflet, Lucide icons. Deploys to Vercel.

All data shown is synthetic and modelled on the AICTE Permanent ID format.

## Run locally

```
npm install
cp .env.example .env.local        # VITE_API_BASE_URL=http://localhost:8000/api/v1
npm run dev                        # http://localhost:5173
```

The API lives in `../backend` (see the project README for how to run it). Demo accounts are listed on the login page when `VITE_DEMO_MODE=true`; the password for all of them is `Demo@2026`.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Vite dev server |
| `npm run typecheck` | `tsc` in strict mode |
| `npm run lint` | ESLint |
| `npm run build` | Typecheck and production build to `dist/` |
| `npm run e2e` | Playwright end-to-end tests (needs the backend and dev server running, and a fresh seed) |
| `npm run gen:api` | Regenerate `src/api/schema.d.ts` from the backend OpenAPI document |

## Layout

```
src/
  api/          fetch client (auth, retry, cold-start warm-up), query hooks, generated schema
  auth/         auth context and route guards
  components/   ui/ primitives, domain/ components (RelationBadge, ClockPill, ScoreMeter, ...)
  features/     one folder per area: cases, institutions, intake, review, preaction,
                clearances, coordination, passport, dashboard, reports, import, admin, evaluation
  shell/        left nav, top bar, environment bar, global search, notifications
  styles/       tokens.css (design tokens) and index.css
  lib/          formatting (IST dates, en-IN numbers), constants, ECharts theme
```

## Design rules

Government operations software, not a SaaS template: no gradients, no glassmorphism, no emoji, small radii, 1px borders instead of shadows, IBM Plex Sans / Mono with Noto Sans Devanagari, saffron reserved for coordination UI. Thresholds, clock durations and clause labels come from the API, never from literals in the UI.

## Deploy

Vercel, root directory `frontend`, build `npm run build`, output `dist`. Set `VITE_API_BASE_URL` to the backend's `/api/v1` URL. `vercel.json` rewrites all paths to `index.html` for client-side routing.
