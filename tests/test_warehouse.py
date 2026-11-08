"""Warehouse logic on the CI profile: dbt build passes (all schema, contract and singular tests)
and the controlling identities hold."""

import pytest


def test_kpi_group_is_sum_of_company_codes(wcon):
    d = wcon.execute("""
        select g.period, g.kpi, g.actual_eur - sum(c.actual_eur) as diff
        from controlling.mart_kpi_monthly g
        join controlling.mart_kpi_monthly c on c.period = g.period and c.kpi = g.kpi and c.scope <> 'GRUPPE'
        where g.scope = 'GRUPPE' group by g.period, g.kpi, g.actual_eur""").df()
    assert d["diff"].abs().max() < 0.01


def test_bridge_closes_for_every_scope_and_month(wcon):
    d = wcon.execute("""select max(abs(plan_db2_eur + volume_effect + mix_effect + price_effect + var_cost_effect
                               + sales_deduction_effect + fixed_cost_db2_effect + fx_effect_db2 - actual_db2_eur))
                        from controlling.mart_db2_bridge""").fetchone()[0]
    assert d < 0.01


def test_db_scheme_identities(wcon):
    d = wcon.execute("""select max(abs(net_revenue_eur - var_cost_eur - db1_eur)) a,
                               max(abs(db1_eur - fix_db2_eur - db2_eur)) b,
                               max(abs(db2_eur - fix_db3_eur - db3_eur)) c
                        from controlling.mart_db_statement_monthly""").fetchone()
    assert max(d) < 0.01


def test_row_level_security_restricts_cost_centre_owner(warehouse):
    import duckdb

    c = duckdb.connect(str(warehouse), read_only=True)
    c.execute("set variable planwerk_user = 'leitung_instandhaltung'")
    ccs = {r[0] for r in c.execute("select distinct kostenstelle from semantic.sem_kostenstellen").fetchall()}
    assert ccs == {"1410"}
    c.execute("set variable planwerk_user = 'controller'")
    assert len({r[0] for r in c.execute("select distinct kostenstelle from semantic.sem_kostenstellen").fetchall()}) > 20
    c.execute("set variable planwerk_user = 'niemand'")
    assert c.execute("select count(*) from semantic.sem_kostenarten").fetchone()[0] == 0


@pytest.mark.parametrize("table", ["forecast.rolling_forecast", "forecast.liquidity_13w", "semantic.sem_prognose"])
def test_downstream_tables_exist(wcon, table):
    assert wcon.execute(f"select count(*) from {table}").fetchone()[0] > 0


def test_liquidity_has_13_weeks_per_company(wcon):
    n = wcon.execute("select company_code, count(distinct week) from forecast.liquidity_13w group by 1").fetchall()
    assert {c for c, _ in n} == {"1000", "2000", "3000"}
    assert all(k == 13 for _, k in n)
