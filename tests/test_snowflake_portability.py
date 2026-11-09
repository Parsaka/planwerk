"""Snowflake path without a Snowflake account: loader statements, the DuckDB/Snowflake comparison
logic, and SQL that behaves differently on the two engines."""

import duckdb
import pytest

from planwerk.generator.config import REPO_ROOT
from planwerk.load import snowflake, snowflake_compare


def test_loader_creates_upper_case_columns_for_every_file(ci_data, capsys):
    out, _ = ci_data
    snowflake.main(["--raw", str(out), "--dry-run"])
    stmts = [s for s in capsys.readouterr().out.splitlines() if s]
    creates = [s for s in stmts if s.startswith("create or replace table")]
    assert len(creates) == len(list(out.glob("*.parquet"))) == 27
    # drivers.parquet has lower-case column names; without upper-casing Snowflake creates quoted
    # lower-case columns that dbt's unquoted identifiers cannot find (seen in the first real run)
    assert all("upper(column_name)" in s for s in creates)
    assert any(s.startswith("create or replace table S4_RAW.DRIVERS ") for s in creates)
    assert sum(s.startswith("copy into S4_RAW.") for s in stmts) == len(creates)


def test_compare_same_warehouse_is_equal(warehouse):
    a = duckdb.connect(str(warehouse), read_only=True)
    res = snowflake_compare.compare(snowflake_compare.cursor_runner(a.execute),
                                    snowflake_compare.cursor_runner(a.execute))
    a.close()
    assert res["all_equal"] and res["differences"] == 0
    assert res["checks"] == sum(len(m) + 1 for m in snowflake_compare.CHECKS.values())
    assert all(r["duckdb"] != 0 for r in res["rows"] if r["measure"] == "row_count")


def test_compare_detects_a_changed_figure_and_a_missing_row(warehouse):
    a = duckdb.connect(str(warehouse), read_only=True)
    ref = snowflake_compare.cursor_runner(a.execute)

    def tampered(sql: str) -> dict:
        row = ref(sql)
        if "mart_kpi_monthly" in sql:
            row["actual_eur"] += 2.0   # more than the 1 EUR tolerance
            row["row_count"] -= 1
        if "fct_journal_line" in sql:
            row["amount_eur"] += 0.4   # floating-point noise, within tolerance
        return row

    res = snowflake_compare.compare(ref, tampered)
    a.close()
    bad = {(r["relation"], r["measure"]) for r in res["rows"] if not r["equal"]}
    assert bad == {("controlling.mart_kpi_monthly", "actual_eur"), ("controlling.mart_kpi_monthly", "row_count")}
    assert not res["all_equal"]


def test_compare_reads_upper_case_column_names():
    class Cursor:
        description = [("ROW_COUNT",), ("AMOUNT_EUR",)]

        def fetchone(self):
            return (3, None)

    assert snowflake_compare.cursor_runner(lambda _sql: Cursor())("select 1") == {"row_count": 3.0, "amount_eur": 0.0}


def test_fiscal_quarter_is_q1_to_q4(wcon):
    rows = wcon.execute("select fiscal_month, fiscal_quarter from core.dim_period group by all").fetchall()
    assert {q for _, q in rows} == {"Q1", "Q2", "Q3", "Q4"}
    assert all(q == f"Q{(m - 1) // 3 + 1}" for m, q in rows)


@pytest.mark.parametrize("path", sorted((REPO_ROOT / "dbt" / "models").rglob("*.sql")), ids=lambda p: p.stem)
def test_models_avoid_engine_specific_sql(path):
    """Functions that exist on DuckDB only must go through a dispatched macro (macros/periods.sql)."""
    sql = path.read_text(encoding="utf-8").lower()
    for token in ("strftime(", "getvariable(", "read_parquet(", "::", "epoch(", " // "):
        assert token not in sql, f"{path.name}: {token} is DuckDB-only"


def test_policy_protected_mart_is_compared_as_a_named_user():
    sql = snowflake_compare.statement("controlling.mart_cost_variance", ["variance_cc_eur"])
    wrapped = snowflake_compare.snowflake_statement("controlling.mart_cost_variance", sql)
    assert wrapped == f"execute using policy_context(current_user => 'CONTROLLER') as {sql}"
    plain = snowflake_compare.statement("controlling.mart_kpi_monthly", ["actual_eur"])
    assert snowflake_compare.snowflake_statement("controlling.mart_kpi_monthly", plain) == plain
    seen = []
    snowflake_compare.compare(lambda q: {"row_count": 1.0, "variance_cc_eur": 2.0},
                              lambda q: seen.append(q) or {"row_count": 1.0, "variance_cc_eur": 2.0},
                              checks={"controlling.mart_cost_variance": ["variance_cc_eur"]},
                              candidate_sql=snowflake_compare.snowflake_statement)
    assert seen == [wrapped]
