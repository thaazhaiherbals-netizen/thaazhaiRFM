# Shopify → WhatsApp order notifications (Node.js)

A small Node.js service that receives Shopify order webhooks and sends the customer an
approved WhatsApp template message.

Both templates take the same **three body variables, in this order**:

| Variable | Value | Taken from the Shopify order |
|---|---|---|
| `{{1}}` | Customer first name | `customer.first_name`, else shipping, else billing first name, else "Customer" |
| `{{2}}` | Order number, e.g. `#1001` | `name` |
| `{{3}}` | Order status link | `order_status_url` (orders without one are skipped) |

Suggested template text (Meta category **Utility**; a template may not start or end
with a variable, so each ends with text):

| Shopify event | Template text |
|---|---|
| `orders/create` | Hi {{1}}, thank you for shopping with Thaazhai! Your order {{2}} is confirmed. You can check your order status here: {{3}} We will message you again when it ships. |
| `orders/fulfilled` (fully fulfilled only) | Hi {{1}}, good news! Your Thaazhai order {{2}} has been shipped. Track it here: {{3}} Thank you for shopping with us. |

When submitting each template to Meta, give sample values such as `Priya`, `#1001`,
`https://thaazhai.com/…/orders/…/authenticate?key=…`. No header or button variables.

Plain JavaScript, Node 22+, Node's built-in `http`/`crypto`/`fetch`/`node:test`, and one
dependency (`pg`). It is independent of the Python API, worker and web app.

## How it works

```
Shopify ──POST /webhooks/shopify──▶ server.js
                                     1. check HMAC signature + store domain   (shopify.js)
                                     2. receive_only → log the event, stop
                                        send         → save a row             (queue.js)
                                                         │ order_notifications table
                                     sender.js loop ◀────┘ claim one row (SKIP LOCKED)
                                        └─▶ whatsapp.js → Meta Cloud API → record result
```

| File | What it does |
|---|---|
| `src/index.js` | Entry point: reads settings, starts server (+ sender in send mode), clean shutdown |
| `src/config.js` | All environment variables in one place; refuses to start send mode half-configured |
| `src/server.js` | The three HTTP routes |
| `src/shopify.js` | Signature check; reads order id, name, number, status link, phone and opt-in |
| `src/queue.js` | PostgreSQL queries for the queue |
| `src/whatsapp.js` | Builds the template message, calls Meta, turns the response into a result |
| `src/sender.js` | Background loop that sends queued notifications |
| `src/migrate.js` | Applies only `db/migrations/016_order_notifications.sql` |

### Rules it follows

- **Only Shopify, only our store:** unsigned/wrongly signed requests get 401, other stores 403.
- **Consent:** a message is sent only when the order has the note attribute
  `whatsapp_opt_in=true` **and** an international phone (`+91…`). Otherwise the row is
  saved as `skipped` with the reason in `error`. SMS/email marketing consent does not count.
- **Exact order ids:** read from `admin_graphql_api_id`, because very large numeric ids
  lose digits in JavaScript.
- **Never twice:** one row per (shop, order, event). Shopify retries → `duplicate`.
- **Nothing lost:** if the database is down the webhook gets 503 and Shopify retries later.
- **No accidental duplicates:** if Meta times out or returns 5xx we can't know whether the
  message went out, so the row becomes `unknown` and is not retried automatically.

### Queue states (`order_notifications.state`)

| State | Meaning | Action |
|---|---|---|
| `pending` | Waiting to send (or waiting after a rate limit) | none |
| `skipped` | No opt-in, no international phone or no status link (see `error`) | none |
| `sending` | Being sent right now. Stuck here after a crash = unknown | check Meta |
| `unknown` | Timeout / Meta 5xx: may or may not have been delivered | check Meta, then requeue if not sent |
| `accepted` | Meta accepted the message (`message_id`). Not proof of delivery/read | none |
| `failed` | Meta rejected it (bad token/template/number) or rate-limited 5 times | fix settings, requeue |

Requeue one row: `UPDATE order_notifications SET state='pending', next_attempt_at=NOW() WHERE id=…;`

## Modes

`NOTIFICATION_MODE=receive_only` (default) — verifies webhooks and writes each event
(full order JSON) to the log. No database, no WhatsApp. Use it first to inspect real
Shopify data. **The log contains customer details; keep Railway log access restricted.**

