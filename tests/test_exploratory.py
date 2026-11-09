"""Exploratory follow-ups to Q1 and Q2. They add measurements; they must never touch the
pre-registered criteria."""

import json

import duckdb
import pytest

from planwerk.controlling import q1_evaluation
from planwerk.forecast import q2_matched as Q
from planwerk.forecast.evaluation import MISS_THRESHOLD
from planwerk.forecast.methods import METHODS


def _row(index, miss, sl, ml, target=100.0):
    return dict(index=index, target=target, actual=(95.0 if miss else 101.0), miss=miss,
                forecasts=dict(straight_line=sl, seasonal_naive=ml, ml=ml))


# straight-line starts low in every year (seasonal bias) and recovers only in a healthy year
HEALTHY = [_row(i, False, [96.0] * 4 + [101.0] * 8, [101.0] * 12) for i in range(0, 20)]
MISSES = [_row(i, True, [96.0] * 12, [101.0] * 2 + [96.5] * 10) for i in range(20, 40)]
FRESH = [dict(r, index=r["index"] + 200) for r in HEALTHY + MISSES]


def test_pre_registered_rule_reproduces_the_bias_trade_off():
    r = Q.evaluate(HEALTHY + MISSES, {m: MISS_THRESHOLD for m in METHODS})
    assert r["straight_line"]["false_alarm_rate"] == 0.0  # the flag does not stay on until month 11
    assert r["straight_line"]["median_detection_month"] == 1 and r["ml"]["median_detection_month"] == 3
    assert r["lead_ml_vs_straight_line"]["median"] == -2


def test_false_alarm_is_a_flag_that_stays_on():
    stays = _row(0, False, [96.0] * 12, [101.0] * 12)
    assert Q.false_alarm_rate([stays], "straight_line", 0.98) == 1.0
    assert Q.false_alarm_rate([stays], "ml", 0.98) == 0.0


def test_calibration_picks_the_most_sensitive_threshold_within_the_budget():
    rows = [_row(i, False, [97.0] * 12, [99.2] * 12) for i in range(10)] + MISSES
    t = Q.calibrate(rows, budget=0.05)
    assert t["straight_line"] == 0.97   # 97.0 < 0.975 x 100 would flag every healthy year
    assert t["ml"] == 0.99
    assert Q.false_alarm_rate(rows, "straight_line", t["straight_line"]) <= 0.05
    assert Q.false_alarm_rate(rows, "straight_line", 0.975) == 1.0


def test_thresholds_come_from_the_calibration_set_only():
    res = Q.analyse(HEALTHY + MISSES + FRESH, budget=0.05)
    changed = [dict(r, forecasts={m: [0.0] * 12 for m in METHODS}) for r in FRESH]
    res2 = Q.analyse(HEALTHY + MISSES + changed, budget=0.05)
    assert res["calibration_set"]["thresholds"] == res2["calibration_set"]["thresholds"]
    assert res["evaluation_set_matched_false_alarm"]["thresholds"] == res["calibration_set"]["thresholds"]
    assert res["evaluation_set_pre_registered_rule"]["thresholds"] == {m: MISS_THRESHOLD for m in METHODS}
    assert "not pre-registered" in res["note"]


@pytest.fixture(scope="module")
def q1(warehouse, ci_data):
    out, _ = ci_data
    con = duckdb.connect(str(warehouse), read_only=True)
    res = q1_evaluation.evaluate(con, json.loads((out / "ground_truth.json").read_text()))
    con.close()
    return res


def test_volume_split_is_reported_next_to_the_criteria_not_inside_them(q1):
    split = q1["exploratory_volume_split"]
    assert "not pre-registered" in split["note"]
    names = [r["effect"] for r in q1["recovery"]]
    assert not any(n.startswith("customer_loss") for n in names)       # criterion 2 still judges the
    assert any(n.startswith("volume_level + customer_loss") for n in names)  # combined volume effect
    assert q1["criteria"]["c2_recovered_count"] == f"{sum(r['recovered'] for r in q1['recovery'])}/{len(names)}"
    assert q1["h1_met"] == (q1["criteria"]["c1_bridge_closes"] and q1["criteria"]["c2_effects_recovered"]
                            and q1["criteria"]["c3_met"])


def test_customer_loss_is_measured_at_customer_level(q1):
    (c,) = q1["exploratory_volume_split"]["customer_loss"]
    assert 0 < c["share_of_cell_before_loss"] < 1
    assert c["measured_eur"] == pytest.approx(c["actual_db1_eur"] - c["expected_db1_eur"], abs=0.02)
    assert c["measured_eur"] < 0 and c["injected_eur"] < 0     # the customer was lost: DB I is missing
    m = q1["exploratory_volume_split"]["market_volume"]
    assert m["measured_eur"] == pytest.approx(q1["bridge"]["volume_effect"] - c["measured_eur"], abs=0.02)
