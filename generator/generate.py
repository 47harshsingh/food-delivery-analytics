"""Generate the synthetic food-delivery dataset (7 tables) as CSVs.

Usage:  python -m generator.generate --out data

The effects the analysis looks for are injected on purpose and calibrated
against the targets in params.py. Nothing here is real data.
"""

import argparse
import itertools
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import brentq, least_squares

from . import params as P
from .entities import build_menus, build_partners, build_promotions, build_restaurants, build_zones

YEAR_START = date(P.YEAR, 1, 1)
DAYS_IN_YEAR = 365
KMAX = 10  # max line picks per order
HOUR_LOAD = np.array([P.HOUR_LOAD.get(h, 0.0) for h in range(24)])


def hour_probs():
    p = np.zeros(24)
    off = np.array(list(P.OFFPEAK_HOUR_WEIGHTS.values()))
    p[list(P.OFFPEAK_HOUR_WEIGHTS)] = off / off.sum() * (1 - sum(P.PEAK_HOUR_WEIGHTS.values()))
    p[list(P.PEAK_HOUR_WEIGHTS)] = list(P.PEAK_HOUR_WEIGHTS.values())
    return p / p.sum()


# ---------------------------------------------------------------- restaurant choice

def choice_matrix(zones, rest, sigma):
    """P(restaurant | customer zone): popularity x same-zone boost, same city only."""
    pop = np.exp(sigma * rest.pop_z.values)
    same_city = zones.city.to_numpy(dtype=object)[:, None] == rest.city.to_numpy(dtype=object)[None, :]
    same_zone = zones.zone_id.values[:, None] == rest.zone_id.values[None, :]
    w = pop[None, :] * same_city * np.where(same_zone, P.SAME_ZONE_BOOST, 1.0)
    return w / w.sum(axis=1, keepdims=True)


def expected_rest_share(zones, rest, sigma):
    return zones.share.values @ choice_matrix(zones, rest, sigma)


def top_share(shares, frac):
    k = int(round(len(shares) * frac))
    return np.sort(shares)[::-1][:k].sum()


def calibrate_popularity(zones, rest):
    f = lambda s: top_share(expected_rest_share(zones, rest, s), 0.12) - P.TARGET_TOP12_ORDER_SHARE
    return brentq(f, 0.1, 4.0)


def pick_restaurants(rng, zone_idx, W):
    out = np.empty(len(zone_idx), dtype=np.int64)
    cum = np.cumsum(W, axis=1)
    for z in range(W.shape[0]):
        m = zone_idx == z
        u = rng.random(m.sum())
        out[m] = np.minimum(np.searchsorted(cum[z], u * cum[z, -1]), W.shape[1] - 1)
    return out


# ---------------------------------------------------------------- delivery time

def delivery_draws(rng, n):
    return {"zp": rng.standard_normal(n), "zt": rng.standard_normal(n),
            "u_inc": rng.random(n), "u_delay": rng.random(n)}


def delivery_minutes(theta, hours, zone_idx, rest_idx, draws, zone_mult, zone_bad, rest_mult, rest_bad):
    """Prep (restaurant) + travel (zone, incl. occasional rider delays) in whole minutes."""
    s, f, q, mz, mr = theta
    sig = P.DELIVERY_NOISE_SIGMA
    peak = np.isin(hours, P.PEAK_HOURS)
    pf = 1.0 + f * HOUR_LOAD[hours]
    zm = zone_mult[zone_idx] * np.where(zone_bad[zone_idx], mz, 1.0)
    rm = rest_mult[rest_idx] * np.where(rest_bad[rest_idx], mr, 1.0)
    prep = P.PREP_BASE_MIN * s * rm * pf * np.exp(sig * draws["zp"] - sig ** 2 / 2)
    travel = P.TRAVEL_BASE_MIN * s * zm * pf * np.exp(sig * draws["zt"] - sig ** 2 / 2)
    # incidents (rider reassigned, rain, address issues): more likely at peak
    incident = draws["u_inc"] < q * np.where(peak, P.INCIDENT_PEAK_FACTOR, 1.0)
    lo, hi = P.INCIDENT_DELAY_MIN
    travel = travel + incident * (lo + (hi - lo) * draws["u_delay"])
    return np.maximum(np.rint(prep), 3), np.maximum(np.rint(travel), 4)


