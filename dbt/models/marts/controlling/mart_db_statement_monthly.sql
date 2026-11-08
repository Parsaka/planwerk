-- Mehrstufige Deckungsbeitragsrechnung per period and company code, actual and budget.
with cm as (
    select version, period, company_code,
           sum(revenue_eur) as revenue_eur, sum(var_cost_eur) as var_cost_eur,
           sum(revenue_cc_eur) as revenue_cc_eur, sum(var_cost_cc_eur) as var_cost_cc_eur
    from {{ ref('mart_contribution_margin_monthly') }} group by all
),
deductions as (
    select 'IST' as version, j.period, j.company_code,
           sum(j.amount_eur) as deductions_eur, sum(j.amount_lc / fx.plan_rate) as deductions_cc_eur
    from {{ ref('stg_s4__journal_lines') }} j
    join {{ ref('int_fx_rates') }} fx on fx.company_code = j.company_code and fx.period = j.period
    where j.gl_account = '409000'
    group by all
    union all
    select 'PLAN', period, company_code, sum(amount_eur), sum(amount_eur)
    from {{ ref('fct_plan_line') }} where gl_account = '409000'
    group by all
),
other as (
    select 'IST' as version, j.period, j.company_code,
           sum(j.amount_eur) as other_eur, sum(j.amount_lc / fx.plan_rate) as other_cc_eur
    from {{ ref('stg_s4__journal_lines') }} j
    join {{ ref('int_fx_rates') }} fx on fx.company_code = j.company_code and fx.period = j.period
    join {{ ref('stg_s4__gl_accounts') }} a on a.gl_account = j.gl_account
    where a.cm_block = 'OTH'
    group by all
),
fixed as (
    select version, period, company_code,
           sum(case when cm_level = 'DB2' then total_eur else 0 end) as fix_db2_eur,
           sum(case when cm_level = 'DB3' then total_eur else 0 end) as fix_db3_eur,
           sum(case when cm_level = 'UNT' then total_eur else 0 end) as fix_unt_eur,
           sum(case when cm_level = 'HILF' then total_eur else 0 end) as fix_unallocated_eur,
           sum(case when cm_level = 'DB2' then total_cc_eur else 0 end) as fix_db2_cc_eur,
           sum(case when cm_level = 'DB3' then total_cc_eur else 0 end) as fix_db3_cc_eur,
           sum(case when cm_level = 'UNT' then total_cc_eur else 0 end) as fix_unt_cc_eur,
           sum(case when cm_level = 'HILF' then total_cc_eur else 0 end) as fix_unallocated_cc_eur
    from {{ ref('mart_cost_centre_monthly') }} group by all
),
base as (
    select f.version, f.period, f.company_code,
           coalesce(cm.revenue_eur, 0) as revenue_eur,
           coalesce(d.deductions_eur, 0) as sales_deductions_eur,
           coalesce(cm.var_cost_eur, 0) as var_cost_eur,
           f.fix_db2_eur, f.fix_db3_eur, f.fix_unt_eur, f.fix_unallocated_eur,
           coalesce(o.other_eur, 0) as other_eur,
           coalesce(cm.revenue_cc_eur, 0) as revenue_cc_eur,
           coalesce(d.deductions_cc_eur, 0) as sales_deductions_cc_eur,
           coalesce(cm.var_cost_cc_eur, 0) as var_cost_cc_eur,
           f.fix_db2_cc_eur, f.fix_db3_cc_eur, f.fix_unt_cc_eur, f.fix_unallocated_cc_eur,
           coalesce(o.other_cc_eur, 0) as other_cc_eur
    from fixed f
    left join cm using (version, period, company_code)
    left join deductions d using (version, period, company_code)
    left join other o using (version, period, company_code)
)
select
    version, period, cast(left(period, 4) as integer) as fiscal_year, cast(right(period, 2) as integer) as fiscal_month,
    company_code,
    revenue_eur, sales_deductions_eur, revenue_eur - sales_deductions_eur as net_revenue_eur, var_cost_eur,
    revenue_eur - sales_deductions_eur - var_cost_eur as db1_eur,
    fix_db2_eur, revenue_eur - sales_deductions_eur - var_cost_eur - fix_db2_eur as db2_eur,
    fix_db3_eur, revenue_eur - sales_deductions_eur - var_cost_eur - fix_db2_eur - fix_db3_eur as db3_eur,
    fix_unt_eur, fix_unallocated_eur, other_eur,
    revenue_eur - sales_deductions_eur - var_cost_eur - fix_db2_eur - fix_db3_eur - fix_unt_eur
        - fix_unallocated_eur - other_eur as operating_result_eur,
    revenue_cc_eur, sales_deductions_cc_eur, var_cost_cc_eur,
    revenue_cc_eur - sales_deductions_cc_eur - var_cost_cc_eur as db1_cc_eur,
    fix_db2_cc_eur, revenue_cc_eur - sales_deductions_cc_eur - var_cost_cc_eur - fix_db2_cc_eur as db2_cc_eur,
    fix_db3_cc_eur, fix_unt_cc_eur, fix_unallocated_cc_eur, other_cc_eur,
    revenue_cc_eur - sales_deductions_cc_eur - var_cost_cc_eur - fix_db2_cc_eur - fix_db3_cc_eur - fix_unt_cc_eur
        - fix_unallocated_cc_eur - other_cc_eur as operating_result_cc_eur
from base
