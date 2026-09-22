# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Current continuation point:** read
[docs/CLAUDE_HANDOFF.md](docs/CLAUDE_HANDOFF.md) before changing code. It records the
implemented baseline, local-data state, next Meta Marketing API task, safe work that can
start without credentials, and the exact handoff prompt.

## What this is

Thaazhai operations + analytics: an internal admin app for raw-order processing,
customers, orders and analytics. Render hosts three services from this one repo:
Next.js (`apps/web`), FastAPI (`apps/api`), and a Python worker
(`workers/order_processor`). Supabase PostgreSQL is the source of truth **and**
the durable job queue — there is no Redis, broker, Kubernetes, or AI layer.

Read [README.md](README.md) and `docs/` before making non-trivial changes — this
project has a lot of load-bearing decisions documented there. In particular:
- [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) — phase boundaries, what's out of scope for V1.
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — migration-by-migration schema rationale.
- [docs/PROCESSING_FLOW.md](docs/PROCESSING_FLOW.md) — how a single order is normalized and saved.
- [docs/PROCESSING_JOBS.md](docs/PROCESSING_JOBS.md) — how the job queue and worker operate.
- [docs/ENVIRONMENTS.md](docs/ENVIRONMENTS.md) — how APP_ENV picks which env file loads.
- [docs/VALIDATION.md](docs/VALIDATION.md) — what has actually been verified so far, and how.
- [docs/CUSTOMER_SEGMENTATION.md](docs/CUSTOMER_SEGMENTATION.md) - dynamic D2C buckets, tags and sales actions.
- [docs/GROWTH_PLATFORM.md](docs/GROWTH_PLATFORM.md) — planning-only doc for Phases 6-10
  (Meta/Zoho financial truth, Shopify cart funnel, RFM segmentation, WhatsApp retention
  actions, AI prompt layer). Nothing in it is built yet; check it before assuming scope
  for any ads/expenses/WhatsApp/AI-related work.

- [docs/META_MARKETING_INTEGRATION.md](docs/META_MARKETING_INTEGRATION.md) - implementation
  contract for the next read-only Meta Ads metrics job. It is designed, not implemented.
- [docs/CLAUDE_HANDOFF.md](docs/CLAUDE_HANDOFF.md) - current continuation state and
  required order for the next work session.

## Two separate environments — never blur them

| | Local development | Live production |
|---|---|---|
| Database | PostgreSQL in Docker on your machine | Existing Supabase database |
| Backend settings | Root `.env.local` | Render variables / root `.env.production` |
| Selection | Default: `APP_ENV=development` | Explicit: `APP_ENV=production` |

The same application code runs in both; only settings differ. The legacy shared
`.env` is never read. `apps/api/config.py` rejects a non-production `DATABASE_URL`
that doesn't point at `localhost`/`127.0.0.1`/`postgres` — this is intentional, to
stop local runs from accidentally touching Supabase.

The local database contains an explicitly imported snapshot of Supabase
`raw_order_ingestion` for development. It is isolated and does not stay synchronized.
Normal local processing commands must never point at Supabase. Migrations/seeds already exist on Supabase — never blindly
rerun all migration/seed files against it; compare schema and migration history
first. Migration 005 (RLS / access revocation) needs particular care since it
changes what anon/authenticated Supabase roles can see.

## Common commands

All commands below run from the repo root unless noted.

### Local environment (first time)
```powershell
Copy-Item .env.local.example .env.local
Copy-Item apps/web/.env.example apps/web/.env.local
docker compose --env-file .env.local up -d --build
docker compose --env-file .env.local exec api python -m db.migrate --seed
```

### Run the app
```powershell
docker compose --env-file .env.local up -d --build   # postgres + api (+ worker)
cd apps/web && npm ci && npm run dev                  # frontend, separate terminal
```
Web: http://localhost:3000 · API docs: http://localhost:8000/docs ·
DB readiness: http://localhost:8000/health/ready

Python source under `apps/api` and `db` is bind-mounted into the API container,
so edits reload automatically. **Restart the API after changing env values**:
```powershell
docker compose --env-file .env.local up -d --force-recreate api
```
Restart the worker after worker-code changes (no autoreload):
```powershell
docker compose --env-file .env.local restart worker
```