def delivery_metrics(total, peak, zone_idx, rest_bad_flag, n_zones):
    late = total > P.LATE_THRESHOLD_MIN
    late_by_zone = np.bincount(zone_idx[late], minlength=n_zones)
    return {
        "peak_avg": total[peak].mean(),
        "offpeak_avg": total[~peak].mean(),
        "late_rate": late.mean(),
        "top3_zone_late_share": np.sort(late_by_zone)[::-1][:3].sum() / late.sum(),
        "bad_rest_late_share": rest_bad_flag[late].mean(),
    }


def fit_delivery(hours, zone_idx, rest_idx, draws, ctx, fixed=None, x0=(0.8, 0.6, 0.15, 1.9, 2.2)):
    """Solve the 5 delivery parameters so the 5 delivery targets hold.

    fixed: orders whose minutes are already set (first orders), included in the metrics.
    """
    zone_mult, zone_bad, rest_mult, rest_bad, n_zones = ctx
    peak = np.isin(hours, P.PEAK_HOURS)
    if fixed is not None:
        peak_all = np.concatenate([fixed["peak"], peak])
        zone_all = np.concatenate([fixed["zone_idx"], zone_idx])
        bad_all = np.concatenate([fixed["rest_bad"], rest_bad[rest_idx]])
    else:
        peak_all, zone_all, bad_all = peak, zone_idx, rest_bad[rest_idx]

    def resid(theta):
        prep, travel = delivery_minutes(theta, hours, zone_idx, rest_idx, draws, zone_mult, zone_bad, rest_mult, rest_bad)
        total = prep + travel
        if fixed is not None:
            total = np.concatenate([fixed["total"], total])
        m = delivery_metrics(total, peak_all, zone_all, bad_all, n_zones)
        return [m["peak_avg"] - P.TARGET_PEAK_AVG_MIN,
                m["offpeak_avg"] - P.TARGET_OFFPEAK_AVG_MIN,
                100 * (m["late_rate"] - P.TARGET_LATE_RATE),
                100 * (m["top3_zone_late_share"] - P.TARGET_TOP3_ZONE_LATE_SHARE),
                100 * (m["bad_rest_late_share"] - P.TARGET_BAD_REST_LATE_SHARE)]

    fit = least_squares(resid, x0=list(x0), bounds=([0.5, 0.0, 0.0, 1.0, 1.0], [2.0, 2.0, 0.4, 4.0, 5.0]),
                        diff_step=1e-2)
    return fit.x, np.array(resid(fit.x))


# ---------------------------------------------------------------- customers

def repeat_probability(first_minutes, disc_acq):
    """P(second order within 30 days): a discount penalty plus a smooth penalty that ramps up
    as the first delivery gets slower. Level and ramp size are solved so the on-time and late
    groups land on their targets."""
    s = 1 / (1 + np.exp(-(first_minutes - P.REPEAT_CURVE_MID_MIN) / P.REPEAT_CURVE_WIDTH_MIN))
    late = first_minutes > P.LATE_THRESHOLD_MIN
    d = P.DISCOUNT_REPEAT_PENALTY * disc_acq
    # E[p | group] = c0 - mean(d) - L * mean(s)  ->  two linear equations in (c0, L)
    A = np.array([[1, -s[~late].mean()], [1, -s[late].mean()]])
    rhs = np.array([P.TARGET_REPEAT_ONTIME + d[~late].mean(), P.TARGET_REPEAT_LATE + d[late].mean()])
    c0, L = np.linalg.solve(A, rhs)
    return np.clip(c0 - d - L * s, 0.01, 0.99)


