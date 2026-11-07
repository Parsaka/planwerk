"""Working-day calendar (simplified: weekends and nationwide fixed holidays)."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

_FIXED_HOLIDAYS = {"01-01", "05-01", "10-03", "12-24", "12-25", "12-26", "12-31"}


@lru_cache(maxsize=128)
def business_days(period: str) -> np.ndarray:
    """All working days of a period ('YYYY-MM') as numpy datetime64[D]."""
    days = pd.date_range(f"{period}-01", periods=pd.Period(period, freq="M").days_in_month, freq="D")
    keep = [d for d in days if d.weekday() < 5 and d.strftime("%m-%d") not in _FIXED_HOLIDAYS]
    return np.array(keep, dtype="datetime64[D]")


def random_business_days(periods: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """One random working day per entry of ``periods`` (array of 'YYYY-MM')."""
    out = np.empty(len(periods), dtype="datetime64[D]")
    uniq, inv = np.unique(periods, return_inverse=True)
    u = rng.random(len(periods))
    for i, p in enumerate(uniq):
        bd = business_days(str(p))
        mask = inv == i
        out[mask] = bd[(u[mask] * len(bd)).astype(int)]
    return out


def last_business_day(period: str) -> np.datetime64:
    return business_days(period)[-1]


def first_business_day(period: str) -> np.datetime64:
    return business_days(period)[0]


def to_period(dates: np.ndarray) -> np.ndarray:
    return np.datetime_as_string(dates.astype("datetime64[M]"), unit="M")
