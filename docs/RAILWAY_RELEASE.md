# Railway release: business intelligence

Release branch: codex/release-business-intelligence.
Prepared 2026-09-23. Production deployment has NOT happened yet.

## Included
- Customer-support token and customer-scoped permissions.
- Meta read-only reporting, migration 013, backfill CLI and daily scheduler.
- Sales/marketing day, week and month comparisons.
- CAC from actual new customers in orders, with provisional-data labels.
- Intelligence vision and Git workflow documentation.

## Verification on the combined release
- 141 backend tests passed in Docker against a new disposable local *_check database.
- 11 web authentication tests passed.
- Production HTTP smoke passed for admin, viewer and support roles.
- Ruff, TypeScript and Next.js production build passed.
- No production database changes, credential changes or deploys have been performed.

## Deployment order
1. Authenticate Railway CLI and identify the existing production project/services.
2. Inspect existing deployment settings, environment variable NAMES (do not expose values),
   production schema_migrations and current service health.
3. Compare migration checksums and actual schema. Apply only verified missing migrations;
   migration 013 is the expected addition. Do not rerun seeds or blindly apply earlier SQL.
4. Preserve existing admin/viewer/session credentials. Configure a distinct SUPPORT_UI_TOKEN
   on web only; configure META_* on API and scheduler only. Keep tokens out of Git and logs.
5. Deploy API and verify readiness/reports, then web and all three roles.
6. Configure the separate Meta scheduler (python -m workers.meta_sync) with a PostgreSQL
   direct/session connection and production settings. Do not repurpose the order worker.
7. Run the agreed bounded historical Meta backfill into production, reconcile sync spend,
   and verify campaign and business comparison pages. Do not copy the local order snapshot.
8. Record service URLs, release SHA, applied migrations, deployment IDs and verification.
9. Merge through the release PR in coordination with Railway's actual Git auto-deploy setup.

The original mixed checkout stays preserved on codex/local-recovery. Development
continues only in clean feature worktrees.

## Rollback
Capture the currently deployed revision/IDs before deploy. Revert application deployments
to those revisions if health checks fail. Migration 013 is additive; preserve its tables
and imported data when rolling back application code rather than dropping data.
