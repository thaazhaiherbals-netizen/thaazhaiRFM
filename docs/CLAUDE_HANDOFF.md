# Claude handoff: current state and next task

Last updated: 2026-09-23.

Latest local change: shared team viewer access is implemented in the web app. See `docs/TEAM_ACCESS.md` for permissions, tests and rollout. The user has deployed web/API to Railway and confirmed the app opens; viewer changes still require a web deployment. No viewer migration is needed.

This is the starting document for continuing the Thaazhai operations and analytics
project in Claude Code. Read the repository `CLAUDE.md` first, then this file, then
`docs/META_MARKETING_INTEGRATION.md`.

## Mission for the next work session

The immediate release adds customer follow-up tracking and deploys the current analytics
application to Render. After that release is verified, the next planned development is
the read-only Meta Marketing API integration in
`docs/META_MARKETING_INTEGRATION.md`.

Migration 010 is customer follow-up history, migration 011 is dynamic customer
segmentation, migration 012 adds sales configuration; the next new migration should use 013.
No Meta tables, clients, sync jobs, endpoints, pages, fixtures, or real credentials
exist yet.

## What is already implemented

- Local PostgreSQL 17 through Docker Compose.
- FastAPI backend under `apps/api`.
- PostgreSQL-backed order worker under `workers/order_processor`.
- Next.js App Router admin UI under `apps/web`.
- Raw-order import from Supabase into isolated local PostgreSQL.
- Transactional order normalization and customer/order/item creation.
- Product alias matching that preserves sales with `PENDING` unmapped items.
- Delivery location fields with provenance while preserving source JSON.
- Processing jobs, retries, mapping resolution and audited order-date correction.
- Protected Ingestion, Jobs, Product Mappings, Orders and Customers pages.
- Customer order-history expansion and order drill-down.
- Sorting/searching on operational lists.
- Shared append-only customer follow-up outcomes, notes, ownership and next-contact time.
- Dynamic D2C sales buckets with lifecycle, value and product-affinity tags.
- CEO sales dashboard with yearly, rolling three-month and selected-month daily views
  for revenue, orders, products and new customers.

## Current local data and validation baseline

- 1,419 raw records in the imported snapshot: 1,418 processed and one error.
- The remaining error is source record `2443`, which has no `order_date` in its raw
  payload. Do not invent a date. No correction has been saved for it.
- Latest recorded verification: 73 backend tests passed, plus Python lint, TypeScript
  checking and Next.js production build.
- Migrations 001 through 011 exist. Migration 010 adds `customer_follow_ups`;
  migration 011 adds dynamic customer analysis. The next planned schema file is
  `012_meta_marketing.sql`; never edit an applied migration.
- No Meta API call or production database change has been made.

Update `docs/VALIDATION.md` with new evidence as work is completed. Treat the values
above as a recorded baseline, not as assertions that automatically remain current.

## Environment boundaries

Local development uses `.env.local` and Docker PostgreSQL. Production uses Render
environment variables and Supabase PostgreSQL with `APP_ENV=production`.

The local raw-order data is an explicitly imported snapshot. It does not synchronize
automatically with Supabase. Normal development, migration and test commands must not
target Supabase. Never run all migrations or seeds blindly against production.

Meta secrets must remain server-side. Never place the access token in Git, a database
row, logs, HTML, browser requests, screenshots, fixtures, or a `NEXT_PUBLIC_*` value.
The example env files contain blank reserved Meta variable names only.

## Work that can start without Meta credentials

Do not block local implementation while waiting for a live token. Claude can build and
validate these parts entirely with redacted fixtures:

1. Typed optional Meta settings and configuration tests.
2. Migration 012 and disposable-database migration tests.
3. Pure parsers for money, counts, actions and action values.
4. HTTP client behavior using mocked responses: pagination, retries, async reports and
   sanitized errors.
5. Idempotent raw landing and normalized upsert logic.
6. Manual sync CLI, authenticated endpoints and absent-configuration 503 behavior.
7. Marketing UI loading, empty, error, freshness and drill-down states.

A real account is required only for saving a redacted representative response,
confirming action names, running a small-range reconciliation, enabling a production
schedule and performing the historical backfill.

## Information to request from the owner before live connection

