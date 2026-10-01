-- Reusable views. The analysis queries and the Power BI model both read from these.
USE food_delivery;

-- One row per order with the derived flags every analysis needs.
-- Contribution margin = commission on gross + delivery fee - partner payout - platform-funded discount.
CREATE OR REPLACE VIEW v_orders AS
SELECT
    o.order_id,
    o.customer_id,
    o.restaurant_id,
    o.partner_id,
    o.zone_id,
    z.city,
    o.promo_id,
    o.order_ts,
    DATE(o.order_ts)                    AS order_date,
    HOUR(o.order_ts)                    AS order_hour,
    HOUR(o.order_ts) BETWEEN 19 AND 21  AS is_peak,
    o.promo_id IS NOT NULL              AS is_discounted,
    o.gross_amount,
    o.discount_amount,
    o.net_amount,
    o.delivery_fee,
    o.partner_payout,
    o.prep_minutes,
    o.travel_minutes,
    o.delivery_minutes,
    o.delivery_minutes > 45             AS is_late,
    o.is_refunded,
    o.refund_amount,
    ROUND(r.commission_rate * o.gross_amount + o.delivery_fee
          - o.partner_payout - o.discount_amount, 2) AS contribution_margin
FROM orders o
JOIN zones z       ON z.zone_id = o.zone_id
JOIN restaurants r ON r.restaurant_id = o.restaurant_id;

-- One row per customer: how their first order went and whether they came back within 30 days.
-- Every customer's first order is on or before 30 Nov, so the 30-day window is always observable.
CREATE OR REPLACE VIEW v_customer_first_order AS
WITH ranked AS (
    SELECT customer_id, order_id, order_ts, is_late, is_discounted,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_ts, order_id) AS rn
    FROM v_orders
)
SELECT
    f.customer_id,
    f.order_id                                AS first_order_id,
    f.order_ts                                AS first_order_ts,
    DATE_FORMAT(f.order_ts, '%Y-%m-01')       AS cohort_month,
    f.is_late                                 AS first_order_late,
    f.is_discounted                           AS discount_acquired,
    EXISTS (
        SELECT 1 FROM orders o2
        WHERE o2.customer_id = f.customer_id
          AND o2.order_ts > f.order_ts
          AND DATE(o2.order_ts) <= DATE(f.order_ts) + INTERVAL 30 DAY
    )                                         AS repeat_30d
FROM ranked f
WHERE f.rn = 1;

-- One row per restaurant with the underperformer flag.
-- Rule: >= 300 orders, average prep time >= 1.5x the median restaurant, and a late rate above
-- the platform average. Prep time is the part of delivery the restaurant controls.
CREATE OR REPLACE VIEW v_restaurant_scorecard AS
WITH rs AS (
    SELECT restaurant_id,
           COUNT(*)            AS orders,
           AVG(prep_minutes)   AS avg_prep_min,
           AVG(is_late)        AS late_rate,
           AVG(is_refunded)    AS refund_rate,
           SUM(net_amount)     AS net_revenue
    FROM v_orders
    GROUP BY restaurant_id
),
med AS (
    SELECT AVG(avg_prep_min) AS median_prep
    FROM (SELECT avg_prep_min,
                 ROW_NUMBER() OVER (ORDER BY avg_prep_min) AS rn,
                 COUNT(*) OVER ()                          AS cnt
          FROM rs) t
    WHERE rn IN (FLOOR((cnt + 1) / 2), CEIL((cnt + 1) / 2))
),
platform AS (
    SELECT AVG(is_late) AS late_rate FROM v_orders
)
SELECT
    r.restaurant_id, r.restaurant_name, r.cuisine, z.city, z.zone_name,
    rs.orders,
    ROUND(rs.avg_prep_min, 1)         AS avg_prep_min,
    ROUND(rs.late_rate, 4)            AS late_rate,
    ROUND(rs.refund_rate, 4)          AS refund_rate,
    rs.net_revenue,
    (rs.orders >= 300
     AND rs.avg_prep_min >= 1.5 * med.median_prep
     AND rs.late_rate > platform.late_rate) AS is_underperformer
FROM rs
JOIN restaurants r ON r.restaurant_id = rs.restaurant_id
JOIN zones z       ON z.zone_id = r.zone_id
CROSS JOIN med
CROSS JOIN platform;

-- Customer x month activity for cohort charts (month_n = months since first order month).
CREATE OR REPLACE VIEW v_cohort_activity AS
SELECT DISTINCT
    f.customer_id,
    f.cohort_month,
    TIMESTAMPDIFF(MONTH, f.cohort_month, DATE_FORMAT(o.order_ts, '%Y-%m-01')) AS month_n
FROM v_customer_first_order f
JOIN orders o ON o.customer_id = f.customer_id;
