"""Exploratory follow-up to Q2 (not part of the pre-registered criteria in ADR-0001).

    python -m planwerk.forecast.q2_matched [--scenarios 400] [--budget 0.05]

The pre-registered rule flags a year when a forecast falls below 98 % of the target, for every
method alike. Straight-line extrapolation is biased low early in the year (seasonality), so with
that rule it raises false alarms in healthy years, and the same bias makes it flag true misses
early. Its early detections and its false alarms are two sides of one property.

This script asks the question a steering committee would ask instead: *if every method is allowed
the same false-alarm rate, which one warns first?*

Protocol, fixed before the evaluation scenarios were generated:

* calibration set: scenarios 0-199 (the scenarios of the pre-registered backtest);
  evaluation set: scenarios 200-399 (never used before);
* per method, the flag threshold is the highest value on a grid from 90 % to 100 % of the target
  (steps of 0.5 points) whose false-alarm rate on the calibration set stays within the budget
  (default 5 %);
* on the evaluation set, with those thresholds: false-alarm rate, detection month and the paired
  lead over straight-line, all computed exactly as in :mod:`planwerk.forecast.evaluation`;
* the pre-registered rule (98 % for all) is repeated on the evaluation set as a replication.

It never changes the verdict on H2, which is fixed by the pre-registered backtest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from planwerk.forecast.backtest import plan_series, run_scenario
from planwerk.forecast.evaluation import MISS_THRESHOLD, detection_month, false_alarm
from planwerk.forecast.methods import METHODS
from planwerk.generator.config import REPO_ROOT, GeneratorConfig
from planwerk.generator.drivers import load_drivers
from planwerk.generator.masterdata import build_master_data
from planwerk.generator.scenario import main_scenario, random_scenario

CACHE = REPO_ROOT / "data" / "explore" / "q2_forecasts.json"
OUT = REPO_ROOT / "docs" / "ergebnisse" / "q2_matched_false_alarm.json"
GRID = [round(0.90 + 0.005 * k, 3) for k in range(21)]  # 0.900 ... 1.000
CALIBRATION = range(0, 200)


def simulate(n: int, cache: Path = CACHE) -> list[dict]:
    """Forecast paths (12 origins x 3 methods) per scenario; cached because 400 scenarios take
    about an hour. Scenario i uses the same definition and seed as the pre-registered backtest."""
    done = json.loads(cache.read_text()) if cache.exists() else []
    if len(done) >= n:
        return done[:n]
    drivers = load_drivers()
    base = main_scenario()
    md = build_master_data(GeneratorConfig(profile="dev"), drivers, base.component_price_change_plan)
    plan = plan_series(md, drivers, base, 1.0)
    cache.parent.mkdir(parents=True, exist_ok=True)
    for i in range(len(done), n):
        r = run_scenario(md, drivers, random_scenario(i), plan, 1.0, seed=1000 + i)
        done.append(dict(index=i, target=r["target"], actual=r["actual"], miss=bool(r["miss"]),
                         forecasts={m: r[m]["forecasts"] for m in METHODS}))
        if (i + 1) % 25 == 0:
            cache.write_text(json.dumps(done))
            print(f"{i + 1}/{n} scenarios", flush=True)
    cache.write_text(json.dumps(done))
    return done


def flags(forecasts: list[float], target: float, threshold: float) -> list[bool]:
    return [f < threshold * target for f in forecasts]


def false_alarm_rate(rows: list[dict], method: str, threshold: float) -> float:
    ok = [r for r in rows if not r["miss"]]
    return float(np.mean([false_alarm(flags(r["forecasts"][method], r["target"], threshold)) for r in ok]))


def calibrate(rows: list[dict], budget: float) -> dict[str, float]:
    """Highest threshold per method whose false-alarm rate on ``rows`` stays within the budget."""
    out = {}
    for m in METHODS:
        fitting = [t for t in GRID if false_alarm_rate(rows, m, t) <= budget]
        out[m] = max(fitting) if fitting else min(GRID)
    return out


def evaluate(rows: list[dict], thresholds: dict[str, float]) -> dict:
    misses = [r for r in rows if r["miss"]]
    det = {m: np.array([detection_month(flags(r["forecasts"][m], r["target"], thresholds[m])) for r in misses])
           for m in METHODS}
    res = dict(n_scenarios=len(rows), n_miss=len(misses), thresholds=thresholds)
    for m in METHODS:
        res[m] = dict(false_alarm_rate=round(false_alarm_rate(rows, m, thresholds[m]), 4),
                      median_detection_month=float(np.median(det[m])),
                      mean_detection_month=round(float(np.mean(det[m])), 2),
                      detected_share=round(float(np.mean(det[m] <= 12)), 4))
    for m in ("seasonal_naive", "ml"):
        lead = det["straight_line"] - det[m]
        res[f"lead_{m}_vs_straight_line"] = dict(
            median=float(np.median(lead)), q25=float(np.percentile(lead, 25)), q75=float(np.percentile(lead, 75)),
            mean=round(float(np.mean(lead)), 2), share_earlier=round(float(np.mean(lead > 0)), 4),
            share_later=round(float(np.mean(lead < 0)), 4))
    return res


def analyse(rows: list[dict], budget: float) -> dict:
    cal = [r for r in rows if r["index"] in CALIBRATION]
    ev = [r for r in rows if r["index"] not in CALIBRATION]
    same = {m: MISS_THRESHOLD for m in METHODS}
    matched = calibrate(cal, budget)
    return dict(
        note="Exploratory, not pre-registered. The H2 verdict stays as in q2_backtest_summary.json.",
        false_alarm_budget=budget,
        calibration_set=dict(scenarios="0-199", **evaluate(cal, matched)),
        evaluation_set_pre_registered_rule=dict(scenarios="200-399", **evaluate(ev, same)) if ev else None,
        evaluation_set_matched_false_alarm=dict(scenarios="200-399", **evaluate(ev, matched)) if ev else None)


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=400)
    ap.add_argument("--budget", type=float, default=0.05, help="false-alarm rate every method may use")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    res = analyse(simulate(a.scenarios), a.budget)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=2))
    for key in ("evaluation_set_pre_registered_rule", "evaluation_set_matched_false_alarm"):
        r = res[key]
        if not r:
            continue
        print(f"{key}: {r['n_miss']} misses of {r['n_scenarios']}")
        for m in METHODS:
            print(f"  {m:<15} threshold {r['thresholds'][m]:.3f}  false alarms {r[m]['false_alarm_rate']:.1%}  "
                  f"median detection month {r[m]['median_detection_month']:.0f}")
        lead = r["lead_ml_vs_straight_line"]
        print(f"  lead ML over straight-line: median {lead['median']:.0f}, mean {lead['mean']:+.2f}")
    return res


if __name__ == "__main__":
    main()
