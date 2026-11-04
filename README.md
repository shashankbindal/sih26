# Lok Sutra

**One institution. One truth.** An institution-centric complaint coordination layer for AICTE bureaus and Regional Offices.

Smart India Hackathon 2026 · Problem statement **SIH26264**: *Integrated Dashboard for Monitoring and Tracking Institution-Related Complaint Cases Across AICTE Bureaus/Cells* · Team **Neurals Knight**

## Prototype

| | URL |
|---|---|
| Web app | https://sih.shashankbindal.me |
| Overview page (no sign-in) | https://sih.shashankbindal.me/home |

The backend runs on a free hosting tier, so the first request after a period of inactivity can take up to a minute while it wakes up. The app shows a "Connecting to the server" banner during that time.

All data in the prototype is **synthetic**, modelled on the AICTE Permanent ID format. No real complaints or institutions are used.

### Demo accounts

Sign in from the login page with the quick sign-in buttons, or type an email below. The password for every demo account is `Demo@2026`.

| Email | Role | Good for seeing |
|---|---|---|
| `pgrc.officer@demo.loksutra.in` | PGRC officer | Complaint intake, matching, related cases, clearances |
| `approval.officer@demo.loksutra.in` | Approval officer | Pre-Action Check before a security-deposit release |
| `rb.officer@demo.loksutra.in` | RB officer | Complainant details hidden for another bureau's case |
| `vigilance.officer@demo.loksutra.in` | Vigilance officer | Responding to clearance requests |
| `ro.kanpur@demo.loksutra.in` | Regional Office officer (Kanpur) | Region-scoped case register |
| `pgrc.head@demo.loksutra.in`, `rb.head@demo.loksutra.in` | Bureau heads | Priority-review alerts |
| `mgmt@demo.loksutra.in` | Senior management | Oversight dashboard, reports; never sees complainant identity |
| `admin@demo.loksutra.in` | Administrator | Thresholds, policy clocks, import, demo tools |

## The problem

Complaints about one AICTE-approved institution reach AICTE through several doors (CSS, CPGRAMS, e-mail, Regional Office registers, bureau files) and are handled separately by PGRC, the Regulation Bureau (RB), the Approval Bureau, Vigilance and the Regional Offices. The same college appears under different reference numbers and spellings, so:

