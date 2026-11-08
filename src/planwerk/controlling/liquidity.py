"""13-week liquidity forecast (Liquiditätsvorschau) from open items and payment behaviour.

As-of date 31.12.2025; weeks start on Monday 05.01.2026 (week 1 also takes everything overdue).
All amounts in EUR (PLN translated at the last ECB monthly rate). Logic: Fachkonzept section 8.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from planwerk.generator.config import REPO_ROOT
from planwerk.warehouse import connect

AS_OF = pd.Timestamp("2025-12-31")
WEEK1 = pd.Timestamp("2026-01-05")
N_WEEKS = 13


def _week_index(dates: pd.Series) -> pd.Series:
    w = ((pd.to_datetime(dates) - WEEK1).dt.days // 7) + 1
    return w.clip(lower=1)


def build(con) -> pd.DataFrame:
    fx_last = con.execute("select eur_pln from staging.stg_ext__drivers order by period desc limit 1").fetchone()[0]
    rate = {"1000": 1.0, "2000": 1.0, "3000": fx_last}
    rows = []

    # 1) open receivables: due date + customer's historic delay
    ar = con.execute("""
        select o.company_code, o.customer, o.due_date, o.amount_lc, coalesce(b.avg_days_after_due, 0) as delay
        from core.fct_open_item o
        left join controlling.mart_payment_behaviour b on b.customer = o.customer and b.company_code = o.company_code
        where o.item_type = 'AR'""").df()
    ar["expected"] = pd.to_datetime(ar["due_date"]) + pd.to_timedelta(ar["delay"].clip(lower=-20).round(), unit="D")
    ar["week"] = _week_index(ar["expected"])
    ar["eur"] = ar["amount_lc"] / ar["company_code"].map(rate)
    rows.append(ar.assign(position="Einzahlungen offene Forderungen")[["company_code", "week", "position", "eur"]])

    # 2) open payables at due date (negative amounts on 330000 are liabilities -> outflow)
    ap = con.execute("""select company_code, due_date, amount_lc from core.fct_open_item where item_type = 'AP'""").df()
    ap["week"] = _week_index(ap["due_date"])
    ap["eur"] = ap["amount_lc"] / ap["company_code"].map(rate)  # negative = outflow
    rows.append(ap.assign(position="Auszahlungen offene Verbindlichkeiten")[["company_code", "week", "position", "eur"]])

    # 3) new business: revenue run-rate of the last 3 months (gross), collected after the
    #    company code's average days-to-pay; purchases at the material ratio, paid after 30 days
    rr = con.execute("""
        select company_code, avg(revenue_eur) as rev, avg(var_cost_eur) as var
        from controlling.mart_db_statement_monthly
        where version = 'IST' and period between '2025-10' and '2025-12' group by 1""").df()
    dso = con.execute("""select company_code, sum(avg_days_to_pay * paid_invoices) / sum(paid_invoices) as dso
                         from controlling.mart_payment_behaviour group by 1""").df()
    vat = {"1000": 0.19, "2000": 0.20, "3000": 0.23}
    rr = rr.merge(dso, on="company_code")
    days = pd.date_range("2026-01-01", WEEK1 + pd.Timedelta(days=7 * N_WEEKS - 1), freq="D")
    for _, r in rr.iterrows():
        daily_in = r["rev"] * (1 + vat[r["company_code"]]) * 12 / 365
        daily_out = r["var"] * (1 + vat[r["company_code"]]) * 12 / 365
        inflow_days = days + pd.Timedelta(days=float(r["dso"]))
        outflow_days = days + pd.Timedelta(days=30)
        for dts, amt, pos in ((inflow_days, daily_in, "Einzahlungen Neugeschäft"),
                              (outflow_days, -daily_out, "Auszahlungen Material Neugeschäft")):
            w = _week_index(pd.Series(dts))
            rows.append(pd.DataFrame(dict(company_code=r["company_code"], week=w, position=pos, eur=amt)))

    # 3b) other cash fixed costs (overheads, energy, freight; excl. personnel and depreciation):
    #     run-rate of the last 3 months, paid evenly; maintenance capex = depreciation run-rate
    oh = con.execute("""
        select j.company_code,
               sum(case when j.gl_account not in ('600000', '601000', '640000', '680000') then j.amount_eur else 0 end) / 3 as oh,
               sum(case when j.gl_account = '680000' then j.amount_eur else 0 end) / 3 as capex
        from staging.stg_s4__journal_lines j
        join staging.stg_s4__gl_accounts a on a.gl_account = j.gl_account
        where a.cm_block = 'FIX' and j.period between '2025-10' and '2025-12' group by 1""").df()
    for _, r in oh.iterrows():
        w = _week_index(pd.Series(days + pd.Timedelta(days=30)))
        rows.append(pd.DataFrame(dict(company_code=r["company_code"], week=w, position="Auszahlungen Gemeinkosten",
                                      eur=-r["oh"] * 1.15 * 12 / 365)))
        w = _week_index(pd.Series(days))
        rows.append(pd.DataFrame(dict(company_code=r["company_code"], week=w, position="Investitionen (Erhaltung)",
                                      eur=-r["capex"] * 12 / 365)))

    # 4) recurring: payroll (median of the last 6 monthly payouts without Jun/Nov bonuses),
    #    VAT payment on the 10th, interest at month end, tax prepayment on 10 March
    rec = con.execute("""
        select company_code, period, line_text, gl_account, sum(amount_eur) as eur
        from staging.stg_s4__journal_lines
        where gl_account = '180000' and period between '2025-01' and '2025-12'
          and (line_text like 'Auszahlung Löhne%' or line_text like 'USt-Voranmeldung%')
        group by all""").df()
    pay = rec[rec["line_text"].str.startswith("Auszahlung")]
    pay = pay[~pay["period"].str[5:7].isin(["06", "11"])]
    payroll = pay.groupby("company_code")["eur"].median()
    ust = rec[rec["line_text"].str.startswith("USt")].groupby("company_code")["eur"].apply(
        lambda s: s.tail(3).mean())
    fin = con.execute("""select company_code, gl_account, avg(amount_eur) eur from staging.stg_s4__journal_lines
                         where gl_account in ('750000', '770000') and period >= '2025-01' group by all""").df()
    for cc in rate:
        for month_end in ("2026-01-30", "2026-02-27", "2026-03-31"):
            rows.append(pd.DataFrame(dict(company_code=[cc], week=_week_index(pd.Series([pd.Timestamp(month_end)])),
                                          position="Löhne und Gehälter", eur=[payroll.get(cc, 0.0)])))
            i = fin[(fin.company_code == cc) & (fin.gl_account == "750000")]["eur"]
            rows.append(pd.DataFrame(dict(company_code=[cc], week=_week_index(pd.Series([pd.Timestamp(month_end)])),
                                          position="Zinsen", eur=[-float(i.iloc[0]) if len(i) else 0.0])))
        for d in ("2026-01-12", "2026-02-10", "2026-03-10"):
            rows.append(pd.DataFrame(dict(company_code=[cc], week=_week_index(pd.Series([pd.Timestamp(d)])),
                                          position="Umsatzsteuer-Zahllast", eur=[ust.get(cc, 0.0)])))
        t = fin[(fin.company_code == cc) & (fin.gl_account == "770000")]["eur"]
        rows.append(pd.DataFrame(dict(company_code=[cc], week=_week_index(pd.Series([pd.Timestamp("2026-03-10")])),
                                      position="Ertragsteuer-Vorauszahlung",
                                      eur=[-float(t.iloc[0]) * 3 if len(t) else 0.0])))

    df = pd.concat(rows, ignore_index=True)
    df = df[df["week"] <= N_WEEKS]
    out = df.groupby(["company_code", "position", "week"], as_index=False)["eur"].sum()
    bank = con.execute("""select company_code, sum(amount_eur) eur from staging.stg_s4__journal_lines
                          where gl_account = '180000' group by 1""").df().set_index("company_code")["eur"]
    out["opening_bank_eur"] = out["company_code"].map(bank)
    out["week_start"] = (WEEK1 + pd.to_timedelta((out["week"] - 1) * 7, unit="D")).dt.date
    return out


def weekly_summary(df: pd.DataFrame) -> pd.DataFrame:
    w = df.groupby(["week", "week_start"], as_index=False)["eur"].sum().rename(columns={"eur": "net_cashflow_eur"})
    opening = df.drop_duplicates("company_code")["opening_bank_eur"].sum()
    w["closing_bank_eur"] = opening + w["net_cashflow_eur"].cumsum()
    w["opening_bank_eur"] = w["closing_bank_eur"] - w["net_cashflow_eur"]
    return w


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "reports" / "out")
    a = ap.parse_args(argv)
    con = connect(read_only=False)
    df = build(con)
    con.execute("create schema if not exists forecast")
    con.register("liq", df)
    con.execute("create or replace table forecast.liquidity_13w as select * from liq")
    a.out.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out / "liquiditaet_13_wochen.csv", index=False)
    s = weekly_summary(df)
    print(s.round(0).to_string(index=False))


if __name__ == "__main__":
    main()
