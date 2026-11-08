-- Bridge from budget to actual DB II and operating result, year to date, per company code and
-- for the group ('GRUPPE'). Effects in EUR, positive = favourable. residual must be 0.
with months as (select distinct fiscal_month as to_month from {{ ref('dim_period') }}),
st as (
    select s.*, m.to_month from {{ ref('mart_db_statement_monthly') }} s
    join months m on s.fiscal_month <= m.to_month
),
st_scoped as (
    select fiscal_year, to_month, company_code as scope, version,
           sum(db2_eur) db2_eur, sum(db2_cc_eur) db2_cc_eur, sum(operating_result_eur) op_eur,
           sum(operating_result_cc_eur) op_cc_eur, sum(sales_deductions_cc_eur) ded_cc,
           sum(fix_db2_cc_eur) fix2_cc, sum(fix_db3_cc_eur) fix3_cc, sum(fix_unt_cc_eur) fixu_cc,
           sum(fix_unallocated_cc_eur) fixh_cc, sum(other_cc_eur) oth_cc, sum(db1_cc_eur) db1_cc
    from st group by all
    union all
    select fiscal_year, to_month, 'GRUPPE', version,
           sum(db2_eur), sum(db2_cc_eur), sum(operating_result_eur), sum(operating_result_cc_eur),
           sum(sales_deductions_cc_eur), sum(fix_db2_cc_eur), sum(fix_db3_cc_eur), sum(fix_unt_cc_eur),
           sum(fix_unallocated_cc_eur), sum(other_cc_eur), sum(db1_cc_eur)
    from st group by all
),
pvm_company as (
    select fiscal_year, to_month, company_code as scope,
           sum(price_effect) price, sum(var_cost_effect) var_cost, sum(volume_effect) volume, sum(mix_effect) mix
    from {{ ref('mart_pvm_cells') }} group by all
),
pvm_group as (
    -- group view: volume measured against the group's plan volume, so the split differs
    -- slightly from the sum of the company codes (total is identical)
    select fiscal_year, to_month, 'GRUPPE' as scope,
           sum(price_effect) price, sum(var_cost_effect) var_cost,
           (sum(revenue_ist_at_plan_price) / sum(revenue_plan) - 1) * sum(db1_plan) as volume,
           sum(revenue_ist_at_plan_price - standard_cost_ist) - sum(db1_plan)
             - (sum(revenue_ist_at_plan_price) / sum(revenue_plan) - 1) * sum(db1_plan) as mix
    from {{ ref('mart_pvm_cells') }} group by fiscal_year, to_month
),
pvm as (select * from pvm_company union all select * from pvm_group),
i as (select * from st_scoped where version = 'IST'),
p as (select * from st_scoped where version = 'PLAN')
select
    i.fiscal_year, i.to_month, i.scope,
    p.db2_eur as plan_db2_eur,
    pvm.volume as volume_effect,
    pvm.mix as mix_effect,
    pvm.price as price_effect,
    pvm.var_cost as var_cost_effect,
    p.ded_cc - i.ded_cc as sales_deduction_effect,
    p.fix2_cc - i.fix2_cc as fixed_cost_db2_effect,
    i.db2_eur - i.db2_cc_eur as fx_effect_db2,
    i.db2_eur as actual_db2_eur,
    i.db2_eur - p.db2_eur - (pvm.volume + pvm.mix + pvm.price + pvm.var_cost + (p.ded_cc - i.ded_cc)
        + (p.fix2_cc - i.fix2_cc) + (i.db2_eur - i.db2_cc_eur)) as residual_db2,
    p.op_eur as plan_operating_result_eur,
    p.fix3_cc - i.fix3_cc as fixed_cost_db3_effect,
    p.fixu_cc - i.fixu_cc as fixed_cost_unt_effect,
    (p.fixh_cc - i.fixh_cc) + (p.oth_cc - i.oth_cc) as other_effect,
    (i.op_eur - i.op_cc_eur) as fx_effect_operating,
    i.op_eur as actual_operating_result_eur
from i
join p using (fiscal_year, to_month, scope)
join pvm using (fiscal_year, to_month, scope)
