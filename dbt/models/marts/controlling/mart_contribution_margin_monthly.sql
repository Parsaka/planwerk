-- DB I per period, company code, product group and customer group for actual and budget.
-- *_eur: actual FX (budget: plan FX); *_cc_eur: constant currency at plan FX.
with ist as (
    select 'IST' as version, period, fiscal_year, fiscal_month, company_code, material_group, customer_group,
           sum(quantity) as quantity,
           sum(revenue_eur) as revenue_eur, sum(var_cost_eur) as var_cost_eur,
           sum(revenue_cc_eur) as revenue_cc_eur, sum(var_cost_cc_eur) as var_cost_cc_eur,
           sum(revenue_at_plan_price_cc_eur) as revenue_at_plan_price_cc_eur,
           sum(standard_cost_cc_eur) as standard_cost_cc_eur
    from {{ ref('fct_sales_item') }}
    group by all
),
plan as (
    select 'PLAN' as version, period, fiscal_year, cast(right(period, 2) as integer) as fiscal_month,
           company_code, material_group, customer_group,
           sum(case when gl_account in ('400000', '405000') then -quantity else 0 end) as quantity,
           sum(case when gl_account in ('400000', '405000') then -amount_eur else 0 end) as revenue_eur,
           sum(case when cm_block = 'VAR' then amount_eur else 0 end) as var_cost_eur
    from {{ ref('fct_plan_line') }}
    where cm_block in ('REV', 'VAR')
    group by all
)
select version, period, fiscal_year, fiscal_month, company_code, material_group, customer_group, quantity,
       revenue_eur, var_cost_eur, revenue_eur - var_cost_eur as db1_eur,
       revenue_cc_eur, var_cost_cc_eur, revenue_cc_eur - var_cost_cc_eur as db1_cc_eur,
       revenue_at_plan_price_cc_eur, standard_cost_cc_eur
from ist
union all
select version, period, fiscal_year, fiscal_month, company_code, material_group, customer_group, quantity,
       revenue_eur, var_cost_eur, revenue_eur - var_cost_eur,
       revenue_eur, var_cost_eur, revenue_eur - var_cost_eur,
       revenue_eur, var_cost_eur
from plan
