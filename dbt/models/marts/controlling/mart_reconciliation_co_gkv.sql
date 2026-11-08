-- Überleitung Betriebsergebnis (Controlling, Umsatzkosten-Logik der Ergebnisrechnung) zum
-- operativen Ergebnis der GuV (Gesamtkostenverfahren) per period and company code.
--   GuV operativ = Betriebsergebnis CO + Bestandsveränderungen + Periodenabgrenzung Material
-- Interest and income taxes are below the operating result and excluded on both sides.
with gkv as (
    select j.period, j.company_code,
           -sum(case when a.gkv_position not in ('13_ZINSAUFWAND', '14_STEUERN_EE') then j.amount_eur else 0 end) as gkv_operating_eur,
           -sum(case when j.gl_account = '480000' then j.amount_eur else 0 end) as inventory_change_eur,
           sum(case when j.gl_account in ('500000', '501000', '502000', '503000') then j.amount_eur else 0 end) as material_expense_eur
    from {{ ref('stg_s4__journal_lines') }} j
    join {{ ref('stg_s4__gl_accounts') }} a on a.gl_account = j.gl_account
    where not a.is_balance_sheet
    group by all
),
co as (
    select period, company_code, operating_result_eur, var_cost_eur
    from {{ ref('mart_db_statement_monthly') }} where version = 'IST'
)
select
    co.period, cast(left(co.period, 4) as integer) as fiscal_year, co.company_code,
    co.operating_result_eur as co_operating_result_eur,
    gkv.inventory_change_eur,
    co.var_cost_eur - gkv.material_expense_eur as material_timing_eur,
    gkv.gkv_operating_eur,
    gkv.gkv_operating_eur - (co.operating_result_eur + gkv.inventory_change_eur
        + co.var_cost_eur - gkv.material_expense_eur) as residual_eur
from co join gkv using (period, company_code)
