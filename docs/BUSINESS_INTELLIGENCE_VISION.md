# Future work: business intelligence and customer action loop

Recorded: 2026-09-23.
Status: agreed direction for future work, not an implementation record or authorization
to launch customer messaging. Deliver in small, independently reviewable upgrades.

## Vision

Turn orders, customer history, marketing spend, and eventually expenses and stock
into understandable decisions for Thaazhai. The owner should see what changed,
why it deserves attention, what evidence supports it, and what action to consider.
The support team should see who needs attention today and why.

Data sync is the foundation. The full loop is:
collect events -> calculate facts -> detect changes -> recommend an action ->
record the action and outcome -> evaluate and improve the rules.

Start with deterministic calculations and explicit business rules. AI may later
explain verified metrics or summarise contact notes; it must not invent facts,
causes, customer intent, attribution, or profit.

## Existing foundation and missing pieces

At the time of this discussion:
- Orders, customers, product mappings, customer buckets/tags, configurable bucket
  thresholds, and follow-up history exist.
- Support access and Meta reporting are implemented locally, with mixed uncommitted
  work. Follow CLAUDE_HANDOFF.md before starting another feature.
- Meta has daily ad facts, reporting, historical sync and a separate scheduler.
- Local orders are an imported snapshot, not a continuously current production feed.
- Customer movement history, a managed recommendation queue, outcome evaluation,
  and the broader intelligence layer described here are future work.
- Zoho expenses and inventory are not integrated. Reliable product costs,
  refunds/returns and other costs must be established before profit claims.

Read CUSTOMER_SEGMENTATION.md, TEAM_ACCESS.md, META_MARKETING_INTEGRATION.md,
GROWTH_PLATFORM.md and CLAUDE_HANDOFF.md before implementation.

## Business questions

| Question | Insight to develop | Data or limitation |
|---|---|---|
| Is growth keeping pace with ad spend? | Comparable weekly spend, actual sales, new customers, repeat revenue and trends | Align completeness and dates across orders and Meta |
| Are customers returning? | Second-purchase rate, time to second purchase, 30/60/90-day repeat behaviour and observed revenue per customer | Compare cohorts at equal ages; incomplete imported history can misclassify a returning customer as new |
| Which products build relationships? | First-order products, repeat-associated products, product pairs and next-product sequences | Association is not causation; keep unmapped products visible |
| Where might the funnel need attention? | Changes between impressions, clicks, landing-page views, carts, checkouts and Meta purchases | Meta counts are not necessarily one matched customer journey; confirm tracking and investigate causes |
| Which campaigns need review? | Meaningful spend with weak results, deterioration, and promising but small samples | Use minimum evidence and comparable periods; no automatic budget changes |
| Who needs attention today? | Eligible callbacks, reorder candidates and at-risk repeat customers | Apply contact preferences, recent activity and duplicate prevention |
| Are sales contributing enough money? | Contribution after variable costs and advertising; later operating results | Needs agreed revenue/cost definitions, shipping, fees, discounts, returns and Zoho mappings |
| Can we fulfil demand? | Stock cover, low-stock risks and slow-moving stock | Needs reliable SKU mapping, inventory snapshots and stockout-aware demand estimates |

Meta-reported purchases must remain separate from actual business orders.
Meta spend divided by all new business customers is a blended indicator, not proof
of Meta acquisition or fully loaded CAC. Do not attribute a customer's later orders
to a campaign without reliable linking data. Revenue is not profit.

## Changing customers: retain history as well as current state

A bucket answers "where is this customer now?" The system must also explain
"what changed, when, and why?"

Keep three separate concepts:
1. Business position: purchase recency, frequency, value, product interests and bucket.
2. Contact state: latest outcome, callback due, recent contact and contact preferences.
3. Recommended action: a current, explainable suggestion subject to eligibility checks.

A high-value or at-risk classification never overrides a do-not-contact preference.
A callback date can take precedence over a generic reorder suggestion.

Illustrative journey (not fixed production thresholds):
- First order: new customer; consider product-use support.
- No repeat order after a suitable interval: possible second-purchase opportunity.
- Customer requests a callback next week: defer general outreach until then.
- Customer purchases again: update their position and invalidate an obsolete reorder task.
- Customer later becomes inactive: consider a win-back action if contact is appropriate.

### Calculation and history requirements

- Retain source events and provenance: orders, corrections, product lines and
  recorded follow-ups. Never rewrite raw source payloads to fit an insight.
- Recalculate affected customers after orders or follow-ups; also run a daily
  time-based refresh, because inactivity changes without a new event.
- Before implementation, verify which date anchors current buckets use. Choose
  explicit business timezone and as-of date semantics; a frozen local snapshot
  must not quietly produce "today" recommendations as if its feed were current.
