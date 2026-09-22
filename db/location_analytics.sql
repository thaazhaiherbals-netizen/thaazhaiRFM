-- Run in pgAdmin against thaazhai_dev. No item join: each order counted once.
-- Customers are distinct within each location; don't sum customer counts across
-- locations because one customer can have orders delivered to different places.
SELECT
    COALESCE(delivery_pincode, 'Unknown') AS pincode,
    COUNT(*) AS orders,
    COUNT(DISTINCT customer_id) AS customers,
    SUM(order_value) AS revenue,
    ROUND(AVG(order_value), 2) AS average_order_value
FROM orders
GROUP BY delivery_pincode
ORDER BY revenue DESC, pincode;

-- City spelling variants are not merged automatically.
SELECT
    COALESCE(delivery_city, 'Unknown') AS city,
    COALESCE(delivery_state, 'Unknown') AS state,
    COALESCE(delivery_country, 'Unknown') AS country,
    COUNT(*) AS orders,
    SUM(order_value) AS revenue
FROM orders
GROUP BY delivery_city, delivery_state, delivery_country
ORDER BY revenue DESC, city, state, country;

