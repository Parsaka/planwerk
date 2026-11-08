-- Price-volume-mix analysis of DB I, year to date, per company code x product group x
-- customer group cell, at constant currency (plan FX). Signs: positive = favourable.
--   price    = revenue - revenue at plan prices                (actual quantities)
--   var_cost = standard cost - actual variable cost            (actual quantities)
--   volume   = (V_ist / V_plan - 1) x DB I plan                (V = revenue at plan prices, per company code)
--   mix      = (DB I at plan prices/std for actual qty - DB I plan) - volume
-- The four effects add up to DB I actual (cc) - DB I plan exactly (see ADR-0001, test pvm_closes).
with months as (
    select distinct fiscal_month as to_month from {{ ref('dim_period') }}
),
cells as (
    select fiscal_year, fiscal_month, company_code, material_group, customer_group, version,
           revenue_cc_eur, var_cost_cc_eur, db1_cc_eur, revenue_at_plan_price_cc_eur, standard_cost_cc_eur, quantity
    from {{ ref('mart_contribution_margin_monthly') }}
),
ytd as (
    select c.fiscal_year, m.to_month, c.company_code, c.material_group, c.customer_group,
           sum(case when version = 'IST' then quantity else 0 end) as qty_ist,
           sum(case when version = 'PLAN' then quantity else 0 end) as qty_plan,
           sum(case when version = 'IST' then revenue_cc_eur else 0 end) as revenue_ist,
           sum(case when version = 'IST' then var_cost_cc_eur else 0 end) as var_cost_ist,
           sum(case when version = 'IST' then revenue_at_plan_price_cc_eur else 0 end) as revenue_ist_at_plan_price,
           sum(case when version = 'IST' then standard_cost_cc_eur else 0 end) as standard_cost_ist,
           sum(case when version = 'PLAN' then revenue_cc_eur else 0 end) as revenue_plan,
           sum(case when version = 'PLAN' then var_cost_cc_eur else 0 end) as var_cost_plan
    from cells c
    join months m on c.fiscal_month <= m.to_month
    group by all
),
ratio as (
    select fiscal_year, to_month, company_code,
           sum(revenue_ist_at_plan_price) / nullif(sum(revenue_plan), 0) as volume_ratio
    from ytd group by all
)
select
    y.*,
    y.revenue_ist - y.var_cost_ist as db1_ist,
    y.revenue_plan - y.var_cost_plan as db1_plan,
    y.revenue_ist - y.revenue_ist_at_plan_price as price_effect,
    y.standard_cost_ist - y.var_cost_ist as var_cost_effect,
    (r.volume_ratio - 1) * (y.revenue_plan - y.var_cost_plan) as volume_effect,
    (y.revenue_ist_at_plan_price - y.standard_cost_ist) - (y.revenue_plan - y.var_cost_plan)
        - (r.volume_ratio - 1) * (y.revenue_plan - y.var_cost_plan) as mix_effect
from ytd y
join ratio r using (fiscal_year, to_month, company_code)
