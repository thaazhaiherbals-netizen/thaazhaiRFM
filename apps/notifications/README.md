# Shopify → WhatsApp order notifications (Node.js)

A small Node.js service that receives Shopify order webhooks and sends the customer an
approved WhatsApp template message.

Both templates have the same shape: **two body variables** and, as the **first button**,
a "Track order" URL button whose link ends in one variable:

| Variable | Value | Taken from the Shopify order |
|---|---|---|
| Body `{{1}}` | Customer first name | shipping first name, else first word of shipping name, else customer/billing first name, else "Customer" |
| Body `{{2}}` | Order number, e.g. `#1001` | `name` |
| Button `{{1}}` | End of the order status link | `order_status_url` after `WA_STATUS_BUTTON_BASE_URL` (orders whose link does not start with it are skipped) |

### Order confirmation template (`orders/create`)

Create in WhatsApp Manager → Message templates:

- **Name** `order_confirmation` (→ `WA_ORDER_TEMPLATE`), **category** Utility,
  **language** English `en` (→ `WA_TEMPLATE_LANGUAGE`).
- **Header**: **Image**. Upload the brand logo as the sample. The upload is only for
  review: every message sends the image from `WA_HEADER_IMAGE_URL`, so keep that set
  (currently the Shopify Files link to `THAAZHAI_LOGO.jpg`).
- **Body** (a template may not start or end with a variable):

  ```
  *Order confirmed* ✅

  Hi {{1}}, thank you for shopping with Thaazhai! 🌿

  Your order {{2}} has been placed successfully. We will update you on WhatsApp as soon as it is shipped.

  Tap "Track order" below to view your order details and status anytime.

  This is an automated message and replies are not monitored. For any help, please tap "Call us".
  ```

- **Footer**: `Thaazhai – Natural Herbal Care`
- **Buttons** (Call to action), in this order:
  1. **Visit website**, text `Track order`, URL type **Dynamic**,
     URL `https://thaazhai.com/81506271484/orders/{{1}}`
  2. **Call phone number**, text `Call us`, the support number (static, no variable).
- **Samples**: body `Bharathi`, `#1021`; button
  `77ec8fdb5ebd8702b73cfabde46b08e3/authenticate?key=sample`.

The button URL before `{{1}}` must equal `WA_STATUS_BUTTON_BASE_URL` (default
`https://thaazhai.com/81506271484/orders/`). If the store domain changes, update both.

### Shipped template (`orders/fulfilled`, fully fulfilled only — later)

Same shape: body `Hi {{1}}, good news! Your Thaazhai order {{2}} has been shipped. …`
with the same `Track order` button first.

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
| `src/shopify.js` | Signature check; reads order id, name, number, status link and phone |
| `src/queue.js` | PostgreSQL queries for the queue |
| `src/whatsapp.js` | Builds the template message, calls Meta, turns the response into a result |
| `src/sender.js` | Background loop that sends queued notifications |
| `src/migrate.js` | Applies only `db/migrations/016_order_notifications.sql` |

### Rules it follows

- **Only Shopify, only our store:** unsigned/wrongly signed requests get 401, other stores 403.
- **Website orders only:** `source_name` must be `web`; POS/draft/app orders are skipped.
- **Name:** shipping address first name, else first word of its full name, then the
  customer/billing first name, else "Customer".
- **Phone:** the first valid number from `phone` (checkout contact), `shipping_address`,
  `billing_address`, then `customer.default_address`; blank or invalid numbers fall
  through to the next. Shopify stores address phones as typed (`9243023483`), so an
  Indian 10-digit mobile gets the `91` prefix (for `phone`, the shipping/billing country
  is used); any other number without a country code is skipped, never guessed.
- **Consent:** no separate WhatsApp opt-in. The Shopify checkout phone field will state
  that order updates are sent to that number, so giving the number is the consent.
  Orders without a valid phone are saved as `skipped` with the reason in `error`.
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
| `skipped` | Not a website order, no valid phone or unusable status link (see `error`) | none |
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
   Its `notification` field shows exactly what would be sent: `source`, `customerName`,
   `orderNumber`, `statusUrl`, `recipient`, `phoneSource`, `buttonPath`, `wouldSend` and
   `skipReason` (`not_website_order`, `no_valid_phone`, `no_order_status_url` or
   `unexpected_order_status_url`).

### Switching to send mode (after templates are approved)

1. Meta: approved utility template(s) exactly as described at the top (two body variables,
   `Track order` dynamic URL button first). The sending number must be connected to the
   WhatsApp Cloud API (listed under API phone numbers in WhatsApp Manager).
2. Shopify checkout: phone field text saying order updates are sent to this number on WhatsApp.
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
   WA_HEADER_IMAGE_URL=https://cdn.shopify.com/s/files/1/0815/0627/1484/files/THAAZHAI_LOGO.jpg?v=1791356834
   WA_STATUS_BUTTON_BASE_URL=https://thaazhai.com/81506271484/orders/   # optional, this is the default
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

No Railway service, Shopify webhook, Meta template, checkout phone consent text or production
migration has been set up by this code. Later upgrades: Meta delivery/read callbacks,
a team view of the queue in the admin app, and a retention policy for old rows.
