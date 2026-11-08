"""Master data in S/4HANA table shapes.

Tables: T001, T001W, SKA1/SKAT (accounts), CSKS/CSKT (cost centres, with validity
intervals -> SCD2 source), CEPC (profit centres), MARA/MAKT/MARC/MBEW, STPO (BOM, lite),
KNA1/KNVV, LFA1. Column names follow SAP technical names; only a relevant subset of
columns is generated.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from planwerk.generator import config as C
from planwerk.generator.config import GeneratorConfig

FAR_FUTURE = "9999-12-31"

# Fictional name parts. Combinations are random, so any match with a real company is
# coincidental; every table carries the SIMULATED label in the data catalogue.
_NAME_A = ["Alder", "Birk", "Dorn", "Eschen", "Falk", "Gerst", "Hagen", "Ilm", "Kalm", "Linden",
           "Moor", "Nessel", "Osten", "Pappel", "Quell", "Ried", "Sand", "Tann", "Ulmen", "Wald",
           "Weiden", "Zinn", "Brunn", "Kessel", "Mühl", "Stein", "Ahorn", "Holm", "Klee", "Rabe"]
_NAME_B = ["au", "berg", "bach", "feld", "hof", "horst", "kamp", "ried", "stedt", "tal", "dorf", "brück"]
_INDUSTRY = {
    "01": ["Anlagenbau", "Maschinenbau", "Prozesstechnik", "Apparatebau"],
    "02": ["Chemie", "Lebensmitteltechnik", "Papierfabrik", "Brauerei", "Kunststoffwerk", "Galvanik"],
    "03": ["Wasserverband", "Stadtwerke", "Abwasserzweckverband", "Wasserversorgung"],
    "04": ["Industriebedarf", "Technischer Handel", "Pumpenhandel", "Haustechnik Großhandel"],
}
_LEGAL = {"DE": ["GmbH", "GmbH & Co. KG", "AG", "KG"], "AT": ["GmbH", "Ges.m.b.H.", "AG"],
          "PL": ["Sp. z o.o.", "S.A.", "Sp. j."]}
_PL_INDUSTRY = {"01": ["Inżynieria", "Budowa Maszyn"], "02": ["Zakłady Chemiczne", "Przetwórstwo"],
                "03": ["Wodociągi", "Przedsiębiorstwo Komunalne"], "04": ["Hurtownia Techniczna", "Handel"]}
_PL_NAMES = ["Warta", "Odra", "Noteć", "Prosna", "Obra", "Wełna", "Gopło", "Brda", "Wieprz", "Bóbr"]
_CITIES = {
    "DE": ["Bremen", "Hamburg", "Hannover", "Dortmund", "Bielefeld", "Osnabrück", "Kiel", "Münster",
           "Oldenburg", "Essen", "Köln", "Kassel", "Magdeburg", "Leipzig", "Stuttgart", "Nürnberg"],
    "AT": ["Linz", "Wien", "Graz", "Salzburg", "Wels", "Steyr", "Innsbruck", "St. Pölten"],
    "PL": ["Poznań", "Wrocław", "Łódź", "Gdańsk", "Szczecin", "Katowice", "Kraków", "Bydgoszcz"],
}


@dataclass
class MasterData:
    t001: pd.DataFrame
    t001w: pd.DataFrame
    ska1: pd.DataFrame
    cepc: pd.DataFrame
    csks: pd.DataFrame
    mara: pd.DataFrame
    marc: pd.DataFrame
    mbew: pd.DataFrame
    stpo: pd.DataFrame
    kna1: pd.DataFrame
    knvv: pd.DataFrame
    lfa1: pd.DataFrame
    alloc_keys: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        return {k: v for k, v in self.__dict__.items()}


# --------------------------------------------------------------------------------------
def _company_codes() -> tuple[pd.DataFrame, pd.DataFrame]:
    t001 = pd.DataFrame([
        dict(BUKRS=k, BUTXT=v["name"], ORT01=v["city"], LAND1=v["country"], WAERS=v["currency"],
             KTOPL="NWKR", KKBER=C.CONTROLLING_AREA, PERIV="K4")
        for k, v in C.COMPANY_CODES.items()
    ])
    t001w = pd.DataFrame([
        dict(WERKS=v["plant"], NAME1=f"Werk {v['city']}", BWKEY=v["plant"], BUKRS=k, LAND1=v["country"])
        for k, v in C.COMPANY_CODES.items()
    ])
    return t001, t001w


def _accounts() -> pd.DataFrame:
    rows = []
    for saknr, a in C.ACCOUNTS.items():
        rows.append(dict(KTOPL="NWKR", SAKNR=saknr, TXT50=a["text"],
                         XBILK="X" if a["kind"] == "B" else "",
                         GLACCOUNT_TYPE="X" if a["kind"] == "B" else "P",
                         KATYP="" if a["kind"] == "B" else "01",
                         GKV_POSITION=a["gkv"], CM_BLOCK=a["cm"]))
    return pd.DataFrame(rows)


def _profit_centre_for(bukrs: str, kostl: str, level: str, name: str) -> str:
    if "Service" in name:
        return f"P{bukrs}_SERV"
    if bukrs == "1000" and kostl == "1510":
        return "P1000_VENT"
    if bukrs == "1000" and kostl in ("1500", "1520"):
        return "P1000_PUMP"
    if level == "DB2" and bukrs != "1000":
        return f"P{bukrs}_FERT"
    return f"P{bukrs}_ZENT"


def _profit_centres() -> pd.DataFrame:
    rows = []
    texts = {"PUMP": "Pumpen", "VENT": "Ventile", "SERV": "Service und Ersatzteile",
             "FERT": "Fertigung", "ZENT": "Zentrale"}
    for bukrs in C.COMPANY_CODES:
        for suffix, txt in texts.items():
            if bukrs != "1000" and suffix in ("PUMP", "VENT"):
                continue
            if bukrs == "1000" and suffix == "FERT":
                continue
            rows.append(dict(KOKRS=C.CONTROLLING_AREA, PRCTR=f"P{bukrs}_{suffix}", BUKRS=bukrs,
                             KTEXT=f"{txt} {C.COMPANY_CODES[bukrs]['country']}", DATAB="2020-01-01",
                             DATBI=FAR_FUTURE))
    return pd.DataFrame(rows)


def _cost_centres(cfg: GeneratorConfig) -> pd.DataFrame:
    """CSKS with validity intervals. Three changes create SCD2 history:

    * 2024-01-01 cost centre 1520 moves from profit centre P1000_PUMP to P1000_ZENT
      (Mechanische Fertigung becomes a shared service for pumps and valves).
    * 2024-07-01 new manager for 1610 Vertrieb Export.
    * 2025-01-01 new manager for 2600 Vertrieb AT.
    * New cost centre 1630 Digitaler Vertrieb valid from 2024-04-01.
    """
    rng = cfg.rng("csks")
    managers = list(C.MANAGERS)
    rng.shuffle(managers)
    rows = []
    for i, (bukrs, kostl, name, level, hc, _wage, _blue) in enumerate(C.COST_CENTRES):
        base = dict(KOKRS=C.CONTROLLING_AREA, KOSTL=kostl, BUKRS=bukrs, KTEXT=name[:20], LTEXT=name,
                    KOSAR={"HILF": "H", "DB2": "F", "DB3": "V", "UNT": "W"}[level],
                    CM_LEVEL=level, VERAK=managers[i % len(managers)],
                    PRCTR=_profit_centre_for(bukrs, kostl, level, name), WAERS=C.COMPANY_CODES[bukrs]["currency"],
                    HEADCOUNT=hc, DATAB="2020-01-01", DATBI=FAR_FUTURE)
        if kostl == "1520":
            rows.append({**base, "DATBI": "2023-12-31"})
            rows.append({**base, "DATAB": "2024-01-01", "PRCTR": "P1000_ZENT"})
        elif kostl == "1610":
            rows.append({**base, "DATBI": "2024-06-30"})
            rows.append({**base, "DATAB": "2024-07-01", "VERAK": "S. Neumann"})
        elif kostl == "2600":
            rows.append({**base, "DATBI": "2024-12-31"})
            rows.append({**base, "DATAB": "2025-01-01", "VERAK": "E. Brandstätter"})
        else:
            rows.append(base)
    rows.append(dict(KOKRS=C.CONTROLLING_AREA, KOSTL="1630", BUKRS="1000", KTEXT="Digitaler Vertrieb",
                     LTEXT="Digitaler Vertrieb / E-Shop", KOSAR="V", CM_LEVEL="DB3", VERAK="L. Brockmann",
                     PRCTR="P1000_SERV", WAERS="EUR", HEADCOUNT=5, DATAB="2024-04-01", DATBI=FAR_FUTURE))
    return pd.DataFrame(rows)


def cost_centre_params() -> pd.DataFrame:
    """Static parameters (headcount, wage, blue-collar share) per cost centre."""
    rows = [dict(BUKRS=b, KOSTL=k, NAME=n, LEVEL=l, HC=hc, WAGE=w, BLUE=bl, VALID_FROM="2020-01")
            for b, k, n, l, hc, w, bl in C.COST_CENTRES]
    rows.append(dict(BUKRS="1000", KOSTL="1630", NAME="Digitaler Vertrieb", LEVEL="DB3", HC=5, WAGE=6000,
                     BLUE=0.0, VALID_FROM="2024-04"))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
def _materials(cfg: GeneratorConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Finished goods, trading goods, services and raw components.

    Returns (mara, stpo). Prices: LIST_PRICE_2022 in EUR (DE price level),
    BASE_PRICE (components / trading goods purchase price at 2022-01 index level).
    """
    rng = cfg.rng("materials")
    rows = []
    # components
    comp_rows = []
    nr = 20000001
    for cls, c in C.COMPONENT_CLASSES.items():
        lo, hi = c["price"]
        prices = np.exp(rng.uniform(np.log(lo), np.log(hi), c["n"]))
        for j in range(c["n"]):
            comp_rows.append(dict(MATNR=str(nr), MTART="ROH", MATKL=cls, MAKTX=f"{c['name']} {j + 1:03d}",
                                  MEINS="ST", BASE_PRICE=round(float(prices[j]), 2), LIST_PRICE_2022=np.nan,
                                  POPULARITY=np.nan, DRIVER=c["driver"]))
            nr += 1
    comps = pd.DataFrame(comp_rows)

    prefix = {"PG10": 10000001, "PG20": 11000001, "PG30": 12000001, "PG40": 40000001, "PG50": 50000001}
    for pg, g in C.PRODUCT_GROUPS.items():
        lo, hi = g["price"]
        n = g["n"]
        if pg == "PG50":
            prices = np.array([135.0, 110.0, 120.0, 95.0])
            names = [f"Service {s}" for s in C.SERVICE_MATERIALS]
        else:
            prices = np.exp(rng.uniform(np.log(lo), np.log(hi), n))
            names = [f"{g['name']} Typ {pg[2:]}-{j + 1:03d}" for j in range(n)]
        pop = 1.0 / np.arange(1, n + 1) ** 0.9
        rng.shuffle(pop)
        pop = pop / pop.sum()
        for j in range(n):
            rows.append(dict(MATNR=str(prefix[pg] + j), MTART=g["mtart"], MATKL=pg, MAKTX=names[j][:40],
                             MEINS=g["unit"], LIST_PRICE_2022=round(float(prices[j]), 2),
                             BASE_PRICE=np.nan, POPULARITY=float(pop[j]),
                             DRIVER=C.TRADING_GOODS_DRIVER if pg == "PG40" else ""))
    prods = pd.DataFrame(rows)

    # trading goods: purchase price from material ratio
    avg_discount = 0.11
    hawa = prods["MTART"] == "HAWA"
    prods.loc[hawa, "BASE_PRICE"] = (prods.loc[hawa, "LIST_PRICE_2022"] * (1 - avg_discount)
                                     * C.PRODUCT_GROUPS["PG40"]["material_ratio"]
                                     * rng.uniform(0.85, 1.15, hawa.sum())).round(2)

    # BOM for finished goods: hit the material ratio at 2022 prices
    bom_rows = []
    by_cls = {cls: comps[comps["MATKL"] == cls].reset_index(drop=True) for cls in C.COMPONENT_CLASSES}
    for _, p in prods[prods["MTART"] == "FERT"].iterrows():
        g = C.PRODUCT_GROUPS[p["MATKL"]]
        target = p["LIST_PRICE_2022"] * (1 - avg_discount) * g["material_ratio"] * rng.uniform(0.9, 1.1)
        n_cls = {"STAHL": int(rng.integers(2, 4)), "KUNST": int(rng.integers(1, 3)),
                 "ELEK": int(rng.integers(1, 3)) if p["MATKL"] != "PG30" else int(rng.integers(0, 2))}
        weight_cls = {"STAHL": 0.50, "KUNST": 0.12, "ELEK": 0.38} if p["MATKL"] != "PG30" else \
            {"STAHL": 0.72, "KUNST": 0.18, "ELEK": 0.10}
        if n_cls["ELEK"] == 0:
            weight_cls = {"STAHL": 0.80, "KUNST": 0.20, "ELEK": 0.0}
        pos = 10
        for cls, k in n_cls.items():
            if k == 0:
                continue
            pick = by_cls[cls].sample(n=k, random_state=int(rng.integers(0, 2**31 - 1)))
            w = rng.dirichlet(np.ones(k))
            for (_, comp), wj in zip(pick.iterrows(), w, strict=False):
                value = target * weight_cls[cls] * wj
                qty = max(value / comp["BASE_PRICE"], 0.01)
                bom_rows.append(dict(MATNR=p["MATNR"], POSNR=f"{pos:04d}", IDNRK=comp["MATNR"],
                                     MENGE=round(float(qty), 3), MEINS="ST"))
                pos += 10
    stpo = pd.DataFrame(bom_rows)
    mara = pd.concat([prods, comps], ignore_index=True)
    mara["ERSDA"] = "2019-06-01"
    return mara, stpo


