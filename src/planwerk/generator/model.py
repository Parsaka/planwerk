"""Expected-value model of the Nordwerk business.

Both the line-level generator and the fast aggregate mode (forecast backtest) are built on
these functions, so the two can never drift apart.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from planwerk.generator import config as C
from planwerk.generator.drivers import lci_column
from planwerk.generator.masterdata import MasterData, cost_centre_params
from planwerk.generator.scenario import Scenario

BASE_REVENUE_EUR = 250_000_000.0  # group revenue 2023 at scale 1 (expected)
PL_PRICE_LIST_FX = 4.40          # PLN per EUR used to set the PLN price list in 2023
ORDER_START = "2022-10"          # orders before 2023 create the opening backlog

# Actual overhead inflation (approximately the German CPI path 2023-2025); plan assumptions
# live in the scenario.
OVERHEAD_LEVEL_ACTUAL = {2023: 1.0, 2024: 1.022, 2025: 1.022 * 1.022}
SOCIAL_RATE = {"1000": 0.21, "2000": 0.235, "3000": 0.20}
COUNTRY_COST_LEVEL = {"1000": 1.0, "2000": 1.05, "3000": 0.55}


def periods(first: str, last: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(first, last, freq="M")]


def shift_period(period: str, months: int) -> str:
    return (pd.Period(period, freq="M") + months).strftime("%Y-%m")


def fx_actual(drivers: pd.DataFrame) -> dict[str, float]:
    return dict(zip(drivers["period"], drivers["eur_pln"]))


# --------------------------------------------------------------------------------------
# Prices
# --------------------------------------------------------------------------------------
def list_price_factor(increases: dict, year: int, pg: str) -> float:
    """Cumulative list-price factor relative to the 2022 list."""
    f = 1.0
    for y in range(2023, year + 1):
        f *= 1.0 + increases[y][pg]
    return f


def local_price_level(bukrs: str) -> float:
    """Multiplier that turns a EUR (DE level) list price into the company code's list price."""
    lvl = C.COMPANY_CODES[bukrs]["price_level"]
    if C.COMPANY_CODES[bukrs]["currency"] == "PLN":
        lvl *= PL_PRICE_LIST_FX
    return lvl


