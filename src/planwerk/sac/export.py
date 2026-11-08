"""Exports the SAP Analytics Cloud (SAC) planning model NW_CONTROLLING as import files.

    python -m planwerk.sac.export [--out sac/import]

Files (CSV, UTF-8, ';' separated, '.' decimals as SAC's file import expects):
  dim_*.csv           master data with hierarchies (parent ids) for the public dimensions
  fact_ist_plan.csv   Actual and Budget 2023-2025 per month, account, entity, product group,
                      cost centre (EUR and local currency, quantity)
  driver_basis_2026.csv  units, net price and standard cost per entity x product group x month of
                      2025 (actual), the starting point of the driver-based plan 2026
The model design and the data actions are documented in sac/README.md.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from planwerk.generator.config import REPO_ROOT
from planwerk.warehouse import connect

ACCOUNT_TREE = [  # id, description, parent, account type (SAC: INC income, EXP expense, NFIN non-financial)
    ("BE", "Betriebsergebnis", "", "INC"),
    ("DB3", "Deckungsbeitrag III", "BE", "INC"), ("FIX_UNT", "Unternehmensfixkosten", "BE", "EXP"),
    ("DB2", "Deckungsbeitrag II", "DB3", "INC"), ("FIX_DB3", "Bereichsfixkosten", "DB3", "EXP"),
    ("DB1", "Deckungsbeitrag I", "DB2", "INC"), ("FIX_DB2", "Fixkosten Produktgruppen/Fertigung", "DB2", "EXP"),
    ("NETTOUMSATZ", "Nettoumsatz", "DB1", "INC"), ("VAR_KOSTEN", "Variable Kosten", "DB1", "EXP"),
    ("UMSATZ", "Umsatzerlöse", "NETTOUMSATZ", "INC"), ("ERLOESSCHM", "Erlösschmälerungen", "NETTOUMSATZ", "EXP"),
    ("FIX_COSTS", "Primäre Fixkosten (Kostenstellen)", "", "EXP"),
    ("QTY", "Absatzmenge", "", "NFIN"), ("PRICE", "Nettopreis je Einheit", "", "NFIN"),
    ("STDCOST", "Standardkosten je Einheit", "", "NFIN"),
]


def dims(con) -> dict[str, pd.DataFrame]:
    acc = con.execute("""select gl_account, gl_account_text, cm_block from core.dim_gl_account
                         where not is_balance_sheet and cm_block = 'FIX' order by gl_account""").df()
    nodes = pd.DataFrame(ACCOUNT_TREE, columns=["ID", "Description", "ParentId", "AccType"])
    # CO leaves for the variable part (cost of sales at product-group level, as in the DB statement)
    leaves = [("ERL_PROD", "Umsatzerlöse Produkte und Service (CO)", "UMSATZ", "INC"),
              ("ERL_SKONTO", "Erlösschmälerungen Skonti (CO)", "ERLOESSCHM", "EXP"),
              ("VAR_MAT", "Variable Herstellkosten des Umsatzes (CO)", "VAR_KOSTEN", "EXP")]
    # primary fixed-cost accounts; their DB level comes from the cost centre's CM level, so in SAC
    # they hang under FIX_COSTS and the DB II/III/BE split is a calculated account per cost-centre node
    for r in acc[acc["cm_block"] == "FIX"].itertuples():
        leaves.append((r.gl_account, r.gl_account_text, "FIX_COSTS", "EXP"))
    account = pd.concat([nodes, pd.DataFrame(leaves, columns=nodes.columns)], ignore_index=True)
    entity = con.execute("""select company_code as ID, company_name as Description, 'GRUPPE' as ParentId,
                                   local_currency as Currency from core.dim_company_code order by 1""").df()
    entity = pd.concat([pd.DataFrame([dict(ID="GRUPPE", Description="Nordwerk-Gruppe (konsolidiert)", ParentId="",
                                           Currency="EUR")]), entity], ignore_index=True)
    pg = con.execute("""select distinct material_group as ID, material_group_text as Description, 'ALL_PG' as ParentId
                        from core.dim_material where material_type in ('FERT', 'HAWA', 'DIEN') order by 1""").df()
    pg = pd.concat([pd.DataFrame([dict(ID="ALL_PG", Description="Alle Produktgruppen", ParentId=""),
                                  dict(ID="#", Description="ohne Produktgruppe", ParentId="ALL_PG")]), pg])
    cc = con.execute("""select cost_centre as ID, cost_centre_name as Description, 'CM_' || CM_LEVEL as ParentId,
                               company_code as Entity, responsible as Responsible
                        from core.dim_cost_centre where is_current order by 1""").df()
    cc_nodes = pd.DataFrame([dict(ID="ALL_CC", Description="Alle Kostenstellen", ParentId=""),
                             dict(ID="#", Description="ohne Kostenstelle", ParentId="ALL_CC")]
                            + [dict(ID=f"CM_{k}", Description=t, ParentId="ALL_CC") for k, t in
                               [("DB2", "Fertigung und Material"), ("DB3", "Vertrieb, Service, Logistik"),
                                ("UNT", "Verwaltung und Unternehmensleitung"), ("HILF", "Hilfskostenstellen")]])
    version = pd.DataFrame([("public.Actual", "Ist", "Actual"), ("public.Budget2023", "Budget 2023", "Budget"),
                            ("public.Budget2024", "Budget 2024", "Budget"), ("public.Budget2025", "Budget 2025", "Budget"),
                            ("public.FC3_9_2025", "Forecast 3+9 2025", "Forecast"),
                            ("public.FC6_6_2025", "Forecast 6+6 2025", "Forecast"),
                            ("public.FC9_3_2025", "Forecast 9+3 2025", "Forecast"),
                            ("public.Budget2026", "Budget 2026 (in Planung)", "Budget")],
                           columns=["ID", "Description", "Category"])
    return dict(dim_account=account, dim_entity=entity, dim_productgroup=pg,
                dim_costcenter=pd.concat([cc_nodes, cc], ignore_index=True), dim_version=version)


def facts(con) -> pd.DataFrame:
    """Cost-accounting (CO) view, consistent with the DB statement: revenue and variable cost of sales
    per product group from the contribution-margin mart, cash discounts, and primary fixed costs per
    cost centre and account. Signs follow SAC account types (INC and EXP both positive)."""
    q = """
    with ver as (
        select 'IST' as v, 'public.Actual' as Version union all
        select 'PLAN', 'public.Budget'
    ),
    cm as (
        select version, period, company_code, material_group, sum(revenue_eur) as rev, sum(var_cost_eur) as var,
               sum(quantity) as qty
        from controlling.mart_contribution_margin_monthly group by all
    ),
    rows_ as (
        select version, period, 'ERL_PROD' as Account, company_code, material_group, '#' as cc, rev as amt, qty
        from cm
        union all
        select version, period, 'VAR_MAT', company_code, material_group, '#', var, 0 from cm
        union all
        select 'IST', j.period, 'ERL_SKONTO', j.company_code, '#', '#', sum(j.amount_eur), 0
        from core.fct_journal_line j where j.gl_account = '409000' group by all
        union all
        select 'PLAN', p.period, 'ERL_SKONTO', p.company_code, '#', '#', sum(p.amount_eur), 0
        from core.fct_plan_line p where p.gl_account = '409000' group by all
        union all
        select 'IST', j.period, j.gl_account, j.company_code, '#', coalesce(nullif(j.cost_centre, ''), '#'),
               sum(j.amount_eur), 0
        from core.fct_journal_line j join core.dim_gl_account a using (gl_account)
        where a.cm_block = 'FIX' group by all
        union all
        select 'PLAN', p.period, p.gl_account, p.company_code, '#', coalesce(nullif(p.cost_centre, ''), '#'),
               sum(p.amount_eur), 0
        from core.fct_plan_line p join core.dim_gl_account a using (gl_account)
        where a.cm_block = 'FIX' group by all
    )
    select case when r.version = 'IST' then 'public.Actual'
                else 'public.Budget' || left(r.period, 4) end as Version,
           replace(r.period, '-', '') as Date, r.Account, r.company_code as Entity,
           coalesce(nullif(r.material_group, ''), '#') as ProductGroup, r.cc as CostCenter,
           round(sum(r.amt), 2) as Amount_EUR, round(sum(r.qty), 3) as Quantity
    from rows_ r group by all having abs(sum(r.amt)) >= 0.005 or abs(sum(r.qty)) > 0
    order by 1, 2, 4, 3"""
    return con.execute(q).df()


def driver_basis(con) -> pd.DataFrame:
    return con.execute("""
        select replace(period, '-', '') as Date, company_code as Entity, material_group as ProductGroup,
               sum(quantity) as Units,
               sum(revenue_eur) / nullif(sum(quantity), 0) as Price_EUR,
               sum(var_cost_eur) / nullif(sum(quantity), 0) as StdCost_EUR
        from controlling.mart_contribution_margin_monthly
        where version = 'IST' and fiscal_year = 2025 and material_group <> 'PG50'
        group by all order by 1, 2, 3""").df().round(4)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "sac" / "import")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    con = connect()
    files = {**dims(con), "fact_ist_plan": facts(con), "driver_basis_2026": driver_basis(con)}
    for name, df in files.items():
        df.to_csv(a.out / f"{name}.csv", sep=";", index=False, encoding="utf-8")
        print(f"{name}: {len(df):,} rows")


if __name__ == "__main__":
    main()
