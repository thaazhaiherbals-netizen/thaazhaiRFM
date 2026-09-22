# Customer segmentation and sales actions

Customer buckets are calculated dynamically by the PostgreSQL
`customer_analysis` view from migration 011. They are not manually stored labels.
A new order can move a customer immediately, and recency changes with the current date.

## Current business signal

The 2026-09-22 local snapshot contains 1,238 customers and 1,419 orders. Only 141
customers have two or more orders, while 1,097 have purchased once. The median customer
lifetime value is INR 280, the 75th percentile is INR 560, and the 90th percentile is
INR 1,000. Increasing the second-purchase rate is therefore the primary retention
opportunity.

These numbers are a dated baseline. The UI calculates current counts and thresholds.

## Bucket rules and recommended treatment

Rules are evaluated in this order so every customer belongs to exactly one bucket.

| Bucket | Rule | Current count | Recommended sales action |
|---|---|---:|---|
| Champions | 3+ orders, at or above 90th-percentile value, purchase within 60 days | 26 | Protect, reward, ask for referrals/reviews, give early access |
| Loyal repeat | 2+ orders and purchase within 90 days | 101 | Cross-sell an adjacent product and reinforce replenishment |
| New customer | One order within 30 days | 178 | Onboard, educate and drive a relevant second purchase |
| High-value one-time | One order, at or above 75th-percentile value, within 90 days | 76 | Priority personal call/WhatsApp with a complementary offer |
| At-risk repeat | 2+ orders but no purchase within 90 days | 14 | Immediate win-back contact based on previous products |
| At-risk high-value | One high-value order but no purchase within 90 days | 71 | Personal win-back with service check and relevant incentive |
| Active one-time | Other one-order customer within 90 days | 321 | Nurture with product education and social proof |
| Dormant one-time | Other one-order customer older than 90 days | 451 | Low-cost reactivation; avoid expensive manual calls first |

Current counts sum to 1,238. Percentile thresholds adapt as the business grows, so the
high-value and VIP labels remain relative to the active customer base.

## Tags

Tags overlap and explain why a customer matters:

- Lifecycle/value: `RECENT_30D`, `FIRST_TIME_BUYER`, `REPEAT_BUYER`,
  `HIGH_VALUE`, and `VIP_VALUE`.
- Product affinity: `HAIR_COLOR`, `HAIR_CARE`, `SKIN_CARE`, `HYDROSOL`, and
  `COMBO_BUYER`.

The source product catalogue currently has blank category values, so affinity uses
explicit product-name families. When verified product categories are populated, replace
the name rules with category IDs in a new migration.

## Sales operating rhythm

1. Work Callback and Interested follow-up statuses first.
2. Then contact At-risk repeat and At-risk high-value customers.
3. Contact recent High-value one-time customers to convert the second purchase.
4. Run onboarding/education for New customers.
5. Maintain Champions and Loyal repeat customers with service, referral and cross-sell.
6. Use broadcast/low-cost campaigns for Dormant one-time customers before manual calls.

Always record each contact in the append-only follow-up history. Use the bucket to choose
the conversation, product-affinity tags to choose the relevant product, and the
follow-up status to prevent duplicate outreach.

## Technical contract

- Overall monetary metrics come from `orders`, not item joins.
- Customer segment grain is one customer.
- High value is the 75th percentile of customer lifetime value.
- VIP value is the 90th percentile.
- Recency is `CURRENT_DATE - last_order_date`.
- Product tags use distinct customer/order relationships and never affect revenue.
- The view is backend-only; public Supabase roles have no direct access.
- The authenticated summary endpoint is `GET /admin/customer-segments`.
- Customer list filtering uses `GET /customers?segment=...`.
