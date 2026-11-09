"""Portability check (ADR-0003): the Snowflake build must give the same figures as the DuckDB build.

    python -m planwerk.load.snowflake_compare [--out docs/ergebnisse/snowflake_run.json]

Both warehouses are built from the same Parquet files by the same dbt project. For a fixed list
of core tables and controlling marts the row count and the sum of every measure are read from
both engines and compared. Sums of floating-point columns may differ in the last digits because
the engines add in a different order, so a measure counts as equal when it differs by at most
1 EUR or 1e-9 of its size, whichever is larger. Exit code 1 on any difference.

Credentials come only from the environment, as in :mod:`planwerk.load.snowflake`.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from planwerk.generator.config import REPO_ROOT

# relation -> measures. Counts and plain sums only, so the statements are valid on both engines.
CHECKS: dict[str, list[str]] = {
    "core.fct_journal_line": ["amount_lc", "amount_eur", "quantity"],
    "core.fct_sales_item": ["quantity", "revenue_eur", "var_cost_eur", "revenue_cc_eur"],
    "core.fct_order_intake": ["quantity", "net_value_eur"],
    "core.fct_plan_line": ["amount_lc", "amount_eur"],
    "core.fct_open_item": ["amount_eur"],
    "core.dim_cost_centre": ["headcount_reference"],
    "intermediate.int_bab_allocation": ["amount_eur", "amount_cc_eur"],
    "controlling.mart_db_statement_monthly": ["revenue_eur", "db1_eur", "db2_eur", "db3_eur",
                                              "fix_unallocated_eur"],
    "controlling.mart_cost_centre_monthly": ["primary_eur", "received_eur", "sent_eur", "total_eur"],
    "controlling.mart_cost_variance": ["plan_cc_eur", "actual_cc_eur", "variance_cc_eur"],
    "controlling.mart_pvm_cells": ["price_effect", "var_cost_effect", "db1_ist", "db1_plan"],
    "controlling.mart_db2_bridge": ["plan_db2_eur", "volume_effect", "mix_effect", "price_effect",
                                    "var_cost_effect", "fixed_cost_db2_effect", "fx_effect_db2",
                                    "actual_db2_eur", "residual_db2"],
    "controlling.mart_kpi_monthly": ["actual_eur", "plan_eur", "variance_eur"],
    "controlling.mart_gkv_pnl": ["amount_eur"],
    "controlling.mart_reconciliation_co_gkv": ["co_operating_result_eur", "gkv_operating_eur", "residual_eur"],
    "controlling.mart_order_intake_monthly": ["order_intake_eur", "revenue_eur"],
    "semantic.sem_kennzahlen_monat": ["ist_eur", "plan_eur"],
    "semantic.sem_abweichungsbruecke": ["plan_db2_eur", "ist_db2_eur"],
}

ABS_TOL_EUR = 1.0
REL_TOL = 1e-9

Runner = Callable[[str], dict[str, float]]


def statement(relation: str, measures: list[str]) -> str:
    sums = ", ".join(f"sum({m}) as {m}" for m in measures)
    return f"select count(*) as row_count, {sums} from {relation}"


def equal(a: float, b: float) -> bool:
    return abs(a - b) <= max(ABS_TOL_EUR, REL_TOL * max(abs(a), abs(b)))


def compare(reference: Runner, candidate: Runner, checks: dict[str, list[str]] | None = None) -> dict:
    """Run every check on both engines. ``reference`` is DuckDB, ``candidate`` is Snowflake."""
    rows = []
    for relation, measures in (checks or CHECKS).items():
        sql = statement(relation, measures)
        ref, cand = reference(sql), candidate(sql)
        for key in ["row_count", *measures]:
            a, b = ref[key], cand[key]
            same = a == b if key == "row_count" else equal(a, b)
            rows.append(dict(relation=relation, measure=key, duckdb=a, snowflake=b, difference=b - a,
                             equal=bool(same)))
    return dict(checks=len(rows), differences=sum(not r["equal"] for r in rows),
                all_equal=all(r["equal"] for r in rows), rows=rows)


def cursor_runner(execute) -> Runner:
    """Wrap a DB-API style ``execute`` that returns a cursor; keys are lower-cased (Snowflake
    reports unquoted column names in upper case)."""

    def run(sql: str) -> dict[str, float]:
        cur = execute(sql)
        cols = [d[0].lower() for d in cur.description]
        return {c: float(v or 0.0) for c, v in zip(cols, cur.fetchone(), strict=True)}

    return run


def dbt_summary(target_dir: Path) -> dict | None:
    """Pass/fail counts of the last dbt invocation, if its run_results.json is there."""
    p = target_dir / "run_results.json"
    if not p.exists():
        return None
    res = json.loads(p.read_text())
    counts: dict[str, int] = {}
    for r in res.get("results", []):
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return dict(dbt_version=res.get("metadata", {}).get("dbt_version"), statuses=counts,
                elapsed_seconds=round(res.get("elapsed_time", 0.0), 1))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "docs" / "ergebnisse" / "snowflake_run.json")
    ap.add_argument("--raw", type=Path, default=Path(os.environ.get("PLANWERK_RAW", REPO_ROOT / "data" / "raw")))
    ap.add_argument("--dbt-target", type=Path, default=REPO_ROOT / "dbt" / "target")
    a = ap.parse_args(argv)

    from planwerk.load.snowflake import DATABASE, _connect
    from planwerk.warehouse import connect

    duck = connect(read_only=True)
    os.environ.setdefault("SNOWFLAKE_ROLE", "PLANWERK_TRANSFORMER")
    snow = _connect()
    cur = snow.cursor()
    cur.execute(f"use database {DATABASE}")
    res = compare(cursor_runner(duck.execute), cursor_runner(cur.execute))
    version = cur.execute("select current_version(), current_region()").fetchone()
    snow.close()

    manifest = json.loads((a.raw / "manifest.json").read_text())
    out = dict(run_at=datetime.now(UTC).isoformat(timespec="seconds"), data="SIMULATED (Nordwerk GmbH)",
               profile=manifest.get("profile"), seed=manifest.get("seed"),
               snowflake=dict(version=version[0], region=version[1]), dbt=dbt_summary(a.dbt_target),
               tolerance=dict(absolute_eur=ABS_TOL_EUR, relative=REL_TOL), **res)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    for r in res["rows"]:
        if not r["equal"]:
            print(f"DIFFERENT {r['relation']}.{r['measure']}: duckdb {r['duckdb']:,.2f}  "
                  f"snowflake {r['snowflake']:,.2f}")
    print(f"{res['checks'] - res['differences']}/{res['checks']} figures equal on DuckDB and Snowflake")
    return 0 if res["all_equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
