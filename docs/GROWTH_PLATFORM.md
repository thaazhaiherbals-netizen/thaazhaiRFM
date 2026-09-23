# Growth platform (Phases 6-10, planning)

This is a planning document, not an implementation record. **Status 2026-09-23:** the
Meta Ads half of Layer 1 is built (see
[META_MARKETING_INTEGRATION.md](META_MARKETING_INTEGRATION.md)); everything else here,
including Zoho, is not built. It exists so the founders and future contributors share one picture of
where Phases 6-10 are headed before any schema or integration work starts.

## The problem being solved

The founders currently manage money and sales without a consolidated view. Sales
data exists in this system; spend, expenses and cart abandonment do not. The goal
is one operational board answering, with real numbers: is the business growing,
and is it bleeding money.

## Layers, in build order

The order matters. Each layer depends on the one before it being trustworthy.
Acting on customers (layer 4) using segments built on incomplete financial data
(layer 1) produces wrong actions, not just missing ones.

### Layer 1 — Financial truth (Meta ad spend + Zoho expenses + existing sales)

Answers: is the business bleeding, and where does the money go.

- Meta Marketing API supplies daily ad spend, campaign/ad-set/ad performance,
  live and historical, once a Business/ad account with API access exists.
- Zoho supplies business expenses (COGS, opex, payroll, fees) — expense
  categories are not yet mapped with the founders. This must happen before
  ingestion design, not during it: the categories decide the schema, not the
  other way round.
- Combined with existing `orders.order_value`, this produces gross/contribution
  margin, not just revenue growth. Revenue-only reporting cannot answer whether
  the business is bleeding; this layer is what makes that question answerable.
- Read-only, same ingestion discipline as `raw_order_ingestion`: land raw
  responses, normalize into reporting tables, never invent a missing category
  or backfill a number that wasn't reported.

Meta: built and running locally against the live account; production rollout
pending ([META_MARKETING_INTEGRATION.md](META_MARKETING_INTEGRATION.md)).

Zoho (next): requested scope is **expenses and stock-based analytics**. Before any
schema work, write `docs/ZOHO_INTEGRATION.md` in the same shape as the Meta contract,
settling first:

1. Which Zoho product(s): Books (expenses, bills, vendor payments) and/or Inventory
   (items, stock on hand, warehouses, adjustments); organization ID and data centre
   (.in / .com), since API hosts differ by region.
2. OAuth: a Zoho API console client with read-only scopes and a refresh token kept
   server-side like the Meta token; access tokens are short-lived and refreshed.
3. Expense category mapping to COGS / marketing / opex / payroll / fees (owner:
   founders). Categories decide the schema, not the other way round.
4. Stock: how Zoho item/SKU IDs map to `products`/`product_variants` (never guess;
   unmapped items stay visible, like `PENDING` order items), and whether stock is
   snapshotted daily for trend analytics (stock-outs, days of cover, sell-through).
5. History start date, sync time and rate limits.

Then follow the Meta slice order: optional settings, migration, fixture-tested client
and parser, append-only raw landing plus idempotent normalization, CLI and scheduler,
reporting API, UI, live reconciliation against Zoho reports.

### Layer 2 — Funnel efficiency (ad spend vs. orders vs. new customers vs. abandoned carts)

Answers: is the spend converting.

- Requires Shopify abandoned-cart data (see the Shopify migration below) joined
  by date against layer 1's daily spend and this system's existing daily
  orders/new-customer counts.
- Still read-only. No attribution to individual campaigns yet — that needs a
  conversion signal (UTM/click ID/Conversions API) this system does not
  currently capture anywhere in the order pipeline, and is a separate decision
  from building this layer.

### Layer 3 — Customer intelligence (RFM, segmentation)

Answers: who matters, who is slipping away.

- Recency/frequency/monetary inputs already exist per customer in the current
  schema (`customers`, `orders`). This layer adds the scoring and bucketing,
  not new source data.
- Still passive: produces segments, does not act on them.
- This is the existing "Phase 5: Analytics and RFM" item in the main roadmap;
  layers 1-2 are new work that sits alongside it, not a replacement for it.

### Layer 4 — Retention action loop (WhatsApp cross-sell/upsell, discounts, calls, feedback)

Answers: what do we do about it.

- Acts on layer 3's segments: WhatsApp messages, discount offers, calls,
  feedback collection.
- This is a different risk category from layers 1-3. Layers 1-3 are about data
  correctness — get the numbers right. Layer 4 is about acting on real
  customers — get the targeting, consent and compliance right. A wrong number
  in a dashboard is a bug; a wrong discount sent to the wrong segment, or a
  message sent without consent, reaches a real customer.
- WhatsApp Business API requires approved message templates, respects a
  24-hour customer-service session window outside of which only pre-approved
  templates can be sent, and needs explicit opt-in tracking. This system does
  not yet track customer consent/opt-in anywhere; that has to exist before any
  outbound message is sent, following the same provenance discipline as
  `delivery_location_sources` (migration 007) — record why a customer is
  contactable, not just that they once ordered.
- Do not build this layer until layers 1-3 exist and are trusted.

### Layer 5 — AI prompt layer

Answers: let someone ask a question in plain language and get a real answer.

- Sits on top of whatever of layers 1-4 exists; gets meaningfully more useful
  as more layers land, and is of limited value before layer 1 exists.
- Should query a curated set of precomputed metrics/views, not raw tables or
  free-form SQL against production data — same reasoning as the rest of this
  system's defensive posture around raw data.

## Shopify migration (cart abandonment)

Moving to Shopify adds a funnel dimension nothing here currently tracks:
started-but-not-completed checkouts. Treat it as a new raw ingestion source,
same pattern as `raw_order_ingestion` for Hostinger — land the raw webhook
payload, normalize separately, never infer a reason for abandonment that
wasn't reported.

## Relationship to the existing roadmap

The main roadmap in [README.md](../README.md) already lists Phase 5 as
"Analytics and RFM" and names Shopify, WhatsApp, Meta Ads and Zoho as future
integrations in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md). This document is
where those integrations get a concrete sequence and rationale once the
founders are ready to commit to build order. Nothing here changes what's
already implemented (Phases 1-3) or in progress.