1. Meta Business ID and ad account ID.
2. Account currency and timezone from Ads Manager.
3. Read-only app/system-user token authorized for the account with `ads_read`.
4. Earliest history date to import.
5. Attribution windows.
6. Real action types for purchase, checkout, add-to-cart and lead.
7. Whether business revenue remains gross `orders.order_value`.
8. Desired daily sync time and owner for token failures.

Ask for secrets only when the live reconciliation step is ready. The owner should put
the token directly in `.env.local` or Render; do not ask them to paste it into source,
documentation or a chat response.

## Required implementation order

1. Read `CLAUDE.md`, this handoff, `docs/DATA_MODEL.md`, `docs/ENVIRONMENTS.md`,
   `docs/VALIDATION.md` and `docs/META_MARKETING_INTEGRATION.md`.
2. Inspect existing code and tests; do not assume the documents replace the code.
3. Add optional settings and fixture-based tests. Existing application startup must
   continue to work when every Meta value is blank.
4. Add migration 012 and prove repeatability against a disposable database ending in
   `_check`.
5. Build the pure parser and mocked client before making a live request.
6. Build raw landing, normalized facts, idempotent reruns and manual CLI.
7. Add authenticated API reporting and sync-status endpoints.
8. Add the Marketing page using the established dashboard visual language.
9. Reconcile a small date range with Ads Manager using identical dates, timezone,
   attribution and filters.
10. Only after reconciliation, add the production cron and bounded historical backfill.

Complete each independent step and its tests before moving to the next. Do not deploy,
schedule or backfill the live account merely because fixture tests pass.

## Data rules that must survive the change

- Compute sales revenue/AOV/order counts from `orders`, avoiding order-item fanout.
- Keep unmapped items and unknown locations in analytics with explicit fallback buckets.
- Join Meta dimensions by stable IDs; names are mutable labels.
- Store money as PostgreSQL `NUMERIC` and Python `Decimal`, not floating point.
- Canonical Meta fact grain is one ad, one reporting date and one attribution
  configuration. Do not sum responses from multiple reporting levels.
- Keep Meta-attributed conversions distinct from observed business orders.
- Do not claim campaign-level sales attribution until reliable order-side UTM/click IDs
  and an attribution model exist.
- Preserve full action arrays/raw payloads so new action types are not discarded.
- Re-fetch a configurable recent lookback because Meta can restate conversions.
- The existing order worker is not the Meta scheduler.

## Validation commands

From the repository root:

```powershell
docker compose --env-file .env.local up -d --build
docker compose --env-file .env.local exec api python -m db.migrate --seed
```

Run Python checks using the documented Docker/disposable-database path when native
Windows `psycopg` is blocked:

```powershell
.\.venv\Scripts\python -m pytest tests/test_config.py tests/test_health.py
.\.venv\Scripts\python -m ruff check apps/api db tests
cd apps/web
npm run typecheck
npm run build
```

Database-backed tests must opt in with `RUN_DATABASE_TESTS=1` and point only to a
disposable local database whose name ends in `_check`.

## Repository state warning

At the time of this handoff, `git status` showed most implementation files as untracked
and only `README.md` as modified. Do not assume the GitHub repository contains the
current local application. Inspect `.gitignore`, review all files for secrets, and have
the owner explicitly decide when to stage, commit and push the complete baseline.

## Completion evidence

The Meta task is complete only when all acceptance criteria in
`docs/META_MARKETING_INTEGRATION.md` pass. Record exact test results, migration results,
the reconciled account/date range without secrets, metric differences, and deployment
status in `docs/VALIDATION.md`. Change planning language in README and other docs only
after the corresponding feature actually works.

## Prompt to start Claude

Continue the Thaazhai project from `docs/CLAUDE_HANDOFF.md`. Implement the read-only
Meta Marketing API work in `docs/META_MARKETING_INTEGRATION.md` in the required order.
Start with credential-independent configuration, migration and fixture-tested parsing.
Preserve all documented data and security invariants, run the appropriate checks after
each slice, and update `docs/VALIDATION.md` with evidence. Ask me for the eight live
account inputs only when they are needed for real-account reconciliation.


## Future business intelligence vision

See [Business intelligence and customer action loop](BUSINESS_INTELLIGENCE_VISION.md)
for the future direction and incremental delivery plan. This is planning, not implemented functionality.
