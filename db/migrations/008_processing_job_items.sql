-- See docs/PROCESSING_JOBS.md. Fixed membership and atomic item progress allow restart recovery.
CREATE TABLE processing_job_items (
    job_id UUID NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    ingestion_id UUID NOT NULL REFERENCES raw_order_ingestion(id),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED')),
    error_message TEXT,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (job_id, ingestion_id)
);
CREATE INDEX idx_job_items_pending ON processing_job_items(job_id, status);
-- V1 intentionally runs one administrative job at a time.
CREATE UNIQUE INDEX uq_processing_job_active ON processing_jobs ((1))
WHERE status IN ('QUEUED', 'RUNNING');
ALTER TABLE processing_job_items ENABLE ROW LEVEL SECURITY;
DO $$
DECLARE role_name TEXT;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('REVOKE ALL ON processing_job_items FROM %I', role_name);
        END IF;
    END LOOP;
END $$;

