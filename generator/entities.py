"""Dimension tables: zones, restaurants (with menus), delivery partners, promotions."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import params as P

# (item, category, base price in INR)
CUISINE_MENUS = {
    "North Indian": [("Butter Chicken", "main", 320), ("Dal Makhani", "main", 240), ("Paneer Butter Masala", "main", 270),
                     ("Paneer Tikka", "starter", 260), ("Butter Naan", "side", 50), ("Jeera Rice", "side", 140),
                     ("Chole Bhature", "main", 190)],
    "South Indian": [("Masala Dosa", "main", 120), ("Idli Vada Combo", "main", 90), ("Rava Dosa", "main", 130),
                     ("Mini Meals", "main", 180), ("Filter Coffee", "beverage", 40), ("Medu Vada", "starter", 70)],
    "Biryani": [("Chicken Dum Biryani", "main", 290), ("Mutton Biryani", "main", 380), ("Veg Biryani", "main", 220),
                ("Chicken 65", "starter", 240), ("Raita", "side", 40), ("Double Ka Meetha", "dessert", 110)],
    "Chinese": [("Veg Hakka Noodles", "main", 180), ("Chicken Fried Rice", "main", 210), ("Chilli Paneer", "starter", 230),
                ("Veg Manchurian", "starter", 190), ("Hot and Sour Soup", "starter", 130), ("Schezwan Noodles", "main", 200)],
    "Pizza": [("Margherita Pizza", "main", 250), ("Farmhouse Pizza", "main", 380), ("Pepperoni Pizza", "main", 450),
              ("Garlic Bread", "side", 130), ("Choco Lava Cake", "dessert", 110)],
    "Burgers": [("Classic Veg Burger", "main", 130), ("Crispy Chicken Burger", "main", 190), ("Double Patty Burger", "main", 260),
                ("Peri Peri Fries", "side", 120), ("Cold Coffee", "beverage", 140)],
    "Rolls": [("Paneer Kathi Roll", "main", 160), ("Chicken Tikka Roll", "main", 180), ("Egg Roll", "main", 120),
              ("Mutton Seekh Roll", "main", 220), ("Masala Fries", "side", 100)],
    "Desserts": [("Brownie Sundae", "dessert", 190), ("Red Velvet Pastry", "dessert", 140), ("Rasmalai (2 pc)", "dessert", 120),
                 ("Belgian Waffle", "dessert", 210), ("Kulfi Falooda", "dessert", 170)],
    "Cafe": [("Cappuccino", "beverage", 160), ("Club Sandwich", "main", 240), ("Pasta Alfredo", "main", 310),
             ("Blueberry Muffin", "dessert", 130), ("Iced Americano", "beverage", 170)],
    "Healthy Bowls": [("Quinoa Salad Bowl", "main", 320), ("Grilled Chicken Bowl", "main", 360), ("Paneer Protein Bowl", "main", 330),
                      ("Cold Pressed Juice", "beverage", 150), ("Greek Yogurt Parfait", "dessert", 180)],
}
CUISINE_WEIGHTS = {"North Indian": 0.20, "South Indian": 0.10, "Biryani": 0.15, "Chinese": 0.13, "Pizza": 0.09,
                   "Burgers": 0.09, "Rolls": 0.07, "Desserts": 0.06, "Cafe": 0.06, "Healthy Bowls": 0.05}
COMMON_ITEMS = [("Masala Chaas", "beverage", 60), ("Soft Drink 500ml", "beverage", 60), ("Gulab Jamun (2 pc)", "dessert", 80)]

NAME_PREFIX = ["Royal", "Urban", "Spice", "Golden", "Green", "Little", "Lucky", "Grand", "Desi", "The Hungry",
               "Old Town", "Saffron", "Tandoor", "Coastal", "Midnight", "Happy", "Fresh", "Mama's", "Chef's"]
NAME_SUFFIX = {
    "North Indian": ["Dhaba", "Rasoi", "Kitchen", "Punjab Grill"], "South Indian": ["Tiffins", "Udupi", "Dosa Corner", "Bhavan"],
    "Biryani": ["Biryani House", "Dum Biryani", "Biryani Co."], "Chinese": ["Wok", "Noodle Bar", "Dragon"],
    "Pizza": ["Pizzeria", "Pizza Co.", "Slice"], "Burgers": ["Burger Joint", "Burgers", "Grill"],
    "Rolls": ["Rolls", "Kathi Junction", "Wraps"], "Desserts": ["Desserts", "Bakehouse", "Sweets"],
    "Cafe": ["Cafe", "Coffee House", "Brew Co."], "Healthy Bowls": ["Bowls", "Greens", "Salad Co."],
}


def split_counts(total, shares):
    """Integer counts proportional to shares that sum exactly to total."""
    shares = np.asarray(shares, dtype=float)
    raw = shares / shares.sum() * total
    counts = np.floor(raw).astype(int)
    counts[np.argsort(raw - counts)[::-1][: total - counts.sum()]] += 1
    return counts


def random_dates(rng, n, start, end):
    span = (end - start).days
    return [start + timedelta(days=int(d)) for d in rng.integers(0, span + 1, n)]


def build_zones(rng):
    rows = []
    for city, names in P.ZONES.items():
        within = rng.uniform(0.18, 0.32, size=len(names))
        within /= within.sum()
        for name, w in zip(names, within):
            rows.append({"zone_name": name, "city": city, "share": P.CITIES[city] * w,
                         "is_bad": name in P.BAD_ZONES})
    zones = pd.DataFrame(rows)
    zones.insert(0, "zone_id", np.arange(1, len(zones) + 1))
    zones["share"] /= zones["share"].sum()
    return zones


def build_restaurants(rng, zones):
    city_counts = split_counts(P.N_RESTAURANTS, list(P.CITIES.values()))
    zone_ids = []
    for city, n in zip(P.CITIES, city_counts):
        cz = zones[zones.city == city]
        zone_ids.extend(rng.choice(cz.zone_id, size=n, p=cz.share / cz.share.sum()))
    zone_ids = np.array(zone_ids)
    n = len(zone_ids)

    cuisines = rng.choice(list(CUISINE_WEIGHTS), size=n, p=list(CUISINE_WEIGHTS.values()))
    zone_lookup = zones.set_index("zone_id")
    names, seen = [], set()
    for zid, c in zip(zone_ids, cuisines):
        name = f"{rng.choice(NAME_PREFIX)} {rng.choice(NAME_SUFFIX[c])}"
        if name in seen:
            name = f"{name} {zone_lookup.loc[zid, 'zone_name']}"
        k = 2
        base = name
        while name in seen:
            name = f"{base} {k}"
            k += 1
        seen.add(name)
        names.append(name)

    rest = pd.DataFrame({
        "restaurant_id": np.arange(1, n + 1),
        "restaurant_name": names,
        "zone_id": zone_ids,
        "cuisine": cuisines,
        "price_level": rng.uniform(0.85, 1.45, n).round(2),
        "commission_rate": rng.choice(P.COMMISSION_RATES, size=n, p=P.COMMISSION_WEIGHTS),
        "onboarded_date": random_dates(rng, n, date(2019, 1, 1), date(2024, 12, 31)),
        # latent: popularity score (scaled later) and prep-speed multiplier
        "pop_z": rng.standard_normal(n),
        "prep_mult": np.exp(rng.normal(0, 0.10, n)),
    })
    rest["city"] = rest.zone_id.map(zone_lookup.city)
    return rest


def build_menus(rest):
    """Per-restaurant menu as padded arrays (prices rounded to Rs 5)."""
    menus = []
    for c, lvl in zip(rest.cuisine, rest.price_level):
        items = CUISINE_MENUS[c] + COMMON_ITEMS
        menus.append([(name, cat, int(round(price * lvl / 5) * 5)) for name, cat, price in items])
    max_len = max(len(m) for m in menus)
    prices = np.zeros((len(menus), max_len), dtype=np.int64)
    lengths = np.array([len(m) for m in menus])
    for i, m in enumerate(menus):
        prices[i, : len(m)] = [p for _, _, p in m]
    return menus, prices, lengths


def build_partners(rng, zones, zone_order_volume):
    supply = np.where(zones.is_bad, P.BAD_ZONE_PARTNER_FACTOR, 1.0) * np.exp(rng.normal(0, 0.08, len(zones)))
    weight = zone_order_volume * supply
    counts = split_counts(P.N_PARTNERS, weight)
    home_zone = np.repeat(zones.zone_id.values, counts)
    n = len(home_zone)
    return pd.DataFrame({
        "partner_id": np.arange(1, n + 1),
        "zone_id": home_zone,
        "vehicle_type": rng.choice(["motorbike", "e-bike", "bicycle"], size=n, p=[0.82, 0.14, 0.04]),
        "joined_date": random_dates(rng, n, date(2021, 1, 1), date(2025, 6, 30)),
        "activity": np.exp(rng.normal(0, 0.5, n)),  # latent: how many shifts they pick up
    })


def build_promotions(flat_values):
    rows = []
    for i, (code, name, typ, pct, cap, free, start, end, rule, min_order) in enumerate(P.PROMOTIONS, start=1):
        rows.append({
            "promo_id": i, "promo_code": code, "campaign_name": name, "discount_type": typ,
            "discount_value": flat_values[code] if typ == "flat" else pct,
            "max_discount": cap if cap is not None else flat_values[code],
            "min_order_value": min_order, "free_delivery": int(free),
            "start_date": start, "end_date": end, "eligibility": rule,
        })
    return pd.DataFrame(rows)