def customer_timelines(rng, repeat):
    """First order day, second order day and how many further orders each customer places.

    Customers order as a Poisson process at their own rate until they churn. Repeaters order
    again within 30 days; everyone else waits at least 31. Orders that would fall after
    31 Dec are simply not in the data, as in a real extract.
    """
    n_c = len(repeat)
    end = DAYS_IN_YEAR - 1
    t0 = np.floor((P.LAST_ACQUISITION_DAY + 1) * rng.random(n_c) ** P.ACQUISITION_SKEW).astype(int)
    life = rng.exponential(P.MEAN_ACTIVE_DAYS, n_c)
    gap = np.where(repeat, rng.integers(1, 31, n_c), 31 + np.floor(rng.exponential(P.NON_REPEATER_GAP_DAYS, n_c)))
    life = np.where(repeat, np.maximum(life, gap), life)  # a repeater is still active at their repeat
    t1 = t0 + gap.astype(int)
    active_end = np.minimum(end, t0 + life)
    has_second = repeat | (t1 <= active_end)
    window = np.where(has_second, np.maximum(active_end - t1, 0), 0)

    u_g, u_p, z_rev = rng.random(n_c), rng.random(n_c), rng.standard_normal(n_c)
    rel = np.where(repeat, 1.0, P.NON_REPEATER_RATE_FACTOR)
    base_orders = n_c + has_second.sum()

    def rates(k):
        g = stats.gamma.ppf(u_g, a=k, scale=1 / k)  # mean 1, dispersion set by k
        exposure = (g * rel * window).sum()
        m = (P.N_ORDERS - base_orders) / exposure  # mean daily rate that fills N_ORDERS
        return m * g * rel

    def counts(k):
        lam = rates(k) * window
        return 1 + has_second + stats.poisson.ppf(u_p, lam).astype(np.int64)

    def top_decile_share(k):
        n = counts(k)
        rev = n * 470 + np.sqrt(n) * 470 * 0.45 * z_rev  # rough per-customer revenue
        return top_share(rev, 0.10) / rev.sum()

    k = brentq(lambda k: top_decile_share(k) - P.TARGET_TOP_DECILE_REV_SHARE, 0.05, 20)
    n = counts(k)

    # Poisson noise leaves the total a little off N_ORDERS; nudge customers who order again later
    diff = P.N_ORDERS - n.sum()
    if diff > 0:
        eligible = np.flatnonzero(window > 0)
        n[rng.choice(eligible, diff, replace=False, p=window[eligible] / window[eligible].sum())] += 1
    elif diff < 0:
        eligible = np.flatnonzero(n > 1 + has_second)
        n[rng.choice(eligible, -diff, replace=False)] -= 1
    return t0, t1, window, n, k


def later_order_days(rng, t1, window):
    """Spread a customer's later orders over their active window, with busier weekends."""
    day = t1 + np.floor(rng.random(len(t1)) * (window + 1)).astype(int)
    for _ in range(3):
        wd = (day + YEAR_START.weekday()) % 7
        redraw = (wd < 4) & (rng.random(len(day)) > P.WEEKDAY_VOLUME_FACTOR)  # Mon-Thu
        day[redraw] = t1[redraw] + np.floor(rng.random(redraw.sum()) * (window[redraw] + 1)).astype(int)
    return day


# ---------------------------------------------------------------- money

def campaign_eligibility(promos, day, hour, is_first, weekday):
    out = {}
    for code, _, _, _, _, _, start, end, rule, _ in promos:
        s = (date.fromisoformat(start) - YEAR_START).days
        e = (date.fromisoformat(end) - YEAR_START).days
        ok = (day >= s) & (day <= e)
        if rule == "first_order":
            ok &= is_first
        elif rule == "weekend":
            ok &= weekday >= 5
        elif rule == "lunch":
            ok &= (hour >= 11) & (hour <= 14)
        out[code] = ok
    return out


