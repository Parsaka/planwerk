"""Full-year forecast methods compared in ADR-0001 Q2.

All methods receive the same information set at forecast origin m (actuals of months 1..m of
the target year and the full prior history) and return a full-year DB II forecast.

* ``straight_line``: YTD DB II x 12 / m (the classic "Hochrechnung").
* ``seasonal_naive``: YTD plus the prior year's remaining months scaled by YTD / prior-year YTD.
* ``ml``: gradient-boosted model of the monthly DB I deviation from budget, driven by order
  intake versus budget revenue (leading indicator), recent DB I deviation, calendar month and
  forecast horizon;
  fixed costs for the remaining months = budget x YTD run-rate (actual / budget).
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

COLS = ["PERIOD", "ORDER_INTAKE", "REVENUE", "DB1", "FIX_DB2", "DB2"]


def _split(series: pd.DataFrame, year: int, m: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    s = series.sort_values("PERIOD").reset_index(drop=True)
    cut = f"{year}-{m:02d}"
    return s[s["PERIOD"] <= cut].copy(), s[(s["PERIOD"] > cut) & (s["PERIOD"].str[:4] == str(year))].copy()


def straight_line(series: pd.DataFrame, plan: pd.DataFrame, year: int, m: int) -> float:
    known, _ = _split(series, year, m)
    ytd = known[known["PERIOD"].str[:4] == str(year)]["DB2"].sum()
    return float(ytd * 12.0 / m)


def seasonal_naive(series: pd.DataFrame, plan: pd.DataFrame, year: int, m: int) -> float:
    s = series.set_index("PERIOD")["DB2"]
    ytd = sum(s[f"{year}-{k:02d}"] for k in range(1, m + 1))
    prev_ytd = sum(s[f"{year - 1}-{k:02d}"] for k in range(1, m + 1))
    rest_prev = sum(s[f"{year - 1}-{k:02d}"] for k in range(m + 1, 13))
    factor = ytd / prev_ytd if prev_ytd else 1.0
    return float(ytd + rest_prev * factor)


def _ratio(a: np.ndarray, b: np.ndarray, lo: int, hi: int) -> float:
    den = b[lo:hi + 1].sum()
    return float(a[lo:hi + 1].sum() / den - 1.0) if den else 0.0


def _features(s: pd.DataFrame, origin_idx: int, target_idx: int) -> dict:
    """Features known at the origin for a target month. Everything is expressed relative to the
    budget of the same months, so the model learns how deviations propagate, not levels."""
    oi, db1, prev, pdb1 = (s["ORDER_INTAKE"].to_numpy(), s["DB1"].to_numpy(), s["PLAN_REVENUE"].to_numpy(),
                           s["PLAN_DB1"].to_numpy())
    o = origin_idx
    return dict(
        horizon=target_idx - o,
        month=int(s["PERIOD"].iloc[target_idx][5:7]),
        oi_vs_plan_1=_ratio(oi, prev, o, o),
        oi_vs_plan_3=_ratio(oi, prev, o - 2, o),
        db1_vs_plan_1=_ratio(db1, pdb1, o, o),
        db1_vs_plan_3=_ratio(db1, pdb1, o - 2, o),
        db1_vs_plan_6=_ratio(db1, pdb1, max(o - 5, 0), o),
    )


class MLForecaster:
    """Monthly DB I model: target = DB1(t) / PLAN_DB1(t) - 1, trained on all origins before m."""

    def __init__(self, random_state: int = 0):
        self.random_state = random_state

    def _training_set(self, s: pd.DataFrame, last_known: int) -> tuple[pd.DataFrame, np.ndarray]:
        rows, y = [], []
        db1, pdb1 = s["DB1"].to_numpy(), s["PLAN_DB1"].to_numpy()
        for o in range(2, last_known):
            for t in range(o + 1, min(o + 11, last_known) + 1):
                if pdb1[t] == 0:
                    continue
                rows.append(_features(s, o, t))
                y.append(db1[t] / pdb1[t] - 1.0)
        return pd.DataFrame(rows), np.array(y)

    def forecast(self, series: pd.DataFrame, plan: pd.DataFrame, year: int, m: int) -> float:
        p = plan.set_index("PERIOD")
        s = series.sort_values("PERIOD").reset_index(drop=True)
        s["PLAN_REVENUE"] = s["PERIOD"].map(p["REVENUE"])
        s["PLAN_DB1"] = s["PERIOD"].map(p["DB1"])
        idx = {q: i for i, q in enumerate(s["PERIOD"])}
        o = idx[f"{year}-{m:02d}"]
        X, y = self._training_set(s, o)
        model = GradientBoostingRegressor(n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.8,
                                          random_state=self.random_state)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(X, y)
        rest = [idx[f"{year}-{k:02d}"] for k in range(m + 1, 13)]
        Xf = pd.DataFrame([_features(s, o, t) for t in rest])
        db1_rest = float((s["PLAN_DB1"].to_numpy()[rest] * (1.0 + model.predict(Xf))).sum())
        # fixed costs: remaining budget scaled by the YTD actual/budget run-rate
        ytd = s[(s["PERIOD"].str[:4] == str(year)) & (s["PERIOD"] <= f"{year}-{m:02d}")]
        plan_ytd_fix = sum(p.loc[f"{year}-{k:02d}", "FIX_DB2"] for k in range(1, m + 1))
        run_rate = ytd["FIX_DB2"].sum() / plan_ytd_fix if plan_ytd_fix else 1.0
        fix_rest = sum(p.loc[f"{year}-{k:02d}", "FIX_DB2"] for k in range(m + 1, 13)) * run_rate
        return float(ytd["DB2"].sum() + db1_rest - fix_rest)


def ml(series: pd.DataFrame, plan: pd.DataFrame, year: int, m: int) -> float:
    if m == 12:
        return float(series[series["PERIOD"].str[:4] == str(year)]["DB2"].sum())
    return MLForecaster().forecast(series, plan, year, m)


METHODS = {"straight_line": straight_line, "seasonal_naive": seasonal_naive, "ml": ml}
