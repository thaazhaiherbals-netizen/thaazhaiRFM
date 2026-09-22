-- Configurable customer bucket thresholds and richer call outcomes.
CREATE TABLE customer_segment_settings (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    new_customer_days INTEGER NOT NULL DEFAULT 30
        CHECK (new_customer_days BETWEEN 1 AND 89),
    active_customer_days INTEGER NOT NULL DEFAULT 90
        CHECK (active_customer_days BETWEEN 30 AND 365),
    champion_recency_days INTEGER NOT NULL DEFAULT 60
        CHECK (champion_recency_days BETWEEN 1 AND 365),
    champion_min_orders INTEGER NOT NULL DEFAULT 3
        CHECK (champion_min_orders BETWEEN 3 AND 20),
    high_value_percentile NUMERIC(4,3) NOT NULL DEFAULT 0.750
        CHECK (high_value_percentile BETWEEN 0.500 AND 0.950),
    vip_value_percentile NUMERIC(4,3) NOT NULL DEFAULT 0.900
        CHECK (vip_value_percentile BETWEEN 0.600 AND 0.990),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (new_customer_days < active_customer_days),
    CHECK (high_value_percentile < vip_value_percentile)
);

INSERT INTO customer_segment_settings (singleton) VALUES (TRUE);

ALTER TABLE customer_segment_settings ENABLE ROW LEVEL SECURITY;

ALTER TABLE customer_follow_ups
    ADD COLUMN sentiment VARCHAR(20) NOT NULL DEFAULT 'NOT_RECORDED'
        CHECK (sentiment IN ('NOT_RECORDED', 'POSITIVE', 'NEUTRAL', 'MIXED', 'NEGATIVE')),
    ADD COLUMN feedback_tags TEXT[] NOT NULL DEFAULT '{}'
        CHECK (feedback_tags <@ ARRAY[
            'POSITIVE_FEEDBACK', 'PRODUCT_LIKED', 'PRODUCT_DISLIKED',
            'HAS_CONCERNS', 'PRICE_TOO_HIGH', 'QUALITY_CONCERN',
            'PACKAGING_CONCERN', 'DELIVERY_CONCERN', 'RESULTS_NOT_SEEN',
            'WANTS_OFFER', 'READY_TO_REORDER'
        ]::TEXT[]),
    ADD COLUMN purchase_intent VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'
        CHECK (purchase_intent IN ('UNKNOWN', 'HIGH', 'MEDIUM', 'LOW', 'NONE')),
    ADD COLUMN offer_interest BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN expected_order_date DATE;

CREATE INDEX ix_customer_follow_ups_sales_signal
ON customer_follow_ups(purchase_intent, offer_interest, contacted_at DESC);

DO $$
DECLARE role_name TEXT;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('REVOKE ALL ON customer_segment_settings FROM %I', role_name);
        END IF;
    END LOOP;
END $$;

