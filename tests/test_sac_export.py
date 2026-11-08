"""SAC import files reconcile to the warehouse DB statement (DB I and total fixed costs per version/year)."""

import pandas as pd

from planwerk.sac import export


def test_sac_export_reconciles(warehouse, tmp_path):
    from planwerk.warehouse import connect

    export.main(["--out", str(tmp_path)])
    f = pd.read_csv(tmp_path / "fact_ist_plan.csv", sep=";", dtype={"Account": str, "Date": str})
    f["year"] = f["Date"].str[:4].astype(int)
    f["version"] = f["Version"].map(lambda v: "IST" if v == "public.Actual" else "PLAN")
    sign = {"ERL_PROD": 1.0, "ERL_SKONTO": -1.0, "VAR_MAT": -1.0}
    f["db1"] = f["Amount_EUR"] * f["Account"].map(sign).fillna(0.0)
    f["fix"] = f["Amount_EUR"].where(~f["Account"].isin(list(sign)), 0.0)
    got = f.groupby(["version", "year"])[["db1", "fix"]].sum()
    con = connect()
    exp = con.execute("""select version, fiscal_year as year, sum(db1_eur) as db1,
                                sum(fix_db2_eur + fix_db3_eur + fix_unt_eur + fix_unallocated_eur) as fix
                         from controlling.mart_db_statement_monthly group by 1, 2""").df().set_index(["version", "year"])
    diff = (got - exp.loc[got.index]).abs().max()
    assert diff["db1"] < 1.0 and diff["fix"] < 1.0, diff
    acc = pd.read_csv(tmp_path / "dim_account.csv", sep=";", dtype=str, keep_default_na=False)
    assert set(f["Account"]) <= set(acc["ID"])
    assert set(acc["ParentId"]) - {""} <= set(acc["ID"])
