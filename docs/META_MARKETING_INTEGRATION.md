# Meta Marketing API integration handoff

This is the implementation-ready brief for Phase 6 marketing performance ingestion.
Give this file to the developer or coding agent responsible for the Meta integration.

**Status: designed, not implemented.** No Meta credential, API client, database table,
sync process, endpoint, or marketing page exists yet.

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

## Proposed migration 012

Create `012_meta_marketing.sql`. Never edit an applied migration.

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

Add typed settings when implementation begins. The app must still start without Meta
configuration; marketing sync endpoints return 503 when required settings are absent.
Production secrets belong in Render environment variables, never Git, logs, HTML,
browser requests or any `NEXT_PUBLIC_*` variable.

## Sync and scheduling

Provide:

1. Historical backfill with explicit dates and bounded chunks.
2. Manual recent-window sync for development/recovery.
3. Daily production sync through a separate Render cron job or explicit scheduler,
   not the order-processing worker loop.
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

## Suggested sequence

1. Add typed optional settings and validation.
2. Add migration 012 and database tests.
3. Build/test the client and pure parser with redacted fixtures.
4. Implement idempotent sync and manual CLI.
5. Add reporting endpoints and tests.
6. Add Marketing UI with freshness/error states and drill-down.
7. Confirm the eight owner inputs and save one redacted real Insights response.
8. Reconcile a small date range with Ads Manager.
9. Add production cron only after reconciliation sign-off.
10. Backfill history in bounded windows and record results in VALIDATION.

## Copyable job prompt

Implement `docs/META_MARKETING_INTEGRATION.md` end to end for this repository. Start by
recording the eight business-owner inputs and a redacted real Insights response. Build
the optional configuration, migration 012, fixture-tested Meta client/parser,
idempotent raw and normalized sync, authenticated reporting endpoints, Marketing UI,
and reconciliation workflow. Keep Meta credentials server-side, keep platform-attributed
conversions distinct from business orders, and do not schedule production sync or
backfill the live account until the small-range Ads Manager reconciliation passes.
Preserve the existing order-processing and analytics baseline and update the
documentation and validation evidence when implementation is complete.