CREATE OR REPLACE VIEW customer_analysis AS
WITH purchase AS (
    SELECT c.id AS customer_id,
        count(o.id)::INTEGER AS order_count,
        COALESCE(sum(o.order_value), 0)::NUMERIC(14,2) AS lifetime_value,
        COALESCE(avg(o.order_value), 0)::NUMERIC(14,2) AS average_order_value,
        min(o.order_date) AS first_order_date,
        max(o.order_date) AS last_order_date,
        (CURRENT_DATE - max(o.order_date))::INTEGER AS recency_days
    FROM customers c
    LEFT JOIN orders o ON o.customer_id = c.id
    GROUP BY c.id
),
thresholds AS (
    SELECT s.*,
        percentile_cont(s.high_value_percentile::DOUBLE PRECISION)
            WITHIN GROUP (ORDER BY p.lifetime_value)
            FILTER (WHERE p.order_count > 0) AS high_value,
        percentile_cont(s.vip_value_percentile::DOUBLE PRECISION)
            WITHIN GROUP (ORDER BY p.lifetime_value)
            FILTER (WHERE p.order_count > 0) AS vip_value
    FROM customer_segment_settings s
    CROSS JOIN purchase p
    GROUP BY s.singleton, s.new_customer_days, s.active_customer_days,
        s.champion_recency_days, s.champion_min_orders,
        s.high_value_percentile, s.vip_value_percentile, s.updated_at
),
affinity AS (
    SELECT o.customer_id,
        bool_or(lower(COALESCE(p.canonical_name, i.raw_product_name, ''))
            SIMILAR TO '%(hair color|hair colour)%') AS hair_color,
        bool_or(lower(COALESCE(p.canonical_name, i.raw_product_name, ''))
            SIMILAR TO '%(shampoo|hair serum|hair mask|hair strengthening|hair care|rosemary)%')
            AS hair_care,
        bool_or(lower(COALESCE(p.canonical_name, i.raw_product_name, ''))
            SIMILAR TO '%(aloe|face wash|cream|soap|lip balm|body wash|skin serum)%')
            AS skin_care,
        bool_or(lower(COALESCE(p.canonical_name, i.raw_product_name, ''))
            LIKE '%hydrosol%') AS hydrosol,
        bool_or(lower(COALESCE(p.canonical_name, i.raw_product_name, ''))
            SIMILAR TO '%(combo|duo)%') AS combo_buyer
    FROM orders o
    JOIN order_items i ON i.order_id = o.id
    LEFT JOIN products p ON p.id = i.product_id
    WHERE o.customer_id IS NOT NULL
    GROUP BY o.customer_id
),
scored AS (
    SELECT p.*, t.high_value::NUMERIC(14,2) AS high_value_threshold,
        t.vip_value::NUMERIC(14,2) AS vip_value_threshold,
        CASE
            WHEN p.order_count >= t.champion_min_orders
                AND p.lifetime_value >= t.vip_value
                AND p.recency_days <= t.champion_recency_days THEN 'CHAMPIONS'
            WHEN p.order_count >= 2 AND p.recency_days <= t.active_customer_days
                THEN 'LOYAL_REPEAT'
            WHEN p.order_count >= 2 THEN 'AT_RISK_REPEAT'
            WHEN p.first_order_date = p.last_order_date
                AND p.recency_days <= t.new_customer_days THEN 'NEW_CUSTOMER'
            WHEN p.order_count = 1 AND p.lifetime_value >= t.high_value
                AND p.recency_days <= t.active_customer_days THEN 'HIGH_VALUE_ONE_TIME'
            WHEN p.order_count = 1 AND p.lifetime_value >= t.high_value
                THEN 'AT_RISK_HIGH_VALUE'
            WHEN p.recency_days <= t.active_customer_days THEN 'ACTIVE_ONE_TIME'
            ELSE 'DORMANT_ONE_TIME'
        END AS segment,
        a.hair_color, a.hair_care, a.skin_care, a.hydrosol, a.combo_buyer
    FROM purchase p
    CROSS JOIN thresholds t
    LEFT JOIN affinity a ON a.customer_id = p.customer_id
)
SELECT customer_id, order_count, lifetime_value, average_order_value,
    first_order_date, last_order_date, recency_days,
    high_value_threshold, vip_value_threshold, segment,
    array_remove(ARRAY[
        CASE WHEN recency_days <= 30 THEN 'RECENT_30D' END,
        CASE WHEN order_count = 1 THEN 'FIRST_TIME_BUYER' END,
        CASE WHEN order_count >= 2 THEN 'REPEAT_BUYER' END,
        CASE WHEN lifetime_value >= high_value_threshold THEN 'HIGH_VALUE' END,
        CASE WHEN lifetime_value >= vip_value_threshold THEN 'VIP_VALUE' END,
        CASE WHEN hair_color THEN 'HAIR_COLOR' END,
        CASE WHEN hair_care THEN 'HAIR_CARE' END,
        CASE WHEN skin_care THEN 'SKIN_CARE' END,
        CASE WHEN hydrosol THEN 'HYDROSOL' END,
        CASE WHEN combo_buyer THEN 'COMBO_BUYER' END
    ], NULL)::TEXT[] AS tags
FROM scored;

REVOKE ALL ON customer_analysis FROM PUBLIC;
