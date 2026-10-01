"""Check every headline figure against the database.

    python scripts/validate.py --user root

Each check is one SQL query returning one number, compared to the figure quoted
in the README. If a check fails, the README is wrong, not the data.
"""

import argparse
import getpass
import os
import sys

import pymysql

# name, sql, expected, tolerance
CHECKS = [
    ("orders", "SELECT COUNT(*) FROM orders", 500_000, 0),
    ("customers", "SELECT COUNT(*) FROM customers", 118_000, 0),
    ("restaurants", "SELECT COUNT(*) FROM restaurants", 480, 0),
    ("delivery partners", "SELECT COUNT(*) FROM delivery_partners", 3_200, 0),
    ("zones", "SELECT COUNT(*) FROM zones", 24, 0),
    ("campaigns", "SELECT COUNT(*) FROM promotions", 8, 0),

    ("blended AOV (INR)", "SELECT AVG(net_amount) FROM orders", 470, 0.5),
    ("GMV (INR crore)", "SELECT SUM(net_amount) / 1e7 FROM orders", 23.5, 0.05),
    ("discounted share of orders (%)", "SELECT 100 * AVG(promo_id IS NOT NULL) FROM orders", 33.0, 0.05),
    ("AOV discounted (INR)", "SELECT AVG(net_amount) FROM orders WHERE promo_id IS NOT NULL", 385, 0.5),
    ("AOV organic (INR)", "SELECT AVG(net_amount) FROM orders WHERE promo_id IS NULL", 512, 0.5),

    ("avg delivery (min)", "SELECT AVG(delivery_minutes) FROM v_orders", 32, 0.5),
    ("peak avg delivery (min)", "SELECT AVG(delivery_minutes) FROM v_orders WHERE is_peak", 41, 0.5),
    ("off-peak avg delivery (min)", "SELECT AVG(delivery_minutes) FROM v_orders WHERE NOT is_peak", 27, 0.5),
    ("peak share of orders (%)", "SELECT 100 * AVG(is_peak) FROM v_orders", 38, 0.5),
    ("late rate (%)", "SELECT 100 * AVG(is_late) FROM v_orders", 18.4, 0.05),
    ("worst 3 zones' share of late (%)", """
        SELECT 100 * SUM(CASE WHEN rn <= 3 THEN late END) / SUM(late) FROM (
            SELECT SUM(is_late) AS late, ROW_NUMBER() OVER (ORDER BY SUM(is_late) DESC) AS rn
            FROM v_orders GROUP BY zone_id) z""", 31, 0.5),

    ("top 12% restaurants' order share (%)", """
        SELECT 100 * SUM(CASE WHEN rn <= CEIL(0.12 * n) THEN orders END) / SUM(orders) FROM (
            SELECT COUNT(*) AS orders, ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS rn, COUNT(*) OVER () AS n
            FROM orders GROUP BY restaurant_id) r""", 58, 0.5),
    ("underperforming restaurants", "SELECT COUNT(*) FROM tmp_underperformers", 22, 0),
    ("underperformers' share of late (%)", """
        SELECT 100 * SUM(o.is_late * (u.restaurant_id IS NOT NULL)) / SUM(o.is_late)
        FROM v_orders o LEFT JOIN tmp_underperformers u USING (restaurant_id)""", 27, 0.5),
    ("underperformers' share of refunds (%)", """
        SELECT 100 * SUM(o.is_refunded * (u.restaurant_id IS NOT NULL)) / SUM(o.is_refunded)
        FROM v_orders o LEFT JOIN tmp_underperformers u USING (restaurant_id)""", 19, 0.5),

    ("top-decile customers' revenue share (%)", """
        SELECT 100 * SUM(CASE WHEN d = 1 THEN rev END) / SUM(rev) FROM (
            SELECT SUM(net_amount) AS rev, NTILE(10) OVER (ORDER BY SUM(net_amount) DESC) AS d
            FROM orders GROUP BY customer_id) c""", 34, 0.5),
    ("top-decile orders per customer", """
        SELECT AVG(n) FROM (
            SELECT COUNT(*) AS n, NTILE(10) OVER (ORDER BY SUM(net_amount) DESC) AS d
            FROM orders GROUP BY customer_id) c WHERE d = 1""", 14, 0.5),
    ("30-day repeat, overall (%)", "SELECT 100 * AVG(repeat_30d) FROM v_customer_first_order", 38, 0.5),
    ("30-day repeat, first order on time (%)",
     "SELECT 100 * AVG(repeat_30d) FROM v_customer_first_order WHERE NOT first_order_late", 41, 0.5),
    ("30-day repeat, first order late (%)",
     "SELECT 100 * AVG(repeat_30d) FROM v_customer_first_order WHERE first_order_late", 26, 0.5),
    ("30-day repeat, discount-acquired (%)",
     "SELECT 100 * AVG(repeat_30d) FROM v_customer_first_order WHERE discount_acquired", 24, 0.5),
    ("30-day repeat, organic-acquired (%)",
     "SELECT 100 * AVG(repeat_30d) FROM v_customer_first_order WHERE NOT discount_acquired", 43, 0.5),

    ("loss-making campaigns", """
        SELECT COUNT(*) FROM (SELECT promo_id FROM v_orders WHERE promo_id IS NOT NULL
                              GROUP BY promo_id HAVING SUM(contribution_margin) < 0) c""", 3, 0),
    ("orders under loss-making campaigns", """
        SELECT COUNT(*) FROM v_orders WHERE promo_id IN (
            SELECT promo_id FROM v_orders WHERE promo_id IS NOT NULL
            GROUP BY promo_id HAVING SUM(contribution_margin) < 0)""", 40_000, 0),
    ("their avg margin per order (INR)", """
        SELECT AVG(contribution_margin) FROM v_orders WHERE promo_id IN (
            SELECT promo_id FROM v_orders WHERE promo_id IS NOT NULL
            GROUP BY promo_id HAVING SUM(contribution_margin) < 0)""", -47, 0.5),
    ("recoverable spend (INR lakh)", """
        SELECT -SUM(contribution_margin) / 1e5 FROM v_orders WHERE promo_id IN (
            SELECT promo_id FROM v_orders WHERE promo_id IS NOT NULL
            GROUP BY promo_id HAVING SUM(contribution_margin) < 0)""", 18.8, 0.05),
]

# flag defined once in sql/02_views.sql (v_restaurant_scorecard)
UNDERPERFORMERS = """
CREATE TEMPORARY TABLE tmp_underperformers AS
SELECT restaurant_id FROM v_restaurant_scorecard WHERE is_underperformer
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", default="root")
    args = ap.parse_args()
    password = os.environ.get("MYSQL_PWD") or getpass.getpass("MySQL password: ")
    conn = pymysql.connect(host=args.host, port=args.port, user=args.user, password=password,
                           database="food_delivery")
    failed = 0
    with conn.cursor() as cur:
        cur.execute(UNDERPERFORMERS)
        print(f"{'check':<42}{'actual':>14}{'expected':>12}  result")
        for name, sql, expected, tol in CHECKS:
            cur.execute(sql)
            actual = float(cur.fetchone()[0])
            ok = abs(actual - expected) <= tol
            failed += not ok
            print(f"{name:<42}{actual:>14,.2f}{expected:>12,}  {'ok' if ok else 'FAIL'}")
    conn.close()
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