### Tests, lint, typecheck (mirrors README "Verification")
```powershell
.\.venv\Scripts\python -m pytest tests/test_config.py tests/test_health.py
.\.venv\Scripts\python -m ruff check apps/api db tests
cd apps/web && npm run typecheck && npm run build
```
Run a single test file/case:
```powershell
.\.venv\Scripts\python -m pytest tests/test_order_processing.py -k some_case
```
Most of the test suite (everything beyond config/health) needs a real
PostgreSQL, opted in via `RUN_DATABASE_TESTS=1` with `DATABASE_URL` pointing at
a **disposable** database whose name ends in `_check` — never point it at the
dev or production database. These tests apply migrations/seeds twice and assert
on counts, alias relationships, and RLS; that's expected, not a bug.

Native `psycopg` can be blocked by Windows Application Control on this machine
(see [docs/VALIDATION.md](docs/VALIDATION.md)) — database-backed checks may need to run inside
Docker/Linux instead of the native `.venv`.

### Single-order / job operations (local)
```powershell
docker compose --env-file .env.local exec api python -m db.process_order --id <raw_order_ingestion.id>
docker compose --env-file .env.local exec api python -m db.backfill_locations
```
`process_order` uses the raw UUID, not the storefront order number. Rerunning an
already-processed order repairs only its PENDING item mappings — it never
duplicates the order, changes prices, or touches `raw_payload`.

## Architecture

### Request/data flow
```
Shopify/Hostinger export (raw JSON)
  -> raw_order_ingestion (migration 001)     [source of truth for what was received]
  -> db/process_order.py / worker            [normalizes + resolves + inserts]
  -> customers, orders, order_items          [migration 003, +006 pending mappings, +007 location]
  -> apps/api (FastAPI)                      [admin.py: ingestion/jobs/mappings; operations.py: dashboard/orders/customers]
  -> apps/web (Next.js)                      [operational UI + CEO sales dashboard]
```

### Order processing pipeline (read in this order — docs/PROCESSING_FLOW.md)
1. `db/process_order.py` — entry point, gets the engine, calls `process_single_order()`.
2. `apps/api/normalization.py` — **pure** functions for phone/date/price transforms; no SQL.
3. `apps/api/product_resolver.py` — `resolve_product()` matches aliases -> product/variant
   IDs; raises `MappingPending` on missing/ambiguous/inactive matches (this is not an error path).
4. `apps/api/order_processing.py` — owns the transaction, does the actual inserts.
5. `apps/api/location.py` — `normalize_delivery_location()` fills city/state/country/pincode
   with per-field provenance before the orders INSERT.

Key invariant carried through migrations 006–007: **a catalogue/location problem
never blocks a valid sale.** Unresolvable product mappings become
`order_items.mapping_status = PENDING` (product_id NULL) instead of rejecting the
order; unresolvable delivery fields stay NULL instead of rejecting the order.
`raw_payload` and `orders.address` are never rewritten — only derived/report
columns are. Any new analytics query must `LEFT JOIN` the catalogue/location and
keep an "Unmapped"/"Unknown" bucket rather than dropping those rows. Overall
revenue/AOV/RFM must be computed from `orders`, not from a join that fans out per
line item.

Processing one raw record: `SELECT ... FOR UPDATE SKIP LOCKED` claims it, marks
`PROCESSING` inside the transaction, uses a savepoint for the row inserts so a
validation failure can roll back to `ERROR` without losing the transaction, then
commits. Only `HOSTINGER` as a source is implemented; other sources need their
own adapter under `normalization.py`/`product_resolver.py`, following the same
"never invent a mapping, never reject a valid sale" contract.