def _marc(mara: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _bukrs, cc in C.COMPANY_CODES.items():
        sub = mara[mara["MTART"] != "DIEN"]
        for _, m in sub.iterrows():
            rows.append(dict(MATNR=m["MATNR"], WERKS=cc["plant"],
                             BESKZ="E" if m["MTART"] == "FERT" else "F",
                             DISMM="PD", PLIFZ=0 if m["MTART"] == "FERT" else 10))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
def component_price_index(drivers: pd.DataFrame, driver: str, period: str) -> float:
    base = float(drivers.loc[drivers["period"] == "2022-01", driver].iloc[0])
    cur = float(drivers.loc[drivers["period"] == period, driver].iloc[0])
    return cur / base


def standard_prices(mara: pd.DataFrame, stpo: pd.DataFrame, drivers: pd.DataFrame,
                    plan_change: dict, years=(2023, 2024, 2025)) -> pd.DataFrame:
    """MBEW standard prices per year, set in September of the prior year.

    Standard for components/trading goods = base price x index(prior Sep) x (1 + planned change).
    Finished goods = BOM roll-up of component standards.
    """
    rows = []
    purchased = mara[mara["MTART"].isin(["ROH", "HAWA"])]
    for y in years:
        ref = f"{y - 1}-09"
        std = {}
        for _, m in purchased.iterrows():
            idx = component_price_index(drivers, m["DRIVER"], ref)
            std[m["MATNR"]] = m["BASE_PRICE"] * idx * (1 + plan_change[y])
        bom = stpo.assign(STD=stpo["IDNRK"].map(std))
        bom["VAL"] = bom["MENGE"] * bom["STD"]
        fert = bom.groupby("MATNR")["VAL"].sum()
        for matnr, val in {**std, **fert.to_dict()}.items():
            rows.append(dict(MATNR=matnr, BDATJ=y, STPRS=round(float(val), 4), PEINH=1, VPRSV="S"))
    for _, m in mara[mara["MTART"] == "DIEN"].iterrows():
        for y in years:
            rows.append(dict(MATNR=m["MATNR"], BDATJ=y, STPRS=0.0, PEINH=1, VPRSV="S"))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------
def _customers(cfg: GeneratorConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = cfg.rng("customers")
    kna1, knvv = [], []
    used_names: set[str] = set()
    for bukrs, n_base in C.CUSTOMERS_PER_COMPANY.items():
        country = C.COMPANY_CODES[bukrs]["country"]
        n = max(int(round(n_base * cfg.scale)), 12)
        segs = list(C.SEGMENTS)
        seg_p = np.array([C.SEGMENTS[s]["customer_share"] for s in segs])
        seg_draw = rng.choice(segs, size=n, p=seg_p / seg_p.sum())
        # guarantee every segment has customers
        seg_draw[: len(segs)] = segs
        weights = rng.lognormal(0.0, 1.1, n)
        for i in range(n):
            seg = str(seg_draw[i])
            kunnr = f"{int(bukrs[0]) * 1000000 + i + 1:010d}"
            for _ in range(50):
                if country == "PL":
                    name = f"{rng.choice(_PL_INDUSTRY[seg])} {rng.choice(_PL_NAMES)} {rng.choice(_LEGAL['PL'])}"
                else:
                    stem = f"{rng.choice(_NAME_A)}{rng.choice(_NAME_B)}"
                    name = f"{stem} {rng.choice(_INDUSTRY[seg])} {rng.choice(_LEGAL[country])}"
                    if seg == "03":
                        name = f"{rng.choice(_INDUSTRY[seg])} {stem}"
                if name not in used_names:
                    break
                name = f"{name} {i}"
            used_names.add(name)
            if seg == "01":
                zterm = "Z060"
            elif seg == "04":
                zterm = "Z014"
            elif seg == "03":
                zterm = "Z030"
            else:
                zterm = str(rng.choice(["Z030", "Z014"]))
            kna1.append(dict(KUNNR=kunnr, NAME1=name[:35], LAND1=country,
                             ORT01=str(rng.choice(_CITIES[country])), KTOKD="KUNA", BRSCH=seg,
                             STCEG=f"{country}{rng.integers(100000000, 999999999)}", ERDAT="2019-01-01",
                             LOEVM=""))
            knvv.append(dict(KUNNR=kunnr, VKORG=bukrs, VTWEG="10", SPART="00", KDGRP=seg, ZTERM=zterm,
                             WAERS=C.COMPANY_CODES[bukrs]["currency"], WEIGHT=float(weights[i]),
                             PAY_DELAY_MEAN=float(rng.gamma(2.0, 3.0 if seg != "03" else 6.0))))
    kna1 = pd.DataFrame(kna1)
    knvv = pd.DataFrame(knvv)

    # Largest Kommunal customer in Austria = the framework contract that is lost in 2025
    at = knvv[(knvv["VKORG"] == "2000") & (knvv["KDGRP"] == "03")]
    seg_total = at["WEIGHT"].sum()
    top = at.index[0]
    others = seg_total - knvv.loc[top, "WEIGHT"]
    if others > 0:
        knvv.loc[top, "WEIGHT"] = others * 0.40 / 0.60  # 40 % of the segment
    kna1.loc[kna1["KUNNR"] == knvv.loc[top, "KUNNR"], "NAME1"] = "Wasserverband Mühlried-Ennstal"

    # Master-data quality findings to be caught by the MDG-style checks (documented):
    dq = rng.choice(len(kna1), size=max(2, int(0.01 * len(kna1))), replace=False)
    kna1.loc[dq[: len(dq) // 2], "STCEG"] = ""  # missing VAT id
    dup_src = kna1.iloc[int(dq[-1])]
    dup = dup_src.copy()
    dup["KUNNR"] = f"{int(dup_src['KUNNR']) + 900000:010d}"
    kna1 = pd.concat([kna1, dup.to_frame().T], ignore_index=True)  # duplicate customer, never used
    return kna1, knvv


def _vendors(cfg: GeneratorConfig) -> pd.DataFrame:
    rng = cfg.rng("vendors")
    cats = ["STAHL", "KUNST", "ELEK", "HAWA", "ENERGIE", "MIETE", "INSTAND", "FRACHT", "REISE",
            "WERBUNG", "IT", "BERATUNG", "VERSICH", "SONST"]
    rows = []
    for bukrs, n_base in C.VENDORS_PER_COMPANY.items():
        country = C.COMPANY_CODES[bukrs]["country"]
        n = max(int(round(n_base * min(cfg.scale, 3.0))), len(cats))
        for i in range(n):
            cat = cats[i % len(cats)]
            stem = f"{rng.choice(_NAME_A)}{rng.choice(_NAME_B)}"
            rows.append(dict(LIFNR=f"{int(bukrs[0]) * 1000000 + 900000 + i + 1:010d}",
                             NAME1=f"{stem} {cat.title()} {rng.choice(_LEGAL[country])}"[:35],
                             LAND1=country, ORT01=str(rng.choice(_CITIES[country])), KTOKK="LIEF",
                             BUKRS=bukrs, CATEGORY=cat, ZTERM=str(rng.choice(["Z030", "Z014", "Z060"]))))
    return pd.DataFrame(rows)


def _allocation_keys() -> pd.DataFrame:
    """Statistical key figures per receiver cost centre (yearly, plan = actual structure).

    ENERGY: share of MWh, MAINT: share of machine/maintenance hours, IT: headcount based.
    """
    rows = []
    params = cost_centre_params()
    for bukrs in C.COMPANY_CODES:
        p = params[params["BUKRS"] == bukrs]
        prod = p[p["LEVEL"] == "DB2"]
        for _, r in p.iterrows():
            if r["LEVEL"] == "HILF":
                continue
            energy = {"DB2": 1.0 if "Fertigung" in r["NAME"] else 0.15}.get(r["LEVEL"], 0.05) * r["HC"]
            maint = (r["HC"] if "Fertigung" in r["NAME"] else 0.1 * r["HC"]) if r["LEVEL"] == "DB2" else \
                (0.05 * r["HC"] if r["LEVEL"] == "DB3" else 0.0)
            rows.append(dict(BUKRS=bukrs, KOSTL=r["KOSTL"], KEY_ENERGY=round(float(energy), 2),
                             KEY_MAINT=round(float(maint), 2), KEY_IT=float(r["HC"])))
        _ = prod
    keys = pd.DataFrame(rows)
    # Instandhaltung itself consumes energy; IT serves everyone including service cost centres
    for bukrs in C.COMPANY_CODES:
        for _, r in params[(params["BUKRS"] == bukrs) & (params["LEVEL"] == "HILF")].iterrows():
            keys = pd.concat([keys, pd.DataFrame([dict(
                BUKRS=bukrs, KOSTL=r["KOSTL"],
                KEY_ENERGY=round(0.5 * r["HC"], 2) if "Instand" in r["NAME"] else 0.0,
                KEY_MAINT=0.0, KEY_IT=float(r["HC"]))])], ignore_index=True)
    return keys


def build_master_data(cfg: GeneratorConfig, drivers: pd.DataFrame, plan_change: dict) -> MasterData:
    t001, t001w = _company_codes()
    mara, stpo = _materials(cfg)
    mbew = standard_prices(mara, stpo, drivers, plan_change)
    kna1, knvv = _customers(cfg)
    return MasterData(
        t001=t001, t001w=t001w, ska1=_accounts(), cepc=_profit_centres(), csks=_cost_centres(cfg),
        mara=mara, marc=_marc(mara), mbew=mbew, stpo=stpo, kna1=kna1, knvv=knvv,
        lfa1=_vendors(cfg), alloc_keys=_allocation_keys(),
    )
