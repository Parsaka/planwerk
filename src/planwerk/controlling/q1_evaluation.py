"""Q1 evaluation (ADR-0001): does the DB II bridge close, are the injected effects recovered, and
is the cost deviation assigned to named cost centres?

    python -m planwerk.controlling.q1_evaluation [--raw data/raw] [--out docs/ergebnisse/q1_evaluation.json]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from planwerk.generator.config import REPO_ROOT
from planwerk.warehouse import connect

YEAR = 2025


def tolerance(truth: float) -> float:
    return max(0.10 * abs(truth), 50_000.0)


def evaluate(con, truth: dict) -> dict:
    b = con.execute(f"""select * from controlling.mart_db2_bridge
                        where fiscal_year = {YEAR} and to_month = 12 and scope = 'GRUPPE'""").df().iloc[0]
    effects = ["volume_effect", "mix_effect", "price_effect", "var_cost_effect", "sales_deduction_effect",
               "fixed_cost_db2_effect", "fx_effect_db2"]
    gap = float(b["actual_db2_eur"] - b["plan_db2_eur"])
    closure = abs(sum(float(b[e]) for e in effects) - gap)
    pg10 = con.execute(f"""select sum(price_effect) from controlling.mart_pvm_cells
                           where fiscal_year = {YEAR} and to_month = 12 and material_group = 'PG10'""").fetchone()[0]
    gt = {e["effect"]: e for e in truth["effects"]}
    rows = []

    def add(name, measured, injected, note=""):
        ok = abs(measured - injected) <= tolerance(injected)
        rows.append(dict(effect=name, injected_eur=round(injected, 2), measured_eur=round(measured, 2),
                         difference_eur=round(measured - injected, 2), tolerance_eur=round(tolerance(injected), 2),
                         recovered=bool(ok), note=note))

    add("price_pg10", float(pg10), gt["price_pg10"]["impact_db2_eur"], "PVM price effect of PG10 (group)")
    if "demand_shift" in gt:
        add("demand_shift (mix)", float(b["mix_effect"]), gt["demand_shift"]["impact_db2_eur"], "group mix effect")
    vol_truth = sum(e["impact_db2_eur"] for e in truth["effects"] if e["category"] == "volume")
    add("volume_level + customer_loss (volume)", float(b["volume_effect"]), vol_truth,
        "group volume effect at plan prices; contains the random demand of the single realisation")
    for e in truth["effects"]:
        if e["category"] == "fixed_cost":
            cc, acc, per = e["scope"]["cost_centre"], e["scope"]["account"], e["scope"]["period"]
            m = int(per[5:7])
            v = con.execute(f"""select sum(case when to_month = {m} then variance_cc_eur else -variance_cc_eur end)
                                from controlling.mart_cost_variance
                                where fiscal_year = {YEAR} and cost_centre = '{cc}' and gl_account = '{acc}'
                                  and to_month in ({m}, {m - 1})""").fetchone()[0]
            add(e["effect"], float(v), e["impact_db2_eur"], f"cost centre {cc}, account {acc}, month {per}")
    cov = con.execute(f"""select sum(case when cost_centre is not null and cost_centre_name is not null
                                          then abs(variance_cc_eur) else 0 end) / sum(abs(variance_cc_eur))
                          from controlling.mart_cost_variance where fiscal_year = {YEAR} and to_month = 12""").fetchone()[0]
    revenue = con.execute(f"""select sum(revenue_eur) from controlling.mart_db_statement_monthly
                              where version = 'IST' and fiscal_year = {YEAR}""").fetchone()[0]
    realisation = dict(
        revenue_actual_eur=round(float(revenue), 2),
        revenue_expected_eur=round(truth["expected_actual"]["REVENUE"], 2),
        revenue_realisation_vs_expected=round(float(revenue) / truth["expected_actual"]["REVENUE"] - 1, 4),
        db2_actual_eur=round(float(b["actual_db2_eur"]), 2),
        db2_expected_eur=round(truth["expected_actual"]["DB2"], 2),
    )
    crit = dict(
        c1_bridge_closes=bool(closure < 0.01),
        c2_effects_recovered=all(r["recovered"] for r in rows),
        c2_recovered_count=f"{sum(r['recovered'] for r in rows)}/{len(rows)}",
        c3_cost_centre_coverage=round(float(cov), 4), c3_met=bool(cov >= 0.90),
    )
    return dict(year=YEAR, plan_db2_eur=round(float(b["plan_db2_eur"]), 2),
                actual_db2_eur=round(float(b["actual_db2_eur"]), 2), gap_db2_eur=round(gap, 2),
                bridge={e: round(float(b[e]), 2) for e in effects}, closure_abs_eur=closure, recovery=rows,
                realisation=realisation, criteria=crit,
                h1_met=bool(crit["c1_bridge_closes"] and crit["c2_effects_recovered"] and crit["c3_met"]))


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=Path(os.environ.get("PLANWERK_RAW", REPO_ROOT / "data" / "raw")))
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "ergebnisse" / "q1_evaluation.json")
    a = ap.parse_args(argv)
    truth = json.loads((a.raw / "ground_truth.json").read_text())
    res = evaluate(connect(), truth)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    for r in res["recovery"]:
        print(f"{r['effect']:<42} injected {r['injected_eur']:>14,.0f}  measured {r['measured_eur']:>14,.0f}  "
              f"{'OK' if r['recovered'] else 'MISSED'}")
    print("criteria:", res["criteria"], "H1 met:", res["h1_met"])
    return res


if __name__ == "__main__":
    main()
