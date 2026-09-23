# Claude handoff: current state and next task

Last updated: 2026-09-23.

Start every session here. Read the repository `CLAUDE.md` first, then this file, then
the doc for the area you are touching. Treat numbers below as a recorded baseline, not
as facts that automatically remain true: re-check before relying on them.

## Repository workflow and branch separation

The earlier shared checkout contained mixed, uncommitted support and Meta work.
That checkout and its original staging state are preserved for recovery. Do not
continue feature development in it.

Independent feature worktrees were prepared from origin/main (1d42671):
- feature/meta-marketing-integration: Meta client/parser/sync, reporting UI,
  scheduler, schema and operating documentation. This branch contains Meta only.
- codex/customer-support-access: web support role, permissions and tests.
- codex/intelligence-vision: future vision and Git workflow documentation.

The current support-only shared-file change is in components.tsx. actions.ts and
globals.css contain Meta-only additions. main remains unchanged; these branches
require review and integration before deployment. See Git history for commit status.

New work must start in an isolated worktree from updated origin/main. A feature
that depends on unmerged Meta work may explicitly stack on its committed tip;
record that base and review only the dependent diff. Never carry a dirty tree
between branches, or use git add -A on the original mixed checkout.

## What is implemented

Operations and sales (committed on `main`):

- Local PostgreSQL 17 through Docker Compose; FastAPI (`apps/api`); Next.js admin UI
  (`apps/web`); PostgreSQL-backed order worker (`workers/order_processor`).
- Raw-order import, transactional normalization, product alias matching that keeps
  `PENDING` unmapped items, delivery location with provenance, processing jobs,
  retries, mapping resolution, audited order-date correction.
- Ingestion, Jobs, Mappings, Orders, Customers pages; customer follow-up history
  (migration 010); dynamic customer buckets (011) with configurable thresholds (012).
- CEO sales dashboard (yearly, rolling three-month, daily month views).
- Read-only team viewer role (`VIEWER_UI_TOKEN`); see `docs/TEAM_ACCESS.md`.

Separate feature branches (see above): customer-support role; Meta marketing.

### Meta marketing (live locally, not in production)

Full operating guide: [META_MARKETING_INTEGRATION.md](META_MARKETING_INTEGRATION.md).

- Migration `013_meta_marketing.sql` (seven RLS-restricted tables). Applied to the local
  Docker database only. **Not applied to Supabase.** Next new migration: **014**.
- Read-only Graph API client, pure parser, idempotent sync, CLI backfill, reporting
  API under `/admin/marketing/*`, `/marketing` page with campaign drill-down, and a
  separate daily scheduler (`workers/meta_sync`, compose service `meta-scheduler`).
- Live local data: the account "Thaazhai New Ad account" (INR, Asia/Kolkata),
  2026-03-01 to 2026-09-22 backfilled; first spend on 2026-04-11; 21 campaigns;
  every run's ad-level spend equals Meta's account-level control total (difference
  0.00). The scheduler syncs the previous 7 days each morning after 06:00 IST.

## Current validation baseline

- Backend: 126 tests passed in Linux Python 3.12 against a freshly created disposable
  `thaazhai_check` database. Ruff, `npm run typecheck`, `npm run build` passed.
- Local data: 1,419 raw order records, 1,418 processed, one error (source record
  `2443`, no `order_date` in the raw payload; do not invent a date).
- Evidence and details: [VALIDATION.md](VALIDATION.md).

## Next work, in priority order

1. **Separate and commit** the two uncommitted features (above). Owner decides when to
   commit and push.
2. **Ads Manager spot check** for Meta: pick one or two dates, set Ads Manager to the
   same dates and "7-day click, 1-day view", and compare spend, impressions, link
   clicks, purchases and purchase value with `/marketing`. Record differences in
   `docs/VALIDATION.md`. Spend already reconciles against the API control total.
3. **Review unclassified Meta actions** with the owner (messaging conversations,
   custom conversions such as `offsite_*_add_20_s_calls`, `onsite_web_*`). Promote
   only confirmed ones to columns via a new migration; keep the priority-list rule
   (never sum overlapping action types).
4. **Production rollout of Meta** (only after steps 1-2): compare Supabase
   `schema_migrations` with the repo, apply only migration 013; add `META_*` variables
   to the API service; add a separate always-on service running
   `python -m workers.meta_sync` with the same `META_*` and `DATABASE_URL`
   (direct/session connection); run a bounded backfill from the CLI; confirm the
   dashboard. Hosting is Railway (earlier docs say Render; the commands are the same).
