-- Primary fixed costs per cost centre, account and period for actual (IST) and budget (PLAN).
with acc as (
    select gl_account from {{ ref('stg_s4__gl_accounts') }} where cm_block = 'FIX'
),
ist as (
    select 'IST' as version, j.company_code, j.period, j.cost_centre, j.gl_account,
           sum(j.amount_lc) as amount_lc, sum(j.amount_eur) as amount_eur
    from {{ ref('stg_s4__journal_lines') }} j
    join acc on acc.gl_account = j.gl_account
    where j.cost_centre is not null
    group by all
),
plan as (
    select 'PLAN' as version, p.company_code, p.period, p.cost_centre, p.gl_account,
           sum(p.amount_lc) as amount_lc, sum(p.amount_eur) as amount_eur
    from {{ ref('stg_s4__plan_lines') }} p
    join acc on acc.gl_account = p.gl_account
    where p.cost_centre is not null
    group by all
)
-- constant currency: actuals translated at the plan rate; the budget already is at plan rate
select u.*, case when u.version = 'PLAN' then u.amount_eur else u.amount_lc / fx.plan_rate end as amount_cc_eur
from (select * from ist union all select * from plan) u
join {{ ref('int_fx_rates') }} fx on fx.company_code = u.company_code and fx.period = u.period
