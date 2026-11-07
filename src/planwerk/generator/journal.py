"""Turns posting frames into balanced ACDOCA line items and BKPF headers.

Every generator step emits a DataFrame of *postings* with a ``DOC_KEY`` that groups lines
into one document and exactly one line per document flagged ``BAL = True``. The balancing
line receives the negative sum of the other lines in transaction, local and group currency
after rounding, so every document balances to the cent in all three currencies.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from planwerk.generator import config as C

# Number range prefixes per document type (10-digit BELNR = prefix * 10^8 + sequence)
NUMBER_RANGE = {"RV": 90, "DZ": 14, "RE": 51, "KR": 19, "KZ": 15, "WA": 49, "WE": 50, "WL": 48,
                "SA": 10, "AF": 11, "UV": 12}

POSTING_COLUMNS = {
    "DOC_KEY": "", "BUKRS": "", "BUDAT": np.datetime64("NaT", "D"), "BLDAT": np.datetime64("NaT", "D"), "BLART": "",
    "RACCT": "", "RCNTR": "", "PRCTR": "", "RTCUR": "", "TSL": 0.0, "MSL": 0.0, "RUNIT": "",
    "KOART": "S", "KUNNR": "", "LIFNR": "", "MATNR": "", "WERKS": "", "AUFNR": "", "KDAUF": "",
    "KDPOS": "", "MATKL_MM": "", "KDGRP": "", "AWTYP": "", "AWREF": "", "NETDT": np.datetime64("NaT", "D"),
    "CLEAR_KEY": "", "MWSKZ": "", "SGTXT": "", "XBLNR": "", "BAL": False,
}


def postings(n: int, **cols) -> pd.DataFrame:
    """Create a posting frame of length n; scalar or array values per column."""
    data = {}
    for c, default in POSTING_COLUMNS.items():
        v = cols.get(c, default)
        if np.isscalar(v) or v is None or isinstance(v, np.datetime64):
            data[c] = np.full(n, v) if not isinstance(v, str) else np.full(n, v, dtype=object)
        else:
            data[c] = np.asarray(v)
    unknown = set(cols) - set(POSTING_COLUMNS)
    if unknown:
        raise KeyError(f"unknown posting columns {unknown}")
    return pd.DataFrame(data)


def _local_currency(bukrs: pd.Series) -> pd.Series:
    return bukrs.map({k: v["currency"] for k, v in C.COMPANY_CODES.items()})


def finalize(frames: list[pd.DataFrame], fx: dict[str, float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.concat([f for f in frames if len(f)], ignore_index=True)
    df["BUDAT"] = pd.to_datetime(df["BUDAT"])
    df["BLDAT"] = pd.to_datetime(df["BLDAT"]).fillna(df["BUDAT"])
    df["NETDT"] = pd.to_datetime(df["NETDT"])
    df["PERIOD"] = df["BUDAT"].dt.strftime("%Y-%m")
    rate = df["PERIOD"].map(fx).astype(float)
    df["RHCUR"] = _local_currency(df["BUKRS"])
    df["RKCUR"] = C.GROUP_CURRENCY

    tsl = df["TSL"].astype(float).round(2)
    hsl = np.where(df["RTCUR"] == df["RHCUR"], tsl,
                   np.where((df["RHCUR"] == "PLN") & (df["RTCUR"] == "EUR"), tsl * rate, np.nan))
    if np.isnan(hsl).any():
        raise ValueError("unsupported currency combination in postings")
    hsl = np.round(hsl, 2)
    ksl = np.where(df["RHCUR"] == "EUR", hsl, np.where(df["RTCUR"] == "EUR", tsl, hsl / rate))
    ksl = np.round(ksl, 2)
    df["TSL"], df["HSL"], df["KSL"] = tsl, hsl, ksl

    def _balance() -> None:
        bal = df["BAL"].astype(bool).to_numpy()
        for col in ("TSL", "HSL", "KSL"):
            others = df.loc[~bal].groupby("DOC_KEY")[col].sum()
            df.loc[bal, col] = -df.loc[bal, "DOC_KEY"].map(others).fillna(0.0).round(2).to_numpy()

    counts = df.loc[df["BAL"].astype(bool)].groupby("DOC_KEY").size()
    if (counts != 1).any() or counts.size != df["DOC_KEY"].nunique():
        raise ValueError("every document needs exactly one balancing line")
    _balance()
    # clearing lines take over the local-currency value of the open item they clear, so that
    # cleared items net to zero; exchange differences land on the balancing (FX) line
    clr = (df["CLEAR_KEY"] != "") & (df["CLEAR_KEY"] == df["DOC_KEY"])
    opn = (df["CLEAR_KEY"] != "") & (df["CLEAR_KEY"] != df["DOC_KEY"])
    if clr.any():
        orig = df.loc[opn].groupby(["CLEAR_KEY", "RACCT"])["HSL"].sum()
        idx = pd.MultiIndex.from_arrays([df.loc[clr, "CLEAR_KEY"], df.loc[clr, "RACCT"]])
        mapped = pd.Series(orig.reindex(idx).to_numpy(), index=df.index[clr])
        has = mapped.notna()
        df.loc[mapped.index[has], "HSL"] = -mapped[has].round(2)

        _balance()

    # document numbers per company code, fiscal year and document type
    df["GJAHR"] = df["BUDAT"].dt.year.astype(str)
    docs = (df.groupby("DOC_KEY", sort=False)
              .agg(BUKRS=("BUKRS", "first"), GJAHR=("GJAHR", "first"), BLART=("BLART", "first"),
                   BUDAT=("BUDAT", "first"), BLDAT=("BLDAT", "first"), RTCUR=("RTCUR", "first"),
                   XBLNR=("XBLNR", "first"), AWTYP=("AWTYP", "first"), AWREF=("AWREF", "first"))
              .reset_index())
    docs = docs.sort_values(["BUKRS", "GJAHR", "BLART", "BUDAT", "DOC_KEY"]).reset_index(drop=True)
    seq = docs.groupby(["BUKRS", "GJAHR", "BLART"]).cumcount() + 1
    prefix = docs["BLART"].map(NUMBER_RANGE)
    if prefix.isna().any():
        raise KeyError(f"no number range for {docs.loc[prefix.isna(), 'BLART'].unique()}")
    docs["BELNR"] = (prefix.astype(np.int64) * 10**8 + seq).astype(str).str.zfill(10)
    belnr = dict(zip(docs["DOC_KEY"], docs["BELNR"]))
    budat = dict(zip(docs["DOC_KEY"], docs["BUDAT"]))

    df["BELNR"] = df["DOC_KEY"].map(belnr)
    df = df.sort_values(["BUKRS", "GJAHR", "BELNR", "BAL"], kind="stable").reset_index(drop=True)
    df["DOCLN"] = (df.groupby(["BUKRS", "GJAHR", "BELNR"]).cumcount() + 1).astype(str).str.zfill(6)
    df["AUGBL"] = df["CLEAR_KEY"].map(belnr).fillna("")
    df["AUGDT"] = pd.to_datetime(df["CLEAR_KEY"].map(budat))
    df["DRCRK"] = np.where(df["HSL"] >= 0, "S", "H")
    df["POPER"] = df["BUDAT"].dt.month.astype(str).str.zfill(3)
    df["RYEAR"] = df["GJAHR"]
    df["RCLNT"] = C.CLIENT
    df["RLDNR"] = C.LEDGER
    df["RBUKRS"] = df["BUKRS"]
    df["KOKRS"] = C.CONTROLLING_AREA

    acdoca = df[[
        "RCLNT", "RLDNR", "RBUKRS", "GJAHR", "BELNR", "DOCLN", "RYEAR", "POPER", "BUDAT", "BLDAT", "BLART",
        "RACCT", "KOKRS", "RCNTR", "PRCTR", "RTCUR", "RHCUR", "RKCUR", "TSL", "HSL", "KSL", "MSL", "RUNIT",
        "DRCRK", "KOART", "KUNNR", "LIFNR", "MATNR", "WERKS", "AUFNR", "KDAUF", "KDPOS", "MATKL_MM", "KDGRP",
        "AWTYP", "AWREF", "NETDT", "AUGBL", "AUGDT", "MWSKZ", "SGTXT",
    ]].copy()
    acdoca["BUDAT"] = acdoca["BUDAT"].dt.date
    acdoca["BLDAT"] = acdoca["BLDAT"].dt.date
    acdoca["NETDT"] = acdoca["NETDT"].dt.date
    acdoca["AUGDT"] = acdoca["AUGDT"].dt.date

    bkpf = docs.rename(columns={"RTCUR": "WAERS"})
    bkpf["MONAT"] = bkpf["BUDAT"].dt.month.astype(str).str.zfill(2)
    bkpf["CPUDT"] = bkpf["BUDAT"].dt.date
    bkpf["BUDAT"] = bkpf["BUDAT"].dt.date
    bkpf["BLDAT"] = bkpf["BLDAT"].dt.date
    bkpf["USNAM"] = bkpf["BLART"].map({"RV": "BATCH_SD", "WA": "BATCH_PP", "WE": "BATCH_MM", "WL": "BATCH_SD",
                                       "RE": "BATCH_MM", "SA": "BATCH_HR", "AF": "BATCH_AA"}).fillna("FI_USER")
    bkpf["BSTAT"] = ""
    bkpf = bkpf[["BUKRS", "BELNR", "GJAHR", "BLART", "BLDAT", "BUDAT", "MONAT", "CPUDT", "USNAM", "WAERS",
                 "XBLNR", "AWTYP", "AWREF", "BSTAT", "DOC_KEY"]]
    return acdoca, bkpf
