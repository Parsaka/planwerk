"""Rolling forecast 3+9, 6+6 and 9+3 for the main (generated) scenario, from the warehouse.

Writes forecast.rolling_forecast (one row per version, method, scope) and
forecast.rolling_forecast_monthly (ML monthly path) and prints the comparison with the budget.
"""

from __future__ import annotations

import pandas as pd

from planwerk.forecast.evaluation import MISS_THRESHOLD
from planwerk.forecast.methods import METHODS, MLForecaster
from planwerk.warehouse import connect

YEAR = 2025
VERSIONS = {"FC3_9": 3, "FC6_6": 6, "FC9_3": 9}


def load_series(con, scope: str = "GRUPPE") -> tuple[pd.DataFrame, pd.DataFrame]:
    flt = "" if scope == "GRUPPE" else f"and company_code = '{scope}'"
    q = f"""
        select s.period, s.version,
               sum(s.revenue_eur) as revenue, sum(s.db1_eur) as db1,
               sum(s.fix_db2_eur) as fix_db2, sum(s.db2_eur) as db2
        from controlling.mart_db_statement_monthly s
        where 1 = 1 {flt}
        group by all order by 1"""
    st = con.execute(q).df()
    oi = con.execute(f"""select period, sum(order_intake_eur) as order_intake
                         from controlling.mart_order_intake_monthly where 1 = 1 {flt} group by 1""").df()
    act = st[st["version"] == "IST"].merge(oi, on="period", how="left")
    plan = st[st["version"] == "PLAN"].copy()
    ren = {"period": "PERIOD", "revenue": "REVENUE", "db1": "DB1", "fix_db2": "FIX_DB2", "db2": "DB2",
           "order_intake": "ORDER_INTAKE"}
    act = act.rename(columns=ren).drop(columns="version")
    plan = plan.rename(columns=ren).drop(columns="version")
    plan["ORDER_INTAKE"] = plan["REVENUE"]
    return act, plan


def run(con, scope: str = "GRUPPE") -> tuple[pd.DataFrame, pd.DataFrame]:
    act, plan = load_series(con, scope)
    target = float(plan[plan["PERIOD"].str[:4] == str(YEAR)]["DB2"].sum())
    actual = float(act[act["PERIOD"].str[:4] == str(YEAR)]["DB2"].sum())
    rows, monthly = [], []
    for version, m in VERSIONS.items():
        for meth, fn in METHODS.items():
            fc = fn(act, plan, YEAR, m)
            rows.append(dict(version=version, method=meth, scope=scope, fiscal_year=YEAR, known_months=m,
                             forecast_db2_eur=fc, plan_db2_eur=target, actual_db2_eur=actual,
                             flag_target_miss=fc < MISS_THRESHOLD * target))
        # monthly path of the ML forecast for the version (actuals + forecast months)
        f = MLForecaster()
        s = act.sort_values("PERIOD").reset_index(drop=True)
        p = plan.set_index("PERIOD")
        s["PLAN_REVENUE"] = s["PERIOD"].map(p["REVENUE"])
        s["PLAN_DB1"] = s["PERIOD"].map(p["DB1"])
        idx = {q: i for i, q in enumerate(s["PERIOD"])}
        o = idx[f"{YEAR}-{m:02d}"]
        X, y = f._training_set(s, o)
        from sklearn.ensemble import GradientBoostingRegressor
        model = GradientBoostingRegressor(n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.8,
                                          random_state=0).fit(X, y)
        from planwerk.forecast.methods import _features
        for k in range(1, 13):
            per = f"{YEAR}-{k:02d}"
            t = idx[per]
            if k <= m:
                val, kind = float(s.loc[t, "DB1"]), "IST"
            else:
                val = float(s.loc[t, "PLAN_DB1"] * (1 + model.predict(pd.DataFrame([_features(s, o, t)]))[0]))
                kind = "FC"
            monthly.append(dict(version=version, scope=scope, period=per, kind=kind, db1_eur=val,
                                plan_db1_eur=float(p.loc[per, "DB1"])))
    return pd.DataFrame(rows), pd.DataFrame(monthly)


def main() -> None:
    con = connect(read_only=False)
    frames, months = [], []
    for scope in ("GRUPPE", "1000", "2000", "3000"):
        r, mth = run(con, scope)
        frames.append(r)
        months.append(mth)
    res, mon = pd.concat(frames), pd.concat(months)
    con.execute("create schema if not exists forecast")
    con.register("r", res)
    con.register("m", mon)
    con.execute("create or replace table forecast.rolling_forecast as select * from r")
    con.execute("create or replace table forecast.rolling_forecast_monthly as select * from m")
    g = res[res["scope"] == "GRUPPE"].copy()
    g["vs_plan"] = g["forecast_db2_eur"] / g["plan_db2_eur"] - 1
    print(g[["version", "method", "forecast_db2_eur", "plan_db2_eur", "actual_db2_eur", "vs_plan",
             "flag_target_miss"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
