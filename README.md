# Thaazhai operations + analytics

An internal admin app for raw-order processing, customers, orders and analytics.
Current implementation includes transactional processing, background jobs, the protected
operations UI, customer/order drill-down, and the CEO sales analytics dashboard.

## Two separate environments

| | Local development | Live production |
|---|---|---|
| Database | PostgreSQL in Docker on your computer | Existing Supabase database |
| Backend settings | Root `.env.local` | Render variables / root `.env.production` |
| Selection | Default: `APP_ENV=development` | Explicit: `APP_ENV=production` |
| Data | Persistent local snapshot imported from Supabase plus development changes | Real business data |

The same Python application runs in both. The current local database was populated from
the Supabase `raw_order_ingestion` source so processing can be developed against a
realistic snapshot. Later production changes do not automatically sync into local.
The old shared `.env` is no longer read. Real env files are ignored by Git.

## Start local development

Install/start Docker Desktop and use Node.js 22+. From the repository root:

```powershell
# First setup only; do not overwrite existing files containing your settings.
Copy-Item .env.local.example .env.local
Copy-Item apps/web/.env.example apps/web/.env.local

# Start the local database and Python API.
docker compose --env-file .env.local up -d --build

# First setup: create tables and confirmed product mappings in LOCAL PostgreSQL.
docker compose --env-file .env.local exec api python -m db.migrate --seed

# Start the frontend in this terminal.
cd apps/web
npm ci
npm run dev
```

If the env files already exist, skip the Copy-Item commands.
The local setup has already been initialized on this workspace.

Open http://localhost:3000 for the app and http://localhost:8000/docs for the API.
http://localhost:8000/health/ready verifies the API can reach the local database.
Python edits reload automatically through the mounted source folders.
Restart the API after changing environment values:

```powershell
docker compose --env-file .env.local up -d --force-recreate api
```

Stop local API/database with:

```powershell
docker compose --env-file .env.local down
```

The named Docker volume retains your data after stopping. Do not add `-v` unless
you intend to erase local database data. Stop the frontend with Ctrl+C.

## Live deployment later

`.env.production.example` documents the required live settings. A blank
`.env.production` is prepared locally; it is not used by development.
For Render, set APP_ENV=production, DATABASE_URL to the existing Supabase URL,
and CORS_ORIGINS to a JSON array containing the live frontend URL.
Set the web service NEXT_PUBLIC_API_URL to the live API URL before building.
The Render Blueprint already sets production mode. Never put database credentials
in a NEXT_PUBLIC variable.

Starting the live API does not run SQL or seed data. Your live tables/seeds already
exist: inspect them and reconcile migration history before applying any missing
changes. Do not blindly rerun all seed/migration files against live Supabase.
Migration 005 changes Supabase client permissions and needs particular review.

See [the environment walkthrough](docs/ENVIRONMENTS.md) for configuration details.

## Verification

```powershell
.\.venv\Scripts\python -m pytest tests/test_config.py tests/test_health.py
.\.venv\Scripts\python -m ruff check apps/api db tests
cd apps/web
npm run typecheck
npm run build
```

Local API/database checks run through Docker because Windows Application Control
blocked this machine's native psycopg DLL. See docs/VALIDATION.md.

## Roadmap

1. Foundation: web shell, API health, SQL, product seeds and deployment setup.
2. Transactional order processing and core business tests.
3. Background worker, job APIs, retries and admin authentication.
4. Operational UI.
5. Sales analytics dashboard is implemented; RFM scoring remains planned.
6. Financial truth: Meta ad spend and Zoho expenses, joined with sales. Meta Ads
   reporting is built and running locally against the live account (spend reconciles
   exactly; not yet in production). Zoho expenses/stock is not built.
7. Funnel efficiency: Shopify abandoned carts vs. spend vs. orders.
8. Customer segmentation and bucketing on top of Phase 5's RFM data.
9. Retention actions: WhatsApp cross-sell/upsell, discounts, calls, feedback.
10. AI prompt layer over the metrics produced by phases 6-9.

Apart from Meta Ads reporting, phases 6-10 are planning only. See
[docs/GROWTH_PLATFORM.md](docs/GROWTH_PLATFORM.md) for the layer-by-layer
rationale and build order.

Meta Ads reporting (`/marketing`) is documented in
[docs/META_MARKETING_INTEGRATION.md](docs/META_MARKETING_INTEGRATION.md): how syncing
works, the daily scheduler, settings, token setup and troubleshooting. Do not add a
real Meta token to any committed env file.

For continuation in Claude Code, start with
[docs/CLAUDE_HANDOFF.md](docs/CLAUDE_HANDOFF.md). It records the repository state, the
local baseline, the prioritized next work and a copyable prompt.

The seed catalogue includes 22 products, 25 variants and eight confirmed Hostinger
aliases. The full historical mapping file still needs verification.

## Phase 2: single-order processing

The processor is now implemented. See docs/PROCESSING_FLOW.md for a beginner
walkthrough and the local single-order command. Valid sales are saved even when
catalogue matching needs attention; those items carry mapping_status=PENDING.
Migration 006 adds this behavior without changing raw payloads. Overall analytics
must include pending items' orders; product reports must show an Unmapped bucket.
Job APIs, automatic batch processing and the operational dashboards are implemented.

## Phase 3: admin API and worker

Implemented PostgreSQL-backed jobs, a separate worker, progress endpoints, error
retries, pending-mapping resolution and alias management. Admin routes use bearer
authentication. The local ADMIN_API_TOKEN is in .env.local; use Swagger Authorize.
See docs/PROCESSING_JOBS.md for the call-by-call explanation and commands.
Run migrations before starting the worker. Starting services does not queue work.
The Process Pending API processes all NEW records selected at request time.
The frontend operational pages described below are implemented.

## Phase 4

The operational admin interface is available at http://localhost:3000. It includes
protected Dashboard, Ingestion, Jobs, Product Mappings, Orders and Customers pages.
Sign in using ADMIN_API_TOKEN from the root .env.local file. See
`docs/PROCESSING_JOBS.md` for architecture and security details.

Customers include shared follow-up tracking for calls, WhatsApp, email and other
contact. The latest outcome is visible and filterable in the customer list; expanding
a customer allows the team to record who contacted them, notes, an optional next
follow-up time, and review the append-only contact history.

The Customers page also calculates actionable D2C sales buckets and overlapping
lifecycle, value and product-affinity tags. See
[docs/CUSTOMER_SEGMENTATION.md](docs/CUSTOMER_SEGMENTATION.md) for the business rules
and recommended outreach order.


## Current analytics baseline

The dashboard uses processed local PostgreSQL orders and supports annual, rolling
three-month and daily month views for revenue, customers and product sales. Customers
have dynamic opportunity buckets, value/lifecycle/product tags and contact history.
`/marketing` shows Meta spend, clicks, Meta-attributed conversions and blended MER/CAC
against orders. Local data is backfilled from 2026-03-01 and the `meta-scheduler`
service re-syncs the previous 7 days every morning after 06:00 IST.

## Team view-only access

See [Team access](docs/TEAM_ACCESS.md) for viewer permissions, Railway setup, session revocation and verification.
