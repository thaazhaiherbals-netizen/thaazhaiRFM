-- WhatsApp order notification queue used by apps/notifications (Node.js service).
-- Backend-only: holds customer phone numbers, so RLS blocks Supabase REST roles.
CREATE TABLE order_notifications (
    id BIGSERIAL PRIMARY KEY,
    shop TEXT NOT NULL,
    order_id TEXT NOT NULL,
    order_name TEXT NOT NULL,          -- e.g. #1001 (template variable 2)
    customer_name TEXT NOT NULL,       -- first name (template variable 1)
    order_status_url TEXT,             -- Shopify order status page (template variable 3)
    topic TEXT NOT NULL CHECK (topic IN ('orders/create', 'orders/fulfilled')),
    webhook_id TEXT NOT NULL,
    recipient TEXT,
    -- pending: waiting to send | skipped: no opt-in or no international phone
    -- sending: claimed by the sender right now (a row stuck here after a crash = unknown)
    -- unknown: timeout/Meta 5xx, may or may not have been sent; check Meta before requeuing
    -- accepted: Meta accepted the message | failed: Meta rejected it
    state TEXT NOT NULL CHECK (
        state IN ('pending', 'skipped', 'sending', 'unknown', 'accepted', 'failed')
    ),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    message_id TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- One message per order and event, however many times Shopify retries the webhook.
    UNIQUE (shop, order_id, topic)
);

CREATE INDEX order_notifications_due ON order_notifications (next_attempt_at, id)
    WHERE state = 'pending';

ALTER TABLE order_notifications ENABLE ROW LEVEL SECURITY;
