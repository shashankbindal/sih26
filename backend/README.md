# Lok Sutra backend

FastAPI service behind the Lok Sutra prototype: case intake, institution matching (CaseLink), relationship detection, Pre-Action Check and clearances, policy clocks, the hash-chained Case Passport, dashboards, reports, import and evaluation. All data is synthetic.

- Stack: Python 3.12+, FastAPI, SQLAlchemy 2 (typed ORM), Alembic, Pydantic v2, psycopg 3, PostgreSQL (`pg_trgm`, `unaccent`, `pgcrypto`, `citext`), RapidFuzz, jellyfish, indic-transliteration, scikit-learn, APScheduler, ReportLab, openpyxl

## Run locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # then edit DATABASE_URL and JWT_SECRET
alembic upgrade head                 # creates extensions, tables, triggers
python -m app.seed.generate --reset  # synthetic data, deterministic (seed 26264)
python -m app.seed.generate --check  # asserts the scripted demo scenarios
uvicorn app.main:app --reload --port 8000
```

The database user needs permission to run `CREATE EXTENSION` for `pg_trgm`, `unaccent`, `pgcrypto` and `citext` (the first migration does it). Open http://localhost:8000/docs for the API.

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL URL; `postgres://` and `postgresql://` are rewritten to the psycopg 3 dialect | local Postgres on port 5432 |
| `JWT_SECRET` | HS256 signing key (set a long random value in production) | development placeholder |
| `JWT_EXPIRE_MINUTES` | Token lifetime | `480` |
| `CORS_ORIGINS` | Comma-separated allowed browser origins, no trailing slash | `http://localhost:5173` |
| `DEMO_MODE` | Enables demo accounts on the login page, the demo reset and the tamper demo | `false` |
| `SCHEDULER_ENABLED` | Hourly clock evaluation and the 02:00 IST relationship sweep | `true` |

## Tests

```bash
createdb loksutra_test                                  # once
export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/loksutra_test
pytest                       # in-process suite: engine, passport, privacy, clocks, workflows, reporting
ruff check .

# black-box HTTP tests against a running, freshly seeded server
python -m app.seed.generate --reset && uvicorn app.main:app --port 8000 &
QA_LIVE=1 pytest tests/api
```

Each pytest session rebuilds the test database through Alembic, so use a database you do not mind dropping.

## Layout

```
app/
  main.py            app factory, CORS, request-id middleware, error envelope, routers, scheduler lifecycle
  config.py db.py deps.py errors.py scheduler.py
  api/               routers: auth, institutions, cases, links, review, preaction, clearances, passport,
                     notifications, dashboard, reports, imports, admin, evaluation, risk, search, health
  services/          business logic (routers only validate and call services)
    caselink/        institution resolution, relationship detection, sweep, explanations
    normalise.py classify.py   transliteration, Hinglish text map, PII masking, category suggestion
    passport.py privacy.py clocks.py preaction.py links.py intake.py importer.py reports.py evaluation.py ...
  models/ schemas/   SQLAlchemy models and Pydantic schemas
  seed/              deterministic synthetic data generator, scenarios and checks
alembic/             migrations (extensions, enums, indexes, append-only trigger)
tests/               engine, workflows, reporting, privacy, clocks, passport, and tests/api (black-box)
```

## How the main pieces work

- **Institution resolution.** Exact Permanent ID, then a remembered alias, then a probabilistic score in the Fellegi-Sunter style (log-weights for name similarity, district, pincode and a distinctive-token match). Scores of 0.92 and above are auto-suggested, 0.75 to 0.92 go to the review queue, and lower scores stay unresolved. Every candidate carries plain-text reasons. Devanagari is transliterated to Latin with schwa deletion and a Hindi institution-word dictionary; Hinglish is mapped to canonical terms.
- **Relationship detection.** For cases at the same institution: TF-IDF character n-gram similarity, category family, time and party features, plus a conflict matrix of pending actions. Each pair is classified as duplicate, related, conflicting or unrelated. The engine is advisory: it never merges cases, and every officer decision is versioned and reversible.
- **Policy clocks.** Three separate timers: the CPGRAMS 21-day redress target, the CSS 72-hour first reply, and the institution's 7-day refund duty. States are on track, amber, breached, paused and met, and are computed on read as well as by the hourly job.
- **Case Passport.** Append-only event log per case. Each entry stores `SHA-256(prev_hash + canonical payload)`; a database trigger rejects updates and deletes, and `verify` recomputes the chain and returns the first broken sequence number.
- **Access control and privacy.** Eight roles enforced with `require_roles`. Complainant identity is masked in API responses for non-owning bureaus and for senior management; a reveal needs a written reason and is logged.

## Developer notes

- Services never commit (they `flush`); routers call `db.commit()` after writes. Session dependency: `from app.deps import DbSession`.
- Errors: `raise ApiError(status, "CODE", "message", {details})`; the envelope `{"error": {"code", "message", "details"}}` is added automatically.
- Auth: `from app.deps import CurrentUser, get_current_user, require_roles`; `Depends(require_roles(Role.ADMIN, Role.BUREAU_HEAD))`.
- Passport: `passport.append_entry(session, event=..., case_id=..., actor=user, payload={...})`; `passport.verify_chain(session, case_id=...)`. Institution-action chains use `chain_key=f"action:{action.id}"`.
- Privacy: return `case_views.build_case_detail(session, case, user)` from any endpoint that emits a case; it applies `privacy.mask_case`. Never log complainant fields.
- Clocks: `clocks.start_clocks_for_case(...)`, then `clocks.sync_clocks_for_case(...)` after status or pending-step changes. `CaseClock.due_at` stores the base due time; pauses are added on read.
- Thresholds, clock durations and clause labels live in the `policy_config` table and are editable through `/api/v1/admin/config/{key}`.