def assign_campaigns(rng, orders, discounted):
    codes = [p[0] for p in P.PROMOTIONS]
    elig = campaign_eligibility(P.PROMOTIONS, orders.day.values, orders.hour.values,
                                orders.is_first.values, orders.weekday.values)
    promo = np.full(len(orders), -1)

    for code, n_target in P.BAD_CAMPAIGN_ORDERS.items():
        pool = np.flatnonzero(discounted & (promo < 0) & elig[code])
        assert len(pool) > 1.3 * n_target, f"{code}: window too small ({len(pool)} discounted orders)"
        promo[rng.choice(pool, n_target, replace=False)] = codes.index(code)

    good = ["WELCOME20", "SAVE15", "WEEKEND15", "LUNCH25", "MONSOON20"]
    weights = np.array([0.0, 1.0, 1.2, 1.2, 1.5])
    rest = np.flatnonzero(discounted & (promo < 0))
    first = orders.is_first.values[rest]
    # most discounted first orders use the welcome offer
    use_welcome = first & (rng.random(len(rest)) < P.WELCOME_SHARE_OF_FIRST_ORDERS)
    promo[rest[use_welcome]] = codes.index("WELCOME20")
    rest = rest[~use_welcome]
    E = np.column_stack([elig[c][rest] for c in good]) * weights
    E[:, 1] = np.maximum(E[:, 1], 1.0)  # SAVE15 is always available
    cum = np.cumsum(E / E.sum(axis=1, keepdims=True), axis=1)
    pick = (rng.random(len(rest))[:, None] > cum).sum(axis=1)
    promo[rest] = [codes.index(good[i]) for i in pick]
    return promo


def discount_amounts(gross, promo, flat_values):
    disc = np.zeros(len(gross))
    for i, (code, _, typ, pct, cap, *_rest) in enumerate(P.PROMOTIONS):
        m = promo == i
        if typ == "percent":
            disc[m] = np.minimum(np.floor(gross[m] * pct / 100), cap)
        else:
            disc[m] = flat_values[code]
    return disc


def build_money(rng, orders, rest, menu_prices, menu_len, promo, travel):
    n = len(orders)
    r = orders.rest_idx.values
    pick_u = rng.random((n, KMAX))
    item_idx = np.floor(pick_u * menu_len[r][:, None]).astype(np.int64)
    item_price = menu_prices[r[:, None], item_idx]
    cum = np.cumsum(item_price, axis=1)
    menu_mean = menu_prices.sum(axis=1) / menu_len
    size = np.exp(0.4 * rng.standard_normal(n) - 0.08)

    codes = [p[0] for p in P.PROMOTIONS]
    flat_codes = [c for c in codes if c in P.BAD_CAMPAIGN_ORDERS]
    flat_idx = [codes.index(c) for c in flat_codes]
    is_flat = np.isin(promo, flat_idx)
    disc_mask = promo >= 0
    free_delivery = is_flat
    comm = rest.commission_rate.values[r]
    payout = np.round(P.PAYOUT_BASE + P.PAYOUT_PER_TRAVEL_MIN * travel, 2)
    fee = np.where(free_delivery, 0, P.DELIVERY_FEE)

    scale_o, scale_d = P.TARGET_AOV_ORGANIC, P.TARGET_AOV_DISCOUNTED + 60
    flat = {c: 100.0 for c in flat_codes}
    counts = np.array([P.BAD_CAMPAIGN_ORDERS[c] for c in flat_codes], dtype=float)
    offsets = np.array([P.BAD_CAMPAIGN_OFFSETS[c] for c in flat_codes])

    def basket(scale_o, scale_d):
        target = np.where(disc_mask, scale_d, scale_o) * size
        k = np.clip(np.rint(target / menu_mean[r]), 1, KMAX).astype(int)
        gross = cum[np.arange(n), k - 1]
        short = is_flat & (gross < 299)  # flat offers need a Rs 299 minimum basket
        k[short] = np.argmax(cum[short] >= 299, axis=1) + 1
        return k, cum[np.arange(n), k - 1].astype(float)

    def margin(gross, disc):
        return comm * gross + fee - payout - disc

    for it in range(12):
        k, gross = basket(scale_o, scale_d)
        disc = discount_amounts(gross, promo, flat)
        net = gross - disc
        scale_o *= P.TARGET_AOV_ORGANIC / net[~disc_mask].mean()
        scale_d *= P.TARGET_AOV_DISCOUNTED / net[disc_mask].mean()
        if it < 8:
            base = (comm * gross + fee - payout)[is_flat].mean()
            d0 = base - P.TARGET_BAD_CAMPAIGN_MARGIN - (offsets * counts).sum() / counts.sum()
            flat = {c: d0 + o for c, o in zip(flat_codes, offsets)}
        elif it == 8:
            # whole-rupee flat values: pick the floor/ceil combination closest to target
            best = None
            for combo in itertools.product(*[(np.floor(flat[c]), np.ceil(flat[c])) for c in flat_codes]):
                trial = dict(zip(flat_codes, combo))
                m = margin(gross, discount_amounts(gross, promo, trial))[is_flat].mean()
                if best is None or abs(m - P.TARGET_BAD_CAMPAIGN_MARGIN) < best[0]:
                    best = (abs(m - P.TARGET_BAD_CAMPAIGN_MARGIN), trial)
            flat = {c: int(v) for c, v in best[1].items()}

    k, gross = basket(scale_o, scale_d)
    disc = discount_amounts(gross, promo, flat)
    return {
        "k": k, "item_idx": item_idx, "gross": gross, "discount": disc, "net": gross - disc,
        "fee": fee, "payout": payout, "flat_values": flat,
    }


