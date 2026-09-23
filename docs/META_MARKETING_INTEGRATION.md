# Meta Marketing API integration

Design contract **and** operating guide for Phase 6 read-only Meta Ads reporting.

**Status (2026-09-23): implemented and running locally against the live ad account;
not deployed to production; not yet committed** (see `docs/CLAUDE_HANDOFF.md`,
"Repository state"). Spend reconciles exactly with Meta's account-level control total
for every run. Remaining: an Ads Manager spot check of results metrics, review of
unclassified action types, and production rollout.

## How it works (operating guide)

```
Meta Graph API (ads_read) --sync--> PostgreSQL --read--> /admin/marketing/* --> /marketing
        ^                               ^
        |  CLI backfill, in-app sync,   |  orders/customers for blended MER/CAC
        |  daily scheduler              |
```

The dashboard never calls Meta. Changing dates filters data already synced; a **sync**
is what calls Meta. This keeps reports fast, avoids Meta rate limits, allows joining
with `orders`, and preserves history and restatements.

### One sync run (`apps/api/integrations/meta/sync.py`)

1. Take a PostgreSQL advisory lock per ad account (a second run gets "already running").
2. Insert a `meta_insight_sync_runs` row (`RUNNING`, dates, attribution, API version).
3. Read account name/currency/timezone into `meta_ad_accounts`.
4. Fetch ad-level daily Insights (`level=ad`, `time_increment=1`), cursor-paginated;
   runs longer than 7 days (in-app) or with `--async` (CLI) use Meta's async reports.
5. Land every row unchanged in append-only `raw_meta_insights` (committed per page).
6. Fetch Meta's account-level spend for the same dates as a control total.
7. In one transaction: upsert campaigns/ad sets/ads by ID, **delete** facts for the
   account + dates + attribution key, rebuild them from this run's raw rows.
8. Mark `SUCCEEDED` with normalized vs control spend, or `FAILED` with a sanitized
   error (the token is scrubbed). A failed run leaves previous facts untouched.

**Re-syncing the same dates is safe:** facts are replaced, never added, so totals do
not double; Meta restatements and withdrawn rows are reflected; raw history keeps
every version.

### Ways to sync

| Way | Command / place | Notes |
|---|---|---|
| Backfill | `docker compose --env-file .env.local exec api python -m db.import_meta_insights --from 2026-03-01 --to 2026-09-22 --async` | 31-day chunks (`--chunk-days`), trigger `BACKFILL` |
| Recent window | `docker compose --env-file .env.local exec api python -m db.import_meta_insights --recent` | `META_SYNC_LOOKBACK_DAYS` through yesterday, account timezone |
| In app (admin) | `/marketing` "Sync from Meta" form, or "Fetch these dates" in the coverage banner | `POST /admin/marketing/sync`; up to 31 days inline, up to 400 days in background 31-day chunks (HTTP 202) |
| Daily schedule | compose service `meta-scheduler` (`python -m workers.meta_sync`) | After `META_SYNC_TIME` (account timezone) re-fetches the lookback through yesterday once per day; catches up if the host was off; retries every 30 min, max 3 attempts/day; idle when Meta is not configured |

The scheduler decides from sync-run history (`apps/api/integrations/meta/schedule.py`),
not memory, so restarts are safe. Worker processes do not auto-reload: after code
changes run `docker compose --env-file .env.local restart meta-scheduler`.

### Settings (root `.env.local`; host variables in production)

| Variable | Meaning |
|---|---|
| `META_AD_ACCOUNT_ID` | Numeric ad account ID (`act_` prefix optional) |
| `META_ACCESS_TOKEN` | System-user token with **only `ads_read`**; starts with `EAA` |
| `META_GRAPH_API_VERSION` | e.g. `v23.0` (format validated) |
| `META_SYNC_START_DATE` | Optional earliest date the CLI may backfill |
| `META_SYNC_LOOKBACK_DAYS` | Default 7; recent/scheduled re-fetch window |
| `META_ATTRIBUTION_WINDOWS` | Default `["7d_click","1d_view"]`; comma list also accepted |
| `META_ACTION_REPORT_TIME` | `conversion` (default), `impression` or `mixed` |
| `META_SYNC_TIME` | Daily scheduler time `HH:MM` in account timezone; default `06:00` |

