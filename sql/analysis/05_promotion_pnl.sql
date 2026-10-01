-- Which promotions pay for themselves?
-- Contribution margin per order = commission on gross + delivery fee - partner payout - discount
-- (see v_orders). Refunds are reported separately and not netted in.
USE food_delivery;

-- 1. Discounted vs organic orders
SELECT
    CASE WHEN is_discounted THEN 'Discounted' ELSE 'Organic' END AS order_type,
    COUNT(*)                                      AS orders,
    ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct,
    ROUND(AVG(net_amount), 0)                     AS aov,
    ROUND(AVG(discount_amount), 0)                AS avg_discount,
    ROUND(AVG(contribution_margin), 1)            AS margin_per_order
FROM v_orders
GROUP BY order_type;

-- 2. Campaign P&L
SELECT
    p.promo_code,
    p.campaign_name,
    p.start_date,
    p.end_date,
    COUNT(*)                                   AS orders,
    ROUND(AVG(o.net_amount), 0)                AS aov,
    ROUND(SUM(o.discount_amount) / 1e5, 2)     AS discount_spend_lakh,
    ROUND(AVG(o.contribution_margin), 1)       AS margin_per_order,
    ROUND(SUM(o.contribution_margin) / 1e5, 2) AS total_margin_lakh,
    CASE WHEN AVG(o.contribution_margin) < 0 THEN 'Loss-making' ELSE 'Profitable' END AS verdict
FROM v_orders o
JOIN promotions p ON p.promo_id = o.promo_id
GROUP BY p.promo_id, p.promo_code, p.campaign_name, p.start_date, p.end_date
ORDER BY margin_per_order;

-- 3. Recoverable spend: what the loss-making campaigns cost below break-even
WITH c AS (
    SELECT promo_id, COUNT(*) AS orders, SUM(contribution_margin) AS margin
    FROM v_orders
    WHERE promo_id IS NOT NULL
    GROUP BY promo_id
    HAVING SUM(contribution_margin) < 0
)
SELECT
    COUNT(*)                                      AS loss_making_campaigns,
    SUM(orders)                                   AS orders,
    ROUND(100 * SUM(orders) / (SELECT COUNT(*) FROM orders WHERE promo_id IS NOT NULL), 1) AS pct_of_discounted_orders,
    ROUND(SUM(margin) / SUM(orders), 1)           AS avg_margin_per_order,
    ROUND(-SUM(margin) / 1e5, 1)                  AS recoverable_lakh
FROM c;

-- 4. Do campaign-acquired customers stick? 30-day repeat by the promo on their first order
SELECT
    COALESCE(p.promo_code, 'ORGANIC')    AS first_order_promo,
    COUNT(*)                             AS customers,
    ROUND(100 * AVG(f.repeat_30d), 1)    AS repeat_30d_pct
FROM v_customer_first_order f
JOIN orders o           ON o.order_id = f.first_order_id
LEFT JOIN promotions p  ON p.promo_id = o.promo_id
GROUP BY first_order_promo
ORDER BY customers DESC;