# ---------------------------------------------------------------- main

def generate(out_dir, seed=P.SEED):
    t_start = time.time()
    rng = np.random.default_rng(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    zones = build_zones(rng)
    rest = build_restaurants(rng, zones)
    menus, menu_prices, menu_len = build_menus(rest)

    sigma_pop = calibrate_popularity(zones, rest)
    W = choice_matrix(zones, rest, sigma_pop)
    exp_share = expected_rest_share(zones, rest, sigma_pop)

    # underperformers: 22 busy restaurants (rank 5-100 by expected volume)
    ranked = np.argsort(exp_share)[::-1]
    bad_rest_idx = rng.choice(ranked[5:100], P.N_BAD_RESTAURANTS, replace=False)
    rest_bad = np.zeros(len(rest), dtype=bool)
    rest_bad[bad_rest_idx] = True
    zone_mult = np.exp(rng.normal(0, 0.06, len(zones)))
    zone_bad = zones.is_bad.values
    rest_mult = rest.prep_mult.values
    ctx = (zone_mult, zone_bad, rest_mult, rest_bad, len(zones))
    hp = hour_probs()

    # pass 1: fit delivery parameters on a simulated order sample (used for first orders)
    n_sim = 500_000
    s_zone = rng.choice(len(zones), size=n_sim, p=zones.share.values)
    theta, resid = fit_delivery(rng.choice(24, size=n_sim, p=hp), s_zone, pick_restaurants(rng, s_zone, W),
                                delivery_draws(rng, n_sim), ctx)
    print(f"popularity sigma={sigma_pop:.3f}; underperformers' expected order share={exp_share[rest_bad].sum():.3f}")
    print("pass 1 delivery params (scale, hour load, incident p, bad zone, bad restaurant):", np.round(theta, 3),
          "residuals:", np.round(resid, 3))

    # customers and their first order
    n_c = P.N_CUSTOMERS
    c_zone = rng.choice(len(zones), size=n_c, p=zones.share.values)
    disc_acq = np.zeros(n_c, dtype=bool)
    disc_acq[rng.choice(n_c, int(round(P.DISCOUNT_ACQUIRED_SHARE * n_c)), replace=False)] = True
    f_hour = rng.choice(24, size=n_c, p=hp)
    f_rest = pick_restaurants(rng, c_zone, W)
    f_prep, f_travel = delivery_minutes(theta, f_hour, c_zone, f_rest, delivery_draws(rng, n_c),
                                        zone_mult, zone_bad, rest_mult, rest_bad)
    f_late = (f_prep + f_travel) > P.LATE_THRESHOLD_MIN
    repeat = rng.random(n_c) < repeat_probability(f_prep + f_travel, disc_acq)
    t0, t1, window, n_orders, k_disp = customer_timelines(rng, repeat)
    print(f"first-order late rate={f_late.mean():.4f}; repeat flag rate={repeat.mean():.4f}; "
          f"order-rate dispersion k={k_disp:.3f}")

    # explode to orders
    cust = np.repeat(np.arange(n_c), n_orders)
    starts = np.repeat(np.cumsum(n_orders) - n_orders, n_orders)
    seq = np.arange(len(cust)) - starts
    first = seq == 0
    later_day = later_order_days(rng, t1[cust], window[cust])
    day = np.where(first, t0[cust], np.where(seq == 1, t1[cust], later_day))
    zone_idx = c_zone[cust]
    hour = np.where(first, f_hour[cust], rng.choice(24, size=len(cust), p=hp))
    rest_idx = np.where(first, f_rest[cust], pick_restaurants(rng, zone_idx, W))

    # pass 2: refit on the actual repeat orders so the full table lands on target
    nf = ~first
    draws = delivery_draws(rng, nf.sum())
    fixed = {"total": (f_prep + f_travel)[cust[first]], "peak": np.isin(hour[first], P.PEAK_HOURS),
             "zone_idx": zone_idx[first], "rest_bad": rest_bad[rest_idx[first]]}
    theta2, resid2 = fit_delivery(hour[nf], zone_idx[nf], rest_idx[nf], draws, ctx, fixed=fixed, x0=theta)
    print("pass 2 delivery params:", np.round(theta2, 3), "residuals:", np.round(resid2, 3))
    prep, travel = np.empty(len(cust)), np.empty(len(cust))
    prep[first], travel[first] = f_prep[cust[first]], f_travel[cust[first]]
    prep[nf], travel[nf] = delivery_minutes(theta2, hour[nf], zone_idx[nf], rest_idx[nf], draws,
                                            zone_mult, zone_bad, rest_mult, rest_bad)
    minute, second = rng.integers(0, 60, len(cust)), rng.integers(0, 60, len(cust))

    orders = pd.DataFrame({"cust": cust, "is_first": first, "day": day, "hour": hour, "minute": minute,
                           "second": second, "zone_idx": zone_idx, "rest_idx": rest_idx,
                           "prep": prep.astype(int), "travel": travel.astype(int)})
    orders["weekday"] = (orders.day + YEAR_START.weekday()) % 7
    orders = orders.sort_values(["day", "hour", "minute", "second", "cust"], kind="mergesort").reset_index(drop=True)
    orders["order_id"] = np.arange(1, len(orders) + 1)

    # delivery partners, matched within the delivery zone
    zone_vol = np.bincount(orders.zone_idx, minlength=len(zones)).astype(float)
    partners = build_partners(rng, zones, zone_vol)
    p_zone_idx = partners.zone_id.values - 1
    orders["partner_id"] = 0
    for z in range(len(zones)):
        m = (orders.zone_idx == z).values
        pz = partners[p_zone_idx == z]
        orders.loc[m, "partner_id"] = rng.choice(pz.partner_id.values, m.sum(),
                                                 p=pz.activity.values / pz.activity.sum())

    # which orders carry a discount: every discount-acquired first order + random repeat orders
    discounted = orders.is_first.values & disc_acq[orders.cust.values]
    need = P.N_DISCOUNTED_ORDERS - discounted.sum()
    pool = np.flatnonzero(~orders.is_first.values)
    discounted[rng.choice(pool, need, replace=False)] = True
    promo = assign_campaigns(rng, orders, discounted)

    money = build_money(rng, orders, rest, menu_prices, menu_len, promo, orders.travel.values.astype(float))
    print("flat values for loss-making campaigns:", money["flat_values"])

    # refunds: a base rate plus a lateness effect, sized so underperformers carry ~19% of refunds
    late = (orders.prep + orders.travel).values > P.LATE_THRESHOLD_MIN
    bad_o = rest_bad[orders.rest_idx.values]
    a, tgt = P.REFUND_BASE_PROB, P.TARGET_BAD_REST_REFUND_SHARE
    b = a * (tgt * len(orders) - bad_o.sum()) / ((late & bad_o).sum() - tgt * late.sum())
    refunded = rng.random(len(orders)) < (a + b * late)
    full = rng.random(len(orders)) < 0.4
    refund_amt = np.where(refunded, np.where(full, money["net"], np.round(money["net"] * 0.5, 2)), 0.0)

    write_tables(out, zones, rest, menus, partners, orders, money, promo, refunded, refund_amt, rng)
    print(f"done in {time.time() - t_start:.0f}s -> {out.resolve()}")


def write_tables(out, zones, rest, menus, partners, orders, money, promo, refunded, refund_amt, rng):
    zones[["zone_id", "zone_name", "city"]].to_csv(out / "zones.csv", index=False, lineterminator="\n")

    rest[["restaurant_id", "restaurant_name", "zone_id", "cuisine", "commission_rate", "onboarded_date"]].to_csv(
        out / "restaurants.csv", index=False, lineterminator="\n")

    partners[["partner_id", "zone_id", "vehicle_type", "joined_date"]].to_csv(out / "delivery_partners.csv", index=False, lineterminator="\n")

    build_promotions(money["flat_values"]).to_csv(out / "promotions.csv", index=False, lineterminator="\n")

    first = orders[orders.is_first].sort_values("cust")
    customers = pd.DataFrame({
        "customer_id": first.cust.values + 1,
        "zone_id": first.zone_idx.values + 1,
        "signup_date": [YEAR_START + timedelta(days=int(d)) for d in first.day.values],
        "platform": rng.choice(["android", "ios", "web"], size=len(first), p=[0.68, 0.27, 0.05]),
    })
    customers.to_csv(out / "customers.csv", index=False, lineterminator="\n")

    ts = (pd.Timestamp(YEAR_START) + pd.to_timedelta(orders.day, unit="D") + pd.to_timedelta(orders.hour, unit="h")
          + pd.to_timedelta(orders.minute, unit="m") + pd.to_timedelta(orders.second, unit="s"))
    promo_id = pd.array(np.where(promo >= 0, promo + 1, 0), dtype="Int64")
    promo_id[promo < 0] = pd.NA
    o = pd.DataFrame({
        "order_id": orders.order_id.values,
        "customer_id": orders.cust.values + 1,
        "restaurant_id": orders.rest_idx.values + 1,
        "partner_id": orders.partner_id.values,
        "zone_id": orders.zone_idx.values + 1,
        "promo_id": promo_id,
        "order_ts": ts.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "gross_amount": money["gross"].astype(int),
        "discount_amount": money["discount"].astype(int),
        "net_amount": money["net"].astype(int),
        "delivery_fee": money["fee"].astype(int),
        "partner_payout": money["payout"],
        "prep_minutes": orders.prep.values,
        "travel_minutes": orders.travel.values,
        "delivery_minutes": (orders.prep + orders.travel).values,
        "is_refunded": refunded.astype(int),
        "refund_amount": refund_amt,
    })
    o.to_csv(out / "orders.csv", index=False, lineterminator="\n")

    # order lines: the first k picks of each order, duplicates collapsed into quantity
    k, idx = money["k"], money["item_idx"]
    rows = np.repeat(np.arange(len(o)), k)
    col = np.arange(rows.size) - np.repeat(np.cumsum(k) - k, k)
    lines = pd.DataFrame({"row": rows, "item": idx[rows, col]})
    lines = lines.groupby(["row", "item"], sort=True).size().rename("quantity").reset_index()
    r_idx = orders.rest_idx.values[lines.row.values]
    lines["order_id"] = o.order_id.values[lines.row.values]
    lines["item_name"] = [menus[r][i][0] for r, i in zip(r_idx, lines.item.values)]
    lines["category"] = [menus[r][i][1] for r, i in zip(r_idx, lines.item.values)]
    lines["unit_price"] = [menus[r][i][2] for r, i in zip(r_idx, lines.item.values)]
    lines.insert(0, "order_item_id", np.arange(1, len(lines) + 1))
    check = (lines.quantity * lines.unit_price).groupby(lines.order_id).sum()
    assert (check.values == o.gross_amount.values).all(), "order lines don't add up to gross_amount"
    lines[["order_item_id", "order_id", "item_name", "category", "quantity", "unit_price"]].to_csv(
        out / "order_items.csv", index=False, lineterminator="\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--seed", type=int, default=P.SEED)
    args = ap.parse_args()
    generate(args.out, args.seed)
