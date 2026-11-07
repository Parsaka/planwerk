"""Expected (and fast randomised) monthly P&L at aggregate level.

Used for three things:

1. The **plan** (ACDOCP): the controller's expectation under plan assumptions.
2. The **ground truth** of injected effects: expected DB with and without each effect.
3. The **Q2 backtest**: hundreds of randomised scenarios without generating line items.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from planwerk.generator import config as C
from planwerk.generator import model as M
from planwerk.generator.masterdata import MasterData
from planwerk.generator.scenario import Scenario


def unit_cost_tables(md: MasterData, drivers: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Popularity-weighted unit cost per product group.

    Returns (standard per year, actual expected per period), both in EUR.
    """
    w = M.material_weights(md)[["MATNR", "MATKL", "POPULARITY"]]
    std = md.mbew.merge(w, on="MATNR")
    std = (std.assign(V=std["STPRS"] * std["POPULARITY"]).groupby(["MATKL", "BDATJ"])["V"].sum()
              .rename("STD_UNIT").reset_index())
    base = drivers[drivers["period"] == "2022-01"].iloc[0]
    rows = []
    purch = md.mara[md.mara["MTART"].isin(["ROH", "HAWA"])].set_index("MATNR")
    bom = md.stpo.merge(purch[["BASE_PRICE", "DRIVER"]], left_on="IDNRK", right_index=True)
    for _, d in drivers.iterrows():
        p = d["period"]
        if p < "2022-10":
            continue
        idx = {c: d[c] / base[c] for c in set(purch["DRIVER"])}
        b = bom.assign(V=bom["MENGE"] * bom["BASE_PRICE"] * bom["DRIVER"].map(idx))
        fert = b.groupby("MATNR")["V"].sum()
        hawa = purch[purch["MTART"] == "HAWA"]
        hawa_v = hawa["BASE_PRICE"] * hawa["DRIVER"].map(idx)
        unit = pd.concat([fert, hawa_v]).rename("U").reset_index().rename(columns={"index": "MATNR"})
        unit = unit.merge(w, on="MATNR")
        g = unit.assign(V=unit["U"] * unit["POPULARITY"]).groupby("MATKL")["V"].sum()
        for pg in C.PRODUCT_GROUPS:
            rows.append(dict(MATKL=pg, PERIOD=p, ACT_UNIT=float(g.get(pg, 0.0))))
    return std, pd.DataFrame(rows)


def avg_net_price(md: MasterData, increases: dict) -> pd.DataFrame:
    """Expected net price per unit (local currency) by company code, segment, product group, year."""
    lp = M.avg_list_price_2022(md)
    rows = []
    for bukrs in C.COMPANY_CODES:
        for seg, s in C.SEGMENTS.items():
            for pg in C.PRODUCT_GROUPS:
                for y in (2022, 2023, 2024, 2025):
                    yy = max(y, 2023)
                    rows.append(dict(BUKRS=bukrs, KDGRP=seg, MATKL=pg, YEAR=y,
                                     PRICE=lp[pg] * M.list_price_factor(increases, yy, pg)
                                     * M.local_price_level(bukrs) * (1 - s["discount"])))
    return pd.DataFrame(rows)


