-- Append-only customer contact history for coordinated team follow-up.
CREATE TABLE customer_follow_ups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL CHECK (status IN (
        'CONTACTED', 'NO_ANSWER', 'CALLBACK', 'INTERESTED',
        'NOT_INTERESTED', 'DO_NOT_CONTACT'
    )),
    channel VARCHAR(20) NOT NULL CHECK (channel IN (
        'CALL', 'WHATSAPP', 'EMAIL', 'OTHER'
    )),
    contacted_by VARCHAR(100) NOT NULL CHECK (length(trim(contacted_by)) >= 2),
    notes TEXT CHECK (notes IS NULL OR length(notes) <= 1000),
    contacted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    next_follow_up_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_customer_follow_ups_customer_time
ON customer_follow_ups(customer_id, contacted_at DESC, id DESC);

CREATE INDEX ix_customer_follow_ups_next_due
ON customer_follow_ups(next_follow_up_at)
WHERE next_follow_up_at IS NOT NULL;

ALTER TABLE customer_follow_ups ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE role_name TEXT;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('REVOKE ALL ON customer_follow_ups FROM %I', role_name);
        END IF;
    END LOOP;
END $$;
