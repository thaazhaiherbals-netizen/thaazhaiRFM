-- Existing installations: IF NOT EXISTS preserves the current landing table.
CREATE TABLE IF NOT EXISTS raw_order_ingestion (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system VARCHAR(30) NOT NULL,
    source_record_id VARCHAR(150),
    raw_payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processing_started_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_order_source_record
ON raw_order_ingestion(source_system, source_record_id);
CREATE INDEX IF NOT EXISTS idx_raw_order_status
ON raw_order_ingestion(status, ingested_at);
