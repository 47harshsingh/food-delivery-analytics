"""Targets and assumptions for the synthetic dataset.

Targets are the figures the SQL analysis is expected to recover.
Assumptions are business inputs the targets don't pin down on their own
(commission, partner payout, fees). Change them here, not in the code.
"""

SEED = 42
YEAR = 2025

N_ORDERS = 500_000
N_CUSTOMERS = 118_000
N_RESTAURANTS = 480
N_PARTNERS = 3_200

# share of customers per city
CITIES = {
    "Bengaluru": 0.22,
    "Mumbai": 0.20,
    "Delhi": 0.19,
    "Hyderabad": 0.15,
    "Pune": 0.12,
    "Chennai": 0.12,
}
ZONES = {
    "Bengaluru": ["Koramangala", "Indiranagar", "Whitefield", "HSR Layout"],
    "Mumbai": ["Bandra West", "Andheri East", "Powai", "Lower Parel"],
    "Delhi": ["Saket", "Connaught Place", "Dwarka", "Rohini"],
    "Hyderabad": ["Gachibowli", "Banjara Hills", "Kondapur", "Begumpet"],
    "Pune": ["Koregaon Park", "Hinjewadi", "Baner", "Viman Nagar"],
    "Chennai": ["T Nagar", "Adyar", "Velachery", "Anna Nagar"],
}
# Zones with long travel times and thin partner supply (the injected bottleneck)
BAD_ZONES = ["Whitefield", "Andheri East", "Gachibowli"]
BAD_ZONE_PARTNER_FACTOR = 0.6  # partners per order relative to other zones

# --- delivery time ---
PEAK_HOURS = (19, 20, 21)  # 19:00-21:59
LATE_THRESHOLD_MIN = 45
TARGET_PEAK_AVG_MIN = 41.0
TARGET_OFFPEAK_AVG_MIN = 27.0  # blended works out to ~32 min at 38% peak share
TARGET_LATE_RATE = 0.184
TARGET_TOP3_ZONE_LATE_SHARE = 0.31

# hour-of-day order weights; peak hours are fixed to 38% of orders
OFFPEAK_HOUR_WEIGHTS = {
    0: 1.0, 1: 0.5, 7: 0.5, 8: 1.0, 9: 1.5, 10: 2.0, 11: 4.0, 12: 7.0,
    13: 7.5, 14: 5.0, 15: 3.0, 16: 2.5, 17: 3.0, 18: 4.5, 22: 4.0, 23: 2.0,
}
PEAK_HOUR_WEIGHTS = {19: 0.12, 20: 0.14, 21: 0.12}

# how loaded the kitchens and roads are by hour (0 = quiet); scaled by a fitted factor
HOUR_LOAD = {11: 0.10, 12: 0.25, 13: 0.25, 14: 0.10, 18: 0.30, 19: 0.85, 20: 1.00, 21: 0.90, 22: 0.35, 23: 0.10}

PREP_BASE_MIN = 11.0
TRAVEL_BASE_MIN = 14.0
DELIVERY_NOISE_SIGMA = 0.40      # lognormal noise on prep and travel
INCIDENT_PEAK_FACTOR = 1.5       # incidents are 1.5x likelier at peak
INCIDENT_DELAY_MIN = (10, 30)    # extra minutes when an incident happens

# --- restaurants ---
N_BAD_RESTAURANTS = 22
TARGET_BAD_REST_LATE_SHARE = 0.27
TARGET_BAD_REST_REFUND_SHARE = 0.19
TARGET_TOP12_ORDER_SHARE = 0.58
SAME_ZONE_BOOST = 3.0  # customers are 3x likelier to order from their own zone
COMMISSION_RATES = [0.18, 0.20, 0.22, 0.24, 0.25]
COMMISSION_WEIGHTS = [0.15, 0.25, 0.30, 0.20, 0.10]

# --- revenue ---
N_DISCOUNTED_ORDERS = 165_000  # 33%
TARGET_AOV_DISCOUNTED = 385.0
TARGET_AOV_ORGANIC = 512.0
DELIVERY_FEE = 25
PAYOUT_BASE = 30.0
PAYOUT_PER_TRAVEL_MIN = 0.6
REFUND_BASE_PROB = 0.025  # refunds for reasons other than lateness

# --- customers ---
DISCOUNT_ACQUIRED_SHARE = 0.263  # needed for 24% / 43% repeat to blend to 38%
TARGET_REPEAT_ONTIME = 0.41
TARGET_REPEAT_LATE = 0.26
DISCOUNT_REPEAT_PENALTY = 0.19   # pp lower repeat for discount-acquired customers
REPEAT_CURVE_MID_MIN = 45        # repeat probability falls off around the late threshold
REPEAT_CURVE_WIDTH_MIN = 6
MEAN_ACTIVE_DAYS = 200           # mean time before a customer stops ordering
NON_REPEATER_GAP_DAYS = 60       # mean wait beyond 31 days for a non-repeater's second order
NON_REPEATER_RATE_FACTOR = 0.4   # non-repeaters order at 40% of a repeater's rate
ACQUISITION_SKEW = 0.85          # <1 = acquisitions grow through the year
WEEKDAY_VOLUME_FACTOR = 0.8      # Mon-Thu volume relative to Fri-Sun
TARGET_TOP_DECILE_REV_SHARE = 0.34
LAST_ACQUISITION_DAY = 333  # 30 Nov, so every customer has a full 30-day window

# --- promotions ---
# rule: who is eligible. flat campaigns are the three loss-makers;
# their flat value is solved so the average contribution margin is TARGET_BAD_CAMPAIGN_MARGIN
PROMOTIONS = [
    # code, name, type, pct, cap, free_delivery, start, end, rule, min_order
    ("WELCOME20", "New user 20% off", "percent", 20, 60, False, "2025-01-01", "2025-12-31", "first_order", 0),
    ("SAVE15", "Everyday 15% off", "percent", 15, 50, False, "2025-01-01", "2025-12-31", "any", 0),
    ("WEEKEND15", "Weekend 15% off", "percent", 15, 60, False, "2025-01-01", "2025-12-31", "weekend", 0),
    ("LUNCH25", "Lunch 25% off", "percent", 25, 60, False, "2025-01-01", "2025-12-31", "lunch", 0),
    ("MONSOON20", "Monsoon 20% off", "percent", 20, 60, False, "2025-06-15", "2025-09-15", "any", 0),
    ("IPLFEAST", "IPL match-night flat off + free delivery", "flat", None, None, True, "2025-03-22", "2025-06-03", "any", 299),
    ("FREEDOMFEAST", "Independence week flat off + free delivery", "flat", None, None, True, "2025-07-20", "2025-08-31", "any", 299),
    ("DIWALIFEAST", "Diwali flat off + free delivery", "flat", None, None, True, "2025-10-01", "2025-11-10", "any", 299),
]
BAD_CAMPAIGN_ORDERS = {"IPLFEAST": 16_000, "FREEDOMFEAST": 11_000, "DIWALIFEAST": 13_000}
BAD_CAMPAIGN_OFFSETS = {"IPLFEAST": 10.0, "FREEDOMFEAST": -10.0, "DIWALIFEAST": 0.0}
TARGET_BAD_CAMPAIGN_MARGIN = -47.0
WELCOME_SHARE_OF_FIRST_ORDERS = 0.85