def price_conditions(md: MasterData, scenario: Scenario) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sales price list per material, sales organisation and year (condition table, A004/KONP
    style) in two versions: ACT (price list actually in force) and PLN (price list the budget
    assumed). Plus the standard discount per customer group (condition K007 style)."""
    m = md.mara[md.mara["MTART"].isin(["FERT", "HAWA", "DIEN"])][["MATNR", "MATKL", "LIST_PRICE_2022"]]
    rows = []
    for bukrs, cc in C.COMPANY_CODES.items():
        lvl = local_price_level(bukrs)
        for y in (2023, 2024, 2025):
            for version, inc in (("ACT", scenario.price_increase_actual), ("PLN", scenario.price_increase_plan)):
                # the plan of year y knows the actual list prices of earlier years
                f = m["MATKL"].map(lambda g: list_price_factor(
                    {yy: (inc[yy] if yy == y else scenario.price_increase_actual[yy]) for yy in inc}, y, g))
                rows.append(pd.DataFrame(dict(MATNR=m["MATNR"], VKORG=bukrs, DATAB=f"{y}-01-01", DATBI=f"{y}-12-31",
                                              VERSION=version, KBETR=(m["LIST_PRICE_2022"] * f * lvl).round(2),
                                              KONWA=cc["currency"])))
    prices = pd.concat(rows, ignore_index=True)
    disc = pd.DataFrame([dict(KSCHL="K007", KDGRP=k, KBETR=v["discount"]) for k, v in C.SEGMENTS.items()])
    return prices, disc


def material_weights(md: MasterData) -> pd.DataFrame:
    m = md.mara[md.mara["MTART"].isin(["FERT", "HAWA", "DIEN"])][["MATNR", "MATKL", "POPULARITY",
                                                                  "LIST_PRICE_2022"]]
    return m.reset_index(drop=True)


def avg_list_price_2022(md: MasterData) -> dict[str, float]:
    m = material_weights(md)
    return (m.assign(v=m["POPULARITY"] * m["LIST_PRICE_2022"]).groupby("MATKL")["v"].sum()).to_dict()


def segment_shares(md: MasterData) -> pd.DataFrame:
    """Share of each segment in the demand of a (company code, product group)."""
    w = md.knvv.groupby(["VKORG", "KDGRP"])["WEIGHT"].sum().reset_index()
    rows = []
    for _, r in w.iterrows():
        for pg in C.PRODUCT_GROUPS:
            rows.append(dict(BUKRS=r["VKORG"], KDGRP=r["KDGRP"], MATKL=pg,
                             W=r["WEIGHT"] * C.SEGMENTS[r["KDGRP"]]["affinity"][pg]))
    df = pd.DataFrame(rows)
    df["SEG_SHARE"] = df["W"] / df.groupby(["BUKRS", "MATKL"])["W"].transform("sum")
    return df.drop(columns="W")


def avg_discount(seg_shares: pd.DataFrame) -> pd.DataFrame:
    d = seg_shares.assign(D=seg_shares["KDGRP"].map(lambda s: C.SEGMENTS[s]["discount"]) * seg_shares["SEG_SHARE"])
    return d.groupby(["BUKRS", "MATKL"])["D"].sum().rename("AVG_DISC").reset_index()


# --------------------------------------------------------------------------------------
# Demand
# --------------------------------------------------------------------------------------
def base_units_per_year(md: MasterData, scale: float) -> pd.DataFrame:
    """Expected units per year 2023 (volume level 1.0) per company code, segment, product group."""
    seg = segment_shares(md)
    disc = avg_discount(seg)
    lp = avg_list_price_2022(md)
    rows = []
    for bukrs, cc in C.COMPANY_CODES.items():
        for pg, g in C.PRODUCT_GROUPS.items():
            d = float(disc[(disc["BUKRS"] == bukrs) & (disc["MATKL"] == pg)]["AVG_DISC"].iloc[0])
            net_eur = lp[pg] * list_price_factor(C.PRICE_INCREASE, 2023, pg) * cc["price_level"] * (1 - d)
            revenue = BASE_REVENUE_EUR * scale * cc["share"] * g["revenue_share"]
            rows.append(dict(BUKRS=bukrs, MATKL=pg, UNITS_YEAR=revenue / net_eur))
    base = pd.DataFrame(rows)
    out = seg.merge(base, on=["BUKRS", "MATKL"])
    out["UNITS_YEAR"] = out["UNITS_YEAR"] * out["SEG_SHARE"]
    return out[["BUKRS", "KDGRP", "MATKL", "UNITS_YEAR"]]


def demand_noise(rng: np.random.Generator, n_periods: int, level: float) -> np.ndarray:
    """AR(1) multiplicative noise, phi = 0.6, sd = 4 %."""
    e = np.zeros(n_periods)
    shocks = rng.normal(0.0, 0.04 * level, n_periods)
    for t in range(n_periods):
        e[t] = (0.6 * e[t - 1] if t else 0.0) + shocks[t]
    return np.exp(e - 0.5 * (0.04 * level) ** 2 / (1 - 0.36))


def shift_factor(scenario: Scenario, bukrs: str, pg: str, period: str) -> float:
    f = 1.0
    for s in scenario.demand_shifts:
        if (s.company_code in (None, bukrs)) and (s.product_group in (None, pg)) and period >= s.start_period:
            f *= s.factor
    return f


def expected_order_units(md: MasterData, scenario: Scenario, scale: float, rng: np.random.Generator,
                         last_period: str = C.LAST_PERIOD, plan: bool = False,
                         plan_year: int | None = None) -> pd.DataFrame:
    """Expected order-intake units per (BUKRS, KDGRP, MATKL, PERIOD).

    ``plan=True`` returns what the controller expected when the plan for ``plan_year``
    was set: no noise, no shifts, plan volume level.
    """
    base = base_units_per_year(md, scale)
    pers = periods(ORDER_START, last_period)
    years = np.array([int(p[:4]) for p in pers])
    months = np.array([int(p[5:7]) for p in pers])
    season = C.SEASONALITY[months - 1] / 12.0
    frames = []
    noise_cache: dict[tuple[str, str], np.ndarray] = {}
    for _, r in base.iterrows():
        key = (r["BUKRS"], r["MATKL"])
        if plan:
            vol = np.array([scenario.year_volume_plan.get(max(y, 2023), 1.0) if y == plan_year else
                            scenario.year_volume_actual.get(max(y, 2023), 1.0) for y in years])
            mult = np.ones(len(pers))
        else:
            vol = np.array([scenario.year_volume_actual.get(max(y, 2023), 1.0) for y in years])
            if key not in noise_cache:
                noise_cache[key] = demand_noise(rng, len(pers), scenario.noise_level)
            mult = noise_cache[key] * np.array([shift_factor(scenario, key[0], key[1], p) for p in pers])
        units = r["UNITS_YEAR"] * season * vol * mult
        frames.append(pd.DataFrame(dict(BUKRS=r["BUKRS"], KDGRP=r["KDGRP"], MATKL=r["MATKL"],
                                        PERIOD=pers, UNITS=units)))
    return pd.concat(frames, ignore_index=True)


def customer_loss_share(md: MasterData, scenario: Scenario) -> list[tuple]:
    """Resolve customer losses to concrete customers: (kunnr, bukrs, seg, factor, start, share)."""
    out = []
    for loss in scenario.customer_losses:
        seg = md.knvv[(md.knvv["VKORG"] == loss.company_code) & (md.knvv["KDGRP"] == loss.segment)]
        top = seg.sort_values("WEIGHT", ascending=False).iloc[0]
        share = float(top["WEIGHT"] / seg["WEIGHT"].sum())
        loss.kunnr = str(top["KUNNR"])
        out.append((loss.kunnr, loss.company_code, loss.segment, loss.factor, loss.start_period, share))
    return out


def billing_from_orders(order_units: pd.DataFrame) -> pd.DataFrame:
    """Convolve expected order units with the lead-time distribution -> expected billed units."""
    out = []
    for pg, g in C.PRODUCT_GROUPS.items():
        sub = order_units[order_units["MATKL"] == pg]
        for k, p in enumerate(g["lead"]):
            if p == 0:
                continue
            s = sub.copy()
            s["PERIOD"] = s["PERIOD"].map(lambda x: shift_period(x, k))
            s["UNITS"] = s["UNITS"] * p
            out.append(s)
    df = pd.concat(out).groupby(["BUKRS", "KDGRP", "MATKL", "PERIOD"], as_index=False)["UNITS"].sum()
    return df[(df["PERIOD"] >= C.FIRST_PERIOD) & (df["PERIOD"] <= C.LAST_PERIOD)]


# --------------------------------------------------------------------------------------
# Fixed costs (expected amounts in local currency)
# --------------------------------------------------------------------------------------
def bonus_factor(bukrs: str, month: int) -> float:
    """German Urlaubs-/Weihnachtsgeld, Austrian 13th/14th salary, none in Poland."""
    if bukrs == "1000":
        return {6: 1.50, 11: 1.55}.get(month, 1.0)
    if bukrs == "2000":
        return {6: 2.0, 11: 2.0}.get(month, 1.0)
    return 1.0


def lci_ratio(drivers: pd.DataFrame, bukrs: str, period: str) -> float:
    col = lci_column(bukrs)
    base = drivers[drivers["year"] == 2023][col].mean()
    return float(drivers.loc[drivers["period"] == period, col].iloc[0] / base)


def plan_lci_ratio(drivers: pd.DataFrame, scenario: Scenario, bukrs: str, year: int, month: int) -> float:
    """Wage level assumed in the plan: prior-year Q3 level, increased from April."""
    col = lci_column(bukrs)
    base = drivers[drivers["year"] == 2023][col].mean()
    ref = float(drivers.loc[drivers["period"] == f"{year - 1}-08", col].iloc[0]) / base
    return ref * (1 + scenario.wage_increase_plan[year] * (1.0 if month >= 4 else 0.0))


def energy_mwh(bukrs: str, month: int, scale: float) -> float:
    winter = 1.10 if month in (12, 1, 2) else (0.95 if month in (6, 7, 8) else 1.0)
    prod = 0.6 + 0.4 * C.SEASONALITY[month - 1]
    return C.ENERGY_MWH[bukrs] * scale * winter * prod


def energy_price_eur(year: int, spot: float) -> float:
    return C.ENERGY_HEDGE_SHARE * C.ENERGY_HEDGE_PRICE[year] + (1 - C.ENERGY_HEDGE_SHARE) * spot + C.ENERGY_GRID_FEES


def overhead_rules(bukrs: str, kostl: str, name: str, level: str, hc: float) -> dict[str, float]:
    """Expected monthly overhead per account at 2023 level, DE prices, before scaling by country."""
    r: dict[str, float] = {}
    r["700000"] = 180.0 * hc
    r["709000"] = 35.0 * hc
    if "Instand" in name:
        r["701000"] = 25_000.0 * (hc / 28.0)
    if level == "DB2" and "Fertigung" in name:
        r["701000"] = 40.0 * hc
        r["530000"] = 90.0 * hc
    if "Vertrieb" in name:
        r["703000"] = 450.0 * hc
    elif "Service" in name:
        r["703000"] = 300.0 * hc
    elif "Geschäftsführung" in name or "Zarząd" in name:
        r["703000"] = 600.0 * hc
    else:
        r["703000"] = 40.0 * hc
    if "Marketing" in name or (bukrs != "1000" and "Vertrieb" in name):
        r["704000"] = 9_000.0 * max(hc, 1) if "Marketing" in name else 1_500.0 * hc
    if kostl == "1630":
        r["704000"] = 6_000.0
        r["705000"] = 9_000.0
    if name == "IT":
        r["705000"] = 70_000.0
    elif level != "HILF":
        r["705000"] = 60.0 * hc
    if "Finanzen" in name or "Geschäftsführung" in name or "Zarząd" in name:
        r["706000"] = 9_000.0 * (1.0 if bukrs == "1000" else 0.3)
    return r


def depreciation_rate(name: str, level: str) -> float:
    if level == "DB2" and "Fertigung" in name:
        return 420.0
    if name == "IT":
        return 900.0
    if "Instand" in name or "Energie" in name:
        return 600.0
    return 120.0


def special_month_amount(bukrs: str, kostl: str, name: str, account: str, period: str) -> float:
    """Calendar-driven extras, known to the planner (they are in the plan too)."""
    y, m = int(period[:4]), int(period[5:7])
    extra = 0.0
    if account == "707000" and m == 1 and ("Finanzen" in name or (bukrs != "1000" and name.startswith(("Gesch", "Zarz")))):
        extra += {"1000": 480_000.0, "2000": 70_000.0, "3000": 45_000.0}[bukrs]
    if account == "706000" and m == 3 and ("Finanzen" in name or name.startswith(("Gesch", "Zarz"))):
        extra += {"1000": 60_000.0, "2000": 18_000.0, "3000": 12_000.0}[bukrs]
    if account == "705000" and m == 1 and name == "IT":
        extra += 220_000.0
    if account == "704000" and "Marketing" in name:
        if m == 4:
            extra += 120_000.0  # Hannover Messe
        if y == 2024 and m == 5:
            extra += 300_000.0  # IFAT Munich (biennial, even years)
    return extra


def fixed_cost_expectations(md: MasterData, drivers: pd.DataFrame, scenario: Scenario, scale: float,
                            plan_year: int | None = None, first: str = C.FIRST_PERIOD,
                            last: str = C.LAST_PERIOD) -> pd.DataFrame:
    """Expected fixed cost per (BUKRS, KOSTL, RACCT, PERIOD) in local currency.

    ``plan_year`` set -> the planner's expectation for that year (plan wage/inflation/energy
    assumptions, no one-offs). Otherwise actual expectations incl. one-offs.
    """
    params = cost_centre_params()
    rows = []
    spot = dict(zip(drivers["period"], drivers["dayahead_eur_mwh"]))
    fx = fx_actual(drivers)
    pers = periods(first, last) if plan_year is None else periods(f"{plan_year}-01", f"{plan_year}-12")
    for _, cc in params.iterrows():
        bukrs, kostl, name, level = cc["BUKRS"], cc["KOSTL"], cc["NAME"], cc["LEVEL"]
        hc = cc["HC"] * scale
        country = COUNTRY_COST_LEVEL[bukrs]
        local = PL_PRICE_LIST_FX if bukrs == "3000" else 1.0
        oh = overhead_rules(bukrs, kostl, name, level, hc)
        for p in pers:
            if p < cc["VALID_FROM"]:
                continue
            y, m = int(p[:4]), int(p[5:7])
            if plan_year is None:
                wage_lvl = lci_ratio(drivers, bukrs, p)
                oh_lvl = OVERHEAD_LEVEL_ACTUAL[y]
            else:
                wage_lvl = plan_lci_ratio(drivers, scenario, bukrs, y, m)
                prev = OVERHEAD_LEVEL_ACTUAL.get(y - 1, 1 / 1.059)
                oh_lvl = prev * (1 + scenario.overhead_inflation_plan[y])
            # wage in local currency: params are EUR for DE/AT and EUR-equivalent for PL
            wage = cc["WAGE"] * (local if bukrs == "3000" else 1.0)
            gross = hc * wage * wage_lvl * bonus_factor(bukrs, m)
            rows.append((bukrs, kostl, "600000", p, gross * cc["BLUE"]))
            rows.append((bukrs, kostl, "601000", p, gross * (1 - cc["BLUE"])))
            rows.append((bukrs, kostl, "640000", p, gross * SOCIAL_RATE[bukrs]))
            dep = hc * depreciation_rate(name, level) * country * local * (1.03 ** (y - 2023))
            rows.append((bukrs, kostl, "680000", p, dep))
            for acc, amt in oh.items():
                v = amt * country * local * oh_lvl + special_month_amount(bukrs, kostl, name, acc, p) * local * scale
                rows.append((bukrs, kostl, acc, p, v))
            if "Energie" in name:
                sp = scenario.energy_spot_plan[y] if plan_year is not None else spot[p]
                price_eur = energy_price_eur(y, sp)
                rate = (scenario.fx_plan_eur_pln[y] if plan_year is not None else fx[p]) if bukrs == "3000" else 1.0
                rows.append((bukrs, kostl, "520000", p, energy_mwh(bukrs, m, scale) * price_eur * rate))
    df = pd.DataFrame(rows, columns=["BUKRS", "KOSTL", "RACCT", "PERIOD", "AMOUNT"])
    if plan_year is None:
        for oc in scenario.one_off_costs:
            if first <= oc.period <= last:
                rate = fx[oc.period] if oc.company_code == "3000" else 1.0
                df = pd.concat([df, pd.DataFrame([dict(BUKRS=oc.company_code, KOSTL=oc.cost_centre,
                                                       RACCT=oc.account, PERIOD=oc.period,
                                                       AMOUNT=oc.amount_eur * rate * scale)])], ignore_index=True)
    return df.groupby(["BUKRS", "KOSTL", "RACCT", "PERIOD"], as_index=False)["AMOUNT"].sum()


def freight_rate() -> float:
    """Outbound freight as share of revenue (physical goods), booked on logistics cost centres."""
    return 0.022