def expected_sales(md: MasterData, drivers: pd.DataFrame, scenario: Scenario, scale: float,
                   plan_year: int | None = None, rng: np.random.Generator | None = None,
                   noise: bool = False, sample: bool = False) -> pd.DataFrame:
    """Monthly order intake, billed units, revenue (local) and variable cost (local).

    plan_year: build the planner's view for that year (plan prices, plan volume, standard cost,
    plan FX); other years in the result are irrelevant for the plan and are dropped.
    noise/sample: add AR demand noise and Poisson sampling (backtest realisations).
    """
    rng = rng if rng is not None else np.random.default_rng(0)
    plan = plan_year is not None
    if plan:
        orders = M.expected_order_units(md, scenario, scale, rng, plan=True, plan_year=plan_year)
    elif noise:
        orders = M.expected_order_units(md, scenario, scale, rng)
    else:
        s0 = Scenario(**{**scenario.__dict__, "noise_level": 0.0})
        orders = M.expected_order_units(md, s0, scale, rng)
    if not plan:
        for kunnr, bukrs, seg, factor, start, share in M.customer_loss_share(md, scenario):
            hit = (orders["BUKRS"] == bukrs) & (orders["KDGRP"] == seg) & (orders["PERIOD"] >= start)
            orders.loc[hit, "UNITS"] *= 1 - share * (1 - factor)
            _ = kunnr
    if sample:
        qm = orders["MATKL"].map(lambda g: C.PRODUCT_GROUPS[g]["qty_mean"]).to_numpy()
        lam = orders["UNITS"].to_numpy() / qm
        orders["UNITS"] = rng.poisson(lam) * qm
    increases = scenario.price_increase_plan if plan else scenario.price_increase_actual
    if plan:
        # the plan knows the actual list prices of earlier years (backlog), only the plan year is assumed
        increases = {y: (scenario.price_increase_plan[y] if y == plan_year else scenario.price_increase_actual[y])
                     for y in scenario.price_increase_actual}
    price = avg_net_price(md, increases)
    orders["YEAR"] = orders["PERIOD"].str[:4].astype(int)
    orders = orders.merge(price, on=["BUKRS", "KDGRP", "MATKL", "YEAR"])
    orders["ORDER_VALUE"] = orders["UNITS"] * orders["PRICE"]

    billed = []
    for pg, g in C.PRODUCT_GROUPS.items():
        sub = orders[orders["MATKL"] == pg]
        for k, p in enumerate(g["lead"]):
            if p == 0:
                continue
            s = sub[["BUKRS", "KDGRP", "MATKL", "PERIOD", "UNITS", "ORDER_VALUE"]].copy()
            s["PERIOD"] = s["PERIOD"].map(lambda x: M.shift_period(x, k))
            s["UNITS"] *= p
            s["REVENUE"] = s["ORDER_VALUE"] * p
            billed.append(s.drop(columns="ORDER_VALUE"))
    bill = pd.concat(billed).groupby(["BUKRS", "KDGRP", "MATKL", "PERIOD"], as_index=False)[["UNITS", "REVENUE"]].sum()
    bill = bill[(bill["PERIOD"] >= C.FIRST_PERIOD) & (bill["PERIOD"] <= C.LAST_PERIOD)]
    oi = orders.groupby(["BUKRS", "KDGRP", "MATKL", "PERIOD"], as_index=False)["ORDER_VALUE"].sum()
    bill = bill.merge(oi, on=["BUKRS", "KDGRP", "MATKL", "PERIOD"], how="left").fillna({"ORDER_VALUE": 0.0})

    std, act = unit_cost_tables(md, drivers)
    bill["YEAR"] = bill["PERIOD"].str[:4].astype(int)
    fx = M.fx_actual(drivers)
    if plan:
        bill = bill.merge(std.rename(columns={"BDATJ": "YEAR"}), on=["MATKL", "YEAR"], how="left")
        bill["UNIT_EUR"] = bill["STD_UNIT"]
        rate = bill["YEAR"].map(scenario.fx_plan_eur_pln)
    else:
        bill = bill.merge(act, on=["MATKL", "PERIOD"], how="left")
        bill["UNIT_EUR"] = bill["ACT_UNIT"]
        rate = bill["PERIOD"].map(fx)
    bill.loc[bill["MATKL"] == "PG50", "UNIT_EUR"] = 0.0
    is_pl = bill["BUKRS"] == "3000"
    bill["VARCOST"] = bill["UNITS"] * bill["UNIT_EUR"] * np.where(is_pl, rate, 1.0)
    bill["FX"] = np.where(is_pl, rate, 1.0)
    if plan:
        bill = bill[bill["YEAR"] == plan_year]
    return bill[["BUKRS", "KDGRP", "MATKL", "PERIOD", "UNITS", "REVENUE", "VARCOST", "ORDER_VALUE", "FX"]]


