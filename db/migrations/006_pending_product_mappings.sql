-- Preserve valid sales even when their catalogue mapping needs manual attention.
-- See docs/DATA_MODEL.md for the requested behavior change.
ALTER TABLE order_items ALTER COLUMN product_id DROP NOT NULL;
ALTER TABLE order_items
    ADD COLUMN mapping_status VARCHAR(20) NOT NULL DEFAULT 'RESOLVED',
    ADD COLUMN mapping_error TEXT;
ALTER TABLE order_items ADD CONSTRAINT ck_order_item_mapping CHECK (
    (mapping_status = 'RESOLVED' AND product_id IS NOT NULL AND mapping_error IS NULL)
    OR
    (mapping_status = 'PENDING' AND product_id IS NULL AND variant_id IS NULL
     AND mapping_error IS NOT NULL)
);
CREATE INDEX idx_order_items_pending_mapping ON order_items(order_id)
WHERE mapping_status = 'PENDING';
