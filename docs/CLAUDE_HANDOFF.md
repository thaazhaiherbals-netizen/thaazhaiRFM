# Claude handoff: merged release and next work

Updated 2026-09-24. This supersedes the earlier uncommitted-feature handoff.
Read CLAUDE.md and AGENTS.md, then verify Git and live service status before acting.

## Repository state: the release is already merged

GitHub main was verified at cbf51789822a135b86977e126ea871d7d49dc74f.
PR #1: https://github.com/thaazhaiherbals-netizen/thaazhaiRFM/pull/1
Merged 2026-09-23 from codex/release-business-intelligence (tip 05915b9).

Included in main:
- Customer-support login and customer-scoped permissions (ab89650).
- Meta read-only integration, reports, backfill, migration 013 and daily scheduler
  (ce94212, b912e88).
- Sales/marketing day, week and month comparisons (fe4449e).
- Available-record CAC with provisional-data labels (d3839fc).
- Business intelligence vision and Git workflow documentation (5cb6e11).

Do not separate, recommit or merge these features again. Old feature commits remain in main history; merged branch names can be removed.

## Working branches and cleanup

The owner has established develop as the integration branch. The required path is:
feature/fix branch from origin/develop -> PR to develop -> PR develop to main ->
Railway production deployment. No direct feature-to-main releases.

Keep develop and main as permanent branches. Delete merged feature branches and
temporary worktrees after verifying inclusion. The original project folder is
returned to a clean, updated main checkout. Recovery snapshots are kept under
.git/codex-recovery; they are backups, not active development branches. Never
reapply old recovery files wholesale: they contain pre-fix code and outdated docs.

Before every new feature, fetch origin, ensure a clean working tree, and create a
focused codex/ branch from origin/develop. Use temporary worktrees only when needed
for concurrent work and remove them when done. See AGENTS.md.

## Production: verified facts versus pending checks

Production is Railway with Supabase PostgreSQL, not Render.
See RAILWAY_RELEASE.md for deployment IDs and outstanding verification.

Verified during the 2026-09-23 rollout:
- Only additive migration 013 was applied in a transaction.
- Existing business tables had no schema_migrations ledger. A ledger was created
  recording 013 only. Missing 001-012 ledger entries do NOT mean their SQL is absent:
  never run the full migration runner or seeds blindly against production.
- Meta configuration was set on API and the separate scheduler.
- A distinct SUPPORT_UI_TOKEN was set on web; admin/viewer credentials were preserved.
- Historical Meta import 2026-03-01 through 2026-09-22 completed all seven chunks.
- The GitHub API deployment of cbf5178 succeeded; /health/ready and
  /admin/performance?period=month returned HTTP 200.
- PR merge triggered web and order-worker builds. The new thaazhai-meta-sync
  service was connected to GitHub main with python -m workers.meta_sync.

Not yet verified at the end of that session:
- Final success of web, order-worker and Meta scheduler deployments.
- Live admin/viewer/support permission smoke checks.
- Final production Meta coverage/control-spend reconciliation and displayed CAC
  after the completed historical import.
- Independent Ads Manager spot check using matching dates/attribution.

Do not infer these checks passed from the merge or the local tests. Inspect current
Railway status first; do not automatically redeploy, recreate services or reimport history.

## Validation baseline

The combined release passed 141 backend tests on a new disposable local PostgreSQL
database, 11 web auth tests, Ruff, TypeScript and Next.js production build.
The production-build HTTP role smoke ran LOCALLY against fixtures, not the live site.
Local imported order history is a snapshot and is not production's current data.

## Business rules

- Actual sales/orders/new customers come from business order records, never Meta purchases.
- Meta spend / actual new customers is a blended acquisition indicator, not fully
  loaded or individually attributed CAC. Zero customers means unavailable, not zero CAC.
- Show calculable ratios on available records with provisional labels when order
  coverage is uncertain. Incomplete Meta coverage still withholds affected ratios.
- Compare matching periods; respect Asia/Kolkata dates and partial-day limitations.
- Preserve NUMERIC/Decimal money, idempotency, source IDs and explicit unknown buckets.
- Keep Meta dimensions joined by ID; do not sum overlapping action types or daily reach.
- The order worker and Meta scheduler remain separate.
- Secrets stay server-side and out of Git, logs, chat, fixtures and NEXT_PUBLIC variables.
- Tests use disposable local *_check databases, never production.
- Production changes require explicit scope, schema inspection and targeted operations.
- Add migration 014 or later for new schema changes; do not edit applied 013.

## Next business direction: Zoho orders as source of truth

The business says website and WhatsApp orders are already maintained in Zoho.
The requested direction is to pull complete orders/customers from Zoho into the
dashboard, avoid duplicate entry, and combine actual sales with Meta spend.

This is a request/design direction, NOT implemented functionality.
The Zoho product, organization, access and actual record workflow are not identified.
Ask for the app name/browser address (never ask for secrets in chat).
Do not assume Books versus Inventory, or treat sales orders and invoices as separate sales.

Before cutover:
1. Define qualifying sales, order/invoice relationships, statuses, refunds, taxes,
   shipping, channel identity and historical customer matching.
2. Design a read-only connector with stable source IDs, repeatable updates,
   pagination, incremental sync, cancellation/refund handling and visible freshness.
3. Reconcile history against existing orders so imports do not duplicate sales.
4. Validate daily totals and first-purchase history with the business before switching
   reporting and retiring duplicate entry/import flows.
5. Add expenses/stock analytics later when source data and cost definitions are agreed.

The existing dashboard, Meta sync and comparison work remain useful.
Ad spend / sales is advertising cost-to-sales; profit needs additional cost data.
See BUSINESS_INTELLIGENCE_VISION.md for the broader phased roadmap.

## Prompt to resume Claude

Read CLAUDE.md, AGENTS.md, docs/CLAUDE_HANDOFF.md and docs/RAILWAY_RELEASE.md.
The Meta/support/comparison/CAC release is already merged in main through PR #1.
Verify current Git and Railway state, finish outstanding release checks, and use
a clean feature branch from origin/develop for new work. Open feature PRs into
develop, then release via a develop-to-main PR. Do not resurrect recovery branches.
For Zoho, first identify the actual app and records and design a reconciled,
read-only order source integration; do not implement based on an assumed product.
