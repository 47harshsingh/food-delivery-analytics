# Data dictionary

7 tables. Money is in INR, times are in minutes, and all timestamps fall in calendar year 2025.

## orders (500,000 rows)

| Column | Type | Notes |
|---|---|---|
| order_id | INT PK | Chronological |
| customer_id | INT FK | |
| restaurant_id | SMALLINT FK | |
| partner_id | SMALLINT FK | Delivery partner, from the delivery zone |
| zone_id | SMALLINT FK | Delivery zone (the customer's zone) |
| promo_id | TINYINT FK, nullable | NULL = organic order |
| order_ts | DATETIME | Order placed |
| gross_amount | DECIMAL | Menu value of the basket; equals the sum of order_items |
| discount_amount | DECIMAL | Funded by the platform |
| net_amount | DECIMAL | gross - discount. AOV and GMV are computed on this |
| delivery_fee | DECIMAL | ₹25, or 0 on free-delivery campaigns |
| partner_payout | DECIMAL | ₹30 + ₹0.60 per travel minute |
| prep_minutes | SMALLINT | Order placed to food ready (restaurant-controlled) |
| travel_minutes | SMALLINT | Food ready to delivered, including rider delays |
| delivery_minutes | SMALLINT | prep + travel; late if > 45 |
| is_refunded | TINYINT | 1 if any refund was issued |
| refund_amount | DECIMAL | Full or 50% of net_amount |

## order_items (~1.29M rows)

| Column | Type | Notes |
|---|---|---|
| order_item_id | INT PK | |
| order_id | INT FK | |
| item_name | VARCHAR | From the restaurant's menu |
| category | VARCHAR | starter / main / side / dessert / beverage |
| quantity | TINYINT | |
| unit_price | DECIMAL | Menu price at that restaurant |

## customers (118,000)

| Column | Type | Notes |
|---|---|---|
| customer_id | INT PK | |
| zone_id | SMALLINT FK | Home / delivery zone |
| signup_date | DATE | Same day as first order |
| platform | VARCHAR | android / ios / web |

Acquisition channel isn't stored. It's derived from the first order: if that order carried a promo, the customer was discount-acquired. See `v_customer_first_order`.

## restaurants (480)

| Column | Type | Notes |
|---|---|---|
| restaurant_id | SMALLINT PK | |
| restaurant_name | VARCHAR | |
| zone_id | SMALLINT FK | Where the kitchen is |
| cuisine | VARCHAR | 10 cuisines |
| commission_rate | DECIMAL | 0.18-0.25 of gross |
| onboarded_date | DATE | Before 2025 |

## delivery_partners (3,200)

| Column | Type | Notes |
|---|---|---|
| partner_id | SMALLINT PK | |
| zone_id | SMALLINT FK | Home zone |
| vehicle_type | VARCHAR | motorbike / e-bike / bicycle |
| joined_date | DATE | |

## promotions (8)

| Column | Type | Notes |
|---|---|---|
| promo_id | TINYINT PK | |
| promo_code | VARCHAR | |
| campaign_name | VARCHAR | |
| discount_type | ENUM | percent / flat |
| discount_value | DECIMAL | % or ₹ |
| max_discount | DECIMAL | Cap in ₹ |
| min_order_value | DECIMAL | ₹299 on flat offers |
| free_delivery | TINYINT | |
| start_date, end_date | DATE | Campaign window |
| eligibility | VARCHAR | any / first_order / weekend / lunch (11:00-14:59) |

## zones (24)

| Column | Type | Notes |
|---|---|---|
| zone_id | SMALLINT PK | |
| zone_name | VARCHAR | |
| city | VARCHAR | 6 cities, 4 zones each |

## Views (sql/02_views.sql)

| View | Grain | Adds |
|---|---|---|
| v_orders | order | city, hour, is_peak, is_late, is_discounted, contribution_margin |
| v_customer_first_order | customer | first order, cohort_month, first_order_late, discount_acquired, repeat_30d |
| v_restaurant_scorecard | restaurant | orders, avg prep, late / refund rate, is_underperformer |
| v_cohort_activity | customer x active month | month_n since first order month |
