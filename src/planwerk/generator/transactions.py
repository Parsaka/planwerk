"""Line-level business transactions: sales, production, purchasing, overheads, payroll,
payments and tax. Produces document tables (VBAK/VBAP/VBRK/VBRP, AFKO, EKKO/EKPO) and
posting frames for the journal builder.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from planwerk.generator import config as C
from planwerk.generator import model as M
from planwerk.generator.calendar import (
    first_business_day,
    last_business_day,
    random_business_days,
    to_period,
)
from planwerk.generator.config import GeneratorConfig
from planwerk.generator.journal import postings
from planwerk.generator.masterdata import MasterData
from planwerk.generator.scenario import Scenario

END_DATE = np.datetime64("2025-12-31")
ITEMS_PER_ORDER_EXTRA = 0.5  # items per order = 1 + Poisson(0.5)


@dataclass
class Documents:
    vbak: pd.DataFrame = field(default_factory=pd.DataFrame)
    vbap: pd.DataFrame = field(default_factory=pd.DataFrame)
    vbrk: pd.DataFrame = field(default_factory=pd.DataFrame)
    vbrp: pd.DataFrame = field(default_factory=pd.DataFrame)
    afko: pd.DataFrame = field(default_factory=pd.DataFrame)
    ekko: pd.DataFrame = field(default_factory=pd.DataFrame)
    ekpo: pd.DataFrame = field(default_factory=pd.DataFrame)
    frames: list = field(default_factory=list)
    ar: pd.DataFrame = field(default_factory=pd.DataFrame)


def _pc_for_pg(bukrs: str, pg: str) -> str:
    if pg in ("PG40", "PG50"):
        return f"P{bukrs}_SERV"
    if bukrs == "1000":
        return "P1000_VENT" if pg == "PG30" else "P1000_PUMP"
    return f"P{bukrs}_FERT"


def _vendor_pool(md: MasterData) -> dict[tuple[str, str], np.ndarray]:
    return {k: g["LIFNR"].to_numpy() for k, g in md.lfa1.groupby(["BUKRS", "CATEGORY"])}


def component_actual_prices(md: MasterData, drivers: pd.DataFrame, cfg: GeneratorConfig) -> pd.DataFrame:
    """Actual purchase price (EUR) per purchased material and period."""
    rng = cfg.rng("component_prices")
    mat = md.mara[md.mara["MTART"].isin(["ROH", "HAWA"])][["MATNR", "BASE_PRICE", "DRIVER"]].reset_index(drop=True)
    base_row = drivers[drivers["period"] == "2022-01"].iloc[0]
    years = [2023, 2024, 2025]
    # material-specific deviation from the index, fixed per year (supplier negotiations)
    dev = {y: rng.normal(0.0, 0.03, len(mat)) for y in years}
    rows = []
    for p in M.periods("2022-10", C.LAST_PERIOD):
        d = drivers[drivers["period"] == p].iloc[0]
        y = max(int(p[:4]), 2023)
        idx = mat["DRIVER"].map(lambda c: d[c] / base_row[c]).to_numpy()
        rows.append(pd.DataFrame(dict(MATNR=mat["MATNR"], PERIOD=p,
                                      PRICE=np.round(mat["BASE_PRICE"].to_numpy() * idx * (1 + dev[y]), 4))))
    return pd.concat(rows, ignore_index=True)


# --------------------------------------------------------------------------------------
# Sales
# --------------------------------------------------------------------------------------
def generate_orders(md: MasterData, scenario: Scenario, cfg: GeneratorConfig) -> pd.DataFrame:
    """Order items with customer, material, quantity, price, order and billing dates."""
    rng = cfg.rng("orders")
    lam = M.expected_order_units(md, scenario, cfg.scale, cfg.rng("demand_noise"))
    qmean = lam["MATKL"].map(lambda g: C.PRODUCT_GROUPS[g]["qty_mean"])
    lam["LAM_ORDERS"] = lam["UNITS"] / (qmean * (1 + ITEMS_PER_ORDER_EXTRA))
    n_orders = rng.poisson(lam["LAM_ORDERS"].to_numpy())
    orders = lam.loc[lam.index.repeat(n_orders), ["BUKRS", "KDGRP", "MATKL", "PERIOD"]].reset_index(drop=True)
    n = len(orders)

    # customers by weight within (company code, segment)
    kun = np.empty(n, dtype=object)
    pay_delay = np.zeros(n)
    zterm = np.empty(n, dtype=object)
    for (bukrs, seg), idx in orders.groupby(["BUKRS", "KDGRP"]).groups.items():
        pool = md.knvv[(md.knvv["VKORG"] == bukrs) & (md.knvv["KDGRP"] == seg)]
        w = pool["WEIGHT"].to_numpy()
        pick = rng.choice(len(pool), size=len(idx), p=w / w.sum())
        kun[idx] = pool["KUNNR"].to_numpy()[pick]
        pay_delay[idx] = pool["PAY_DELAY_MEAN"].to_numpy()[pick]
        zterm[idx] = pool["ZTERM"].to_numpy()[pick]
    orders["KUNNR"], orders["PAY_DELAY_MEAN"], orders["ZTERM"] = kun, pay_delay, zterm

    # customer losses: thin the lost customer's orders after the start period
    keep = np.ones(n, dtype=bool)
    for kunnr, _b, _s, factor, start, _share in M.customer_loss_share(md, scenario):
        hit = (orders["KUNNR"].to_numpy() == kunnr) & (orders["PERIOD"].to_numpy() >= start)
        keep &= ~(hit & (rng.random(n) > factor))
    orders = orders[keep].reset_index(drop=True)
    n = len(orders)

    orders["ERDAT"] = random_business_days(orders["PERIOD"].to_numpy(), rng)
    lead = np.zeros(n, dtype=int)
    for pg, idx in orders.groupby("MATKL").groups.items():
        p = np.array(C.PRODUCT_GROUPS[pg]["lead"])
        lead[idx] = rng.choice(4, size=len(idx), p=p / p.sum())
    orders["LEAD"] = lead
    orders["VBELN"] = [f"{i:010d}" for i in range(100001, 100001 + n)]
    orders = orders.sort_values(["ERDAT", "VBELN"]).reset_index(drop=True)
    orders["VBELN"] = [f"{i:010d}" for i in range(100001, 100001 + n)]

    # items
    k = 1 + rng.poisson(ITEMS_PER_ORDER_EXTRA, n)
    items = orders.loc[orders.index.repeat(k)].reset_index(drop=True)
    items["POSNR"] = ((items.groupby("VBELN").cumcount() + 1) * 10).astype(str).str.zfill(6)
    m = len(items)
    mats = M.material_weights(md)
    matnr = np.empty(m, dtype=object)
    list22 = np.zeros(m)
    for pg, idx in items.groupby("MATKL").groups.items():
        pool = mats[mats["MATKL"] == pg]
        pick = rng.choice(len(pool), size=len(idx), p=pool["POPULARITY"].to_numpy())
        matnr[idx] = pool["MATNR"].to_numpy()[pick]
        list22[idx] = pool["LIST_PRICE_2022"].to_numpy()[pick]
    items["MATNR"] = matnr
    qmean = items["MATKL"].map(lambda g: C.PRODUCT_GROUPS[g]["qty_mean"]).to_numpy()
    items["KWMENG"] = rng.geometric(1.0 / qmean).astype(float)

    # price at order date: price list of the order year
    oyear = np.maximum(items["PERIOD"].str[:4].astype(int).to_numpy(), 2023)
    factor = np.array([M.list_price_factor(scenario.price_increase_actual, y, g)
                       for y, g in zip(oyear, items["MATKL"], strict=False)])
    lvl = items["BUKRS"].map(M.local_price_level).to_numpy()
    disc = items["KDGRP"].map(lambda s: C.SEGMENTS[s]["discount"]).to_numpy()
    noise = 1 + rng.normal(0.0, 0.02 * scenario.noise_level, m)
    items["NETPR"] = np.round(list22 * factor * lvl * (1 - disc) * noise, 2)
    items["NETWR"] = np.round(items["NETPR"] * items["KWMENG"], 2)

    # billing date (= delivery date)
    bill_period = np.array([M.shift_period(p, int(l)) for p, l in zip(orders["PERIOD"], orders["LEAD"], strict=False)])
    orders["BILL_PERIOD"] = bill_period
    billed = bill_period <= C.LAST_PERIOD
    bdate = np.full(len(orders), np.datetime64("NaT", "D"), dtype="datetime64[D]")
    if billed.any():
        cand = random_business_days(bill_period[billed], rng)
        erdat = orders["ERDAT"].to_numpy().astype("datetime64[D]")[billed]
        # same-month billing must not be before the order date
        same = cand < erdat
        if same.any():
            bd_last = np.array([last_business_day(p) for p in bill_period[billed][same]])
            span = (bd_last - erdat[same]).astype(int)
            cand[same] = erdat[same] + (rng.random(same.sum()) * (span + 1)).astype(int)
        bdate[billed] = cand
    orders["FKDAT"] = bdate
    items = items.merge(orders[["VBELN", "BILL_PERIOD", "FKDAT"]], on="VBELN", how="left")
    # orders delivered before the data window are pre-history; the 2022 backlog stays
    return items[items["BILL_PERIOD"] >= C.FIRST_PERIOD].reset_index(drop=True)


def sales_documents(items: pd.DataFrame, md: MasterData, docs: Documents) -> None:
    head = items.groupby("VBELN", sort=False).agg(
        ERDAT=("ERDAT", "first"), VKORG=("BUKRS", "first"), KUNNR=("KUNNR", "first"),
        KDGRP=("KDGRP", "first"), NETWR=("NETWR", "sum"), ZTERM=("ZTERM", "first")).reset_index()
    head["AUART"] = "TA"
    head["WAERK"] = head["VKORG"].map(lambda b: C.COMPANY_CODES[b]["currency"])
    docs.vbak = head[["VBELN", "ERDAT", "AUART", "VKORG", "KUNNR", "KDGRP", "NETWR", "WAERK", "ZTERM"]].copy()
    docs.vbak["ERDAT"] = pd.to_datetime(docs.vbak["ERDAT"]).dt.date
    vbap = items[["VBELN", "POSNR", "MATNR", "MATKL", "KWMENG", "NETPR", "NETWR", "BUKRS", "FKDAT"]].copy()
    vbap["WERKS"] = vbap["BUKRS"].map(lambda b: C.COMPANY_CODES[b]["plant"])
    vbap["VRKME"] = vbap["MATKL"].map(lambda g: C.PRODUCT_GROUPS[g]["unit"])
    vbap["EDATU"] = pd.to_datetime(vbap["FKDAT"]).dt.date
    docs.vbap = vbap.drop(columns=["BUKRS", "FKDAT"])


def billing(items: pd.DataFrame, md: MasterData, cfg: GeneratorConfig, std: pd.DataFrame,
            hawa_price: pd.DataFrame, docs: Documents) -> pd.DataFrame:
    """Invoices (VBRK/VBRP), FI postings for revenue/AR/VAT and goods issue; returns invoices."""
    cfg.rng("billing")
    b = items[items["BILL_PERIOD"] <= C.LAST_PERIOD].copy()
    inv = b.groupby("VBELN", sort=False).agg(BUKRS=("BUKRS", "first"), KUNNR=("KUNNR", "first"),
                                              KDGRP=("KDGRP", "first"), FKDAT=("FKDAT", "first"),
                                              NETWR=("NETWR", "sum"), ZTERM=("ZTERM", "first"),
                                              PAY_DELAY_MEAN=("PAY_DELAY_MEAN", "first")).reset_index()
    inv = inv.rename(columns={"VBELN": "AUBEL"})
    inv = inv.sort_values(["FKDAT", "AUBEL"]).reset_index(drop=True)
    inv["VBELN"] = [f"{90000001 + i:010d}" for i in range(len(inv))]
    vat = inv["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["vat"])
    inv["MWSBK"] = np.round(inv["NETWR"] * vat, 2)
    inv["GROSS"] = inv["NETWR"] + inv["MWSBK"]
    inv["WAERK"] = inv["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["currency"])
    net_days = inv["ZTERM"].map(lambda z: C.PAYMENT_TERMS[z]["net"]).to_numpy()
    fkdat = inv["FKDAT"].to_numpy().astype("datetime64[D]")
    inv["NETDT"] = fkdat + net_days.astype("timedelta64[D]")
    b = b.merge(inv[["AUBEL", "VBELN"]].rename(columns={"VBELN": "INV"}), left_on="VBELN", right_on="AUBEL")

    # cost at standard (FERT) or actual purchase price (HAWA) of the billing period
    b["YEAR"] = b["BILL_PERIOD"].str[:4].astype(int)
    b = b.merge(std.rename(columns={"BDATJ": "YEAR", "STPRS": "STD"})[["MATNR", "YEAR", "STD"]],
                on=["MATNR", "YEAR"], how="left")
    b = b.merge(hawa_price.rename(columns={"PERIOD": "BILL_PERIOD", "PRICE": "HAWA_EUR"}),
                on=["MATNR", "BILL_PERIOD"], how="left")
    b["WAVWR_EUR"] = np.where(b["MATKL"] == "PG40", b["HAWA_EUR"], b["STD"]) * b["KWMENG"]
    b.loc[b["MATKL"] == "PG50", "WAVWR_EUR"] = 0.0
    b["WAVWR_EUR"] = b["WAVWR_EUR"].fillna(0.0).round(2)

    docs.vbrk = inv[["VBELN", "BUKRS", "KUNNR", "FKDAT", "NETWR", "MWSBK", "WAERK", "ZTERM", "AUBEL"]].assign(
        FKART="F2", VKORG=inv["BUKRS"], KUNRG=inv["KUNNR"]).drop(columns="KUNNR")
    docs.vbrk["FKDAT"] = pd.to_datetime(docs.vbrk["FKDAT"]).dt.date
    vbrp = b[["INV", "POSNR", "MATNR", "MATKL", "KWMENG", "NETWR", "AUBEL", "WAVWR_EUR", "BUKRS"]].rename(
        columns={"INV": "VBELN", "KWMENG": "FKIMG"})
    vbrp["AUPOS"] = vbrp["POSNR"]
    vbrp["PRCTR"] = [_pc_for_pg(x, g) for x, g in zip(vbrp["BUKRS"], vbrp["MATKL"], strict=False)]
    vbrp["WERKS"] = vbrp["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["plant"])
    docs.vbrp = vbrp.drop(columns="BUKRS")

    # --- FI: revenue document per invoice
    cur = inv["WAERK"].to_numpy()
    key = "RV" + inv["VBELN"]
    ar = postings(len(inv), DOC_KEY=key.to_numpy(), BUKRS=inv["BUKRS"].to_numpy(), BUDAT=fkdat, BLART="RV",
                  RACCT="120000", KOART="D", KUNNR=inv["KUNNR"].to_numpy(), RTCUR=cur,
                  TSL=inv["GROSS"].to_numpy(), KDGRP=inv["KDGRP"].to_numpy(), AWTYP="VBRK",
                  AWREF=inv["VBELN"].to_numpy(), NETDT=inv["NETDT"].to_numpy(), BAL=True,
                  XBLNR=inv["VBELN"].to_numpy(), PRCTR=(inv["BUKRS"].map(lambda x: f"P{x}_ZENT")).to_numpy())
    vatl = postings(len(inv), DOC_KEY=key.to_numpy(), BUKRS=inv["BUKRS"].to_numpy(), BUDAT=fkdat, BLART="RV",
                    RACCT="380000", RTCUR=cur, TSL=-inv["MWSBK"].to_numpy(), MWSKZ="A1", AWTYP="VBRK",
                    AWREF=inv["VBELN"].to_numpy())
    bk = b["BUKRS"].to_numpy()
    bcur = b["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["currency"]).to_numpy()
    bdat = b["FKDAT"].to_numpy().astype("datetime64[D]")
    rev_acc = np.where(b["MATKL"] == "PG50", "405000", "400000")
    pcs = np.array([_pc_for_pg(x, g) for x, g in zip(bk, b["MATKL"], strict=False)])
    rev = postings(len(b), DOC_KEY=("RV" + b["INV"]).to_numpy(), BUKRS=bk, BUDAT=bdat, BLART="RV",
                   RACCT=rev_acc, PRCTR=pcs, RTCUR=bcur, TSL=-b["NETWR"].to_numpy(),
                   MSL=-b["KWMENG"].to_numpy(), RUNIT=b["MATKL"].map(lambda g: C.PRODUCT_GROUPS[g]["unit"]).to_numpy(),
                   KUNNR=b["KUNNR"].to_numpy(), MATNR=b["MATNR"].to_numpy(),
                   WERKS=b["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["plant"]).to_numpy(),
                   KDAUF=b["VBELN"].to_numpy(), KDPOS=b["POSNR"].to_numpy(),
                   MATKL_MM=b["MATKL"].to_numpy(), KDGRP=b["KDGRP"].to_numpy(), AWTYP="VBRK",
                   AWREF=b["INV"].to_numpy(), MWSKZ="A1")
    docs.ar = ar
    docs.frames += [ar, vatl, rev]

    # --- goods issue for delivery (finished goods at standard, trading goods at actual)
    phys = b[b["MATKL"] != "PG50"].reset_index(drop=True)
    # PL: inventory valued in PLN at the period rate; postings carry EUR as transaction currency
    gi_key = ("WL" + phys["INV"]).to_numpy()
    gi_acc = np.where(phys["MATKL"] == "PG40", "503000", "480000")
    pk = phys["BUKRS"].to_numpy()
    pdat = phys["FKDAT"].to_numpy().astype("datetime64[D]")
    ppc = np.array([_pc_for_pg(x, g) for x, g in zip(pk, phys["MATKL"], strict=False)])
    common = dict(BUKRS=pk, BUDAT=pdat, BLART="WL", RTCUR="EUR", MATNR=phys["MATNR"].to_numpy(),
                  WERKS=phys["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["plant"]).to_numpy(),
                  KDAUF=phys["VBELN"].to_numpy(), KDPOS=phys["POSNR"].to_numpy(),
                  MATKL_MM=phys["MATKL"].to_numpy(), KDGRP=phys["KDGRP"].to_numpy(), KUNNR=phys["KUNNR"].to_numpy(),
                  AWTYP="LIKP", AWREF=phys["INV"].to_numpy(), PRCTR=ppc)
    exp = postings(len(phys), DOC_KEY=gi_key, RACCT=gi_acc, TSL=phys["WAVWR_EUR"].to_numpy(),
                   MSL=phys["KWMENG"].to_numpy(), RUNIT="ST", **common)
    inv_line = postings(len(phys), DOC_KEY=gi_key, RACCT="101000", KOART="M", TSL=-phys["WAVWR_EUR"].to_numpy(),
                        MSL=-phys["KWMENG"].to_numpy(), RUNIT="ST", **common)
    # one balancing line per GI document: mark the first inventory line of each document
    first = ~pd.Series(gi_key).duplicated().to_numpy()
    inv_line["BAL"] = first
    docs.frames += [exp, inv_line]
    return inv


def customer_payments(inv: pd.DataFrame, cfg: GeneratorConfig, docs: Documents) -> None:
    rng = cfg.rng("customer_payments")
    n = len(inv)
    fkdat = inv["FKDAT"].to_numpy().astype("datetime64[D]")
    netdt = inv["NETDT"].to_numpy().astype("datetime64[D]")
    terms = inv["ZTERM"].map(C.PAYMENT_TERMS)
    sk_rate = terms.map(lambda t: t["skonto"]).to_numpy()
    takes = (sk_rate > 0) & (rng.random(n) < 0.75)
    delay = rng.poisson(inv["PAY_DELAY_MEAN"].to_numpy()).astype(int)
    pay = np.where(takes, fkdat + rng.integers(7, 15, n).astype("timedelta64[D]"),
                   netdt + delay.astype("timedelta64[D]"))
    pay = pay.astype("datetime64[D]")
    # move weekend payments to Monday
    wd = (pay.astype("datetime64[D]").view("int64") - 4) % 7  # 0 = Monday
    pay = pay + np.where(wd == 5, 2, np.where(wd == 6, 1, 0)).astype("timedelta64[D]")
    paid = pay <= END_DATE
    p = inv[paid].reset_index(drop=True)
    pay = pay[paid]
    takes = takes[paid]
    gross = p["GROSS"].to_numpy()
    skonto = np.where(takes, np.round(gross * sk_rate[paid], 2), 0.0)
    key = ("DZ" + p["VBELN"]).to_numpy()
    cur = p["WAERK"].to_numpy()
    base = dict(DOC_KEY=key, BUKRS=p["BUKRS"].to_numpy(), BUDAT=pay, BLART="DZ", RTCUR=cur,
                AWTYP="BKPF", XBLNR=p["VBELN"].to_numpy())
    clear = postings(len(p), RACCT="120000", KOART="D", KUNNR=p["KUNNR"].to_numpy(), TSL=-gross,
                     CLEAR_KEY=key, KDGRP=p["KDGRP"].to_numpy(),
                     PRCTR=p["BUKRS"].map(lambda x: f"P{x}_ZENT").to_numpy(), **base)
    bank = postings(len(p), RACCT="180000", TSL=gross - skonto, BAL=True, **base)
    frames = [clear, bank]
    if takes.any():
        s = postings(int(takes.sum()), RACCT="409000", TSL=skonto[takes], KUNNR=p["KUNNR"].to_numpy()[takes],
                     KDGRP=p["KDGRP"].to_numpy()[takes],
                     PRCTR=p["BUKRS"].map(lambda x: f"P{x}_SERV").to_numpy()[takes],
                     **{k: (v[takes] if isinstance(v, np.ndarray) else v) for k, v in base.items()})
        frames.append(s)
    docs.frames += frames
    # clear the invoice's AR line with the payment document
    clear_map = dict(zip(("RV" + p["VBELN"]).to_numpy(), key, strict=False))
    docs.ar["CLEAR_KEY"] = docs.ar["DOC_KEY"].map(clear_map).fillna("").to_numpy()


# --------------------------------------------------------------------------------------
# Production (make-to-order) and purchasing
# --------------------------------------------------------------------------------------
def production(items: pd.DataFrame, md: MasterData, comp_prices: pd.DataFrame, std: pd.DataFrame,
               cfg: GeneratorConfig, docs: Documents) -> pd.DataFrame:
    """One production order per finished-goods order item; returns component consumption."""
    rng = cfg.rng("production")
    fert = items[items["MATKL"].isin(["PG10", "PG20", "PG30"])].copy()
    # finished one month before billing when lead >= 1, else in the billing month
    comp_period = np.where(fert["BILL_PERIOD"] > fert["PERIOD"],
                           [M.shift_period(p, -1) for p in fert["BILL_PERIOD"]], fert["BILL_PERIOD"])
    comp_period = np.asarray(comp_period).astype(str)
    fert["COMP_PERIOD"] = np.where(comp_period < C.FIRST_PERIOD, C.FIRST_PERIOD, comp_period)
    fert = fert[fert["COMP_PERIOD"] <= C.LAST_PERIOD].reset_index(drop=True)
    gltri = random_business_days(fert["COMP_PERIOD"].to_numpy(), rng)
    fdat = fert["FKDAT"].to_numpy().astype("datetime64[D]")
    erdat = fert["ERDAT"].to_numpy().astype("datetime64[D]")
    same = fert["COMP_PERIOD"].to_numpy() == fert["BILL_PERIOD"].to_numpy()
    gltri = np.where(same & ~np.isnat(fdat), np.minimum(gltri, fdat), gltri)
    gltri = np.maximum(gltri, erdat)
    fert["GLTRI"] = gltri
    fert["AUFNR"] = [f"{1000000001 + i:012d}" for i in range(len(fert))]
    fert["KOSTL"] = [C.PRODUCTION_CC[(b, g)] for b, g in zip(fert["BUKRS"], fert["MATKL"], strict=False)]
    fert["WERKS"] = fert["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["plant"])
    docs.afko = fert[["AUFNR", "MATNR", "KWMENG", "WERKS", "BUKRS", "KOSTL", "GLTRI", "VBELN", "POSNR"]].rename(
        columns={"KWMENG": "GAMNG", "VBELN": "KDAUF", "POSNR": "KDPOS"}).assign(AUART="PP01")
    docs.afko["GLTRI"] = pd.to_datetime(docs.afko["GLTRI"]).dt.date

    # component consumption at actual price of the completion period
    cons = fert[["AUFNR", "MATNR", "KWMENG", "BUKRS", "KOSTL", "WERKS", "COMP_PERIOD", "GLTRI", "MATKL",
                 "VBELN", "POSNR"]].merge(md.stpo[["MATNR", "IDNRK", "MENGE"]], on="MATNR")
    cons["QTY"] = cons["KWMENG"] * cons["MENGE"]
    cons = cons.merge(comp_prices.rename(columns={"MATNR": "IDNRK", "PERIOD": "COMP_PERIOD"}),
                      on=["IDNRK", "COMP_PERIOD"], how="left")
    cons["VALUE_EUR"] = np.round(cons["QTY"] * cons["PRICE"], 2)
    cls = cons["IDNRK"].map(md.mara.set_index("MATNR")["MATKL"])
    cons["RACCT"] = cls.map(C.COMPONENT_ACCOUNT)
    cons["PRCTR"] = [_pc_for_pg(b, g) for b, g in zip(cons["BUKRS"], cons["MATKL"], strict=False)]

    key = ("WA" + cons["AUFNR"]).to_numpy()
    gdate = cons["GLTRI"].to_numpy().astype("datetime64[D]")
    common = dict(DOC_KEY=key, BUKRS=cons["BUKRS"].to_numpy(), BUDAT=gdate, BLART="WA", RTCUR="EUR",
                  WERKS=cons["WERKS"].to_numpy(), AUFNR=cons["AUFNR"].to_numpy(),
                  KDAUF=cons["VBELN"].to_numpy(), KDPOS=cons["POSNR"].to_numpy(),
                  MATKL_MM=cons["MATKL"].to_numpy(), AWTYP="MKPF", AWREF=cons["AUFNR"].to_numpy(),
                  PRCTR=cons["PRCTR"].to_numpy())
    expl = postings(len(cons), RACCT=cons["RACCT"].to_numpy(), RCNTR=cons["KOSTL"].to_numpy(),
                    TSL=cons["VALUE_EUR"].to_numpy(), MSL=cons["QTY"].to_numpy(), RUNIT="ST",
                    MATNR=cons["IDNRK"].to_numpy(), **common)
    invl = postings(len(cons), RACCT="100000", KOART="M", TSL=-cons["VALUE_EUR"].to_numpy(),
                    MSL=-cons["QTY"].to_numpy(), RUNIT="ST", MATNR=cons["IDNRK"].to_numpy(), **common)
    invl["BAL"] = ~pd.Series(key).duplicated().to_numpy()
    docs.frames += [expl, invl]

    # goods receipt of the finished product at standard -> Bestandsveränderung
    fert["YEAR"] = fert["COMP_PERIOD"].str[:4].astype(int)
    fert = fert.merge(std.rename(columns={"BDATJ": "YEAR", "STPRS": "STD"})[["MATNR", "YEAR", "STD"]],
                      on=["MATNR", "YEAR"], how="left")
    val = np.round(fert["STD"].to_numpy() * fert["KWMENG"].to_numpy(), 2)
    rkey = ("WE" + fert["AUFNR"]).to_numpy()
    pcs = np.array([_pc_for_pg(b, g) for b, g in zip(fert["BUKRS"], fert["MATKL"], strict=False)])
    rc = dict(DOC_KEY=rkey, BUKRS=fert["BUKRS"].to_numpy(), BUDAT=fert["GLTRI"].to_numpy().astype("datetime64[D]"),
              BLART="WE", RTCUR="EUR", MATNR=fert["MATNR"].to_numpy(), WERKS=fert["WERKS"].to_numpy(),
              AUFNR=fert["AUFNR"].to_numpy(), KDAUF=fert["VBELN"].to_numpy(), KDPOS=fert["POSNR"].to_numpy(),
              MATKL_MM=fert["MATKL"].to_numpy(), AWTYP="MKPF", AWREF=fert["AUFNR"].to_numpy(), PRCTR=pcs)
    fg = postings(len(fert), RACCT="101000", KOART="M", TSL=val, MSL=fert["KWMENG"].to_numpy(), RUNIT="ST", **rc)
    bv = postings(len(fert), RACCT="480000", TSL=-val, MSL=-fert["KWMENG"].to_numpy(), RUNIT="ST", BAL=True, **rc)
    docs.frames += [fg, bv]
    return cons


def purchasing(cons: pd.DataFrame, billed_items: pd.DataFrame, comp_prices: pd.DataFrame, md: MasterData,
               cfg: GeneratorConfig, docs: Documents) -> None:
    """Monthly purchase orders covering component consumption and trading-goods sales."""
    rng = cfg.rng("purchasing")
    vend = _vendor_pool(md)
    mcls = md.mara.set_index("MATNR")["MATKL"]
    rm = cons.groupby(["BUKRS", "WERKS", "COMP_PERIOD", "IDNRK"], as_index=False)["QTY"].sum().rename(
        columns={"COMP_PERIOD": "PERIOD", "IDNRK": "MATNR"})
    hw = billed_items[billed_items["MATKL"] == "PG40"].groupby(["BUKRS", "BILL_PERIOD", "MATNR"],
                                                               as_index=False)["KWMENG"].sum()
    hw = hw.rename(columns={"BILL_PERIOD": "PERIOD", "KWMENG": "QTY"})
    hw["WERKS"] = hw["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["plant"])
    po = pd.concat([rm, hw], ignore_index=True)
    po = po[po["PERIOD"] >= "2022-10"]
    po = po.merge(comp_prices, on=["MATNR", "PERIOD"], how="left")
    po["CLASS"] = po["MATNR"].map(mcls).replace({"PG40": "HAWA"})
    # one main vendor per (company code, material)
    lif = []
    for b, c, mat in zip(po["BUKRS"], po["CLASS"], po["MATNR"], strict=False):
        pool = vend[(b, c)]
        lif.append(pool[int(mat) % len(pool)])
    po["LIFNR"] = lif
    po["NETWR"] = np.round(po["QTY"] * po["PRICE"], 2)
    po = po.sort_values(["BUKRS", "PERIOD", "LIFNR", "MATNR"]).reset_index(drop=True)
    hdr = po.groupby(["BUKRS", "PERIOD", "LIFNR"], sort=False).size().reset_index()[["BUKRS", "PERIOD", "LIFNR"]]
    hdr["EBELN"] = [f"{4500000001 + i:010d}" for i in range(len(hdr))]
    po = po.merge(hdr, on=["BUKRS", "PERIOD", "LIFNR"])
    po["EBELP"] = ((po.groupby("EBELN").cumcount() + 1) * 10).astype(str).str.zfill(5)
    hdr["BEDAT"] = [first_business_day(p) - np.timedelta64(7, "D") for p in hdr["PERIOD"]]
    docs.ekko = hdr.assign(BSART="NB", WAERS="EUR")[["EBELN", "BUKRS", "BSART", "LIFNR", "BEDAT", "WAERS"]].copy()
    docs.ekko["BEDAT"] = pd.to_datetime(docs.ekko["BEDAT"]).dt.date
    docs.ekpo = po[["EBELN", "EBELP", "MATNR", "QTY", "PRICE", "NETWR", "WERKS"]].rename(
        columns={"QTY": "MENGE", "PRICE": "NETPR"}).assign(MEINS="ST")

    # GR on the first working day of the period (only periods inside the data window)
    po = po[po["PERIOD"] >= C.FIRST_PERIOD].reset_index(drop=True)
    gr_date = np.array([first_business_day(p) for p in po["PERIOD"]])
    inv_acc = np.where(po["CLASS"] == "HAWA", "101000", "100000")
    key = ("WE" + po["EBELN"]).to_numpy()
    c = dict(DOC_KEY=key, BUKRS=po["BUKRS"].to_numpy(), BUDAT=gr_date, BLART="WE", RTCUR="EUR",
             MATNR=po["MATNR"].to_numpy(), WERKS=po["WERKS"].to_numpy(), AWTYP="MKPF", AWREF=po["EBELN"].to_numpy(),
             LIFNR=po["LIFNR"].to_numpy())
    gr = postings(len(po), RACCT=inv_acc, KOART="M", TSL=po["NETWR"].to_numpy(), MSL=po["QTY"].to_numpy(),
                  RUNIT="ST", **c)
    grir = postings(len(po), RACCT="350000", TSL=-po["NETWR"].to_numpy(), **c)
    grir["BAL"] = ~pd.Series(key).duplicated().to_numpy()
    docs.frames += [gr, grir]

    # supplier invoice (MM) per PO and payment
    h = po.groupby("EBELN", sort=False).agg(BUKRS=("BUKRS", "first"), LIFNR=("LIFNR", "first"),
                                             PERIOD=("PERIOD", "first"), NETWR=("NETWR", "sum")).reset_index()
    h["BLDAT"] = np.array([first_business_day(p) for p in h["PERIOD"]]) + rng.integers(1, 12, len(h)).astype(
        "timedelta64[D]")
    vat = h["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["vat"]).to_numpy()
    h["VAT"] = np.round(h["NETWR"].to_numpy() * vat, 2)
    _invoice_and_payment(h, "RE", cfg, docs, md, expense_lines=[
        dict(RACCT="350000", TSL=h["NETWR"].to_numpy())])


def _invoice_and_payment(h: pd.DataFrame, blart: str, cfg: GeneratorConfig, docs: Documents, md: MasterData,
                         expense_lines: list[dict], currency: np.ndarray | str = "EUR",
                         vat_deductible: np.ndarray | None = None) -> None:
    """Vendor invoice (AP line + expense/GRIR lines + input VAT) and its payment."""
    rng = cfg.rng(f"pay_{blart}")
    zterm = md.lfa1.set_index("LIFNR")["ZTERM"]
    net_days = h["LIFNR"].map(zterm).map(lambda z: C.PAYMENT_TERMS[z]["net"]).to_numpy()
    bldat = h["BLDAT"].to_numpy().astype("datetime64[D]")
    netdt = bldat + net_days.astype("timedelta64[D]")
    ref = h["REF"].to_numpy() if "REF" in h else h["EBELN"].to_numpy()
    key = (blart + pd.Series(ref)).to_numpy()
    gross = h["NETWR"].to_numpy() + h["VAT"].to_numpy()
    base = dict(DOC_KEY=key, BUKRS=h["BUKRS"].to_numpy(), BUDAT=bldat, BLART=blart, RTCUR=currency,
                AWTYP="RMRP" if blart == "RE" else "BKPF", AWREF=ref, XBLNR=ref)
    ap = postings(len(h), RACCT="330000", KOART="K", LIFNR=h["LIFNR"].to_numpy(), TSL=-gross, NETDT=netdt,
                  BAL=True, PRCTR=h["BUKRS"].map(lambda x: f"P{x}_ZENT").to_numpy(), **base)
    frames = [ap]
    for el in expense_lines:
        frames.append(postings(len(h), **{**base, **el}))
    has_vat = h["VAT"].to_numpy() != 0
    if has_vat.any():
        frames.append(postings(int(has_vat.sum()), RACCT="140000", MWSKZ="V1", TSL=h["VAT"].to_numpy()[has_vat],
                               **{k: (v[has_vat] if isinstance(v, np.ndarray) else v) for k, v in base.items()}))
    pay = netdt + rng.integers(-2, 4, len(h)).astype("timedelta64[D]")
    pay = np.maximum(pay, bldat)
    wd = (pay.view("int64") - 4) % 7
    pay = pay + np.where(wd == 5, 2, np.where(wd == 6, 1, 0)).astype("timedelta64[D]")
    paid = pay <= END_DATE
    pkey = ("KZ" + pd.Series(ref[paid])).to_numpy()
    pb = dict(DOC_KEY=pkey, BUKRS=h["BUKRS"].to_numpy()[paid], BUDAT=pay[paid], BLART="KZ",
              RTCUR=currency if isinstance(currency, str) else currency[paid], AWTYP="BKPF", XBLNR=ref[paid])
    frames.append(postings(int(paid.sum()), RACCT="330000", KOART="K", LIFNR=h["LIFNR"].to_numpy()[paid],
                           TSL=gross[paid], CLEAR_KEY=pkey,
                           PRCTR=h["BUKRS"].map(lambda x: f"P{x}_ZENT").to_numpy()[paid], **pb))
    # EUR invoices in a PLN company code: bank at the payment-day rate, difference to FX account
    fx_doc = (h["BUKRS"].to_numpy()[paid] == "3000") & (np.asarray(pb["RTCUR"]) == "EUR") \
        if not isinstance(pb["RTCUR"], str) else np.full(int(paid.sum()), pb["RTCUR"] == "EUR") & \
        (h["BUKRS"].to_numpy()[paid] == "3000")
    frames.append(postings(int(paid.sum()), RACCT="180000", TSL=-gross[paid], BAL=~fx_doc, **pb))
    if fx_doc.any():
        frames.append(postings(int(fx_doc.sum()), RACCT="760000", TSL=0.0, BAL=True,
                               SGTXT="Realisierte Kursdifferenz",
                               **{k: (v[fx_doc] if isinstance(v, np.ndarray) else v) for k, v in pb.items()}))
    # clear the invoice's AP line too
    clear_map = dict(zip(key[paid], pkey, strict=False))
    ap["CLEAR_KEY"] = pd.Series(ap["DOC_KEY"]).map(clear_map).fillna("").to_numpy()
    docs.frames += frames


# --------------------------------------------------------------------------------------
# Overheads, energy, payroll, depreciation, interest, tax
# --------------------------------------------------------------------------------------
_CATEGORY = {"520000": "ENERGIE", "530000": "INSTAND", "700000": "MIETE", "701000": "INSTAND",
             "702000": "FRACHT", "703000": "REISE", "704000": "WERBUNG", "705000": "IT",
             "706000": "BERATUNG", "707000": "VERSICH", "709000": "SONST"}


def overheads(md: MasterData, drivers: pd.DataFrame, scenario: Scenario, cfg: GeneratorConfig,
              revenue_by_month: pd.DataFrame, docs: Documents) -> pd.DataFrame:
    """Fixed costs from the expectation model with noise; returns the actual amounts."""
    rng = cfg.rng("overheads")
    exp = M.fixed_cost_expectations(md, drivers, scenario, cfg.scale)
    # freight: variable with physical revenue, booked on the logistics cost centre
    fr = revenue_by_month.copy()
    fr["KOSTL"] = fr["BUKRS"].map(C.LOGISTICS_CC)
    fr["RACCT"] = "702000"
    fr["AMOUNT"] = fr["REVENUE_PHYS"] * M.freight_rate()
    exp = pd.concat([exp, fr[["BUKRS", "KOSTL", "RACCT", "PERIOD", "AMOUNT"]]], ignore_index=True)
    sd = np.where(exp["RACCT"].isin(["600000", "601000", "640000"]), 0.008,
                  np.where(exp["RACCT"] == "680000", 0.0, 0.06)) * scenario.noise_level
    exp["ACTUAL"] = np.round(exp["AMOUNT"] * np.exp(rng.normal(0.0, sd) - sd ** 2 / 2), 2)
    exp = exp[exp["ACTUAL"].abs() > 0.005].reset_index(drop=True)
    pcs = md.csks.drop_duplicates("KOSTL", keep="last").set_index("KOSTL")["PRCTR"]

    # payroll: one document per cost centre and month (summarised posting from payroll)
    pr = exp[exp["RACCT"].isin(["600000", "601000", "640000"])].copy()
    pr["DATE"] = [last_business_day(p) for p in pr["PERIOD"]]
    pkey = ("SA-PY-" + pr["BUKRS"] + pr["KOSTL"] + pr["PERIOD"]).to_numpy()
    cur = pr["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["currency"]).to_numpy()
    base = dict(DOC_KEY=pkey, BUKRS=pr["BUKRS"].to_numpy(), BUDAT=pr["DATE"].to_numpy(), BLART="SA", RTCUR=cur,
                AWTYP="HRPAY", SGTXT="Lohn- und Gehaltsabrechnung")
    e = postings(len(pr), RACCT=pr["RACCT"].to_numpy(), RCNTR=pr["KOSTL"].to_numpy(),
                 PRCTR=pr["KOSTL"].map(pcs).to_numpy(), TSL=pr["ACTUAL"].to_numpy(), **base)
    lia = postings(len(pr), RACCT="370000", TSL=-pr["ACTUAL"].to_numpy(), **base)
    lia["BAL"] = ~pd.Series(pkey).duplicated().to_numpy()
    docs.frames += [e, lia]
    pay = pr.groupby(["BUKRS", "PERIOD"], as_index=False)["ACTUAL"].sum()
    pay["DATE"] = [last_business_day(p) for p in pay["PERIOD"]]
    k = ("SA-PYPAY-" + pay["BUKRS"] + pay["PERIOD"]).to_numpy()
    pc = pay["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["currency"]).to_numpy()
    b2 = dict(DOC_KEY=k, BUKRS=pay["BUKRS"].to_numpy(), BUDAT=pay["DATE"].to_numpy(), BLART="SA", RTCUR=pc,
              SGTXT="Auszahlung Löhne, Gehälter und Sozialabgaben")
    docs.frames += [postings(len(pay), RACCT="370000", TSL=pay["ACTUAL"].to_numpy(), **b2),
                    postings(len(pay), RACCT="180000", TSL=-pay["ACTUAL"].to_numpy(), BAL=True, **b2)]

    # depreciation
    dp = exp[exp["RACCT"] == "680000"].copy()
    dp["DATE"] = [last_business_day(p) for p in dp["PERIOD"]]
    dkey = ("AF-" + dp["BUKRS"] + dp["KOSTL"] + dp["PERIOD"]).to_numpy()
    dc = dp["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["currency"]).to_numpy()
    b3 = dict(DOC_KEY=dkey, BUKRS=dp["BUKRS"].to_numpy(), BUDAT=dp["DATE"].to_numpy(), BLART="AF", RTCUR=dc,
              AWTYP="AMDP")
    docs.frames += [postings(len(dp), RACCT="680000", RCNTR=dp["KOSTL"].to_numpy(),
                             PRCTR=dp["KOSTL"].map(pcs).to_numpy(), TSL=dp["ACTUAL"].to_numpy(), **b3),
                    postings(len(dp), RACCT="039000", TSL=-dp["ACTUAL"].to_numpy(), BAL=True, **b3)]

    # vendor invoices for all other cost accounts: split into 1-4 invoices
    oh = exp[~exp["RACCT"].isin(["600000", "601000", "640000", "680000"])].reset_index(drop=True)
    n_inv = np.where(oh["RACCT"].isin(["520000", "707000", "700000"]), 1, rng.integers(1, 5, len(oh)))
    rep = oh.loc[oh.index.repeat(n_inv)].reset_index(drop=True)
    shares = np.concatenate([rng.dirichlet(np.ones(k) * 2.0) for k in n_inv])
    rep["NETWR"] = np.round(rep["ACTUAL"].to_numpy() * shares, 2)
    rep["BLDAT"] = random_business_days(rep["PERIOD"].to_numpy(), rng)
    vend = _vendor_pool(md)
    rep["LIFNR"] = [vend[(b, _CATEGORY[a])][int(rng.integers(0, len(vend[(b, _CATEGORY[a])])))]
                    for b, a in zip(rep["BUKRS"], rep["RACCT"], strict=False)]
    no_vat = rep["RACCT"].isin(["707000"])
    vat = rep["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["vat"]).to_numpy()
    rep["VAT"] = np.where(no_vat, 0.0, np.round(rep["NETWR"].to_numpy() * vat, 2))
    rep["REF"] = [f"KR{b}{i:08d}" for i, b in enumerate(rep["BUKRS"])]
    cur = rep["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["currency"]).to_numpy()
    _invoice_and_payment(rep, "KR", cfg, docs, md, currency=cur, expense_lines=[
        dict(RACCT=rep["RACCT"].to_numpy(), RCNTR=rep["KOSTL"].to_numpy(),
             PRCTR=rep["KOSTL"].map(pcs).to_numpy(), TSL=rep["NETWR"].to_numpy(),
             SGTXT=np.where(rep["RACCT"] == "701000", "Instandhaltung Fremdleistung", ""))])

    # interest and quarterly income-tax prepayments (no cost centre)
    rows = []
    for bukrs in C.COMPANY_CODES:
        local = M.PL_PRICE_LIST_FX if bukrs == "3000" else 1.0
        for p in M.periods(C.FIRST_PERIOD, C.LAST_PERIOD):
            d = last_business_day(p)
            rows.append((bukrs, p, d, "750000", {"1000": 95_000, "2000": 12_000, "3000": 20_000}[bukrs] * local))
            if int(p[5:7]) in (3, 6, 9, 12):
                rows.append((bukrs, p, np.datetime64(f"{p}-10"), "770000",
                             {"1000": 1_100_000, "2000": 150_000, "3000": 120_000}[bukrs] * local))
    it = pd.DataFrame(rows, columns=["BUKRS", "PERIOD", "DATE", "RACCT", "AMOUNT"])
    # opening bank balance (carry-forward 01.01.2023) and yearly profit distribution in May
    eq = []
    for bukrs in C.COMPANY_CODES:
        local = M.PL_PRICE_LIST_FX if bukrs == "3000" else 1.0
        eq.append((bukrs, "2023-01", np.datetime64("2023-01-02"), "290000",
                   -{"1000": 12e6, "2000": 2.5e6, "3000": 2.0e6}[bukrs] * local))
        for y, d in ((2023, 22e6), (2024, 26e6), (2025, 30e6)):
            amt = {"1000": d, "2000": d * 0.15, "3000": d * 0.2}[bukrs] * local
            eq.append((bukrs, f"{y}-05", np.datetime64(f"{y}-05-15"), "290000", amt))
    it = pd.concat([it, pd.DataFrame(eq, columns=it.columns)], ignore_index=True)
    it["AMOUNT"] = np.round(it["AMOUNT"] * cfg.scale, 2)
    ikey = ("SA-FIN-" + it["BUKRS"] + it["PERIOD"] + it["RACCT"]).to_numpy()
    ic = it["BUKRS"].map(lambda x: C.COMPANY_CODES[x]["currency"]).to_numpy()
    b4 = dict(DOC_KEY=ikey, BUKRS=it["BUKRS"].to_numpy(), BUDAT=it["DATE"].to_numpy().astype("datetime64[D]"),
              BLART="SA", RTCUR=ic)
    docs.frames += [postings(len(it), RACCT=it["RACCT"].to_numpy(), TSL=it["AMOUNT"].to_numpy(), **b4),
                    postings(len(it), RACCT="180000", TSL=-it["AMOUNT"].to_numpy(), BAL=True, **b4)]
    return exp


def vat_settlement(frames: list[pd.DataFrame], docs: Documents) -> None:
    """Monthly VAT return (Umsatzsteuer-Voranmeldung) paid on the 10th of the next month."""
    df = pd.concat([f[f["RACCT"].isin(["380000", "140000"])][["BUKRS", "BUDAT", "RACCT", "TSL", "RTCUR"]]
                    for f in frames if len(f)])
    df["PERIOD"] = to_period(df["BUDAT"].to_numpy().astype("datetime64[D]"))
    # PL purchases are in EUR: convert later in the journal; settle per transaction currency
    agg = df.groupby(["BUKRS", "PERIOD", "RACCT", "RTCUR"], as_index=False)["TSL"].sum()
    out = []
    for (bukrs, period, cur), g in agg.groupby(["BUKRS", "PERIOD", "RTCUR"]):
        nxt = M.shift_period(period, 1)
        if nxt > C.LAST_PERIOD:
            continue
        date = np.datetime64(f"{nxt}-10")
        key = f"UV-{bukrs}-{period}-{cur}"
        for _, r in g.iterrows():
            out.append(postings(1, DOC_KEY=key, BUKRS=bukrs, BUDAT=date, BLART="UV", RACCT=r["RACCT"],
                                RTCUR=cur, TSL=-r["TSL"], SGTXT=f"USt-Voranmeldung {period}"))
        out.append(postings(1, DOC_KEY=key, BUKRS=bukrs, BUDAT=date, BLART="UV", RACCT="180000", RTCUR=cur,
                            TSL=0.0, BAL=True, SGTXT=f"USt-Voranmeldung {period}"))
    docs.frames += out
