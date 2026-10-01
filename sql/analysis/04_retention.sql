-- Does the first order decide whether a customer comes back?
-- Repeat = a second order within 30 days of the first.
USE food_delivery;

-- 1. 30-day repeat rate: overall, by first-order delivery outcome, by acquisition channel
SELECT 'Overall' AS cut, COUNT(*) AS customers, ROUND(100 * AVG(repeat_30d), 1) AS repeat_30d_pct
FROM v_customer_first_order
UNION ALL
SELECT CASE WHEN first_order_late THEN 'First order late (>45 min)' ELSE 'First order on time' END,
       COUNT(*), ROUND(100 * AVG(repeat_30d), 1)
FROM v_customer_first_order
GROUP BY first_order_late
UNION ALL
SELECT CASE WHEN discount_acquired THEN 'Discount-acquired' ELSE 'Organic-acquired' END,
       COUNT(*), ROUND(100 * AVG(repeat_30d), 1)
FROM v_customer_first_order
GROUP BY discount_acquired;

-- 2. Both effects together (2x2). If they were the same effect in disguise, one would vanish here.
SELECT
    CASE WHEN discount_acquired THEN 'Discount' ELSE 'Organic' END     AS acquisition,
    CASE WHEN first_order_late THEN 'Late' ELSE 'On time' END          AS first_order,
    COUNT(*)                                                           AS customers,
    ROUND(100 * AVG(repeat_30d), 1)                                    AS repeat_30d_pct
FROM v_customer_first_order
GROUP BY acquisition, first_order
ORDER BY acquisition, first_order;

-- 3. Dose-response: repeat rate by how long the first delivery took
SELECT
    CASE
        WHEN o.delivery_minutes <= 25 THEN '1) <=25 min'
        WHEN o.delivery_minutes <= 35 THEN '2) 26-35 min'
        WHEN o.delivery_minutes <= 45 THEN '3) 36-45 min'
        WHEN o.delivery_minutes <= 60 THEN '4) 46-60 min'
        ELSE '5) >60 min'
    END                                   AS first_delivery_time,
    COUNT(*)                              AS customers,
    ROUND(100 * AVG(f.repeat_30d), 1)     AS repeat_30d_pct
FROM v_customer_first_order f
JOIN orders o ON o.order_id = f.first_order_id
GROUP BY first_delivery_time
ORDER BY first_delivery_time;

-- 4. Monthly cohort retention: % of each cohort ordering in month N after their first month
WITH activity AS (
    SELECT DISTINCT f.customer_id, f.cohort_month,
           TIMESTAMPDIFF(MONTH, f.cohort_month, DATE_FORMAT(o.order_ts, '%Y-%m-01')) AS month_n
    FROM v_customer_first_order f
    JOIN orders o ON o.customer_id = f.customer_id
),
sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size FROM v_customer_first_order GROUP BY cohort_month
)
SELECT
    a.cohort_month,
    s.cohort_size,
    -- NULL where month N falls after the data ends (31 Dec), rather than a misleading 0
    CASE WHEN a.cohort_month + INTERVAL 1 MONTH <= '2025-12-01'
         THEN ROUND(100 * SUM(a.month_n = 1) / s.cohort_size, 1) END AS m1_pct,
    CASE WHEN a.cohort_month + INTERVAL 2 MONTH <= '2025-12-01'
         THEN ROUND(100 * SUM(a.month_n = 2) / s.cohort_size, 1) END AS m2_pct,
    CASE WHEN a.cohort_month + INTERVAL 3 MONTH <= '2025-12-01'
         THEN ROUND(100 * SUM(a.month_n = 3) / s.cohort_size, 1) END AS m3_pct,
    CASE WHEN a.cohort_month + INTERVAL 6 MONTH <= '2025-12-01'
         THEN ROUND(100 * SUM(a.month_n = 6) / s.cohort_size, 1) END AS m6_pct
FROM activity a
JOIN sizes s ON s.cohort_month = a.cohort_month
GROUP BY a.cohort_month, s.cohort_size
ORDER BY a.cohort_month;
