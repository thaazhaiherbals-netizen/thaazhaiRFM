-- Audited corrections preserve immutable source payloads.
CREATE TABLE order_corrections (
    ingestion_id UUID PRIMARY KEY REFERENCES raw_order_ingestion(id) ON DELETE CASCADE,
    order_date DATE,
    reason TEXT NOT NULL CHECK (length(trim(reason)) >= 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE order_corrections ENABLE ROW LEVEL SECURITY;
DO $$
DECLARE role_name TEXT;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('REVOKE ALL ON order_corrections FROM %I', role_name);
        END IF;
    END LOOP;
END $$;
