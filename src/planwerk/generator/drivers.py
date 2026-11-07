"""Real macro drivers that shape the simulated cost and FX side.

Sources (snapshots committed in ``data/drivers``, see its README for provenance):

* Eurostat ``sts_inpp_m`` producer price indices for Germany (data supplied by Destatis),
  2021 = 100, not seasonally adjusted.
* Eurostat ``lc_lci_r2_q`` labour cost index, manufacturing (NACE C), 2020 = 100,
  seasonally and calendar adjusted, for DE, AT and PL.
* ECB reference rate EUR/PLN, monthly average.
* SMARD (Bundesnetzagentur) day-ahead price, bidding zone DE-LU, monthly average.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from planwerk.generator.config import DRIVER_DIR


@lru_cache(maxsize=4)
def load_drivers(driver_dir: Path = DRIVER_DIR) -> pd.DataFrame:
    """Return one row per month (2022-01 .. 2025-12) with all driver columns."""
    ppi = pd.read_csv(driver_dir / "eurostat_ppi_de_monthly.csv")
    fx = pd.read_csv(driver_dir / "ecb_eur_pln_monthly.csv")
    power = pd.read_csv(driver_dir / "smard_dayahead_de_lu_monthly.csv")
    lci = pd.read_csv(driver_dir / "eurostat_labour_cost_index_quarterly.csv")

    df = ppi.merge(fx, on="period", how="inner").merge(power, on="period", how="inner")
    df["quarter"] = df["period"].str[:4] + "-Q" + ((df["period"].str[5:7].astype(int) - 1) // 3 + 1).astype(str)
    df = df.merge(lci, on="quarter", how="left")
    if df[["lci_de", "lci_at", "lci_pl"]].isna().any().any():
        raise ValueError("labour cost index does not cover all months")
    df["year"] = df["period"].str[:4].astype(int)
    df["month"] = df["period"].str[5:7].astype(int)
    df = df.sort_values("period").reset_index(drop=True)
    if len(df) != 48:
        raise ValueError(f"expected 48 driver months 2022-01..2025-12, got {len(df)}")
    return df


def driver_value(drivers: pd.DataFrame, column: str, period: str) -> float:
    row = drivers.loc[drivers["period"] == period, column]
    if row.empty:
        raise KeyError(f"no driver value for {column} {period}")
    return float(row.iloc[0])


def lci_column(company_code: str) -> str:
    return {"1000": "lci_de", "2000": "lci_at", "3000": "lci_pl"}[company_code]
