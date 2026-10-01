-- Where and when are deliveries slow?
-- Late = delivered in more than 45 minutes. Peak = orders placed 19:00-21:59.
USE food_delivery;

-- 1. Headline delivery metrics
SELECT
    COUNT(*)                                             AS orders,
    ROUND(AVG(delivery_minutes), 1)                      AS avg_delivery_min,
    ROUND(AVG(CASE WHEN is_peak THEN delivery_minutes END), 1)     AS peak_avg_min,
    ROUND(AVG(CASE WHEN NOT is_peak THEN delivery_minutes END), 1) AS offpeak_avg_min,
    ROUND(100 * AVG(is_peak), 1)                         AS peak_share_pct,
    SUM(is_late)                                         AS late_orders,
    ROUND(100 * AVG(is_late), 1)                         AS late_rate_pct
FROM v_orders;

-- 2. Hour of day: volume, speed, lateness
SELECT
    order_hour,
    COUNT(*)                          AS orders,
    ROUND(AVG(prep_minutes), 1)       AS avg_prep_min,
    ROUND(AVG(travel_minutes), 1)     AS avg_travel_min,
    ROUND(AVG(delivery_minutes), 1)   AS avg_delivery_min,
    ROUND(100 * AVG(is_late), 1)      AS late_rate_pct
FROM v_orders
GROUP BY order_hour
ORDER BY order_hour;

-- 3. Zones ranked by late deliveries, with cumulative share and partner supply
WITH zone_stats AS (
    SELECT z.zone_id, z.zone_name, z.city,
           COUNT(*)                         AS orders,
           SUM(o.is_late)                   AS late_orders,
           ROUND(100 * AVG(o.is_late), 1)   AS late_rate_pct,
           ROUND(AVG(o.prep_minutes), 1)    AS avg_prep_min,
           ROUND(AVG(o.travel_minutes), 1)  AS avg_travel_min
    FROM v_orders o
    JOIN zones z ON z.zone_id = o.zone_id
    GROUP BY z.zone_id, z.zone_name, z.city
),
partners AS (
    SELECT zone_id, COUNT(*) AS partners FROM delivery_partners GROUP BY zone_id
)
SELECT
    RANK() OVER (ORDER BY s.late_orders DESC)                       AS late_rank,
    s.zone_name, s.city, s.orders, s.late_orders, s.late_rate_pct,
    s.avg_prep_min, s.avg_travel_min,
    ROUND(100 * s.late_orders / SUM(s.late_orders) OVER (), 1)      AS share_of_all_late_pct,
    ROUND(100 * SUM(s.late_orders) OVER (ORDER BY s.late_orders DESC)
              / SUM(s.late_orders) OVER (), 1)                      AS cumulative_late_share_pct,
    ROUND(1000 * p.partners / s.orders, 2)                          AS partners_per_1k_orders
FROM zone_stats s
JOIN partners p ON p.zone_id = s.zone_id
ORDER BY s.late_orders DESC;

-- 4. How concentrated is lateness? Share of late deliveries in the worst 3 of 24 zones
WITH z AS (
    SELECT zone_id, SUM(is_late) AS late_orders,
           ROW_NUMBER() OVER (ORDER BY SUM(is_late) DESC) AS rn
    FROM v_orders
    GROUP BY zone_id
)
SELECT
    ROUND(100 * SUM(CASE WHEN rn <= 3 THEN late_orders END) / SUM(late_orders), 1) AS top3_zone_share_of_late_pct,
    ROUND(100 * 3 / COUNT(*), 1)                                                    AS top3_share_of_zones_pct
FROM z;

-- 5. Peak vs off-peak by zone: is the bottleneck a peak-hour problem or all-day?
SELECT
    z.zone_name, z.city,
    ROUND(AVG(CASE WHEN o.is_peak THEN o.delivery_minutes END), 1)          AS peak_avg_min,
    ROUND(AVG(CASE WHEN NOT o.is_peak THEN o.delivery_minutes END), 1)      AS offpeak_avg_min,
    ROUND(100 * AVG(CASE WHEN o.is_peak THEN o.is_late END), 1)             AS peak_late_pct,
    ROUND(100 * AVG(CASE WHEN NOT o.is_peak THEN o.is_late END), 1)         AS offpeak_late_pct
FROM v_orders o
JOIN zones z ON z.zone_id = o.zone_id
GROUP BY z.zone_name, z.city
ORDER BY peak_late_pct DESC;