`NOTIFICATION_MODE=send` — saves to PostgreSQL and sends WhatsApp messages. Startup fails
if `DATABASE_URL`, `WA_ACCESS_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_GRAPH_VERSION` or
`WA_ORDER_TEMPLATE` is missing. `WA_SHIPPED_TEMPLATE` is optional: while unset,
`orders/fulfilled` events are answered `disabled` and nothing is queued.

## Routes

| Route | Answer |
|---|---|
| `GET /health` | `{"status":"ok"}` while the process runs |
| `GET /health/ready` | receive_only: `shopify_configured` true/false. send: 503 unless sender, Shopify settings and database are OK |
| `POST /webhooks/shopify` | `logged`, `pending`, `skipped`, `duplicate`, `disabled`, `not_fully_fulfilled`, `ignored` |

## Railway setup (one service)

After the release PR is merged into `main`:

1. New service `thaazhai-notifications` in the existing Railway project → this GitHub repo,
   branch `main`, root directory `/`.
2. Variable `RAILWAY_DOCKERFILE_PATH=apps/notifications/Dockerfile`
   (the image needs `db/migrations/016…`, so it builds from the repo root).
3. Healthcheck path `/health/ready`, 1 replica, restart on failure.
4. Settings → Networking → Generate domain.
5. Variables for the first test (receive_only):

   ```
   NOTIFICATION_MODE=receive_only
   SHOPIFY_SHOP_DOMAIN=thaazhai-fn1psxft.myshopify.com
   SHOPIFY_WEBHOOK_SECRET=<from Shopify, step 6>
   ```

6. Shopify admin → Settings → Notifications → Webhooks → Create webhook:
   event **Order creation**, format JSON, URL `https://<railway-domain>/webhooks/shopify`.
   Copy the signing secret shown on that page into `SHOPIFY_WEBHOOK_SECRET`.
   (Add **Order fulfillment** too if you want to inspect that event.)
7. Test: place a test order → Railway logs show one `shopify_webhook_received` line.
   Its `notification` field shows exactly what would be sent: `customerName`,
   `orderNumber`, `statusUrl`, `recipient`, `consent`, `wouldSend` and `skipReason`
   (`no_whatsapp_opt_in`, `no_international_phone` or `no_order_status_url`).

### Switching to send mode (after templates are approved)

1. Meta: approved utility template(s) with the three body variables above, no header/button variables.
2. Shopify checkout: WhatsApp opt-in that saves note attribute `whatsapp_opt_in=true`.
3. Review `db/migrations/016_order_notifications.sql`, then once, in the Railway service shell:
   `npm run migrate` (with `APP_ENV=production` and `DATABASE_URL` set). It applies only
   016 and records it in `schema_migrations`; running it again is harmless.
4. Variables:

   ```
   NOTIFICATION_MODE=send
   APP_ENV=production            # TLS to Supabase
   DATABASE_URL=<Supabase session-pooler URL>
   WA_ACCESS_TOKEN=...
   WA_PHONE_NUMBER_ID=...
   WA_GRAPH_VERSION=v21.0        # a version your Meta app supports
   WA_ORDER_TEMPLATE=<approved template name>
   WA_TEMPLATE_LANGUAGE=en       # exact language code of the approved template
   WA_SHIPPED_TEMPLATE=<only once approved>
   ```

5. Test with your own opted-in phone: order → message arrives, row is `accepted`;
   resend the webhook from Shopify → `duplicate`; then a full fulfilment.

## Local development and tests

```powershell
cd apps/notifications
npm ci
npm test                       # unit + HTTP tests, no database needed
```

Real PostgreSQL tests (only against a throwaway database whose name ends in `_check`):

```powershell
docker run -d --rm --name notif_check_pg -e POSTGRES_PASSWORD=check -e POSTGRES_DB=notifications_check -p 55432:5432 postgres:17-alpine
$env:RUN_NOTIFICATION_DB_TESTS='1'; $env:DATABASE_URL='postgresql://postgres:check@127.0.0.1:55432/notifications_check'
node --test test/queue.db.test.js
docker stop notif_check_pg
```

Container check, from the repo root: `docker build -f apps/notifications/Dockerfile .`

## Not done yet

No Railway service, Shopify webhook, Meta template, checkout opt-in or production
migration has been set up by this code. Later upgrades: Meta delivery/read callbacks,
a team view of the queue in the admin app, and a retention policy for old rows.