Blank values keep the app running; sync endpoints then return 503. Recreate containers
after changing values:
`docker compose --env-file .env.local up -d --force-recreate api meta-scheduler`.
Changing attribution settings creates a new attribution key and reports only show facts
for the current key, so re-backfill after changing it.

### Getting a token (done once on 2026-09-23)

1. developers.facebook.com: create an app (Business type / Marketing API use case)
   connected to the Thaazhai Business portfolio.
2. Business Settings > Users > System users: create a system user, then **Assign
   assets**: the app (Manage/Develop app) and the ad account (**View performance** only).
3. Generate a token for that app with only `ads_read` (expiry "Never" if offered).
4. Paste it into `.env.local` directly, never into chat, Git or docs.

| Error (sync-runs / CLI) | Cause |
|---|---|
| `code 190` "Cannot parse access token" | Value malformed (placeholder, quotes, spaces) |
| `code 190` expired/invalid | Regenerate the token |
| `code 200` "has NOT grant ads_management or ads_read" | System user not assigned to the ad account, token lacks `ads_read`, or app not authorized for the account |
| `code 100` | Wrong account ID or unsupported API version |
| HTTP 409 on sync | Another sync for the account is running |

### API

All under `/admin/marketing`, admin bearer token. In the web app admins and viewers can
read `/marketing`; only admins can sync; the support role has no access. Dates default
to the 30 days ending yesterday. Swagger: `http://localhost:8000/docs` > Authorize.

- `GET /overview?date_from=&date_to=`: Meta totals and ratios; business revenue, orders,
  new customers; blended MER, spend per order, new-customer CAC; daily series;
  `coverage` (days not covered by a successful sync); freshness; unclassified actions.
- `GET /campaigns?date_from=&date_to=&sort=&direction=&limit=&offset=`
- `GET /campaigns/{campaign_id}?date_from=&date_to=`: totals, ad sets, ads.
- `GET /sync-runs`: history including `control_difference`.
- `POST /sync` `{"date_from","date_to"}`: see "Ways to sync".

### Code map

- `apps/api/integrations/meta/client.py`: HTTP; cursor pagination (never follows
  `paging.next`, which embeds the token); async reports; bounded retries.
- `apps/api/integrations/meta/parser.py`: pure parsing and action-type priority lists.
- `apps/api/integrations/meta/sync.py`: lock, raw landing, normalization.
- `apps/api/integrations/meta/schedule.py`, `workers/meta_sync/`: daily scheduler.
- `db/import_meta_insights.py`: CLI. `apps/api/marketing.py`: reports and manual sync.
- `apps/web/app/marketing/`: page, campaign drill-down, chart.
- Tests: `tests/test_meta_*.py`, `tests/test_marketing_api.py`, `tests/fixtures/meta/`.

### Action-type mapping (confirmed on the live account)

Each metric takes the **first present** type from its list; overlapping types describe
the same event and summing them would double count.

- purchases and value: `omni_purchase`, `purchase`, `offsite_conversion.fb_pixel_purchase`
- add to cart: `omni_add_to_cart`, `add_to_cart`, `offsite_conversion.fb_pixel_add_to_cart`
- checkouts: `omni_initiated_checkout`, `initiate_checkout`,
  `offsite_conversion.fb_pixel_initiate_checkout` (this account uses `initiate_checkout`)
- leads: `lead`, `onsite_conversion.lead_grouped`, `offsite_conversion.fb_pixel_lead`
- landing page views: `landing_page_view`, `omni_landing_page_view`; link clicks come
  from `inline_link_clicks`.

Everything else stays in the `actions` JSON and is listed as "Unclassified". The live
account also reports messaging (`onsite_conversion.messaging_*`), custom conversions
(`offsite_*_add_20_s_calls`, `offsite_*_add_meta_leads`), `onsite_web_*` and
engagement types. Promote one to a column only after owner confirmation, via a new
migration plus a re-sync.

### Owner inputs (recorded 2026-09-23)

