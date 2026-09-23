# Data model

Migrations 001–002 preserve the supplied existing table definitions, including
zoho_item_name and zoho_item_type. Migration 003 adds customers, orders and items.
Orders are unique by ingestion ID and (source_system, source_record_id).
Historical price belongs in order_items.unit_price; no product selling price is added.
Migration 004 adds the supplied job lifecycle and counters. The runner maintains
schema_migrations with checksums.

## Access-control addition: migration 005

Supabase can expose public-schema tables through its Data API. These backend-only
tables include personal data. Migration 005 enables RLS and revokes table access
from anon/authenticated roles without adding client policies. This changes access
permissions, not rows or business schema. Existing REST clients using those roles
will lose access; review this before applying to a shared database. The backend
uses a trusted database role with the necessary permissions (database owner for
initial setup). Never put its credentials in browser code.

## Alias contract for Phase 2

Match uppercase source, normalized product name and separately normalized variant.
Decode HTML entities, trim/collapse whitespace and lowercase text. normalized_alias
stores the product name only. Treat empty/null variants identically; preserve
meaningful text. Shampoo 100 and 100 ml have separate confirmed aliases.
Inspect existing aliases against this convention before Phase 2.

Resolve active aliases/products/variants only. Reject ambiguity and variants that
belong to a different product. Do not choose an arbitrary result. Seeds preserve
existing master rows; they do not silently repair conflicts or overwrite metadata.

## Phase 2 change: preserve sales when catalogue mappings are missing

Requested behavior: valid orders must remain available to sales/customer analytics
even when a product alias is missing, ambiguous, inactive, or inconsistent.

Migration 006 makes order_items.product_id nullable and adds mapping_status
(RESOLVED or PENDING) and mapping_error. Existing items default to RESOLVED.
A check constraint requires a product for RESOLVED items and no product/variant
for PENDING items. Original item names, quantity and actual prices remain stored.

A raw record becomes PROCESSED when the complete valid order is saved, even with
PENDING items. ERROR is reserved for invalid required order data or database faults.
No product or alias is invented. Overall revenue, AOV and customer/RFM analytics
must read orders; product reports must use a LEFT JOIN and an Unmapped products
bucket to avoid losing pending item revenue. Header totals may differ from item totals.

Reprocessing an already saved order attempts to resolve only its pending mappings.
It never inserts another order, modifies prices, or changes raw_payload.
This supersedes the original all-products-must-map requirement.


## Delivery location reporting (migration 007)

Delivery locations belong to orders so a customer's address changes do not rewrite
historical sales geography. Add nullable delivery_city/state/country/pincode and
per-field delivery_location_sources JSONB. Keep orders.address and raw_payload unchanged.
Only structured source fields are used; normalize whitespace/case, not spellings.
Missing/invalid values stay NULL and reports label them Unknown. A six-digit pin is
format-valid, not verified against a postal reference. Do not infer country/state
from a pin or parse full address text speculatively. SOURCE provenance is recorded
per populated field; future verified lookup enrichment must record its own source.
Existing orders use the explicit local backfill command; it leaves already-populated
location records alone. No customer master address or coordinates are introduced.


## Customer follow-up history (migration 010)

Customer contact activity is append-only in `customer_follow_ups`. Each event records
the customer, outcome, channel, team member, server contact time, notes and an optional
next follow-up time. Customer pages derive their current status from the newest event
rather than overwriting history. The table is backend-only: RLS is enabled and direct
anon/authenticated access is revoked. Deleting a customer cascades its contact history.
Indexes support latest-status lookup and scheduled follow-ups.

## Dynamic customer segmentation (migration 011)

The backend-only `customer_analysis` view computes one mutually exclusive sales bucket
per customer from recency, order count and lifetime-value percentiles. It also produces
overlapping lifecycle/value and product-affinity tags. Segment values are dynamic and
are not copied onto the customer row. See
[CUSTOMER_SEGMENTATION.md](CUSTOMER_SEGMENTATION.md) for exact rules and sales actions.

## Meta marketing data (migration 013)

Migration 013 adds `meta_ad_accounts`, `meta_campaigns`, `meta_ad_sets`, `meta_ads`
(stable Meta IDs; names are mutable labels), `meta_insight_sync_runs` (requested range,
attribution configuration, API version, counts, normalized vs account-level control
spend, sanitized error; never the token), append-only `raw_meta_insights` and the
canonical fact `meta_ad_daily_performance` keyed by account + ad + reporting date +
attribution key. Money is `NUMERIC`. All seven tables have RLS enabled and
anon/authenticated access revoked, like migration 005.

A successful run replaces facts for its account, dates and attribution key from that
run's raw rows in one transaction, so restated or withdrawn rows are reflected while
raw history is kept. Do not add campaign/ad-set/account aggregates to the fact table:
that would double count spend. Daily `reach` is not additive across days; reports
expose its sum only as `reach_daily_sum` / average daily frequency. See
[META_MARKETING_INTEGRATION.md](META_MARKETING_INTEGRATION.md).
