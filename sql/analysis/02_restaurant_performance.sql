-- Which restaurant partners drive volume, and which ones drive late deliveries and refunds?
USE food_delivery;

-- 1. Order concentration: share of orders from the top 12% of restaurants
WITH r AS (
    SELECT restaurant_id, COUNT(*) AS orders,
           ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS rn,
           COUNT(*) OVER ()                           AS n_restaurants
    FROM v_orders
    GROUP BY restaurant_id
)
SELECT
    SUM(rn <= CEIL(0.12 * n_restaurants))                                           AS top_restaurants,
    ROUND(100 * SUM(CASE WHEN rn <= CEIL(0.12 * n_restaurants) THEN orders END) / SUM(orders), 1) AS top12_order_share_pct
FROM r;

-- 2. Restaurant scorecard
--    Prep time is the part of delivery time the restaurant controls, so it is the fairest
--    way to separate a slow kitchen from a restaurant that just sits in a slow zone.
WITH scorecard AS (
    SELECT o.restaurant_id, r.restaurant_name, r.cuisine, z.city,
           COUNT(*)                          AS orders,
           ROUND(AVG(o.prep_minutes), 1)     AS avg_prep_min,
           ROUND(100 * AVG(o.is_late), 1)    AS late_rate_pct,
           ROUND(100 * AVG(o.is_refunded), 1) AS refund_rate_pct,
           SUM(o.net_amount)                 AS net_revenue
    FROM v_orders o
    JOIN restaurants r ON r.restaurant_id = o.restaurant_id
    JOIN zones z       ON z.zone_id = r.zone_id
    GROUP BY o.restaurant_id, r.restaurant_name, r.cuisine, z.city
)
SELECT * FROM scorecard ORDER BY avg_prep_min DESC LIMIT 40;

-- 3. Underperforming partners and what they cost
--    The flag is defined once in v_restaurant_scorecard (sql/02_views.sql): >= 300 orders,
--    average prep >= 1.5x the median restaurant, late rate above the platform average.
--    The 1.5x cut sits in a clear gap in the prep-time distribution (query 4), so nudging
--    the threshold doesn't change who gets flagged.
SELECT
    SUM(s.is_underperformer)                                          AS underperformers,
    COUNT(*)                                                          AS restaurants,
    ROUND(100 * AVG(s.is_underperformer), 1)                          AS pct_of_partners,
    ROUND(100 * SUM(s.orders * s.is_underperformer) / SUM(s.orders), 1)                         AS share_of_orders_pct,
    ROUND(100 * SUM(s.orders * s.late_rate * s.is_underperformer) / SUM(s.orders * s.late_rate), 1)     AS share_of_late_pct,
    ROUND(100 * SUM(s.orders * s.refund_rate * s.is_underperformer) / SUM(s.orders * s.refund_rate), 1) AS share_of_refunds_pct
FROM v_restaurant_scorecard s;

-- The flagged restaurants
SELECT restaurant_name, cuisine, city, zone_name, orders, avg_prep_min,
       ROUND(100 * late_rate, 1) AS late_rate_pct, ROUND(100 * refund_rate, 1) AS refund_rate_pct
FROM v_restaurant_scorecard
WHERE is_underperformer
ORDER BY orders * late_rate DESC;

-- 4. Prep-time distribution across restaurants (>= 300 orders), in 2-minute buckets.
--    The gap between the bulk of restaurants and the slow tail is what justifies the 1.5x rule.
SELECT
    FLOOR(avg_prep / 2) * 2   AS prep_bucket_min,
    COUNT(*)                  AS restaurants
FROM (
    SELECT restaurant_id, AVG(prep_minutes) AS avg_prep
    FROM v_orders
    GROUP BY restaurant_id
    HAVING COUNT(*) >= 300
) t
GROUP BY prep_bucket_min
ORDER BY prep_bucket_min;