1. Ad account "Thaazhai New Ad account" (ID kept in `.env.local`, not in docs).
2. Currency INR, timezone Asia/Kolkata (read from the API).
3. System-user token with `ads_read`, configured locally.
4. History from 2026-03-01 (first spend 2026-04-11).
5. Attribution 7-day click + 1-day view, `action_report_time=conversion`.
6. Action types confirmed above; messaging and custom conversions pending review.
7. Business revenue stays gross `orders.order_value` (revisit refunds/tax later).
8. Daily sync 06:00 IST. **Owner for token failures: not yet named.**

---

# Design contract

The sections below are the original contract. They still govern changes: keep the
grain, security, metric and test rules when extending the integration.

## Outcome

Collect read-only Meta Ads performance into PostgreSQL and combine it with existing
sales/customer facts so the CEO dashboard can answer:

- How much did we spend and what reach, impressions, clicks and results did it buy?
- What are CPM, CTR, CPC and Meta-reported ROAS?
- What are blended MER, spend per order and new-customer acquisition cost?
- Which campaigns, ad sets and ads consume spend or produce results?
- Are daily numbers current, complete and reconciled with Meta Ads Manager?

This task does not create, edit, pause or publish ads. Request only read access.

## Existing project boundaries

- FastAPI backend: `apps/api`.
- Next.js App Router frontend: `apps/web`.
- PostgreSQL migrations are append-only numbered files in `db/migrations`.
- Sales facts: `orders.order_date` and `orders.order_value`.
- Customer acquisition date: `customers.first_order_date`.
- The existing worker processes PostgreSQL order jobs. It is not a scheduler.
- Development must use local PostgreSQL; production uses Supabase PostgreSQL.
- Admin endpoints require `ADMIN_API_TOKEN`.
- Meta secrets must never reach the browser.
- Sales revenue must come from `orders`, avoiding line-item fanout.

Read `CLAUDE.md`, `docs/DATA_MODEL.md`, `docs/ENVIRONMENTS.md`, and
`docs/GROWTH_PLATFORM.md` before coding.

## Business-owner inputs required before live account connection

Do not guess these values. Credential-independent work may proceed with fixtures, but
record the agreed values before real-account reconciliation or production scheduling.

1. Meta Business ID and ad account ID (`act_...`).
2. Ad-account currency and timezone exactly as displayed in Ads Manager.
3. Meta app/system-user access and a token authorized for the account with
   read-only insights permission (`ads_read`).
4. Earliest historical date to import.
5. Attribution windows to request and display.
6. Action types representing purchase, checkout, add-to-cart and lead for this account.
   Inspect a real response; do not assume action names.
7. Whether business revenue remains gross `orders.order_value` or later accounts for
   refunds, discounts, shipping and taxes.
8. Daily production sync time and owner for expired/revoked tokens.

## Meta API contract

Use the Meta Marketing API Insights endpoint for the configured account:

`GET /act_{ad_account_id}/insights`

Keep the version configurable in `META_GRAPH_API_VERSION`. Confirm the supported
version when implementation starts:

- Marketing API: <https://developers.facebook.com/docs/marketing-apis/>
- Insights API: <https://developers.facebook.com/docs/marketing-api/insights/>
- Permissions: <https://developers.facebook.com/docs/permissions/>

Minimum MVP request:

- `level=ad`
- `time_increment=1`
- explicit `time_range` with inclusive `since` and `until`
- account/campaign/ad-set/ad IDs and names, objective, spend, impressions, reach,
  frequency, clicks, outbound clicks, actions and action values
- configured attribution windows and documented `action_report_time`
- cursor pagination until `paging.next` is absent

Use response `date_start` and `date_stop`; never assign metrics to the fetch date.
Preserve account currency/timezone and the API/attribution configuration per run.

Meta can restate recent conversions. Daily sync must re-fetch a configurable lookback
instead of only yesterday. Start with seven days, then align it with the selected
attribution window.

Small daily windows may use synchronous Insights. Historical/large reports must support
the asynchronous report-run flow, polling and paginated retrieval. Retry HTTP 429 and
transient 5xx failures with bounded exponential backoff, honor `Retry-After`, and retain
usage headers for diagnostics without logging authorization data.

## Canonical grain and double-counting rule

