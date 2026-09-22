# Phase 1 validation

Local runtime: Windows Python 3.14.7 and Node 24.19.0.
Deployment-target DB test: Linux Python 3.12 and disposable PostgreSQL 17.

Run pytest, Ruff, npm run typecheck and npm run build as documented in README.
The opt-in database test needs RUN_DATABASE_TESTS=1 and DATABASE_URL pointing to a
disposable database ending in _check. It applies migrations/seeds twice and checks
counts, alias relationships, absence of seeded orders, and RLS. Never use business data.

Windows Application Control blocked the local psycopg binary DLL. The health API
and web shell run locally; database-backed work requires an approved driver
installation or the Linux runtime. No security settings were changed.

The Python lockfile includes runtime and test tooling for reproducibility.
Upstream Starlette emits httpx/AnyIO deprecation warnings in the test client;
these do not fail health tests. Supabase credentials are not configured.

Final results: 3 tests passed in Linux Python 3.12.14 against PostgreSQL 17;
Ruff passed; TypeScript passed; Next.js production build passed; the built web
server returned HTTP 200 with the expected shell content. Migrations and seeds
were applied twice successfully. The disposable database was removed afterward.
Browser visual inspection was unavailable because the browser sandbox failed to
start. No Supabase migration, Render deployment, or GitHub push was performed.

## Phase 2 result

45 tests passed against isolated PostgreSQL; Python lint passed. Coverage includes
phone normalization, multiple items, unknown/ambiguous/inactive pending mappings,
null variants, shampoo 100, duplicate prevention, explicit ERROR retries, date
ordering, locked-record exclusion, and rollback after normalized inserts.
No imported business records were processed during these checks.

Location extension: 59 tests passed in disposable PostgreSQL and lint passed.
Migration 007 applied locally; one existing order was backfilled. Original address
JSON/raw payloads are preserved. Supabase was not accessed or changed.

Phase 3 verification completed: 67 tests passed against isolated PostgreSQL;
Python lint passed. Local API, database, and worker are running. Public health
returns 200; unauthenticated admin requests return 401; authenticated summary and
job listing return 200. No jobs were queued on the imported dataset: 1,418 NEW,
1 PROCESSED, zero ERROR, and one normalized order. Supabase was not touched.

Phase 4 verification: 70 backend tests passed against isolated PostgreSQL. Python
lint, TypeScript, and Next.js production build passed. Standard login rejects a
wrong token, establishes an HTTP-only cookie for the correct token, and all list
and real detail pages returned HTTP 200. Local migration 009 applied. No correction
was entered for order 2443; order/customer/raw counts were unchanged by Phase 4.
Computer-use visual inspection was unavailable because the Windows sandbox helper
failed, so verification used the production build and HTTP-rendered pages.


## Baseline before Meta integration

The current local dataset contains 1,418 processed orders and one raw order error.
Sales analytics supports annual, rolling three-month and daily month views. The latest
backend suite completed with 73 passing tests; Python lint, TypeScript and the Next.js
production build passed. No Meta API call, token, table, migration or marketing metric
has been added. The next implementation must preserve this baseline and update this
section with reconciliation evidence from Ads Manager.

## Customer follow-up and release candidate

Migration 010 adds backend-only, append-only customer follow-up history with outcome,
channel, team member, notes and optional next-contact time. Customers expose the latest
status for filtering and sorting, while detail responses preserve full history. The
customer UI records and immediately displays shared contact activity.

Local migration 010 applied successfully without changing order or raw-ingestion data.
The complete backend suite passed in Linux Python 3.12 against a disposable PostgreSQL
database: 72 passed. Ruff, TypeScript and the Next.js production build passed. The local
readiness endpoint returned ready and the NOT_CONTACTED customer filter returned current
business rows. Production migration and Render deployment are still pending in this
entry and must be recorded separately after verification.

## Customer segmentation

Migration 011 adds the backend-only `customer_analysis` view. On the 2026-09-22 local
snapshot it produced 26 Champions, 101 Loyal repeat, 178 New customer, 76 High-value
one-time, 14 At-risk repeat, 71 At-risk high-value, 321 Active one-time and 451 Dormant
one-time customers. Counts sum to 1,238. Current value thresholds were INR 560 for high
value and INR 1,000 for VIP value.

The customer UI shows bucket strategy cards, filtering, row-level segments, recency,
average order value and overlapping lifecycle/value/product-affinity tags. The complete
backend suite passed against disposable PostgreSQL: 73 passed. Ruff, TypeScript and the
Next.js production build passed. An authenticated rendered Champions page returned HTTP
200 with bucket strategy and VIP tag content. Migration 011 was applied only to local
PostgreSQL; production remains unchanged.