- one bureau issues a show-cause notice while another negotiates a refund with the same college;
- nobody can quickly say who is handling an institution;
- three different deadlines (CPGRAMS 21 days, CSS 72 hours, the institution's 7-day refund duty) are tracked separately or not at all;
- management has no institution-wise or region-wise view;
- institution-level actions, such as releasing a security deposit, are taken without seeing the other open matters.

Lok Sutra sits behind CSS and CPGRAMS. It does not replace them.

## What it does

- **Institution resolution.** Matches a complaint to the right institution by Permanent ID, a remembered alias, or a probabilistic score on name, district and pincode. It reads Hindi (Devanagari), Hinglish and English, shows its reasons in plain words, and sends uncertain matches to a review queue. Confirmed matches become aliases.
- **Relationship detection.** Compares open cases at the same institution and classifies each pair as duplicate, related, conflicting or unrelated. Unrelated pairs raise no alert. Nothing is merged automatically; officers confirm, reject or defer with a reason, and every decision is versioned and reversible.
- **Institution 360.** One page per institution with every case across bureaus, shown in team lanes with markers for linked cases, a timeline and an action history.
- **Pre-Action Check and clearances.** Before an institution-level action (issue NOC, security-deposit release, show-cause, closure approval, extension of approval, inspection order) it lists every open matter, ranked by relevance, and the clearance chain (PGRC, then Vigilance, then Approval NOC). The check is advisory: the officer acknowledges and decides, and it is logged.
- **Policy clocks.** Three separate timers with on-track, amber, breached, paused and met states, alerts and escalation on breach.
- **Oversight dashboard.** "What needs attention" cards, filters, status by bureau, deadline clocks, ageing, trends, a regional map, institutions with the most open matters, and coordination alerts. PDF and CSV pendency reports.
- **Case Passport.** An append-only, hash-chained audit trail for every case. A verify action recomputes the chain and names the first broken entry.
- **Role-based access control (RBAC) and privacy.** Eight roles. Complainant identity is masked for other bureaus and for senior management; a reveal requires a written reason and is logged.
- **Intake.** Manual entry, paste an e-mail, or CSV and Excel import with column mapping.
- **Evaluation.** Measures the matcher on a held-out synthetic set and shows sample sizes and known failure cases.
- **Administration.** Matching thresholds, policy clocks, clause labels and lead-bureau rules are stored as configuration and editable without a code change.

### Measured on the synthetic held-out set

| Measure | Result | Sample |
|---|---|---|
| Right institution among the auto-suggested and review candidates | 98.8% | 169 complaints |
| Alert precision (alerts that were truly related, duplicate or conflicting) | 83.3% | 12 alerts (small sample) |

These come from the Evaluation page (`GET /api/v1/evaluation/run`), which re-runs the matcher on data the thresholds were not tuned on. They describe synthetic data and are not a claim about real AICTE complaints.

## Architecture

```mermaid
flowchart LR
    subgraph Sources
      A[CSS] & B[CPGRAMS] & C[E-mail] & D[RO registers] & E[Bureau files]
    end
    Sources --> H[Intake: manual, paste e-mail, CSV / XLSX]
    H --> N[Normalise and transliterate]
    N --> R[CaseLink: institution resolution]
    R --> L[CaseLink: relationship detection]
    L --> DB[(PostgreSQL)]
    DB --> API[FastAPI]
    API --> UI[React web app]
    API --> P[Case Passport hash chain]
    API --> K[Policy clocks and scheduler]
```

- **Frontend** (`frontend/`): React 18, Vite, TypeScript (strict), React Router, TanStack Query, Tailwind mapped to CSS variables, ECharts, Leaflet, Lucide icons, IBM Plex Sans and Mono with Noto Sans Devanagari. API types are generated from the backend's OpenAPI document.
- **Backend** (`backend/`): Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, psycopg 3, APScheduler, RapidFuzz, jellyfish, indic-transliteration, scikit-learn, ReportLab, openpyxl.
- **Database:** PostgreSQL with the `pg_trgm`, `unaccent`, `pgcrypto` and `citext` extensions.
- **Hosting:** Vercel (frontend), Render (backend), Neon (PostgreSQL).

The matcher, text-similarity and transliteration components are small, self-contained modules, so heavier production components (for example multilingual embeddings or a dedicated record-linkage library) can replace them behind the same functions. The backend runs inside a 512 MB free instance (measured peak about 270 MB).

## Repository layout

```
backend/    FastAPI service, CaseLink engine, seed data generator, tests      (see backend/README.md)
frontend/   React web app, end-to-end tests                                    (see frontend/README.md)
```

## Run it locally

Prerequisites: Python 3.12+, Node.js 20+, PostgreSQL 16+.

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # edit DATABASE_URL and JWT_SECRET
alembic upgrade head
python -m app.seed.generate --reset                    # 200 institutions, 600 cases, 12 users
python -m app.seed.generate --check                    # asserts the scripted demo scenarios
uvicorn app.main:app --reload --port 8000
```

**Frontend**

```bash
cd frontend
npm install
cp .env.example .env.local                             # VITE_API_BASE_URL=http://localhost:8000/api/v1
npm run dev                                            # http://127.0.0.1:5173
```

Then open the app, choose a demo account on the login page, and sign in.

### Environment variables

| Where | Variable | Meaning |
|---|---|---|
| backend | `DATABASE_URL` | PostgreSQL connection string |
| backend | `JWT_SECRET` | Token signing key |
| backend | `CORS_ORIGINS` | Allowed web origins, comma-separated, no trailing slash |
| backend | `DEMO_MODE` | `true` enables the demo accounts, demo reset and tamper demo |
| frontend | `VITE_API_BASE_URL` | Backend URL ending in `/api/v1` |
| frontend | `VITE_DEMO_MODE` | `true` shows the demo account shortcuts on the login page |

## Tests

```bash
# backend: engine, privacy, clocks, passport, workflows, reporting (rebuilds a test database)
cd backend && export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/loksutra_test && pytest

# backend: black-box API tests against a running, freshly seeded server
QA_LIVE=1 pytest tests/api

# frontend
cd frontend && npm run typecheck && npm run lint && npm run build
npm run e2e        # Playwright; needs the backend and the dev server running, and a fresh seed
```

## Deployment

- **Backend (Render).** Build `pip install -r requirements.txt`; start `alembic upgrade head && python -m app.seed.generate --if-empty && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`; health check `/api/v1/health`. Set `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS` (the frontend origin) and `DEMO_MODE`.
- **Database (Neon).** Any PostgreSQL 16+ that allows the four extensions works.
- **Frontend (Vercel).** Root directory `frontend`, build `npm run build`, output `dist`. Set `VITE_API_BASE_URL` and `VITE_DEMO_MODE`. `vercel.json` rewrites all paths to `index.html`.

## Limits of the prototype

- Data is synthetic. Matching thresholds are starting values tuned on synthetic data and need re-tuning on real exports.
- Live connectors to CSS, CPGRAMS and e-Office are not included; CSV and Excel import covers the same workflow today.
- Notifications are in-app only (no e-mail or SMS), and sign-in uses JWT with the same role model rather than single sign-on.
- The clause label for the deposit-release clearance step is configurable and should be confirmed against the final handbook before any real use.

## Team

Team Neurals Knight · Smart India Hackathon 2026 · SIH26264
