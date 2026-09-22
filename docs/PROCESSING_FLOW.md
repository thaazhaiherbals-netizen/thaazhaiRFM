# Phase 2 processing flow

## Entry point

For an explicitly selected LOCAL raw order:

```powershell
docker compose --env-file .env.local exec api python -m db.process_order --id YOUR-RAW-UUID
```

Use the UUID in raw_order_ingestion.id, not the storefront order number.
This command writes normalized data for that one order. It does not process the
whole imported dataset. The function can later be called by the Phase 3 worker.
For an ERROR record, explicitly add --retry-error. Rerunning a completed order
repairs pending item mappings without creating a duplicate sale.

## Read the code in this order

1. db/process_order.py: reads the command argument, gets the local database engine,
   and calls process_single_order().
2. apps/api/normalization.py: pure functions transform phone/date/price values.
   A function receives input and returns a result; these functions do not write SQL.
3. apps/api/product_resolver.py: resolve_product() reads aliases and returns product
   and variant IDs. Missing/ambiguous/inactive mappings raise MappingPending.
4. apps/api/order_processing.py: controls the transaction and inserts the records.

## One order, step by step

- Open engine.begin(): commit on success, rollback if an exception escapes.
- SELECT the raw record FOR UPDATE SKIP LOCKED. Another processor cannot work on
  that record simultaneously. Missing/locked IDs return UNAVAILABLE.
- If the normalized order exists, repair only pending mappings and return its ID.
- Otherwise, process NEW, or ERROR only with explicit retry. Other states are skipped.
- Mark PROCESSING inside the transaction. This intermediate state is not visible to
  other sessions before commit; a crash rolls back the claim so it can be retried.
- Begin a savepoint: a smaller rollback boundary inside the main transaction.
- Validate order identity, date, phone, total and every line item.
- Match aliases. A catalogue problem becomes a PENDING item, not a rejected sale.
- Upsert the customer by normalized phone. Keep minimum/maximum purchase dates
  irrespective of the order in which historical records arrive.
- Insert the order and every item, retaining actual prices and raw product names.
- If those writes fail, roll back the savepoint and commit ERROR on the raw record.
- Otherwise commit the complete order with raw status PROCESSED.
- Never change raw_payload.

A lost database connection may prevent even the ERROR update; that exception
propagates to the caller and the transaction rolls back.

## Current validation rules

Only HOSTINGER is implemented. source_record_id must match payload order_id.
Dates accept April 3, 2026 or 2026-04-03. A valid Indian mobile number is required.
Quantity must be a positive integer; monetary values must be finite, nonnegative,
fit NUMERIC(12,2), and have no fractional paise. Missing unit prices are errors.
These are explicit V1 rules; other source formats need an adapter.

Existing customer contact fields are preserved on repeat purchases; only purchase
dates are updated. We do not guess which historical name/email is most current.

## Missing mappings do not hide sales

Migration 006 adds mapping_status and mapping_error to order_items and permits a
null product_id only for pending mappings. Existing items remain RESOLVED.
The order remains available to total revenue/order/customer/RFM calculations.

Future product analytics must LEFT JOIN the catalogue and include an Unmapped
products bucket. Overall revenue comes from orders.order_value, not a join that
duplicates orders per line item. Item totals and order totals can differ.

Correct a confirmed alias, then run the same order ID again to repair PENDING
items. Prices, quantities, raw_payload and order identity remain unchanged.
This supersedes the original brief's rollback-on-unknown-product rule.

## Phase boundary

Processing job APIs, automatic batches, mapping UI and dashboards are Phase 3–5.
Phase 2 supplies tested functions and a local single-order command.


## Delivery-location fields

create_normalized_order() calls normalize_delivery_location(address) in
apps/api/location.py before inserting the order. The returned dictionary supplies
city, state, country, pincode and per-field provenance to the orders INSERT.
Unknown or invalid location values stay NULL; they do not reject a sale.
Original address JSON is stored unchanged. Text case/spacing is standardized, but
city spelling variants are not merged and pincode geography is not inferred.

Migration 007 adds the columns. Existing orders can be populated locally with:

```powershell
docker compose --env-file .env.local exec api python -m db.backfill_locations
```

This reads orders.address and fills only untouched reporting fields. Running it
again preserves populated fields. It does not process more raw orders.
Open db/location_analytics.sql in pgAdmin for pincode and city revenue queries.
They retain an Unknown bucket and count each order once, including pending-product
orders. Customer counts are distinct per location, not additive across locations.
There is no location dashboard yet and no latitude/longitude geocoding.