The canonical fact is **one ad x one reporting date x one attribution configuration**.
Campaign, ad-set and account values are aggregates of those rows.

Do not put account-, campaign-, ad-set- and ad-level responses in one fact and sum them.
That multiplies spend. If account-level pulls are used for reconciliation, store them as
separate control totals.

## Migration 013 (implemented)

Implemented as `013_meta_marketing.sql` (012 was already used). Never edit it once
applied anywhere; add a new migration instead.

### meta_ad_accounts

- ad account ID primary key
- name, currency, timezone name/offset
- last seen timestamp and raw metadata JSONB

### meta_campaigns, meta_ad_sets, meta_ads

Store stable Meta IDs, parent IDs, latest name/status/objective, last seen timestamp and
raw metadata. Facts join by ID because names change.

### meta_insight_sync_runs

Store requested dates, level, fields/breakdowns, attribution configuration, API version,
ad account, status, page/row/attempt counts, timestamps, sanitized error summary and API
usage headers. Never store the access token or authorization header.

### raw_meta_insights

Append-only rows tied to a sync run with reporting date, object ID, raw payload JSONB,
payload hash and fetched timestamp. This proves what Meta returned and permits parser
repair. Dashboards query normalized facts, not this table.

### meta_ad_daily_performance

Required fields:

- reporting date and account/campaign/ad-set/ad IDs
- account currency and timezone
- attribution/action-report settings
- spend/action values as `NUMERIC`, never floating point
- impressions, reach, clicks and action counts
- full `actions` and `action_values` JSONB
- confirmed extracted link clicks, outbound clicks, landing-page views, add-to-cart,
  checkout, purchases, purchase value and leads
- source sync run and fetched/updated timestamps

Unique key: ad account + ad ID + reporting date + attribution configuration. Re-fetching
updates normalized facts while raw snapshots remain append-only.

Index reporting date and campaign/ad-set/ad plus date. Apply the backend-only access
controls from migration 005; browser/Supabase public roles must not read raw marketing
payloads.

## Metric definitions

Calculate ratios from summed numerators/denominators. Never average row-level ratios.

| Metric | Definition |
|---|---|
| Spend | Sum of Meta `spend` in account currency |
| CPM | `spend / impressions * 1000` |
| CTR | `link_clicks / impressions * 100`; label the click definition |
| CPC | `spend / link_clicks` |
| Frequency | `impressions / reach` |
| Meta purchases | Confirmed purchase action type reported by Meta |
| Meta purchase value | Confirmed purchase action value reported by Meta |
| Meta ROAS | `Meta purchase value / spend` |
| Business revenue | Sum of `orders.order_value` by order date |
| Blended MER | `business revenue / Meta spend` for the same dates |
| Spend per order | `Meta spend / business order count` |
| New-customer CAC | `Meta spend / new customers` for the same dates |

Return NULL for zero denominators. Display the account currency; do not assume INR.

Meta conversions are platform-attributed. Database orders are observed business facts.
Show these as different concepts. Until orders capture a reliable UTM/click ID and an
attribution model is approved, never claim an individual order came from a campaign,
ad set or ad. Clearly labeled date-level blended MER/CAC is allowed.

## Recommended code layout

- `apps/api/integrations/meta/client.py`: HTTP, pagination, async reports, retries.
- `apps/api/integrations/meta/parser.py`: pure action/numeric parsing.
- `apps/api/integrations/meta/sync.py`: raw landing and idempotent normalization.
- `db/import_meta_insights.py`: manual/historical sync command.
- `apps/api/marketing.py`: authenticated reports and sync status.
- `apps/web/app/marketing/`: marketing overview and drill-down UI.

Keep HTTP and parsing separate so fixtures can test parsing without a live account.

## Configuration

Example env files reserve:

- `META_AD_ACCOUNT_ID`
- `META_ACCESS_TOKEN`
- `META_GRAPH_API_VERSION`
- `META_SYNC_START_DATE`
- `META_SYNC_LOOKBACK_DAYS`
- `META_ATTRIBUTION_WINDOWS`
- `META_ACTION_REPORT_TIME`

Implemented as typed settings in `apps/api/config.py` plus `META_SYNC_TIME` (see the
settings table above). Production secrets belong in host environment variables, never
Git, logs, HTML, browser requests or any `NEXT_PUBLIC_*` variable.

