-- How concentrated is revenue across customers, and who are the customers worth protecting?
USE food_delivery;

-- 1. Revenue by customer decile (decile 1 = highest spenders)
WITH c AS (
    SELECT customer_id, COUNT(*) AS orders, SUM(net_amount) AS revenue
    FROM v_orders
    GROUP BY customer_id
),
d AS (
    SELECT *, NTILE(10) OVER (ORDER BY revenue DESC) AS decile FROM c
)
SELECT
    decile,
    COUNT(*)                                              AS customers,
    ROUND(AVG(orders), 1)                                 AS orders_per_customer,
    ROUND(SUM(revenue) / SUM(orders), 0)                  AS aov,
    ROUND(SUM(revenue) / 1e7, 2)                          AS revenue_cr,
    ROUND(100 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 1) AS revenue_share_pct
FROM d
GROUP BY decile
ORDER BY decile;

-- 2. RFM scoring (reference date: day after the data ends)
WITH c AS (
    SELECT customer_id,
           DATEDIFF('2026-01-01', MAX(order_date)) AS recency_days,
           COUNT(*)                                AS frequency,
           SUM(net_amount)                         AS monetary
    FROM v_orders
    GROUP BY customer_id
),
scored AS (
    SELECT *,
           6 - NTILE(5) OVER (ORDER BY recency_days)   AS r_score,  -- 5 = most recent
           NTILE(5) OVER (ORDER BY frequency)          AS f_score,
           NTILE(5) OVER (ORDER BY monetary)           AS m_score
    FROM c
),
segmented AS (
    SELECT *,
           CASE
               WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
               WHEN f_score >= 4 AND r_score >= 3                  THEN 'Loyal'
               WHEN r_score >= 4 AND f_score <= 2                  THEN 'New / promising'
               WHEN r_score <= 2 AND f_score >= 3                  THEN 'At risk'
               WHEN r_score <= 2 AND f_score <= 2                  THEN 'Lapsed'
               ELSE 'Needs attention'
           END AS segment
    FROM scored
)
SELECT
    segment,
    COUNT(*)                                                   AS customers,
    ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)           AS pct_customers,
    ROUND(AVG(recency_days), 0)                                AS avg_recency_days,
    ROUND(AVG(frequency), 1)                                   AS avg_orders,
    ROUND(AVG(monetary), 0)                                    AS avg_revenue,
    ROUND(100 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 1) AS revenue_share_pct
FROM segmented
GROUP BY segment
ORDER BY revenue_share_pct DESC;
