-- Dynamic D2C customer segmentation and product-affinity tags.
CREATE VIEW customer_analysis AS
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
    SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY lifetime_value)
            FILTER (WHERE order_count > 0) AS high_value,
        percentile_cont(0.90) WITHIN GROUP (ORDER BY lifetime_value)
            FILTER (WHERE order_count > 0) AS vip_value
    FROM purchase
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
            WHEN p.order_count >= 3 AND p.lifetime_value >= t.vip_value
                AND p.recency_days <= 60 THEN 'CHAMPIONS'
            WHEN p.order_count >= 2 AND p.recency_days <= 90 THEN 'LOYAL_REPEAT'
            WHEN p.order_count >= 2 THEN 'AT_RISK_REPEAT'
            WHEN p.first_order_date = p.last_order_date AND p.recency_days <= 30
                THEN 'NEW_CUSTOMER'
            WHEN p.order_count = 1 AND p.lifetime_value >= t.high_value
                AND p.recency_days <= 90 THEN 'HIGH_VALUE_ONE_TIME'
            WHEN p.order_count = 1 AND p.lifetime_value >= t.high_value
                THEN 'AT_RISK_HIGH_VALUE'
            WHEN p.recency_days <= 90 THEN 'ACTIVE_ONE_TIME'
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
DO $$
DECLARE role_name TEXT;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('REVOKE ALL ON customer_analysis FROM %I', role_name);
        END IF;
    END LOOP;
END $$;
