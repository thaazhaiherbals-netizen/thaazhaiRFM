# Project context

Render hosts Next.js (apps/web), FastAPI (apps/api), and a Python worker
(workers/order_processor). Supabase PostgreSQL is the source of truth and durable
job queue. No Redis, broker, Kubernetes, or AI layer in V1.

Order processing, worker jobs, admin authentication, operational pages and the CEO sales
dashboard are implemented locally. RFM, Shopify, WhatsApp, Meta Ads and Zoho remain
future integrations. Meta has an implementation-ready contract in
[META_MARKETING_INTEGRATION.md](META_MARKETING_INTEGRATION.md), but no Meta data or
credentials are present.

The supplied brief contains 22 products, 25 variants, and eight exact Hostinger
aliases. The complete historical mapping file was absent. Do not infer aliases.
Unknown SKUs and Zoho metadata remain NULL.

Deployment references:
https://render.com/docs/blueprint-spec
https://nextjs.org/docs/app/getting-started/installation
