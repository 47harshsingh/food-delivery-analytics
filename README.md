# Food Delivery Operations & Customer Analytics

SQL (MySQL) + Power BI analysis of a food delivery platform across 6 Indian cities. It answers four questions:

1. Where and when do deliveries run late?
2. Which restaurant partners cause it?
3. Does a bad first order cost repeat business?
4. Which promotions lose money?

## The data is synthetic

I don't have access to real order data from a delivery platform, and the public datasets I found were either too small or too clean to have the kind of problems worth analysing. So I wrote a generator (`generator/`) that simulates one year of a delivery platform: 500,000 orders, 118,000 customers, 480 restaurants, 3,200 delivery partners, 24 zones and 8 promotion campaigns, across 7 tables.

I planted specific problems in the data on purpose: slow zones, slow kitchens, a retention penalty after late first orders, and loss-making campaigns. Each one has a known size. The SQL then has to find them from the raw tables, without knowing which zones or restaurants were planted.

Because the right answers are known, the analysis can be checked. `scripts/validate.py` runs 32 checks against the database and compares each one to the numbers below.

So the findings below show what the method finds in a simulated business. They are not facts about any real company.

## Findings

All figures come from `sql/analysis/` and are checked by `scripts/validate.py`.

### Delivery time

| Metric | Value |
|---|---|
| Average delivery time | 32 min |
| Peak (19:00-22:00, 38% of orders) vs off-peak | 41 min vs 27 min |
| Late deliveries (> 45 min) | 18.4% of orders (92,003) |
| Worst 3 of 24 zones' share of late deliveries | 31% |

The three worst zones are Andheri East, Whitefield and Gachibowli. They handle 15% of orders but 31% of late deliveries. Kitchens aren't the problem there: prep time is about the same as everywhere else (12.9 vs 12.5 min). Travel time is what differs, 29.8 min against 18.0 min. These zones also have 39% fewer delivery partners per 1,000 orders (4.2 vs 6.8). The likely fix is partner supply, not restaurant onboarding.

### Restaurant partners

| Metric | Value |
|---|---|
| Top 12% of restaurants' share of orders | 58% |
| Underperforming partners | 22 of 480 (4.6%) |
| Their share of orders / late deliveries / refunds | 12% / 27% / 19% |

A restaurant counts as underperforming if it has at least 300 orders, an average prep time at least 1.5x the median restaurant's, and a late rate above the platform average. I used prep time rather than total delivery time because prep is the part the restaurant controls. A restaurant in a slow zone shouldn't be blamed for the roads. Among restaurants with 300+ orders, average prep time tops out at 14.4 minutes for everyone else, and the 22 flagged restaurants start at 19.6. With that gap, the 1.5x cut-off isn't sensitive (query 4 in `02_restaurant_performance.sql`).

### Customers and retention

| Metric | Value |
|---|---|
| Top 10% of customers' share of revenue | 34% (about 14 orders/yr each, vs about 3 for the rest) |
| 30-day repeat rate, overall | 38% |
| First order on time vs late | 41% vs 26% |
| Discount-acquired vs organic customers | 24% vs 43% |

The delivery-time effect is gradual, not a cliff at 45 minutes. Repeat rate is 43% when the first delivery takes 25 minutes or less, 36% at 36-45 minutes, and 23% above 60 minutes. The late-delivery and discount effects also hold inside each other's groups (2x2 in `04_retention.sql`), so they are two separate problems, not one problem counted twice.

### Promotions

| Metric | Value |
|---|---|
| Discounted orders | 33% of orders |
| AOV discounted / organic / blended | ₹385 / ₹512 / ₹470 |
| GMV (net of discounts) | ₹23.5 crore |
| Loss-making campaigns | 3 of 8 |
| Orders under them, margin per order | 40,000 at -₹47 |
| Spend below break-even | ₹18.8 lakh/yr |

All three loss-makers (IPLFEAST, DIWALIFEAST, FREEDOMFEAST) were flat ₹100+ off with free delivery. The percentage-off campaigns with a ₹50-60 cap all made money. The campaign used to acquire a customer made little difference to whether they came back: every campaign's customers reordered at 24-32% within 30 days, against 43% for organic customers. Whether there was a discount mattered, not which one.

Contribution margin per order is defined as commission on the gross basket + delivery fee - partner payout - discount. Refunds are reported separately and not netted in.

## How the data is generated

`python -m generator.generate` writes 7 CSVs to `data/`. It takes about 40 seconds and is deterministic: seed 42 always gives the same data.

The planted effects and how each one works:

| Effect | How it's built |
|---|---|
| Peak-hour slowdown | Prep and travel times scale with an hour-of-day load curve (lunch bump, dinner peak) |
| 3 slow zones | Longer travel times and about 40% fewer partners per order in 3 zones |
| 22 slow kitchens | Longer prep times for 22 busy restaurants |
| Late first order hurts retention | Probability of reordering within 30 days falls along an S-curve centred on 45 minutes |
| Discount acquisition hurts retention | Customers acquired on a discount are 19 points less likely to reorder |
| Loss-making campaigns | Flat-off + free-delivery campaigns, with the flat value set so margin averages -₹47 |
| Revenue concentration | Customers have different order rates and churn at different times |

All targets and assumptions are in `generator/params.py`. The generator solves its own parameters, such as delivery-time scale and campaign discount size, so that the headline rates land on those targets. Business assumptions the targets don't fix:

- Commission: 18-25% of gross basket, varies by restaurant
- Delivery fee: ₹25, waived on the flat-off campaigns
- Partner payout: ₹30 + ₹0.60 per travel minute
- Late: delivered in more than 45 minutes

### Limitations

- Every customer is acquired between January and November 2025. This gives every customer a full 30-day window to measure repeat orders, but it also means order volume grows through the year and December dips, because no new customers join in December.
- The data is cleaner than real data: no cancellations, no missing values, no duplicate records.
- The effects are deliberately simple and separable. Real causes overlap in ways a generator doesn't capture: weather, festival surges, restaurant menu changes.

## Repo layout

```
generator/          data generator (params.py has every target and assumption)
sql/01_schema.sql   7 normalised tables with keys and indexes
sql/02_views.sql    reusable views: order facts, first-order outcomes, restaurant scorecard, cohorts
sql/analysis/       01 delivery bottlenecks, 02 restaurant performance, 03 customer value / RFM,
                    04 retention and cohorts, 05 promotion P&L
scripts/            MySQL loader, validation checks
dashboard/          Power BI build notes and DAX measures
docs/               data dictionary
```

## Running it

Requires Python 3.10+ and MySQL 8.0+.

```bash
pip install -r requirements.txt
python -m generator.generate --out data

# in MySQL, once:  SET GLOBAL local_infile = 1;
python scripts/load_mysql.py --user root      # creates the schema and views, loads ~1.9M rows
python scripts/validate.py --user root        # 32 checks against the figures above
```

Then run the files in `sql/analysis/` in MySQL Workbench or any client. The Power BI report reads the views in `sql/02_views.sql`. See `dashboard/README.md`.
