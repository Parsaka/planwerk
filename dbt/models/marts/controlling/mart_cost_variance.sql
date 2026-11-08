-- Primary fixed-cost variance per cost centre and account, year to date, constant currency.
-- variance = plan - actual (positive = favourable). Responsibility view (before the BAB).
with months as (select distinct fiscal_month as to_month from {{ ref('dim_period') }}),
base as (
    select cast(left(period, 4) as integer) as fiscal_year, cast(right(period, 2) as integer) as fiscal_month,
           company_code, cost_centre, gl_account, version, amount_cc_eur
    from {{ ref('int_cost_centre_primary') }}
),
ytd as (
    select b.fiscal_year, m.to_month, b.company_code, b.cost_centre, b.gl_account,
           sum(case when version = 'PLAN' then amount_cc_eur else 0 end) as plan_cc_eur,
           sum(case when version = 'IST' then amount_cc_eur else 0 end) as actual_cc_eur
    from base b join months m on b.fiscal_month <= m.to_month
    group by all
),
cc as (select cost_centre, max(cost_centre_name) cost_centre_name, max(cm_level) cm_level,
              max(case when is_current then responsible end) responsible
       from {{ ref('dim_cost_centre') }} group by cost_centre)
select y.*, cc.cost_centre_name, cc.cm_level, cc.responsible, a.gl_account_text,
       y.plan_cc_eur - y.actual_cc_eur as variance_cc_eur
from ytd y
left join cc on cc.cost_centre = y.cost_centre
left join {{ ref('stg_s4__gl_accounts') }} a on a.gl_account = y.gl_account
