# Railway release: business intelligence

Updated 2026-09-24; this records observations from the 2026-09-23 rollout,
not a fresh production health check.

## Git release
PR #1 merged: https://github.com/thaazhaiherbals-netizen/thaazhaiRFM/pull/1
Main SHA: cbf51789822a135b86977e126ea871d7d49dc74f
Release tip: 05915b9 on codex/release-business-intelligence.
Includes support access, Meta integration, comparisons, provisional CAC and vision docs.

## Completed
- Combined release: 141 backend tests, 11 auth tests, local production-build HTTP
  role smoke, Ruff, TypeScript and Next.js build passed.
- Production migration 013 applied transactionally; existing business data preserved.
- Production previously had no migration ledger. New schema_migrations records ONLY
  013; absence of entries 001-012 is not permission to rerun those scripts.
- Web SUPPORT_UI_TOKEN configured; existing admin/viewer/session secrets preserved.
- API/scheduler META_* configured. Scheduler uses production PostgreSQL session
  pooler port 5432, separately from the order worker.
- Meta historical backfill 2026-03-01..2026-09-22: all seven chunks completed.
- API GitHub deployment a2c0ddd5-1716-4a1e-ae9f-e9a0d1661e70 succeeded at cbf5178.
  /health/ready and /admin/performance?period=month returned 200.
- Redundant CLI API build 1b3a2bc1-2837-4feb-9259-b391743f19c2 was cancelled;
  retain the successful GitHub release.
- Scheduler connected to GitHub main, start command python -m workers.meta_sync.

## Outstanding verification
Last observed states, not current claims:
- Web 960678f8-7e13-4eac-ab77-1cd5679cce55: BUILDING.
- Order worker b3e5853e-2f86-4734-a114-cc3615803d00: BUILDING.
- Meta scheduler 74747195-adc3-4ceb-9213-2e247f011b44: QUEUED.
Confirm final deployment health, scheduler logs, live role permissions, Meta coverage
and control-spend totals, and final displayed CAC. Independent Ads Manager spot check
remains open. The local fixture-based role smoke is not live-site verification.

## Production links
Project: https://railway.com/project/af8709ae-3c58-47c7-9666-d17e9de66bf1
Web: https://thaazhai-web-production.up.railway.app
API: https://thaazhai-api-production.up.railway.app

## Rollback references
Previous successful deployments:
- API: a40a0db0-ae46-4763-a85d-661a9b785a7a
- Web: fe0a5a77-e9c6-485c-9231-7265d777594a
- Order worker: 7f433a11-7949-4de7-ae80-84c6e0d69a4e

Inspect live state before choosing a rollback. Migration 013 is additive: preserve
its tables/data when rolling back application code. Never rerun all migrations/seeds
or copy the local order snapshot into production.

## Workflow after this release
The owner established develop on 2026-09-24. Future work starts on a feature branch
from develop, merges through a PR into develop, then releases through a PR from
develop into main. Railway production follows main. This release predates that
workflow. Merged feature branches/worktrees are removed; recovery snapshots live
under .git/codex-recovery, outside active branch workflows.
