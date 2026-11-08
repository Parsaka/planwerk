"""Q2 backtest: how many months earlier does the ML forecast flag a missed DB II target?

For every simulated scenario the aggregate model produces 36 months of actuals (with demand
noise and Poisson sampling) and the budget. At each month m = 1..12 of the target year each
method forecasts the full-year DB II; flags, detection month, lead time and false alarms are
computed exactly as pre-registered in ADR-0001.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from planwerk.forecast.evaluation import MISS_THRESHOLD, detection_month, false_alarm, flags
from planwerk.forecast.methods import METHODS
from planwerk.generator import aggregate as A
from planwerk.generator.config import REPO_ROOT, GeneratorConfig
from planwerk.generator.drivers import load_drivers
from planwerk.generator.masterdata import build_master_data
from planwerk.generator.scenario import main_scenario, random_scenario

YEAR = 2025


def plan_series(md, drivers, scenario, scale) -> pd.DataFrame:
    return pd.concat([A.monthly_db(md, drivers, scenario, scale, plan_year=y) for y in (2023, 2024, 2025)],
                     ignore_index=True)


def run_scenario(md, drivers, scenario, plan, scale: float, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    act = A.monthly_db(md, drivers, scenario, scale, rng=rng, noise=True, sample=True)
    return evaluate_series(act, plan, scenario.name)


def evaluate_series(act: pd.DataFrame, plan: pd.DataFrame, name: str) -> dict:
    target = float(plan[plan["PERIOD"].str[:4] == str(YEAR)]["DB2"].sum())
    actual = float(act[act["PERIOD"].str[:4] == str(YEAR)]["DB2"].sum())
    miss = actual < MISS_THRESHOLD * target
    out = dict(scenario=name, target=target, actual=actual, actual_vs_target=actual / target - 1, miss=miss)
    for meth, fn in METHODS.items():
        fc = [fn(act, plan, YEAR, m) for m in range(1, 13)]
        fl = flags(fc, target)
        out[meth] = dict(forecasts=fc, flags=fl, detection_month=detection_month(fl),
                         false_alarm=(false_alarm(fl) if not miss else False),
                         mape=float(np.mean([abs(f / actual - 1) for f in fc[:11]])))
    return out


def summarise(results: list[dict]) -> dict:
    misses = [r for r in results if r["miss"]]
    ok = [r for r in results if not r["miss"]]
    s = dict(n_scenarios=len(results), n_miss=len(misses), n_no_miss=len(ok))
    for meth in METHODS:
        det = np.array([r[meth]["detection_month"] for r in misses])
        s[meth] = dict(
            median_detection_month=float(np.median(det)) if len(det) else None,
            detected_share=float(np.mean(det <= 12)) if len(det) else None,
            false_alarm_rate=float(np.mean([r[meth]["false_alarm"] for r in ok])) if ok else None,
            mape_months_1_11=float(np.mean([r[meth]["mape"] for r in results])),
        )
    for meth in ("seasonal_naive", "ml"):
        lead = np.array([r["straight_line"]["detection_month"] - r[meth]["detection_month"] for r in misses])
        s[f"lead_{meth}_vs_straight_line"] = dict(
            median=float(np.median(lead)) if len(lead) else None,
            q25=float(np.percentile(lead, 25)) if len(lead) else None,
            q75=float(np.percentile(lead, 75)) if len(lead) else None,
            mean=float(np.mean(lead)) if len(lead) else None)
    ml_lead = s["lead_ml_vs_straight_line"]["median"]
    s["h2_met"] = bool(ml_lead is not None and ml_lead >= 2
                       and s["ml"]["false_alarm_rate"] <= s["straight_line"]["false_alarm_rate"])
    return s


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=200)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "ergebnisse")
    a = ap.parse_args(argv)
    drivers = load_drivers()
    base = main_scenario()
    md = build_master_data(GeneratorConfig(profile="dev"), drivers, base.component_price_change_plan)
    plan = plan_series(md, drivers, base, a.scale)
    results = []
    for i in range(a.scenarios):
        results.append(run_scenario(md, drivers, random_scenario(i), plan, a.scale, seed=1000 + i))
        if (i + 1) % 25 == 0:
            print(f"{i + 1}/{a.scenarios} scenarios")
    summary = summarise(results)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "q2_backtest_summary.json").write_text(json.dumps(summary, indent=2))
    rows = [dict(scenario=r["scenario"], miss=r["miss"], actual_vs_target=r["actual_vs_target"],
                 **{f"{m}_detection": r[m]["detection_month"] for m in METHODS},
                 **{f"{m}_false_alarm": r[m]["false_alarm"] for m in METHODS}) for r in results]
    pd.DataFrame(rows).to_csv(a.out / "q2_backtest_scenarios.csv", index=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