- Record daily snapshots and/or meaningful transitions with previous/new state,
  reason, calculation time, source coverage, as-of date and rule version.
  Select the simplest storage approach in the design; both mechanisms are not
  automatically required.
- Distinguish behaviour changes from reclassification caused by an administrator
  changing bucket thresholds.
- Keep both event time and ingestion time. A Monday order imported Thursday can
  revise historical metrics; preserve what was known when a recommendation was made.
- Recompute affected periods for late orders and corrections. Make scheduled reruns
  idempotent and recoverable without duplicating transitions or recommendations.

## From buckets to a daily action queue

Buckets nominate candidates; an explicit policy decides whether an action is useful.

Example policy, with thresholds to be validated:
"Consider a reorder follow-up when the customer is beyond the product's expected
reorder interval, has not reordered, has no later callback scheduled, is contactable,
and has not been contacted too recently."

Do not assume every product or customer follows one fixed reorder cycle. Start with
a documented business rule where evidence is sparse. Show sample size and uncertainty
when deriving intervals from observed purchases.

Each proposed action should carry:
- Customer, action type, reason and supporting facts.
- Priority, due date, expiry and last eligibility check.
- Source freshness and rule version.
- Owner and state: proposed, assigned, deferred, completed, dismissed or invalidated.
- Links to contact history and any recorded outcome.

Prevent duplicate open actions for the same purpose. Recheck eligibility before a
call or message, including new purchases, another agent's recent contact, preferences
and callback dates. Record why an action was invalidated or dismissed.
Support should be able to record/defer/complete permitted customer work; configuration
and financial administration remain admin-only. Enforce permissions server-side.

Initial scope is a human-reviewed queue. Automated outbound messaging is a separate
future feature requiring channel consent, opt-out enforcement and validated policies.

## Evidence and measurement

Every insight should contain: plain-language finding, period, comparison period,
numerator/denominator, supporting data, freshness, confidence/limitations and suggested
next investigation or action. Separate observed facts from hypotheses.

Compare complete periods and equally aged cohorts. Do not compare an incomplete
month with a complete one or label unavailable data as zero. Preserve zero-spend
days that were actually synced. Show source gaps and stale calculations.

Start with a few high-value rules; avoid overwhelming staff with repeated alerts.
Measure queue completion, time to contact, recorded outcomes and subsequent purchases.
A purchase after a call does not prove the call caused it. Evaluate incremental impact
with suitable controlled comparisons when feasible, rather than promising causal uplift.

## Incremental delivery plan

Each implementation slice starts on its own feature branch after the current mixed
features are separated. Inspect the latest schema; do not reserve a migration number
in this vision document. Preserve existing behaviour until a replacement is verified.

| Slice | Deliverable | Completion evidence |
|---|---|---|
| 0. Definitions and readiness | Metric dictionary, source coverage/freshness, timezone and as-of policy; agreed initial decisions | Example calculations reconcile with source orders and Meta; stale data is explicit |
| 1. Customer movement history | Versioned state calculation and reproducible transitions/snapshots | Tests cover day rollover, new purchase, threshold change, late order and correction; reruns do not duplicate history |
| 2. Owner's overview | Weekly sales/spend, first-vs-repeat business, equally aged cohorts and product opportunities | Totals reconcile; partial periods and small samples are labelled; facts and hypotheses are separate |
| 3. Human-reviewed action queue | One or two initial rules, such as due callbacks and reorder review | Do-not-contact, future callback, recent contact, duplicate and new-order suppression work; support permissions verified |
| 4. Action feedback | Ownership, deferral, outcomes, invalidation history and evaluation | Can explain why an action existed and what followed without claiming causality |
| 5. Financial and stock enrichment | Zoho integration contract, cost mapping, stock snapshots and SKU reconciliation | Costs are not double counted; unknown mappings remain visible; metrics reconcile with source reports |
| 6. Optional advanced assistance | Natural-language explanations, carefully evaluated predictions and separately scoped automation | Answers trace to verified facts; insufficient evidence is explicit; existing access boundaries hold |

Customer movement and basic human-reviewed follow-ups can progress without Zoho once
order and contact data are trustworthy. Profit-based targeting needs financial inputs.
Automated campaign changes and outbound messaging are not part of the initial slices.

## Decisions to settle at the relevant slice

- Initial owner dashboard questions and the first two action rules.
- Order-feed completeness, historical coverage and agreed definition of a new customer.
- Business timezone, reporting date anchors and late-data revision policy.
- Product-level reorder evidence, minimum samples and fallback rules.
- Contact eligibility, cooldown periods, callback ownership and queue assignment.
- Net revenue, contribution and acquisition-cost definitions and required cost sources.
- Zoho product(s), organisation, expenses, stock sources and explicit SKU mappings.
- How the team will measure whether recommendations improve outcomes.

This document preserves the vision. It does not mean these capabilities already
exist, establish fixed thresholds, or replace the implementation contracts.
