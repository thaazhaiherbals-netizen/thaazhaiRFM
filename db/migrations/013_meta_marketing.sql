-- See docs/META_MARKETING_INTEGRATION.md. Read-only Meta Ads performance.
-- Canonical fact grain: one ad x one reporting date x one attribution configuration.
-- Dimensions join by stable Meta IDs; names are mutable labels.
CREATE TABLE meta_ad_accounts (
    ad_account_id TEXT PRIMARY KEY CHECK (ad_account_id ~ '^[0-9]+$'),
    name TEXT,
    currency CHAR(3),
    timezone_name TEXT,
    timezone_offset_hours_utc NUMERIC(5,2),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_metadata JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE TABLE meta_campaigns (
    campaign_id TEXT PRIMARY KEY,
    ad_account_id TEXT NOT NULL REFERENCES meta_ad_accounts(ad_account_id),
    name TEXT,
    status TEXT,
    objective TEXT,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_metadata JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE TABLE meta_ad_sets (
    ad_set_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES meta_campaigns(campaign_id),
    ad_account_id TEXT NOT NULL REFERENCES meta_ad_accounts(ad_account_id),
    name TEXT,
    status TEXT,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_metadata JSONB NOT NULL DEFAULT '{}'::JSONB
);

CREATE TABLE meta_ads (
    ad_id TEXT PRIMARY KEY,
    ad_set_id TEXT NOT NULL REFERENCES meta_ad_sets(ad_set_id),
    campaign_id TEXT NOT NULL REFERENCES meta_campaigns(campaign_id),
    ad_account_id TEXT NOT NULL REFERENCES meta_ad_accounts(ad_account_id),
    name TEXT,
    status TEXT,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_metadata JSONB NOT NULL DEFAULT '{}'::JSONB
);

-- Never store the access token or authorization header here.
CREATE TABLE meta_insight_sync_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ad_account_id TEXT NOT NULL CHECK (ad_account_id ~ '^[0-9]+$'),
    trigger VARCHAR(20) NOT NULL CHECK (trigger IN ('MANUAL', 'SCHEDULED', 'BACKFILL')),
    date_from DATE NOT NULL,
    date_to DATE NOT NULL,
    level VARCHAR(20) NOT NULL DEFAULT 'ad' CHECK (level = 'ad'),
    fields TEXT[] NOT NULL,
    breakdowns TEXT[] NOT NULL DEFAULT '{}',
    attribution_windows TEXT[] NOT NULL,
    action_report_time VARCHAR(20) NOT NULL
        CHECK (action_report_time IN ('impression', 'conversion', 'mixed')),
    attribution_key TEXT NOT NULL,
    api_version TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    page_count INTEGER NOT NULL DEFAULT 0 CHECK (page_count >= 0),
    row_count INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    normalized_spend NUMERIC(14,2),
    control_spend NUMERIC(14,2),
    error_summary TEXT,
    usage_headers JSONB NOT NULL DEFAULT '{}'::JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    CHECK (date_to >= date_from)
);
CREATE INDEX ix_meta_sync_runs_account_started
ON meta_insight_sync_runs(ad_account_id, started_at DESC);

-- Append-only proof of what Meta returned; dashboards read normalized facts instead.
CREATE TABLE raw_meta_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_run_id UUID NOT NULL REFERENCES meta_insight_sync_runs(id),
    reporting_date DATE NOT NULL,
    ad_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (sync_run_id, payload_hash)
);
CREATE INDEX ix_raw_meta_insights_ad_date ON raw_meta_insights(ad_id, reporting_date);

CREATE TABLE meta_ad_daily_performance (
    ad_account_id TEXT NOT NULL REFERENCES meta_ad_accounts(ad_account_id),
    campaign_id TEXT NOT NULL REFERENCES meta_campaigns(campaign_id),
    ad_set_id TEXT NOT NULL REFERENCES meta_ad_sets(ad_set_id),
    ad_id TEXT NOT NULL REFERENCES meta_ads(ad_id),
    reporting_date DATE NOT NULL,
    attribution_key TEXT NOT NULL,
    attribution_windows TEXT[] NOT NULL,
    action_report_time VARCHAR(20) NOT NULL,
    currency CHAR(3),
    timezone_name TEXT,
    spend NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (spend >= 0),
    impressions BIGINT NOT NULL DEFAULT 0 CHECK (impressions >= 0),
    reach BIGINT CHECK (reach >= 0),
    clicks BIGINT NOT NULL DEFAULT 0 CHECK (clicks >= 0),
    link_clicks BIGINT NOT NULL DEFAULT 0,
    outbound_clicks BIGINT NOT NULL DEFAULT 0,
    landing_page_views BIGINT NOT NULL DEFAULT 0,
    add_to_cart NUMERIC(14,2) NOT NULL DEFAULT 0,
    checkouts_initiated NUMERIC(14,2) NOT NULL DEFAULT 0,
    purchases NUMERIC(14,2) NOT NULL DEFAULT 0,
    purchase_value NUMERIC(14,2) NOT NULL DEFAULT 0,
    leads NUMERIC(14,2) NOT NULL DEFAULT 0,
    actions JSONB NOT NULL DEFAULT '[]'::JSONB,
    action_values JSONB NOT NULL DEFAULT '[]'::JSONB,
    unclassified_action_types TEXT[] NOT NULL DEFAULT '{}',
    source_sync_run_id UUID NOT NULL REFERENCES meta_insight_sync_runs(id),
    fetched_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ad_account_id, ad_id, reporting_date, attribution_key)
);
CREATE INDEX ix_meta_perf_date ON meta_ad_daily_performance(reporting_date);
CREATE INDEX ix_meta_perf_campaign_date ON meta_ad_daily_performance(campaign_id, reporting_date);
CREATE INDEX ix_meta_perf_ad_set_date ON meta_ad_daily_performance(ad_set_id, reporting_date);
CREATE INDEX ix_meta_perf_ad_date ON meta_ad_daily_performance(ad_id, reporting_date);

ALTER TABLE meta_ad_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_ad_sets ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_ads ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_insight_sync_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw_meta_insights ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_ad_daily_performance ENABLE ROW LEVEL SECURITY;
DO $$
DECLARE role_name TEXT;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format(
                'REVOKE ALL ON meta_ad_accounts, meta_campaigns, meta_ad_sets, meta_ads, '
                'meta_insight_sync_runs, raw_meta_insights, meta_ad_daily_performance FROM %I',
                role_name
            );
        END IF;
    END LOOP;
END $$;
