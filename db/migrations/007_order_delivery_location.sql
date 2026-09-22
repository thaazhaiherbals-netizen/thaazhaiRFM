-- See docs/DATA_MODEL.md. Preserve order-level delivery history and raw JSON.
ALTER TABLE orders
    ADD COLUMN delivery_city TEXT,
    ADD COLUMN delivery_state TEXT,
    ADD COLUMN delivery_country TEXT,
    ADD COLUMN delivery_pincode VARCHAR(6),
    ADD COLUMN delivery_location_sources JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE orders ADD CONSTRAINT ck_delivery_pincode
    CHECK (delivery_pincode IS NULL OR delivery_pincode ~ '^[1-9][0-9]{5}$');
CREATE INDEX idx_orders_delivery_pincode ON orders(delivery_pincode);
-- Existing rows are populated by db.backfill_locations, using the same Python
-- normalization as new orders. This migration does not reinterpret old addresses.

