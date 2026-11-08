"""Forecast methods: no look-ahead (results must not change when future actuals change)."""

import numpy as np
import pytest

from planwerk.forecast.methods import METHODS
from planwerk.forecast.rolling import YEAR, load_series


@pytest.fixture(scope="module")
def series(warehouse):
    from planwerk.warehouse import connect

    c = connect()
    act, plan = load_series(c, "GRUPPE")
    c.close()
    return act, plan


@pytest.mark.parametrize("method", list(METHODS))
@pytest.mark.parametrize("m", [3, 6, 9])
def test_no_leakage(series, method, m):
    act, plan = series
    base = METHODS[method](act, plan, YEAR, m)
    noisy = act.copy()
    future = noisy["PERIOD"] > f"{YEAR}-{m:02d}"
    rng = np.random.default_rng(1)
    for col in ("REVENUE", "DB1", "FIX_DB2", "DB2", "ORDER_INTAKE"):
        noisy.loc[future, col] = noisy.loc[future, col] * rng.uniform(0.2, 3.0, future.sum())
    assert METHODS[method](noisy, plan, YEAR, m) == pytest.approx(base, rel=1e-12)


def test_forecast_is_finite_and_plausible(series):
    act, plan = series
    target = plan[plan["PERIOD"].str[:4] == str(YEAR)]["DB2"].sum()
    for fn in METHODS.values():
        fc = fn(act, plan, YEAR, 6)
        assert np.isfinite(fc) and 0.5 * target < fc < 1.5 * target
