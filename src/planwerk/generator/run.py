"""Orchestrates a full generator run and writes all tables as Parquet."""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from planwerk import SIMULATED_LABEL, __version__
from planwerk.generator import config as C
from planwerk.generator import model as M
from planwerk.generator import transactions as T
from planwerk.generator.config import GeneratorConfig
from planwerk.generator.drivers import load_drivers
from planwerk.generator.ground_truth import compute_ground_truth
from planwerk.generator.journal import finalize
from planwerk.generator.masterdata import build_master_data
from planwerk.generator.plan import build_plan
from planwerk.generator.scenario import Scenario, main_scenario


def generate(cfg: GeneratorConfig, scenario: Scenario | None = None, write: bool = True,
             log=print) -> dict[str, pd.DataFrame]:
    t0 = time.time()
    scenario = scenario or main_scenario()
    drivers = load_drivers()
    md = build_master_data(cfg, drivers, scenario.component_price_change_plan)
    log(f"master data: {len(md.mara)} materials, {len(md.kna1)} customers, {len(md.csks)} cost-centre records")

    docs = T.Documents()
    comp_prices = T.component_actual_prices(md, drivers, cfg)
    items = T.generate_orders(md, scenario, cfg)
    T.sales_documents(items, md, docs)
    hawa_prices = comp_prices[comp_prices["MATNR"].isin(md.mara.loc[md.mara["MTART"] == "HAWA", "MATNR"])]
    inv = T.billing(items, md, cfg, md.mbew, hawa_prices, docs)
    T.customer_payments(inv, cfg, docs)
    log(f"sales: {len(docs.vbak)} orders, {len(docs.vbap)} order items, {len(docs.vbrk)} invoices")
    cons = T.production(items, md, comp_prices, md.mbew, cfg, docs)
    billed = items[items["BILL_PERIOD"] <= C.LAST_PERIOD]
    T.purchasing(cons, billed, comp_prices, md, cfg, docs)
    log(f"production/purchasing: {len(docs.afko)} production orders, {len(docs.ekpo)} PO items")

    phys = billed[billed["MATKL"] != "PG50"].groupby(["BUKRS", "BILL_PERIOD"], as_index=False)["NETWR"].sum()
    phys = phys.rename(columns={"BILL_PERIOD": "PERIOD", "NETWR": "REVENUE_PHYS"})
    T.overheads(md, drivers, scenario, cfg, phys, docs)
    T.vat_settlement(docs.frames, docs)

    fx = M.fx_actual(drivers)
    acdoca, bkpf = finalize(docs.frames, fx)
    log(f"journal: {len(acdoca):,} ACDOCA lines in {len(bkpf):,} documents")
    acdocp = build_plan(md, drivers, scenario, cfg.scale)
    log(f"plan: {len(acdocp):,} ACDOCP lines")
    truth = compute_ground_truth(md, drivers, scenario, cfg.scale)

    tables: dict[str, pd.DataFrame] = {
        **{k.upper(): v for k, v in md.tables().items() if k != "alloc_keys"},
        "ALLOC_KEYS": md.alloc_keys,
        "VBAK": docs.vbak, "VBAP": docs.vbap, "VBRK": docs.vbrk, "VBRP": docs.vbrp,
        "AFKO": docs.afko, "EKKO": docs.ekko, "EKPO": docs.ekpo,
        "BKPF": bkpf.drop(columns=["DOC_KEY"]), "ACDOCA": acdoca, "ACDOCP": acdocp,
    }
    # BSEG compatibility: FI view of the open-item relevant lines (customer/vendor/GL)
    tables["BSEG"] = acdoca[["RBUKRS", "BELNR", "GJAHR", "DOCLN", "RACCT", "KOART", "DRCRK", "HSL", "TSL",
                             "KUNNR", "LIFNR", "RCNTR", "PRCTR", "AUGBL", "AUGDT", "NETDT", "MWSKZ", "SGTXT"]].rename(
        columns={"RBUKRS": "BUKRS", "DOCLN": "BUZEI", "RACCT": "HKONT", "DRCRK": "SHKZG", "HSL": "DMBTR",
                 "TSL": "WRBTR", "RCNTR": "KOSTL"})
    tables["DRIVERS"] = drivers.drop(columns=["quarter"])
    tables["PRICE_LIST"], tables["DISCOUNT_COND"] = M.price_conditions(md, scenario)
    if write:
        _write(cfg, tables, scenario, truth, time.time() - t0, log)
    tables["_ground_truth"] = truth  # type: ignore[assignment]
    return tables


def _write(cfg: GeneratorConfig, tables: dict, scenario: Scenario, truth: dict, seconds: float, log) -> None:
    out = Path(cfg.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, df in tables.items():
        df = df.copy()
        for c in df.columns:
            if df[c].dtype == object:
                sample = df[c].dropna()
                first = sample.iloc[0] if len(sample) else ""
                if isinstance(first, datetime.date):
                    df[c] = pd.to_datetime(df[c]).astype("datetime64[s]").dt.date
                    continue
                df[c] = df[c].astype("string")
        df.to_parquet(out / f"{name.lower()}.parquet", index=False)
        counts[name] = len(df)
    driver_hash = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(C.DRIVER_DIR.glob("*.csv")))).hexdigest()
    manifest = dict(label=SIMULATED_LABEL, generator_version=__version__, seed=cfg.seed, profile=cfg.profile,
                    scale=cfg.scale, periods=[cfg.first_period, cfg.last_period], row_counts=counts,
                    driver_sha256=driver_hash, runtime_seconds=round(seconds, 1), scenario=scenario.to_dict())
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
    (out / "ground_truth.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False, default=str))
    log(f"wrote {len(tables)} tables to {out}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Generate the simulated Nordwerk GmbH S/4HANA data set")
    ap.add_argument("--profile", default="dev", choices=sorted(C.PROFILES))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=C.REPO_ROOT / "data" / "raw")
    ap.add_argument("--noise-level", type=float, default=1.0,
                    help="scale of random demand and cost noise; 0 = exploratory noise-free run (not the main scenario)")
    a = ap.parse_args(argv)
    scenario = main_scenario()
    if a.noise_level != 1.0:
        scenario = dataclasses.replace(scenario, noise_level=a.noise_level)
    generate(GeneratorConfig(seed=a.seed, profile=a.profile, out_dir=a.out), scenario)


if __name__ == "__main__":
    main()