def expected_fixed(md: MasterData, drivers: pd.DataFrame, scenario: Scenario, scale: float,
                   sales: pd.DataFrame, plan_year: int | None = None) -> pd.DataFrame:
    fixed = M.fixed_cost_expectations(md, drivers, scenario, scale, plan_year=plan_year)
    phys = sales[sales["MATKL"] != "PG50"].groupby(["BUKRS", "PERIOD"], as_index=False)["REVENUE"].sum()
    phys["KOSTL"] = phys["BUKRS"].map(C.LOGISTICS_CC)
    phys["RACCT"] = "702000"
    phys["AMOUNT"] = phys["REVENUE"] * M.freight_rate()
    return pd.concat([fixed, phys[["BUKRS", "KOSTL", "RACCT", "PERIOD", "AMOUNT"]]], ignore_index=True)


def monthly_db(md: MasterData, drivers: pd.DataFrame, scenario: Scenario, scale: float,
               rng: np.random.Generator | None = None, noise: bool = False, sample: bool = False,
               plan_year: int | None = None) -> pd.DataFrame:
    """Group-level monthly figures in EUR: order intake, revenue, DB I, fixed DB II costs, DB II, DB III."""
    sales = expected_sales(md, drivers, scenario, scale, plan_year=plan_year, rng=rng, noise=noise, sample=sample)
    fixed = expected_fixed(md, drivers, scenario, scale, sales, plan_year=plan_year)
    lvl = md.csks.drop_duplicates("KOSTL").set_index("KOSTL")["CM_LEVEL"]
    fixed["LEVEL"] = fixed["KOSTL"].map(lvl)
    fx = M.fx_actual(drivers)
    if plan_year is not None:
        frate = fixed["PERIOD"].str[:4].astype(int).map(scenario.fx_plan_eur_pln)
    else:
        frate = fixed["PERIOD"].map(fx)
    fixed["EUR"] = fixed["AMOUNT"] / np.where(fixed["BUKRS"] == "3000", frate, 1.0)
    if noise:
        r = rng if rng is not None else np.random.default_rng(1)
        fixed["EUR"] *= np.exp(r.normal(0, 0.03, len(fixed)))
    sales["REV_EUR"] = sales["REVENUE"] / sales["FX"]
    sales["VAR_EUR"] = sales["VARCOST"] / sales["FX"]
    sales["OI_EUR"] = sales["ORDER_VALUE"] / sales["FX"]
    s = sales.groupby("PERIOD").agg(ORDER_INTAKE=("OI_EUR", "sum"), REVENUE=("REV_EUR", "sum"),
                                    VARCOST=("VAR_EUR", "sum")).reset_index()
    # service cost centres (HILF) are allocated in the BAB to DB2/DB3 receivers; approximate
    # here by their dominant receivers (production) for the aggregate view
    lvl_map = {"HILF": "DB2", "DB2": "DB2", "DB3": "DB3", "UNT": "UNT"}
    fixed["LVL"] = fixed["LEVEL"].map(lvl_map)
    f = fixed.pivot_table(index="PERIOD", columns="LVL", values="EUR", aggfunc="sum").reset_index()
    f = f.rename(columns={"DB2": "FIX_DB2", "DB3": "FIX_DB3", "UNT": "FIX_UNT"})
    out = s.merge(f, on="PERIOD", how="left").fillna(0.0)
    out["DB1"] = out["REVENUE"] - out["VARCOST"]
    out["DB2"] = out["DB1"] - out["FIX_DB2"]
    out["DB3"] = out["DB2"] - out["FIX_DB3"]
    out["EBIT"] = out["DB3"] - out["FIX_UNT"]
    return out
