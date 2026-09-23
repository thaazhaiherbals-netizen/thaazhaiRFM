# Business performance comparisons

Status: implemented locally, 2026-09-23. Not pushed, merged, or deployed.

## Branch and review baseline

Branch: codex/business-performance-comparisons.
Worktree: C:/Raja/Thaazhai/worktrees/business-performance.
Dependency: feature/meta-marketing-integration at b912e88.
Review with: git diff feature/meta-marketing-integration...codex/business-performance-comparisons.

This is an explicit stacked feature: Meta supplies the stored reporting facts.
After Meta merges to main, rebase this feature onto updated main and rerun checks.
Customer support and intelligence-vision documentation are independent branches.
Do not develop in the original mixed checkout, preserved as codex/local-recovery.

## Behaviour

The executive dashboard now includes sales/marketing comparisons above the existing
historical reports. The new comparison selector is independent of the old year/month
selector; each preserves the other's query parameters.

- Today: current partial calendar day versus yesterday's full day; show values but
  withhold percentage verdicts. This is not a same-hour comparison.
- Yesterday: two completed adjacent days.
- This week: Monday through yesterday versus the same weekdays in the previous week.
- This month: the first N completed days versus the first N days of the previous month.
  If the previous month is shorter, cap BOTH windows at its length and show the dates.
- On Monday or the first of the month, no completed days is an explicit empty state.
- Calendar boundaries use Asia/Kolkata, matching the current business/account.
  Multi-timezone business reporting is not implemented.

Nine metrics show current/previous values, absolute and percentage changes where
valid, paired bars and definitions: recorded sales, orders, average order value,
new customers, returning-customer sales, Meta spend, sales/Meta spend, Meta spend
per new customer, and Meta-reported ROAS. The daily evidence table reconciles sales
and orders for both periods. Signals describe observations and possible investigations,
not causal claims or automatic advertising instructions.

Returning-customer sales means orders placed AFTER the customer's first purchase DATE.
A second purchase on the same first-purchase day is excluded from this metric.
Recorded sales use orders.order_value; these are not net revenue or profit.
New customers are first purchasers in the available history, which may be incomplete.

## Data guards

GET /admin/performance?period=today|yesterday|week|month requires backend admin bearer
authentication. The web's existing server-side access helper mediates admin/viewer reads.
No sync, schema change, order mutation or Meta API request is triggered by this report.

Meta successful-run coverage distinguishes actual zero spend from missing dates.
An incompletely covered period has unavailable spend, Meta ROAS and blended ratios.
Cross-currency sales/spend ratios are withheld unless the Meta account currency is INR.
Zero denominators produce unavailable ratios. Zero prior values never produce infinity
or a made-up 100% increase.

Order ingestion does not yet expose a reliable completeness watermark. The dashboard
labels coverage unverified, but does not discard calculable metrics just because the
last recorded order precedes the period end. Sales changes, CAC and MER use the available
order records, marked provisional when this date gap exists. Insight text avoids
treating those provisional changes as confirmed business trends.

CAC is Meta spend divided by actual new customers in order history, never Meta purchases.
Zero actual new customers produces an undefined CAC with an explicit card explanation.
Missing Meta coverage or currency mismatch still prevents cross-source ratios. Today
remains partial and has no percentage verdict. The CAC card shows two decimal places
and its spend / customer-count calculation.

Fix branch: codex/fix-available-records-cac, based on dashboard commit fe4449e.
Fix worktree: C:/Raja/Thaazhai/worktrees/available-records-cac.
Review the fix against codex/business-performance-comparisons.
The preview on port 3001 now runs this fix; the original feature branch stays unchanged.

Local regression baseline: September monthly spend 58377.12 / 127 actual new customers
= 459.66. Meta reported 183 purchases, which is intentionally not used as the denominator.
A week with zero recorded new customers has no calculable CAC.

## Validation

- 14 focused pytest cases passed (including available-record CAC regressions): completed weekday matching, empty periods, leap
  years, month-length/year boundaries, partial today, zero/missing baselines, Meta
  coverage, currency mismatch, ratio denominators, provisional order data, auth and input validation.
- Ruff passed for changed Python files; Next.js production build and TypeScript passed.
- Read-only local API checks: all four modes returned 200; daily sales and orders
  reconciled to their summaries; anonymous access rejected; missing Meta spend is null.
- Production-build HTTP checks on port 3001: all four tabs rendered; provisional-record
  calculations held; viewer reads worked and viewer follow-up writes were denied.
- No browser screenshot/responsive visual inspection was performed.
- Separate dependency checks during Git cleanup: support auth 11 passed; Meta backend
  non-database tests 55 passed; both worktrees passed TypeScript. The full 126-test
  database suite in Claude's earlier record was not rerun during this feature.

## Local preview

Web: http://localhost:3001 (existing admin/viewer login codes).
API: http://127.0.0.1:8001, container thaazhai-performance-preview.
The API reads the local Docker PostgreSQL database; production is untouched.
The preview has its own ignored web environment and dependency installation.
The original app on port 3000 remains attached to the recovery checkout.
