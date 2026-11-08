"""Budget (Plan) data in ACDOCP shape, category PLN, one version per fiscal year.

The plan is built from the controller's expectations at planning time (autumn of the prior
year): plan volume level, plan price increases, standard costs, plan wage increase, plan
overhead inflation, plan energy price and plan FX rate. It contains no noise and no
injected effects; the difference to actuals is exactly what the variance analysis explains.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from planwerk.generator import aggregate as A
from planwerk.generator import config as C
from planwerk.generator.masterdata import MasterData
from planwerk.generator.scenario import Scenario
from planwerk.generator.transactions import _pc_for_pg


def _material_split(md: MasterData) -> pd.DataFrame:
    """Share of each component account in the standard cost of a product group."""
    w = md.mara[md.mara["MTART"] == "FERT"][["MATNR", "MATKL", "POPULARITY"]]
    comp = md.mara.set_index("MATNR")
    b = md.stpo.merge(w, on="MATNR")
    b["CLS"] = b["IDNRK"].map(comp["MATKL"])
    b["V"] = b["MENGE"] * b["IDNRK"].map(comp["BASE_PRICE"]) * b["POPULARITY"]
    s = b.groupby(["MATKL", "CLS"])["V"].sum().reset_index()
    s["SHARE"] = s["V"] / s.groupby("MATKL")["V"].transform("sum")
    s["RACCT"] = s["CLS"].map(C.COMPONENT_ACCOUNT)
    hawa = pd.DataFrame(dict(MATKL=["PG40"], CLS=["HAWA"], V=[1.0], SHARE=[1.0], RACCT=["503000"]))
    return pd.concat([s, hawa], ignore_index=True)[["MATKL", "RACCT", "SHARE"]]


def _skonto_rate(md: MasterData) -> pd.DataFrame:
    """Expected cash discount as share of net revenue per company code and customer group."""
    k = md.knvv.assign(Z=(md.knvv["ZTERM"] == "Z014").astype(float) * md.knvv["WEIGHT"])
    g = k.groupby(["VKORG", "KDGRP"]).agg(Z=("Z", "sum"), W=("WEIGHT", "sum")).reset_index()
    vat = g["VKORG"].map(lambda b: C.COMPANY_CODES[b]["vat"])
    g["SKONTO_RATE"] = g["Z"] / g["W"] * 0.75 * C.PAYMENT_TERMS["Z014"]["skonto"] * (1 + vat)
    return g.rename(columns={"VKORG": "BUKRS"})[["BUKRS", "KDGRP", "SKONTO_RATE"]]


def build_plan(md: MasterData, drivers: pd.DataFrame, scenario: Scenario, scale: float,
               years=(2023, 2024, 2025)) -> pd.DataFrame:
    split = _material_split(md)
    frames = []
    for y in years:
        sales = A.expected_sales(md, drivers, scenario, scale, plan_year=y)
        fx = scenario.fx_plan_eur_pln[y]
        # revenue (credit, negative) with quantities
        rev = sales.copy()
        rev["RACCT"] = np.where(rev["MATKL"] == "PG50", "405000", "400000")
        rev["HSL"] = -rev["REVENUE"]
        rev["MSL"] = -rev["UNITS"]
        rev["RCNTR"] = ""
        # variable material cost, split to component accounts; production cost centre for FERT
        mat = sales[sales["MATKL"] != "PG50"].merge(split, on="MATKL")
        mat["HSL"] = mat["VARCOST"] * mat["SHARE"]
        mat["MSL"] = 0.0
        mat["RCNTR"] = [C.PRODUCTION_CC.get((b, g), "") for b, g in zip(mat["BUKRS"], mat["MATKL"], strict=False)]
        mat.loc[mat["MATKL"] == "PG40", "RCNTR"] = ""
        # expected cash discounts (Skonti): customers with terms Z014, 75 % take the 2 % on gross
        sk = sales.merge(_skonto_rate(md), on=["BUKRS", "KDGRP"], how="left").fillna({"SKONTO_RATE": 0.0})
        sk["RACCT"] = "409000"
        sk["HSL"] = sk["REVENUE"] * sk["SKONTO_RATE"]
        sk["MSL"] = 0.0
        sk["RCNTR"] = ""
        sk = sk[sk["HSL"] > 0]
        sl = pd.concat([rev, mat, sk], ignore_index=True)
        sl["PRCTR"] = [_pc_for_pg(b, g) for b, g in zip(sl["BUKRS"], sl["MATKL"], strict=False)]
        sl["MATKL_MM"] = sl["MATKL"]
        sl["RUNIT"] = np.where(sl["RACCT"].isin(["400000", "405000"]),
                               sl["MATKL"].map(lambda g: C.PRODUCT_GROUPS[g]["unit"]), "")
        # fixed costs per cost centre and account
        fixed = A.expected_fixed(md, drivers, scenario, scale, sales, plan_year=y)
        fixed = fixed.rename(columns={"KOSTL": "RCNTR", "AMOUNT": "HSL"})
        pcs = md.csks.drop_duplicates("KOSTL", keep="last").set_index("KOSTL")["PRCTR"]
        fixed["PRCTR"] = fixed["RCNTR"].map(pcs)
        fixed["MATKL_MM"], fixed["KDGRP"], fixed["MSL"], fixed["RUNIT"] = "", "", 0.0, ""
        cols = ["BUKRS", "PERIOD", "RACCT", "RCNTR", "PRCTR", "MATKL_MM", "KDGRP", "HSL", "MSL", "RUNIT"]
        both = pd.concat([sl[cols], fixed[cols]], ignore_index=True)
        both["RHCUR"] = both["BUKRS"].map(lambda b: C.COMPANY_CODES[b]["currency"])
        both["KSL"] = np.where(both["BUKRS"] == "3000", both["HSL"] / fx, both["HSL"])
        both["PLAN_FX_EUR_PLN"] = fx
        frames.append(both)
    p = pd.concat(frames, ignore_index=True)
    p = p[p["HSL"].abs() > 0.004].reset_index(drop=True)
    p["HSL"] = p["HSL"].round(2)
    p["KSL"] = p["KSL"].round(2)
    p["MSL"] = p["MSL"].round(3)
    p.insert(0, "RCLNT", C.CLIENT)
    p.insert(1, "RLDNR", C.LEDGER)
    p.insert(2, "CATEGORY", "PLN")
    p["RBUKRS"] = p.pop("BUKRS")
    p["RYEAR"] = p["PERIOD"].str[:4]
    p["POPER"] = p["PERIOD"].str[5:7].str.zfill(3)
    p["FISCYEARPER"] = p["RYEAR"] + p["POPER"]
    p["RKCUR"] = "EUR"
    p["KOKRS"] = C.CONTROLLING_AREA
    return p[["RCLNT", "RLDNR", "CATEGORY", "RBUKRS", "RYEAR", "POPER", "FISCYEARPER", "RACCT", "KOKRS", "RCNTR",
              "PRCTR", "MATKL_MM", "KDGRP", "RHCUR", "HSL", "RKCUR", "KSL", "MSL", "RUNIT", "PLAN_FX_EUR_PLN"]]
