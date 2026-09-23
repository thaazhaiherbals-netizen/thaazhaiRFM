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

## Meta marketing integration (2026-09-23)

Uncommitted, in the working tree on `codex/customer-support-access` (see
`docs/CLAUDE_HANDOFF.md`). Migration 013 applied to the local Docker database only;
Supabase untouched; nothing deployed.

Automated checks:

- Full backend suite in Linux Python 3.12 against a freshly created disposable
  `thaazhai_check` database: **126 passed** (baseline 73). Coverage includes optional,
  blank and malformed settings; attribution-window spellings; Decimal parsing;
  overlapping action types not double counted; unknown actions kept; the live account's
  `initiate_checkout` spelling; pagination without the token in URLs; bounded retries
  with Retry-After; sanitized permanent and network errors; async report runs;
  idempotent reruns; restatements and withdrawn rows; ID-based dimensions; failed pages
  keeping prior facts; the overlapping-run lock; scheduler decisions (wait, run, done,
  backoff, give up, catch-up) and a full scheduler tick; background chunking of long
  manual syncs; coverage/freshness; blended MER and CAC from `orders`/`customers` with
  half-up rounding; admin auth; absent-config 503; migration repeatability and RLS.
- Ruff, `npm run typecheck` and `npm run build` passed.
- A reused `_check` database fails `test_database` and one segment test because
  fixtures truncate at test start only; recreate it before each run (see handoff).
- Test connections must be closed (`with engine.connect()`); an unclosed reader left
  "idle in transaction" blocks the next test's TRUNCATE indefinitely.

Live account (read-only, local database only):

- Account "Thaazhai New Ad account", INR, Asia/Kolkata; attribution 7-day click +
  1-day view, `action_report_time=conversion`; API v23.0.
- Daily scheduler run for 2026-09-16..22 and CLI backfill 2026-03-01..2026-09-22 in
  seven 31-day async chunks: **all 8 runs SUCCEEDED; normalized ad-level spend equals
  Meta's account-level control spend in every run (difference 0.00).**
- Facts 2026-04-11 (first spend) to 2026-09-22: 1,521 ad-day rows, 21 campaigns,
  spend 333,875.67 INR, Meta-reported purchases 1,101 worth 501,688.95 INR,
  checkouts 7,751. March 2026 has no spend (covered, zero rows).
- Monthly spend: Apr 9,759.55; May 56,186.60; Jun 88,349.41; Jul 56,294.95;
  Aug 64,908.04; Sep (to 22nd) 58,377.12.
- Scheduler logs `decision: done` after the day's success.

Read-only connection check (writes nothing; prints account, 7-day spend, row count and
action types):

```bash
docker compose --env-file .env.local exec -T api python -c "
from datetime import date, timedelta
from apps.api.config import get_settings as g
from apps.api.integrations.meta.client import MetaClient, MetaApiError
s=g(); c=MetaClient(s.meta_ad_account_id, s.meta_access_token.get_secret_value(), s.meta_graph_api_version, max_attempts=2)
try:
    a=c.get_account(); print({k:a.get(k) for k in ('name','currency','timezone_name')})
    y=date.today()-timedelta(days=1); f=y-timedelta(days=6)
    print(c.account_spend(f, y, s.meta_attribution_windows, s.meta_action_report_time))
except MetaApiError as e: print('META ERROR:', e)
finally: c.close()"
```

Not yet done: Ads Manager spot check of results metrics (acceptance criteria 3-4),
owner review of unclassified action types, production rollout.

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