### Operational API and dashboard (`apps/api/operations.py`)
Everything the frontend renders — `/admin/dashboard` (raw-status/mapping/revenue
counters), `/admin/analytics` (year/quarter/month-grain revenue, orders, new
customers, top-5 products, all compared against the prior equivalent period),
`/orders`, `/orders/{id}`, `/customers`, `/customers/{id}` — lives here, not in
`admin.py` (which stays focused on ingestion/jobs/mappings/aliases). Revenue and
order counts here already follow the "compute from `orders`, not a fanned-out
item join" rule; only the top-products query joins `order_items` on purpose.
`PUT /admin/ingestion/{id}/order-date` is the audited correction path: it only
accepts `ERROR` records, requires a `reason` (min 5 chars), upserts into
`order_corrections` (migration 009, RLS-restricted like migration 005's tables),
and re-queues that one record via `enqueue_job(..., "RETRY_ONE", ...)` — it never
edits `raw_payload` or writes the order directly.

### Two separate admin credentials — do not conflate them
- **Backend**: `ADMIN_API_TOKEN`, checked by `apps/api/auth.py:require_admin` via
  `HTTPBearer` on every `/admin/*`, `/orders*`, `/customers*` route. Fails closed
  (503) if unset, constant-time compared.
- **Frontend session**: a *different* cookie-based login in
  `apps/web/app/api/login/route.ts` — the operator pastes the same
  `ADMIN_API_TOKEN` into the login form, but once verified the browser gets an
  HTTP-only `thaazhai_admin` cookie derived from a separate `ADMIN_UI_SESSION`
  secret (SHA-256'd, 8-hour maxAge, `secure` in production), not the admin token
  itself. Next.js server routes/components hold `ADMIN_API_TOKEN` server-side to
  call the FastAPI backend; the browser never sees it. Both `ADMIN_API_TOKEN` and
  `ADMIN_UI_SESSION` must be set for login to work locally — check
  `apps/web/.env.local` if login 503s.

### Job queue (Phase 3 — docs/PROCESSING_JOBS.md)
No Redis/broker: `processing_jobs` + `processing_job_items` (migration 008) *are*
the queue. A job snapshots the raw-record IDs to process at request time; later
arrivals wait for the next job. A partial unique index allows only one
QUEUED/RUNNING job at a time. The worker (`workers/order_processor`) takes a
PostgreSQL **session advisory lock** to serialize itself and resumes RUNNING jobs
after a restart — this means the worker's DB connection must be a
direct/session-pooler connection, not a transaction-pooled one (session-scoped
advisory locks don't survive pooled transactions). Each processed item commits
in its own transaction alongside its job-item result and counters, so a crash
loses at most one item's progress, not the whole job.

Call chain: `POST /admin/jobs/process-pending` (`apps/api/admin.py`) ->
`apps/api/jobs.py:enqueue_job()` -> worker polls every 2s ->
`apps/api/jobs.py:run_next_job()` -> `apps/api/order_processing.py:process_single_order()`.

Admin routes require a bearer `ADMIN_API_TOKEN` (fails closed if unset); health
endpoints stay public. Never put this token in a `NEXT_PUBLIC_*` variable.

### Config selection (`apps/api/config.py`)
`APP_ENV` (from the process environment, default `development`) picks which env
file loads — `.env.local` for development, `.env.production` for production,
none for `test`. A file can never change `APP_ENV` itself, and process-level env
vars always override the file (matches how Render injects secrets). Settings are
cached via `lru_cache`, so **restart the process** after changing env values —
edits won't be picked up live.

### Frontend
`apps/web` is a Next.js App Router admin application, cookie-session-gated (see
auth split above). Implemented pages: `/` (dashboard + `dashboard-charts.tsx`
analytics), `/ingestion`, `/jobs`, `/mappings`, `/orders` + `/orders/[id]`,
`/customers` + `/customers/[id]`, `/login`. There is no `/marketing` page yet —
that's the deliverable of the (unimplemented) Meta integration; check
`docs/META_MARKETING_INTEGRATION.md` and `docs/CLAUDE_HANDOFF.md` before adding one.
`apps/web/AGENTS.md` (auto-generated by `next dev`, keep it if it reappears)
warns this Next.js version has breaking API/convention changes from training
data — read `node_modules/next/dist/docs/` before writing frontend code you
haven't verified against this version.

## Conventions worth knowing

- Ruff config lives in [pyproject.toml](pyproject.toml): `E`, `F`, `I` rules, 100-char lines, target py312.
- `db/migrations/*.sql` are numbered and checksummed in `schema_migrations` by the
  runner (`db/migrate.py`) — never edit an already-applied migration file; add a new one.
  Migrations 001-011 are applied locally. Migration 010 adds customer follow-up history
  and migration 011 adds dynamic customer analysis. Migration 012 is planned for Meta
  marketing tables (`docs/META_MARKETING_INTEGRATION.md`) and does not exist yet.
- `db/seeds/*.sql` preserve existing master rows; they don't silently repair
  conflicts or overwrite metadata on rerun.
- Alias matching normalizes case/whitespace/HTML entities but never guesses or
  invents an alias — ambiguous matches must be resolved by an admin, not the code.