5. **Zoho integration** (expenses and stock analytics), Phase 6 in
   [GROWTH_PLATFORM.md](GROWTH_PLATFORM.md). Not designed in detail yet: write a
   contract doc like `META_MARKETING_INTEGRATION.md` first (owner inputs, API scopes,
   tables, sync, metrics, tests), then follow the same slice order: settings,
   migration, fixture-tested client/parser, idempotent sync, API, UI, live check.

## Environment boundaries (unchanged, critical)

- Local: root `.env.local` + Docker PostgreSQL. Production: host variables + Supabase,
  `APP_ENV=production`. The local order data is an imported snapshot, not synced.
- Never point local commands or tests at Supabase. Never rerun all migrations/seeds
  against production; compare migration history first.
- Secrets stay server-side. Never put `ADMIN_API_TOKEN`, `META_ACCESS_TOKEN` or any
  token in Git, database rows, logs, HTML, fixtures, chat, or `NEXT_PUBLIC_*` values.
  The owner pastes tokens directly into `.env.local` or the host's variables.

## Data rules that must survive every change

- Revenue/AOV/order counts come from `orders`, never an order-item fan-out join.
- Keep unmapped items and unknown locations in analytics as explicit buckets.
- Money is PostgreSQL `NUMERIC` / Python `Decimal`; ratios are computed from summed
  parts and rounded half-up.
- Meta fact grain: one ad x one reporting date x one attribution configuration.
  Never add campaign/account-level rows to the same fact. Daily reach is not additive.
- Meta-attributed conversions are not business orders. No campaign-level revenue
  attribution until orders carry reliable UTM/click IDs.
- Join Meta dimensions by ID; names are mutable. Raw Meta payloads are append-only.
- The order worker is not the Meta scheduler.

## Validation commands

```powershell
docker compose --env-file .env.local up -d --build
docker compose --env-file .env.local exec api python -m db.migrate
.\.venv\Scripts\python -m ruff check apps/api db tests workers
.\.venv\Scripts\python -m pytest tests/test_config.py tests/test_health.py tests/test_meta_parser.py tests/test_meta_client.py tests/test_meta_schedule.py tests/test_marketing_api.py
cd apps/web; npm run typecheck; npm run build
```

Database-backed tests (native `psycopg` is blocked on this Windows machine, so run them
in Docker). Recreate the disposable database first; fixtures truncate at test start
only, so a reused `_check` database fails `test_database`:

```bash
set -a; . ./.env.local; set +a
docker compose --env-file .env.local exec -T postgres psql -U "$LOCAL_DB_USER" -d "$LOCAL_DB_NAME" -c "DROP DATABASE IF EXISTS thaazhai_check WITH (FORCE)" -c "CREATE DATABASE thaazhai_check"
MSYS_NO_PATHCONV=1 docker compose --env-file .env.local run --rm -T -v "$(pwd -W)/tests:/app/tests" -v "$(pwd -W)/pyproject.toml:/app/pyproject.toml" -v "$(pwd -W)/apps/api:/app/apps/api" -v "$(pwd -W)/workers:/app/workers" -e APP_ENV=test -e RUN_DATABASE_TESTS=1 -e ADMIN_API_TOKEN= -e META_AD_ACCOUNT_ID= -e META_ACCESS_TOKEN= -e META_GRAPH_API_VERSION= -e META_ATTRIBUTION_WINDOWS= -e DATABASE_URL="postgresql://$LOCAL_DB_USER:$LOCAL_DB_PASSWORD@postgres:5432/thaazhai_check" api python -m pytest tests -q -p no:cacheprovider
```

The blank `META_*`/`ADMIN_API_TOKEN` overrides stop real local secrets leaking into
tests. Tests use redacted fixtures and never call Meta.

## Prompt to start Claude

Continue the Thaazhai project from `docs/CLAUDE_HANDOFF.md`. First confirm the
repository state described there and help me separate and commit the uncommitted
customer-support and Meta marketing work onto their own branches. Then continue with
the next item in "Next work, in priority order". Start every feature on a new branch,
preserve the environment boundaries and data rules, run the validation commands after
each slice, and record evidence in `docs/VALIDATION.md`.
