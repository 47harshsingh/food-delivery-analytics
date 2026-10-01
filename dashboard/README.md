# Power BI report

4 pages: Operations, Restaurant Performance, Customer Retention, Promotion ROI. Drill-through is available on city, restaurant and cohort.

## Data source

Get Data → MySQL database → `localhost` / `food_delivery`. This needs the MySQL Connector/NET installed. Import mode is fine at this size.

Load these:

| Query | Role |
|---|---|
| `v_orders` | fact table |
| `v_customer_first_order` | one row per customer (retention) |
| `v_restaurant_scorecard` | one row per restaurant (scorecard and underperformer flag) |
| `v_cohort_activity` | cohort heatmap |
| `zones`, `promotions` | dimensions |

The views already compute the business rules (late, peak, contribution margin, repeat within 30 days, underperformer). That way, the report and the SQL can't drift apart.

## Model

- `v_orders[zone_id]` → `zones[zone_id]` (many-to-one)
- `v_orders[restaurant_id]` → `v_restaurant_scorecard[restaurant_id]` (many-to-one)
- `v_orders[promo_id]` → `promotions[promo_id]` (many-to-one)
- `v_cohort_activity[customer_id]` → `v_customer_first_order[customer_id]` (many-to-one)
- Date table: `Dates = CALENDAR(DATE(2025,1,1), DATE(2025,12,31))`, marked as date table, related to `v_orders[order_date]`

## Measures

```DAX
Orders = COUNTROWS(v_orders)
GMV = SUM(v_orders[net_amount])
AOV = DIVIDE([GMV], [Orders])

Avg Delivery Min = AVERAGE(v_orders[delivery_minutes])
Peak Avg Min = CALCULATE([Avg Delivery Min], v_orders[is_peak] = 1)
Off-peak Avg Min = CALCULATE([Avg Delivery Min], v_orders[is_peak] = 0)
Late Orders = CALCULATE([Orders], v_orders[is_late] = 1)
Late Rate = DIVIDE([Late Orders], [Orders])
Share of All Late = DIVIDE([Late Orders], CALCULATE([Late Orders], ALL(zones), ALL(v_restaurant_scorecard)))

Refund Rate = DIVIDE(CALCULATE([Orders], v_orders[is_refunded] = 1), [Orders])

Discount Spend = SUM(v_orders[discount_amount])
Contribution Margin = SUM(v_orders[contribution_margin])
Margin per Order = DIVIDE([Contribution Margin], [Orders])
Recoverable Spend =
    -SUMX(
        FILTER(VALUES(promotions[promo_id]), [Contribution Margin] < 0),
        [Contribution Margin]
    )

Customers = COUNTROWS(v_customer_first_order)
Repeat 30d = AVERAGE(v_customer_first_order[repeat_30d])
Cohort Retention =
    DIVIDE(
        DISTINCTCOUNT(v_cohort_activity[customer_id]),
        CALCULATE(DISTINCTCOUNT(v_cohort_activity[customer_id]), v_cohort_activity[month_n] = 0)
    )
```

## Pages

**1. Operations**
- Cards: Orders, Avg Delivery Min, Peak Avg Min, Off-peak Avg Min, Late Rate
- Line: Avg Delivery Min and Late Rate by `order_hour`
- Bar: Share of All Late by `zone_name`, sorted descending
- Matrix heatmap: `zone_name` × `order_hour`, values = Late Rate, background colour scale
- Slicers: city, month

**2. Restaurant Performance**
- Scatter: `avg_prep_min` (x) vs `late_rate` (y), size = `orders`, legend = `is_underperformer`
- Pareto: Orders by restaurant (sorted) with a cumulative % line
- Table: scorecard filtered to underperformers
- Cards: underperformers' share of orders, late deliveries and refunds
- Drill-through target page "Restaurant detail" (field: `restaurant_name`): orders by hour, prep vs travel split, refund rate trend

**3. Customer Retention**
- Bar: Repeat 30d by first-delivery time bucket (add a calculated column on `v_customer_first_order` via a lookup to the first order's `delivery_minutes`)
- Matrix: Repeat 30d, rows = `discount_acquired`, columns = `first_order_late`
- Cohort heatmap: rows = `cohort_month`, columns = `month_n`, values = Cohort Retention
- Drill-through on `cohort_month`

**4. Promotion ROI**
- Table: promo_code, Orders, AOV, Discount Spend, Margin per Order, Contribution Margin; conditional formatting on margin
- Bar: Margin per Order by promo_code
- Cards: Recoverable Spend, discounted share of orders, AOV discounted vs organic

## Check against SQL

Before publishing, these cards should match `scripts/validate.py`: Late Rate 18.4%, Peak/Off-peak 41/27 min, Repeat 30d 38%, Recoverable Spend ₹18.8L.