## Sync and scheduling

Provide:

1. Historical backfill with explicit dates and bounded chunks.
2. Manual recent-window sync for development/recovery.
3. Daily production sync through a separate scheduler service (implemented as
   `workers/meta_sync`), not the order-processing worker loop.
4. Visible sync-run history with failure reason and last successful data date.

Recommended daily flow:

1. Determine yesterday in account timezone.
2. Re-fetch the lookback through yesterday.
3. Land all pages as raw records.
4. Normalize/upsert dimensions and daily ad facts transactionally.
5. Compare normalized spend with account control totals.
6. Mark complete only after every page/write succeeds.

Prevent overlapping runs for one account with a PostgreSQL advisory lock or equivalent.

## Admin API and UI

Authenticated endpoints:

- `GET /admin/marketing/overview?date_from=&date_to=`
- `GET /admin/marketing/campaigns?date_from=&date_to=&sort=&direction=`
- `GET /admin/marketing/campaigns/{campaign_id}` with ad-set/ad drill-down
- `GET /admin/marketing/sync-runs`
- `POST /admin/marketing/sync` for an authorized manual date range

The Marketing page should show:

- spend, impressions, reach, frequency, link clicks, CTR, CPC and CPM
- Meta purchases/value/ROAS, explicitly labeled Meta-reported
- business revenue/orders/new customers from existing tables
- blended MER, spend per order and new-customer CAC
- daily trend and sortable campaign table with drill-down
- freshness, currency, timezone and attribution labels
- an Unclassified action bucket for unknown action types

Campaign-level business-revenue attribution is separate work requiring order-side IDs.

## Tests

No test may require a real token or network request. Use redacted fixtures covering
pagination, action arrays, missing fields and restatements.

Required coverage:

- optional settings do not block normal app startup
- token remains server-side and is never logged
- malformed account/date inputs fail safely
- pagination retrieves every page once
- transient failures retry within bounds; permanent errors fail the run
- Decimal numeric parsing and absent/null fields
- unknown actions remain raw and do not fail sync
- normalized reruns are idempotent
- recent facts can be restated while raw history remains
- dimensions join by stable IDs, never names
- timezone/currency/attribution are preserved
- canonical ad-level totals do not double count
- blended metrics use `orders` and `customers`, not item joins
- admin authentication and absent-config 503
- migration repeatability in a disposable `_check` database

## Acceptance criteria

The job is complete only when:

1. A historical range imports from fixtures and from the real account only in an
   explicitly authorized environment.
2. Reruns change no normalized totals unless Meta restated results.
3. Spend, impressions, link clicks and selected results match Ads Manager for identical
   timezone, currency, dates, attribution and filters.
4. Differences are quantified and explained; money reconciles to currency precision.
5. Campaign totals reconcile to canonical ad-level facts.
6. UI shows freshness and does not present failed/stale syncs as current.
7. No token appears in DB rows, logs, exceptions, HTML, browser calls or snapshots.
8. Existing order processing, sales analytics and tests still pass.
9. Python lint/database tests/TypeScript/production build pass.
10. README, DATA_MODEL, VALIDATION and this file are updated from planned to implemented.

## Remaining work

Done: settings, migration, client/parser, sync and CLI, API, UI, scheduler, owner inputs
1-7, local backfill 2026-03-01 to 2026-09-22 with exact spend reconciliation.

1. Ads Manager spot check of results metrics (purchases, value, link clicks) on one or
   two dates with identical attribution; record in `docs/VALIDATION.md` (acceptance
   criteria 3-4).
2. Owner review of unclassified action types; name the token-failure owner.
3. Commit on `feature/meta-marketing-integration`, separately from the support-access
   work that shares the working tree.
4. Production: apply only migration 013 after comparing Supabase migration history; set
   `META_*` on the API; add an always-on `python -m workers.meta_sync` service with a
   direct/session database connection; backfill with the CLI; verify the dashboard.
5. Optional: quiet `httpx` INFO logs (they print request URLs, never the token); ad
   status enrichment; campaign-level business attribution once orders carry UTM or
   click IDs (separate design).
